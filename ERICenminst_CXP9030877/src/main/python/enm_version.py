"""
ENM Version handling
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


import logging
from argparse import ArgumentParser
from os.path import exists
from urlparse import urlparse

import sys

import import_iso_version
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import main_exceptions
from h_litp.litp_maintenance import LitpMaintenance
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_util.h_utils import exec_process, exec_process_via_pipes, ExitCodes, \
    get_env_var
from import_iso_version import ENM_VERSION_FILENAME, ENM_HISTORY_FILENAME, \
    LITP_RELEASE_FILENAME, LITP_HISTORY_FILENAME

LITP_VERSION_ALL_CMD = '/usr/bin/litp version --all'

REPOSITORY_PATH_BASE = '/var/www/html/'

ENMINST_CONF_ENV_VARIABLE = 'ENMINST_CONF'

KEY_ITEM_TYPE_NAME = 'item-type-name'
KEY_MS_URL_PATH = 'ms_url_path'
KEY_PROPERTIES = 'properties'
KEY_BASE_URL = 'base_url'
KEY_NAME = 'name'

ITEM_TYPE_NAME_VALUE_PACKAGE = 'package'
ITEM_TYPE_NAME_VALUE_PACKAGE_LIST = 'package-list'
ITEM_TYPE_NAME_VALUE_VM_SERVICE = 'vm-service'
ITEM_TYPE_NAME_VALUE_YUM_REPOSITORY = 'yum-repository'
ITEM_TYPE_NAME_VALUE_VM_YUM_REPO = 'vm-yum-repo'

DEFAULT_INDENTATION = '    '
ENM_PRODUCT_VERSIONS_LABEL = "ENM product versions :"
TEMPLATE_LTIP_VERSION = 'LITP versions :'
ENM_SOFTWARE_PACKAGES_LABEL = 'ENM Software packages :'
VM_SERVICES_LABEL = 'ENM VM services :'

NOT_AVAILABLE_LABEL = "Not available"
LITP_RELEASE_INFO_LABEL = "LITP Release info     :"
LITP_HISTORY_INFO_LABEL = "LITP History info     :"
RHEL79_VERSION_INFO_LABEL = "RHEL79 Release info    :"
RHEL79_HISTORY_INFO_LABEL = "RHEL79 History info    :"
RHEL88_VERSION_INFO_LABEL = "RHEL88 Release info    :"
RHEL88_HISTORY_INFO_LABEL = "RHEL88 History info    :"
ENM_VERSION_INFO_LABEL = "ENM Version info      :"
ENM_HISTORY_INFO_LABEL = "ENM History info      :"
FAILED_TO_DISPLAY_LITP_VERSION_LABEL = 'Failed to display litp versions.'
LABEL_NONE = "None"

MAINTENANCE_MODE = "Could not display versions of ENM base software " \
                   "packages and vm packages - LITP is in maintenance mode"

SOFTWARE_ITEMS_PATH = '/software/items'
SOFTWARE_SERVICES_PATH = '/software/services'

SOFTWARE_ITEMS_PACKAGES_TEMPLATE = SOFTWARE_ITEMS_PATH + '/{0}/packages'
SOFTWARE_SERVICES_VM_PACKAGES_TEMPLATE = SOFTWARE_SERVICES_PATH + \
                                         '/{0}/vm_packages'
SOFTWARE_SERVICES_VM_YUM_REPOS_TEMPLATE = SOFTWARE_SERVICES_PATH + \
                                          '/{0}/vm_yum_repos'

VM_SERVICE_TEMPLATE = DEFAULT_INDENTATION + 'VM service : {0} '
VM_SERVICE_PACKAGE_TEMPLATE = DEFAULT_INDENTATION * 2 \
                              + 'vm-package : '
VM_SERVICE_PACKAGE_DEPENDENCIES_TEMPLATE = DEFAULT_INDENTATION * 2 \
                                           + 'dependencies :'
VM_SERVICE_PACKAGE_DEPENDENCIES_NONE_TEMPLATE = \
    VM_SERVICE_PACKAGE_DEPENDENCIES_TEMPLATE + ' ' + LABEL_NONE

REPOQUERY_TAG_NAME = 'name'
REPOQUERY_TAG_VERSION = 'version'
REPOQUERY_TAG_PACKAGER = 'packager'
REPOQUERY_TAG_URL = 'url'
REPOQUERY_TAG_REQUIRES = 'requires'

REPOQUERY_PKG_INFO_TAGS = [REPOQUERY_TAG_NAME, REPOQUERY_TAG_VERSION,
                           REPOQUERY_TAG_PACKAGER, REPOQUERY_TAG_URL]

RHEL79_VERSION_FILENAME = '/etc/rhel79_patch_set-version'
RHEL79_HISTORY_FILENAME = '/etc/rhel79_patch_set-history'
RHEL88_VERSION_FILENAME = '/etc/rhel88_patch_set-version'
RHEL88_HISTORY_FILENAME = '/etc/rhel88_patch_set-history'


class ENMVersion(object):  # pylint: disable=R0904
    """
    Display version of ENM. Show versions of packages managed by LITP2.
    Uses LITP2 Rest API to retrieve list of managed packages.
    Uses yum API to retrieve details of packages.
    """
    RSTATE_ACCEPTED_URLS = set(['www.ericsson.com'])

    def __init__(self, litpd_host='localhost',
                 litpd_port=LitpRestClient.DEFAULT_LITPD_PORT,
                 logger_name='enmversion'):
        """
        Initializes logging, configures litp REST client and creates yum
        object used to query repositories
        :param litpd_host: address of litp service
        :param litpd_port: port of litp service
        """

        self.log = logging.getLogger(logger_name)
        self.litpd_host = litpd_host
        self.litpd_port = litpd_port
        self.litp = LitpRestClient(litpd_host=self.litpd_host,
                                   litpd_port=self.litpd_port)

        self.repoquery_repos = {}
        self.all_available_repo_pkg_info = {}

    @staticmethod
    def get_package_name_from_package_structure(  # pylint: disable=C0103
                                                item):
        """Retrieves name of package from JSON structure
        :param item: package JSON structure
        :return package name
        """
        properties = item[KEY_PROPERTIES]
        package_name = properties['name']
        return package_name

    def get_package_names_from_package_list_structure(  # pylint: disable=C0103
            self, item):
        """Retrieves names of packages from JSON structure
        :param item: package-list JSON structure
        :return: list of package names
        """
        package_names = []
        package_list_id = item['id']
        package_list_path = SOFTWARE_ITEMS_PACKAGES_TEMPLATE.format(
                package_list_id)
        soft_list = self.litp.get_children(package_list_path)
        for model_package in soft_list:
            data = model_package['data']
            package_names.append(self.get_package_name_from_package_structure(
                data))
        return package_names

    def collect_base_packages_names(self):
        """Collects names of packages from base software collection managed by
        LITP. Handle item-type-name like package, package derivatives
        and package-list.
        :return: list of package names
        """
        package_names = []
        software_items = self.litp.get_children(SOFTWARE_ITEMS_PATH)
        for items_element in software_items:
            item = items_element['data']
            item_type_name = item[KEY_ITEM_TYPE_NAME]
            if item_type_name == ITEM_TYPE_NAME_VALUE_PACKAGE_LIST:
                package_names.extend(
                    self.get_package_names_from_package_list_structure(item))
            elif ITEM_TYPE_NAME_VALUE_PACKAGE in item_type_name:
                package_names.append(
                    self.get_package_name_from_package_structure(item))
        return package_names

    def display_packages_info(self, package_names, prefix='  ', postfix=''):
        """Displays details of rpm packages using cached information
        :param package_names: list of package names
        :param prefix: text to be appended before package info
        :param postfix: text to be appended after package info
        """
        sorted_package_names = sorted(package_names)
        for pkg_name in sorted_package_names:
            version, packager, url = self.all_available_repo_pkg_info[pkg_name]
            rstate = ''
            if url in ENMVersion.RSTATE_ACCEPTED_URLS:
                rstate = packager

            product_number = ''
            product_code_parts = pkg_name.split('_')
            if len(product_code_parts) > 1:
                product_number = product_code_parts[1]

            self.log.info("{0}{1} {2} {3} {4} {5}".format(
                    prefix, pkg_name, version, product_number,
                    rstate, postfix))

    def filter_dependencies_to_packages(self, dependency_names):
        """Filters dependencies to keep only valid package names
        :param dependency_names: list of package dependencies
        :return: list of valid package names
        """
        package_names = [rpm_name for rpm_name in
                         self.all_available_repo_pkg_info
                         if rpm_name in dependency_names]
        return package_names

    def get_vm_package_names(self, item):
        """Retrieves name of vm package name from JSON structure
        :param item: JSON structure to inspect
        :return: vm package name
        """
        vm_service_id = item['id']
        package_list_path = SOFTWARE_SERVICES_VM_PACKAGES_TEMPLATE.format(
                vm_service_id)
        vm_packages_elements = self.litp.get_children(package_list_path)
        results = []
        for element in vm_packages_elements:
            data = element['data']
            properties = data['properties']
            vm_package_name = properties['name']
            results.append(vm_package_name)
        return results

    def collect_all_vm_packages_struct(self):
        """Collects all VM packages dictionary mapping VM service Id to
        a list of packages defined for given VM
        :return: dictionary mapping VM service Id to a list of packages
        """
        all_vm_packages = {}
        service_items = self.litp.get_children(SOFTWARE_SERVICES_PATH)
        for service_item in service_items:
            item = service_item['data']
            item_type_name = item[KEY_ITEM_TYPE_NAME]
            if item_type_name == ITEM_TYPE_NAME_VALUE_VM_SERVICE:
                vm_package_names = self. get_vm_package_names(item)
                vm_service_id = item['id']
                all_vm_packages[vm_service_id] = vm_package_names

        return all_vm_packages

    def collect_vm_service_names(self):
        """Collects names of VM services managed by LITP
        :return: list of VM service names
        """
        vm_service_names = []
        service_items = self.litp.get_children(SOFTWARE_SERVICES_PATH)
        for service_item in service_items:
            item = service_item['data']
            item_type_name = item[KEY_ITEM_TYPE_NAME]
            if item_type_name == ITEM_TYPE_NAME_VALUE_VM_SERVICE:
                vm_service_id = item['id']
                vm_service_names.append(vm_service_id)
        return vm_service_names

    def display_vm_packages_info(self, all_vm_packages,
                                 vm_packages_dependencies):
        """Displays list of all VM services and its VM packages.
        For each VM package display its direct package dependencies
        :param all_vm_packages: dictionary mapping vm service name to list
        of main packages defining VM
        :param vm_packages_dependencies: dictionary mapping package name to
        the list of its dependencies
        """
        sorted_vm_service_names = sorted(all_vm_packages.keys())
        for vm_service_id in sorted_vm_service_names:

            self.log.info(VM_SERVICE_TEMPLATE.format(vm_service_id))

            vm_package_names = all_vm_packages[vm_service_id]

            sorted_vm_package_names = sorted(vm_package_names)

            for vm_package_name in sorted_vm_package_names:
                self.display_packages_info(
                    [vm_package_name],
                    VM_SERVICE_PACKAGE_TEMPLATE)
                self.log.info('')
                dependencies = vm_packages_dependencies[vm_package_name]

                filtered_pkgs = self.filter_dependencies_to_packages(
                    dependencies)

                if filtered_pkgs:
                    self.log.info(VM_SERVICE_PACKAGE_DEPENDENCIES_TEMPLATE)
                    self.display_packages_info(filtered_pkgs,
                                               DEFAULT_INDENTATION * 3)
                else:
                    self.log.info(
                        VM_SERVICE_PACKAGE_DEPENDENCIES_NONE_TEMPLATE)
                self.log.info('')

    def find_current_repos(self):
        """Find list of current repos registered in yum
        :return: list of repo names allready registered in yum
        """
        try:
            command_parts_repolist_verbose = ['/usr/bin/yum', '-v', 'repolist']
            command_parts_grep_repo_id = ['/bin/grep', 'Repo-id']
            stdout = exec_process_via_pipes(command_parts_repolist_verbose,
                                            command_parts_grep_repo_id)
            current_repos = []
            for line in stdout.splitlines():
                parts = line.split(':')
                if len(parts) == 2:
                    repo_name = parts[1].strip()
                    current_repos.append(repo_name)
            self.log.debug('current repos {0} '.format(current_repos))
            return current_repos
        except IOError:
            self.log.exception("Unable to query repo {0}"
                               .format(self.repoquery_repos.keys()))
            raise SystemExit(ExitCodes.ERROR)

    def collect_repoquery_repos(self, vm_service_names):
        """Constructs dictionary mapping repo name to path where given repo
        stores its packages on MS node.
        Retrieves repo information from software items
        and software services structures in LITP model
        :param vm_service_names: list of vm service names
        :return: dictionary mapping repo name to the path
        """
        current_repos = self.find_current_repos()
        repositories = {}
        self.add_repos_software_items(current_repos, repositories)
        self.add_repos_software_services(vm_service_names, current_repos,
                                         repositories)
        return repositories

    def add_repos_software_items(self, current_repos, repositories):
        """Adds names of repo's defined by software items definition
        managed by LITP. Skip names defined in current_repos list
        :param current_repos: list of currently enabled repos
        :param repositories: structure to store discovered repositories
        """
        software_items = self.litp.get_children(SOFTWARE_ITEMS_PATH)
        for items_element in software_items:
            item = items_element['data']
            item_type_name = item[KEY_ITEM_TYPE_NAME]
            if ITEM_TYPE_NAME_VALUE_YUM_REPOSITORY == item_type_name:
                properties = item[KEY_PROPERTIES]
                ms_url_path = properties[KEY_MS_URL_PATH]
                repo_name = ms_url_path.strip('/')
                if repo_name not in current_repos:
                    repositories[repo_name] = REPOSITORY_PATH_BASE + repo_name

    def add_repos_software_services(self, vm_service_names, current_repos,
                                    repositories):
        """Adds names of repo's defined by software services definition
        managed by LITP. Skip names defined in current_repos list
        :param current_repos: list of currently enabled repos
        :param vm_service_names: list of all VM services
        :param current_repos: list of currently enabled repos
        :param repositories: structure to store discovered repositories
        """

        for vm_name in vm_service_names:
            vm_yum_items = self.litp.get_children(
                    SOFTWARE_SERVICES_VM_YUM_REPOS_TEMPLATE.format(vm_name))
            for items_element in vm_yum_items:
                item = items_element['data']
                item_type_name = item[KEY_ITEM_TYPE_NAME]
                if ITEM_TYPE_NAME_VALUE_VM_YUM_REPO == item_type_name:
                    properties = item[KEY_PROPERTIES]
                    base_url_property = properties[KEY_BASE_URL]
                    base_url = urlparse(base_url_property)
                    repo_path = base_url.path.strip('/')
                    repo_name = properties[KEY_NAME]
                    if repo_name not in current_repos:
                        repositories[repo_name] = \
                            REPOSITORY_PATH_BASE + repo_path

    def extract_pkg_info(self, stdout):
        """Extracts from stdout parts of rpm package information based on
        custom format of repoquery output
        :param stdout: text to parse
        :return: dictionary mapping package name to tuple of attributes
        """
        result = {}
        lines = stdout.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.strip() == "":
                index += 1
                continue

            tag_value_dict = {}
            for tag_name in REPOQUERY_PKG_INFO_TAGS:
                if index >= len(lines):
                    raise ValueError('Missing line for tag \'{0}\' '.format(
                            tag_name))

                tag_value_dict[tag_name] = self.__extract_tag_value(
                        lines[index], tag_name)
                index += 1

            name = tag_value_dict[REPOQUERY_TAG_NAME]
            version = tag_value_dict[REPOQUERY_TAG_VERSION]
            packager = tag_value_dict[REPOQUERY_TAG_PACKAGER]
            url = tag_value_dict[REPOQUERY_TAG_URL]
            if name not in result:
                result[name] = (version, packager, url)

        return result

    @staticmethod
    def __extract_tag_value(line, tag):
        """Checks if line starts with given tag and then
        extracts its value separated by = character
        :param line: line to process
        :param tag: text to be expected at the beginning of line
        :return: value for tag from selected line
        """
        if line.startswith(tag):
            separator_index = line.find('=')
            if separator_index == -1:
                raise \
                    ValueError('Line \'{0}\'" do not define '
                               'value for attribute {1}'.format(line, tag))
            else:
                value = line[separator_index + 1:]
                return value
        else:
            raise ValueError('Line \'{0}\'" do not define attribute {1}'
                             .format(line, tag))

    def get_all_available_pkg_info(self):
        """Query external repositories to cache pkg info
        :return: dictionary mapping package name to tuple of attributes
        """
        command_parts = self.build_repoquery_commnd_parts()

        command_parts.append('-a')
        command_parts.append('--qf')

        query_format = ''
        for tag_name in REPOQUERY_PKG_INFO_TAGS:
            query_format += self.query_format_for_tag(tag_name)

        command_parts.append(query_format)
        stdout = self.process_repoquery(command_parts)
        return self.extract_pkg_info(stdout)

    @staticmethod
    def query_format_for_tag(tag_name):
        """Build  style query format for tag
        :param tag_name: name of the tag
        :return: string - extended queryformat by the new tag
        """
        tag_query_format = tag_name
        tag_query_format += '=%{'
        tag_query_format += tag_name
        tag_query_format += '}\n'
        return tag_query_format

    def build_repoquery_commnd_parts(self):
        """Build first part of repoquery command adding repositories defined
        in the LITP model
        :return: list of command parts
        """
        command_parts = ['/usr/bin/repoquery']
        for repo_id in self.repoquery_repos:
            repofrompath = "--repofrompath={0},{1}"\
                .format(repo_id, self.repoquery_repos[repo_id])
            command_parts.append(repofrompath)
        return command_parts

    def process_repoquery(self, command_parts):
        """Execute repoquery process
        :param command_parts: array of arguments to build command line
        :return: string containing standard output
        """
        try:
            stdout = exec_process(command_parts)
        except IOError:
            self.log.error("Unable to query repos {0}".
                           format(self.repoquery_repos.keys()))
            raise SystemExit(ExitCodes.ERROR)
        return stdout

    def get_vm_packages_dependencies(self, all_vm_packages):
        """Collects dependencies for vm packges names using repoquery API
        :param all_vm_packages: dictionary mapping VM service name to
        a list of all VM package names
        :return dictionary mapping name of service group package
        to its dependencies
        """
        command_parts = self.build_repoquery_commnd_parts()

        command_parts.append('-a')
        command_parts.append('--qf')
        query_format = REPOQUERY_TAG_NAME + ':'
        query_format += '%{' + REPOQUERY_TAG_NAME + '}\n'
        query_format += '%{' + REPOQUERY_TAG_REQUIRES + '}\n'
        command_parts.append(query_format)
        for vm_package_names in all_vm_packages.values():
            for package_name in vm_package_names:
                command_parts.append(package_name)

        stdout = self.process_repoquery(command_parts)
        return self.extract_package_dependencies(stdout)

    @staticmethod
    def extract_package_dependencies(stdout):
        """Extracts from stdout package dependencies based on custom format of
        repoquery output
        :param stdout: text to parse
        :return: dictionary mapping package name to list of package
        dependencies
        """
        vm_packages_dependencies = {}
        lines = stdout.splitlines(True)
        index = 0
        while index < len(lines):
            package_line = lines[index].strip()
            index += 1
            if package_line.startswith(REPOQUERY_TAG_NAME):
                package_name = package_line.split(':')[1]
            else:
                continue
            providers = []
            while True and index < len(lines):
                line = lines[index].strip()
                if not line:
                    break
                providers.append(line)
                index += 1
            index += 1
            vm_packages_dependencies[package_name] = providers
        return vm_packages_dependencies

    def display_enm_product_header(self):
        """Displays ENM product header
        """
        self.log.info(ENM_PRODUCT_VERSIONS_LABEL)
        self.log.info("")

    def display_release_info(self, filename, label):
        """ Read content of release info filename
        and displays it next to given label
        :param filename: filename to read the release info
        :param label: label to print
        """
        release_info = self.read_release_info(filename)

        self.log.info(label + " {0}".format(release_info))
        self.log.info('')

    @staticmethod
    def read_release_info(filename):
        """
        Reads relase info from given filename.
        If filename is not existent return message of no availability
        :param filename: filename to read release info
        :return: content of file or specific message
        """
        try:
            with open(filename, 'r') as release_file:
                release_info = release_file.read().strip()
        except IOError:
            release_info = NOT_AVAILABLE_LABEL
        return release_info

    def display_release_history(self,
                                history_filename,
                                version_filename,
                                label):
        """ Read content of release history filename
         and displays its lines. If history contains many entries then
         displays given label only in first line.
         If history file is missing then version filename
         is used to create history info. If also version filename
         is missing then displays message of no availability of history.
        :param history_filename: filename to read the history info
        :param version_filename: path to version filename
        :param label: label to print
        """
        if exists(history_filename):
            release_info = self.read_release_info(history_filename)
        elif exists(version_filename):
            release_info = \
                import_iso_version.create_history_entry(
                    history_filename, version_filename)
        else:
            release_info = NOT_AVAILABLE_LABEL

        history_lines = release_info.splitlines()

        empty_label = " " * len(label)
        displayed_label = False
        for line in history_lines:
            if displayed_label:
                self.log.info(empty_label + " {0}".format(line))
            else:
                self.log.info(label + " {0}".format(line))
                displayed_label = True
        self.log.info('')

    def display_litp_release_info(self):
        """ Displays LITP release info.
        """
        self.display_release_info(
            LITP_RELEASE_FILENAME, LITP_RELEASE_INFO_LABEL)

    def display_rhel79_version_info(self):
        """Displays RHEL 7.9 version info.
        """
        self.display_release_info(
            RHEL79_VERSION_FILENAME, RHEL79_VERSION_INFO_LABEL)

    def display_rhel79_history_info(self):
        """Displays RHEL 7.9 history info.
        """
        self.display_release_history(
            RHEL79_HISTORY_FILENAME,
            RHEL79_VERSION_FILENAME,
            RHEL79_HISTORY_INFO_LABEL)

    def display_rhel88_version_info(self):
        """Displays RHEL 8.8 version info.
        """
        self.display_release_info(
            RHEL88_VERSION_FILENAME, RHEL88_VERSION_INFO_LABEL)

    def display_rhel88_history_info(self):
        """Displays RHEL 8.8 history info.
        """
        self.display_release_history(
            RHEL88_HISTORY_FILENAME,
            RHEL88_VERSION_FILENAME,
            RHEL88_HISTORY_INFO_LABEL)

    def display_enm_version_info(self):
        """Displays ENM version info.
        """
        self.display_release_info(
            ENM_VERSION_FILENAME, ENM_VERSION_INFO_LABEL)

    def display_enm_history_info(self):
        """Displays ENM history info.
        """
        self.display_release_history(
            ENM_HISTORY_FILENAME, ENM_VERSION_FILENAME, ENM_HISTORY_INFO_LABEL)

    def display_litp_version(self):
        """Displays LITP version invoking LITP command.
        """
        self.log.info(TEMPLATE_LTIP_VERSION)
        try:
            stdout = exec_process(LITP_VERSION_ALL_CMD.split()).strip()
        except IOError:
            self.log.exception(FAILED_TO_DISPLAY_LITP_VERSION_LABEL)
            return
        for line in stdout.splitlines():
            self.log.info(DEFAULT_INDENTATION + line.strip())
        self.log.info('')

    def display_litp_history_info(self):
        """Displays LITP history info.
        """
        self.display_release_history(LITP_HISTORY_FILENAME,
                                     LITP_RELEASE_FILENAME,
                                     LITP_HISTORY_INFO_LABEL)

    def check_maintenance_mode(self):
        """
        Checks if LITP is in maintenance mode
        and displays appropriate warning.
        :return True if maintenance mode is enabled, otherwise False
        :rtype bool
        """
        litpmaint = LitpMaintenance(client=self.litp)
        is_maintenance = litpmaint.is_maintenance_mode()
        if is_maintenance:
            self.log.info('')
            self.log.warning(MAINTENANCE_MODE)
            self.log.info('')
        return is_maintenance

    def display_enm_versions(self):
        """Displays versions of base software packages and vm packages and its
        dependencies
        """

        if self.check_maintenance_mode():
            return

        vm_service_names = self.collect_vm_service_names()
        self.repoquery_repos = self.collect_repoquery_repos(vm_service_names)
        self.all_available_repo_pkg_info = self.get_all_available_pkg_info()

        base_package_names = self.collect_base_packages_names()
        all_vm_packages = self.collect_all_vm_packages_struct()
        vm_packages_dependencies = self.get_vm_packages_dependencies(
            all_vm_packages)

        if base_package_names:
            self.log.info(ENM_SOFTWARE_PACKAGES_LABEL)
            self.log.info('')
            filtered_base_pkgs = self.filter_dependencies_to_packages(
                base_package_names)
            self.display_packages_info(filtered_base_pkgs,
                                       DEFAULT_INDENTATION * 1)
            self.log.info('')
        else:
            self.log.info(ENM_SOFTWARE_PACKAGES_LABEL +
                          " " + NOT_AVAILABLE_LABEL)
            self.log.info('')

        if all_vm_packages:
            self.log.info(VM_SERVICES_LABEL)
            self.log.info('')
            self.display_vm_packages_info(all_vm_packages,
                                          vm_packages_dependencies)
        else:
            self.log.info(VM_SERVICES_LABEL + " " + NOT_AVAILABLE_LABEL)
            self.log.info('')

    def display_versions(self):
        """
        Displays all information about LITP and ENM versions
        """
        self.display_enm_product_header()
        self.display_litp_release_info()
        self.display_litp_history_info()
        self.display_litp_version()
        self.display_rhel79_version_info()
        self.display_rhel79_history_info()
        self.display_rhel88_version_info()
        self.display_rhel88_history_info()
        self.display_enm_version_info()
        self.display_enm_history_info()
        self.display_enm_versions()


def display_log_enminst():
    """
    Displays version of ENM using 'enminst' logger name to log messages
    """
    display(logger_name='enminst')


def display(litpd_host=LitpRestClient.DEFAULT_LITPD_HOST,
            logger_name='enmversion'):
    """
    Displays version of ENM
    :param litpd_host: address of LITPD host
    :param logger_name: logger name to be used to log messages
    """
    log = init_enminst_logging(logger_name)
    try:
        log_level = get_env_var('LOG_LEVEL')
        set_logging_level(log, log_level)
    except KeyError:
        pass

    try:
        enmv = ENMVersion(litpd_host=litpd_host, logger_name=logger_name)
        enmv.display_versions()
    except:
        log.exception('Could not display ENM product versions properly')
        raise


def create_parser():
    """Creates and configures command line parser instance
    :return: parser instance
    :rtype: ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument('--litpd_host', dest='litpd_host',
                        default='localhost',
                        help='LITPD host, default is \'localhost\'')
    return parser


# =============================================================================
# Main
# =============================================================================
def main(args):
    """Main function parsing command arguments and displaying versions
    :param args: command line arguments
    :type args: List
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args[1:])
    display(parsed_args.litpd_host)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
