# pylint: disable=R0912
"""
This module is used to clean up SAN: disconnect host, deregister host HBA,
disassociate LUN from a storage group, destroy storage group, delete LUN from
a storage pool or a raid group, for LUN in storage pool delete its
snapshot if exist
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import time
from argparse import ArgumentParser

from h_litp.litp_rest_client import LitpRestClient, LitpException
from litp.core.base_plugin_api import BasePluginApi
from litp.core.model_manager import ModelManager
from h_logging.enminst_logger import init_enminst_logging
from h_logging.enminst_logger import set_logging_level
from h_snapshots.snapshots_utils import SAN_TYPE_VNX
from h_util.h_utils import get_env_var, delete_file, exec_process, \
    Redfishtool, is_env_on_rack, get_nas_type

import logging

try:
    SANAPI = True
    from sanapi import *  # pylint: disable=W0401,W0614
    from sanapiexception import SanApiException
except ImportError:
    SANAPI = False

IP_A = 0
IP_B = 1
STORAGE_SITE_ID = 2
LOGIN_SCOPE = 3
SAN_TYPE = 4
USERNAME = 5
SAN_PASSW = 6
ILO_IP = 0
ILO_USER = 1
ILO_PASSWORD = 2
DEL_UNITY_LUN_TIMEOUT = 180
NOT_FOUND = 404

# TODO - CHANGE HOW THIN LUNS ARE HANDLED  # pylint: disable=fixme
THIN_LUNS_FILE = '/etc/san_luns.cfg'

NAVISECCLI = '/opt/Navisphere/bin/naviseccli'

"""
Non error return codes during cleanup

0   No error
84  The HBA UID specified is not known by the storage system
102 The host specified is not known by the storage system
116 invalid megapoll value.
"""  # pylint: disable=W0105
NAVI_GOOD_RETURN_CODES = [0, 84, 102, 116]
REDFISH = Redfishtool()


def poweroff_node(sys_bmc, node):
    """
    Power off blade

    :param sys_bmc: System BMC information
    :type sys_bmc: dict
    :param node: Node id
    :type node: str
    """
    log = logging.getLogger('enminst')
    power_state = REDFISH.power_status(sys_bmc[node][ILO_IP],
                                       sys_bmc[node][ILO_USER],
                                       sys_bmc[node][ILO_PASSWORD])
    log.info('Power state for {0}/{1} is {2}'.format(node,
                                                     sys_bmc[node][ILO_IP],
                                                     power_state))
    if power_state:
        log.info('Attempting Power off {0}'.format(node))
        output = REDFISH.toggle_power(sys_bmc[node][ILO_IP],
                                      sys_bmc[node][ILO_USER],
                                      sys_bmc[node][ILO_PASSWORD],
                                      'ForceOff')
        if output != 200:
            log.error('Failed to power off {0}. {1}'.format(node, output))
            raise SystemExit()


def poweron_node(sys_bmc, node, teardown=False):
    """
    Power on blade

    :param sys_bmc: System BMC information
    :type sys_bmc: dict
    :param node: Node id
    :type node: str
    :param teardown: is script being called by teardown
    :type boolean
    """
    log = logging.getLogger('enminst')
    node_on = True

    if teardown:
        cmd = "/usr/sbin/dmidecode -s system-product-name | /usr/bin/tail -1" \
              " | /bin/grep Virtual"
        try:
            stdout = exec_process(cmd, use_shell=True)

            if "Virtual" in stdout:
                return node_on
        except IOError:
            pass
    power_state = REDFISH.power_status(sys_bmc[node][ILO_IP],
                                           sys_bmc[node][ILO_USER],
                                           sys_bmc[node][ILO_PASSWORD])
    log.info('Power state for {0}/{1} is {2}'.format(node,
                                                     sys_bmc[node][ILO_IP],
                                                     power_state))
    if not power_state:
        node_on = False
        log.info('Attempting Power on {0}'.format(node))
        output = REDFISH.toggle_power(sys_bmc[node][ILO_IP],
                                      sys_bmc[node][ILO_USER],
                                      sys_bmc[node][ILO_PASSWORD], 'On')
        if output != 200:
            log.error('Failed to power on {0}. {1}'.format(node, output))
            raise SystemExit()

    if teardown:
        log.info('Power status for node:{0} is : {1}'.format(
            node, node_on))
        return node_on


class NavisecCliException(Exception):
    """
    Naviseccli command exception
    """
    pass


class SanCleanup(object):
    """
    Provide mechanism to cleanup SAN
    """

    def __init__(self, logger_name='enminst'):
        """
        Initialise LitpRestClient, ModelManager and BasePluginApi
        """
        self.log = logging.getLogger(logger_name)
        self.rest = LitpRestClient()
        self.model_manager = ModelManager()
        self.base_api = BasePluginApi(self.model_manager)
        self.nas_type_name = get_nas_type(self.rest)

    def find_items(self, path, item_type, items):
        """
        Find all items of a certain type
        :param path: Search start point in the model
        :type path: str
        :param item_type: An item type, e.g. 'sfs-service'
        :type item_type: str
        :param items: An initial list of items, it can be an empty list
        :items type: list
        :return: An item list of a certain type
        :rtype: list
        """
        try:
            item = self.rest.get(path, log=False)
            if item['item-type-name'] == item_type:
                items.append(item)
            for item in self.rest.get_children(path):
                self.find_items(item['path'], item_type, items)
        except LitpException as err:
            _code = err.args[0]
            if _code == NOT_FOUND:
                self.log.info('Path not found: %s', path)
                return items
            self.log.error(err)
            raise
        return items

    def get_san_info(self):
        """
        Obtain SAN information from the LITP model

        :return: SAN provider information
        {san : [spa_ip, spb_ip, san_site_id, login_scope, san_type, username,
                password]}
        :rtype: dict
        """
        self.log.info('Get SAN details')
        san_info = {}
        path = '/infrastructure/storage/storage_providers'
        items = self.find_items(path, 'san-emc', [])

        for item in items:
            if item['properties']['san_type'].upper().startswith(SAN_TYPE_VNX):
                ip_b = item['properties']['ip_b']
            else:
                # For unity IP B is ignored, but we still need to set it for
                # now until some refactoring of the code is done
                ip_b = item['properties']['ip_a']

            pass_key = item['properties']['password_key']
            username = item['properties']['username']
            san_passw = self.base_api.get_password(pass_key, username)
            san_info[item['id']] = [
                item['properties']['ip_a'],
                ip_b,
                item['properties']['storage_site_id'],
                item['properties']['login_scope'],
                item['properties']['san_type'],
                username,
                san_passw]
        return san_info

    def build_sg_names(self):
        """
        Compose the storage group name. The SG name does not include
        the SAN site ID
        :return: Collection of hosts / storage group names
        :rtype: dict
        """
        self.log.debug('Gathering information from each node')
        sg_names = {}
        all_nodes = self.rest.get_cluster_nodes()
        for cluster_name, nodes in all_nodes.items():
            for node in nodes.values():
                hostname = node.get_property('hostname')
                sg_names[hostname] = {
                    'deployment': node.path.split('/')[2],
                    'cluster_name': cluster_name,
                    'node_id': node.item_id
                }
        return sg_names

    def get_sys_bmc(self):
        """
        Obtain system BMC information from the LITP model

        :return: Collection of nodes / BMC information
        {node : [iLo_ip_address, iLo_username, iLo_password]}
        :rtype: dict
        """
        self.log.info('Get systems BMC information')
        systems = []
        sys_bmc = {}
        path = '/infrastructure/systems'
        items = self.find_items(path, 'blade', [])
        for item in items:
            systems.append(item['properties']['system_name'])
        for node in systems:
            path = '/infrastructure/systems/{0}_system/bmc'.format(node)
            item = self.rest.get(path, log=False)
            pass_key = item['properties']['password_key']
            username = item['properties']['username']
            raw_password = self.base_api.get_password(pass_key, username)
            sys_bmc[node] = [
                item['properties']['ipaddress'],
                username,
                raw_password]
        return sys_bmc

    def delete_luns(self, san_api, all_luns):
        """
        Delete LUNs with the specified IDs from a storage pool or a raid group

        :param san_api: An object representing the appropriate array type
        :type san_api: apiObj
        :param all_luns: A list of LUN IDs previously disassociated
         from a storage group
        :type all_luns: list
        :return: deleted_luns - list of deleted LUNs
        """
        self.log.info('Delete LUNs %s', all_luns)
        deleted_luns = []
        for lun in all_luns:
            lun_obj = san_api.get_lun(lun_id=lun)
            try:
                if lun_obj.type == 'StoragePool':
                    san_api.delete_lun(
                        lun_id=lun, array_specific_options='-destroySnapshots '
                                                           '-forceDetach')
                    deleted_luns.append(lun)
                elif lun_obj.type == 'RaidGroup':
                    san_api.delete_lun(lun_id=lun)
                    deleted_luns.append(lun)
            except SanApiException as ex:
                self.log.exception('Failed to delete LUN %s: %s', lun, ex)
        return deleted_luns

    def delete_unity_luns(self, san_api, all_luns):
        """
        Delete Unity LUNs with the specified IDs

        :param san_api: An object representing the appropriate array type
        :type san_api: apiObj
        :param all_luns: A list of LUN IDs previously disassociated
         from a storage group
        :type all_luns: list
        :return: deleted_luns - list of deleted LUNs
        """
        self.log.info('Delete LUNs: %s', all_luns)
        deleted_luns = []
        for lun in all_luns:
            timeout = time.time() + DEL_UNITY_LUN_TIMEOUT
            while time.time() < timeout:
                if not san_api.get_snapshots(lun_id=lun):
                    try:
                        self.log.info('Delete LUN %s', lun)
                        san_api.delete_lun(lun_id=lun)
                        deleted_luns.append(lun)
                        break
                    except SanApiException as ex:
                        self.log.exception('Failed to delete LUN %s: %s',
                                           lun, ex)
                        break
                else:
                    time.sleep(10)
                    self.log.info('LUN %s has still snapshot', lun)
        return deleted_luns

    def delete_unity_snapshots(self, san_api, all_luns):
        """
        Delete snapshots of the Unity LUNs

        :param all_luns: A list of LUN IDs previously disassociated
         from a storage group
        :type all_luns: list
        :param san_api: An object representing the appropriate array type
        :type san_api: apiObj
        """
        all_snaps = [s.snap_name for s in san_api.get_snapshots()
                     if s.resource_id in all_luns]
        self.log.info('Delete snapshosts %s', all_snaps)
        for snap in all_snaps:
            self.log.info('Delete snapshot %s', snap)
            try:
                san_api.delete_snapshot(snap)
            except SanApiException as ex:
                self.log.exception('Failed to delete snapshot %s: %s',
                                   snap, ex)

    def delete_unity_pool(self, san_api):
        """
        Delete the Storage Pool

        :param san_api: An object representing the appropriate array type
        :type san_api: apiObj
        """
        path = '/infrastructure/storage/storage_providers/'
        items = self.find_items(path, 'storage-container', [])
        for item in items:
            if item['properties']['type'] == 'POOL':
                sp_name = item['properties']['name']
            try:
                if not san_api.check_storage_pool_exists(sp_name):
                    self.log.warning("Storage pool doesn't exist,"
                                     " skipping deletion.")
                else:
                    self.log.info('Deleting pool %s', sp_name)
                    san_api.delete_storage_pool(sp_name)
            except SanApiException as ex:
                self.log.exception('Failed to delete pool %s: %s'
                                   ', SAN cleanup failed',
                                   sp_name, ex)
                raise SystemExit(1)

    def clean_navi_certs(self):
        """
        Remove any existing Naviseccli security certs as they can
        cause issues (SAN plugin for example) if a hardware
        change occurs on LMS in between installation attempts.

        Note: San plugin creates certs under '/'
              Running Naviseccli directly creates certs under '/root'
              Certs need to be removed from both places.

        :param:
        :return: None
        """
        self.log.info('Checking for existing Naviseccli certs')
        cert_search_paths = ('/', '/root')
        for spath in cert_search_paths:
            self.remove_navi_certs(spath)
            self.log.info('Naviseccli security certs removed from \'{0}\''
                          .format(spath))

    def remove_navi_certs(self, home_dir):
        """
        Remove Naviseccli security certificates from a particular location
        :param home_dir: home dir to set for naviseccli command. This
                         determines the location from where certs are
                         removed.
        :type home_dir: str
        :return: None
        """
        set_home_env_sub_cmd = 'export HOME={0}'.format(home_dir)
        cmd = '{0}; {1} security -certificate -cleanup' \
              .format(set_home_env_sub_cmd, NAVISECCLI)
        self.log.debug('Executing remove_navi_certs with cmd {0}'.format(cmd))
        try:
            exec_process(cmd, use_shell=True)
        except IOError as ex:
            error_msg = 'Error occured removing certificates. Original ' \
                        'exception: {0}'.format(str(ex))
            self.log.error(error_msg)
            raise NavisecCliException(1, error_msg)

    def get_data_luns(self):
        """
        Get LUNs names from the LITP model
        """
        self.log.info('Get LUNs from model')
        luns = []
        path = '/infrastructure/systems'
        items = self.find_items(path, 'lun-disk', [])
        for item in items:
            luns.append(item['properties']['lun_name'])
        return luns

    def get_fencing_disks(self):
        """
        Get fencing disks from the LITP model
        """
        luns = []
        deployment_clusters = self.rest.get_deployment_clusters()
        for deployment, clusters in deployment_clusters.items():
            for cluster in clusters:
                path = '/deployments/{0}/clusters/{1}/fencing_disks'.format(
                    deployment, cluster)
                fencing_disks = self.find_items(path, 'lun-disk', [])
                for fen in fencing_disks:
                    luns.append(fen['properties']['lun_name'])
        return luns


def teardown_san(exclude_nas=None):  # pylint: disable=R0914,R0912,R0915
    """
    Set up logging level. Initilise class SanCleanup. Call all required
    functions to clean down SAN
    :param exclude_nas: A list of NAS filesystems to be excluded from
                        the teardown.
    :type exclude_nas: list
    """
    logger = init_enminst_logging()
    try:
        log_level = get_env_var('LOG_LEVEL')
        set_logging_level(logger, log_level)
    except KeyError:
        set_logging_level(logger, 'DEBUG')

    logger.info('Beginning SAN cleanup')
    san_cleanup = SanCleanup()
    san_info = san_cleanup.get_san_info()
    sys_bmc = san_cleanup.get_sys_bmc()
    sg_names = san_cleanup.build_sg_names()
    model_luns = san_cleanup.get_data_luns()
    model_luns.extend(san_cleanup.get_fencing_disks())

    if not SANAPI:
        logger.warning('The SANAPI is not installed on the LMS.'
                       ' Skip the SAN cleanup')
        return

    clean_navi_certs = False
    delete_unity_pool = False

    if is_env_on_rack() and san_cleanup.nas_type_name == "unityxt" \
            and exclude_nas is None:
        delete_unity_pool = True

    if not san_info or not sys_bmc or not sg_names:
        logger.warning('Either it is a cloud environment or the LITP model '
                       'is empty. Exiting SAN cleanup')
        return
    for san in san_info:
        san_id = san_info[san][STORAGE_SITE_ID]
        san_api = api_builder(san_info[san][SAN_TYPE], logger)

        if san_info[san][SAN_TYPE].upper().startswith(SAN_TYPE_VNX):
            is_vnx = True
            clean_navi_certs = True
            ips = (san_info[san][IP_A], san_info[san][IP_B])
        else:
            is_vnx = False
            ips = (san_info[san][IP_A],)

        san_api.initialise(ips,
                           san_info[san][USERNAME],
                           san_info[san][SAN_PASSW],
                           san_info[san][LOGIN_SCOPE],
                           esc_pwd=True)

        san_sg_objs = san_api.get_storage_groups()
        if not san_sg_objs:
            logger.info('No Storage groups defined on array %s', san_id)
        san_sg_list = [san_sg.name for san_sg in san_sg_objs]

        for host in sg_names:
            node = sg_names[host]['node_id']
            sg_name = '{0}-{1}-{2}-{3}'.format(
                san_id, sg_names[host]['deployment'],
                sg_names[host]['cluster_name'], sg_names[host]['node_id'])
            if sg_name not in san_sg_list:
                continue
            if node in sys_bmc.keys():
                poweroff_node(sys_bmc, node)

            try:
                sg_obj = [sg for sg in san_sg_objs
                          if sg.name == sg_name][0]
            except IndexError:
                continue

            san_api.disconnect_host(sg_name, host)

            if is_vnx:
                # Unity teardown does not need these operations
                if sg_obj.hbasp_list:
                    sg_hba_uids = set([hba.hbauid for hba in
                                       sg_obj.hbasp_list])

                    all_hbas = [hba.hbauid for hba in
                                san_api.get_hba_port_info()]

                    for hba_uid in sg_hba_uids:
                        if hba_uid in all_hbas:
                            san_api.deregister_hba_uid(hba_uid)

                if sg_obj.hlualu_list:
                    san_api.remove_luns_from_storage_group(sg_name,
                                                           sg_obj.hlualu_list)

            san_api.delete_storage_group(sg_name)

            if node in sys_bmc.keys():
                poweron_node(sys_bmc, node)

        all_luns = [lun_obj.id for lun_obj in san_api.get_luns()
                    if lun_obj.name in model_luns]
        all_luns = list(set(all_luns))
        if not all_luns:
            logger.info('No LUNs to be deleted on %s', san_id)
            continue
        if is_vnx:
            deleted_luns = san_cleanup.delete_luns(san_api, all_luns)
        else:
            san_cleanup.delete_unity_snapshots(san_api, all_luns)
            deleted_luns = san_cleanup.delete_unity_luns(san_api, all_luns)
        failed_delete = set(all_luns) - set(deleted_luns)
        if failed_delete:
            logger.warning('Failed to delete the folowing LUNs %s',
                           failed_delete)
            logger.warning('SAN cleanup has not completed successfully')
            raise SystemExit(1)
        else:
            logger.info('All LUNs successfully deleted')

    delete_file(THIN_LUNS_FILE)

    if delete_unity_pool:
        san_cleanup.delete_unity_pool(san_api)

    if clean_navi_certs:
        san_cleanup.clean_navi_certs()

    logger.info('SAN cleanup finished successfully')


def main():
    """
    Main function. Call teardown_san cleanup function
    """
    parser = ArgumentParser(description='Script to clean down SAN')
    parser.add_argument('-y', action='store_true', dest='yes_option',
                        required=True,
                        help='Execute the SAN clean down procedure')
    args = parser.parse_args()
    if args.yes_option:
        teardown_san()
    else:
        parser.print_usage()
        raise SystemExit(2)


if __name__ == '__main__':
    main()
