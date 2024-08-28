"""
Class to handle SAN filesystem snapshots
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
#
# ********************************************************************
# Name    : sfs_snapshot.py
# Purpose : The purpose of this script is to run sfs snapshots
# operations
# ********************************************************************
from math import floor
import logging
from multiprocessing.pool import ThreadPool
from os.path import basename
from time import sleep
from h_litp.litp_utils import LitpObject, LitpException
from h_util.h_nas_console import NasConsole, get_rollback_cache_name, \
    get_rollback_name, normalize_size, NasConsoleException
from h_litp.litp_rest_client import LitpRestClient
from h_util.h_utils import get_nas_type

LITP_INVALID_LOCATION_ERROR = 'InvalidLocationError'
SK_SFS_POOL_NAME = 'nas_pool'
SK_NASCONSOLE_IP = 'nas_console'
SK_NASCONSOLE_USER = 'nasconsole_user'
SK_NASCONSOLE_PASSWD = 'nasconsole_psw'
SK_NASCONSOLE_SUPUSER = 'nas_supuser'
SK_NASCONSOLE_SUPPASSWD = 'nas_supsw'
SFS_SNAP_SIZE_KEY = 'snap_size'
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_ROLLBACKS = 3
EXIT_VALIDATE_ERROR = 4
SERV_BASE_NAMES = ['sdncontroller', 'solr', 'solrautoID']


class SfsSnapshotsException(Exception):
    """
    Simple sfs snapshot exception
    """
    pass


class SfsSnapshots(object):  # pylint: disable=R0902
    """
    Class to run SFS snapshot operations for a deployment
    """

    def __init__(self,  # pylint: disable=R0913
                 nas_cred, snap_prefix, ssh_port=22,
                 num_of_threads=10, log_silent=False):
        """
        Constructor
        :param nas_cred: nas credential
        :type nas_cred: dict
        :param ssh_port: The ssh port (defaults to 22)
        :type ssh_port: int
        :param num_of_threads: Number of threads that can be used for
        thread pool
        :type num_of_threads: int
        :param log_silent: disable logging to enminst log
        :type log_silent: boolean
        :return:
        """
        self.snap_prefix = snap_prefix
        self.cred = nas_cred

        if log_silent:
            self.logger = logging.getLogger('enmsnapshots')
        else:
            self.logger = logging.getLogger('enminst')

        self.poolname = self.cred[SK_SFS_POOL_NAME]
        self.ssh_port = ssh_port
        self.num_of_threads = num_of_threads
        self.log_prefix = 'NAS SNAP'
        self.litp = LitpRestClient()
        self.fs_snap_list = None
        self.nas_type_name = get_nas_type(self.litp)
        if self.nas_type_name == 'unityxt':
            self.litp_sfs_path = '/infrastructure/storage/storage_providers/' \
                                 'unityxt/pools'
        else:
            self.litp_sfs_path = '/infrastructure/storage/storage_providers/' \
                                 'sfs/pools'
        self.nasconsole = NasConsole(self.cred[SK_NASCONSOLE_IP],
                                     self.cred[SK_NASCONSOLE_SUPUSER],
                                     self.cred[SK_NASCONSOLE_SUPPASSWD],
                                     ssh_port=self.ssh_port,
                                     nas_type=self.nas_type_name)

    def remove_snapshots(self, file_system_list=None):
        """
        Destroy all rollbacks (snapshots) in a storage pool

        """
        self.logger.info('{0}: Looking for rollbacks to destroy.'.
                         format(self.log_prefix))
        rollbacks = self.nasconsole.storage_rollback_list(self.poolname,
                                                          self.snap_prefix)
        fs_to_snap = self.build_fs_to_snap(file_system_list=file_system_list)

        for filesystem, rollbacks in rollbacks.items():
            if filesystem in fs_to_snap.keys():
                for snap in rollbacks:
                    self.logger.info('{0}: Destroying rollback {1}'.
                                     format(self.log_prefix, snap))
                    self.nasconsole.storage_rollback_destroy(snap, filesystem)
        if rollbacks:
            self.logger.info('{0}: Rollbacks destroyed.'.
                             format(self.log_prefix))
        else:
            self.logger.info('{0}: No rollbacks to destroy, continuing.'.
                             format(self.log_prefix))
        if self.nas_type_name == 'veritas':
            self.remove_rollback_cache()

    def create_snapshots(self):
        """
        Create rollbacks of all filesystems in the storage pool

        """
        self.logger.info('{0}: Getting snapshot info ...'.
                         format(self.log_prefix))
        cache = None
        cache_size = None
        filesystems = self.build_fs_to_snap()
        # Filesystems to be snapped, but not present on SFS are logged
        modelled_filesystems = self.get_modelled_filesystems()
        for filesystem in modelled_filesystems:
            if filesystem not in filesystems:
                self.logger.info('File system {0} is not in the pool to snap'.
                                 format(filesystem))
        if len(filesystems) == 0:
            raise SfsSnapshotsException('{0}: No filesystems to snapshot!'.
                                        format(self.log_prefix))
        if self.nas_type_name == 'veritas':
            cache = get_rollback_cache_name(self.poolname)
            cache_size = self.calculate_cache_size(filesystems, cache,
                                               modelled_filesystems)
            self.logger.info('{0}: Creating rollback cache {1} of {2}'
                             .format(self.log_prefix, cache, cache_size))

            self.nasconsole.storage_rollback_cache_create(cache, cache_size,
                                                          self.poolname)
        for fs_name, _ in filesystems.items():
            rollback_name = get_rollback_name(self.snap_prefix, fs_name)
            self.logger.info('{0}: Creating rollback {1} for filesystem {2}'.
                             format(self.log_prefix, rollback_name, fs_name))
            self.nasconsole.storage_rollback_create(rollback_name,
                                                    fs_name, cache)
            self.logger.info('{0}: Created rollback {1}'.
                             format(self.log_prefix, rollback_name))
        self.logger.info('{0}: Snapshots created for all filesystems in the '
                         'storage pool {1}'.format(self.log_prefix,
                                                   self.poolname))
        self.logger.info('{0}: Rollback prefix is {1}'.
                         format(self.log_prefix, self.snap_prefix))
        return filesystems

    def calculate_cache_size(self, filesystems, cache, modelled_filesystems):
        """
        Calculate the size of the sfs cache.
        :param filesystems: the file systems to be snapped
        :type filesystems: dict
        :param cache: the name of the sfs cache
        :type cache: str
        :param modelled_filesystems: SFS file systems in the LITP model
        :type modelled_filesystems: dict
        :return: Size of the sfs cache in gigabytes
        :rtype: str
        """
        cache_size = None
        current_caches = self.nasconsole.storage_rollback_cache_list()
        if cache not in current_caches:
            total_cache = 0
            for _filesystem, data in filesystems.items():
                snap_size = int(modelled_filesystems[_filesystem]
                                [SFS_SNAP_SIZE_KEY])
                self.logger.info('{0} {1}'.format(_filesystem,
                                                  data['size']))
                total_cache += (normalize_size(data['size'])
                                / 100) * snap_size
            # convert from MB to GB
            cache_size = int(floor(total_cache / 1024))
            if cache_size == 0:
                cache_size = '256M'
            else:
                cache_size = '{0}G'.format(cache_size)
            self.logger.info('{0}: NAS rollback cache calculated to {1}'
                             .format(self.log_prefix, cache_size))
        else:
            self.logger.info('{0}: Rollback cache {1} exists.'.
                             format(self.log_prefix, cache))
        return cache_size

    def build_exported_fs(self):
        """
        Get a list of exported snappable filesystems.
        :return:
        """
        retry_count = 5
        retries = 0
        while retries < retry_count:
            try:
                fs_exports_all = self.nasconsole.nfs_share_show(self.poolname)
                break
            except Exception as error:  # pylint: disable=W0703
                retries += 1
                if retries >= retry_count:
                    self.logger.error("{0}: Retry limit reached ({1}) for "
                                "listing NFS shares"
                                .format(self.log_prefix, retry_count))
                    self.logger.error("{0}: Exception: {1}"
                                .format(self.log_prefix, str(error)))
                    raise SfsSnapshotsException('{0}: {1}'.
                                        format(self.log_prefix, str(error)))
                else:
                    self.logger.info("{0}: Waiting for shares to become"
                                     " available, going to retry command.."
                                     .format(self.log_prefix))
                    sleep(2)
        return self.build_fs_to_snap(filesystems=fs_exports_all)

    def build_fs_to_snap(self, file_system_list=None, filesystems=None):
        """
        Building a list of filesystems to be snapped.

        :param file_system_list: A backed up list of file systems
        :param filesystems: File systems to be snapped
        to use if it exists.
        :return:
        :rtype: dict
        :raises: SfsSnapshotsException
        """
        if not filesystems:
            filesystems = self.nasconsole.storage_fs_list(self.poolname)
        if len(filesystems) == 0:
            raise SfsSnapshotsException('No snap related filesystems found!')
        fs_to_snap = dict()
        if file_system_list:
            fs_to_snap = file_system_list
        else:
            for filesystem in self.get_modelled_filesystems():
                if filesystem in filesystems:
                    fs_to_snap[filesystem] = filesystems[filesystem]
        return fs_to_snap

    def list_rollbacks(self):
        """
       Get the snapshots from SFS server
        :return: Snapshots and file system names
        :rtype: dict
       """
        storage_pool = self.poolname
        return self.nasconsole.storage_rollback_list(storage_pool,
                                                     self.snap_prefix)

    def list_snapshots(self, detailed):
        """
        List the existing snapshots

        :return:
       """
        rollbacks = self.list_rollbacks()
        filesystems = self.build_fs_to_snap()
        snapshots = []
        for _filesystem in filesystems:
            if _filesystem in rollbacks and rollbacks[_filesystem]:
                snapshots.append(_filesystem)
                snaplist = ', '.join(rollbacks[_filesystem])
                self.logger.info('{0}: Filesystem {1} has associated '
                                 'rollback(s): {2}'.format(self.log_prefix,
                                                           _filesystem,
                                                           snaplist))
                if detailed:
                    for _snapname in rollbacks[_filesystem]:
                        snapdata = self.nasconsole.storage_rollback_info(
                                _snapname)[_snapname]
                        if self.nas_type_name == 'veritas':
                            self.logger.info('{0}:  Creation {1}'.format(
                                self.log_prefix, snapdata['SNAPDATE']))
                            self.logger.info('{0}:  Changed  {1}'.format(
                                self.log_prefix, snapdata['CHANGED_DATA']))
                            self.logger.info('{0}:  Synced   {1}'.format(
                                self.log_prefix, snapdata['SYNCED_DATA']))
                        else:
                            self.logger.info('{0}:  Creation {1}'.format(
                                self.log_prefix, snapdata['CREATIONTIME']))
        if not snapshots:
            self.logger.info('{0}: No NAS snapshots found on the system'
                             ' (tag={1}).'.format(self.log_prefix,
                                                  self.snap_prefix))
        return snapshots

    def validate(self, filesystems=None):
        """
        Check the validity of snapshot
        :param filesystems: List of filesystems to validate
        """
        threshold = 80
        self.logger.info('{0}: Validating NAS snapshots.'.
                         format(self.log_prefix))
        cache_name = get_rollback_cache_name(self.poolname)
        existing_caches = self.nasconsole.storage_rollback_cache_list()
        exit_code = EXIT_OK
        if self.nas_type_name == 'veritas':
            if cache_name not in existing_caches:
                self.logger.error('{0}: No rollback cache {1} exists.'.
                                  format(self.log_prefix, cache_name))
                exit_code = EXIT_VALIDATE_ERROR
            else:
                self.logger.info('{0}: OK Found rollback cache {1}'.
                                 format(self.log_prefix, cache_name))
                usage = float(existing_caches[cache_name]['used_perc'])
                if usage == 100:
                    self.logger.error('{0}: Rollback cache {1} is full!'.
                                      format(self.log_prefix, cache_name))
                    exit_code = EXIT_VALIDATE_ERROR
                elif usage >= threshold:
                    self.logger.error('{0}: Usage of rollback cache {1} is'
                                  ' exceeding {2}%!'.format(self.log_prefix,
                                                            cache_name,
                                                            threshold))
                else:
                    self.logger.info('{0}: Rollback cache {1} usage at {2}%'.
                                 format(self.log_prefix, cache_name, usage))
        if not filesystems:
            filesystems = self.build_fs_to_snap()
        self.logger.info('{0}: Verifying {1} filesystems in storage pool '
                         '{2} have snapshots'.format(self.log_prefix,
                                                     len(filesystems),
                                                     self.poolname))
        snapshots = self.nasconsole.storage_rollback_list(self.poolname,
                                                          self.snap_prefix)
        for fs_name in filesystems:
            if fs_name in snapshots:
                self.logger.info('{0}: Found snapshot(s) {1} for filesystem '
                                 '{2}'.format(self.log_prefix,
                                              ','.join(snapshots[fs_name]),
                                              fs_name))
            else:
                self.logger.error('{0}: Filesystem {1} has no snapshot with '
                                  'prefix {2}'.format(self.log_prefix,
                                                      fs_name,
                                                      self.snap_prefix))
                exit_code = EXIT_VALIDATE_ERROR
        if exit_code != EXIT_OK:
            raise SystemExit(exit_code)

    def create_threads(self,  # pylint: disable=R0912
                       funct, snapshots, action, snap_fs_export=None):
        """
        Run a function in a series of threads
        """
        pool = ThreadPool(processes=self.num_of_threads)
        results = []

        def report(result):
            """
            Add results to list

            :param result: Thread result tuple
            :return:
            """
            results.append(result)
        try:
            for filesystem, snapshot in snapshots.items():
                if action == "Remove":
                    pool.apply_async(funct, args=(filesystem, snap_fs_export),
                                     callback=report)
                else:
                    pool.apply_async(funct, args=(filesystem, snapshot,
                                                  snap_fs_export),
                                 callback=report)
            pool.close()
            pool.join()
        except KeyboardInterrupt:
            pool.terminate()
            raise

        if not results:
            raise SfsSnapshotsException('{0}: {1} NAS FS threads did not'
                                        ' return any result'.format
                                        (self.log_prefix, action))
        all_ok = True
        for success, exception in results:
            if not success:
                all_ok = False
                if exception:
                    self.logger.error('{0}'.format(exception))
        if not all_ok:
            raise SfsSnapshotsException('{0}: {1} NAS rollbacks failed'.
                                        format(self.log_prefix, action))

        if len(results) != len(snapshots):
            snapshots_results = dict(snapshots)
            for success, filesystem in results:
                del snapshots_results[filesystem]
            for filesystem in snapshots_results:
                self.logger.error('{0}: {1} NAS file system {2} thread '
                                  'did not return any result'.format
                                  (self.log_prefix, action, filesystem))
            raise SfsSnapshotsException('{0}: All the NAS file system {1}'
                                        ' threads did not return result'.
                                        format(self.log_prefix, action))

    def get_snapshots_info(self):
        """
        Get snapshot data
        """
        snapshots_all = self.nasconsole.storage_rollback_list(self.poolname,
                                                              self.snap_prefix)
        return self.build_fs_to_snap(filesystems=snapshots_all)

    def restore_snapshots(self, snap_fs_export):
        """
        Offline SFS filesystems using threads
        Restore SFS filesystems using threads
        Export SFS filesystems using threads
        :param snap_fs_export: exported file systems at the time of snapshot
        :type snap_fs_export: dict
        :return:
        """
        snapshots = self.get_snapshots_info()
        self.create_threads(self.rollback_nas_fs, snapshots, 'Rollback',
                            snap_fs_export)
        self.logger.info('{0}: Restore rollbacks finished '.
                         format(self.log_prefix))

    def rollback_nas_fs(self,  # pylint: disable=R0912, R0915
                        filesystem, snapshots, snap_fs_export):
        """
        Offline, Restore and Export nas fs share for a given file
        system
        :param filesystem: filesystem to be rolled back
        :param snapshots: snapshots for fs
        :param snap_fs_export: list of nas exports
        :return:
        """
        nasconsole = NasConsole(self.cred[SK_NASCONSOLE_IP],
                                self.cred[SK_NASCONSOLE_SUPUSER],
                                self.cred[SK_NASCONSOLE_SUPPASSWD],
                                ssh_port=self.ssh_port,
                                nas_type=self.nas_type_name)
        if self.nas_type_name == 'veritas':
            try:
                self.logger.info('{0}: Offlining filesystem {1}'.
                             format(self.log_prefix, filesystem))
                nasconsole.storage_fs_offline(filesystem)
                nasconsole.ensure_fs_status(filesystem, self.poolname,
                                            'offline')
            except Exception as error:  # pylint: disable=W0703
                self.logger.error("{0}: Offline for fs {1} failed "
                              "with error {2}".format(self.log_prefix,
                                                      filesystem,
                                                      str(error)))
                return False, filesystem
        if len(snapshots) > 1:
            return False, 'More than one rollback found for NAS filesystem ' \
                          '{0}'.format(filesystem)
        snapshot = snapshots[0]
        self.logger.info('{0}: Restoring snapshot {1} for filesystem {2}'.
                         format(self.log_prefix, snapshot, filesystem))
        try:
            self.logger.info('{0}: Restoring snapshot {1}'.
                             format(self.log_prefix, snapshot))
            nasconsole.storage_rollback_restore(filesystem, snapshot)
            if self.nas_type_name == 'veritas':
                self.logger.info('{0}: Onlining filesystem {1}'.
                             format(self.log_prefix, filesystem))
                nasconsole.storage_fs_online(filesystem)
        except Exception as error:  # pylint: disable=W0703
            self.logger.error("{0}: Restore snapshot for fs {1} failed "
                              "with error {2}".format(self.log_prefix,
                                                      filesystem,
                                                      str(error)))
            return False, filesystem
        if filesystem in snap_fs_export:
            for export in snap_fs_export[filesystem]:
                retry_count = 3
                retries = 0
                client = export['client']
                options = export['options']
                while True:
                    self.logger.info("{0}: Exporting {1} "
                                     "to client {2} "
                                     "with options {3}"
                                     .format(self.log_prefix,
                                             filesystem,
                                             client,
                                             options))
                    try:
                        nasconsole.nfs_share_add(filesystem, client, options)
                        sleep(2)
                        exported_fs = nasconsole.nfs_share_show(self.poolname)
                        share_found = False
                        if filesystem in exported_fs:
                            for share_dict in exported_fs[filesystem]:
                                if share_dict['client'] == client:
                                    share_found = True
                                    break
                            if share_found:
                                break
                            else:
                                raise SfsSnapshotsException("{0}: "
                                    "Filesystem {1} "
                                    "has not been exported to client {2} "
                                    "with options {3}"
                                    .format(self.log_prefix,
                                            filesystem,
                                            client,
                                            options))
                        else:
                            raise SfsSnapshotsException("{0}: Filesystem {1} "
                                "has not been exported to client {2} "
                                "with options {3}"
                                .format(self.log_prefix,
                                        filesystem,
                                        client,
                                        options))
                    except Exception as error:  # pylint: disable=W0703
                        retries += 1
                        if retries >= retry_count:
                            self.logger.error("{0}: Retry limit reached ({1}) "
                                "for exporting {2} "
                                "to client {3} "
                                "with options {4}"
                                .format(self.log_prefix,
                                        retry_count,
                                        filesystem,
                                        client,
                                        options))
                            self.logger.error("{0}: Exception: {1} "
                                "Exporting {2} "
                                "to client {3} "
                                "with options {4}"
                                .format(self.log_prefix,
                                        str(error),
                                        filesystem,
                                        client,
                                        options))
                            return False, filesystem
                        else:
                            self.logger.info("{0}: Waiting for export of {1} "
                                "to client {2} "
                                "with options {3} "
                                "to become available, "
                                "retrying command.."
                                .format(self.log_prefix,
                                        filesystem,
                                        client,
                                        options))
                            sleep(2)
                            continue
        self.logger.info('{0}: Restored filesystem {1} from snapshot {2}'.
                         format(self.log_prefix, filesystem, snapshot))
        return True, filesystem

    def remove_rollback_cache(self):
        """
        Destroy the rollback cache (if it exists)

        """
        self.logger.info('{0}: Looking for rollback caches to destroy.'.
                         format(self.log_prefix))
        cache_list = self.nasconsole.storage_rollback_cache_list()
        cache_name = get_rollback_cache_name(self.poolname)
        if cache_name in cache_list:
            self.logger.info('{0}: Destroying rollback cache {1}'.
                             format(self.log_prefix, cache_name))
            self.nasconsole.storage_rollback_cache_destroy(cache_name)
        else:
            self.logger.info('{0}: No rollback cache needs destroying.'.
                             format(self.log_prefix))

    def remove_sfs_shares(self):
        """
        Remove SFS Share(if it exists) of the file systems having snapshots

        """
        snapshots_all = self.nasconsole.storage_rollback_list(self.poolname,
                                                              self.snap_prefix)
        fs_exports_all = self.nasconsole.nfs_share_show(self.poolname)
        fs_exports = self.build_fs_to_snap(filesystems=fs_exports_all)
        snapshots = self.build_fs_to_snap(filesystems=snapshots_all)
        self.create_threads(self.nfs_share_delete, snapshots, 'Remove',
                            fs_exports)

    def nfs_share_delete(self, filesystem, fs_exports):
        """
        Removes Nas shares of the filesystems
        :param filesystem: filesystem for which an export is to be removed
        :type filesystem: string
        :param fs_exports: details of exported file system in snapshot
        :type fs_exports: dict
        :return: Result and Filesystem name
        :rtype: Tuple
        """
        nasconsole = NasConsole(self.cred[SK_NASCONSOLE_IP],
                                self.cred[SK_NASCONSOLE_SUPUSER],
                                self.cred[SK_NASCONSOLE_SUPPASSWD],
                                ssh_port=self.ssh_port,
                                nas_type=self.nas_type_name)
        try:
            if filesystem in fs_exports:
                for export in fs_exports[filesystem]:
                    client = export['client']
                    options = export['options']
                    self.logger.info("{0}: Removing export of {1} "
                                     "to client {2} "
                                     "with options {3}"
                                     .format(self.log_prefix,
                                             filesystem,
                                             client,
                                             options))
                    nasconsole.nfs_share_delete(filesystem, client)
                    self.logger.info("{0}: Removed export of {1} to client {2}"
                                     .format(self.log_prefix,
                                             filesystem,
                                             client))
                    return True, filesystem
        except Exception as error:  # pylint: disable=W0703
            self.logger.error("{0}: Remove export for fs {1}"
                              "failed with error {2}"
                              .format(self.log_prefix,
                                      filesystem,
                                      str(error)))
        return False, filesystem

    def get_modelled_filesystems(self):
        """
        Query the LITP model to get a list of file systems. The file
        system will be included in the list only if the snap size
        is set to be greater than zero.
        :return: A dictionary of file systems
        :rtype: dict
        """
        if not self.fs_snap_list:
            self.fs_snap_list = {}
            _storage_pools = self.litp.get_children(self.litp_sfs_path)
            for storage_pool in _storage_pools:
                fs_model_path = '{0}/file_systems'.format(storage_pool['path'])
                file_systems = self.litp.get_children(fs_model_path)
                for filesystem in file_systems:
                    file_system_obj = LitpObject(None, filesystem['data'],
                                                 self.litp.path_parser)
                    snap_size = file_system_obj.get_int_property(
                        'snap_size', 0)
                    if snap_size > 0:
                        self.fs_snap_list[(basename(
                            file_system_obj.get_property('path')))] = \
                            {SFS_SNAP_SIZE_KEY: snap_size}
        return self.fs_snap_list

    def get_filesystems_for_removal(self):
        """
        Get a defined list of filesystems to be removed. Check that any
        services with this name no longer exist in the deployment model under
        /software/services.
        :return: A list of filesystems
        """
        self.logger.info('{0}: Determining list of filesytems for removal'
                         .format(self.log_prefix))

        filesystems_to_remove = list()

        for filesystem in SERV_BASE_NAMES:
            service_vpath = '/software/services/{0}'.format(filesystem)
            filesystem_full_name = '{0}-{1}'\
                                    .format(self.poolname, filesystem.lower())
            try:
                self.litp.get_children(service_vpath)
                self.logger.info('{0}: {1} still exists in the '
                                 'deployment model at {2}'
                                 .format(self.log_prefix,
                                         filesystem,
                                         service_vpath))
                self.logger.info('{0}: Filesystem {1} will not be removed'
                                 .format(self.log_prefix,
                                         filesystem_full_name))
            except LitpException as ex:
                if ex.get_message_from_messages('type') == \
                        LITP_INVALID_LOCATION_ERROR:
                    self.logger.debug('{0}: {1} does not exist in the '
                                      'deployment model at {2}'
                                      .format(self.log_prefix, filesystem,
                                              service_vpath))
                    filesystems_to_remove.append(filesystem_full_name)
                else:
                    raise
        return filesystems_to_remove

    def ensure_removal_fs_not_required(self):
        """
        Get filesystems that are marked to be removed from NAS. If they exist
        on the NAS, remove each of these filesystem's exports and delete them.
        """
        self.logger.info('{0}: Ensuring any filesystems marked for removal '
                         'are not present on the NAS'.format(self.log_prefix))

        fs_for_removal = self.get_filesystems_for_removal()
        nas_fs = self.nasconsole.storage_fs_list(self.poolname)
        nas_exports = self.nasconsole.nfs_share_show(self.poolname)

        for filesystem in fs_for_removal:
            if filesystem in nas_fs:
                try:
                    self.logger.info('{0}: Filesystem {1} in pool {2} is '
                                     'marked as a filesystem for removal'
                                     .format(self.log_prefix,
                                             filesystem, self.poolname))

                    client = nas_exports[filesystem][0]['client']
                    self.logger.info('{0}: Removing export of {1} to host {2}'
                                     .format(self.log_prefix, filesystem,
                                             client))
                    self.nasconsole.nfs_share_delete(filesystem, client)
                    self.logger.info('{0}: Removed export of {1} to host {2}'
                                     .format(self.log_prefix, filesystem,
                                             client))

                    self.logger.info('{0}: Destroying {1} filesystem'
                                     .format(self.log_prefix, filesystem))
                    self.nasconsole.storage_fs_destroy(filesystem)
                    self.logger.info('{0}: Filesystem {1} successfully '
                                     'destroyed'.format(self.log_prefix,
                                                        filesystem))
                except NasConsoleException:
                    self.logger.error('{0}: Failed to remove export and '
                                      'destroy filesystem {1}'
                                      .format(self.log_prefix, filesystem))
                    raise
