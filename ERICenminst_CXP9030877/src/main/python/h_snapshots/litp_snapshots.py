# pylint: disable=too-many-lines
"""
Classes to perform LITP Plugin bases filesystem snapshots
"""
##############################################################################
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from ConfigParser import NoSectionError
from collections import namedtuple
from os.path import basename

from h_litp.litp_rest_client import LitpRestClient, LitpObject
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_puppet.mco_agents import EnminstAgent
from h_snapshots.snapshots_utils import SAN_SPA_IP, SAN_LOGIN_SCOPE, \
    SAN_USER, SAN_SPB_IP, SAN_POOLNAME, SAN_TYPE, SAN_PW, NavisecCLI
from h_util.h_nas_console import NasConsole
from h_util.h_utils import ExitCodes, exec_process, Decryptor, get_nas_type


class LitpSnapError(Exception):
    """
    Generic LITP snap error
    """
    pass


def join(parent, name):
    """
    Join the child ID with the parent path.
    :param parent: The model parent item path
    :type parent: str
    :param name: The child model id
    :type name: str
    :returns: Full model path to child
    :rtype: str
    """
    return '{0}/{1}'.format(parent, name)


def get_volume_snapshot_name(fs_name, snap_name):
    """
    Get the name of the snapshot for a volume name

    :param fs_name: The source volume name
    :type fs_name: str
    :param snap_name: The LITP named snapshot name
    :type snap_name: str
    :returns: The name of the volume snapshot
    :rtype: str
    """
    if not snap_name or snap_name == 'snapshot':
        return 'L_{0}_'.format(fs_name)
    else:
        return '{0}_{1}'.format(fs_name, snap_name)


class LitpBaseSnapshots(object):
    """
    Base class containing common functions.
    """

    def __init__(self, verbose=False):
        self.__litp = LitpRestClient()
        self.__log = init_enminst_logging()
        self._verbose = verbose
        if self._verbose:
            set_logging_level(self.__log, 'DEBUG')
        self.p_storage_providers = '/infrastructure/storage/storage_providers'
        self.nas_type_name = get_nas_type(self.__litp)

    def get(self, model_path):
        """
        Get an item from the LITP deployment model

        :param model_path: The path of the item to get
        :type model_path: str
        :returns: The model item
        :rtype: LitpObject
        """
        json_data = self.__litp.get(model_path, log=self._verbose)
        return self._json_to_object({'path': model_path, 'data': json_data})

    def get_children(self, model_path):
        """
        Get a list of children of a model item

        :param model_path: The path of the model item
         :type model_path: str
        :returns: List of chilren
        :rtype: LitpObject[]
        """
        children = []
        for model_item in self.__litp.get_children(model_path,
                                                   verbose=self._verbose):
            children.append(self._json_to_object(model_item))
        return children

    def _json_to_object(self, json_data):
        """
        Convert a REST GET json result to a LitpObject

        :param json_data: The return result of a REST GET operation from the
        LITP deployment model.

        :returns: A ``LitpObject`` representing the LITP deployment model item
        :rtype: LitpObject
        """
        return LitpObject(None, json_data['data'], self.__litp.path_parser)

    def info(self, message):
        """
        Log a message at level INFO

        :param message: Message to log
        """
        self.__log.info(message)

    def debug(self, message):
        """
        Log a message at level DEBUG

        :param message: Message to log
        """
        self.__log.debug(message)

    def error(self, message):
        """
        Log a message at level ERROR

        :param message: Message to log
        """
        self.__log.error(message)

    def _get_modeled_clusters(self):
        """
        Get a list of modeled clusters

        :returns: List of clusters in the deployment
        :rtype: LitpObject[]
        """
        modeled_clusters = []
        deployments = self.get_children('/deployments')
        for deployment in deployments:
            modeled_clusters.extend(
                self.get_children('{0}/{1}'.format(deployment.path,
                                                   'clusters')))
        return modeled_clusters

    def _get_modeled_nodes(self, cluster):
        """
        Get a list of modeled nodes in a cluster

        :returns: List of nodes in the cluster
        :rtype: LitpObject[]
        """
        return self.get_children(join(cluster.path, 'nodes'))


class LitpSanSnapshots(LitpBaseSnapshots):
    """
    Class to handle list/validate of LUN snapshots created via LITP plugins.
    """

    def __init__(self, verbose=False):
        super(LitpSanSnapshots, self).__init__(verbose)

    def get_node_lundisks(self):
        """
        Get a list of compute node file-system LUNs that are snappable.

        :returns: A map of snappable LUNs. The key is the lun_name, value is
        the deployment model item represented as a LitpObject class

        :rtype: dict
        """
        lun_disks = {}

        for cluster in self._get_modeled_clusters():
            nodes = self.get_children(join(cluster.path, 'nodes'))
            for cluster_node in nodes:
                self.debug('Checking node {0} for disk luns'
                           ''.format(cluster_node.item_id))
                disks = self.get_children(
                    join(cluster_node.path, 'system/disks'))
                for disk in disks:
                    if disk.item_type == 'lun-disk':
                        if int(disk.get_property('snap_size')) > 0:
                            lun_name = disk.get_property('lun_name')
                            self.debug('Found LUN {0}/{1}'
                                       ''.format(disk.item_id, lun_name))
                            lun_disks[lun_name] = disk
        return lun_disks

    def get_nodes_with_luns(self):
        """
        Get a list of compute nodes that contain SAN LUNs.

        :returns: A set of hostnames

        :rtype: set
        """
        lun_nodes = set([])

        for cluster in self._get_modeled_clusters():
            nodes = self.get_children(join(cluster.path, 'nodes'))
            for cluster_node in nodes:
                self.debug('Checking node {0} for disk luns'
                           ''.format(cluster_node.item_id))
                disks = self.get_children(
                    join(cluster_node.path, 'system/disks'))
                for disk in disks:
                    if disk.item_type == 'lun-disk':
                        lun_nodes.add(cluster_node.get_property('hostname'))
        return lun_nodes

    def get_deployment_type(self):
        """
        Determine if the deployment is VNX or Unity

        :return: str
        """
        san_providers = [p for p in self.get_children(self.p_storage_providers)
                         if p.item_type == 'san-emc']
        if not san_providers:
            self.info("No SAN providers found")
            return ''
        provider = san_providers[0].get_property('san_type').lower()
        if provider.startswith('vnx'):
            return 'vnx'
        elif provider == 'unity':
            return 'unity'
        self.error("SAN provider is {0}, accepted options are vnx or unity."
            "Falling back to the one with highest requirements".format(
                provider
        ))
        return 'vnx'

    def _get_lun_providers(self, lun_list):
        """
        Group the input ``lun_list`` by StoragePool
         {
            <storage_pool> : {
                'san': <SAN connection details (san-emc)> ,
                'luns', <List of LUNs in the storage pool>
            }
            ....
         }

        :param lun_list: Collection of LUN items to group by storage pool
        :type lun_list: dict
        :return: dict
        """
        san_list = {}
        for provider in self.get_children(self.p_storage_providers):
            if provider.item_type == 'san-emc':
                for container in self.get_children(
                        join(provider.path, 'storage_containers')):
                    san_list[container.get_property('name')] = provider

        pool_lun_info = {}
        for _, lun_data in lun_list.items():
            lun_container = lun_data.get_property('storage_container')
            if lun_container in san_list:
                san = san_list[lun_container]
                if lun_container not in pool_lun_info:
                    pool_lun_info[lun_container] = {
                        'san': san,
                        'luns': []
                    }
                pool_lun_info[lun_container]['luns'].append(lun_data)
        return pool_lun_info

    def get_snapshots(self):  # pylint: disable=too-many-locals
        """
        Get a list of modeled LUNs that can be snapped and
         associated snapshots (if any)

        :returns: Collecion of modeled LUNs that can be snapped and
         associated snapshots (if any)
        :rtype: dict
        """
        self.debug('Getting SAN snapshot details ...')
        # Get lun-disks that can be snapped i.e. snap_size > 0 (snap_external
        # is ignored; once 'snap_size>0' someone has to snap it ... ).
        snappable_luns = self.get_node_lundisks()

        lun_providers = self._get_lun_providers(snappable_luns)
        pooled_lun_snap_info = {}
        for pool_name, pool_data in lun_providers.items():
            modeled_san = pool_data['san']
            modeled_luns = pool_data['luns']

            modeled_lun_names = []
            for modeled_lun in modeled_luns:
                modeled_lun_names.append(modeled_lun.get_property('lun_name'))
            san_name = modeled_san.get_property('name')
            sp_ipa = modeled_san.get_property('ip_a')
            sp_ipb = modeled_san.get_property('ip_b')

            decrypt = Decryptor()
            password_key = modeled_san.get_property('password_key')
            san_username = modeled_san.get_property('username')
            san_type = modeled_san.get_property('san_type')

            try:
                san_password = decrypt.get_password(password_key,
                                                    san_username)
            except NoSectionError:
                raise LitpSnapError('Could not get password for key '
                                    '{0}'.format(password_key))

            cli_conn_details = {
                SAN_POOLNAME: pool_name,
                SAN_SPA_IP: sp_ipa, SAN_SPB_IP: sp_ipb,
                SAN_LOGIN_SCOPE: modeled_san.get_property('login_scope'),
                SAN_USER: san_username, SAN_PW: san_password,
                SAN_TYPE: san_type
            }
            cli = NavisecCLI(cli_conn_details, verbose=self._verbose)

            self.debug(
                'Connected to {0} ({1}/{2})'.format(san_name, sp_ipa, sp_ipb))
            self.debug('Getting all {0} LUN snapshots ...'.format(pool_name))

            lun_snaps = cli.list_all_snaps()
            pool_luns = cli.list_all_luns(pool_name)
            pool_info = cli.get_storagepool_info(pool_name)

            for snap in lun_snaps:
                self.debug('Have Snapshot {0}/{1}'.format(snap.snap_name,
                                                      snap.resource_id))

            pooled_lun_snap_info[pool_name] = {
                'luns': {},
                'pool': pool_info
            }

            for lun in pool_luns:
                if lun.name not in snappable_luns:
                    continue
                _luns = pooled_lun_snap_info[pool_name]['luns']
                _luns[lun] = []
                self.debug('Finding snapshots of source LUN {0}'.format(
                    lun.name))
                _luns = pooled_lun_snap_info[pool_name]['luns']
                for snap in lun_snaps:
                    if snap.resource_id == lun.id:
                        _luns[lun].append(snap)

        return pooled_lun_snap_info

    def list_snapshots(self,  # pylint: disable=too-many-locals
                       snap_name, detailed=False):
        """
        For all nodes in the deployment, list the snapshots of modeled
         LUNs that have ``snap_size > 0``

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :param detailed: Show detailed information of the snapshots (default
            is ``False``)
        :type detailed: bool

        """
        fmt_str = 'SAN - {0:40} - {1:30}'

        lun_snapshots = self.get_snapshots()
        for pool_name in lun_snapshots.keys():
            pool_luns = lun_snapshots[pool_name]['luns']
            pool_info = lun_snapshots[pool_name]['pool']

            l_pool = 'Pool:{0}/{1}'.format(pool_name, pool_info.id)
            lstr = fmt_str.format(l_pool, 'Total Subscription: {0}%'.format(
                pool_info.subscribed
            ))
            self.info(lstr)
            for lun, snaps in pool_luns.items():
                l_lun = 'LUN:' \
                        '{0}/{1}/{2}'.format(pool_name.strip(),
                                             lun.name.strip(),
                                             lun.id.strip())
                w_snap_name = get_volume_snapshot_name(lun.name, snap_name)
                snap_found = False
                if snaps:
                    for snap in snaps:
                        if snap_name == '*' or w_snap_name == snap.snap_name:
                            snap_found = True
                            log_str = fmt_str.format(l_lun, snap.snap_name)
                            if detailed:
                                log_str += ' Creation: "{0}"'.format(
                                    snap.creation_time)
                                log_str += ' State: "{0}"'.format(snap.state)
                            self.info(log_str)
                if not snap_found:
                    self.info(fmt_str.format(l_lun, 'N/A'))

    def validate_snapshots(self, snap_name):
        """
        For all nodes in the deployment, validate the snapshots of modeled
         LUNs that have ``snap_size > 0``

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :returns: ``True`` if the snapshots are OK, ``False`` otherwise
        :rtype: bool

        """
        lun_snapshots = self.get_snapshots()
        invalid_snaps = False
        for pool_name in lun_snapshots.keys():
            pool_luns = lun_snapshots[pool_name]['luns']
            pool_info = lun_snapshots[pool_name]['pool']

            if float(pool_info.subscribed) >= 100:
                invalid_snaps = True
                self.error('SAN - Pool "{0}" total subscription is {1}%'
                           ''.format(pool_name,
                                     pool_info.subscribed))

            for lun, snaps in pool_luns.items():

                l_lun = '{0}/{1}/{2}'.format(pool_name.strip(),
                                             lun.name.strip(),
                                             lun.id.strip())
                wanted_snap_name = get_volume_snapshot_name(lun.name,
                                                            snap_name)
                required_snap = None
                for snap in snaps:
                    if wanted_snap_name == snap.snap_name:
                        required_snap = snap
                        break

                if required_snap:
                    self.info(
                        'SAN - {0} has expected snapshot '
                        '"{1}"'.format(l_lun, wanted_snap_name))
                else:
                    self.error('SAN - Could not find snapshot '
                               'named "{0}" for {1}'
                               ''.format(wanted_snap_name, l_lun))
                    invalid_snaps = True
        return not invalid_snaps


class LitpNasSnapshots(LitpBaseSnapshots):
    """
    Class to handle list/validate of SAN snapshots created via LITP plugins.
    """

    def __init__(self, verbose=False):
        super(LitpNasSnapshots, self).__init__(verbose)

    def get_snapshots(self, detailed):  # pylint: disable=R0912,R0914
        """
        Get a list of modeled filesystems that can be snapped and
         associated snapshots (if any)

        :param detailed: Get detailed snapshot info
        :type detailed: bool
        :returns: Collecion of modeled filesystems that can be snapped and
         associated snapshots (if any)
        :rtype: dict
        """
        self.debug('Getting NAS snapshot details ...')
        pooled_nas_snap_info = {}
        for nas_provider in self.get_children(self.p_storage_providers):
            if nas_provider.item_type == 'sfs-service':

                decrypt = Decryptor()
                password_key = nas_provider.get_property('password_key')
                nas_username = nas_provider.get_property('user_name')
                try:
                    nas_password = decrypt.get_password(password_key,
                                                        nas_username)
                except NoSectionError:
                    raise LitpSnapError('Could not get password for key '
                                        '{0}'.format(password_key))

                nasconsole = nas_provider.get_property('management_ipv4')
                nascli = NasConsole(nasconsole, nas_username, nas_password)
                nas_rbcaches = nascli.storage_rollback_cache_list()
                nas_name = nas_provider.get_property('name')
                self.debug('Connected to {0} ({1})'.format(nas_name,
                                                           nasconsole))
                pools = self.get_children(
                    '{0}/pools'.format(nas_provider.path))
                for sp_pool in pools:
                    sp_pool_name = sp_pool.get_property('name')

                    pooled_nas_snap_info[sp_pool_name] = {
                        'filesystems': {},
                        'caches': {}
                    }
                    _caches = pooled_nas_snap_info[sp_pool_name]['caches']

                    # pooled_nas_cacheinfo[sp_pool_name] = rbcaches
                    self.debug('Getting all FS snapshots ...')

                    pool_caches = self.get_children(
                        join(sp_pool.path, 'cache_objects'))

                    for cache in pool_caches:
                        cache_name = cache.get_property('name')
                        if cache_name in nas_rbcaches:
                            _caches[cache_name] = nas_rbcaches[cache_name]
                        else:
                            # No cache in the pool
                            _caches[cache_name] = {}
                        _caches[cache_name]['modeled'] = True

                    for nas_cache, nas_cinfo in nas_rbcaches.items():
                        # Add other caches that are part of the SFS pool
                        if nas_cache not in _caches:
                            nas_cinfo['modeled'] = False
                            _caches[nas_cache] = nas_cinfo

                    nas_fs_snaps = {}

                    for fs_name, rb_list in nascli.storage_rollback_list(
                            sp_pool_name, '*').items():
                        nas_fs_snaps[fs_name] = {}
                        rollback_info = {}
                        if detailed:
                            rollback_info = nascli.storage_rollback_info(
                                fs_name)
                        for rollback in rb_list:
                            nas_fs_snaps[fs_name][
                                rollback] = rollback_info.get(rollback, {})

                    fs_list = self.get_children(
                        '{0}/file_systems'.format(sp_pool.path))

                    _filesystems = pooled_nas_snap_info[sp_pool_name][
                        'filesystems']

                    for nas_fs in fs_list:
                        if int(nas_fs.get_property('snap_size')) > 0:
                            fs_name = basename(nas_fs.get_property('path'))
                            _filesystems[nas_fs] = nas_fs_snaps.get(fs_name,
                                                                    {})
        return pooled_nas_snap_info

    def list_snapshots(self,  # pylint: disable=R0914
                       snap_name, detailed=False):
        """
        For all nodes in the deployment, list the snapshots of modeled
         filesystems that have ``snap_size > 0``

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :param detailed: Show detailed information of the snapshots (default
            is ``False``)
        :type detailed: bool

        """
        fstr = 'NAS - {0:40} - {1:20}'
        nas_snapshots = self.get_snapshots(detailed)
        for pool_name in nas_snapshots.keys():
            pool_filesystems = nas_snapshots[pool_name]['filesystems']
            caches = nas_snapshots[pool_name]['caches']
            for cache_name, cache_info in caches.items():
                l_cache = 'Cache:{0}/{1}'.format(pool_name, cache_name)
                if 'size_mb' in cache_info:
                    used_perc = '{0}%'.format(cache_info['used_perc'])
                    size_mb = '{0}Mb'.format(cache_info['size_mb'])
                else:
                    used_perc = 'N/A'
                    size_mb = 'N/A'
                lstr = fstr.format(l_cache,
                                   'Usage: {0}, Size: {1}'.format(used_perc,
                                                                  size_mb))
                if snap_name == '*' or cache_info['modeled']:
                    self.info(lstr)

            for filesystem, snaps in pool_filesystems.items():
                fs_name = basename(filesystem.get_property('path'))
                w_snap_name = get_volume_snapshot_name(fs_name, snap_name)
                l_vol = 'FS:{0}/{1}'.format(pool_name,
                                            fs_name)
                snap_found = False
                if snaps:
                    for snap in snaps:
                        if snap_name == '*' or w_snap_name == snap:
                            snap_found = True
                            l_snap = snap
                            log_str = fstr.format(l_vol, l_snap)
                            if detailed and self.nas_type_name == 'veritas':
                                log_str += ' Creation: "{0}"'.format(
                                        snaps[snap]['SNAPDATE'])
                                log_str += ' Changed: {0}'.format(
                                        snaps[snap]['CHANGED_DATA'])
                                log_str += ' Synced: {0}'.format(
                                        snaps[snap]['SYNCED_DATA'])
                            elif detailed and self.nas_type_name != 'veritas':
                                log_str += ' Creation: "{0}"'.format(
                                        snaps[snap]['CREATIONTIME'])
                            self.info(log_str)
                if not snap_found:
                    self.info(fstr.format(l_vol, 'N/A'))

    def validate_snapshots(self, snap_name):
        """
        For all nodes in the deployment, validate the snapshots of modeled
         filesystems that have ``snap_size > 0``

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :returns: ``True`` if the snapshots are OK, ``False`` otherwise
        :rtype: bool

        """
        nas_snapshots = self.get_snapshots(False)
        invalid_snaps = False
        for pool_name in nas_snapshots.keys():
            pool_filesystems = nas_snapshots[pool_name]['filesystems']
            caches = nas_snapshots[pool_name]['caches']
            for cache_name, cache_info in caches.items():
                if not cache_info['modeled']:
                    # Only check thge cache usage if its flagged as being
                    # in the deployment model
                    continue
                if 'used_perc' in cache_info:
                    usage = float(cache_info['used_perc'])
                    if usage >= 100:
                        self.error(
                            'NAS - Rollback cache {0} for pool {1} is '
                            'at {2}% usage!'.format(cache_name,
                                                    pool_name,
                                                    usage))
                        invalid_snaps = True
                    else:
                        self.info(
                            'NAS - Pool {0} has expected cache '
                            '"{1}", usage at {2}%'.format(pool_name,
                                                          cache_name,
                                                          usage))
                else:
                    self.error('NAS - Could not find rollback cache '
                               'named "{0}" for pool {1}'
                               ''.format(cache_name,
                                         pool_name))
                    invalid_snaps = True
            for filesystem, snaps in pool_filesystems.items():
                fs_name = basename(filesystem.get_property('path'))
                wanted_snap_name = get_volume_snapshot_name(fs_name, snap_name)
                if wanted_snap_name in snaps:
                    self.info(
                        'NAS - {0}/{1} has expected snapshot '
                        '"{2}"'.format(pool_name,
                                       fs_name,
                                       wanted_snap_name))
                else:
                    self.error('NAS - Could not find snapshot '
                               'named "{0}" for {1}/{2}'
                               ''.format(wanted_snap_name,
                                         pool_name,
                                         fs_name))
                    invalid_snaps = True
        return not invalid_snaps


class LitpVolMgrSnapshots(LitpBaseSnapshots):
    """
    Class to handle list/validate of LVM snapshots created via LITP plugins.
    """

    LV_OPTS = 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,' \
              'lv_snapshot_invalid,snap_percent,lv_time'
    O_LV_ATTR = 'lv_attr'
    C_LV_ATTR = namedtuple(O_LV_ATTR,
                           'vol_type,permissions,alloc_policy,fixed_m,'
                           'state,device,target_type,newly_alloc,'
                           'vol_health,skip')
    C_LOGVOL = namedtuple('logvol', LV_OPTS)

    def __init__(self, verbose=False):
        super(LitpVolMgrSnapshots, self).__init__(verbose)

    @staticmethod
    def is_origin_vol(vol):
        """
        Check if a volume is an origin volume or not.

        :param vol: The volume to check
        :type vol: `LitpVolMgrSnapshots.C_LOGVOL`
        :returns: ``True`` if an origin volume, ``False`` otherwise
        :rtype: bool
        """
        return vol.lv_attr.vol_type in ['o', 'O', '-']

    @staticmethod
    def is_snapshot_vol(vol):
        """
        Check if a volume is an snapshot volume or not.

        :param vol: The volume to check
        :type vol: `LitpVolMgrSnapshots.C_LOGVOL`
        :returns: ``True`` if a snapshot volume, ``False`` otherwise
        :rtype: bool
        """
        return vol.lv_attr.vol_type in ['s', 'S']

    def _get_system_disks(self, node):
        """
        Get a list of modeled disks for a node

        :param node: The node to get the system disks for.
        :type node: LitpObject
        :returns: The node system and a list of system disks for that node
        :rtype: (LitpObject, dict(<str>, <LitpObject>))
        """
        disk_list = {}
        for disk in self.get_children(join(node.path, 'system/disks')):
            disk_list[disk.get_property('name')] = disk
        return self.get(join(node.path, 'system')), disk_list

    def _get_vg_devices(self, volume_group):
        """
        Get a list of modeled physical devices for a volume group

        :param volume_group: The volume group to get the devices for
        :type volume_group: LitpObject
        :returns: Collection of physical devices on the volume group:
            key => device_name, value => LitpObject
        :rtype: dict
        """
        physical_devices = {}
        for phy_device in self.get_children(
                join(volume_group.path, 'physical_devices')):
            physical_devices[
                phy_device.get_property('device_name')] = phy_device
        return physical_devices

    def _get_vg_filesystems(self, volume_group):
        """
        Get a list of modeled filesystems in the volume group.

        :param volume_group: The volume group containing filesystems
        :type volume_group: LitpObject
        :returns: Collection of filesystems in the volume group:
            key => filesystem id, value => LitpObject
        :rtype: dict
        """
        file_systems = {}
        for _filesystem in self.get_children(
                join(volume_group.path, 'file_systems')):
            file_systems[_filesystem.item_id] = _filesystem
        return file_systems

    def _get_node_non_lun_volumegroups(self, node):
        """
        Get a list of modeled volume groups for a node that are not backed
         by a LUN i.e. local storage groups.

        :param node: The node to get the non LUN backed volume groups for
        :type node: LitpObject
        :returns: Collection of volume groups and contained filesystems:
            key -> LitpObject<VolumeGroup>, value -> LitpObject[]
        :rtype: dict
        """
        self.debug('Getting snappable volumes for {0}'.format(node.item_id))
        system_data, systems_disks = self._get_system_disks(node)
        system_name = system_data.get_property('system_name')
        for disk_name, disk_data in systems_disks.items():
            self.debug('System {sysname}({nodeid}) has {type} {mpath} '
                       '(device={devname})'.format(sysname=system_name,
                                                   nodeid=node.item_id,
                                                   type=disk_data.item_type,
                                                   mpath=disk_data.path,
                                                   devname=disk_name))
        snappable_device_types = ['disk']
        non_san_volgroups = {}
        for o_volgrp in self.get_children(join(
                node.path, 'storage_profile/volume_groups')):
            devices = self._get_vg_devices(o_volgrp)
            self.debug(
                'Checking {0} {1} on node {2}'.format(o_volgrp.item_type,
                                                      o_volgrp.item_id,
                                                      node.item_id))
            for device_name, device_data in devices.items():
                itemtype = device_data.item_type
                self.debug('Node {0} has {1} {2} '
                           '({3})'.format(node.item_id,
                                          itemtype,
                                          device_data.path,
                                          device_data.item_id))

                if device_name in systems_disks:
                    system_dev = systems_disks[device_name]
                    self.debug('Node {id} {dev_type} "{dev_id}" is on '
                               'system {sysdevtype} "{sysdevid}"'
                               ''.format(id=node.item_id,
                                         dev_type=itemtype,
                                         dev_id=device_data.item_id,
                                         sysdevtype=system_dev.item_type,
                                         sysdevid=system_dev.item_id))
                    if system_dev.item_type in snappable_device_types:
                        non_san_volgroups[o_volgrp] = \
                            self._get_vg_filesystems(o_volgrp)
                else:
                    raise LitpSnapError('Could not get the system disk for '
                                        'physical device {0}'
                                        ''.format(device_name))
        return non_san_volgroups

    def _get_modeled_non_lun_volumegroups(self):  # pylint: disable=C0103
        """
        Get a list of modeled volume groups that are not backed by a LUN
         for all nodes in a deployment (LMS included)

        :returns: Collection of volume groups and contained filesystems for
         each node in the deployment

        :rtype: dict
        """
        lms = self.get('/ms')
        nodes = {lms: self._get_node_non_lun_volumegroups(lms)}

        for cluster in self._get_modeled_clusters():
            for node in self._get_modeled_nodes(cluster):
                non_lun_groups = self._get_node_non_lun_volumegroups(node)
                if non_lun_groups:
                    nodes[node] = non_lun_groups
        return nodes

    def _parse_lvs(self, lvdata):  # pylint: disable=W0212
        """
        Parse ``lvs`` output data into a mapping of origin volumes and
         associated snapshots (if any)

        :param lvdata: Output from ``lvs`` command
        :type lvdata: str[]
        :returns: Collecion of origin volumes and any associated snapshot
         volumes

        :rtype: dict
        """
        headers = lvdata[0].split(',')

        origin_volumes = {}
        snap_volumes = []

        for line in lvdata[1:]:
            line = line.strip()

            if 'File descriptor' in line or 'Input/output ' \
                                            'error' in line or not line:
                continue
            line = line.split(',')
            replace_index = headers.index(LitpVolMgrSnapshots.O_LV_ATTR)

            _c_lv_attr = LitpVolMgrSnapshots.C_LV_ATTR
            # noinspection PyProtectedMember
            line[replace_index] = _c_lv_attr._make(  # pylint: disable=W0212
                                                     list(line[replace_index]))

            # noinspection PyProtectedMember
            vol = LitpVolMgrSnapshots.C_LOGVOL._make(  # pylint: disable=W0212
                                                       line)
            self.debug('LV: {0}'.format(vol))

            if LitpVolMgrSnapshots.is_origin_vol(vol):
                if vol.vg_name not in origin_volumes:  # pylint: disable=E1101
                    origin_volumes[vol.vg_name] = {}  # pylint: disable=E1101
                origin_volumes[vol.vg_name][vol] = []  # pylint: disable=E1101

            if LitpVolMgrSnapshots.is_snapshot_vol(vol):
                snap_volumes.append(vol)

        for snap in snap_volumes:
            if snap.vg_name not in origin_volumes:
                continue
            for ovol in origin_volumes[snap.vg_name].keys():
                if ovol.lv_name == snap.origin:
                    origin_volumes[snap.vg_name][ovol].append(snap)
                    break
        return origin_volumes

    def _get_node_logical_volumes(self, node_hostnames):
        """
        Get LVM data from nodes in the deployment

        :param node_hostnames: List of nodes to get the LVM data from
        :type node_hostnames: str[]
        :returns: Collection of origin volumes and associated snapshot volumes
         (if any) for each node.
        :rtype: dict
        """
        self.debug(
            'Getting LV data from {0}'.format(', '.join(node_hostnames)))
        host_lv_data = EnminstAgent().lvs_list(node_hostnames,
                                               LitpVolMgrSnapshots.LV_OPTS)
        hosts_data = {}
        for hostname, lvdata in host_lv_data.items():
            origin_volumes = self._parse_lvs(lvdata.split('\n'))
            hosts_data[hostname] = origin_volumes
        return hosts_data

    def _get_modeled_lvm_snapshots(self,  # pylint: disable=R0914
                                   modeled_volume_groups, node_vg_data):
        """
        With a list if what should be snapped i.e. modeled, get what is
         actually snapped (lvm data from nodes)

        :param modeled_volume_groups: Modeled filesystems that should be
         snapped
        :type modeled_volume_groups: dict
        :param node_vg_data: LVM data from the nodes
        :type node_vg_data: dict

        :returns: Collection of modeled filesystems and any associated real
         snapshots

        :rtype: dict
        """
        # only show modeled filesystems regardless of what node returns....
        applied_volgrps = {}
        for host, m_volgrps in modeled_volume_groups.items():
            hostname = host.get_property('hostname')
            real_node_vgs = node_vg_data[hostname]

            applied_volgrps[hostname] = {}

            for m_volgrp, m_vg_fslist in m_volgrps.items():
                m_volname = m_volgrp.get_property('volume_group_name')
                applied_volgrps[hostname][m_volname] = {}

                for m_fsname, _ in m_vg_fslist.items():
                    mapped_fs_name = '{0}_{1}'.format(m_volgrp.item_id,
                                                      m_fsname)
                    if m_volname in real_node_vgs:
                        r_vg = real_node_vgs[m_volname]
                        for r_fs, r_fs_snaps in r_vg.items():
                            if r_fs.lv_name == mapped_fs_name:
                                applied_volgrps[hostname][m_volname][
                                    r_fs] = r_fs_snaps
                    else:
                        self.debug('No volume group called "{0}" found '
                                   'on node {1}'.format(m_volname, hostname))
        return applied_volgrps

    def _get_kickstart_snapshots(self):
        """
        Get origin volumes from the LMS and any associated snapshots.
        These volumes arnt modeled but created at LMS install time.

        :returns: Any volume groups (and filesystems) on the LMS that arn't
         modeled (exluding swap).

        :type: dict
        """
        lvdata = exec_process(['lvs', '-o', LitpVolMgrSnapshots.LV_OPTS,
                               '--separator', ',', '--unquoted',
                               '--noheadings']).split('\n')
        lvdata.insert(0, LitpVolMgrSnapshots.LV_OPTS)
        # Remove swap from the list
        lms_vols = self._parse_lvs(lvdata)
        # Use dictionary keys() to iterate, prevents dictionary change
        # errors as dict.keys() makes a copy
        for volgroup in lms_vols.keys():
            lv_list = lms_vols[volgroup].keys()
            for logvol in lv_list:
                info = exec_process(['/sbin/blkid', '-o', 'export',
                                     '/dev/{0}/{1}'.format(volgroup,
                                                           logvol.lv_name)])
                for line in info.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    name, value = line.split('=', 1)
                    if name == 'TYPE' and value == 'swap':
                        del lms_vols[volgroup][logvol]
        return lms_vols

    def get_snapshots(self):
        """
        Get a list of modeled filesystems that can be snapped and
         associated snapshots (if any)

        :returns: Collecion of modeled filesystems that can be snapped and
         associated snapshots (if any)
        :rtype: dict
        """
        self.debug('Getting VOLMGR snapshot details ...')
        modeled_volgrps = self._get_modeled_non_lun_volumegroups()

        hostnames = []
        for node in modeled_volgrps.keys():
            hostnames.append(node.get_property('hostname'))
        real_node_data = self._get_node_logical_volumes(hostnames)

        snapshots = self._get_modeled_lvm_snapshots(modeled_volgrps,
                                                    real_node_data)

        lms_kick_snaps = self._get_kickstart_snapshots()
        lms = self.get('/ms')
        lms_modeled_snaps = snapshots[lms.get_property('hostname')]
        for volgroup, vols in lms_kick_snaps.items():
            for k_vol, k_vol_snaps in vols.items():
                modeled = False
                for l_vol in lms_modeled_snaps[volgroup].keys():
                    # Skip any volumes that are modeled
                    if l_vol.lv_name == k_vol.lv_name:
                        modeled = True
                        break
                if not modeled:
                    if k_vol.vg_name not in lms_modeled_snaps:
                        lms_modeled_snaps[k_vol.vg_name] = {}
                    lms_modeled_snaps[k_vol.vg_name][k_vol] = k_vol_snaps
        return snapshots

    def list_snapshots(self, snap_name, detailed=False):
        """
        For all nodes in the deployment, list the snapshots of modeled
         filesystems that have ``snap_size > 0``

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :param detailed: Show detailed information of the snapshots (default
            is ``False``)
        :type detailed: bool

        """
        snapshots = self.get_snapshots()
        for hostname, volgrp_data in snapshots.items():
            for volgrp_name, origin_vols in volgrp_data.items():
                for origon_vol, snapshots in origin_vols.items():
                    w_snap_name = get_volume_snapshot_name(origon_vol.lv_name,
                                                           snap_name)
                    l_vol = '{0}/{1}/{2}'.format(hostname,
                                                 volgrp_name,
                                                 origon_vol.lv_name)
                    snap_found = False
                    if snapshots:
                        for snap in snapshots:
                            if snap_name == '*' or w_snap_name == snap.lv_name:
                                snap_found = True
                                log_str = 'VOL - {0:40} - {1:20}' \
                                          ''.format(l_vol, snap.lv_name)
                                if detailed:
                                    log_str += 'Usage: {0}%'.format(
                                        snap.snap_percent)
                                    log_str += ', Creation: "{0}"'.format(
                                        snap.lv_time)
                                self.info(log_str)
                    if not snap_found:
                        self.info('VOL - {0:40} - {1:20}'.format(l_vol,
                                                                 'N/A'))

    def validate_snapshots(self, snap_name):
        """
        For all nodes in the deployment, validate the snapshots of modeled
         filesystems that have ``snap_size > 0``

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :returns: ``True`` if the snapshots are OK, ``False`` otherwise
        :rtype: bool

        """
        snapshots = self.get_snapshots()
        invalid_snaps = False
        for hostname, volgrp_data in snapshots.items():
            for volgrp_name, origin_vols in volgrp_data.items():
                for origin_vol, snapshots in origin_vols.items():
                    wanted_snap_name = get_volume_snapshot_name(
                        origin_vol.lv_name,
                        snap_name)
                    required_snap = None
                    for snap in snapshots:
                        if wanted_snap_name == snap.lv_name:
                            required_snap = snap
                            break
                    if required_snap:
                        if required_snap.lv_snapshot_invalid:
                            self.error(
                                'VOL - {0}/{1}/{2} has INVALID '
                                'snapshot "{3}": {4}% usage'
                                '.'.format(hostname,
                                           volgrp_name,
                                           origin_vol.lv_name,
                                           required_snap.lv_name,
                                           required_snap.snap_percent))
                            invalid_snaps = True
                        else:
                            self.info(
                                'VOL - {0}/{1}/{2} has expected snapshot '
                                '"{3}"'.format(hostname,
                                               volgrp_name,
                                               origin_vol.lv_name,
                                               required_snap.lv_name))
                    else:
                        self.error('VOL - Could not find snapshot '
                                   'named "{0}" for {1}/{2}'
                                   ''.format(wanted_snap_name,
                                             volgrp_name,
                                             origin_vol.lv_name))
                        invalid_snaps = True
        return not invalid_snaps


class LitpSnapshots(object):
    """
    Class to handle create/delete/restore/list/validate of LITP plugin
    bases snapshots
    """

    def __init__(self):
        self._log = init_enminst_logging()

    @property
    def logger(self):
        """
        Get the logger
        :returns: The logger
        :rtype: Logger
        """
        return self._log

    def list_snapshot_names(self):
        """
        Show a list of LITP named snapshots.

        """
        litp = LitpRestClient()
        modeled_snapshots = litp.list_snapshots()
        if modeled_snapshots:
            for snap_name in modeled_snapshots:
                self.logger.info('Modeled named snapshot: '
                                 '{0}'.format(snap_name))
        else:
            self.logger.info('No modeled snapshots found.')

    def list_snapshots(self, snap_name, detailed=False, force=False,
                       verbose=False):
        """
        List the snapshots of all volume types (SAN/NAS/LVM) for a named
        LITP snapshot.

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :param detailed: Show detailed snapshot info
        :type detailed: bool
        :param force: Try and get the snapshot info even if the snapshot is
         not modeled.
        :param verbose: Show debug messages
        :type verbose: bool

        """
        litp = LitpRestClient()
        modeled_snapshots = litp.list_snapshots()
        if snap_name in modeled_snapshots:
            self.logger.info('Modeled snapshots: {0}'.format(snap_name))
        else:
            self.logger.info('No modeled snapshot called "{0}" '
                             'exists!'.format(snap_name))
            if not force:
                raise SystemExit(ExitCodes.LITP_NO_NAMED_SNAPS_EXIST)

        LitpVolMgrSnapshots(verbose).list_snapshots(snap_name, detailed)
        LitpSanSnapshots(verbose).list_snapshots(snap_name, detailed)
        LitpNasSnapshots(verbose).list_snapshots(snap_name, detailed)

    def validate_snapshots(self, snap_name, verbose=False, force=False):
        """
        Validate the snapshots of all volume types (SAN/NAS/LVM) for a named
        LITP snapshot.

        :param snap_name: The LITP snapshot name
        :type snap_name: str
        :param force: Try and validate the snapshots even if the snapshot is
         not modeled.
        :param verbose: Show debug messages
        :type verbose: bool

        """
        litp = LitpRestClient()
        modeled_snapshots = litp.list_snapshots()
        if snap_name not in modeled_snapshots:
            self.logger.info('No modeled snapshot called "{0}" '
                             'exists!'.format(snap_name))
            if not force:
                raise SystemExit(ExitCodes.LITP_NO_NAMED_SNAPS_EXIST)

        snaps_ok = LitpVolMgrSnapshots(verbose).validate_snapshots(snap_name)
        snaps_ok &= LitpSanSnapshots(verbose).validate_snapshots(snap_name)
        snaps_ok &= LitpNasSnapshots(verbose).validate_snapshots(snap_name)
        if not snaps_ok:
            raise SystemExit(ExitCodes.LITP_SNAP_ERROR)
