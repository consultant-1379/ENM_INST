# pylint: disable=C0302,R0801
"""
Module to handle various ENM snapshot actions
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
import logging
import os
import shutil
import sys
from copy import deepcopy
from datetime import datetime
from multiprocessing.pool import ThreadPool
from os import makedirs
from os.path import exists, isfile, dirname
from time import sleep
from socket import gethostname

from argparse import ArgumentParser
from simplejson import dump, load

import import_iso
import sanapiexception  # pylint: disable=F0401
from clean_san_luns import SanCleanup, IP_A, IP_B, LOGIN_SCOPE, USERNAME, \
    SAN_PASSW, SAN_TYPE, STORAGE_SITE_ID
from deployer import Deployer
from deployment_teardown import CleanupDeployment
from h_litp.litp_rest_client import LitpRestClient, LitpException
from h_litp.litp_utils import main_exceptions, LitpObject
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_puppet import h_puppet
from h_puppet.h_puppet import discover_all_nodes
from h_puppet.mco_agents import EnminstAgent, McoAgentException
from h_snapshots.litp_snapshots import LitpSnapshots
from h_snapshots.lvm_snapshot import LVMSnapshots
from h_snapshots.san_snapshot import VNXSnap
from h_snapshots.sfs_snapshot import SfsSnapshots
from h_snapshots.snap_agent import SnapAgents
from h_util import h_utils
from h_util.h_utils import (exec_process, keyboard_interruptable,
                            read_enminst_config, ExitCodes, touch, time_delta,
                            Decryptor, delete_file, sanitize,
                            kill_processes_dir, Redfishtool,
                            exec_process_via_pipes)
from h_vcs.vcs_cli import Vcs
from h_vcs.vcs_utils import discover_vcs_clusters, is_dps_using_neo4j
from sanapi import api_builder
from h_snapshots.lvm_snapshot import RHEL7_NODE_LIST_FILE, MIGRATION_LOCK_FILE
from litp.core.rpc_commands import run_rpc_command

DEFAULT_SNAP_PREFIX = 'Snapshot'
WAIT_VCS_SYS_UPDATE = 85

_LOGGER = None
_CACTION = None
_BLADE_INFO = 'blade_info'
_REMOVED_BLADES_INFO = 'removed_blades_info'
_EXCLUDED_LUNS = ['elasticsearchdb', 'versant_bur']

UPGRADE_SNAPSHOTS_TAKEN = 'upgrade_snapshots_taken'
ITRP_MSG = {
    'create_snapshot': 'CTRL-C: Interrupted creating snapshots, run the'
                       ' remove_snapshot action to remove partially '
                       'created snapshots.',
    'remove_snapshot': 'CTRL-C: Interrupted removal of snapshots, not '
                       'all snapshots may have been removed, rerun the '
                       'remove_snapshot action to remove any remaining '
                       'snapshots.',
    'restore_snapshot': 'CTRL-C: Interrupted restoration of snapshots, not '
                        'all snapshots may have been restored!',
    'restore_snapshot.error': None
}

DATA_PATH = '/ericsson/tor/data'


def set_current_action(action):
    """
    Set the current action
    :param action: The action name
    :return:
    """
    global _CACTION  # pylint: disable=W0603
    _CACTION = action


def get_current_action():
    """
    Get the current action
    """
    global _CACTION  # pylint: disable=W0602
    return _CACTION


def check_blade_info_file_exists():
    """
    Check if the blade info file exists under enminst runtime directory.

    :return: True if file exists, False if not
    :rtype: bool
    """
    blade_info_filename = get_blade_info_filename()
    return isfile(blade_info_filename)


def check_removed_blades_info_file_exists():  # pylint: disable=C0103
    """
    Check if the removed blades info file exists in enminst runtime directory.

    :return: True if file exists, False if not
    :rtype: bool
    """
    removed_blades_info_filename = get_removed_blades_info_filename()
    return isfile(removed_blades_info_filename)


def check_snapshots_indicator_file_exists():  # pylint: disable=C0103
    """
    Checks for the existance of the snapshot flag file that gets created as
    part of the ENM Upgrade orchestration script.

    :returns: ``True`` if snapshots_indicator_filename exists and ``False``
     if not.

    :rtype: bool
    """
    snapshots_indicator_filename = get_snapshots_indicator_filename()
    return isfile(snapshots_indicator_filename)


def create_blade_info_file():
    """
    Create the blade info file with a list of blades defined in the model at
    the time snapshots were taken
    :return:
    """
    blade_info_filename = get_blade_info_filename()
    litp = LitpRestClient()
    items = litp.get_items_by_type('/infrastructure/systems', 'blade', [])
    nodes = [item['data']['properties']['system_name'] for item in items]
    with open(blade_info_filename, 'w') as _writer:
        dump(nodes, _writer)


def create_removed_blades_info_file():
    """
    Persist the removed blades runtime file
    :return: None
    """
    removed_nodes = h_utils.get_removed_nodes()
    litp = LitpRestClient()
    removed_blades = {}

    for cluster_path in h_utils.get_removed_clusters():
        for node in litp.get_children('{0}/nodes'.format(cluster_path)):
            if node['path'] not in removed_nodes:
                removed_nodes.append(node['path'])

    for node_path in removed_nodes:
        node_path_elements = node_path.split('/')
        node_id = node_path_elements[-1]
        cluster_name = node_path_elements[4]
        obj = LitpObject(None, litp.get(node_path), litp.path_parser)
        bmc = LitpObject(None, litp.get('{0}/system/bmc'.format(obj.path)),
                         litp.path_parser)

        removed_blades[node_id] = {
            'cluster': cluster_name,
            'hostname': obj.get_property('hostname'),
            'username': bmc.get_property('username'),
            'iloaddress': bmc.get_property('ipaddress'),
            'password': bmc.get_property('password_key')
        }

    removed_blades_info_filename = get_removed_blades_info_filename()
    with open(removed_blades_info_filename, 'w') as _writer:
        dump(removed_blades, _writer)


def create_snapshots_indicator_file():
    """
    Create the snapshot flag file that's used as part of the ENM Upgrade
    orchestration script.

    """
    snapshots_indicator_filename = get_snapshots_indicator_filename()
    touch(snapshots_indicator_filename)
    if get_logger():
        get_logger().info('Touched {0}'.format(snapshots_indicator_filename))


def get_blade_info_filename():
    """
    Get the name of the blade info file.

    :returns: Absolute path to blade info file (runtime dir+filename)
    :rtype: str
    """
    config = read_enminst_config()
    property_enminst_runtime = config['enminst_runtime']
    return '{0}/{1}'.format(property_enminst_runtime, _BLADE_INFO)


def get_removed_blades_info_filename():  # pylint: disable=C0103
    """
    Get the name of the removed blades info file.

    :returns: Absolute path to removed blade info file (runtime dir+filename)
    :rtype: str
    """
    config = read_enminst_config()
    property_enminst_runtime = config['enminst_runtime']
    return '{0}/{1}'.format(property_enminst_runtime, _REMOVED_BLADES_INFO)


def get_snapshots_indicator_filename():  # pylint: disable=C0103
    """
    Get the name of the snapshot flag file that's used as part of the
    ENM Upgrade orchestration script.

    :returns: Absolute path to snapshot flag file(runtime dir+filename)
    :rtype: str
    """
    config = read_enminst_config()
    property_enminst_runtime = config['enminst_runtime']
    return '{0}/{1}'.format(property_enminst_runtime, UPGRADE_SNAPSHOTS_TAKEN)


def remove_blade_info_file():
    """
    Remove the blade info file.

    """
    blade_info_filename = get_blade_info_filename()
    delete_file(blade_info_filename)


def remove_removed_blades_info_file():
    """
    Remove the persisted removed blades info file
    """
    removed_blades_info_filename = get_removed_blades_info_filename()
    delete_file(removed_blades_info_filename)


def remove_snapshots_indicator_file():
    """
    Remove the snapshot flag file that's used as part of the ENM Upgrade
    orchestration script.

    """
    snapshots_indicator_filename = get_snapshots_indicator_filename()
    try:
        os.remove(snapshots_indicator_filename)
        if get_logger():
            get_logger().info('Removed {0}'.format(
                snapshots_indicator_filename))
    except OSError:
        pass


class EnmSnapException(Exception):
    """
    Enm Snapshot failure
    """
    pass


class EnmSnap(object):  # pylint: disable=R0902,R0904
    """
    Class to pre snapshot operations i.e get required credentials,power off/on
    nodes
    """

    INFRA_STORAGE_PROVIDERS = '/infrastructure/storage/storage_providers'
    INFRA_SYSTEMS = '/infrastructure/systems'
    ITEM_TYPE_LUN_DISK = 'lun-disk'
    ITEM_TYPE_SAN_EMC = 'san-emc'
    ITEM_TYPE_NAS_SVC = 'sfs-service'

    SWFK_INFO_FILE = '/ericsson/tor/data/enmbur/enmrestoredata.txt'
    SWFK_DIR_RM = '/ericsson/tor/data/enmbur/sfwk-restoreinfo/'

    def __init__(self, config, num_of_threads=10, log_silent=False):
        """
        Set up the logging , security api and initialize cred dicts
        :param config: enm inst config
        :type config: dict
        :param num_of_threads: number of threads that can be used for
         thread pool
        :type num_of_threads: int
        :param log_silent: disable logging to enminst log
        :type log_silent: boolean
        """

        self.litp = LitpRestClient()
        self.nas_cred = dict()
        self.node_cred = dict()

        if log_silent:
            self.logger = logging.getLogger('enmsnapshots')
        else:
            self.logger = logging.getLogger('enminst')

        self.decrypt = Decryptor()
        self.lun_list_bkup = '%s/lun_list_bkup.txt' \
                             % config['enminst_runtime']
        self.lms_vol_bkup = '%s/lms_vol_list_bkup.txt' \
                            % config['enminst_runtime']
        self.node_vol_bkup = '%s/node_vol_list_bkup.txt' \
                             % config['enminst_runtime']
        self.sfs_share_list = '%s/sfs_share_list.txt' \
                              % config['enminst_runtime']
        self.sfs_fs_bkup = '%s/sfs_fs_bkup.txt' \
                           % config['enminst_runtime']
        self.num_of_threads = num_of_threads

    def get_psw(self, psw_key, user, sanitise=True):
        """
        Get the decrypted password
        :param psw_key: The key to use
        :param user: The user of the password
        :param sanitise: Make the string shell safe by inserting escape
        characters
        :return: Either decrypted or sanitized decrypted password
        """
        if sanitise:
            return sanitize(self.decrypt.get_password(psw_key, user))
        return self.decrypt.get_password(psw_key, user)

    def get_san_cred(self):
        """
        Execute LITP command on the LMS and parse the output to build up
        san credential.

        :return: san_cred
        :type: dict()
        """
        pool_name = self.get_systems_storage_container()
        if pool_name is None:
            return None
        self.logger.debug('SAN StoragePool is {0}'.format(pool_name))
        san_creds = None
        it_storage_container = 'storage-container'
        k_itn = 'item-type-name'
        for stor_prov in self.litp.get_children(self.INFRA_STORAGE_PROVIDERS):
            if stor_prov['data'][k_itn] == self.ITEM_TYPE_SAN_EMC:
                contains_pool = False
                for container in self.litp.get_children(
                        '{0}/storage_containers'.format(stor_prov['path'])):
                    item_type = container['data'][k_itn]
                    is_type = item_type == it_storage_container
                    props = container['data']['properties']
                    if is_type and props['name'] == pool_name:
                        contains_pool = True
                if not contains_pool:
                    continue
                properties = stor_prov['data']['properties']
                san_creds = {
                    'san_user': properties['username'],
                    'san_spa_ip': properties['ip_a'],
                    'san_spb_ip': properties['ip_b'],
                    'san_login_scope': properties['login_scope'],
                    'san_psw': self.get_psw(properties['password_key'],
                                            properties['username'],
                                            sanitise=False),
                    'san_type': properties['san_type'],
                    'san_pool': pool_name
                }
                break
        if not san_creds:
            raise EnmSnapException('Could not find a model entry for a san-emc'
                                   ' item called {0}'.format(pool_name))
        self.logger.debug('San credentials build up successfully for {0}'
                          ''.format(pool_name))
        return san_creds

    def get_removed_node_cred(self):
        """
       Execute LITP command on the LMS and parse the output to build up
       a dictionary of credentials for removed nodes.
       :return: node_cred
       :type: dict()
       """
        # pylint: disable=E1103
        if check_removed_blades_info_file_exists():
            with open(get_removed_blades_info_filename(), 'r') as _reader:
                removed_nodes = load(_reader)
            for node, data in removed_nodes.items():
                self.node_cred[node] = {
                    'username': data.get('username'),
                    'iloaddress': data.get('iloaddress'),
                    'password': self.get_psw(
                            data.get('password'), data.get('username'))
                }
        else:
            self.logger.error("Unable to read {0}".
                              format(_REMOVED_BLADES_INFO))
        return self.node_cred

    def get_nas_cred(self):
        """
        Execute LITP command on the LMS and parse the output to build up
        nas credential.
        :return: nas_cred
        :type: dict()
        """
        sfs_properties = self.get_nas_service_container()
        creds = None
        if sfs_properties:
            creds = {'nas_name': sfs_properties['name'],
                     'nas_console': sfs_properties['management_ipv4'],
                     'nas_supuser': sfs_properties['user_name'],
                     'nas_supsw': self.get_psw(sfs_properties['password_key'],
                                               sfs_properties['user_name'],
                                               sanitise=False),
                     'nas_pool': sfs_properties['pool_name']}
        return creds

    def get_node_cred(self):
        """
       Execute LITP command on the LMS and parse the output to build up
       managed nodes credential.
       :return: node_cred
       :type: dict()
       """
        node = self.litp.get(self.INFRA_SYSTEMS, log=False)

        removed_blades = []
        if check_removed_blades_info_file_exists():
            removed_blades = self.load_list(get_removed_blades_info_filename())

        for item in node['_embedded']['item']:
            if (
                item['item-type-name'] == 'blade' and
                item['properties']['system_name'] not in removed_blades
            ):
                self.node_cred[item['properties']['system_name']] = \
                    {'id': item['id']}
        for name in self.node_cred:
            path = '{0}/{1}/bmc'.format(self.INFRA_SYSTEMS,
                                        self.node_cred[name]['id'])
            node = self.litp.get(path, log=False)['properties']
            self.node_cred[name]['username'] = node['username']
            self.node_cred[name]['iloaddress'] = node['ipaddress']
            self.node_cred[name]['password'] = \
                self.get_psw(node['password_key'], node['username'], \
                             sanitise=False)
        return self.node_cred

    def shutdown_nodes(self,  # pylint: disable=R0914,R0912
                       redfish, node_cred, timeout=60):
        """
        Power off all the managed nodes in threads
        :param redfish: instance of ippmi class
        :type redfish: instance of class
        :param node_cred: nodes ip,user name,password
        :type node_cred: dict()
        :param timeout: timeout to wait for redfish command to succeed
        :type timeout: int
        :return: node_cred
        :type: dict()
        """
        self.manage_lms_services('stop', ['puppet', 'httpd', 'crond'])
        self.manage_lms_services('stop', ['consul'],
                                 skip_uninstalled_service=True)
        # If restoring snapshot after db cluster expansion, shutdown db-3 and
        # db-4 and wait for fencing keys to get cleared
        temp_node_cred = deepcopy(node_cred)
        if check_blade_info_file_exists():
            wait_to_update_cluster = False
            clean_vxfen_keys_nodes = set(['db-3', 'db-4'])
            blade_snapshot = self.load_list(get_blade_info_filename())
            for node in clean_vxfen_keys_nodes.difference(set(blade_snapshot)):
                if node in node_cred:
                    self.poweroff_node(redfish, node, node_cred,
                                       timeout=timeout)
                    del temp_node_cred[node]
                    wait_to_update_cluster = True
            if wait_to_update_cluster:
                self.logger.info('Wait until DB cluster updates systems state')
                sleep(WAIT_VCS_SYS_UPDATE)

        thread_pool = ThreadPool(processes=self.num_of_threads)
        thread_results = []

        def report(result):
            """
            Add results to list
            :param result: Thread result tuple
            :return:
            """
            thread_results.append(result)

        try:
            for node in temp_node_cred:
                thread_pool.apply_async(self.poweroff_node, args=(
                    redfish, node, temp_node_cred, timeout), callback=report)
            thread_pool.close()
            thread_pool.join()
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise
        if not thread_results:
            raise EnmSnapException('Shutdown nodes threads did not return'
                                   ' any result')
        all_ok = True
        for success, exception, node in thread_results:
            if not success:
                all_ok = False
                if exception:
                    self.logger.error('{0}'.format(exception))
        if not all_ok:
            raise EnmSnapException('Shutdown nodes failed')

        if len(temp_node_cred) != len(thread_results):
            node_results = dict(temp_node_cred)
            for success, exception, node in thread_results:
                del node_results[node]
            for node in node_results:
                self.logger.error('Shutdown node thread for {0} did not '
                                  'return any result'.format(node))
            raise EnmSnapException('All the shutdown nodes threads did not '
                                   'return with result')
        self.logger.info('All the nodes are shut down successfully')

    def poweroff_node(self, redfish, node, node_cred, timeout):
        """
        Power off the managed node
        :param redfish: instance of redfish class
        :type redfish: instance of class
        :param node_cred: nodes ip,user name,password
        :type node_cred: dict()
        :param node: node name to be shut down
        :type node: string
        :param timeout: timeout to wait for redfish command to succeed
        :type timeout: int
        :return: result with node name
        :type: tuple
       """
        try:
            ilo_address = node_cred[node]['iloaddress']
            username = node_cred[node]['username']
            password = node_cred[node]['password']
            power_status = redfish.power_status(ilo_address, username,
                                                password)
            if power_status:
                self.logger.info('Powering off system {0}'.format(node))
                redfish.toggle_power(ilo_address, username, password,
                                     'ForceOff')
                elapsed_time = 0
                while True:
                    if elapsed_time > timeout:
                        raise EnmSnapException('Timeout waiting for node {0} '
                                               'to power off'.format(node))
                    if not redfish.power_status(ilo_address, username,
                                                  password):
                        break

                    sleep(2)
                    elapsed_time += 2
            else:
                self.logger.info('System {0} is already powered off'.
                                 format(node))
        except Exception as err:  # pylint: disable=W0703
            self.logger.error('System {0} power off failed with error {1}'
                              .format(node, str(err)))
            return False, str(err), node
        return True, None, node

    def manage_lms_services(self, action, services,
                            skip_uninstalled_service=False):
        """
        Manages services on LMS
        :param action : stop/start the services
        :param skip_uninstalled_service: Should error be ignored if service not
         installed
        :type action: string
        """
        self.logger.info('{0} LMS service(s) : {1}'.format(action, ' '
                                                        .join(services)))
        for service in services:
            cmd = ['service', service, action]
            try:
                exec_process(cmd)
            except IOError as err:
                _msg = str(err)
                if 'unrecognized service' in _msg and \
                        skip_uninstalled_service:
                    self.logger.warning('Skipping Service {0} as not '
                                        'installed...'.format(service))
                else:
                    raise

    def check_puppet_catalog(self):
        """
        Wait for puppet to complete all ongoing catalog runs on all nodes in
         the deployment.

        """
        all_nodes = discover_all_nodes()
        self.logger.info('Waiting for ongoing puppet catalog runs '
                         'to complete on {0}'.format(', '.join(all_nodes)))
        h_puppet.puppet_trigger_wait(False, self.logger.info,
                                     host_list=all_nodes)
        self.logger.info('All completed.')

    def power_up_node(self,  # pylint: disable=R0913
                      redfish, node, node_cred, timeout, ignore_if_on):
        """
        Power on  managed node
        :param redfish: instance of redfish class
        :type redfish: instance of class
        :param node: The node to power up
        :param node_cred: nodes ip,user name,password
        :type node_cred: dict()
        :param timeout: timeout to wait for redfish command to succeed
        :type timeout: int
        :param ignore_if_on: flag to skip power on if node already powered on
        :type ignore_if_on: boolean
        :return: Result and node name
        :type: tuple
        """
        try:
            ilo_address = node_cred[node]['iloaddress']
            username = node_cred[node]['username']
            password = node_cred[node]['password']
            power_status = redfish.power_status(ilo_address, username,
                                                password)
            if power_status:
                if not ignore_if_on:
                    raise EnmSnapException('System {0} is already powered on'.
                                           format(node))
                else:
                    self.logger.info('System {0} is already powered on.'.
                                     format(node))
                    return True, None, node
            self.logger.info('Powering on system {0}'.format(node))
            redfish.toggle_power(ilo_address, username, password, 'On')
            elapsed_time = 0
            while True:
                if elapsed_time > timeout:
                    raise EnmSnapException('Timeout waiting for node {0}'
                                           ' to power on'.format(node))
                if redfish.power_status(ilo_address, username,
                                              password):
                    break

                sleep(2)
                elapsed_time += 2
        except Exception as err:  # pylint: disable=W0703
            self.logger.error('System {0} power on failed with error {1}'
                              ''.format(node, str(err)))
            return False, str(err), node
        return True, None, node

    @staticmethod
    def is_60k_env_on_neo4j(node_cred):
        """
        Check if this is 60K Env and Neo4j db in use
        """
        if 'db-3' in node_cred and is_dps_using_neo4j():
            return True
        return False

    def start_nodes(self,  # pylint: disable=R0913,R0914,R0912
                redfish, node_cred, timeout=60, sleeptime=1,
                ignore_if_on=False):
        """
        Start all the managed node in threads
        :param redfish: instance of redfish class
        :type redfish: instance of class
        :param node_cred: nodes ip,user name,password
        :type node_cred: dict()
        :param timeout: timeout to wait for redfish command to succeed
        :type timeout: int
        :param sleeptime: timeout to wait for db nodes to come online
        :type sleeptime: int
        :param ignore_if_on: flag to skip power on if node already
        :powered on
        :type ignore_if_on: boolean
        :return: None
        """
        db_nodes = []
        db_nodes_low_start_priority = []
        rest_nodes = []
        for nid in node_cred:
            if EnmSnap.is_60k_env_on_neo4j(node_cred) and \
                 nid.startswith('db-2'):
                self.logger.info('db-2 node of 60K Env: {0}'.format(nid))
                db_nodes_low_start_priority.append(nid)
            elif nid.startswith('db-'):
                db_nodes.append(nid)
            else:
                rest_nodes.append(nid)

        for nodeid in db_nodes:
            success, exception, node = \
                self.power_up_node(redfish, nodeid, node_cred, timeout,
                                   ignore_if_on)
            if not success:
                raise EnmSnapException('Start node for {0} failed with '
                                       'error:{1}'.format(node, exception))
        if db_nodes_low_start_priority:
            self.logger.info('Pause for boot low start priority db node')
            sleep(300)
            for nodeid in db_nodes_low_start_priority:
                self.logger.info('Boot low priority node {0}'.format(
                    nodeid))
                success, exception, node = \
                   self.power_up_node(redfish, nodeid, node_cred, timeout,
                                       ignore_if_on)
                if not success:
                    raise EnmSnapException('Start node for {0} failed '
                                           'with error:{1}'.format(node,
                                           exception))

        sleep(sleeptime)
        thread_pool = ThreadPool(processes=self.num_of_threads)
        thread_results = []

        def report(result):
            """
            Add results to list
            :param result: Thread result tuple
            :return:
            """
            thread_results.append(result)

        try:
            for nodeid in rest_nodes:
                thread_pool.apply_async(self.power_up_node,
                                        args=(redfish, nodeid, node_cred,
                                              timeout, ignore_if_on),
                                        callback=report)
            thread_pool.close()
            thread_pool.join()
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise

        if not thread_results:
            raise EnmSnapException('Start nodes threads did not return'
                                   ' any result')
        all_ok = True
        for success, exception, node in thread_results:
            if not success:
                all_ok = False
                if exception:
                    self.logger.error('{0}'.format(exception))
        if not all_ok:
            raise EnmSnapException('Start up nodes failed')

        if len(rest_nodes) != len(thread_results):
            nodes_result = list(rest_nodes)
            for success, exception, node in thread_results:
                nodes_result.remove(node)
            for node in nodes_result:
                self.logger.error('Startup node thread for {0} did not '
                                  'return any result'.format(node))
            raise EnmSnapException('All the startup nodes threads did not '
                                   'return with result')
        self.logger.info('All the nodes are power on successfully')

    def backup_list(self, data, filename):
        """
        Take a backup of lun list in a file which will used during restore
        :param data : list of luns in the POOL/ List of volumes on LMS
        :type data: list
        :param filename : file where list is to be saved
        :type filename: string
        """
        _pdir = dirname(filename)
        if not exists(_pdir):
            self.logger.debug('Created dir {0}'.format(_pdir))
            makedirs(_pdir)
        with open(filename, 'w') as _writer:
            dump(data, _writer)
        self.logger.info('Snapshot information stored successfully in {0}'
                         .format(filename))

    @staticmethod
    def load_list(filename):
        """
        Load a file to a list
        :param filename: the file to load
        Load list of LUNs for restore/validate of SAN snap
        :returns: LUN list
        :rtype: list|dict
        """
        if exists(filename):
            with open(filename, 'r') as _reader:
                lun_list = load(_reader)
            return lun_list
        else:
            return None

    def rm_file(self, filename):
        """
        Remove LUNs list backup file

        :param filename: The file to delete
        :return: None
        """

        self.logger.debug('Removing file {0}'.format(filename))
        try:
            os.remove(filename)
        except OSError as os_error:
            if os_error.errno == 13:
                raise SystemExit('Unable to remove file {0}'.format(filename))
            elif os_error.errno == 2:
                self.logger.debug('File {0} does not exist'.format(filename))
            else:
                raise os_error

    @staticmethod
    def verify_file(filename):
        """
        Verify if file exists and raise exception if it does not exist.
        :param filename: The file to check for
        :return: None
        """
        if not exists(filename):
            raise EnmSnapException('File {0} does not exist on LMS '.
                                   format(filename))

    def get_systems_storage_container(self):
        """
        Get the SAN pool being used for LUNs in the deployment.

        Only supports deployments where one storage pool is used.

        :returns: The SAN storage pool name for LUNs in the deployment
        :rtype: str
        """

        storage_pools = set()
        for system in self.litp.get_children(self.INFRA_SYSTEMS):
            path_disks = '{0}/disks'.format(system['path'])
            for disk in self.litp.get_children(path_disks):
                if disk['data']['item-type-name'] == self.ITEM_TYPE_LUN_DISK:
                    storage_pools.add(
                        disk['data']['properties']['storage_container'])
        if not storage_pools:
            self.logger.info('No SAN StoragePools found in model.')
            return None
        elif len(storage_pools) > 1:
            raise EnmSnapException('More than one SAN StoragePool being used, '
                                   'not supported!')
        return storage_pools.pop()

    def _get_all_used_nas_providers(self):
        """
        Search the model and get a list of all NAS provider ID used by all
        nodes in a model
        :returns: List of NAS provider names being used by all nodes.
        :rtype: str[]
        """
        used_nas_providers = set()
        deployment_clusters = self.litp.get_deployment_clusters()
        for deployment, clusters in deployment_clusters.items():
            for cluster in clusters:
                for node in self.litp.get_children(
                        '/deployments/{0}/clusters/{1}/nodes'.format(
                            deployment, cluster)):
                    for filesystem in self.litp.get_children(
                            '{0}/file_systems'.format(node['path'])):
                        properties = filesystem['data']['properties']
                        used_nas_providers.add(properties['provider'])
        return used_nas_providers

    def _get_infra_nas_providers(self, used_nas_providers):
        """
        Resolve the NAS provider names to /infrastructure object
        :param used_nas_providers: List of NAS provider IDs
        :type used_nas_providers: str[]
        :returns: Properties for each NAS provider ID
        :rtype: dict
        """
        nas_providers = {}
        for infra_provider in \
                self.litp.get_children(self.INFRA_STORAGE_PROVIDERS):
            if infra_provider['data']['item-type-name'] == \
                    self.ITEM_TYPE_NAS_SVC:
                get_path = '{0}/virtual_servers'.format(infra_provider['path'])
                for virt_server in self.litp.get_children(get_path):
                    vs_name = virt_server['data']['properties']['name']
                    if vs_name in used_nas_providers:
                        nas_providers[infra_provider['path']] = \
                            infra_provider['data']['properties']
        return nas_providers

    def get_nas_service_container(self):
        """
        Get the NAS mount provider being used for mounts in the deployment.

        :returns: The SFS storage provider name in the deployment
        :rtype: dict
        """
        used_nas_providers = self._get_all_used_nas_providers()
        nas_providers = self._get_infra_nas_providers(used_nas_providers)
        if nas_providers:
            for pools in self.litp.get_children(
                    '{0}/pools'.format(nas_providers.keys()[0])):
                pool_name = pools['data']['properties']['name']
                nas_providers[nas_providers.keys()[0]]['pool_name'] = pool_name

        if not nas_providers:
            self.logger.info('No NAS StorageProviders found in model!')
            return None
        elif len(nas_providers) > 1:
            raise EnmSnapException('More than one NAS StorageProvider '
                                   'being used, not supported!')
        else:
            self.logger.debug('Nas credentials build up successfully ')
            return nas_providers.popitem()[1]

    def create_sfwk_restore_info(self):
        """
        Run post restore steps
        :returns: None
        :rtype: None
        """
        self.rm_dir_contents(self.SWFK_DIR_RM)
        self.rm_file(self.SWFK_INFO_FILE)
        self.create_restore_file(self.SWFK_INFO_FILE, user='brsadm')

    def rm_dir_contents(self, dir_rm):
        """
        Remove the contents of the directory without removing the
        directory itself.
        CAUTION:  This is dangerous!  For example, if dir_rm == '/'
        :param dir_rm : dir whose contents to be removed
        :type dir_rm : string
        """
        for root, dirs, files in os.walk(dir_rm):
            for fil in files:
                try:
                    os.remove(os.path.join(root, fil))
                except OSError:
                    raise EnmSnapException("Unable to remove file {0}"
                                           .format(fil))
            for directory in dirs:
                try:
                    shutil.rmtree(os.path.join(root, directory))
                except OSError:
                    raise EnmSnapException("Unable to remove dir {0}"
                                           .format(directory))
        self.logger.info("Successfully removed contents of directory %s"
                         % dir_rm)

    def create_restore_file(self, res_file, user=None):
        """
        Create/touch a restore info file for SWFK
        :param res_file : File to be created
        :type res_file : string
        :param user : User name through which command should be run
        :type user : string/none
        """
        cmd = ['/bin/touch', res_file]
        try:
            exec_process(cmd, sudo=user)
        except IOError as error:
            raise EnmSnapException("Unable to create the file {0} with error "
                                   "{1}".format(res_file, error))

        self.logger.info("Successfully created file %s" % res_file)

    def check_any_snapshots_exist(self, snap_prefix=DEFAULT_SNAP_PREFIX):
        """
        Checks if any snapshots exist. First retrieve list
        for all types of snapshots and checks if any list is not empty
        :param snap_prefix: tag in the snapshot name
        """
        sfs_snap = SfsSnapshots(self.get_nas_cred(), snap_prefix)
        lms = LVMSnapshots(snap_prefix=snap_prefix)
        san_snap = VNXSnap(self.get_san_cred(), snap_prefix)
        sfs_snapshots = sfs_snap.list_snapshots(False)
        lms_snapshots, nodelocal_snapshots = lms.list_snapshots(False)
        san_snapshots = san_snap.list_snapshots(False)

        if sfs_snapshots or lms_snapshots or \
                san_snapshots or nodelocal_snapshots:
            return True

        return False

    def vxfenclearpre(self):
        """
        If a cluster is using fencing disks, clear all SCSI3 registration and
        reservation keys from the set of coordinator disks as well as the set
        of shared data disks.

        :returns: stdout from remove process (vxfenclearpre)
        :rtype: str
        """
        clusters = self.litp.get_cluster_nodes()
        agent = EnminstAgent()
        for cluster, nodes in clusters.items():
            node = nodes.values()[0]
            cluster_path = '/'.join(node.path.split('/')[:-2])
            fencing_disks = self.litp.get_children(
                    cluster_path + '/fencing_disks')
            if fencing_disks:
                self.logger.info(
                        'Cluster {0} has {1} fencing disks, '
                        'clearing keys.'.format(
                                cluster, len(fencing_disks)))
                cleared_keys = False
                for node in nodes.values():
                    hostname = node.get_property('hostname')
                    try:
                        _stdout = agent.vxfenclearpre(hostname)
                        self.logger.debug(_stdout)
                        self.logger.info(
                                'Cleared fencing keys from {0}'.format(
                                        hostname))
                        cleared_keys = True
                        break
                    except McoAgentException as error:
                        if hostname in error.args[0]:
                            self.logger.warning(
                                    error.args[0][hostname]['errors'])
                        else:
                            self.logger.debug(
                                    '{0}\n{1}'.format(error.args[0]['out'],
                                                      error.args[0]['err']))
                if not cleared_keys:
                    raise EnmSnapException('Could not clear fencing '
                                           'keys on any nodes in the '
                                           'cluster {0}'.format(cluster))
            else:
                self.logger.info('No fencing disk in cluster {0}'.format(
                        cluster
                ))

    def neo4j_presnapshots_prepare(self):
        """
        Call Neo4j hardening utility script to prepare for snapshots
        """
        util_script = \
            '/opt/ericsson/nms/litp/lib/scripts/neo4j_hardening_util.sh'
        if not os.path.exists(util_script):
            self.logger.info('Neo4j hardening util {0} not found.'.format(
                util_script))
            return
        confirm_cmd = ['echo', 'CoNfIrM']
        cmd = [util_script, '--set_for_restore']
        try:
            exec_process_via_pipes(confirm_cmd,
                                       cmd)
        except IOError as ex:
            self.logger.error('Neo4j hardening util pre-snapshot failed: %s'
                           % ex)
        self.logger.info('Neo4j util hardening completed.')

    def neo4j_postsnapshots_remove(self):
        """
        Call Neo4j hardening utility script to cleanup for snapshots removal
        """
        util_script = \
            '/opt/ericsson/nms/litp/lib/scripts/neo4j_hardening_util.sh'
        if not os.path.exists(util_script):
            self.logger.info('Neo4j hardening util {0} not found.'.format(
                util_script))
            return
        confirm_cmd = ['echo', 'CoNfIrM']
        cmd = [util_script, '--clean_after_restore']
        try:
            exec_process_via_pipes(confirm_cmd,
                                       cmd)
        except IOError as ex:
            self.logger.error('Neo4j hardening postsnapshot cleanup failed: %s'
                           % ex)
        self.logger.info('Neo4j util hardening completed.')


def interrupt_handler():
    """
    Callback for CTRL-c handling
    :return:
    """
    current_action = get_current_action()
    if current_action in ITRP_MSG:
        if current_action + '.error' in ITRP_MSG:
            get_logger().error(ITRP_MSG[current_action])
        else:
            get_logger().warning(ITRP_MSG[current_action])


@keyboard_interruptable(callback=interrupt_handler)
def manage_snapshots(action,  # pylint: disable=R0913
                     snap_prefix='Snapshot', verbose=False,
                     lvm_snapsize=None,
                     snap_type='enminst',
                     force=False, snap_name=None, detailed=False,
                     num_of_threads=10, log_silent=False):
    """
    Manage system snapshots.

    :param snap_name: The LITP snapshot name
    :param force: For the action
    :param detailed: Show more detailed info
    :param action: The action to perform e.g. create/delete/restore/list
    :param snap_prefix: The snapshot prefix
    :param verbose: True to turn on verbose logging
    :param lvm_snapsize: Override default LVM snap size
    :param snap_type: The snap type, one of "all" "enminst" or "litp"
    :param num_of_threads: number of threads
    :param log_silent: disable logging to enminst log
    :return:
    """
    configure_logging(verbose, log_silent)
    valid_actions = ['list_snapshot', 'remove_snapshot']
    if action != 'list_snapshot' and log_silent:
        get_logger().error('Option "--log_silent" only supported with '
                           'action "list_snapshot"')
        raise SystemExit(ExitCodes.INVALID_USAGE)

    if snap_type == 'all' and action not in valid_actions:
        get_logger().error('Option "--snap_type=all" only supported with '
                           'action "list_snapshot" or action '
                           '"remove_snapshot"')
        raise SystemExit(ExitCodes.INVALID_USAGE)

    if action in ['list_named'] and snap_type != 'litp':
        get_logger().error('Action "{0}" only supported with '
                           '--snap_type=litp'.format(action))
        raise SystemExit(ExitCodes.INVALID_USAGE)

    if snap_type == 'all':
        manage_all_snapshots(action, snap_prefix=snap_prefix,
                             lvm_snapsize=lvm_snapsize,
                             num_of_threads=num_of_threads,
                             detailed=detailed, force=force,
                             s_name=snap_name, verbose=verbose,
                             log_silent=log_silent)

    elif snap_type == 'enminst':
        manage_enminst_snapshots(action, snap_prefix=snap_prefix,
                                 lvm_snapsize=lvm_snapsize,
                                 num_of_threads=num_of_threads,
                                 detailed=detailed, log_silent=log_silent)
    elif snap_type == 'litp':
        manage_litp_snapshots(action, force=force, name=snap_name,
                              verbose=verbose, detailed=detailed)


def litp_snapshot_action(litp_kls, action_function, action_name, **kwargs):
    """
    Perform a LITP snapshot action and wait for the plan to complete.

    :param litp_kls: Interface to LITP
    :type litp_kls: LitpRestClient
    :param action_function: The function to call.
    :type action_function: <function>
    :param action_name: The action name
    :type action_name: str
    :param kwargs: Arguements to the action
    :type kwargs: dict
    :return:
    """
    get_logger().info('Generating {0} Snapshot plan ...'.format(action_name))

    _starttime = datetime.now().replace(microsecond=0)
    action_function(**kwargs)
    hours, minutes, seconds = time_delta(_starttime)
    get_logger().info('Plugin task generation took {0}h:{1}m:{2}s'.format(
        hours, minutes, seconds))
    _monitor_starttime = datetime.now().replace(microsecond=0)
    litp_kls.monitor_plan(Deployer.INST_UPG_PLAN_NAME)
    _plancomplete = datetime.now().replace(microsecond=0)
    hours, minutes, seconds = time_delta(_monitor_starttime,
                                         _plancomplete)
    get_logger().info('Plan execution took {0}h:{1}m:{2}s'.format(
        hours, minutes, seconds))

    hours, minutes, seconds = time_delta(_starttime,
                                         _plancomplete)
    get_logger().info('Snapshot {3} took {0}h:{1}m:{2}s'.format(
        hours, minutes, seconds, action_name))


def list_litp_snapshots(snap_name, detailed=False, force=False,
                        verbose=False):
    """
    List volume snapshots for a named LITP snapshot
    :param snap_name: The modeled LITP snapshot name
    :type snap_name: str
    :param detailed: Show more detailed snapshot info
    :type detailed: bool
    :param force: Look for volume snaps even if the snapshot is not modeled.
    :type force: bool
    :param verbose: Show debug level trace
    :type verbose: bool
    :return:
    """
    LitpSnapshots().list_snapshots(snap_name, detailed=detailed, force=force,
                                   verbose=verbose)


def validate_litp_snapshots(snap_name, force=False, verbose=False):
    """
    Validate volume snapshots for a named LITP snapshot

    :param snap_name: The modeled LITP snapshot name
    :type snap_name: str
    :param force: Look for volume snaps even if the snapshot is not modeled.
    :type force: bool
    :param verbose: Show debug level trace
    :type verbose: bool
    :return:
    """
    LitpSnapshots().validate_snapshots(snap_name, force=force,
                                       verbose=verbose)


def create_litp_snapshots(snap_name=None):
    """
    Create and execute a LITP snapshot create plan

    :param snap_name: The modeled LITP snapshot name
    :type snap_name: str
    """
    litp = LitpRestClient()
    modeled_snapshots = litp.list_snapshots()
    if modeled_snapshots:
        if snap_name in modeled_snapshots:
            get_logger().error(
                'Modeled snapshot called \'{0}\''
                ' already exists!'.format(snap_name))
            raise SystemExit(ExitCodes.LITP_SNAPS_EXIST)
        else:
            get_logger().warning('Other modeled snapshot(s) exist: {0}'
                                 ''.format(','.join(modeled_snapshots)))
    litp_snapshot_action(litp, litp.create_snapshot, 'Create',
                         name=snap_name)


def remove_litp_snapshots(snap_name=None, force=False):
    """
    Create and execute a LITP snapshot remove plan

    :param snap_name: The modeled LITP snapshot name
    :type snap_name: str
    :param force: Force the removal of volume snap objects
    :type force: bool
    """
    litp = LitpRestClient()
    modeled_snapshots = litp.list_snapshots()
    if not modeled_snapshots:
        get_logger().info('No modeled snapshot(s) exist!')
        return
    elif snap_name not in modeled_snapshots:
        get_logger().error('No modeled snapshot called \'{0}\' '
                           'exists!'.format(snap_name))
        raise SystemExit(ExitCodes.LITP_NO_NAMED_SNAPS_EXIST)
    litp_snapshot_action(litp, litp.remove_snapshot, 'Remove',
                         name=snap_name, force=force)


def restore_litp_snapshots(snap_name=None, force=False):
    """
    Create and execute a LITP snapshot restore plan

    :param snap_name: The modeled LITP snapshot name
    :type snap_name: str
    :param force: Force the removal of volume snap objects
    :type force: bool
    """
    litp = LitpRestClient()
    modeled_snapshots = litp.list_snapshots()
    if not modeled_snapshots:
        get_logger().error('No modeled snapshot(s) exist!')
        raise SystemExit(ExitCodes.LITP_NO_SNAPS_EXIST)
    elif snap_name not in modeled_snapshots:
        get_logger().error('No modeled snapshot called \'{0}\' '
                           'exists!'.format(snap_name))
        raise SystemExit(ExitCodes.LITP_NO_NAMED_SNAPS_EXIST)
    litp_snapshot_action(litp, litp.restore_snapshot, 'Restore',
                         name=snap_name, force=force)


def remove_cobbler_files(node_list):
    """
    Method to remove cobbler files

    :param node_list: list of nodes
    :type node_list: list
    """
    for node in node_list:
        h_utils.delete_matching_files(CleanupDeployment.KICKSTART,
                               '{0}.ks'.format(node))
        h_utils.delete_matching_files(CleanupDeployment.SNIPPET,
                               '{0}.ks.*.snippet'.format(node))


def manage_all_snapshots(action,  # pylint: disable=R0913
                     snap_prefix='Snapshot', verbose=False,
                     lvm_snapsize=None,
                     force=False, s_name=None, detailed=False,
                     num_of_threads=10, log_silent=False):
    """
    Manage both LITP and ENMInst snapshots

    :param action: action to be performed
    :param snap_prefix: tag in the snapshot name
    :param verbose: Debug level trace
    :param lvm_snapsize: LVM snapshot size
    :param force: For the action
    :param s_name: The modeled snapshot name
    :param detailed: Show detailed snapshot info
    :param num_of_threads: Max number of threads to use to perform any actions
    :param log_silent: disable logging to enminst log
    """
    manage_enminst_snapshots(action, snap_prefix=snap_prefix,
                         lvm_snapsize=lvm_snapsize,
                         num_of_threads=num_of_threads,
                         detailed=detailed, log_silent=log_silent)

    if action in ['remove_snapshot']:
        litp = LitpRestClient()
        modeled_snapshots = litp.list_snapshots()
        for named_snapshot in modeled_snapshots:
            #remove named snapshots
            manage_litp_snapshots(action, force=force,
                              name=named_snapshot, verbose=verbose,
                              detailed=detailed)
        #remove un-named snapshots
        manage_litp_snapshots(action, force=force,
                              name=s_name, verbose=verbose,
                              detailed=detailed)
    else:
        list_snapshot_actions = ['list_named', 'list_snapshot']
        for snapshot_action in list_snapshot_actions:
            manage_litp_snapshots(snapshot_action, force=force,
                                  name=s_name, verbose=verbose,
                                  detailed=detailed)


def manage_litp_snapshots(action, force=False, name=None, detailed=False,
                          verbose=False):
    """
    Manage LITP snapshots.

    :param action: The action i.e create/delete/restore/list/etc
    :param force: For the action
    :param name: The modeled snapshot name
    :param detailed: Show more detailed info
    :param verbose: Debug level trace
    """
    try:
        if action == 'create_snapshot':
            create_litp_snapshots(name)
        elif action == 'remove_snapshot':
            remove_litp_snapshots(name, force)
        elif action == 'restore_snapshot':
            restore_litp_snapshots(name, force)
        elif action == 'list_snapshot':
            list_litp_snapshots(name, detailed=detailed, force=force,
                                verbose=verbose)
        elif action == 'list_named':
            LitpSnapshots().list_snapshot_names()
        elif action == 'validate_snapshot':
            validate_litp_snapshots(name, force=force, verbose=verbose)
        else:
            raise SystemExit(ExitCodes.INVALID_USAGE)
        get_logger().info("ENM {0} finished successfully".format(action))
    except LitpException as error:
        if 'messages' in error.args[1]:
            for errormsg in error.args[1]['messages']:
                get_logger().error(errormsg['message'])
            raise SystemExit(ExitCodes.LITP_SNAP_ERROR)
        else:
            raise


def clear_and_unmount(path, tries=3, sleep_secs=10):
    """
    Unmount a given path, and if that fails then write to log details of
    processes holding resources at that path, kill those processes and
    sleep for a number of seconds before retrying the umount.

    :param path: filesystem path
    :type path: str
    :param tries: number of times to try umount
    :type tries: int
    :param sleep_secs: number of seconds to sleep between retries
    :type sleep_secs: int
    """
    for i in xrange(tries):
        try:
            import_iso.umount(path, force=True)
        except IOError as error:
            get_logger().warning('IOError on umount {0} : {1}'.format(path,
                                                                      error))
            for cmd in ['fuser -v', 'lsof']:
                output = exec_process(cmd.split() + [path], ignore_error=True)
                get_logger().warning('cmd:{0} {1} output: {2}'.format(cmd,
                                                               path, output))
            if i < tries - 1:
                if output:
                    kill_processes_dir(path)
                sleep(sleep_secs)
        else:
            get_logger().info('umount {0} successful'.format(path))
            return

    raise error


def set_device_timeout_option(litp):  # pylint: disable=R0914
    """
    Check if the x-systemd.device-timeout is already present in /etc/fstab
    TORF-584199, TORF-594045
    :param litp: LitpRestClient object
    :type litp: LitpRestClient
    """

    # Check if the x-systemd.device-timeout is already present in manifests
    mount_option = 'x-systemd.device-timeout=300'
    grep_cmd = os.path.join(os.sep, 'usr', 'bin', 'grep')
    manifest_plugins = os.path.join(os.sep, 'opt', 'ericsson', 'nms', 'litp',
                                      'etc', 'puppet', 'manifests', 'plugins')

    grep_def_str = '\'options => "defaults\''
    to_do_nodes = {}
    ignore_states = [LitpRestClient.ITEM_STATE_INITIAL]
    all_cluster_nodes = litp.get_cluster_nodes()
    for nodes in all_cluster_nodes.values():
        for _, details in nodes.items():
            if details.state in ignore_states:
                continue
            manifest = os.path.join(manifest_plugins,
                details.get_property('hostname') + '.pp')
            cmd = [grep_cmd + ' ' + grep_def_str + ' ' + manifest]
            output = exec_process(cmd, ignore_error=True, use_shell=True)
            if mount_option not in output:
                get_logger().info("Mount option {0} not set in {1}".format(
                        mount_option, manifest))
                to_do_nodes[details.get_property('hostname')] = manifest

    lms_hostname = gethostname()
    manifest = os.path.join(manifest_plugins, lms_hostname + '.pp')
    cmd = [grep_cmd + ' ' + grep_def_str + ' ' + manifest]
    output = exec_process(cmd, ignore_error=True, use_shell=True)
    if mount_option not in output:
        get_logger().info("Mount option {0} not set in {1}".format(
                        mount_option, manifest))
        to_do_nodes[lms_hostname] = manifest

    if to_do_nodes:
        run_agent(to_do_nodes.keys(), 'puppet', 'disable')

        for manifest in to_do_nodes.values():
            sed_str = '\'s/^\\( *options => "defaults\\)", '\
                  '*$/\\1,x-systemd.device-timeout=300",/g\''
            cmd = ['sed -i.bak -e ' + sed_str + ' ' + manifest]
            output = exec_process(cmd, use_shell=True)

            #check if the manifest has been updated.
            cmd = [grep_cmd + ' \'' + mount_option + '\' ' + manifest]
            output = exec_process(cmd, ignore_error=True, use_shell=True)
            if mount_option not in output:
                run_agent(to_do_nodes.keys(), 'puppet', 'enable')
                raise SystemExit(
                   "Could not set mount option {0} in {1}.".format(
                       mount_option, manifest))

        get_logger().info('Cleaning puppet cache.')
        cmd = ['mco  rpc puppetcache clean -I {0}'.format(lms_hostname)]
        output = exec_process(cmd, use_shell=True)

        get_logger().info(
        'Waiting for puppet catalog run to complete on nodes')
        h_puppet.puppet_trigger_wait(True, get_logger().info,
                                     host_list=to_do_nodes.keys())
        get_logger().info('Puppet run completed.')

        cmd = ['rm -f ' + os.path.join(manifest_plugins, '*.pp.bak')]
        exec_process(cmd, use_shell=True)
        get_logger().info("Successfully set mount options.")
    else:
        get_logger().info("No mount options to set.")


def run_agent(nodes, agent, action):
    """
        :param nodes: The nodes on wich to execute the agent
        :type nodes: str[]
        :param agent: The agent name
        :type agent: str
        :param action: The action name
        :type action: str
    """
    rpc_results = run_rpc_command(nodes, agent, action)
    for _, rpc_data in rpc_results.items():
        if rpc_data['errors']:
            if (action == "disable" and
                "Could not disable Puppet: Already disabled" in
                rpc_data['errors']) or (action == "enable" and
                "Could not enable Puppet: Already enabled" in
                rpc_data['errors']):
                continue
            else:
                raise SystemExit(
                   "Errors while running (0}:{1}.\n {2} ".format(
                       agent, action, rpc_results))


def is_mount_option_migrated(litp):
    """
    Check LITP model for fs_mount_option migration
    :param litp: LitpRestClient object
    :type litp: LitpRestClient
    """
    infra_path = os.path.join(os.sep, 'infrastructure', 'storage',
                              'storage_profiles')
    file_systems = litp.get_items_by_type(infra_path, 'file-system', [])
    for file_system in file_systems:
        if 'mount_options' in file_system['data']['properties']:
            return True
    return False


def manage_enminst_snapshots(action,  # pylint: disable=R0912,R0914,R0915,R0913
                             snap_prefix='Snapshot',
                             lvm_snapsize=None, num_of_threads=10,
                             verbose=False, detailed=False, log_silent=False):
    """
    Manage ENMIST snapshots.

    :param lvm_snapsize: LVM snapshot size
    :param action: action to be performed
    :param snap_prefix: tag in the snapshot name
    :param snap_prefix: number of threads that can be used
    :param num_of_threads: Max number of threads to use to perform any actions
    :param detailed: Show detailed snapshot info
    :param log_silent: disable logging to enminst log
    """
    config = read_enminst_config()
    snapper = EnmSnap(config, num_of_threads=num_of_threads,
                      log_silent=log_silent)
    san_creds = snapper.get_san_cred()
    nas_creds = snapper.get_nas_cred()
    san_snapper = None
    nas_snapper = None
    if san_creds:
        san_snapper = VNXSnap(san_creds, snap_prefix,
                              num_of_threads=num_of_threads,
                              log_silent=log_silent)
    if nas_creds:
        nas_snapper = SfsSnapshots(nas_creds, snap_prefix,
                                   num_of_threads=num_of_threads,
                                   log_silent=log_silent)
    lvm_snapper = LVMSnapshots(snap_prefix=snap_prefix,
                               log_silent=log_silent)
    set_current_action(action)
    if action == 'create_snapshot':
        litp = LitpRestClient()
        if litp.is_plan_running('plan'):
            get_logger().error('A plan is currently running, wait for it to '
                               'complete before running a snapshot create.')
            raise SystemExit(4)
        get_logger().info('No running plans found.')

        if not is_mount_option_migrated(litp):
            set_device_timeout_option(litp)

        # Need to do this before offlining the LMS services, httpd is the one
        # serving out the repo's to the blades
        clusters = discover_vcs_clusters(Vcs.ENM_DB_CLUSTER_NAME)
        snap_agent = SnapAgents()
        if Vcs.ENM_DB_CLUSTER_NAME in clusters:
            navi_pkg = config['ENMINST_NAVI_PKG'.lower()]
            for host in clusters[Vcs.ENM_DB_CLUSTER_NAME]:
                status = snap_agent.ensure_installed(navi_pkg, host)
                get_logger().info('{0} {1}'.format(host, status))

        snapper.neo4j_presnapshots_prepare()
        snapper.manage_lms_services('stop', ['puppet'])
        snapper.check_puppet_catalog()
        try:
            if nas_snapper:
                snapper.backup_list(nas_snapper.create_snapshots(),
                                    snapper.sfs_fs_bkup)
                snapper.backup_list(nas_snapper.build_exported_fs(),
                                    snapper.sfs_share_list)
            if san_snapper:
                snapper.backup_list(san_snapper.get_snappable_luns().keys(),
                                    snapper.lun_list_bkup)
                san_snapper.create_snapshots()
            lv_list, nodelv_list = lvm_snapper.create_snapshots(
                lvm_snapsize=lvm_snapsize)
            snapper.backup_list(lv_list, snapper.lms_vol_bkup)
            snapper.backup_list(nodelv_list, snapper.node_vol_bkup)
        except Exception as error:
            get_logger().exception('Create snapshot failed with error below, '
                                   'run remove_snapshot before any subsequent '
                                   'attempt to create_snapshot.')
            snapper.neo4j_postsnapshots_remove()
            raise SystemExit(error)
        finally:
            snapper.manage_lms_services('start', ['puppet'])
        create_blade_info_file()

    elif action == 'list_snapshot':
        if nas_snapper:
            nas_snapper.list_snapshots(detailed)
        lvm_snapper.list_snapshots(detailed)
        if san_snapper:
            san_snapper.list_snapshots(detailed,
                                       snapper.load_list(
                                               snapper.lun_list_bkup))
    elif action == 'remove_snapshot':
        try:
            litp = LitpRestClient()
            redfish = Redfishtool()
            migrate_elasticsearch_indexes()
            lvm_snapper.remove_snapshots()
            snapper.rm_file(snapper.lms_vol_bkup)
            snapper.rm_file(snapper.node_vol_bkup)
            if nas_snapper:
                nas_snapper.remove_snapshots(
                    snapper.load_list(snapper.sfs_share_list))
                nas_snapper.ensure_removal_fs_not_required()
                snapper.rm_file(snapper.sfs_fs_bkup)
                snapper.rm_file(snapper.sfs_share_list)
            if san_snapper:
                san_snapper.remove_snapshots(
                    luns=snapper.load_list(snapper.lun_list_bkup))
                if check_removed_blades_info_file_exists() and san_snapper:
                    clean_removed_luns(redfish, litp, snapper)
                san_snapper.opendj_backup_cleanup()
                snapper.rm_file(snapper.lun_list_bkup)
            remove_snapshots_indicator_file()
            remove_blade_info_file()
            remove_removed_blades_info_file()
            remove_migration_lockfile()

        except Exception as error:
            get_logger().exception('Remove snapshot failed with error below, '
                                   'run remove_snapshot again before any '
                                   'subsequent attempt to create_snapshot.')
            raise SystemExit(error)
        finally:
            snapper.neo4j_postsnapshots_remove()

    elif action == 'restore_snapshot':
        try:
            redfish = Redfishtool()
            if nas_snapper:
                nas_snapper.validate(snapper.load_list(snapper.sfs_fs_bkup))
                snapper.verify_file(snapper.sfs_share_list)
            lvm_snapper.validate(snapper.load_list(snapper.lms_vol_bkup),
                                 snapper.load_list(snapper.node_vol_bkup))
            if san_snapper:
                san_snapper.validate(snapper.load_list(snapper.lun_list_bkup))
                snapper.verify_file(snapper.lun_list_bkup)

            node_cred = snapper.get_node_cred()

            node_to_host = {}
            all_cluster_nodes = LitpRestClient().get_cluster_nodes()
            for _, nodes in all_cluster_nodes.items():
                for node, details in nodes.items():
                    node_to_host[details.get_property('hostname')] = node

            # Disable access to puppet manifests
            snapper.manage_lms_services('stop', ['puppetserver',
            'puppetserver_monitor'])

            # Restore LVs on nodes using local storage before
            # powering them off (apart from LMS)
            nodelocal_restore_data = snapper.load_list(snapper.node_vol_bkup)

            if isfile(MIGRATION_LOCK_FILE) and isfile(RHEL7_NODE_LIST_FILE):
                rhel7_node_cred = {}
                rhel7_node_list = snapper.load_list(RHEL7_NODE_LIST_FILE)
                for _node_hostname in rhel7_node_list:
                    # pylint: disable=E1103
                    nodelocal_restore_data.pop(_node_hostname)
                    _node_id = node_to_host[_node_hostname]
                    if _node_id in node_cred:
                        rhel7_node_cred[_node_id] = node_cred[_node_id]
                        node_cred.pop(_node_id)
                get_logger().info('Powering off nodes that lost snapshots: '
                                  '{0}'.format(rhel7_node_list))
                snapper.shutdown_nodes(redfish, rhel7_node_cred)

            lvm_snapper.restore_nodelocal_snapshots(
                nodelocal_restore_data.keys())  # pylint: disable=E1103

            # Clear fencing disk keys on all clusters using them.
            snapper.vxfenclearpre()

            import_iso.configure_logging(verbose)
            clear_and_unmount(DATA_PATH, tries=3, sleep_secs=10)

            # Power down previously removed nodes
            if check_removed_blades_info_file_exists:
                if san_snapper:
                    node_creds = snapper.get_removed_node_cred()
                    node_cred.update(node_creds)
            snapper.shutdown_nodes(redfish, node_cred)

            if nas_snapper:
                nas_snapper.remove_sfs_shares()
                nas_snapper.restore_snapshots(
                    snapper.load_list(snapper.sfs_share_list))

            if san_snapper:
                san_snapper.restore_snapshots(
                    snapper.load_list(snapper.lun_list_bkup))

            import_iso.mount(DATA_PATH)

            snapper.create_sfwk_restore_info()
            if check_blade_info_file_exists():
                if san_snapper:
                    new_blades, node_cred = build_node_cred(snapper,
                                                            node_cred)
                    try:
                        cleanup_blade_expansion(new_blades, snapper.load_list(
                            snapper.lun_list_bkup))
                    except Exception as error:  # pylint: disable=W0703
                        get_logger().warning("The clean up of newly added"
                                             " lun's failed,"
                                             " please clean it manually.")
                        get_logger().exception(error)
                remove_blade_info_file()
                remove_removed_blades_info_file()
            snapper.start_nodes(redfish, node_cred, sleeptime=300)
            if san_snapper:
                san_snapper.remove_snaps_by_prefix(
                    restore_lunids=snapper.load_list(snapper.lun_list_bkup))
            lvm_snapper.restore_lms_snapshots()
            lvm_snapper.reboot()
        except (KeyboardInterrupt, Exception):
            if san_snapper:
                san_snapper.remove_snaps_by_prefix(
                    restore_lunids=snapper.load_list(snapper.lun_list_bkup))
            get_logger().error('Restore Snapshot Failed.')
            raise
    elif action == 'validate_snapshot':
        if nas_snapper:
            nas_snapper.validate(snapper.load_list(snapper.sfs_fs_bkup))
            snapper.verify_file(snapper.sfs_share_list)
        lvm_snapper.validate(
                snapper.load_list(snapper.lms_vol_bkup),
                snapper.load_list(snapper.node_vol_bkup),
                detailed)
        if san_snapper:
            snapper.verify_file(snapper.lun_list_bkup)
            san_snapper.validate(snapper.load_list(snapper.lun_list_bkup))
    else:
        raise SystemExit(ExitCodes.INVALID_USAGE)
    get_logger().info("ENM {0} finished successfully".format(action))


def clean_removed_luns(redfish, litp, snapper):
    """
    Delete unused luns and power off unused cluster nodes.
    :param redfish: instance of redfish class
    :param litp: LITP object
    :param snapper: Snapper object
    :rtype: object
    """
    with open(get_removed_blades_info_filename(), 'r') \
            as _reader:
        removed_nodes = load(_reader)
    delete_nodes = {}
    # pylint: disable=maybe-no-member
    for node, data in removed_nodes.items():
        if not litp.exists('/deployments/enm/clusters/{0}'
                           '/nodes/{1}'.
                                   format(data['cluster'],
                                          node)):
            delete_nodes[node] = data
            hostnames = [data.get('hostname') for data
                         in removed_nodes.values()]
            try:
                remove_cobbler_files(hostnames)
            except IOError as error:
                get_logger().warning("The clean up of "
                                     "unused cobbler  "
                                     "files failed, "
                                     "please clean "
                                     "it manually.")
                get_logger().exception(error)
            try:
                cleanup_blade_expansion(
                        delete_nodes.keys(), [])
            except IOError as error:
                # pylint: disable=W0703
                get_logger().warning(
                        "The clean up of unused "
                        "lun's failed, "
                        "please clean it manually.")
                get_logger().exception(error)
            node_cred = snapper.get_removed_node_cred()
            snapper.poweroff_node(redfish, node, {node: node_cred}, timeout=60)
    # flush cobbler kickstarts
    snapper.manage_lms_services('restart', ['httpd'])


def build_node_cred(snapper, node_cred):
    """
    Building node list to power up excluding blades from info file
    :param snapper: Snapper object
    :type snapper: EnmSnap
    :param node_cred: all nodes credentials
    :type node_cred: dict
    :return: Tuple of blades to destroy and node credentials to power on
    :rtype: tuple
    """
    blade_list_snapshot = snapper.load_list(
        get_blade_info_filename())
    node_cred_snapshot = {}
    new_blades = []
    for node in node_cred:
        if node in blade_list_snapshot:
            node_cred_snapshot[node] = node_cred[node]
        else:
            new_blades.append(node)
    return new_blades, node_cred_snapshot


def cleanup_blade_expansion(nodes, lun_ids):  # pylint: disable=R0912,R0914
    """
    Cleanup blade expansion. Deregister blades, delete LUNs, destroy storage
    groups.
    :param nodes: List of nodes
    :type nodes: list
    :param lun_ids: Luns with valid snapshot
    :type lun_ids: list
    :return:
    """
    san_id = 'san1'
    deployment_name = 'enm'
    litp_ver = 'LITP2'
    litp = LitpRestClient()
    san_cleanup = SanCleanup()
    san_info = san_cleanup.get_san_info()
    san_api = api_builder(san_info[san_id][SAN_TYPE], get_logger())
    san_api.initialise((san_info[san_id][IP_A], san_info[san_id][IP_B]),
                       san_info[san_id][USERNAME],
                       san_info[san_id][SAN_PASSW],
                       san_info[san_id][LOGIN_SCOPE],
                       esc_pwd=True)

    for node in nodes:
        cluster_name = '{0}_cluster'.format(node.split('-')[0])
        vpath = '/deployments/enm/clusters/{0}/nodes/{1}'.format(
                cluster_name, node)
        hostname = None
        if litp.exists(vpath):
            # Delete new node if rolling back expansion snaps
            obj = LitpObject(None, litp.get(vpath), litp.path_parser)
            hostname = obj.get_property('hostname')
        elif check_removed_blades_info_file_exists():
            # Delete snaps after cluster removal and remove deleted node LUNs
            with open(get_removed_blades_info_filename(), 'r') as _reader:
                removed_nodes = load(_reader)
            if node in removed_nodes:
                hostname = removed_nodes[node]['hostname']
        if not hostname:
            raise Exception(
                    'Could not get hostname for {0} from LITP model '
                    'or removed nodes list!'.format(node))

        sg_name = '{0}-{1}-{2}-{3}'.format(
            san_info[san_id][STORAGE_SITE_ID], deployment_name, cluster_name,
            node)

        try:
            if san_info[san_id][SAN_TYPE].upper().startswith('UNITY'):
                sg_obj = san_api.get_storage_group(sg_name)
            else:
                sg_obj = san_api.get_storage_group(sg_name, logmsg=False)
        except sanapiexception.SanApiEntityNotFoundException:
            get_logger().warning(
                'Storage group {0} not defined on array'.format(sg_name))
            continue

        san_api.disconnect_host(sg_name, hostname)

        for hbauid in [hba.hbauid for hba in sg_obj.hbasp_list]:
            san_api.deregister_hba_uid(hbauid)

        if san_info[san_id][SAN_TYPE].upper().startswith('VNX'):
            san_api.remove_luns_from_storage_group(sg_name, sg_obj.hlualu_list)

        del_luns = []
        for lun_id in [hlualu.alu for hlualu in sg_obj.hlualu_list]:
            lun_obj = san_api.get_lun(lun_id=lun_id)
            if lun_id not in lun_ids:
                prefix = '{0}_{1}_'.format(litp_ver,
                                           san_info[san_id][STORAGE_SITE_ID])
                lun_name = lun_obj.name.split(prefix)[-1]
                if lun_name not in _EXCLUDED_LUNS and lun_obj.type != \
                        'RaidGroup':
                    del_luns.append(lun_id)
        if san_info[san_id][SAN_TYPE].upper().startswith('UNITY'):
            san_api.remove_luns_from_storage_group(sg_name, sg_obj.hlualu_list)
        san_cleanup.delete_luns(san_api, del_luns)
        san_api.delete_storage_group(sg_name)


def configure_logging(verbose, log_silent=False):
    """
    Configure a logger instance
    :param verbose: Set debug log on
    :param log_silent: disable logging to enminst log
    :return:
    """
    global _LOGGER  # pylint: disable=W0602,W0603
    if log_silent:
        _LOGGER = init_enminst_logging(logger_name='enmsnapshots')
    else:
        _LOGGER = init_enminst_logging()
    if verbose:
        set_logging_level(_LOGGER, 'DEBUG')
    return _LOGGER


def get_logger():
    """
    Get the current logger instance
    :return:
    """
    global _LOGGER  # pylint: disable=W0602
    return _LOGGER


def get_elasticsearch_active_host():
    ''' Find elasticsearch active host
    '''
    info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                           '.*elasticsearch_clustered_service',
                                           verbose=False)
    for entry in info:
        if entry[Vcs.H_SERVICE_STATE] == 'ONLINE':
            get_logger().info('Active elasticsearch node is {0}'.
                          format(entry[Vcs.H_SYSTEM]))
            return [entry[Vcs.H_SYSTEM]]


def migrate_elasticsearch_indexes():
    """
    Migrate Elasticsearch indexes from 2.1 to 5.6
    :return:
    """
    enminst_agent = EnminstAgent()
    elnode = get_elasticsearch_active_host()
    return enminst_agent.migrate_elasticsearch_indexes(elnode)


def remove_migration_lockfile():
    """
    Method to remove migration lockfile
    :return:
    """
    if LVMSnapshots.is_migration():
        delete_file(MIGRATION_LOCK_FILE)


def create_argument_parser():
    """
    Creates and configures parser to process command line arguments
    :return: argument parser instance
    :rtype ArgumentParser
    """
    arg_parser = ArgumentParser(prog='enm_snapshots.bsh')
    arg_parser.add_argument('--action', dest='action', required=True,
                            choices=['create_snapshot', 'list_snapshot',
                                     'remove_snapshot', 'validate_snapshot',
                                     'restore_snapshot', 'list_named'],
                            help='Snap action i.e either of create_snapshot, '
                                 'list_snapshot, remove_snapshot, '
                                 'validate_snapshot, restore_snapshot.'
                                 '("list_named" only used when '
                                 '--snap_type=litp)')

    arg_parser.add_argument('--snap-prefix', dest='snap_prefix',
                            default=DEFAULT_SNAP_PREFIX,
                            help='Tag to use in the snapshot name, default is '
                                 '\'Snapshot\' (only used when --snap_type='
                                 'enminst)')
    arg_parser.add_argument('--num_of_threads', dest='num_of_threads',
                            default=10, choices=range(1, 11), type=int,
                            help='Optional parameter.Max. number of parallel '
                                 'processes that can be run whenever '
                                 'possible, by default 10 but '
                                 'should not be more than 10.'
                                 '(only used when --snap_type='
                                 'enminst)')
    arg_parser.add_argument('--verbose', action='store_true', default=False,
                            help="Enable all debugging output")

    arg_parser.add_argument('--lvm_snapsize', dest='lvm_snapsize',
                            type=int, default=None)

    arg_parser.add_argument('--snap_type', dest='snap_type',
                            default='enminst',
                            choices=['enminst', 'litp', 'all'],
                            help='The snapshot type to create. \'enminst\' '
                                 '(default) scripted method. \'litp\' '
                                 'plugin method. \'all\' both enminst '
                                 'and litp methods.')

    arg_parser.add_argument('--snap_name', dest='snap_name',
                            default='snapshot',
                            help='Name of the snapshot (only used when '
                                 '--snap_type=litp)')

    arg_parser.add_argument('--detailed', dest='detailed',
                            action='store_true', default=False,
                            help='Get more details in the snapshots'
                                 ' (only used when --snap_type=litp and '
                                 'list_snapshot)')

    arg_parser.add_argument('--log_silent', dest='log_silent',
                            action='store_true', default=False,
                            help='Disable logging to enminst log for '
                                 'list_snapshot')

    arg_parser.add_argument('--force', dest='litp_force',
                            default=False, action='store_true',
                            help='Pass the force flag to LITP (only used when '
                                 '--snap_type=litp)')

    return arg_parser


def main(args):
    """
    Main function.

    Runs snapshot operation depending on the argument given.
    :param args: Main CLI args
    :type args: list(str)
    """
    arg_parser = create_argument_parser()
    options = arg_parser.parse_args(args)
    try:
        manage_snapshots(action=options.action,
                         snap_prefix=options.snap_prefix,
                         snap_name=options.snap_name,
                         verbose=options.verbose,
                         lvm_snapsize=options.lvm_snapsize,
                         snap_type=options.snap_type,
                         force=options.litp_force,
                         detailed=options.detailed,
                         num_of_threads=options.num_of_threads,
                         log_silent=options.log_silent)
    except SystemExit as error:
        if error.args[0] == ExitCodes.INVALID_USAGE:
            arg_parser.print_help()
        else:
            raise


if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
