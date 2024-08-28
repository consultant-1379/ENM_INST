"""
This module is used to clean up SFS filesystems. It removes shares,
filesystems and snapshots (if any exist) from a particular storage pool.
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
# Name    : cleanup_sfs.py
# Purpose : The purpose of this script is to remove sfs snapshots
# ********************************************************************
import logging
import os
import sys
from datetime import datetime
from dircache import listdir
from optparse import OptionParser
from os.path import exists, basename
from re import search
from shutil import copy2
from time import sleep, strftime

from netaddr import IPNetwork

from h_logging.enminst_logger import init_enminst_logging
from h_snapshots.sfs_snapshot import EXIT_NO_ROLLBACKS
from h_util.h_nas_console import NasConsole, NasConsoleException, \
    get_rollback_cache_name, get_litp_rollback_cache_name
from h_util.h_utils import exec_process, Sed, get_env_var, wstderr, \
    get_nas_type_sed

SK_SFS_POOL_NAME = 'ENM_sfs_storage_pool_name'
SK_NASCONSOLE_IP = 'sfs_console_IP'
SK_NASCONSOLE_SUPUSER = 'sfssetup_username'
SK_NASCONSOLE_SUPPASSWD = 'sfssetup_password'
SK_LMS_IP_STORAGE = 'LMS_IP_storage'
SK_STORAGE_SUBNET = 'storage_subnet'
IFCFG = '/etc/sysconfig/network-scripts/ifcfg-{0}'
SYSTEMCTL = '/usr/bin/systemctl'
DEPLOYMENT_TYPE = 'enm_deployment_type'


def get_ip_address(ifname):
    """
    Get the IPv4 address assigned to a nic

    :param ifname: The interface name e.g. eth2
    :type ifname: str
    :return: The IPv4 address assigned to the nic or None if nothing assigned.
    :rtype: str|None
    """
    stdout = exec_process(['/sbin/ifconfig', ifname])
    for line in stdout.split('\n'):
        addrmatch = search(r'inet (.*?)\s+', line)
        if addrmatch:
            return addrmatch.group(1)
    return None


def get_assigned_ips():
    """
    Get a list if nic's and their assigned IPv4 address. Only nics with
    addresses are returned

    :return: List of nics with assigned IPv4 addresses
    :rtype str[]
    """
    dirs = listdir('/sys/class/net/')
    addrs = {}
    for ifname in dirs:
        if ifname == 'bonding_masters':
            continue
        addr = get_ip_address(ifname)
        if addr:
            addrs[addr] = ifname
    return addrs


def wait_detect_link(device, log, link_detect_timeout=180):
    """
    Wait for a nic to be detected by the system
    :param device: The device name
    :param log: Logger
    :param link_detect_timeout: Max time to wait
    :return:
    """
    _time = 0
    log.info('Waiting to detect link for {0}'.format(device))
    while True:
        lines = exec_process(['/sbin/ethtool', device]).split('\n')
        detected = 'no'
        for line in reversed(lines):
            line = line.strip()
            if 'Link detected:' in line:
                detected = line.split(':')[1].strip()
                break
        if detected == 'yes':
            log.info('Link detected.')
            break
        else:
            if _time >= link_detect_timeout:
                raise IOError('Link for {0} not detected in '
                              '{1} seconds!'.format(device,
                                                    link_detect_timeout))
            sleep(1)
            _time += 1


def plumber(device, kwargs, log):
    """
    Update a nics ifcfg file with address info and enable it.

    This check to see if the ifcfg file for the nic exists and updates
    parameters to plumb the nic.

    If the ifcfg file exists and already has the IP address assigned (IPADDR)
    nothing will be done (already plumbed).

    If the ifcfg file exists but the IPADDR is not found then the kwargs are
    merged into the file (one of the kwargs will be IPADDR) and then the nic
    restarted

    :param device: The nic
    :type device: str
    :param kwargs: List of ifcfg entries to merge
    :type kwargs: dict
    :param log: Logger class
    :type log: Logger
    """
    cfg = IFCFG.format(device)
    existing = {}
    merge_needed = True
    if exists(cfg):
        with open(cfg, 'r') as cfg_handle:
            for line in cfg_handle.readlines():
                if not search(r"^\s*#.*$", line):
                    line = line.strip()
                    kvp = line.split('=', 1)
                    existing[kvp[0]] = kvp[1]
        if 'IPADDR' in existing and existing['IPADDR'] == kwargs['IPADDR']:
            log.info('Device {0} already configured (ifcfg-{0}) with '
                     'address IPADDR={1}, no changes being '
                     'made.'.format(device, kwargs['IPADDR']))
            merge_needed = False
    if merge_needed:
        log.info('Assigning address {0} for device '
                 '{1}'.format(kwargs['IPADDR'], device))
        merged = existing.copy()
        merged.update(kwargs)
        contents = '\n'.join(
                ['%s=%s' % (key, value) for (key, value) in merged.items()])
        with open(cfg, 'w+') as cfg_handle:
            cfg_handle.write(contents)
            cfg_handle.write('\n')
        log.info('Restarting {0}'.format(device))
        exec_process(['/sbin/ifdown', device])
        exec_process(['/sbin/ifconfig', device, 'down'])
    else:
        log.info('Making sure {0} is up.'.format(device))
    exec_process(['/sbin/ifconfig', device, 'up'])
    exec_process(['/sbin/ifup', device])
    wait_detect_link(device, log)


def ping_nasconsole(storage_nic, nasconsole, log):
    """
    Ping the nasconsole address from a particular network device (nic/bond)
    :param storage_nic: The device to ping with
    :param nasconsole: The nasconsole address
    :param log: Logger
    :return:
    """
    try:
        exec_process(['/bin/ping', '-c', '5', '-I', storage_nic, nasconsole])
        log.info('Ping of nasconsole/{0} over {1} OK.'.format(nasconsole,
                                                              storage_nic))
    except IOError:
        log.exception('Could not ping nasconsole/{0} over '
                      '{1}!'.format(nasconsole, storage_nic))
        raise


def plumb_lms_storage(storage_nic, sed, log):
    """
    Plumb up the storage address to a nic if it's not already present.
    If the storage address is already assigned to some other nic then nothing
    is changed (should already be connectivity)

    :param storage_nic: The nic to plumb up
    :type storage_nic: str
    :param sed: The Site Engineering file being used to install the deployment
    :type sed: Sed
    :param log: Logger to use
    :type log: Logger
    """
    if not sed.get_value(DEPLOYMENT_TYPE) == 'Extra_Large_ENM_On_Rack_Servers':
        log.info('Checking if storage VLAN address assigned.')
        lms_ip_storage = sed.get_value(SK_LMS_IP_STORAGE)
        storage_subnet = sed.get_value(SK_STORAGE_SUBNET)
        current_ips = get_assigned_ips()
        if lms_ip_storage in current_ips:
            log.info('IP address {0} already plumbed to '
                     'device {1}, nothing more to '
                     'do.'.format(lms_ip_storage, current_ips[lms_ip_storage]))
            return
        lms_eth_mac = sed.get_value('LMS_{0}_macaddress'.format(storage_nic))
        ipnet = IPNetwork(storage_subnet)
        args = {'DEVICE': storage_nic,
                'BOOTPROTO': 'static',
                'NOZEROCONF': 'no',
                'USERCTL': 'no',
                'NETMASK': ipnet.netmask,
                'HWADDR': lms_eth_mac,
                'IPADDR': lms_ip_storage,
                'BROADCAST': ipnet.broadcast}
        plumber(storage_nic, args, log)
        current_ips = get_assigned_ips()
        if lms_ip_storage not in current_ips:
            log.info('Plumbed the IP address {0} to {1} but '
                     'is not visible after device restart!'.format(
                                                               lms_ip_storage,
                                                               storage_nic))
            raise SystemExit(3)
        else:
            log.info('Found IP address, {0} assigned '
                     'address {1}'.format(storage_nic, lms_ip_storage))
        nasconsole = sed.get_value('sfs_console_IP')
        ping_nasconsole(storage_nic, nasconsole, log)
    else:
        log.info('Rack deployment detected, LMS storage '
            'plumbing will be skipped')
        return


def format_msg(levelstr, msg):
    """
    Format a message

    :param levelstr: The level being logged at
    :type levelstr: str
    :param msg: The log message
    :type msg: str
    :return: Formatted log message including level and timestamp
    :rtype: str
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return '{0} {1:<5} {2:<20}: {3}'.format(timestamp, levelstr,
                                            "sfs_cleanup", msg)


class SfsCleanup(object):
    """
    Class the clean up an SFS for a deployment
    """

    def __init__(self, sed, ssh_port=22):
        """
        Constructor
        :param sed: The SED handler
        :type sed: Sed
        :param ssh_port: The ssh port (defaults to 22)
        :type ssh_port: int
        :return:
        """
        self.sed = sed
        self.logger = logging.getLogger('enminst')
        self.poolname = self.sed.get_value(SK_SFS_POOL_NAME)
        uname = self.sed.get_value(SK_NASCONSOLE_SUPUSER)
        passwd = self.sed.get_value(SK_NASCONSOLE_SUPPASSWD)
        self.nas_type_sed = get_nas_type_sed(self.sed)
        self.nasconsole = NasConsole(self.sed.get_value(SK_NASCONSOLE_IP),
                                     uname, passwd, ssh_port=ssh_port,
                                     nas_type=self.nas_type_sed)

    def check_sfs(self):
        """
        Check to ensure no rollback is ongoing
        """
        self.logger.info('Ensuring there are no ongoing procedures')
        rollback = self.nasconsole.rollback_check(self.poolname)
        if rollback:
            self.logger.error('There appears to be a rollback in progress. '
                              'Exiting...')
            raise SystemExit(EXIT_NO_ROLLBACKS)

    def remove_shares(self, exclude=None):
        """
        Remove all shares from filesystems in a pool
        :param exclude: The list of shares to exclude from removal
        :type exclude: list
        """
        self.logger.info('Looking for exports to remove.')
        exports = self.nasconsole.nfs_share_show(self.poolname)
        exclude = exclude or []
        for filesystem, exports in exports.items():
            if filesystem in exclude:
                self.logger.info('Skipping {0} exports for '
                        '{1}'.format(len(exports), filesystem))
                continue
            self.logger.info('Removing {0} exports for '
                             '{1}'.format(len(exports), filesystem))
            for export in exports:
                self.logger.info('Deleting allowed host {0} '
                                 'for file system '
                                 '{1}'.format(export['client'], filesystem))
                self.nasconsole.nfs_share_delete(filesystem, export['client'])
        self.logger.info('Shares removed.')

    def remove_filesystem_snapshots(self):
        """
        Destroy all rollbacks (snapshots) in a storage pool

        """
        self.logger.info('Looking for rollbacks to destroy.')
        rollbacks = self.nasconsole.storage_rollback_list(self.poolname, '*')
        if len(rollbacks) > 0:
            for filesystem, fs_snaps in rollbacks.items():
                self.logger.info('Destroying {0} rollbacks for '
                                 '{1}'.format(len(fs_snaps), filesystem))
                for snap in fs_snaps:
                    self.logger.info('Destroying rollback {0}'.format(snap))
                    self.nasconsole.storage_rollback_destroy(snap, filesystem)
            self.logger.info('Rollbacks destroyed.')
        else:
            self.logger.info('No rollbacks to destroy, continuing.')

    def remove_filesystems(self, exclude=None):
        """
        Destroy all filesystems in a storage pool
        :param exclude: The list of FS to exclude from removal
        :type exclude: list
        """
        self.logger.info('Looking for filesystems to destroy.')
        filesystems = self.nasconsole.storage_fs_list(self.poolname)
        exclude = exclude or []
        vxedit_file = '/tmp/.NoVxEdit'
        if os.path.isfile(vxedit_file):
            vxedit_exists = "True"
        else:
            vxedit_exists = "False"
        if len(filesystems) == 0:
            self.logger.info('No file system to destroy, continuing.')
        else:
            self.logger.info('Destroying {0} '
                             'filesystems'.format(len(filesystems)))
            for filesystem in filesystems.keys():
                if filesystem in exclude:
                    self.logger.info('Skipping filesystem '
                            '{0}'.format(filesystem))
                    continue
                self.logger.info('Destroying filesystem '
                                 '{0}'.format(filesystem))
                self.logger.debug(
                        self.nasconsole.storage_fs_list_details(filesystem))
                if vxedit_exists == "True" and self.nas_type_sed == 'veritas':
                    self.nasconsole.storage_fs_destroy(filesystem)
                else:
                    try:
                        self.nasconsole.storage_fs_destroy(filesystem)
                    except NasConsoleException:
                        self.logger.info('Offlining fs {0}'.format(filesystem))
                        self.nasconsole.storage_fs_offline(filesystem)
                        self.ensure_fs_destroyed(filesystem)
        self.logger.info('Completed fs removal stage.')

    def ensure_fs_destroyed(self, filesystem):
        """
        Destroy all filesystems in a storage pool that did not get
        removed from initial destroy

        """
        self.logger.info('Support user destroying filesystem '
                         '{0}'.format(filesystem))
        self.nasconsole.support_fs_destroy(filesystem)
        self.logger.info('Support destroyed filesystem {0}'.format(filesystem))

    def remove_rollback_caches(self):
        """
        Destroy the rollback cache (if it exists)

        """

        self.logger.info('Looking for rollback caches to destroy.')
        cache_list = self.nasconsole.storage_rollback_cache_list()
        caches = [get_rollback_cache_name(self.poolname),
                  get_litp_rollback_cache_name(self.poolname)]
        if cache_list:
            for cache_name in caches:
                if cache_name in cache_list:
                    self.logger.info('Destroying rollback '
                                     'cache {0}'.format(cache_name))
                    self.nasconsole.storage_rollback_cache_destroy(cache_name)
        else:
            self.logger.info('No rollback cache needs destroying.')

    def clean_all(self, exclude=None):
        """
        Clean up a storage pool for redeployment

        Destroys all filesystems, rollbacks(snapshots) and rollback caches
        :param exclude: The list of shares and FS to exclude from removal
        :type exclude: list
        """
        self.remove_filesystem_snapshots()
        self.remove_shares(exclude)
        self.remove_filesystems(exclude)
        if self.nas_type_sed == 'veritas':
            self.remove_rollback_caches()


def print_header(message, logger):
    """
    Wrap a message in a header formatted string
    :param message: The message to log
    :param logger: Logger instance
    :return:
    """
    logger.info('-' * 65)
    logger.info(message)
    logger.info('-' * 65)


def clean_lms_mounts(nas_type, sfs_pool_name, logger):
    """
    Remove NAS mounts from the LMS fstab file
    :param nas_type: The NAS type, of value 'unityxt' or 'veritas'
    :param sfs_pool_name: The SFS pool name containing the mounts to remove
    :param logger: Logger instance
    :return:
    """
    try:
        logger.info('Stopping DDC ...')
        exec_process([SYSTEMCTL, 'stop', 'ddc.service'])
    except IOError as ioe:
        logger.debug('DDC didn\'t stop: '.format(str(ioe)))

    cleaned_tabs = []
    fstab_file = '/etc/fstab'

    if nas_type == 'unityxt':
        line_regex = '.*?:/{0}-.*'.format(sfs_pool_name)
    else:
        line_regex = '.*?:/vx/{0}-.*'.format(sfs_pool_name)
    changes_made = False
    with open(fstab_file, 'r') as _fstab:
        for line in _fstab.readlines():
            if search(line_regex, line):
                changes_made = True
                mountpoint = line.split()[1]
                try:
                    exec_process(['/bin/umount', '-fl', mountpoint])
                except IOError as ioe:
                    if 'not mounted' not in str(ioe):
                        logger.exception('Failed to unmount '
                                         '{0}'.format(mountpoint))
                        raise
                    else:
                        logger.debug('Mount {0} already '
                                     'unmounted...'.format(mountpoint))
                logger.info('Removed fstab entry for {0}'.format(mountpoint))
            else:
                cleaned_tabs.append(line.strip())

    if changes_made:
        logger.info('Removed NAS mounts from pool'
                    ' \'{0}\''.format(sfs_pool_name))
        tstamp = strftime('%Y%m%d-%H%M%S')
        copy2(fstab_file, '{0}.{1}'.format(fstab_file, tstamp))
        new_contents = '\n'.join(cleaned_tabs).strip()
        # need a newline at the end of the fstab file, stops a mntent warning
        new_contents += '\n'
        with open(fstab_file, 'w+') as _fstab:
            _fstab.write(new_contents)
    else:
        logger.info('No changes made to {0} for '
                    'NAS pool \'{1}\''.format(fstab_file, sfs_pool_name))


def teardown_sfs(sedfile, storage_device, logger, exclude=None):
    """
    Delete filesystems, shares and snapshots in a storage pool to
    enable reinstall. The storage pool name is taken from the input SED.

    :param sedfile: Path to the Site Engineering file used to install
    the system
    :type sedfile: str
    :param storage_device: The NIC to assign the Storage IP too.
    :type storage_device: str
    :param logger: Logger object to log with
    :type logger: Logger
    :param exclude: The list of shares and FS to exclude from removal
    :type exclude: list
    """
    print_header("NAS clean up starting", logger)
    sed = Sed(sedfile)
    plumb_lms_storage(storage_device, sed, logger)
    sfs = SfsCleanup(sed)
    sfs.check_sfs()
    clean_lms_mounts(get_nas_type_sed(sed),
                     sed.get_value(SK_SFS_POOL_NAME), logger)
    sfs.clean_all(exclude)
    print_header("NAS clean up done.", logger)


def main(args):
    """
    Main function.

    Loads a few OS environment variables, sets up logging can then calls
    the cleanup functions.
    :param args: sys args
    """
    try:
        logger = init_enminst_logging()
        logger.setLevel(get_env_var('LOG_LEVEL'))
    except KeyError as keyerror:
        msg = "FATAL ERROR: '{0}' is unable to load the " \
              "environment {1} (started directly?), please correct before " \
              "restarting.".format(basename(__file__), str(keyerror))
        wstderr(msg)
        raise SystemExit(1)

    exclude = None
    usage = ('usage: %prog '
             ' --sed <location to site engineering document>')
    arg_parser = OptionParser(usage)
    arg_parser.add_option('--sed')
    arg_parser.add_option('--sd', dest='storage_device', default='eth1')
    arg_parser.add_option('--exclude', dest='exclude',
        help='File systems and shares to exclude as a comma separated list.')
    (options, _) = arg_parser.parse_args(args)
    if options.exclude:
        exclude = [ex.strip() for ex in options.exclude.split(',') if ex]
    teardown_sfs(options.sed, options.storage_device, logger, exclude)


if __name__ == '__main__':
    main(sys.argv)
