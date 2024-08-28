"""
This script updates ERIClitpsanemc on the LMS and the DB,
as well as installing / upgrading ERICdstutilities and
ERICenmdeploymenttemplates on the LMS.
nodes before kicking off an ENM upgrade.
"""
# pylint: disable=R0903,W0613,W0612,R0201,R0902
##############################################################################
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################

import os
import re
import sys
import yum
import glob
import logging
import import_iso

from distutils.version import LooseVersion
from h_logging.enminst_logger import init_enminst_logging,\
    log_header
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import main_exceptions, get_xml_deployment_file, \
    get_dd_xml_file
from h_puppet.mco_agents import EnmPreCheckAgent, McoAgentException
from h_util.h_utils import install_rpm, copy_file, \
    delete_file, check_package_installed, get_rpm_info, get_rpm_install_size, \
    get_lms_free_space
from h_puppet import h_puppet

NAS_PATH = '/ericsson/enm/dumps'
SAN_PSL_PACKAGE = "ERIClitpsanemc_CXP9030788"
SAN_PSL_PATH = "/litp/plugins/ENM/{0}-*".format(SAN_PSL_PACKAGE)
DST_UTILS_PACKAGE = "ERICdstutilities_CXP9032738"
DST_UTILS_PATH = "/repos/ENM/ms/{0}-*".format(DST_UTILS_PACKAGE)
DEPLOYMENT_TEMPLATES_PACKAGE = "ERICenmdeploymenttemplates_CXP9031758"
DEPLOYMENT_TEMPLATES_PATH = "/repos/ENM/ms/" \
                            "{0}-*".format(DEPLOYMENT_TEMPLATES_PACKAGE)
SAN_PLUGIN_PACKAGE = "ERIClitpsan_CXP9030786"
SAN_PLUGIN_PATH = "/litp/plugins/ENM/{0}-*".format(SAN_PLUGIN_PACKAGE)
HW_COMM_PACKAGE = "ERIChwcomm_CXP9032292"
HW_COMM_PATH = "/repos/ENM/ms/{0}-*".format(HW_COMM_PACKAGE)

init_enminst_logging()
LOGGER = logging.getLogger('enminst')

RPM_UPGRADE_INFO_FILE = "/opt/ericsson/enminst/runtime/pre_upgrade_rpm.info"
VERSION_REGEX = r'\d+\.\d+\.\d+(-SNAPSHOT\d+)*'
RPM_NAME_REGEX = r'ERIC\w+'


class RpmsUpgradedInfo(object):
    """
    Class to handle rpm versions
    """
    def __init__(self, host_name, rpm_info):
        self.host_name = host_name
        self.rpm_name = rpm_info.get("name")
        self.pre_rpm_version = self.format_rpm_version(rpm_info)
        self.post_rpm_version = None
        self.rpm_operation = None

    @staticmethod
    def format_rpm_version(rpm_info):
        """
        Function to handle an RPM version being a snapshot
        :param rpm_info:
        :return: rpm_version containing snapshot or not.
        """
        if "SNAPSHOT" in rpm_info.get("release"):
            return "{0}-{1}".format(rpm_info.get("version"),
                                    rpm_info.get("release"))
        else:
            return rpm_info.get("version")

    def __str__(self):
        return "{0}-{1},{2},{3}-{4},{5}".format(
            self.rpm_name,
            self.pre_rpm_version,
            self.rpm_operation,
            self.rpm_name,
            self.post_rpm_version,
            self.host_name
        )


class PreUpgradeRpm(object):
    """
    Class that handles upgrading RPMs
    """
    RPMS_UPGRADED = False
    UPGRADE_FAILURE = False
    CMD_TIMEOUT = 240

    def __init__(self, enm_iso_path, enm_iso_version):
        self.enm_iso = enm_iso_path
        self.enm_iso_mnt = None
        self.enm_iso_version = LooseVersion(enm_iso_version)
        self.rpms_to_install = []
        self.rpm_info = []
        self.litp_rest = LitpRestClient()
        self.mco_agent = EnmPreCheckAgent(timeout=self.CMD_TIMEOUT)
        self.lms = None
        self.db_cluster = []
        log_header(LOGGER, "Upgrading RPMs.")
        LOGGER.info("Launching pre_upgrade_rpms.sh with argument %s",
                    self.enm_iso)

    def update_rpm_info(self, host, rpm, operation):
        """
        Function that updates the appropriate RpmsUpgradedInfo instance
        with the new RPM version, yum operation performed and host the
        operation was performed on.
        :param host: Name of the host the operation was performed on.
        :param rpm: Full path to the RPM to update.
        :param operation: Yum operation that was performed.
        :return: None
        """
        rpm_info = get_rpm_info(host, rpm_path=rpm)
        rpm_name = rpm_info.get("name")
        LOGGER.info(
            'update_rpm_info: {0} - rpm_name: {1} - opperation: {2} - '\
                'self.rpm_info: {3}'.format(
                    rpm_info, rpm_name, operation, self.rpm_info))
        if "SNAPSHOT" in rpm_info.get("release"):
            new_rpm_version = "{0}-{1}".format(
                rpm_info.get("version"), rpm_info.get("release"))
        else:
            new_rpm_version = rpm_info.get("version")
            LOGGER.info(
                'update_rpm_info new_rpm_version: {0}'.format(new_rpm_version))

        for rpm_info in self.rpm_info:
            if rpm_info.host_name == host and rpm_info.rpm_name == rpm_name:
                rpm_info.rpm_operation = operation
                if operation == "nothing":
                    rpm_info.post_rpm_version = rpm_info.pre_rpm_version
                else:
                    rpm_info.post_rpm_version = new_rpm_version

    def get_installed_rpms_versions(self):
        """
        Function to get the versions of the RPMs installed on the LMS
        and DB nodes.
        If the RPM is not installed it will show the version as None.
        :return: None
        """
        result = ""

        for rpm in self.rpms_to_install:
            rpm_name = re.search(RPM_NAME_REGEX, rpm).group()

            if SAN_PSL_PACKAGE in rpm:
                for db_node in self.db_cluster:
                    host = db_node.properties['hostname']
                    try:
                        LOGGER.info("Querying installed RPM %s on DB %s",
                                    rpm_name, host)
                        mco_result = self.mco_agent.get_package_info(
                            host, rpm_name).split(',')
                        db_version = dict(key_val.split('=')
                                          for key_val in mco_result)
                        self.rpm_info.append(
                            RpmsUpgradedInfo(host, db_version))
                    except McoAgentException:
                        LOGGER.warning("Failed to get info on %s from %s",
                                       rpm_name, host)
                result = get_rpm_info(self.lms, rpm_name=rpm_name)
                self.rpm_info.append(RpmsUpgradedInfo(self.lms, result))
            else:
                if check_package_installed_wrapper(rpm_name):
                    result = get_rpm_info(self.lms, rpm_name)
                    self.rpm_info.append(RpmsUpgradedInfo(self.lms, result))
                else:
                    result = {'release': '1', 'version': None,
                              'name': rpm_name}
                    self.rpm_info.append(RpmsUpgradedInfo(self.lms, result))

    def get_rpms_to_upgrade(self):
        """
        Function to get the RPMs to upgrade from the iso
        and store their path in the rpms_to_install list
        :return: None
        """
        self.enm_iso_mnt = import_iso.create_mnt_dir()
        LOGGER.info("Using mountpoint %s for iso %s",
                    self.enm_iso_mnt, self.enm_iso)
        import_iso.configure_logging(False)
        import_iso.mount(self.enm_iso_mnt, self.enm_iso)

        psl_rpm_path = glob.glob(self.enm_iso_mnt + SAN_PSL_PATH)
        if psl_rpm_path:
            self.rpms_to_install.append(psl_rpm_path[0])

        dst_rpm_path = glob.glob(self.enm_iso_mnt + DST_UTILS_PATH)
        if dst_rpm_path:
            self.rpms_to_install.append(dst_rpm_path[0])

        dep_rpm_path = glob.glob(self.enm_iso_mnt + DEPLOYMENT_TEMPLATES_PATH)
        if dep_rpm_path:
            self.rpms_to_install.append(dep_rpm_path[0])

        san_plugin_rpm_path = glob.glob(self.enm_iso_mnt + SAN_PLUGIN_PATH)
        if san_plugin_rpm_path:
            self.rpms_to_install.append(san_plugin_rpm_path[0])

        hwcomm_plugin_rpm_path = glob.glob(self.enm_iso_mnt + HW_COMM_PATH)
        if hwcomm_plugin_rpm_path:
            self.rpms_to_install.append(hwcomm_plugin_rpm_path[0])

    def check_for_install_space(self):
        """
        Function to check if there is space on the Filesystem
        for the rpms to install.
        :return:
        """
        log_header(LOGGER, "Checking if there's sufficient space "
                           "for rpms to install.")
        total_install_size = 0.0
        old_rpm = 0.0
        try:
            space_available = int(get_lms_free_space())
            for rpm in self.rpms_to_install:
                rpm_name = re.search(RPM_NAME_REGEX, rpm).group()
                if check_package_installed_wrapper(rpm_name):
                    old_rpm = int(get_rpm_install_size(rpm_name=rpm_name))
                rpm_size = int(get_rpm_install_size(rpm_path=rpm))
                print rpm_size
                print old_rpm
                install_diff = rpm_size - old_rpm
                total_install_size += install_diff

            if space_available < total_install_size:
                PreUpgradeRpm.UPGRADE_FAILURE = True
                space_required = round((total_install_size - space_available)
                                       / (1 << 20), 2)
                LOGGER.error("Not enough space to install. "
                             "Free up {0}MB".format(abs(space_required)))
                import_iso.umount(self.enm_iso_mnt)
                raise SystemExit(1)

            LOGGER.info('Sufficient space to install/upgrade RPMs.')

        except IOError as error:
            import_iso.umount(self.enm_iso_mnt)
            LOGGER.error(error)

    def install_rpms(self):
        """
        Function to loop through the RPMs to install and yum
        install or upgrades them.
        It calls a specific function to upgrade the SAN PSL and
        generic functions for other RPMs.
        :return: None
        """
        for rpm in self.rpms_to_install:
            if SAN_PSL_PACKAGE in rpm:
                self.update_san_psl(rpm)
            else:
                self.install_rpm_on_lms(rpm)

        import_iso.umount(self.enm_iso_mnt)
        self.write_rpm_info()
        if self.RPMS_UPGRADED and not self.UPGRADE_FAILURE:
            log_header(LOGGER, "Successfully upgraded RPMs.")
        elif not self.RPMS_UPGRADED and not self.UPGRADE_FAILURE:
            log_header(LOGGER, "No RPMs to upgrade.")
        else:
            log_header(LOGGER, "Failure upgrading RPMs.")
            raise SystemExit(1)

    def update_san_psl(self, rpm):
        """
        Function to upgrade the SAN PSL on the LMS and DB nodes,
        without updating the yum repo.
        The function copies the PSL on to a NAS share and installs
        in on the DB nodes and LMS before deleting it from the share.
        :param rpm: Full path of the RPM to install
        :return: None
        """
        LOGGER.info("Entering update_san_psl")
        result = ""

        # Put SAN PSL RPM onto NAS
        rpm_nas_path = '{0}/{1}'.format(NAS_PATH, os.path.basename(rpm))
        copy_file(rpm, rpm_nas_path)

        # Upgrade SAN PSL on DB Nodes
        for db_node in self.db_cluster:
            host = db_node.properties['hostname']
            LOGGER.info("Upgrading ERIClitpsanemc on DB %s.", host)
            try:
                result = self.mco_agent.upgrade_packages(host, rpm_nas_path)
            except McoAgentException:
                LOGGER.error("Failed to upgrade %s on DB %s",
                             "ERIClitpsanemc", host)
                PreUpgradeRpm.UPGRADE_FAILURE = True
                return

            if 'does not update installed package' in result:
                LOGGER.info("ERIClitpsanemc did not need upgrading on DB %s.",
                            host)
                self.update_rpm_info(host, rpm, "nothing")
            else:
                LOGGER.info("ERIClitpsanemc was upgraded on DB %s.", host)
                PreUpgradeRpm.RPMS_UPGRADED = True
                self.update_rpm_info(host, rpm, "upgrade")

        # Upgrade SAN PSL on LMS
        LOGGER.info("Upgrading ERIClitpsanemc on LMS %s.", self.lms)
        try:
            h_puppet.check_for_puppet_catalog_run()
            LOGGER.info("Disabling puppet agent on all nodes.")
            h_puppet.puppet_enable_disable(state='disable')
            result = self.mco_agent.upgrade_packages(self.lms, rpm_nas_path)
            LOGGER.info("Enabling puppet agent on all nodes.")
            h_puppet.puppet_enable_disable(state='enable')
        except McoAgentException:
            LOGGER.error("Failed to upgrade %s on LMS %s.",
                         "ERIClitpsanemc", self.lms)
            PreUpgradeRpm.UPGRADE_FAILURE = True
            return

        if 'does not update installed package' in result:
            LOGGER.info("ERIClitpsanemc did not need upgrading on LMS %s.",
                        self.lms)
            self.update_rpm_info(self.lms, rpm, "nothing")
        else:
            LOGGER.info("ERIClitpsanemc was upgraded on LMS %s.", self.lms)
            PreUpgradeRpm.RPMS_UPGRADED = True
            self.update_rpm_info(self.lms, rpm, "upgrade")
            LOGGER.info("Running puppet agent on all nodes.")
            h_puppet.puppet_runall()

        # Clean Up
        delete_file(rpm_nas_path)

    def install_rpm_on_lms(self, rpm):
        """
        Function to install an RPM on the LMS.
        It checks if the RPM is already installed and if it is,
        attempts to yum upgrade the RPM.
        :param rpm: Full path of the RPM to install
        :return: None
        """
        rpm_name = re.search(RPM_NAME_REGEX, rpm).group()

        LOGGER.info("Attempting to install %s on the LMS %s.",
                    rpm_name, self.lms)

        if check_package_installed_wrapper(rpm_name):
            LOGGER.info("%s is already installed, "
                        "attempting to upgrade.", rpm_name)
            self.upgrade_rpm_on_lms(rpm_name, rpm)
        else:
            LOGGER.info("Installing %s on LMS %s.", rpm_name, self.lms)
            self.install_rpm_wrapper(rpm_name, rpm, self.lms)
            PreUpgradeRpm.RPMS_UPGRADED = True

    def upgrade_rpm_on_lms(self, rpm_name, rpm_path):
        """
        Function to upgrade an RPM that already exists on the LMS.
        It uses the MCO agent to upgrade the RPM on the LMS.
        :param rpm_name: RPM name without version
        :param rpm_path: Full path of the RPM to install
        :return: None
        """
        result = ""

        LOGGER.info("Upgrading %s on LMS %s.", rpm_name, self.lms)

        if rpm_name in [SAN_PLUGIN_PACKAGE, HW_COMM_PACKAGE]:
            h_puppet.check_for_puppet_catalog_run()
        try:
            if rpm_name == SAN_PLUGIN_PACKAGE:
                LOGGER.info("Disabling puppet agent on all nodes.")
                h_puppet.puppet_enable_disable(state='disable')
                result = self.mco_agent.upgrade_packages(self.lms, rpm_path)
                LOGGER.info("Enabling puppet agent on all nodes.")
                h_puppet.puppet_enable_disable(state='enable')
                LOGGER.info(
                    'Mco Agent Upgrade Packages Result: {0}'.format(result))
            else:
                result = self.mco_agent.upgrade_packages(self.lms, rpm_path)
                LOGGER.info(
                    'Mco Agent Upgrade Packages Result: {0}'.format(result))
        except McoAgentException, exc:
            LOGGER.error(exc)

            rpm_to_upgrade_info = rpm_path.split('/')
            rpm_to_upgrade = rpm_to_upgrade_info[-1]

            #Get the version of the RPM thats installed
            installed_rpm_info = get_rpm_info(self.lms, rpm_name=rpm_name)
            LOGGER.info(
                'Installed RPM Info: {0}'.format(installed_rpm_info))
            installed_rpm = installed_rpm_info.get('name') + '-' + \
                installed_rpm_info.get('version') + ".rpm"

            if installed_rpm == rpm_to_upgrade:
                LOGGER.info("Upgrading %s on LMS has timed out but the RPM \
                    has upgraded successfully.", rpm_name)
                PreUpgradeRpm.RPMS_UPGRADED = True
            else:
                LOGGER.error("Failed to upgrade %s on LMS %s",
                         rpm_name, self.lms)
                PreUpgradeRpm.UPGRADE_FAILURE = True
                return

        if 'does not update installed package' in result:
            LOGGER.info("%s did not need upgrading on LMS %s.",
                        rpm_name, self.lms)
            self.update_rpm_info(self.lms, rpm_path, "nothing")
        else:
            LOGGER.info("%s was upgraded on LMS %s.", rpm_name, self.lms)
            self.update_rpm_info(self.lms, rpm_path, "upgrade")
            PreUpgradeRpm.RPMS_UPGRADED = True
            if rpm_name == SAN_PLUGIN_PACKAGE:
                LOGGER.info("Running puppet agent on all nodes.")
                h_puppet.puppet_runall()

    def install_rpm_wrapper(self, rpm_name, rpm, lms):
        """
        Wrapper function to redirect stdout to dev null when calling
        install_rpm from h_utils.
        :param rpm_name:
        :param rpm:
        :param lms:
        :return:
        """
        redirect_stdout_to_null(True)
        try:
            install_rpm(rpm_name, rpm)
            self.update_rpm_info(lms, rpm, "install")
        except yum.Errors.InstallError:
            LOGGER.error("Failed to install %s on LMS %s", rpm_name, lms)
            PreUpgradeRpm.UPGRADE_FAILURE = True
        redirect_stdout_to_null(False)

    def write_rpm_info(self):
        """
        Function that writes the rpm upgrade info to a file
        for use in automated rollback.
        :return: None
        """
        iso_version = "0.0.0"
        file_exists = True
        enm_iso_version = re.search(VERSION_REGEX, self.enm_iso).group()
        #  Get installed version of ENM iso
        if os.path.exists(RPM_UPGRADE_INFO_FILE):
            with open(RPM_UPGRADE_INFO_FILE) as rpm_info_file:
                iso_versions = rpm_info_file.readline().strip().split(',')
                iso_version = iso_versions[1]
        else:
            file_exists = False

        old_enm_iso_version = LooseVersion(iso_version)

        if not file_exists:
            with open(RPM_UPGRADE_INFO_FILE, 'w') as rpm_info_file:
                rpm_info_file.write("{0},{1}".format(None, enm_iso_version))
                rpm_info_file.write("\n")

                for info in self.rpm_info:
                    rpm_info_file.write(str(info))
                    rpm_info_file.write("\n")
        elif (self.enm_iso_version > old_enm_iso_version) \
                and self.RPMS_UPGRADED:
            with open(RPM_UPGRADE_INFO_FILE, 'w') as rpm_info_file:
                rpm_info_file.write("{0},{1}".format(old_enm_iso_version,
                                                     enm_iso_version))
                rpm_info_file.write("\n")

                for info in self.rpm_info:
                    rpm_info_file.write(str(info))
                    rpm_info_file.write("\n")

    def get_model_info(self):
        """
        Function that fetch data from litp to set values to model variables
        :return: None
        """
        self.lms = self.litp_rest.get_lms().properties.get('hostname')
        self.db_cluster = self.litp_rest.get_cluster_nodes() \
            .get('db_cluster').values()


def redirect_stdout_to_null(redirect_output):
    """
    Function that redirects standard output to dev null
    in order to reduce the number of yum logs.
    :param redirect_output: Boolean flag to toggle redirect.
    :return: None
    """
    if redirect_output:
        sys.stdout = open(os.devnull, 'w')
    else:
        sys.stdout = sys.__stdout__


def check_package_installed_wrapper(rpm_name):
    """
    Wrapper function to redirect stdout to dev null when calling
    check_package_installed from h_utils.
    :param rpm_name: Name of the RPM to check if it is installed.
    :return: A boolean identifying if the RPM is installed or not.
    """
    redirect_stdout_to_null(True)
    rpm_installed = check_package_installed(rpm_name)
    redirect_stdout_to_null(False)

    return rpm_installed


def validate_iso_from_args(args):
    """
    Function to validate that the ENM iso passed to the
    script is the correct format and exists.
    :param args: arguments to be processed
    :return: A string containing the ENM iso path.
    """
    enm_iso = str(args[1])
    if enm_iso.endswith(".iso") and os.path.isfile(enm_iso):
        return enm_iso
    else:
        LOGGER.error("Media passed must exist and be in .iso format.")
        raise SystemExit(1)


def copy_over_xml_dd_file():
    """
    Function to copy over the current Deployment Description file,
    before the deploymentTemplates file gets overwritten.
    :return:
    """
    dd_path = get_dd_xml_file()
    if not dd_path:
        dd_path = get_xml_deployment_file()
    if not dd_path.startswith('/tmp'):
        copy_file(dd_path, '/tmp')


def main(args):
    """
    Main application function
    :param args: arguments to be processed
    """
    if len(args) is 2:
        enm_iso = validate_iso_from_args(args)
        copy_over_xml_dd_file()

        if enm_iso:
            iso_version = re.search(VERSION_REGEX, enm_iso).group()
            pre_upgrade_rpms = PreUpgradeRpm(enm_iso, iso_version)
            pre_upgrade_rpms.get_model_info()
            pre_upgrade_rpms.get_rpms_to_upgrade()
            pre_upgrade_rpms.check_for_install_space()
            pre_upgrade_rpms.get_installed_rpms_versions()
            pre_upgrade_rpms.install_rpms()
    else:
        LOGGER.error("Invalid number of arguments passed. This "
                     "script only accepts the ENM iso as an argument.")
        raise SystemExit(1)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
