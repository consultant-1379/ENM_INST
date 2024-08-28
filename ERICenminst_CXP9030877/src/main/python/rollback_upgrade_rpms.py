"""
This script rolls back rpms that were updated or installed during and ENM
Upgrade
"""
# pylint: disable=R0201,R0911,R0912,R0914,W1401,R0915
##############################################################################
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################
import re
import os
import fnmatch
import sys
import socket
from pre_upgrade_rpms import RPM_UPGRADE_INFO_FILE
from h_util.h_utils import copy_file, get_rpm_info, delete_file,\
    compare_versions
from h_logging.enminst_logger import init_enminst_logging
from h_puppet.mco_agents import EnmPreCheckAgent, McoAgentException
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from h_puppet import h_puppet


class RollbackUpgradeRpm(object):
    """
    Class that handles rolling back upgraded RPMs from an ENM Upgrade
    """
    CMD_TIMEOUT = 240

    def __init__(self, rpm_info_path=RPM_UPGRADE_INFO_FILE):
        self.rpm_info_path = rpm_info_path
        self.rpm_data_list = None
        self.logger = init_enminst_logging()
        self.ms_name = socket.gethostname()

    def get_rpm_data(self, rpm_info_path):
        """
        Get rpm upgrade details from rpm_upgrade_file
        :param rpm_info_path: path to rpm_upgrade_file
        """
        self.logger.info("Getting rpm upgrade info for rollback")
        rpms = []
        try:
            with open(rpm_info_path, 'r') as rpm_info:
                for line in rpm_info:
                    line = line.rstrip()
                    match = re.search(r'^ERIC.*$', line)
                    if match:
                        match = match.group().split(",")
                        if len(match) != 4:
                            continue
                        rpms.append({'before_rpm_name': match[0],
                                     'last_operation': match[1],
                                     'after_rpm_name': match[2],
                                     'host': match[3]})
        except IOError:
            err = "Couldn't read rpm file"
            raise IOError(err, 1)
        self.rpm_data_list = rpms

    def get_installed_rpm_info(self, rpm_name, host, mco_agent):
        """
        Get rpm info on host
        :param rpm_name: name of rpm
        :param host: name of host
        :param mco_agent: EnmPreCheckAgent object
        :return rpm_info: rpm details
        """
        try:
            rpm_info = mco_agent.get_package_info(host, rpm_name)
            return rpm_info

        except (IndexError, McoAgentException) as err:
            if 'is not installed' in str(err):
                self.logger.warning("Package {0} is not installed on"
                                    " node {1}, please rollback manually"
                                    .format(rpm_name, host))
            else:
                self.logger.error('Error getting package info for {0}'
                                  ' from {1}, please rollback manually'
                                  .format(rpm_name, host))
            return None

    def modify_litp_package(self, package_action, package_name,
                                      host, mco_agent):
        """
        Wait for puppet catalogue to complete and disable puppet while
        downgrading litp pre upgrade packages
        :param package_action: action on package to be upgraded
         or downgraded
        :type package_action: String
        :param package_name: package name from pre upgrade script
        :type package_name: String
        :param host: name of host to remove rpm on
        :type host: Dictionary
        :param mco_agent: EnmPreCheckAgent object
        :type mco_agent: Object
        :return result: success or failure of updating package
        :type result: Boolean
        """
        h_puppet.check_for_puppet_catalog_run()
        self.logger.info(
            "Disabling puppet agent on all nodes.")
        h_puppet.puppet_enable_disable(state='disable')

        if package_action == "bigger":
            success = self.upgrade_rpm_on_host(package_name,
                                               host, mco_agent)
        else:
            success = self.downgrade_rpm_on_host(
                package_name, host, mco_agent)
        self.logger.info("Enabling puppet agent on all nodes.")
        h_puppet.puppet_enable_disable(state='enable')
        self.logger.info(
            'Mco Agent Upgrade Packages Result: {0}'
            .format(success))
        return success

    def remove_rpm_from_host(self, rpm_name, host, mco_agent):
        """
        Remove a rpm on a host
        :param rpm_name: name of rpm to remove
        :param host: name of host to remove rpm on
        :param mco_agent: EnmPreCheckAgent object
        :return result: str message
        """
        try:
            result = str(mco_agent.remove_packages(host, rpm_name))
            if 'No Packages marked for removal' in result:
                self.logger.warning("Package {0} has already been removed on"
                                    " node {1}, skipping..."
                                    .format(rpm_name, host))
                return None
            return result
        except McoAgentException:
            self.logger.error("Failed to remove package {0}"
                              " from host {1}, please remove manually"
                              .format(rpm_name, host))
            return None

    def install_rpm_on_host(self, rpm_name, host, mco_agent):
        """
        Install a rpm on a host
        :param rpm_name: name of rpm to install
        :param host: name of host to install rpm on
        :param mco_agent: EnmPreCheckAgent object
        :return result: str message
        """
        try:
            result = str(mco_agent.install_packages(host, rpm_name))
            if 'Nothing to do' in result:
                self.logger.warning("Package {0} has already been installed on"
                                    " node {1}, skipping..."
                                    .format(rpm_name, host))
                return None
            return result
        except McoAgentException:
            self.logger.error("Failed to install package {0}"
                              " from host {1}, please install manually"
                              .format(rpm_name, host))
            return None

    def upgrade_rpm_on_host(self, rpm_name, host, mco_agent):
        """
        Upgrade a rpm on a host
        :param rpm_name: name of rpm to upgrade
        :param host: name of host to upgrade rpm on
        :param mco_agent: EnmPreCheckAgent object
        :return True/False i.e success of upgrade
        """
        try:
            result = mco_agent.upgrade_packages(host, rpm_name)
            if 'No Packages marked for Update' in str(result):
                return False
            return True
        except McoAgentException:
            return False

    def check_old_rpm_vs_rollback_rpm(self, rpm_name, old_package_name):
        """
        Checks if the old rpm matches the rpm currently
        installed on the system.
        :param rpm_name: name of rpm to upgrade
        :param old_package_name: name of old rpm
        :return True/False i.e true if they're the same
        """
        installed_rpm_info = get_rpm_info(self.ms_name,
                                          rpm_name=rpm_name)
        old_package_without_path = os.path. \
            basename(os.path.normpath(old_package_name))
        installed_rpm = installed_rpm_info.get('name') \
                        + '-' + installed_rpm_info.get('version') + ".rpm"
        return installed_rpm == old_package_without_path

    def downgrade_rpm_on_host(self, rpm_name, host, mco_agent):
        """
        Downgrade a rpm on a host
        :param rpm_name: name of rpm to downgrade
        :param host: name of host to downgrade rpm on
        :param mco_agent: EnmPreCheckAgent object
        :return True/False i.e success of downgrade
        """
        try:
            result = mco_agent.downgrade_packages(host, rpm_name)
            if 'Nothing to do' in str(result):
                return False
            return True
        except McoAgentException:
            return False

    def check_if_version_in_yum(self, mco_agent, host, rpm_name):
        """
        Find if version of rpm exists in yum
        :param mco_agent: EnmPreCheckAgent object
        :param host: name of host to look on
        :param rpm_name: name of rpm to check yum versions
        :return available_version_strs: list of rpm versions available in yum
        """
        try:
            yum_versions = mco_agent. \
                get_available_package_versions(host,
                                               rpm_name)
        except McoAgentException:
            self.logger.warning("No versions of package {0}"
                                " available, please rollback"
                                " manually".format(rpm_name))
            return []
        regex = rpm_name + \
                '([^-]*?)(\d+\.\d+\.\d+-?\d*\.?\w*)'
        regex = r'{0}'.format(regex)
        available_versions = re.findall(regex, yum_versions)

        available_versions_strs = []
        for version in available_versions:
            version_str = version[1]
            version_regex = r'(\d+)\.(\d+)\.(\d+)'
            available_version_str = re.search(version_regex,
                                              version_str)
            available_versions_strs.append(
                available_version_str.group())
        return available_versions_strs

    def rollback_upgraded_rpms(self, rpms):
        """
        Rollback upgraded rpms
        :param rpms: list of rpms
        """
        failure = False
        mco_agent = EnmPreCheckAgent(timeout=self.CMD_TIMEOUT)
        for rpm in rpms:
            if rpm['last_operation'] != "nothing":
                rpm_name = re.search(r'^ERIC\w*', rpm['before_rpm_name'])\
                    .group()
                self.logger.info("Beginning Rollback of package {0}"
                                 .format(rpm_name))
                version_regex = r'(\d+)\.(\d+)\.(\d+)'
                host = rpm['host']

                rpm_info = self.get_installed_rpm_info(rpm_name, host,
                                                       mco_agent)
                if not rpm_info:
                    failure = True
                    continue

                installed_version = re.search(version_regex, rpm_info)
                installed_version_str = installed_version.group()
                self.logger.info("Package {0} version {1} installed on {2}"
                                 .format(rpm_name, installed_version_str,
                                         host))

                if rpm['last_operation'] == "install":  # remove
                    if not self.remove_rpm_from_host(rpm_name, host,
                                                     mco_agent):
                        failure = True
                        continue
                    self.logger.info("{0} removed from host {1}"
                                     .format(rpm_name, host))

                elif rpm['last_operation'] == "upgrade":  # downgrade
                    before_version = re.search(version_regex,
                                               rpm['before_rpm_name'])
                    before_version_str = before_version.group()
                    result = compare_versions(before_version_str,
                                              installed_version_str)
                    if result == "equal":
                        self.logger.info("Rollback of package {0} to "
                                         "version {1} has already "
                                         "been completed, skipping.."
                                         .format(rpm_name,
                                                 before_version_str))
                        failure = True
                        continue

                    #  check for rollback rpm in /var/www/html/
                    old_package_name = None
                    paths = find_if_file_in_path(rpm_name, '/var/www/html/')
                    for path in paths:
                        if before_version_str in path:
                            old_package_name = path
                            break

                    moved_rpm = False
                    regex = r'.*/(.*.rpm)'
                    #  if not there check if yum has it cached
                    if not old_package_name and self.ms_name == host:
                        available_versions_strs = self.\
                            check_if_version_in_yum(mco_agent, host, rpm_name)
                        if before_version_str not in \
                                available_versions_strs:
                            self.logger.warning("Rollback version {0} not"
                                                " available for package {1}"
                                                ", please rollback manually.."
                                                .format(before_version_str,
                                                        rpm_name))
                            failure = True
                            continue
                        old_package_name = rpm_name + before_version_str
                    elif old_package_name and self.ms_name != host:
                        extenstion = re.match(regex,
                                              old_package_name).group(1)
                        rpm_nas_path = '{0}/{1}'.format('/ericsson/enm/dumps',
                                                        extenstion)
                        copy_file(old_package_name, rpm_nas_path)
                        old_package_name = rpm_nas_path
                        moved_rpm = True

                    if self.ms_name != host:
                        if not old_package_name:
                            self.logger.warning("Rollback version {0} not"
                                                " available for package {1}"
                                                ", please rollback manually.."
                                                .format(before_version_str,
                                                        rpm_name))
                            failure = True
                            continue
                        success = self.remove_rpm_from_host(re.match
                                                            (regex,
                                                             old_package_name)
                                                            .group(1)
                                                            .split('-')[0],
                                                            host, mco_agent)
                        if not success:
                            self.logger.error("Failed to roll back package {0}"
                                              " from version {1} to {2} on "
                                              "host {3}, please rollback"
                                              " manually"
                                              .format(rpm_name,
                                                      installed_version_str,
                                                      before_version_str,
                                                      host))
                            failure = True
                            continue

                        success = self.install_rpm_on_host(old_package_name,
                                                           host, mco_agent)

                    elif 'litp' in rpm_name:
                        success = self.modify_litp_package(result,
                            old_package_name, host, mco_agent)
                    elif result == "bigger":
                        success = self.upgrade_rpm_on_host(
                            old_package_name, host, mco_agent)
                    else:
                        success = self.downgrade_rpm_on_host(old_package_name,
                                                             host, mco_agent)

                    if moved_rpm:
                        delete_file(old_package_name)

                    if not success:
                        is_rolled_back = self.check_old_rpm_vs_rollback_rpm(
                            rpm_name, old_package_name)
                        if is_rolled_back:
                            self.logger.warning("rollback of {0} on LMS has"
                                                " timed out but the RPM "
                                                "has downgraded"
                                                " successfully."
                                                .format(rpm_name))
                        else:
                            self.logger.error("Failed to roll back"
                                              "package {0}"
                                              " from version {1} to"
                                              " {2} on host "
                                              "{3}, please rollback manually"
                                              .format(rpm_name,
                                                      installed_version_str,
                                                      before_version_str,
                                                      host))
                            failure = True
                            continue

                    self.logger.info("Package {0} has been rolled back from"
                                     " version {1} to {2}"
                                     .format(rpm_name,
                                             installed_version_str,
                                             before_version_str))
                if 'litp' in rpm_name:
                    self.logger.info("Running puppet agent on all nodes")
                    h_puppet.puppet_runall()

        if not failure:
            os.remove(RPM_UPGRADE_INFO_FILE)


def find_if_file_in_path(file_name, path):
    """
    Find if file exists in path and children of path
    :param file_name: nae of file we're looking for
    :param path: path to look for it
    :return results: list of paths with file
    """
    results = []
    for root, _, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, '*' + file_name + '*'):
                results.append(os.path.join(root, name))
    return results


def parse_args(args, logger):
    """
    Checks the arguments are supported
    :param args: the args
    :param logger: a logger
    """
    # process arguements
    this_script = 'rollback_upgrade_rpms.py'
    usage_info = ('Rollback packages that were upgraded .\n' +
                  'Example: ./{0} [-h]').format(this_script)
    parser = ArgumentParser(prog=this_script,
                            usage='{0}'.format(this_script),
                            formatter_class=RawDescriptionHelpFormatter,
                            epilog=usage_info, add_help=False)

    optional_group = parser.add_argument_group('optional arguments')

    optional_group.add_argument('-h', '--help',
                                action='help',
                                help='Show this help message and exit')
    parser.parse_args(args)
    if len(args) != 0:
        logger.error("Incorrect arguments, use -h to see usage")
        sys.exit(1)


def main(args):
    """
    Main application function
    :param args: arguments to be processed
    """
    rb_rpms = RollbackUpgradeRpm()
    parse_args(args, rb_rpms.logger)
    rb_rpms.get_rpm_data(rb_rpms.rpm_info_path)
    rb_rpms.rollback_upgraded_rpms(rb_rpms.rpm_data_list)


if __name__ == '__main__':
    CL_ARGS = sys.argv[1:]
    main(CL_ARGS)
