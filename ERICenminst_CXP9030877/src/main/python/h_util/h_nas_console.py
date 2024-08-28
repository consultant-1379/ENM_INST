"""
Classes for SFS modifications
"""
##############################################################################
# COPYRIGHT Ericsson AB 2022
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import logging
from time import sleep
from h_utils import read_enminst_config
# pylint: disable=import-error,no-name-in-module,unused-import
from naslib.connection import NasConnection
from naslib.log import NasLogger
from naslib.nasexceptions import (NasException,
                                  NasConnectionException,
                                  UnableToDiscoverDriver)
from naslib.objects import FileSystem, Share, Cache, Snapshot, NasServer
from naslib.drivers.sfs.utils import VxCommands, VxCommandsException
# pylint: enable=import-error,no-name-in-module,unused-import

WARNING_MESSAGE = 'An error occurred removing snapshots'
EXCEPTION_MESSAGE = 'Remove snapshot failed with error below run ' \
                    'remove_snapshot again before any subsequent ' \
                    'attempt to create_snapshot.'


def normalize_size(size):
    """
    Convert file system size to Mega from Mega/Gig/Terra

    :param size: size in Mega, Gig or Terra
    :type  size: str
    :returns: Size in Mega
    :rtype: float
    """
    factor = {'m': 1, 'g': 1024, 't': 1048576}
    return float(size[:-1]) * factor[size[-1:].lower()]


def get_rollback_cache_name(storage_pool):
    """
    Get the rollback cache name for a storage pool

    :param storage_pool: SFS storage pool name
    :type  storage_pool: str
    :returns: The rollback cache name
    :rtype: str
    """
    return '{0}-cache'.format(storage_pool)


def get_litp_rollback_cache_name(storage_pool):
    """
    Get the rollback cache name for a storage pool that a LITP snapshot
    plan would create.

    :param storage_pool: SFS storage pool name
    :type  storage_pool: str
    :returns: The rollback cache name
    :rtype: str
    """
    return '{0}_cache'.format(storage_pool)


def get_rollback_name(prefix, fs_name):
    """
    Get the rollback  name

    :param prefix: Snapshot prefix name
    :type  prefix: str
    :param fs_name: file system name
    :type  prefix: str
    :returns: rollback  name
    :rtype: str
    """
    return '{0}-{1}'.format(prefix, fs_name)


def get_pool_prefix(pool_name):
    """
    Get the storage pool prefix ENM/OSS format

    :param pool_name: SFS storage pool name
    :type  pool_name: str
    :returns: The ENM/OSS filesystem prefix
    :rtype: str
    """
    return '{0}-'.format(pool_name)


def is_fs_in_pool(filesystem, storage_pool):
    """
    Test if a filesystem is in a storage pool

    :param filesystem: The filesystem
    :type  filesystem: str
    :param storage_pool: SFS storage pool name
    :type  storage_pool: str
    :returns: True if in the storage pool; False otherwise
    :rtype: bool
    """
    return filesystem.startswith(get_pool_prefix(storage_pool))


class NasConsoleException(Exception):
    """
    Simple nasconsole exception
    """
    pass


def map_tabbed_data(data, id_key, fkl=0):  # pylint: disable=R0914
    """
    Convert nasconsole command output in to a set of dictionaries.
    The first line is used to get the length/width of each column

    e.g. with id_key==NAME

    NAME        TYPE     SNAPDATE         CHANGED_DATA SYNCED_DATA
    L_enm-amos_ spaceopt 2016/02/01 08:30 192K(0.0%)   192K(0.0%)
    L_enm-smrs_ spaceopt 2016/02/01 08:58 222K(0.0%)   333K(0.0%)

    to

    { 'L_enm-amos_': {
        'NAME': 'L_enm-amos_',
        'TYPE': 'spaceopt',
        'SNAPDATE': '2016/02/01 08:30',
        'CHANGED_DATA': '192K(0.0%)',
        'SYNCED_DATA': '192K(0.0%)'}
      ,
      'L_enm-smrs_': {
        'NAME': 'L_enm-smrs_',
        'TYPE': 'spaceopt',
        'SNAPDATE': '2016/02/01 08:58',
        'CHANGED_DATA': '222K(0.0%)',
        'SYNCED_DATA': '333K(0.0%)'}
    }

    :param data: The output of a nasconsole command
    :param id_key:
    :param fkl: The length of the 'id_key' value if known
    :type fkl: int
    :returns: Set of dictionaries, each dictionary storing a lines data
    :rtype: dict
    """
    header_line = data[0]
    headers = filter(None, header_line.split(' '))
    header_indexes = {}
    for idx in range(len(headers)):
        start_index = header_line.index(headers[idx])
        if idx >= len(headers) - 1:
            end_index = -1
        else:
            end_index = header_line.index(headers[idx + 1])
        header_indexes[headers[idx]] = (start_index, end_index)

    # Yeah, some snap names are longer than expected which breaks the way this
    # worked so the flk is the length of the snap name which is used to pad
    # the indexes out...
    #
    # NAME                     TYPE           SNAPDATE
    # Snapshot-ENM425-data     spaceopt       2017/01/30 12:2
    #
    # versus
    #
    # NAME                     TYPE           SNAPDATE
    # Snapshot-ENM425-upgrade_indspaceopt       2017/01/30 12:27
    #                         ^^^^^^^^^^^
    if fkl > 0 and fkl > header_indexes[id_key][1]:
        _pad = fkl - header_indexes[id_key][1]
        for idx in range(len(headers)):
            _orig = header_indexes[headers[idx]]
            _padded = [_orig[0] + _pad, _orig[1] + _pad]
            if idx == 0:
                _padded = [_orig[0], _orig[1] + _pad]
            if _orig[1] == -1:
                _padded[1] = -1
            header_indexes[headers[idx]] = _padded
    # end of "workaround"........

    mapped_data = {}
    for line in data[1:]:
        line = line.strip()
        line_data = {}
        for header, h_range in header_indexes.items():
            start_index = h_range[0]
            end_index = h_range[1]
            if end_index == -1:
                end_index = len(line)
            value = line[start_index: end_index]
            line_data[header] = value.strip()
        mapped_data[line_data[id_key]] = line_data
    return mapped_data


class NasConsole(object):  # pylint: disable=R0904
    """
    Class to access NAS commands

    """
    VX_PATH_PREFIX = '/vx/'

    def __init__(
            self,
            nasconsole,
            username,
            password,
            ssh_port=22,
            nas_type='veritas'
    ):  # pylint: disable=too-many-arguments
        """
        Connect to NAS

        :param nasconsole: NAS management address
        :type nasconsole: str
        :param username: The user to connect as
        :type username: str
        :param password: The password to use
        :type password: str
        :param ssh_port: The SSH port; defaults to 22
        :type ssh_port: int
        :param nas_type: The NAS type: 'veritas' or 'unityxt'
                                     : defaults to 'veritas'
        :type nas_type: str
        """
        self.logger = logging.getLogger('enminst')
        self.nas_connection = NasConnection(
            nasconsole,
            username,
            password,
            port=ssh_port,
            nas_type=nas_type
        )
        self.logger.debug('Connected to NAS; {0}@{1}'.format(username,
                                                             nasconsole))

    def exec_basic_nas_command(self, command, env='', as_master=False):
        # pylint: disable=unused-argument
        """
        Execute a command on the NAS (over ssh). Does not log error or raise
        exception if non-zero error code, but returns info in return tuple

        :param command: The command to execute
        :type command: str
        :return: tuple of return code, stdout, stderr, cmd_run
        :type: (int, str[], str[], str)
        """
        command = "export TERM=xterm;" + command
        if self.nas_connection.nas_type != "unityxt":
            with self.nas_connection as nas:
                vxcmd = VxCommands(nas)
                try:
                    stdout = vxcmd.execute_cmd(command)
                except Exception as err:  # pylint: disable=broad-except
                    err_str = map(str, err)
                    try:
                        return_code = int(err_str[0].split(' ')[1])
                    except:  # pylint: disable=bare-except
                        return_code = 1
                    return (return_code, err_str, err_str, command)
        else:
            with self.nas_connection as nas:
                stdout = u''
        stdout = stdout.rstrip('\n')
        stdout_list = map(unicode.strip, stdout.split(u'\n'))
        return (0, map(str, stdout_list), [], command)

    def exec_nas_command(self, command, env='', as_master=False):
        # pylint: disable=unused-argument
        """
        Execute a command on the SFS (over ssh)
        A NasConsoleException is raised of the exit code of the command is >=1

        :param command: The command to execute
        :type command: str
        :param env: Environment variables needed
        :type env: str
        :return: stdout from the command
        :type: str[]
        """
        command = "export TERM=xterm;" + command
        if self.nas_connection.nas_type != "unityxt":
            with self.nas_connection as nas:
                vxcmd = VxCommands(nas)
                stdout = vxcmd.execute(command)
        else:
            with self.nas_connection as nas:
                stdout = u''
        stdout = stdout.rstrip('\n')
        stdout_list = map(unicode.strip, stdout.split(u'\n'))
        return map(str, stdout_list)

    def nfs_share_show(self, storage_pool):
        """
        Get a list of exports for filesystems in a storage pool

        :param storage_pool: The storage pool name
        :type storage_pool: str
        :return: Collection of exports for filesystems
        :rtype: dict
        """
        share_exports = {}
        with self.nas_connection as nas:
            for share in nas.share.list():
                fs_name = share.name.split('/')[-1]
                if is_fs_in_pool(fs_name, storage_pool):
                    if fs_name not in share_exports:
                        share_exports[fs_name] = []
                    share_exports[fs_name].append({
                        'filesystem': fs_name,
                        'client': share.client,
                        'options': str(share.options)
                    })
                    if share.faulted:
                        raise NasConsoleException("NAS file system {0} has"
                                                  " faulted share which needs "
                                                  "to be fixed, manual "
                                                  "intervention required"
                                                  .format(fs_name))
        return share_exports

    def nfs_share_delete(self, filesystem, client):
        """
        Delete an export (unshare the filesystem)

        :param filesystem: The filesystem VX path
        :type filesystem: str
        :param client: The client to remove
        :type client: str
        """
        if self.nas_connection.nas_type != "unityxt":
            filesystem = NasConsole.VX_PATH_PREFIX + filesystem
        with self.nas_connection as nas:
            nas.share.delete(filesystem, client)

    def storage_fs_list(self, storage_pool):
        """
        List filesystem in a storage pool

        :param storage_pool: The storage pool name
        :type storage_pool: str
        :return: Collecion of filesystems in the storage pool
        :rtype: dict
        """
        filesystems = {}
        with self.nas_connection as nas:
            for filesystem in nas.filesystem.list():
                if is_fs_in_pool(filesystem.name, storage_pool):
                    if self.nas_connection.nas_type != "unityxt":
                        fs_size = str(getattr(filesystem, 'display_size'))
                    else:
                        fs_size = str(getattr(filesystem, 'size'))
                    fs_used = "0B"
                    if filesystem.online:
                        fs_status = "online"
                    else:
                        fs_status = "offline"
                    filesystems[filesystem.name] = {
                        'fs': filesystem.name,
                        'status': fs_status,
                        'size': fs_size,
                        'shared': fs_used
                    }
        return filesystems

    def fs_usage(self, storage_pool):
        """
        List used space on filesystem in a storage pool

        :param storage_pool: The storage pool name
        :type storage_pool: str
        :return: Collecion of filesystems in the storage pool
        with used space as X%
        :rtype: dict
        """
        usage = []
        with self.nas_connection as nas:
            for filesystem in nas.filesystem.usage():
                if is_fs_in_pool(filesystem['FileSystem'], storage_pool):
                    usage.append(filesystem)
            return usage

    def rollback_check(self, storage_pool):
        """
        For each filesystem in the pool, check to ensure no ongoing
        rollback is in progress.

        :param storage_pool: The storage pool name
        :type storage_pool: str
        :return: Collection of filesystems in the storage pool
        :rtype: boolean
        """
        try:
            with self.nas_connection as nas:
                for fsdetails in nas.filesystem.list():
                    if is_fs_in_pool(fsdetails.name, storage_pool):
                        if nas.filesystem.is_restore_running(fsdetails.name):
                            return True
                return False
        except NasConsoleException as nce:
            if 'ERROR V-493-10' in str(nce):
                self.logger.error("Connection to the FS is lost due to FS "
                                  "being down/unreachable with message: {0}"
                                  .format(nce))
            raise

    def storage_fs_list_details(self, fs_name):
        """
        List filesystem details
        :param filesystem: The filesystem name
        :returns: Detailed info on the NAS filesystem
        """
        fs_details = []
        with self.nas_connection as nas:
            if self.nas_connection.nas_type != "unityxt":
                # pylint: disable=protected-access
                fsdetails = nas.filesystem._properties(fs_name)
                # pylint: enable=protected-access
                for key, value in fsdetails.iteritems():
                    fs_details.append(key + ": " + value)
            else:
                for filesystem in nas.filesystem.list():
                    if filesystem.name == fs_name:
                        for key in filesystem.attributes:
                            value = str(getattr(filesystem, key))
                            fs_details.append(key + ": " + value)
        return fs_details

    def storage_fs_destroy(self, filesystem):
        """
        Destroy (delete) a filesystem

        :param filesystem: The filesystem to destroy
        :type filesystem: str
        """
        with self.nas_connection as nas:
            nas.filesystem.delete(filesystem)

    def storage_fs_create(self, name, size, pool, layout_or_nas_server):
        """
        Create a filesystem
        """
        with self.nas_connection as nas:
            nas.filesystem.create(name, size, pool, layout_or_nas_server)

    def ensure_fs_status(self, filesystem, storage_pool, status):
        """
        Ensure that a filesystem is online/offline

        :param filesystem: The filesystem to determine the status of
        :type filesystem: str
        :param storage_pool: The storage pool name
        :type storage_pool: str
        :param status: The status to check
        :type status: string
        """
        status_check = 'offline'
        if status == 'offline':
            if self.nas_connection.nas_type == "unityxt":
                self.logger.info('\'offline\' status is not applicable '\
                                 'to UnityXT - continuing')
                return
            status_check = 'online'
        config = read_enminst_config()
        property_fs_status_check = config['fs_status_check'].split(',')
        check_interval = int(property_fs_status_check[0])
        num_checks = int(property_fs_status_check[1])
        count = 0
        self.logger.info('Waiting for filesystem \'{0}\' to {1}...'
                         .format(filesystem, status))
        while (self.storage_fs_list(storage_pool)[filesystem]['status'] ==
               status_check and count != num_checks):
            count += 1
            sleep(check_interval)
        if count == num_checks:
            error = '\'{0}\' is not {1}. \'{0}\' was queried '\
                    '{2} times for {1} status.'\
                    .format(filesystem, status, num_checks)
            raise Exception(error)
        else:
            self.logger.info('\'{0}\' is {1}'.format(filesystem, status))

    def storage_fs_offline(self, filesystem):
        """
        Offline the filesystem

        :param filesystem: Changing the filesystem to an offline state
        :type filesystem: str
        """
        with self.nas_connection as nas:
            nas.filesystem.online(filesystem, False)

    def support_fs_destroy(self, filesystem):
        """
        Destroy (delete) a filesystem via support user

        :param filesystem: The filesystem to destroy
        :type filesystem: str
        """
        if self.nas_connection.nas_type != "unityxt":
            with self.nas_connection as nas:
                vxcmd = VxCommands(nas)
                vxcmd.execute('vxedit -g sfsdg -rf rm {0}'.format(filesystem))
        else:
            with self.nas_connection as nas:
                nas.filesystem.delete(filesystem)

    def storage_rollback_list(self, storage_pool, snap_prefix):
        """
        Get a list of rollbacks from a storage pool (if any exist)

        :param storage_pool: The storage pool name
        :type storage_pool: str
        :param snap_prefix: Snap name prefix, or * for all
        :type snap_prefix: str
        :return: Collecion of rollbacks (and the filesystem they're covering)
        :rtype: dict
        """
        rollbacks = {}
        with self.nas_connection as nas:
            for snap in nas.snapshot.list():
                snapname = snap.name
                filesystem = snap.filesystem
                if is_fs_in_pool(filesystem, storage_pool):
                    if filesystem not in rollbacks:
                        rollbacks[filesystem] = []
                    if '*' == snap_prefix or snapname.startswith(snap_prefix):
                        rollbacks[filesystem].append(snapname)
        return rollbacks

    def storage_rollback_info(self, rollback_name):
        """
        Get information on a rollback

        :param rollback_name: The rollback name
        :type rollback_name: str
        :returns: Some usage one the rollback
        :rtype: dict
        """
        with self.nas_connection as nas:
            stdout = nas.snapshot.rollbackinfo(rollback_name)
        return map_tabbed_data(stdout, 'NAME', len(rollback_name))

    def storage_rollback_destroy(self, rollback_name, filesystem):
        """
        Destroy (delete) a rollback

        :param rollback_name: The rollback name
        :type rollback_name: str
        :param filesystem: The filesystem name
        :type filesystem: str
        :param filesystem:
        """
        with self.nas_connection as nas:
            nas.snapshot.delete(rollback_name, filesystem)

    def storage_rollback_cache_list(self):
        """
        Get a list of rollback caches currently defined

        :return: str[]
        """
        cache_list = {}
        with self.nas_connection as nas:
            for cache in nas.cache.list():
                cache_size = int(normalize_size(str(getattr(cache, 'size'))))
                cache_used = int(normalize_size(str(getattr(cache, 'used'))))
                cache_used_perc = float(cache_used) / float(cache_size) * 100
                cache_list[cache.name] = {
                    'size_mb': unicode(cache_size),
                    'used_perc': unicode(round(cache_used_perc, 2))
                }
        return cache_list

    def storage_rollback_cache_destroy(self, cache_name):
        """
        Destroy a rollback cache

        :param cache_name: The cache name
        :type cache_name: str
        """
        if self.nas_connection.nas_type == "unityxt":
            return
        with self.nas_connection as nas:
            nas.cache.delete(cache_name)

    def storage_rollback_cache_create(self, cache_name, cache_size,
                                      storage_pool):
        """
        Create a rollback cache

        :param cache_name: The cache name
        :type cache_name: str
        :param cache_size: The cache size
        :type cache_size: str
        :param storage_pool: Pool name
        :type storage_pool: str
        """
        if self.nas_connection.nas_type == "unityxt":
            return
        with self.nas_connection as nas:
            nas.cache.create(cache_name, cache_size, storage_pool)

    def storage_rollback_create(self, rollback_name, filesystem, cache_name,
                                cache_type='space-optimized'):
        # pylint: disable=unused-argument
        """
        Create a rollback

        :param rollback_name: Snapshot name
        :type rollback_name: str
        :param filesystem: filesystem name
        :type filesystem: str
        :param cache_name: cache name
        :type cache_type: cache type
        """
        with self.nas_connection as nas:
            nas.snapshot.create(rollback_name, filesystem, cache_name)

    def storage_rollback_restore(self, filesystem, snapshot):
        """
        Restore rollback

        :param filesystem: filesystem name
        :type filesystem: str
        :param snapshot: Snapshot name
        :type snapshot: str
        """
        with self.nas_connection as nas:
            nas.snapshot.restore(snapshot, filesystem)

    def storage_fs_online(self, filesystem):
        """
        Online filesystem
        :param filesystem: filesystem name
        :type filesystem: str
        """
        with self.nas_connection as nas:
            nas.filesystem.online(filesystem, True)

    def nfs_share_add(self, filesystem, client, options):
        """
        Add nfs share to the file system

        :param filesystem: filesystem name
        :type filesystem: str
        :param client: client to which filesystem shared
        :type client: str
        :param options: share options
        :type filesystem: str
        """
        if self.nas_connection.nas_type != "unityxt":
            filesystem = NasConsole.VX_PATH_PREFIX + filesystem
        with self.nas_connection as nas:
            nas.share.create(filesystem, client, options)

    def ip_route_show(self):
        """
        Show routes currently defined on the NAS

        :returns: The output of the ``ip route show`` command.
        :rtype list
        """
        return self.exec_nas_command('/sbin/ip route show')

    def nas_server_list(self):
        """
        Get a list of UnityXT NAS servers (if any exist)

        :return: Collection of UnityXT NAS servers
        :rtype: dict
        """
        nasservers = {}
        with self.nas_connection as nas:
            for nasserver in nas.nasserver.list():
                nasservers[nasserver.name] = {
                    'ns': nasserver.name,
                    'pool': nasserver.pool.name,
                    'sp': nasserver.homesp
                    }
        return nasservers

    def nas_server_create(self, name, pool, ports,
                          network, protocols, ndmp_pass
        ):  # pylint: disable=too-many-arguments
        """
        Create a UnityXT NAS server

        :param name: The NAS server to create
        :type name: str
        :param pool: Storage pool
        :type pool: str
        :param ports: Comma separated str of port numbers
        :type ports: str
        :param network: Comma separated str which contains
            4 fields "sp,ip,netmask,gateway"
        :type network: str
        :param protocols: Comma separated str of NFS protocols
        :type protocols: str
        :param ndmp_pass: NDMP user's password
        :type ndmp_pass: str
        """
        with self.nas_connection as nas:
            nas.nasserver.create(
                name,
                pool,
                ports,
                network,
                protocols,
                ndmp_pass
            )

    def nas_server_destroy(self, name):
        """
        Destroy (delete) a UnityXT NAS server

        :param name: The NAS server to destroy
        :type name: str
        """
        with self.nas_connection as nas:
            nas.nasserver.delete(name)

    def nas_server_list_details(self, name):
        """
        Get details of a UnityXT NAS server

        :param name: The NAS server to detail
        :type name: str
        :return: Collection of NAS server details
        :rtype: dict
        """
        with self.nas_connection as nas:
            ns_details = nas.nasserver.get_nasserver_details(name)
        return ns_details
