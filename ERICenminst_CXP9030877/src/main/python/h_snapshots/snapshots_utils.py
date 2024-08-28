"""
Utility methods and constants to aid snapshots
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************

from ConfigParser import SafeConfigParser
from io import BytesIO
import logging
import re
from h_logging.enminst_logger import set_logging_level
from h_litp.litp_rest_client import LitpRestClient, LitpException

from sanapi import api_builder
from sanapiexception import SanApiException
from sanapilib import CONTAINER_STORAGE_POOL

SAN_TYPE = 'san_type'
SAN_POOLNAME = 'san_pool'
SAN_SPA_IP = 'san_spa_ip'
SAN_SPB_IP = 'san_spb_ip'
SAN_LOGIN_SCOPE = 'san_login_scope'
SAN_USER = 'san_user'
SAN_PW = 'san_psw'

SAN_TYPE_VNX = 'VNX'
SAN_TYPE_UNITY = 'UNITY'


def get_default_config():
    """
    Get the default SAN config
    :return: Default config settings for naviseccli actions
    """
    rack_deployment_type = r'.*ENM_On_Rack_Servers$'
    litp_rest = LitpRestClient()

    rack_litp_prop_path = \
        "/software/items/config_manager/global_properties/enm_deployment_type"
    prop_value = None
    try:
        items = litp_rest.get(rack_litp_prop_path, log=False)
        prop_value = items["properties"]["value"]
    except LitpException:
        print 'enm_deployment_type  not retained from litp model '

    if prop_value and re.match(rack_deployment_type, prop_value):
        neo4j_lun_names = "neo4j_1,neo4j_2,neo4j_3"
    else:
        neo4j_lun_names = "neo4j_2,neo4j_3,neo4j_4"
    return '''
[VNX]
Navisec=/opt/Navisphere/bin/naviseccli
NavisecTimeout=30
NavisecRetries=1
NavisecRetrySleep=2
StorageProcessors=a,b
snapstr = Snapshot
excludeluns=.*SFS.*,.*elasticsearch.*
db_lun_names = mysql,versantdb,postgresdb,neo4jlun,{0}

[Unity]
UnityTimeout=30
'''.format(neo4j_lun_names)


def read_ini(contents):
    """
    To parse the default configuration for VNX
    :param contents : configuration contents
    :return: config parser
    :type: object
    """
    scp = SafeConfigParser()
    scp.optionxform = str
    scp.readfp(BytesIO(contents))
    return scp


# TODO: CHANGE NAME OF CLASS EVENTUALLY  # pylint: disable=fixme
class NavisecCLI(object):  # pylint: disable=R0902
    """
    Class to execute naviseccli commands
    """

    NAVI_ERR_SNAP_EXISTS = '0x716d8005'

    def __init__(self, san_cred, cfg_ini=None, verbose=False):
        super(NavisecCLI, self).__init__()
        if not san_cred:
            raise SanApiException('No SAN Credentials provided', 1)

        self.san_cred = san_cred
        self.pool_name = self.san_cred[SAN_POOLNAME]
        self.cfg_ini = cfg_ini

        if self.cfg_ini is None:
            self.cfg_ini = read_ini(get_default_config())

        self.logger = logging.getLogger('enminst')
        if verbose:
            set_logging_level(self.logger, 'DEBUG')

        ips = (self.san_cred[SAN_SPA_IP], self.san_cred[SAN_SPB_IP])
        user = self.san_cred[SAN_USER]
        passwd = self.san_cred[SAN_PW]
        scope = self.san_cred[SAN_LOGIN_SCOPE]
        san_type = self.san_cred[SAN_TYPE]

        self.san_api = api_builder(san_type, self.logger)
        self.san_api.initialise(ips, user, passwd, scope, True, False, True)

    def storage_pool_list(self, pool_name):
        """
        TODO: THis appears unused, should remove it  # pylint: disable=fixme
        List the LUN's in a storage pool
        :param pool_name: The storage pool name
        :type pool_name: str
        :param xml: Get the response as XML or not
        :type xml: bool
        :param parse: ...
        :type parse: bool
        :returns: The storage pool info
        :rtype: str
        """
        container_type = CONTAINER_STORAGE_POOL
        return self.san_api.get_luns(container_type, pool_name)

    def get_storagepool_info(self, storage_pool):
        """
        Get storage pool info from the SAN

        :param storage_pool: The storage pool name
        :type storage_pool: str
        :returns: Info on the pool
        :rtype: dict
        """
        return self.san_api.get_storage_pool(storage_pool)

    def list_all_luns(self, storage_pool=None):
        """
        Get a list of all LUN's on the SAN

        :param storage_pool: Get LUNs contained in a particular Pool
        :returns: A list of LUN's currently on the SAN
        :rtype: dict
        """
        container_type = CONTAINER_STORAGE_POOL
        return self.san_api.get_luns(container_type, storage_pool)

    def delete_lun_with_snap(self, lun_name=None, lun_id=None):
        """
        Delete LUN on the SAN
        :param lun_name: The name of the LUN. Default; None.
        :type lun_name: str
        :param lun_id: The ID of the LUN. Default; None.
        :type lun_id: str
        """
        return self.san_api.delete_lun(lun_name, lun_id, \
                            array_specific_options="-destroySnapshots "
                            "-forceDetach")

    def get_storagegroup_info(self, storage_group_name):
        """
        Get storage group info from the SAN
        :param storage_group_name: The storage group name
        :type storage_group_name: str
        :returns: Info on the group
        :rtype: StorageGroupInfo
        """
        return self.san_api.get_storage_group(sg_name=storage_group_name)

    def remove_luns_from_storage_group(self, sg_name, hlus):
        """
        Removes LUN associations from a Storage Group
        :param sg_name: The storage group name
        :type sg_name: str
        :param hlus: The HLUs, either a single value or a list.
        :type hlus: :class:`str` or :class:`int` for a single value,
        """
        return self.san_api.remove_luns_from_storage_group(sg_name=sg_name, \
                        hlus=hlus)

    def list_all_snaps(self):
        """
        Get a list of all Snapshot LUN's on the SAN
        :returns: A list of snapshot LUNs
        :rtype: dict
        """
        return self.san_api.get_snapshots()

    def snap_create(self, lun_id, name):
        """
        Snap a lun

        :param lun_id: The lun to snap
        :type lun_id: str
        :param name: The snap name to create
        :type name: str

        """
        # TODO NEED TO CHANGE NAME  FOR UNITY  # pylint: disable=fixme
        description = "CI VnxSnap"
        return self.san_api.create_snapshot_with_id(lun_id,
                                                    name,
                                                    description=description)

    def snap_destroy(self, snap_id):
        """
        Delete a snapshot

        :param snap_id: The snapshot name
        :type snap_id: str
        """
        return self.san_api.delete_snapshot(snap_id)

    def snap_restore(self, lun_id, snap_name):
        """
        Restore a snapshot

        :param lun_id: The snapshot source LUN
        :type lun_id: str
        :param name: The snapshot name
        :type name: str
        :param xml: Get the response as XML or not
        :type xml: bool
        :param parse: ...
        :type parse: bool

        """
        bkup_snap_name = 'enm_upgrade_bkup_%s' % lun_id
        return self.san_api.restore_snapshot_by_id(lun_id,
                                                   snap_name,
                                                   delete_backupsnap=False,
                                                   backup_name=bkup_snap_name)
