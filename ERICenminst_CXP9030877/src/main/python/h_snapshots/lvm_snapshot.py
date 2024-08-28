# pylint: disable=C0302
"""
Class to handle LVM filesystem snapshots
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
import os.path
import re
import shutil
import socket
from collections import namedtuple
from json import dump, load

from h_litp.litp_rest_client import LitpException, LitpRestClient
from h_litp.litp_utils import LitpObject
from h_puppet.mco_agents import EnminstAgent, FilemanagerAgent, \
    McoAgentException
from h_util.h_utils import exec_process, is_env_on_rack
GRUB_RHEL6 = '/boot/grub/grub.conf'
GRUB_RHEL6_SAVE = '/boot/grub/grub.conf.org'
GRUB_RHEL7 = '/boot/grub2/grub.cfg'
GRUB_RHEL7_SAVE = '/boot/grub2/grub.cfg.org'
GRUB_RHEL7_UEFI = '/boot/efi/EFI/redhat/grub.cfg'
GRUB_RHEL7_UEFI_SAVE = GRUB_RHEL7_UEFI + '.org'
MIGRATION_LOCK_FILE = '/ericsson/custom/migration.lock'
LMS_ROOT_VG_NAME = 'vg_root'
RHEL7_NODE_LIST_FILE = '/ericsson/custom/rhel7_node_list_file.txt'


class LVMManagerException(Exception):
    """
    LVM action failure
    """
    pass


class LVMManager(object):
    """
    Class to run lvm commands snapshot operations

    """

    DEFAULT_LV_OPTS = 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,' \
                      'lv_snapshot_invalid,snap_percent,lv_time'

    def __init__(self, log_silent=False):
        """
        Sets lvm options, lvm arguments and logging
        :param log_silent: disable logging to enminst log
        """
        self.lv_opts = LVMManager.DEFAULT_LV_OPTS
        self.lv_args = '--noheadings --separator , --unquoted'
        self.LogicalVolume = namedtuple(  # pylint: disable=C0103
                'LogicalVolume', self.lv_opts)
        if log_silent:
            self.logger = logging.getLogger('enmsnapshots')
        else:
            self.logger = logging.getLogger('enminst')
        self.log_prefix = 'LVM MGR'
        self.lvm_default_snap_percentage = 100
        self._litp = LitpRestClient()

    @staticmethod
    def process_out(std_out):
        """
        To filter the "File descriptor" warnings thrown by LVM commands,
        which are harmless and need not print them in logging
        :param std_out : standard output
        :return: output
        :type: list
        """
        output = []
        for line in std_out:
            if 'File descriptor' in line or 'Input/output error' in line:
                continue
            output.append(line)
        return output

    def process_lvm_output(self, data):
        """
        Parse LVM command output and return the data on volume and
        volume groups
        :param data : data returned by LVM command
        :return: data in the dictionary format
        :type: dict
        """
        ret_data = []
        data = self.process_out(data.split('\n'))
        for line in data:
            if line:
                parts = line.strip().split(',')
                # noinspection PyProtectedMember
                _class = self.LogicalVolume._make(  # pylint: disable=W0212
                        parts)
                ret_data.append(_class)
        return ret_data

    @staticmethod
    def get_attr(volumes, attr):
        """
        Get any particular attribute from volumes on LMS
        :param volumes : volumes on LMS
        :param attr: LV attributes to get
        :return: attribute value
        :type: string
        """
        return [getattr(vol, attr, '') for vol in volumes]

    def list_volumes(self, volume_group=None, tag=None, exclude_lv=True):
        """
        List the volumes attributes with options specified
        :param volume_group : any particular volume group
        :type volume_group: string
        :param tag : volumes with any particular tag
        :type tag: string
        :param exclude_lv : if swap volume to be included
        :type exclude_lv: boolean
        :return: list volumes attributes
        :type: list
        """
        params = {
            'lv_opts': self.lv_opts,
            'tag': tag and '@%s' % tag or '',
            'lv_args': self.lv_args,
            'vg': volume_group or ''
        }

        if tag:
            # Workaround/fix for typo in default snap name
            params['tag'] += ' @enm_upgarde_snapshot'
        command = 'lvs -o {lv_opts} {tag} {lv_args} {vg}'.format(
                lv_opts=params['lv_opts'],
                tag=params['tag'],
                lv_args=params['lv_args'],
                vg=params['vg'])
        output = exec_process(command.split())
        if exclude_lv:
            volumes = self.process_lvm_output(output)
            return [vol for vol in volumes
                    if vol.lv_name.lower().find('swap') < 0
                    if vol.lv_name.lower().find('log') < 0
                    if vol.lv_name.lower().find('software') < 0]

        return self.process_lvm_output(output)

    def list_origin_volumes(self, volume_group=None, tag=None):
        """
        List the volume origin
        :param volume_group : any particular volume group
        :type volume_group: string
        :param tag : volumes with any particular tag
        :type tag: string
        :return: list volumes groups
        :type: list
        """
        volumes = self.list_volumes(volume_group=volume_group, tag=tag)
        return [vol for vol in volumes if vol.lv_attr.startswith('o')]

    def list_snapshots(self, volume_group=None, tag=None):
        """
        List the snapshots
        :param volume_group : any particular volume group
        :type volume_group: string
        :param tag : volumes with any particular tag
        :type tag: string
        :return: list volumes with snapshot
        :type: list
        """
        volumes = self.list_volumes(volume_group=volume_group, tag=tag)
        return [vol for vol in volumes if vol.lv_attr.startswith('s')]

    def calculate_lvm_snap_size(self):
        """
        Calculate LVM snap size
        :return: snap percentage
        :type: integer
        """
        cmd = 'vgs --units m -o vg_free vg_root --noheadings'
        std_out = exec_process(cmd.split())
        std_out = ''.join(self.process_out(std_out.splitlines()))
        pfree = int(std_out.split('.')[0])
        cmd = 'lvs  --units m -o lv_size --noheadings'
        std_out = exec_process(cmd.split())
        lvs_size = self.process_out(std_out.splitlines())
        sumlsize = 0
        for lv_size in lvs_size:
            if lv_size.strip():
                sumlsize += int(lv_size.split('.')[0].lstrip())
        self.logger.debug("Pfree and sumlsize are calculated to {0} and {1} "
                          "respectively".format(pfree, sumlsize))
        if pfree <= sumlsize:
            return 90 * pfree / sumlsize
        else:
            return self.lvm_default_snap_percentage

    def create_snapshots(self,  # pylint: disable=R0913,C0103
                         volumes, tag='', pc=None, prefix='snapshot',
                         suffix='snap'):
        """
        Create the snapshots
        :param volumes : any particular volume group
        :type volumes: list
        :param tag : snapshot tag name
        :type tag: string
        :param pc : percentage of original volume allocated for snap
        :type pc: integer
        :param prefix : snapshot prefix name
        :type prefix: string
        :param suffix : snapshot suffix name
        :type suffix: string |None
        :return: output of create snapshot
        :type: string
        """
        if self.list_snapshots(tag=tag):
            raise LVMManagerException('LVM snapshots already exist!')
        if tag:
            tag = '--addtag %s' % tag
        self.logger.info('{0}: Creating LVM snapshot(s)'.format(
                self.log_prefix))
        outputs = list()
        for volume in volumes:
            params = {
                'tag': tag,
                'percent': volume['fs_snap_size'] if not pc else pc,
                'prefix': prefix and '%s_' % prefix or '',
                'vol_name': volume['lv_name'],
                'suffix': suffix and '_%s' % suffix or '',
                'vol_path': volume['lv_path'],
            }

            command = 'lvcreate -s {tag} ' \
                      '-l {percent}%ORIGIN ' \
                      '-n {prefix}{vol_name}{suffix} ' \
                      '{vol_path}'.format(tag=params['tag'],
                                          percent=params['percent'],
                                          prefix=params['prefix'],
                                          vol_name=params['vol_name'],
                                          suffix=params['suffix'],
                                          vol_path=params['vol_path'])

            self.logger.info('{0}: Creating snapshot for volume {1}'.
                             format(self.log_prefix, volume['lv_name']))
            try:
                std_out = exec_process(command.split())
                std_out = ''.join(self.process_out(std_out.splitlines()))
                outputs.append(std_out.strip())
            except IOError as error:
                std_out = 'Failed to create snapshot for %s with message %s' \
                          % (volume['lv_name'], error.strerror)
                raise LVMManagerException(std_out)
        return outputs

    def remove_snapshots(self, tag=None, volumes=None):
        """
        Remove the snapshots
        :param tag: Remove the snapshot of any particular tag
        :type tag: string
        :param volumes: Remove the snapshot of any particular volume
        :type volumes: list
        :return: output of remove snapshot
        :rtype: string
        """
        volumes = volumes or list()
        volume_paths = [vol.lv_path for vol in volumes]
        params = {
            'tag': tag and '@%s' % tag or '',
            'vol_paths': ' '.join(volume_paths),
        }

        # Workaround/fix for typo in default snap name
        params['tag'] += ' @enm_upgarde_snapshot'

        command = 'lvremove -f {tag} {vol_paths}'.format(
                tag=params['tag'], vol_paths=params['vol_paths'])
        if tag:
            self.logger.info('%s: Removing LVM snapshots with tag: %s' %
                             (self.log_prefix, tag))
        if volume_paths:
            self.logger.info('%s: Removing snapshots %s' %
                             (self.log_prefix, volume_paths))
        _stdout = exec_process(command.split()).splitlines()
        return self.process_out(_stdout)

    def restore_snapshots(self, tag=None, volumes=None):
        """
        Restore the snapshots
        :param tag: Restore the snapshot of any particular tag
        :type tag: string
        :param volumes: Restore the snapshot for any particular volume
        :type volumes: list
        :return: output of restore snapshot
        :rtype: string
        """
        volumes = volumes or list()
        volume_paths = [vol.lv_path for vol in volumes]

        params = {
            'tag': tag and '@%s' % tag or '',
            'vol_paths': ' '.join(volume_paths),
        }

        # Workaround/fix for typo in default snap name
        if tag:
            params['tag'] += ' @enm_upgarde_snapshot'

        command = 'lvconvert --merge {tag} {vol_paths}'.format(
                tag=params['tag'], vol_paths=params['vol_paths']
        )

        if tag:
            self.logger.info('%s: Restoring LVM snapshots with tag: %s'
                             % (self.log_prefix, tag))
        if volume_paths:
            self.logger.info('%s: Restoring snapshots %s' %
                             (self.log_prefix, volume_paths))

        return self.process_out(exec_process(command.split()).splitlines())

    def get_nodes_using_local_storage(self, ignore_states=None,
                                      is_migration=False):
        """
        Get a collection of nodes that are using physical disks for
        filesystems.

        :param ignore_states: The state of a nodes in the deployment model
                                ie. Initial, Applied
        :type ignore_states: list
        :returns: Map of node->list[device_names]

        :rtype: dict
        """
        _cluster_nodes = self._litp.get_cluster_nodes()
        if ignore_states is None:
            if is_migration:
                ignore_states = []
            else:
                ignore_states = [LitpRestClient.ITEM_STATE_INITIAL]

        local_disk_nodes = {}
        for _nodes in _cluster_nodes.values():
            for _node in _nodes.values():
                if _node.state in ignore_states:
                    continue
                # Check if the node has any LUN's attached to it.
                for _disk in self._litp.get_children(
                        '{0}/system/disks'.format(_node.path)):
                    odisk = LitpObject(None, _disk['data'],
                                       self._litp.path_parser)
                    if not odisk.get_property('lun_name'):
                        if _node.item_id not in local_disk_nodes:
                            local_disk_nodes[_node] = []
                        local_disk_nodes[_node].append(
                                odisk.get_property('name'))
        return local_disk_nodes


# pylint: disable=too-many-instance-attributes
class LVMSnapshots(object):
    """
    Class to run LVM snapshot operations for a deployment
    """

    DEFAULT_SNAPSHOT_LABEL = 'enm_upgrade_snapshot'

    def __init__(self, snap_prefix, tag=DEFAULT_SNAPSHOT_LABEL,
                 log_silent=False):
        """
        Constructor
        :param snap_prefix: snapshot prefix name
        :type snap_prefix: string
        :param tag: Tag name for the snapshot
        :type tag: string
        :param log_silent: disable logging to enminst log
        :type tag: boolean
        :return:
        """
        self.snap_prefix = snap_prefix
        self.tag = tag
        self.lvm = LVMManager(log_silent)
        if log_silent:
            self.logger = logging.getLogger('enmsnapshots')
        else:
            self.logger = logging.getLogger('enminst')
        self.log_prefix = 'LVM SNAP'
        self._litp = LitpRestClient()
        self.grub = GRUB_RHEL6
        self.grub_save = GRUB_RHEL6_SAVE

    @staticmethod
    def _fmt_snap_log(log_prefix, snap_volume, details):
        """
        Format a string to log for the snapshot volume
        :param log_prefix: A log string prefix
        :type log_prefix: str
        :param snap_volume: The snapshot volue to get the info from
        :type snap_volume: LVMManager.LogicalVolume
        :param details: Include more info on the snapshot e.g. creation time
        :type details: bool
        :returns: A formatted log message
        :rtype: str
        """
        _str = ['{prefix}{lv_name} with tag @{lv_tags}'.format(
                prefix=log_prefix, lv_name=snap_volume.lv_name,
                lv_tags=snap_volume.lv_tags)]
        if details:
            _str.append('{prefix}  Origin     {vg}/{origin}'.format(
                    prefix=log_prefix, vg=snap_volume.vg_name,
                    origin=snap_volume.origin))
            _str.append('{prefix}  Attributes {lv_attr}'.format(
                    prefix=log_prefix, lv_attr=snap_volume.lv_attr))
            _str.append('{prefix}  Usage      {usage}%'.format(
                    prefix=log_prefix, usage=snap_volume.snap_percent))
            _str.append('{prefix}  Creation   {ctime}'.format(
                    prefix=log_prefix, ctime=snap_volume.lv_time))
        return _str

    def lms_snapshots(self, snap_tag, details, volume_group=None):
        """
        Get a list of LMS LVM snapshots
        :param snap_tag: A snapshot tag to use to match against snapshots
        :type snap_tag: str
        :param details: Include more info on the snapshot e.g. creation time
        :type details: bool
        :param volume_group: The volume group to get the snapshots in
        :type volume_group: str
        :returns: List of LMS LV snapshots
        :rtype: str[]
        """
        self.logger.debug('{0}: List of available snapshots on host {1}'.format
                          (self.log_prefix, socket.gethostname()))
        _lms_snapshots = self.lvm.list_snapshots(volume_group=volume_group,
                                                 tag=snap_tag)
        _logp = '{0}: LMS snapshot: '.format(self.log_prefix)
        for snap in _lms_snapshots:
            for _logstr in self._fmt_snap_log(_logp, snap, details):
                self.logger.info(_logstr)
        if not _lms_snapshots:
            self.logger.info('{0}: No LMS LVM snapshots found on the system'
                             ' (tag={1}).'.format(self.log_prefix,
                                                  snap_tag))
        return _lms_snapshots

    def nodelocal_snapshots(self, snap_tag, details):
        """
        Get a list of LV snapshots that exist on nodes using local storage

        :param snap_tag: A snapshot tag to use to match against snapshots
        :type snap_tag: str
        :param details: Include more info on the snapshot e.g. creation time
        :type details: bool
        :returns: Dictionary of hosts and snapshots
        :rtype: dict
        """
        self.logger.debug(
                '{0}: Reading available node local Logical Volumes.'.format(
                        self.log_prefix))
        node_local_vols = self._get_node_snappable_localvols(self.snap_prefix)
        if not node_local_vols:
            return {}
        agent = EnminstAgent()
        lvm = LVMManager()
        host_data = agent.lvs_list(node_local_vols.keys(), lvm.lv_opts)

        host_snaps = {}
        for _host, _lvdata in host_data.items():
            volumes = lvm.process_lvm_output(_lvdata)
            _logp = '{0}: {1} snapshot: '.format(self.log_prefix, _host)
            # Skip the first entry as thats the headers returned by the
            # agent
            for _lv in volumes[1:]:
                if _lv.lv_attr.startswith('s') and snap_tag in _lv.lv_tags:
                    if _host not in host_snaps:
                        host_snaps[_host] = []
                    host_snaps[_host].append(_lv)
                    for _logstr in self._fmt_snap_log(_logp, _lv, details):
                        self.logger.info(_logstr)
            if _host not in host_snaps:
                self.logger.info('{0}: No {1} LVM snapshots found on the '
                                 'system (tag={2}).'.format(self.log_prefix,
                                                            _host, snap_tag))
        return host_snaps

    def list_snapshots(self, details, volume_group=None,
                       tag=DEFAULT_SNAPSHOT_LABEL):
        """
        List the snapshots on LMS
        :param volume_group : any particular volume group
        :type volume_group: string
        :param tag : volumes with any particular tag
        :type tag: string
        :param details: Get more details on the snapshots i.e. creation date
        :type details: bool
        :return: list of snapshots
        :rtype: list
        """
        _lms_snapshots = self.lms_snapshots(tag, details, volume_group)
        _nodelocal_snapshots = self.nodelocal_snapshots(tag, details)
        return _lms_snapshots, _nodelocal_snapshots

    def _get_lms_snappable_vols(self):
        """
        List LVs to be snapshotted on LMS. Will get the information from the
        model.
        :return: list of volumes to be snapshotted
        :rtype: list
        """
        fs_list = []
        vg_path = '/ms/storage_profile/volume_groups'
        try:
            all_vgs = LitpObject(None, self._litp.get(vg_path, log=False),
                                 self._litp.path_parser)
        except LitpException as exception:
            err_msg = "Cannot snapshot, an error occurred while getting " \
                      "volume groups in {0}: {1}".format(vg_path, exception)
            raise LVMManagerException(err_msg)
        non_applied_fs = []
        for vg_obj in all_vgs.children.itervalues():
            # LitpObject does not follow links in inherited items, so doing
            # vg_obj.children['file_systems'].children is not possible
            fss_path = "{0}/file_systems".format(vg_obj.path)
            try:
                all_fss = LitpObject(None,
                                     self._litp.get(fss_path, log=False),
                                     self._litp.path_parser)
            except LitpException as exception:
                err_msg = 'Cannot snapshot, an error occurred while getting' \
                          ' file systems in {0}: {1}'.format(fss_path,
                                                             exception)
                raise LVMManagerException(err_msg)
            for fs_item_id, fs_obj in all_fss.children.iteritems():
                if fs_obj.state == LitpRestClient.ITEM_STATE_INITIAL:
                    # we do not care about LVs in Initial state. Since they
                    # will not exist yet they will not cause any damage to the
                    # snapshotting process, so it is safe to ignore them
                    continue
                if fs_obj.state != LitpRestClient.ITEM_STATE_APPLIED:
                    non_applied_fs.append(fs_item_id)
                fs_snap_size = fs_obj.properties.get('snap_size')
                if int(fs_snap_size) != 0:
                    lv_name = LVMSnapshots._get_ms_lv_name(vg_obj, fs_obj)
                    lv_path = LVMSnapshots._get_ms_lv_path(vg_obj, fs_obj)
                    fs_list.append({'fs_item_id': fs_item_id,
                                    'fs_snap_size': int(fs_snap_size),
                                    'lv_name': lv_name,
                                    'lv_path': lv_path})
        if non_applied_fs:
            err_msg = "Cannot snapshot, file system(s) '{0}' are not " \
                      "in Applied state".format(', '.join(non_applied_fs))
            raise LVMManagerException(err_msg)
        return fs_list

    @staticmethod
    def _get_ms_rootvg_fss():
        """
        List LVs which get installed by kickstart on LMS
        :return: list of default volumes
        :rtype: list
        """
        rootvg_fss = []
        for line in exec_process(['df', '-P']).split('\n')[1:]:
            if not line:
                continue
            dev_mapper_path, mountpoint = line.split()[0], line.split()[-1]
            vg_name, lv_name = LVMSnapshots._parse_df_path(dev_mapper_path)
            if not vg_name:
                # no entry in /dev/mapper, skip this line and keep going
                continue
            if vg_name == LMS_ROOT_VG_NAME:
                rootvg_fss.append([lv_name, mountpoint])
        return rootvg_fss

    @staticmethod
    def _parse_df_path(path):
        """
        Parse the output of the df command, particularly the first column of
        the output, which shows the volume path in /dev/mapper.
        :param path : path in /dev/mapper
        :type path: string
        :return: list of vg_name, lv_name
        :rtype: list
        """
        # first expect a /dev/mapper path
        # then anything that is not - (VG name)
        # a VG can have - at the end of its name, so then we can expect any
        # even number of - (that's because the mapper will add an extra - for
        # each - in the VG/LV name)
        # then expect a single -, which is the separator between the VG and LV
        # finally expect the LV name
        regex = r'^/dev/mapper/((?:[^-]*(?:--)*)+)-([^-].*)$'
        try:
            vg_name, lv_name = re.match(regex, path).groups()
        except AttributeError:
            # some entries in df don't have a /dev/mapper path. That does not
            # mean a failure, so return
            return [None, None]
        # dev mapper adds an extra - for each - char
        return [vg_name.replace('--', '-'), lv_name.replace('--', '-')]

    @staticmethod
    def _get_ks_fs(vg_obj, fs_obj):
        """
        List the matching default LV for fs_obj within the VG vg_obj. If it
        does not exist None will be returned instead
        :param vg_obj : the chosen volume group
        :type vg_obj: LitpObject
        :param fs_obj : the chosen file system
        :type fs_obj: LitpObject
        :return: list of KS volume or None
        :rtype: list
        """
        if vg_obj.properties.get('volume_group_name') == LMS_ROOT_VG_NAME:
            for ms_fs in LVMSnapshots._get_ms_rootvg_fss():
                if fs_obj.properties.get('mount_point') == ms_fs[1]:
                    return ms_fs

    @staticmethod
    def _get_ms_lv_name(vg_obj, fs_obj):
        """
        Return the LV name
        :param vg_obj : the chosen volume group
        :type vg_obj: LitpObject
        :param fs_obj : the chosen file system
        :type fs_obj: LitpObject
        :return: LV name
        :rtype: string
        """
        if LVMSnapshots._get_ks_fs(vg_obj, fs_obj):
            return LVMSnapshots._get_ks_fs(vg_obj, fs_obj)[0]
        # the FS is not mounted and it does not appear in df output, so
        # instead use the naming convention to retrieve its LV name
        return "_".join((vg_obj.item_id, fs_obj.item_id))

    @staticmethod
    def _get_ms_lv_path(vg_obj, fs_obj):
        """
        Return the LV path
        :param vg_obj : the chosen volume group
        :type vg_obj: LitpObject
        :param fs_obj : the chosen file system
        :type fs_obj: LitpObject
        :return: LV path
        :rtype: string
        """
        return '/dev/{0}/{1}'.format(
                vg_obj.properties.get('volume_group_name'),
                LVMSnapshots._get_ms_lv_name(vg_obj, fs_obj))

    def _get_vg_snappable_filesystems(self, volume_group, snap_prefix):
        """
        Get snapshot info for filesystem in a volume group that have
        snap_size > 0

        :param volume_group: Volume Group to check
        :type volume_group: LitpObject
        :param snap_prefix: Snapshot name prefix to use
        :type snap_prefix: str
        :returns: List of filesystems that should be snapped
        :rtype list[dict]
        """
        _snap_info = []
        for _fs in self._litp.get_children('{0}/file_systems'.format(
                volume_group.path)):
            file_system = LitpObject(None, _fs['data'],
                                     self._litp.path_parser)
            _snapsize = file_system.get_int_property('snap_size')
            if _snapsize > 0:
                lv_name = '{0}_{1}'.format(volume_group.item_id,
                                           file_system.item_id)

                _snap_info.append({
                    'fs_snap_size': _snapsize,
                    'lv_path': '/dev/{0}/{1}'.format(
                            volume_group.get_property(
                                    'volume_group_name'),
                            lv_name),
                    'lv_name': lv_name,
                    'snap_name': '{0}_{1}'.format(
                            snap_prefix, lv_name)
                })
        return _snap_info

    def _get_node_snappable_localvols(self, snap_prefix):
        """
        Get a mapping of nodes that are using local disks for LVM filesystems
        and the filesystems that should be snapped using lvcreate i.e. snap
        local filesystems on a Rack mounted server.

        :param snap_prefix: Snapshot name prefix to use for each snapshot
         volume
        :type snap_prefix: str
        :returns: Map with keys being hostnames and values being a list of
        volumes to snap onm that node. If no nodes are using disk backed
        filesystems then an empty dict is returned.
        :rtype: dict
        """
        lvm = LVMManager()
        local_disk_nodes = lvm.get_nodes_using_local_storage(
            is_migration=self.is_migration())
        # local_disk_nodes: mapping of node name to list of local device names
        # e.g. node-1: sda,sdb.....

        node_local_vols = {}
        for _node, _ldevices in local_disk_nodes.items():
            snap_vols = []
            for _volgrp in self._litp.get_children(
                    '{0}/storage_profile/volume_groups'.format(_node.path)):
                volgrp = LitpObject(None, _volgrp['data'],
                                    self._litp.path_parser)
                for _pdev in self._litp.get_children(
                        '{0}/physical_devices'.format(volgrp.path)):
                    phy_dev = LitpObject(None, _pdev['data'],
                                         self._litp.path_parser)
                    if phy_dev.get_property('device_name') in _ldevices:
                        snap_vols.extend(
                                self._get_vg_snappable_filesystems(
                                        volgrp, snap_prefix))
            node_local_vols[_node.get_property('hostname')] = snap_vols
        return node_local_vols

    @staticmethod
    def _get_grub_files(check_grub_file=True):
        """
        Determine the GRUB files existent on the LMS
        :param check_grub_file: boolean to check GRUB file or Save file
        :type check_grub_file: boolean
        :return: 2-tuple of GRUB file and save file
        :rtype: tuple: str, str
        """

        gfile = None
        sfile = None

        # if /boot/grub/grub.conf doesn't exist, assume it's RHEL 7
        # and set grub paths to /boot/grub2/
        if check_grub_file:
            if os.path.isfile(GRUB_RHEL7_UEFI):
                gfile = GRUB_RHEL7_UEFI
                sfile = GRUB_RHEL7_UEFI_SAVE
            elif os.path.isfile(GRUB_RHEL6):
                gfile = GRUB_RHEL6
                sfile = GRUB_RHEL6_SAVE
            elif os.path.isfile(GRUB_RHEL7):
                gfile = GRUB_RHEL7
                sfile = GRUB_RHEL7_SAVE
        else:
            if os.path.isfile(GRUB_RHEL7_UEFI_SAVE):
                gfile = GRUB_RHEL7_UEFI
                sfile = GRUB_RHEL7_UEFI_SAVE
            elif os.path.isfile(GRUB_RHEL6_SAVE):
                gfile = GRUB_RHEL6
                sfile = GRUB_RHEL6_SAVE
            elif os.path.isfile(GRUB_RHEL7_SAVE):
                gfile = GRUB_RHEL7
                sfile = GRUB_RHEL7_SAVE
        return (gfile, sfile)

    def snap_lms_volumes(self, lvm_snapsize=None):
        """
        Create LV snapshots of the LMS volumes

        :param lvm_snapsize: Percentage size of LVM snapshot
        :type lvm_snapsize: int

        :returns: List of volume names that were snapped
        :rtype: str[]
        """
        self.logger.info('{0}: Reading available LMS Logical Volumes'.
                         format(self.log_prefix))
        volumes = self._get_lms_snappable_vols()
        vol_names = [vol['lv_name'] for vol in volumes]
        self.logger.info('{0}: Creating LMS snapshots for volumes {1} with '
                         'tag {2}'.format(self.log_prefix,
                                          ', '.join(vol_names),
                                          self.tag))
        outputs = self.lvm.create_snapshots(volumes, tag=self.tag,
                                            prefix=self.snap_prefix,
                                            suffix=None,
                                            pc=lvm_snapsize)
        for std_out in outputs:
            self.logger.info('{0}: {1}'.format(self.log_prefix, std_out))

        (grub_file, grub_save_file) = LVMSnapshots._get_grub_files()

        self.copy_file(grub_file, grub_save_file)
        self.logger.info('{0}: Saved grub file {1} to {2}'.
                         format(self.log_prefix, grub_file,
                                grub_save_file))
        return vol_names

    def snap_nodelocal_volumes(self):
        """
        Create LV snapshots of volumes on nodes that are using physical disks
        as storage

        :returns: Mapping of nodes-to-volume name that LV snap were created on
        :rtype: dict
        """
        self.logger.info(
                '{0}: Reading available node local Logical Volumes.'.format(
                        self.log_prefix))
        node_local_vols = self._get_node_snappable_localvols(self.snap_prefix)

        restore_lv_names = {}
        if node_local_vols:
            self.logger.info('{0}: {1} node(s) with local Logical '
                             'Volumes to snap.'.format(self.log_prefix,
                                                       len(node_local_vols)))
            enminst_agent = EnminstAgent()
            filemgr_agent = FilemanagerAgent()
            snap_hosts = list(node_local_vols.keys())

            for _node, _fsystems in node_local_vols.items():
                restore_lv_names[_node] = [
                    vol['lv_name'] for vol in _fsystems]

            node_local_vols['snap_tag'] = self.tag
            remote_output = enminst_agent.create_lv_snapshots(node_local_vols,
                                                              snap_hosts)

            for _node, _rdata in remote_output.items():
                for _line in _rdata.split('\n'):
                    self.logger.info('{0}: {1} {2}'.format(
                            self.log_prefix, _node, _line))

            self.logger.info('{0}: Backing up grub conf on {1} nodes'.format(
                    self.log_prefix, len(snap_hosts)))

            remote_output = LVMSnapshots._copy_grub_file(filemgr_agent,
                                                 snap_hosts,
                                                 action='create')

            for _node, _copyres in remote_output.items():
                self.logger.info('{0}: {1} {2}'.format(
                        self.log_prefix, _node, _copyres))
        else:
            self.logger.info(
                    '{0}: No node local Logical Volumes to snap.'.format(
                            self.log_prefix))
        return restore_lv_names

    @staticmethod
    def _copy_grub_file(filemgr, hosts, action):
        """
        Copy GRUB file to the Save file
        :param hosts: List of remote hosts on which to perform the copy
        :type hosts: list of strings
        :param action: Snapshot action on behalf of which
                       the copy will be performed
        :type action: string
        :return: Copy results/output
        :rtype: dict
        """
        if 'create' == action:
            sources = [GRUB_RHEL7_UEFI, GRUB_RHEL6, GRUB_RHEL7]
            targets = [GRUB_RHEL7_UEFI_SAVE, GRUB_RHEL6_SAVE, GRUB_RHEL7_SAVE]
        elif 'restore' == action:
            sources = [GRUB_RHEL7_UEFI_SAVE, GRUB_RHEL6_SAVE, GRUB_RHEL7_SAVE]
            targets = [GRUB_RHEL7_UEFI, GRUB_RHEL6, GRUB_RHEL7]

        output = {}

        try:
            output = filemgr.copy_file(sources[0], targets[0], hosts)
        except McoAgentException:
            output = filemgr.copy_file(sources[2], targets[2], hosts)
        except McoAgentException:
            output = filemgr.copy_file(sources[1], targets[1], hosts)
        return output

    def create_snapshots(self, lvm_snapsize=None):
        """
        Create the snapshot
        :param lvm_snapsize: Percentage size of LVM snapshot
        :return:
        """
        lms_vol_names = self.snap_lms_volumes(lvm_snapsize)
        node_vol_names = self.snap_nodelocal_volumes()
        return lms_vol_names, node_vol_names

    def validate_lv_snapshot(self, lv_snaps, node_name, detailed):
        """
        Validate an LV snapshot
        :param lv_snaps: List of snaps to validate
        :type lv_snaps: LogicalVolume[]
        :param node_name: The node the LV data is from
        :type node_name: str
        :param detailed: Show detailed info on the snaps
        :type detailed: bool
        :returns: True if an LV snaps are invalid, False otherwise.
        :rtype: bool
        """
        for lv_snap in lv_snaps:
            validity = lv_snap.lv_snapshot_invalid or 'snapshot valid'
            _log_function = self.logger.info
            if validity != 'snapshot valid':
                _log_function = self.logger.error
            _log_function('{0}: {1} : Snapshot {2} : {3}'.
                          format(self.log_prefix, node_name,
                                 lv_snap.lv_name, validity))
            if detailed:
                _log_function('{prefix}:   {snap} {vg}/{origin} {lv_attr} '
                              'Usage:{sp}%'.format(prefix=self.log_prefix,
                                                   vg=lv_snap.vg_name,
                                                   origin=lv_snap.origin,
                                                   lv_attr=lv_snap.lv_attr,
                                                   sp=lv_snap.snap_percent,
                                                   snap=lv_snap.lv_name))
        return any(self.lvm.get_attr(lv_snaps, 'lv_snapshot_invalid'))

    def validate_lms_snapshots(self, lms_vol_names=None, detailed=False):
        """
        Validate LV snapshots on the LMS
        :param lms_vol_names: Volumes to validate
        :type lms_vol_names: str
        :param detailed: Show more info in the snapshots
        :type detailed: bool
        :returns: True if there are invalid snapshots, False otherwise
        :rtype: bool
        """
        snaps = self.lvm.list_snapshots()
        self.logger.info('{0}: Validating LMS snapshots'.format(
                self.log_prefix))
        if not snaps:
            raise LVMManagerException('No LMS snapshots found on the system.')
        validation_errors = self.validate_lv_snapshot(snaps, 'LMS', detailed)
        if not lms_vol_names:
            all_volumes = self.lvm.list_volumes()
            volumes = [vol for vol in all_volumes
                       if vol.lv_attr[0] in ['-', 'o']]
            lms_vol_names = self.lvm.get_attr(volumes, 'lv_name')
        for vol_name in lms_vol_names:
            if vol_name not in self.lvm.get_attr(snaps, 'origin'):
                validation_errors = True
                self.logger.error('{0}: LMS : Snapshot for volume {1} not '
                                  'found'.format(self.log_prefix, vol_name))
        # if /boot/grub/grub.conf doesn't exist, assume it's RHEL 7
        # and set grub paths to /boot/grub2/
        (grub_file, grub_save_file) = LVMSnapshots._get_grub_files()
        if grub_file and grub_save_file:
            self.grub = grub_file
            self.grub_save = grub_save_file
            self.logger.info('{0}: Grub file {1} exists to restore on LMS'
                             .format(self.log_prefix, grub_save_file))
        else:
            validation_errors = True
            self.logger.error('{0} Grub files do not exist on LMS '
                              'to restore'.format(self.log_prefix))
        return validation_errors

    def validate_local_snapshots(self, node_name,  # pylint: disable=R0913
                                 required_volumes,
                                 host_grub_data, host_lv_data, detailed):
        """
        Validate LV snaps for a node.
        :param node_name: The nodes hostname
        :param required_volumes: List of volumes that should have snaps
        :param host_grub_data: GRUB backup data from nodes
        :param host_lv_data: LV data from nodes
        :param detailed: Show more info in the snapshots
        :type detailed: bool
        :returns: True if there are invalid snaps on the node, False otherwise
        :rtype: bool
        """
        validation_errors = False
        if node_name in host_grub_data:
            if bool(host_grub_data[node_name]):
                self.logger.info(
                    '{0}: {1} : Grub file exists.'.format(
                        self.log_prefix, node_name))
            else:
                self.logger.error(
                    '{0} : {1} : Grub file does not '
                    'exist.'.format(self.log_prefix, node_name))
                validation_errors = True
        else:
            self.logger.error('{0} : {1} : Got no grub data from node!'
                              .format(self.log_prefix, node_name))
            validation_errors = True
        if node_name in host_lv_data:
            node_snaps = {}
            lvm = LVMManager()
            for _vol in lvm.process_lvm_output(host_lv_data[node_name]):
                if _vol.lv_attr.startswith('s'):
                    node_snaps[_vol.origin] = _vol
            validation_errors |= self.validate_lv_snapshot(
                    node_snaps.values(), node_name, detailed)
            for required in required_volumes:
                if required not in node_snaps:
                    validation_errors = True
                    self.logger.error(
                            '{0} : {1} : Snapshot for volume {2} '
                            'not found!'.format(self.log_prefix,
                                                node_name,
                                                required))
        else:
            self.logger.error('{0} : {1} : Got no LV data from node!'
                              .format(self.log_prefix, node_name))
            validation_errors = True
        return validation_errors

    # pylint: disable=too-many-branches
    # pylint: disable=too-many-locals
    def validate_nodelocal_snapshots(self, backedup_volumes, detailed):
        """
        Validate LV snapshots on nodes using local storage
        :param backedup_volumes: Volumes to validate
        :type backedup_volumes: dict
        :param detailed: Show more info in the snapshots
        :type detailed: bool
        :returns: True if there are invalid snapshots, False otherwise
        :rtype: bool
        """
        node_local_vols = self._get_node_snappable_localvols(self.snap_prefix)
        validation_errors = False
        if node_local_vols and backedup_volumes:
            lost_nodes = []
            host_lv_data = {}
            for node_name in node_local_vols.keys():
                if node_name not in backedup_volumes.keys():
                    self.logger.debug('{0}: Expanded node {1} not part '
                                      'of snapshot'.format(self.log_prefix,
                                                           node_name))
                    del node_local_vols[node_name]
                else:
                    try:
                        lv_data = EnminstAgent().lvs_list(
                        [node_name],
                        LVMManager.DEFAULT_LV_OPTS)
                        host_lv_data.update(lv_data)
                    except McoAgentException as error:
                        if "No answer" in str(error.message) and\
                            self.is_migration():
                            self.logger.info('{0}: {1} is unreachable, being'
                            ' categorized as a lost node'.
                            format(self.log_prefix, node_name))
                            lost_nodes.append(node_name)
                            del node_local_vols[node_name]
                            del backedup_volumes[node_name]

            host_grub6_data = {}
            host_grub7_data = {}
            if node_local_vols:
                host_grub6_data, host_grub7_data = \
                    LVMSnapshots._get_grub_save_file(node_local_vols)

                if self.is_migration():
                    for _node in node_local_vols.keys():
                        if (_node in host_grub6_data.keys() and
                            not bool(host_grub6_data[_node])) and \
                            (_node in host_grub7_data.keys() and
                            not bool(host_grub7_data[_node])):
                            self.logger.info('{0}: {1} is being categorized as'
                            ' a lost node.'.format(self.log_prefix, _node))

                            lost_nodes.append(_node)
            if lost_nodes:
                self.create_rhel7_node_list_file(lost_nodes)

            for _node, fslist in backedup_volumes.items():
                # Ignore racks that didn't return True
                # in host_grub_data by doing the following
                if self.is_migration():
                    if (_node in host_grub6_data.keys() and
                            not bool(host_grub6_data[_node])) and \
                            (_node in host_grub7_data.keys() and
                                 not bool(host_grub7_data[_node])):
                        self.logger.warning('{0}: Snapshots for {1} '
                                            'lost as part of RHEL 7 '
                                            'migration'.format(self.log_prefix,
                                                               _node))
                        continue

                grub_data = host_grub6_data
                if (_node in host_grub6_data.keys() and
                        not bool(host_grub6_data[_node])):
                    grub_data = host_grub7_data

                validation_errors |= self.validate_local_snapshots(
                    _node, fslist, grub_data, host_lv_data, detailed)
        elif node_local_vols and not backedup_volumes:
            self.logger.debug('{0}: Expanded nodes {1} not part of '
                              'snapshot'.format(self.log_prefix,
                                               node_local_vols.keys()))

        else:
            self.logger.info('{0}: No nodes using local storage.'.format(
                    self.log_prefix))

        return validation_errors

    @staticmethod
    def _get_grub_save_file(node_local_vols):
        """
        Get the saved GRUB file, first trying RHEl6, then based on
        whether it is an rENM deployement RHEL7 UEFI or RHEL7 grub2
        @param node_local_vols: Node local Logical Volumes
        @return: tuple containing two dictionaries indicating
        existence of RHEL6 and RHEL7 saved grub files
        """
        host_grub6_data = {}
        host_grub7_data = {}
        fm_agent = FilemanagerAgent()
        try:
            host_grub6_data = fm_agent.exists(GRUB_RHEL6_SAVE,
                                              node_local_vols.keys())
        except McoAgentException:
            host_grub6_data = {}
        try:
            if is_env_on_rack():
                host_grub7_data = fm_agent.exists(GRUB_RHEL7_UEFI_SAVE,
                                                  node_local_vols.keys())
            else:
                host_grub7_data = fm_agent.exists(GRUB_RHEL7_SAVE,
                                                  node_local_vols.keys())
        except McoAgentException:
            host_grub7_data = {}
        return host_grub6_data, host_grub7_data

    def validate(self, lms_vol_names=None, node_vol_names=None,
                 detailed=False):
        """
        Validate LV snapshots on the LMS and any nodes using local storage
        :param lms_vol_names: List of LMS volumes that should have snapshots.
        :param node_vol_names: List of node volumes that should have snapshots.
        :param detailed: Shot detailed snapshot info.
        """
        lms_errors = self.validate_lms_snapshots(lms_vol_names, detailed)
        node_errors = self.validate_nodelocal_snapshots(node_vol_names,
                                                        detailed)
        if lms_errors or node_errors:
            raise LVMManagerException('Invalid LV snapshots found!')

    def restore_lms_snapshots(self):
        """
        Restore the snapshots on the LMS
        :param
        :return: None
        """
        (grub_file, grub_save) = LVMSnapshots._get_grub_files(
            check_grub_file=False)

        if grub_file and grub_save:
            self.logger.info('{0}: Restoring GRUB file {1} on LMS'
                             .format(self.log_prefix, grub_save))
            self.copy_file(grub_save, grub_file)

        self.logger.info('{0}: Restoring snapshots with tag @{1}'.format
                         (self.log_prefix, self.tag))

        res = self.lvm.restore_snapshots(tag=self.tag)
        if not res:
            self.logger.info('{0}: No snapshots found for restore.'.
                             format(self.log_prefix))
        else:
            for _line in res:
                self.logger.info('{0}: LMS : {1}'.format(self.log_prefix,
                                                         _line))

    def restore_nodelocal_snapshots(self, restore_volume_hosts):
        """
        Restore LV snapshots on nodes using local storage.
        Also restores the grub file created during the create_snapshot
        :param restore_volume_hosts: List of nodes using local storage
        :type restore_volume_hosts: list
        """
        self.logger.info('Restoring grub on {0} nodes.'.format(
                len(restore_volume_hosts)
        ))
        if len(restore_volume_hosts) == 0:
            return
        filemgr_agent = FilemanagerAgent()
        remote_output = LVMSnapshots._copy_grub_file(filemgr_agent,
                                             restore_volume_hosts,
                                             action='restore')
        for _node, _copyres in remote_output.items():
            self.logger.info('{0}: {1} {2}'.format(
                    self.log_prefix, _node, _copyres))

        snap_agent = EnminstAgent()
        self.logger.info('Restoring LV snapshots on {0} nodes.'.format(
                len(restore_volume_hosts)
        ))
        remote_output = snap_agent.restore_lv_snapshots(self.tag,
                                                        restore_volume_hosts)
        for _node, _stdout in remote_output.items():
            _lines = filter(None, _stdout.split('\n'))
            if _lines:
                for _line in _lines:
                    self.logger.info('{0}: {1} : {2}'.format(
                            self.log_prefix, _node, _line.strip()))

        # TORF-317966: run /bin/sync command at the end to make sure
        # grub.conf copy registered on disk
        remote_output = snap_agent.execute_sync_command(restore_volume_hosts)
        for _node, _stdout in remote_output.items():
            _lines = filter(None, _stdout.split('\n'))
            if _lines:
                for _line in _lines:
                    self.logger.info('{0}: {1} : {2}'.format(
                            self.log_prefix, _node, _line.strip()))

    def remove_lms_snaphots(self):
        """
        Delete LV snapshots on the LMS and remove grub.conf backup.
        """
        self.logger.info('{0}: Deleting LMS snapshots with tag @{1}'.
                         format(self.log_prefix, self.tag))
        res = self.lvm.remove_snapshots(tag=self.tag)
        if not res:
            self.logger.info('{0}: LMS : No LV snapshots found to delete.'.
                             format(self.log_prefix))
        else:
            for _line in res:
                self.logger.info('{0}: LMS : {1}'.format(self.log_prefix,
                                                         _line.strip()))
        (_, grub_save_file) = LVMSnapshots._get_grub_files(
            check_grub_file=False)

        if grub_save_file:
            self.logger.info('{0}: Removing the LMS backup grub file {1}'.
                             format(self.log_prefix, grub_save_file))
            try:
                os.remove(grub_save_file)
            except IOError:
                raise SystemExit('Unable to remove LMS grub backup file {0}'.
                                 format(grub_save_file))

    def remove_nodelocal_snapshots(self):
        """
        Delete LV snapshots on any nodes using local storage and remove
        grub.conf backup.
        """
        self.logger.info(
                '{0}: Reading available node local Logical Volumes.'.format(
                        self.log_prefix))
        node_local_vols = self._get_node_snappable_localvols(self.snap_prefix)

        if self.is_migration() and os.path.isfile(RHEL7_NODE_LIST_FILE):
            rhel7_node_list = []
            with open(RHEL7_NODE_LIST_FILE, 'r') as _reader:
                rhel7_node_list = load(_reader)

            for node in rhel7_node_list:
                if node in node_local_vols.keys():
                    self.logger.debug("Removing Lost Node {0} "
                                      "from node_local_vols".format(node))
                    del node_local_vols[node]

        if node_local_vols:
            enminst_agent = EnminstAgent()
            fmgr_agent = FilemanagerAgent()
            _results = enminst_agent.delete_lv_snapshots(
                    self.tag, node_local_vols.keys())
            for _node, _stdout in _results.items():
                _lines = filter(None, _stdout.split('\n'))
                if _lines:
                    for _line in _lines:
                        self.logger.info('{0}: {1} : {2}'.format(
                                self.log_prefix, _node, _line.strip()))
                else:
                    self.logger.info('{0}: {1} : No LV snapshots found to '
                                     'delete.'.format(self.log_prefix, _node))

            _results = {}
            try:
                _results = fmgr_agent.delete(GRUB_RHEL7_UEFI_SAVE,
                                            node_local_vols.keys())
            except McoAgentException:
                try:
                    _results = fmgr_agent.delete(GRUB_RHEL6_SAVE,
                                                 node_local_vols.keys())
                except McoAgentException:
                    _results = fmgr_agent.delete(GRUB_RHEL7_SAVE,
                                             node_local_vols.keys())

            for _node, _stdout in _results.items():
                if _stdout:
                    self.logger.info('{0}: {1} : {2}'.format(
                            self.log_prefix, _node, _stdout.strip()))
        else:
            self.logger.info('{0}: No nodes using local storage.')

    def remove_snapshots(self):
        """
       Remove all LVM snapshots on the LMS and any nodes using local storage
       """
        self.remove_lms_snaphots()
        self.remove_nodelocal_snapshots()

    def copy_file(self, source, dest):
        """
        Copy the file (grub.conf does not exist in any of the LVM volume
        so need to copy that during the snapshot and restore back during
        restore )
        :param source: Source file
        :type source: String
        :param dest: Destination file
        :type dest: String
        :return:
        """
        self.logger.info('{0}: Copying {1} to {2}'.format(self.log_prefix,
                                                          source, dest))
        try:
            shutil.copy2(source, dest)
        except IOError:
            raise SystemExit('{0}: Unable to copy {1} in to {2}'.format
                             (self.log_prefix, source, dest))

    def reboot(self):
        """
       Reboot LMS after snapshot restore
       :param
       :return:
       """
        self.logger.info('{0}: Rebooting LMS ...'.format(self.log_prefix))
        command = 'shutdown -r 1 "System is going down for reboot in 1 minute"'
        exec_process(command.split())

    @staticmethod
    def is_migration():
        """
        Check to see if migration lock file is in place
        :return: True/False
        """
        return True if os.path.isfile(MIGRATION_LOCK_FILE) else False

    @staticmethod
    def create_rhel7_node_list_file(lost_nodes):
        """
        Creates a file with list of nodes that attempted migration to RHEL7
        :param lost_nodes: List of hostnames of nodes that attempted migration
        :return:
        """
        if os.path.isfile(RHEL7_NODE_LIST_FILE):
            os.remove(RHEL7_NODE_LIST_FILE)
        with open(RHEL7_NODE_LIST_FILE, 'w+') as _writer:
            dump(lost_nodes, _writer)
