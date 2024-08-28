# pylint: disable=C0302
"""
The purpose of this script is to cleanup various aspects
of the deployment and allow the LMS to return to a clean
basic state.
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2021 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : deployment_teardown.py
# Purpose : The purpose of this script is to cleanup various aspects
# of the deployment and allow the LMS to return to a clean
# basic state.
# ********************************************************************
import logging
import time
import os
import glob
from ConfigParser import SafeConfigParser
from re import match
import shutil
import socket
import sys
from optparse import OptionParser
from os.path import isfile, basename, join
from socket import gethostname

import import_iso_version
from clean_san_luns import teardown_san, SanCleanup,\
    poweroff_node, poweron_node
from cleanup_sfs import teardown_sfs
from h_litp.litp_rest_client import LitpRestClient
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import exec_process, Sed, keyboard_interruptable, \
    ExitCodes, strong_confirmation_or_exit, delete_file, get_nas_type_sed
from h_util.ini import IniReader
from h_hc.hc_services import Services
from h_snapshots.lvm_snapshot import LVMManager
from h_util.h_nas_console import NasConsole

SK_NASCONSOLE_IP = 'sfs_console_IP'
SK_NASCONSOLE_SUPUSER = 'sfssetup_username'
SK_NASCONSOLE_SUPPASSWD = 'sfssetup_password'


_LOGGER = None


def init_logging():
    """
    Init a logger
    :return:
    """
    global _LOGGER  # pylint: disable=global-statement
    _LOGGER = init_enminst_logging()


def get_logger():
    """
    Get a logger
    :return:
    """
    global _LOGGER  # pylint: disable=global-statement,W0602
    return _LOGGER


class CleanupDeployment(object):  # pylint: disable=R0902,R0904
    """
    Class to clean a deployment so it can be reinstalled from scratch
    """
    YUM = '/usr/bin/yum'
    PYTHON = '/usr/bin/python'
    COBBLER = '/usr/bin/cobbler'
    COBB_LIB = '/var/lib/cobbler'
    KICKSTART = COBB_LIB + '/kickstarts/'
    SNIPPET = COBB_LIB + '/snippets/'
    repo_base = '/var/www/html'
    enm_repos = '{0}/ENM*'.format(repo_base)
    repo_files = '/etc/yum.repos.d'
    SYSTEMCTL = '/usr/bin/systemctl'

    def __init__(self, sed, exclude_nas=None, ssh_port=22):
        self.log = logging.getLogger('enminst')
        self.conf_etc = os.environ['ENMINST_ETC']
        self.enminst_lib = os.environ['ENMINST_LIB']
        self.enminst_bin = os.environ['ENMINST_BIN']
        self.enminst_runtime = os.environ['ENMINST_RUNTIME']
        self.enminst_sedfile = sed
        self.ini_path = self.conf_etc + '/enminst_cfg.ini'
        self.siteini = None
        if isfile(self.ini_path):
            self.siteini = IniReader(self.ini_path)
        self.full_parameter_list = {}
        self.sed = Sed(sed)
        self.infra_storage = '/infrastructure/storage/storage_providers'
        self.item_type = 'sfs-service'
        self.esm_mount_dirs = ["/var/esm-x65736D/", "/var/lib/mysql/"]
        self.esm_dirs = ['postgresql-data', 'rhq-agent', 'rhq-data', 'h2']
        self.esm_vm_dir = "/var/lib/libvirt/instances/"
        self.cleanup_cron_file = "/etc/cron.daily/cleanup_java_core_dumps"
        self.san_fault_cron_file = "/etc/cron.d/san_fault_checker"
        self.nasaudit_error_cron_file = "/etc/cron.d/nasaudit_error_check"
        self.backup_cron_file = "/etc/cron.d/litp_state_backup"
        self.exclude_nas = exclude_nas
        self.consul_data_dir = "/var/consul"
        self.consul_config_dir = "/etc/consul.d"
        self.nas_type_sed = get_nas_type_sed(self.sed)
        uname = self.sed.get_value(SK_NASCONSOLE_SUPUSER)
        passwd = self.sed.get_value(SK_NASCONSOLE_SUPPASSWD)
        self.nasconsole = NasConsole(self.sed.get_value(SK_NASCONSOLE_IP),
                                     uname, passwd, ssh_port=ssh_port,
                                     nas_type=self.nas_type_sed)

    def clean_sfs(self):
        """
        Function Description:
        This function executes the cleanup_sfs.py script.
        This script checks for SFS snapshots and if they exist
        will be removed. The sed (site engineering file) is passed
        as an argument.
        """
        self.log.info('Beginning NAS cleanup')
        if self.nas_type_sed == 'unityxt':
            storage_vlan = self.sed.get_value('VLAN_ID_storage')
            teardown_sfs(self.enminst_sedfile, 'bond0.' + storage_vlan,
                         self.log, self.exclude_nas)
        else:
            teardown_sfs(self.enminst_sedfile, 'eth1', self.log,
                         self.exclude_nas)
        self.log.info("Successfully completed NAS snapshot cleanup")

    def clean_nas_servers(self):
        """
        Function Description:
        This function destroys the nas servers for unityxt.
        The server name is obtained from the litp model.
        """
        if self.nas_type_sed == 'veritas' or self.exclude_nas is not None:
            return

        self.log.info('Beginning cleanup of NAS servers')
        litp = LitpRestClient()
        vs_names = []
        for infra_provider in litp.get_children(self.infra_storage):
            if infra_provider['data']['item-type-name'] == self.item_type:
                get_path = '{0}/virtual_servers'.format(infra_provider['path'])
                for virt_server in litp.get_children(get_path):
                    vs_names.append(virt_server['data']['properties']['name'])
        if not vs_names:
            self.log.warning('No NAS server found in model!')
        else:
            for server_name in vs_names:
                self.nasconsole.nas_server_destroy(server_name)
                self.log.info('Removed NAS server {0}'.format(server_name))

    def clean_san(self):
        """
        This function executes the clean_san_luns.py script.
        This script will disconnect host, deregister host HBA,
        disassociate LUN from a storage group, destroy storage group,
        delete LUN from a storage pool or a raid group, for LUN in
        storage pool delete its snapshot if exist. All required input
        to the script is taken from the LITP model.
        """
        self.log.info("Calling the clean_san_luns")
        teardown_san(self.exclude_nas)
        self.log.info("The clean_san_luns executed successfully")

    def remove_cobbler_distro(self):
        """
        Function Description:
        This function generates a list of cobbler distros.
        if the list contains a value or values, we will attempt
        to remove each element.
        This function is executed from the clean_cobbler function
        :param - none
        :type - none
        """
        self.log.info('Getting cobbler distro list.')
        cmd = 'cobbler distro list'.split()
        try:
            profiles = exec_process(cmd)
        except Exception as ex:
            self.log.exception('Could not read cobbler distro list')
            raise SystemExit(ex)
        profiles = profiles.splitlines()
        profile = map(str.strip, profiles)

        if not profile:
            self.log.info("Cobbler distro list empty, nothing to do.")
        else:
            for node in profile:
                self.log.info('Removing distro {0} from cobbler'.format(node))
                remove_cmd = 'cobbler distro remove --name {0}' \
                    .format(node).split()
                exec_process(remove_cmd)
                self.log.info('Removed {0} from cobbler distro list'.
                              format(node))

    def _delete_matching_files(self, path, ext):
        """
        Function Description:
        This function removes a file based on the path and ext[ension]
        passed, using the delete_file function.
        :param path: File path to where file is stored
        :param ext: File extension
        """
        for filename in glob.glob1(path, ext):
            cobbler_file = join(path, filename)

            self.log.info('Removing {0}'.format(cobbler_file))
            delete_file(cobbler_file)

    def remove_cobbler_kickstart(self):
        """
        Function Description:
        This function generates a list of cobbler kickstart files.
        if the list contains a value it will attempt to call the
        _delete_matching_files function.
        This function is executed from the clean_cobbler function
        :param - none
        :type - none
        """
        self.log.info('Generating list of cobbler kickstart files.')
        services = Services()

        node_list = services.source_nodes()
        for node in node_list:
            self._delete_matching_files(self.KICKSTART,
                                        '{0}.ks'.format(node))

    def disable_maintenance_mode(self):
        """
        Function Description:
        Disable litp maintenance mode
        :return:None
        """
        self.log.info('Disabling LITP maintenance mode.')
        services = Services()
        services.litp().disable_maintenance_mode()

    def is_in_maintenance_mode(self):
        """
        Function Description:
        Return the enabled flag in /litp/maintenence
        :return: True if litp is in maintenance mode
        """
        self.log.info('Determining LITP maintenance mode.')
        services = Services()
        return services.litp().is_in_maintenance_mode()

    def remove_cobbler_snippets(self):
        """
        Function Description:
        This function generates a list of cobbler snippet files.
        if the list contains a value it will attempt to call the
        _delete_matching_files function.
        This function is executed from the clean_cobbler function
        :param - none
        :type - none
        """
        self.log.info('Generating list of cobbler snippet files.')
        services = Services()
        node_list = services.source_nodes()
        for node in node_list:
            self._delete_matching_files(self.SNIPPET,
                                        '{0}.ks.*.snippet'.format(node))

    def remove_cobbler_system(self):
        """
        Function Description:
        This function generates a list of systems in cobbler.
        If the list contains a value or values, we will attempt
        to remove each element.
        This function is executed from the clean_cobbler function
        :param - none
        :type - none
        """
        self.log.info('Getting cobbler system list.')
        cmd = 'cobbler system list'.split()
        try:
            systems = exec_process(cmd)
        except Exception as ex:
            self.log.exception('Could not execute cobbler systems list')
            raise SystemExit(ex)
        systems = systems.splitlines()
        system = map(str.strip, systems)
        if not system:
            self.log.info("Cobbler system list empty, nothing to do.")
        else:
            for node in systems:
                self.log.info('Removing {0} from cobbler'.format(node))
                remove_cmd = 'cobbler system remove --name {0}' \
                    .format(node).split()
                try:
                    exec_process(remove_cmd)
                    self.log.info('Removed {0} from cobbler system list'.
                                  format(node))
                except IOError:
                    self.log.error("Unable to remove cobbler " + node)

    def remove_cobbler_profile(self):
        """
        Function Description:
        This function generates a list of cobbler profiles.
        if the list contains a value or values, we will attempt
        to remove each element.
        This function is executed from the clean_cobbler function
        :param - none
        :type - none
        """
        self.log.info('Getting cobbler profile list.')
        cmd = 'cobbler profile list'.split()
        try:
            profiles = exec_process(cmd)
        except Exception as ex:
            self.log.exception('Could not execute cobbler profile list')
            raise SystemExit(ex)
        profiles = profiles.splitlines()
        profile = map(str.strip, profiles)
        if not profile:
            self.log.info("Cobbler profile list is empty. Nothing to do.")
        else:
            for node in profile:
                self.log.info('Removing profile {0} from cobbler'.format(node))
                remove_cmd = 'cobbler profile remove --name {0}'.format(node)
                try:
                    exec_process(remove_cmd.split())
                    self.log.info('Removed {0} from cobbler profile list'.
                                  format(node))
                except IOError:
                    self.log.error("Unable to remove cobbler %s" % node)

    def clean_cobbler(self):
        """
        Function Description:
        clean_cobbler calls three functions that will tidy up all
        cobbler related files and resources
        :param - none
        :type - none
        """
        self.log.info('Beginning Cobbler cleanup')
        CleanupDeployment.remove_cobbler_system(self)
        CleanupDeployment.remove_cobbler_profile(self)
        CleanupDeployment.remove_cobbler_distro(self)
        CleanupDeployment.remove_cobbler_kickstart(self)
        CleanupDeployment.remove_cobbler_snippets(self)
        self.log.info('Successfully completed Cobbler cleanup.')

    def clean_puppet_certs(self):
        """
        Delete all agent puppet certs (excluding LMS)
        """
        self.log.info("Beginning Cleanup of Puppet Certs")

        try:
            stdout = exec_process(['/usr/bin/puppet', 'cert', 'list', '-all'])
        except IOError as error:
            self.log.exception('An error occurred listing puppet certs!')
            raise SystemExit(error)
        lms_hostname = gethostname()
        for line in stdout.split('\n'):
            line = line.strip()
            if not line:
                continue
            cert_host = line.split('"')[1]
            if lms_hostname == cert_host:
                # Dont remove the LMS cert
                continue
            self.log.info('Removing puppet cert for {0}'.format(cert_host))
            try:
                exec_process(['/usr/bin/puppet', 'cert', 'clean', cert_host])
            except IOError as error:
                self.log.exception('An error occurred removing '
                                   'cert for: {0}'.format(cert_host))
                raise SystemExit(error)
        self.log.info('Successfully completed cleanup puppet certs.')

    @staticmethod
    def clean_enm_version_and_history_info():  # pylint: disable=C0103
        """
        Function Description:
        Remove ENM version and history info.
        :param - none
        :type - none
        """
        delete_file(import_iso_version.ENM_VERSION_FILENAME)
        delete_file(import_iso_version.ENM_HISTORY_FILENAME)

    def clean_known_hosts(self):
        """
        Function Description:
        The clean_known_hosts function removes the .ssh/known_hosts
        directory if it exists
        :param - none
        :type - none
        """
        self.log.info("Beginning cleanup of known hosts")
        enm_known_hosts = '/root/.ssh/known_hosts'
        if os.path.isfile(enm_known_hosts):
            try:
                os.remove(enm_known_hosts)
                self.log.info("Successfully removed known hosts file")
            except IOError:
                self.log.error("An error occurred trying to remove the hosts "
                               "file")
        else:
            self.log.info("No host file to be removed")
        self.log.info("Successfully completed known hosts cleanup")

    def clean_litp(self):
        """
        Function Description:
        The clean_litp function initially stops the litpd service,
        removes the litp directory and then starts the service
        :param - none
        :type - none
        """
        self.log.info("Beginning cleanup of litp model")
        litp_stop = (self.SYSTEMCTL + ' stop litpd.service').split()
        try:
            exec_process(litp_stop)
        except IOError as error:
            self.log.exception("An error occurred stopping service")
            raise Exception(error)
        else:
            self.log.info('LITP daemon stopped')
        litp_dir = "/var/lib/litp/core/model"
        if os.path.isdir(litp_dir):
            shutil.rmtree(litp_dir)
            self.log.info("Successfully removed LITP directory")

        litp_purgedb = '/usr/local/bin/litpd.sh --purgedb'
        try:
            exec_process(litp_purgedb, use_shell=True)
        except Exception as error:
            self.log.exception("An error occurred purging litp database")
            raise Exception(error)
        else:
            self.log.info('LITP database purged')

        litp_start = (self.SYSTEMCTL + ' start litpd.service').split()
        try:
            exec_process(litp_start)
        except Exception as error:
            self.log.exception("An error occurred starting service")
            raise Exception(error)
        else:
            self.log.info('LITP daemon started.')
        self.log.info("Successfully completed LITP cleanup")

    def clean_lvm_snapshots(self):
        """
        Function Description:
        This function executes the cleanup_lvm.py script.
        This script checks for SFS snapshots and if they exist
        will be removed. The sed (site engineering file) is passed
        as an argument.
        :param - none
        :type - none
        """
        sed = self.enminst_sedfile
        self.log.info("Beginning LVM cleanup")
        cleanup_lvm = os.path.join(self.enminst_lib, 'cleanup_lvm.py')
        cmd = (self.PYTHON, cleanup_lvm, sed)
        if os.path.isfile(cleanup_lvm):
            try:
                exec_process(cmd)
            except IOError as error:
                self.log.exception("An error occurred executing "
                                   "cleanup_lvm.py")
                raise SystemExit(error)
        else:
            self.log.error("LVM cleanup script not found")
        self.log.info("Successfully completed LVM snapshot cleanup")

    def clean_puppet(self):
        """
        Function Description:
        The clean_puppet function removes the puppet manifest
        the known_hosts directories and ensures the puppet can
        start thereafter
        :param - none
        :type - none
        """
        self.log.info("Beginning cleanup of puppet")
        puppet_stop = (self.SYSTEMCTL + ' stop puppet.service').split()
        puppet_start = (self.SYSTEMCTL + ' start puppet.service').split()
        try:
            exec_process(puppet_stop)
        except Exception as error:
            self.log.exception("An error occurred stopping service")
            raise Exception(error)
        puppet_plugin_dir = \
            "/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/"
        if os.path.isdir(puppet_plugin_dir):
            try:
                for root, dirs, files in os.walk(puppet_plugin_dir):
                    for fil in files:
                        os.remove(os.path.join(root, fil))
                        self.log.info("Successfully removed file %s" % fil)
                    for directory in dirs:
                        shutil.rmtree(os.path.join(root, directory))
                        self.log.info("Successfully removed directory %s"
                                      % directory)
            except IOError:
                self.log.error("Unable to remove puppet contents")
        CleanupDeployment.clean_known_hosts(self)
        try:
            exec_process(puppet_start)
        except IOError as error:
            self.log.exception("An error occurred starting service")
            raise Exception(error)
        self.log.info("Successfully completed puppet cleanup")

    def clean_runtime(self):
        """
        Function Description:
        The clean_runtime function removes the ENM runtime
        directory
        :param - none
        :type - none
        """
        self.log.info("Cleaning up ENM runtime")
        if os.path.isdir(self.enminst_runtime):
            shutil.rmtree(self.enminst_runtime)
            self.log.info("Successfully removed ENM runtime directory")
        else:
            self.log.info("No runtime directory to delete")
        self.log.info("Successfully completed runtime cleanup")

    def clean_vm_images(self):
        """
        Function Description:
        The clean_vm_images function removes the images directory
        :param - none
        :type - none
        """
        self.log.info("Beginning cleanup VM images")
        vm_image_dir = "/var/www/html/images"
        if os.path.isdir(vm_image_dir):
            shutil.rmtree(vm_image_dir)
            self.log.info("Successfully removed VM image directory")
        else:
            self.log.info("No VM directory to delete")
        self.log.info("Successfully completed VM Images cleanup")

    def clean_esm_vm(self):
        """
        Function Description:
        The clean_esm_vm function shuts down and removes the ESM VM
        :param - none
        :type - none
        """
        self.log.info("Beginning cleanup of ESM VM")
        vm_name = 'esmon'
        destroy_cmd = ['virsh', 'destroy', vm_name]
        undefine_cmd = ['virsh', 'undefine', vm_name]
        exec_process(destroy_cmd, True)
        exec_process(undefine_cmd, True)

        esm_vm_dir = os.path.join(self.esm_vm_dir, vm_name)

        if os.path.isdir(esm_vm_dir):
            shutil.rmtree(esm_vm_dir)
            self.log.info("Successfully removed ESM VM directory")
        else:
            self.log.info("No VM directory to delete")

        esm_dirs_to_remove = [path + dir_name for path in self.esm_mount_dirs
                              for dir_name in self.esm_dirs]
        for _dir in esm_dirs_to_remove:
            if os.path.isdir(_dir):
                shutil.rmtree(_dir)
                self.log.info("Successfully removed directory: {0}".format(
                               _dir))
            else:
                self.log.info("No directory to delete: {0}".format(_dir))

        self.log.info("Successfully completed ESM VM cleanup")

    @staticmethod
    def get_pkg_names_of_type(pkg_list, item_type):
        """
        Get the a list of name property values from modeled
        item types
        :param pkg_list: The item list
        :param item_type: The item type
        :return:
        """
        return [package['data']['properties']['name']
                for package in pkg_list
                if package['data']['item-type-name'] == item_type]

    def clean_ms_packages(self, exclude_packages=None):
        """
        Reads LITP model for installed packages on MS and removes them.
        Does not remove any packages provided in exclude_packages list.
        :param exclude_packages: List of package names to skip removal.
        :return: None
        """
        litp = LitpRestClient()
        self.log.info('Reading MS installed RPM package(s) from model ...')
        litp_items = litp.get_children('/ms/items')
        package_names = self.get_pkg_names_of_type(litp_items,
                                                   'reference-to-package')
        if not package_names:
            self.log.info('No MS RPM packages found in model. Continue.')
            return

        if exclude_packages:
            self.log.debug(
                    'Excluding packages: {0}'.format(
                            ', '.join(exclude_packages)))
            for pkg in exclude_packages:
                try:
                    package_names.remove(pkg)
                except ValueError:
                    self.log.debug('Package %s not found in model.' % pkg)

        self.yum_remove(package_names)
        self.log.info('Successfully removed MS installed RPM package(s).')

    def clean_ms_rsyslog(self):
        """
        Installs rsyslog.
        :param: none
        :return: None
        """
        package_names = ["rsyslog"]
        self.yum_install(package_names)
        self.log.info('Successfully installed MS RPM package(s).')
        self.log.info("Reloading systemd manager configuration")
        systemctl_daemon_reload = (self.SYSTEMCTL + ' daemon-reload').split()
        try:
            exec_process(systemctl_daemon_reload)
        except Exception as error:
            mess = "An error occurred reloading systemd manager configuration"
            self.log.exception(mess)
            raise Exception(error)
        self.log.info("Restarting rsyslog")
        rsyslog_restart = (self.SYSTEMCTL + ' restart rsyslog').split()
        try:
            exec_process(rsyslog_restart)
        except Exception as error:
            self.log.exception("An error occurred restarting service")
            raise Exception(error)
        self.log.info("Restarting systemd-journald.socket")
        socket_restart = \
                (self.SYSTEMCTL + ' restart systemd-journald.socket').split()
        try:
            exec_process(socket_restart)
        except Exception as error:
            self.log.exception("An error occurred restarting service")
            raise Exception(error)

    def yum_remove(self, packages):
        """
        Uninstall a package using yum
        :param packages: List of packages to remove
        :return:
        """
        yum_remove_cmd = '{yum} remove -y -q'.format(yum=self.YUM).split()
        yum_remove_cmd.extend(packages)
        self.log.info('Removing package(s): {0}'
                      .format(', '.join(packages)))
        try:
            exec_process(yum_remove_cmd)
        except IOError as ioe:
            self.log.exception(ioe.message)
            raise ioe

    def yum_install(self, packages):
        """
        Install a package using yum
        :param packages: List of packages to install
        :return:
        """
        yum_install_cmd = '{yum} install -y -q'.format(yum=self.YUM).split()
        yum_install_cmd.extend(packages)
        self.log.info('Installing package(s): {0}'
                      .format(', '.join(packages)))
        try:
            exec_process(yum_install_cmd)
        except IOError as ioe:
            self.log.exception(ioe.message)
            raise ioe

    def clean_model_packages(self):
        """
        Uninstalled any packages that are modeled in the /ms
        :return:
        """
        litp = LitpRestClient()
        self.log.info('Reading installed model package(s) from LITP model ...')
        litp_items = litp.get_children('/ms/items')
        item_type = 'reference-to-package-list'
        pkg_lists = [item['path'] for item in litp_items
                     if item['data']['item-type-name'] == item_type]
        collections = list()
        for plist in pkg_lists:
            collections.extend(litp.get_children(plist))
        package_names = list()
        for collection in collections:
            packages = litp.get_children(collection['path'])
            package_names.extend(
                    self.get_pkg_names_of_type(
                            packages, 'reference-to-model-package'))

        if not package_names:
            self.log.info('No model packages found in LITP model. Continue.')
            return
        self.yum_remove(package_names)
        self.log.info('Successfully removed model package(s).')

    def clean_kvm_ssh_keys(self):
        """
        Function Description:
        Check if the ssh key functionality from the /root/.ssh/
        directory exists, and if so, remove it
        :param - none
        :type - none
        """
        self.log.info("Beginning cleanup of ssh keys ")
        ssh_path = '/root/.ssh/'
        ssh_config_file = ssh_path + 'config'
        ssh_private_key = ssh_path + 'vm_private_key'
        ssh_public_key = ssh_private_key + '.pub'
        ssh_file_list = [ssh_private_key, ssh_config_file, ssh_public_key]
        for ssh_file in ssh_file_list:
            if os.path.isfile(ssh_file):
                try:
                    os.remove(ssh_file)
                    self.log.info("Successfully removed {0} ".
                                  format(ssh_file))
                except IOError:
                    self.log.error("An error occurred trying to remove the "
                                   "{0} file".format(ssh_file))
        self.log.info('Successfully completed ssh cleanup')

    def clean_yum_repositories(self):
        """
        Remove any yum repositories that it can find beginning with the
        prefix `ENM_` in `/var/www/html/`
        :return:
        """
        html_repo_dirs = glob.glob(self.enm_repos)

        if not html_repo_dirs:
            self.log.info('No repositories found to remove.')
            return

        self.log.info('Cleaning YUM repository caches')
        yum_clean_cmd = '{yum} clean all'.format(yum=self.YUM)
        try:
            exec_process(yum_clean_cmd.split())
        except IOError as ioe:
            self.log.exception(ioe.message)
            raise ioe

        for repo_dir in html_repo_dirs:
            self.log.info('Removing repository directory: {0}'
                          .format(repo_dir))
            self.remove_dir(repo_dir)
            self.remove_repo_file(basename(repo_dir))

    def clean_lms_hosts_file(self, hosts_file=None):
        """
        Function Description:
        Clean LMS /etc/hosts file and bring it to the LITP install level.
        :param - none
        :type - none
        """
        if not hosts_file:
            hosts_file = '/etc/hosts'
        if not isfile(hosts_file):
            err_msg = "{0} file does not exist on LMS".format(hosts_file)
            self.log.exception(err_msg)
            raise SystemExit(2)
        self.delete_content(hosts_file)
        self.write_default_hosts_file(hosts_file)

    def clean_consul(self):
        """
        Uninstall consul from MS
        :return:
        """
        consul_stop = (self.SYSTEMCTL + ' stop consul.service').split()
        consul_packages = ['ERICconsulconfig_CXP9033977.noarch']
        consul_start_script = '/etc/init.d/consul'
        consul_unit_link = \
                '/etc/systemd/system/multi-user.target.wants/consul.service'
        if os.path.isfile(consul_start_script):
            self.log.info("Beginning cleanup of consul")
            try:
                exec_process(consul_stop)
            except IOError as error:
                self.log.exception("An error occurred stopping consul service")
                raise Exception(error)
            else:
                self.log.info('consul service stopped')
                self.remove_dir(self.consul_data_dir)
                self.remove_dir(self.consul_config_dir)
                if os.path.islink(consul_unit_link):
                    try:
                        os.unlink(consul_unit_link)
                    except IOError:
                        self.log.error("An error occurred unlinking \
                                {0}".format(consul_unit_link))
                self.yum_remove(consul_packages)
                self.log.info('Successfully removed consul.')

    def clean_lms_crons(self):
        """
        Function Description:
        Clean /etc/cron.daily/cleanup_java_core_dumps file and
        the /etc/cron.d/litp_state_backup file
        :param - none
        :type - none
        """
        self.log.info("Removing cron files ")
        delete_file(self.cleanup_cron_file)
        delete_file(self.backup_cron_file)
        delete_file(self.san_fault_cron_file)
        delete_file(self.nasaudit_error_cron_file)

    def delete_content(self, file_name):
        """
        Function Description:
        Remove the contents of the file.
        :param - file_name
        :type - string
        """
        self.log.info("Removing contents of file {0}".format(file_name))
        with open(file_name, "r+") as hosts:
            hosts.truncate()
        self.log.info("Removed contents of file {0}".format(file_name))

    def write_default_hosts_file(self, hosts_file):
        """
       Write to the hosts file.
       :param - hosts_file
       :type - string
       """
        hostname = socket.gethostname()
        with open(hosts_file, "r+") as hosts:
            self.log.info("Resetting the contents of {0}".format(hosts_file))
            hosts.write('127.0.0.1 {0} localhost\n'.format(hostname))
            self.log.info("Wrote first line to {0}".format(hosts_file))
            hosts.write('::1 {0} localhost\n'.format(hostname))
            self.log.info("Wrote second line to {0}".format(hosts_file))
        self.log.info("Reset default contents of {0} done".format(hosts_file))

    def remove_item_with(self, func, item):
        """
        Delete a file, ignored  not found errors
        :param func:
        :param item:
        :return:
        """
        try:
            func(item)
        except OSError as error:
            if error.errno == 2:
                self.log.debug(error.strerror)
            else:
                self.log.exception(error.strerror)
                raise error

    def remove_repo_file(self, repo_id):
        """
        Remove a file ignoring not found errors.
        Checking each `.repo` file and if the baseurl match ENM_*
        only then it will delete the file. If there are multiple repos
        defined in a file, it will remove the section that holds reference
        to baseurl matching ENM_*, but it will not delete the file as it
        still might hold references to other repos(multi repo file).
        :param repo_id: regex to match against
        """
        for repo_file in glob.glob(join(self.repo_files, '*.repo')):
            parser = SafeConfigParser()
            parser.read(repo_file)
            remove_section_name = None
            for section in parser.sections():
                for item in parser.items(section):
                    if len(item) > 1:
                        if match(r'.*/{0}.*'.format(repo_id),
                                 item[1]):
                            remove_section_name = section
                            break
            if remove_section_name:
                parser.remove_section(remove_section_name)

                if parser.sections():
                    self.log.info(
                        'Removing repo {0} from multi repo file {1}'.format(
                            remove_section_name, repo_file))
                    with open(repo_file, 'w') as _writer:
                        parser.write(_writer)
                else:
                    self.log.info('Removing repo file: {0}'.format(repo_file))
                    self.remove_item_with(os.remove, repo_file)

    def remove_dir(self, directory):
        """
        Remove a directory ignoring not found errors
        :param directory: Path of directory to remove
        :return:
        """
        self.remove_item_with(shutil.rmtree, directory)

    def powerdown_racks(self):
        """
        Get a list of rack servers and power them off
        :return:
        """
        lvm = LVMManager()
        local_disk_nodes = lvm.get_nodes_using_local_storage(ignore_states=[])
        san_cleanup = SanCleanup()
        sys_bmc = san_cleanup.get_sys_bmc()
        for rack in local_disk_nodes.keys():
            self.log.info('Powering off rack server {0}'.format(rack.item_id))
            poweroff_node(sys_bmc, rack.item_id)
            self.log.info('Powered off rack server {0}'.format(rack.item_id))

    def get_node_ilo_info(self):
        """
        Get a dict of ilo info for each node
        :return: dict with node ilo info
                 e.g  {node : [iLo_ip_address, iLo_username, iLo_password]}
        """
        node_details = {}
        node_keys = self.sed.find_keys('^.*?_node[0-9]+_ilo_IP')
        regex = r'^.*_node\d'
        for node in node_keys:
            try:
                ilo_ip = self.sed.get_value(node)
                if ilo_ip is None or ilo_ip == "":
                    continue
                node_name = match(regex, node).group()
                ilo_username = self.sed.get_value(node_name + "_iloUsername")
                if ilo_username is None or ilo_username == "":
                    continue
                ilo_password = self.sed.get_value(node_name + "_iloPassword")
                if ilo_password is None or ilo_password == "":
                    continue
            except KeyError:
                continue
            node_details[node_name] = [ilo_ip, ilo_username, ilo_password]
        return node_details

    def poweron_nodes(self):
        """
        Get a list of servers and power them on
        :return:
        """
        nodes_in_sed = self.get_node_ilo_info()
        all_nodes_up = True
        nodes_to_powerup = {}
        for node in nodes_in_sed:
            try:
                self.log.info('Powering on {0}'.format(str(node)))
                node_up = poweron_node(nodes_in_sed, node, True)

                self.log.info(
                    'Power Status for {0}:{1}'.format(str(node), node_up))

                if not node_up:
                    self.log.info(
                    'Node {0} has not powered up. Power status: {1}'.format(
                        str(node), node_up))
                    nodes_to_powerup.update({node: nodes_in_sed[node]})
                self.log.info('Powered on {0}'.format(str(node)))
            except SystemExit:
                self.log.info('Failed to power on {0}'.format(str(node)))
                all_nodes_up = False
        if not all_nodes_up:
            self.log.warning('One or more nodes failed to power up,'
                             ' please power them up manually '
                             'before continuing so the last stage of'
                             ' teardown is complete.')
            sys.exit(1)
        elif len(nodes_to_powerup) > 0:
            self.log.info('Waiting for nodes to power up')
            time.sleep(180)
            retries = 5
            while retries > 0:
                retries -= 1
                nodes_finished = \
                    self.check_if_nodes_finished_post(nodes_to_powerup)
                if nodes_finished is True:
                    break
                elif retries == 0:
                    self.log.warning('One or more nodes failed to power up,'
                                     ' please power them up manually '
                                     'before continuing so the last stage of'
                                     ' teardown is complete.')
                    sys.exit(1)
                time.sleep(150)

    def check_if_nodes_finished_post(self, nodes_ilo_info):
        """
        Function Description:
        This function will check if nodes are finished powering on
        :param - "nodes_ilo_info"
        :type - dict of nodes along with
         ilo info(returned from get_node_ilo_info)
        """
        from h_util.h_utils import Redfishtool
        redfish_tool = Redfishtool()
        response = False
        for node in nodes_ilo_info:
            node_ilo_info = nodes_ilo_info[node]
            node_ip = node_ilo_info[0]
            node_username = node_ilo_info[1]
            node_password = node_ilo_info[2]
            response = redfish_tool.finished_post(node_ip, node_username,
                                                  node_password)
            self.log.info('FinishedPost status of node {0} is: {1}'
                          .format(node, response))
        return response

    def clean_all(self):
        """
        Function Description:
        The clean_all function allows the user to execute all
        functions from the deployment_teardown.py script
        :param - none
        :type - none
        """
        self.log.info("Beginning full cleanup")
        # Ensure LITP is not in maintenance mode
        # Then do puppet as it stop it from reapplying stuff that's being
        # torn down (e.g. sfs mounts)

        if self.is_in_maintenance_mode():
            self.disable_maintenance_mode()
        self.clean_puppet()
        self.clean_puppet_certs()
        self.clean_cobbler()
        self.clean_sfs()
        self.clean_nas_servers()
        self.clean_san()
        self.powerdown_racks()
        self.clean_runtime()
        self.clean_ms_packages()
        self.clean_ms_rsyslog()
        self.clean_model_packages()
        self.clean_yum_repositories()
        self.clean_consul()
        self.clean_litp()
        self.clean_lvm_snapshots()
        self.clean_enm_version_and_history_info()
        self.clean_vm_images()
        self.clean_esm_vm()
        self.clean_lms_hosts_file()
        self.clean_kvm_ssh_keys()
        self.clean_lms_crons()
        self.log.info("Successfully completed full cleanup")


def function_list():
    """
    Function Description:
    This function returns a list of functions within the script
    that contain 'clean_' This list will allow the user
    to execute various aspects of the deployment_teardown.py script
    :param - "clean_<argument>"
    :type - parameter command
    """
    output = dir(CleanupDeployment)
    elements = []
    for i in output:
        if "clean_" in i:
            elements.append(i)
    return elements


def interrupt_handler():
    """
    Callback to handle CTRL-c
    :return:
    """
    get_logger().warning('CTRL-C: Teardown interrupted, re-run again to '
                         'ensure everything is completed.')


@keyboard_interruptable(callback=interrupt_handler)
def main(args):
    """
    Main fucntion
    :param args: Input args from cli
    :return:
    """
    init_logging()
    exclude = None
    usage = ('usage: %prog '
             ' --sed <location to site engineering document>'
             ' --exclude-nas <NAS file system/share name to exclude>'
             ' --command clean_ <argument> \n' + str(function_list()))
    arg_parser = OptionParser(usage)
    arg_parser.add_option('-y', '--assumeyes', dest='assumeyes',
                          default=False, action='store_true',
                          help='Answer yes for all questions')

    arg_parser.add_option('--sed')
    arg_parser.add_option('--command')
    arg_parser.add_option('--exclude-nas', dest='exclude')

    (options, _) = arg_parser.parse_args(args)
    if not options.sed:
        arg_parser.print_help()
        raise SystemExit(2)
    if not options.command:
        arg_parser.print_help()
        raise SystemExit(2)
    if options.exclude:
        exclude = [ex.strip() for ex in options.exclude.split(',') if ex]
    strong_confirmation_or_exit(options.assumeyes, 'Teardown',
                                "Teardown is going to start.")

    cleanup_class = CleanupDeployment(options.sed, exclude)
    clean_function = options.command
    if clean_function in function_list():
        funct = getattr(cleanup_class, clean_function)
        try:
            get_logger().debug('Calling clean function: {0}'.format(
                    clean_function))
            funct()
        except Exception:
            get_logger().exception('Function {0} failed'.
                                   format(clean_function))
            raise SystemExit(ExitCodes.TEARDOWN_FUNCTION_ERROR)
    cleanup_class.poweron_nodes()
    cleanup_class.log.info('Teardown completed successfully')


if __name__ == '__main__':
    main(sys.argv)
