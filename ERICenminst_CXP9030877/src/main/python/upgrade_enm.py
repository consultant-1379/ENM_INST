# pylint: disable=C0302,R0912
"""
Upgrade_enm upgrade ENM systems.
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2015 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : upgrade_enm.py
# Purpose : upgrade_enm upgrade ENM systems.
# Date    : 24-03-2015
# Revision: A2
# ********************************************************************
import logging
import operator
import os
import re
import time
import shutil
import sys
import pickle
import tarfile
import textwrap
import filecmp
import yaml
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from os.path import isfile
from platform import uname
from tempfile import NamedTemporaryFile, mkdtemp
from urlparse import urlparse, urlunparse
from json import load, dumps

import deployer
import encrypt_passwords
import crypto_service
import enm_snapshots
import enm_version
import import_iso
import import_iso_version
import ms_uuid
import ssh_key_creation
import substitute_parameters
from clean_san_luns import SanCleanup
from enm_healthcheck import HealthCheck
from enm_snapshots import manage_snapshots, EnmSnap, \
    check_snapshots_indicator_file_exists, \
    create_snapshots_indicator_file, \
    remove_snapshots_indicator_file
from h_hc.hc_neo4j_cluster import DbNodesSshCredentials, \
    Neo4jClusterOverview, Neo4jLun, FORCE_SSH_KEY_ACCESS_FLAG_PATH
from h_infra.pre_upgrade_infra import pre_snap_changes
from h_litp.litp_rest_client import LitpRestClient, LitpException, LitpObject
from h_litp.litp_utils import main_exceptions, get_xml_deployment_file
from h_litp.sed_password_encrypter import set_key_nodes
from h_logging.enminst_logger import init_enminst_logging, \
    set_logging_level, log_header, log_cmdline_args
from h_util.h_housekeeping import EnmLmsHouseKeeping
from h_util.h_postgres import PostgresService
from h_util import h_utils
from h_util.h_utils import exec_process, exec_process_via_pipes, ExitCodes, \
    keyboard_interruptable, is_valid_file, read_enminst_config, Sed, \
    is_physical_environment, strong_confirmation_or_exit, \
    delete_file, copy_file, litp_backup_state_cron, \
    remove_rpm, install_rpm, cleanup_java_core_dumps_cron, \
    check_package_installed, RHELUtil, is_valid_hc_list, \
    create_san_fault_check_cron, create_nasaudit_errorcheck_cron, \
    EnminstWorking, Redfishtool, get_nas_type, migrate_cleanup_cmd, \
    compare_versions, copy_custom_banners, get_rpm_info
from h_vcs.vcs_cli import Vcs

from h_xml.xml_utils import load_xml, xpath
from hw_resources import HwResources
from switch_db_groups import switch_dbcluster_groups
from litp.core.rpc_commands import PuppetExecutionProcessor
from upgrade_enm_internal_model_only import update_litp
from h_puppet.mco_agents import PostgresAgent
from h_xml.xml_utils import unity_model_updates
from h_xml.xml_validator import XMLValidator
from enm_bouncer import EnmBouncer
from datetime import datetime
from preonlinedep import PreOnlineProvisioner
from glob import glob
from socket import gethostname

TGZ_FILE_TYPE = "gzip compressed data, from Unix"
ISO_FILE_TYPE = "ISO 9660 CD-ROM filesystem data"

SOFTWARE_IMAGES_PATH = '/software/images'
NOT_ONLY_PATCH = ('-m', '--model')

KEY_PROPERTIES = 'properties'
KEY_SOURCE_URI = 'source_uri'

URL_PATH_INDEX = 2

YUM_UPGRADE_USING_OS_REPO_CMD = \
    'yum -y --disablerepo=* --enablerepo=OS upgrade'
YUM_UPGRADE_USING_UPDATES_REPO_CMD = \
    'yum -y --disablerepo=* --enablerepo=UPDATES upgrade'
YUM_CHECK_UPGRADE_USING_UPDATES_REPO_CMD = \
    'yum -y --disablerepo=* --enablerepo=UPDATES check-update'
YUM_CLEAN_ALL_CMD = 'yum clean all'
PUPPET_DISABLE_MS_CMD = 'puppet agent --disable'
PUPPET_ENABLE_MS_CMD = 'puppet agent --enable'
PUPPET_ACTION_NON_MASTER_CMD_TEMPLATE = 'mco puppet {0} -W puppet_master=false'
LABEL_LITP = 'LITP'
LABEL_RHEL = 'RHEL'
LABEL_OS_PATCHES = 'OS_PATCHES'

RPM_QUERY_KERNEL_BY_LAST = '/bin/rpm -q --last kernel'
EXTRACT_KERNEL_RELEASE_REGEXP = '^kernel-(\\S+).*'
UNAME_INDEX_RELEASE = 2

CMD_OPTION_NOREBOOT_SHORT = '-R'

ITEM_NOT_FOR_REMOVAL = ()

INFRA_PLAN = 'infrastructure_plan'
UPGRADE_PLAN = 'upgrade_plan'
STATE_START = 'start'
STATE_FAILED = 'failed'
STATE_END = 'end'
WEB_ROOT = '/var/www/html'

INFRASTRUCTURE_CLUSTERS = ['svc_cluster', 'scp_cluster',
                           'eba_cluster', 'ebs_cluster',
                           'str_cluster', 'asr_cluster',
                           'evt_cluster', 'aut_cluster',
                           'db_cluster']
GOSSIP_SG_VPATH = '/deployments/enm/clusters/db_cluster' \
'/services/gossiprouter_clustered_service'
GOSSIP_AFFECTED_CLUSTERS = ['svc_cluster', 'scp_cluster',
                           'eba_cluster', 'ebs_cluster',
                           'str_cluster', 'asr_cluster',
                           'evt_cluster', 'aut_cluster']

JGROUPS_PROTOCOL_MIGRATION = "jgroups_protocol_migration"
POST_RESTORE_SCRIPT = '/opt/ericsson/enminst/bin/enm_post_restore.sh '\
'get_check_clear_non_dbcluster_groups'
POST_BOUNCE_SLEEP_SECONDS = 600
POST_BOUNCE_TIMEOUT_SECONDS = 5400
MONITORING_POST_BOUNCE_SLEEP_SECONDS = 60
CONSUL_URL = "http://ms-1:8500/v1/kv/"
PIB_CRON_DELTA = 59
VMS_WITHOUT_JGROUPS = 'vms_without_jgroups'
VMS_WITHOUT_JGROUPS_VALUE = 'httpd,'\
                'amos,scripting,winfiol,openidm,'\
                'bnsiserv,fmx,sso,visinamingnb,visinamingsb,'\
                'flowautomation,ops,nodeplugins,vaultserv,cnom,'\
                'ebsm1,ebsm2,ebsm3,ebsm4,ebsm5,udcdashboard,imadserv,'\
                'imadserv-2,imadserv-3,imadserv-4,imkbserv,imgroupingserv,'\
                'imgroupingserv-2,imfmalarmserv,imlcserv,ebaapeps1,'\
                'ebaapeps2,ebaapeps3,ebaapeps4,ebakafka1,ebakafka2,'\
                'ebamsstr1,ebamsstr2,ebareg1,ebareg2,ebazoo1,rpmoflow1,'\
                'rpmoflow2,rpmoflow3,rpmokafka1,rpmokafka2,rttflow1,'\
                'rttflow2,supervc,ncm'


class ENMUpgrade(object):  # pylint: disable=R0902,R0904,R0912
    """
    Manages upgrade of ENM system
    """
    YUM = '/usr/bin/yum'
    MAP_VM_IMAGE_TO_PARAM_NAME = {'rhel7-lsb-image': 'ERICrhel79lsbimage',
                                  'rhel7-jboss-image': 'ERICrhel79jbossimage',
                                  'sles15-image': "ERICsles15image"}

    PARAM_LVM_SNAPSIZE = 'lvm_snapsize'
    PARAM_REGENERATE_KEYS = 'regenerate_keys'
    PARAM_DISABLE_HC = 'disable_hc'
    PARAM_EXCLUDE_HCS = 'disable_hcs'
    PARAM_OS_PATCH = 'os_patch'
    PARAM_LITP_ISO = 'litp_iso'
    PARAM_NOREBOOT = 'noreboot'
    PARAM_SED_FILE = 'sed_file'
    PARAM_MODEL_XML = 'model_xml'
    PARAM_ENM_ISO = 'enm_iso'
    PARAM_INTERNAL_MODEL = 'internal_model'
    PARAM_RHEL_ISO = 'rhel7_9_iso'

    MAIN_UPGRADE_PARAMS = [PARAM_LVM_SNAPSIZE, PARAM_REGENERATE_KEYS,
                           PARAM_DISABLE_HC, PARAM_EXCLUDE_HCS,
                           PARAM_OS_PATCH, PARAM_LITP_ISO,
                           PARAM_NOREBOOT, PARAM_SED_FILE, PARAM_MODEL_XML,
                           PARAM_ENM_ISO, PARAM_INTERNAL_MODEL]

    def __init__(self):
        """
        Initializes instance
        """
        self.log = logging.getLogger('enminst')
        self.config = read_enminst_config()
        self.passwords_store_file = None
        self.litp = LitpRestClient()
        self.runtime_xml_deployment = self.config.get('enminst_xml_deployment')
        self.litp_xsd = self.config.get('litp_xsd')
        self.ms_rhel_done_file = os.path.join(
            os.environ['ENMINST_RUNTIME'], 'rhel_copied')
        self.ms_patched_done_file = os.path.join(
                os.environ['ENMINST_RUNTIME'], 'ms_os_patched')
        self.prev_dep_xml = self.config.get('previous_xml_deployment')
        self.deploy_diff_out = self.config.get('deployment_diff_output')
        self.generate_depl_diff_command = self.config.get('dstutil_scr')
        self.persisted_params = None
        self.rhel_os_patch_rpms = {}
        self.rhel_patch_cxps = {}
        self.rhel7_ver = self.config.get('rhel7_ver')
        self.rhel8_ver = self.config.get('rhel8_ver')
        self.valid_rhel_patch_versions = (self.rhel7_ver,
                                          self.rhel8_ver)
        self.rhel7_9_copied = False
        self.rhel_util = RHELUtil(WEB_ROOT)
        self.gossip_upgrade = False
        self.infra_plan = False
        self.reboot_required = True
        self.vers_conf_key_map = {self.rhel7_ver: 'rhel7',
                                  self.rhel8_ver: 'rhel8'}

    def regenerate_ssh_keys(self):
        """
        Executes the ssh_key_creation script, which will regenerate
        ssh keys for all VM's deployed without running the plan.
        """
        try:
            ssh = ssh_key_creation.SshCreation()
            ssh.manage_ssh_action(regenerate=True, no_litp_plan=True)
        except IOError as error:
            self.log.error('Unable to execute {0} script, whilst '
                           'regenerating SSH Keys. Exiting..'.
                           format(ssh_key_creation))
            raise SystemExit(error)

    def prepare_snapshot(self, cfg):
        """
        Prepares snapshots of filesystem if not exists. Handles multiple
        invocations based on snapshot indicator file
        :param cfg: upgrade configuration
        """
        if not self.is_snapshots_supported():
            self.log.warning('Snapshots are not supported on this system. '
                             'Either this is cloud environment'
                             ' or LITP model is empty')
            return

        if check_snapshots_indicator_file_exists():
            try:
                self.validate_snapshots(cfg.verbose)
                self.log.info(
                        'Continue execution - upgrade snapshots'
                        ' have been already taken on this system and are '
                        'valid')
            except Exception:
                self.log.exception('Snapshots validation has failed')
                raise SystemExit(ExitCodes.INVALID_SNAPSHOTS)
            return

        log_header(self.log, 'Create the snapshots')
        if self.check_snapshots_exists(cfg.verbose):
            self.log.error('Stop execution - unexpected snapshots'
                           ' have been found')
            raise SystemExit(ExitCodes.ERROR)
        try:
            self.create_snapshots(cfg)
            self.validate_snapshots(cfg.verbose)
            create_snapshots_indicator_file()
        except Exception:
            self.log.exception('Snapshot preparation has failed')
            raise SystemExit(ExitCodes.INVALID_SNAPSHOTS)
        return

    def is_snapshots_supported(self):
        """
        Checks if snapshots are supported
        :return: True or False depends of SAN config in LITP or not
        """
        if is_physical_environment():
            self.log.info('Snapshots are supported'
                          ' in this physical environment')
            return True
        san_cleanup = SanCleanup()
        san_info = san_cleanup.get_san_info()
        if san_info:
            self.log.info('SAN configuration has been found in LITP model.'
                          ' Snapshots are supported'
                          ' in this virtual environment')
            return True
        else:
            self.log.info('LITP model does not contain SAN configuration.'
                          ' Snapshots are not supported'
                          ' in this virtual environment')
        return False

    def check_snapshots_exists(self, verbose):
        """
        Checks is any filesystem snapshots exist
        :param verbose: True to turn on verbose logging
        :return: True if some snapshots exist
        """
        snapper = EnmSnap(self.config)
        enm_snapshots.configure_logging(verbose)
        return snapper.check_any_snapshots_exist()

    @staticmethod
    def create_snapshots(cfg):
        """
        Creates snapshots of filesystems
        :param cfg: upgrade configuration
        """
        manage_snapshots(action='create_snapshot',
                         verbose=cfg.verbose,
                         lvm_snapsize=cfg.lvm_snapsize)

    @staticmethod
    def validate_snapshots(verbose):
        """
        Validates snapshots of filesystems
        :param verbose: True to turn on verbose logging
        """
        manage_snapshots(action='validate_snapshot', verbose=verbose)

    def _handle_exec_process(self, command, info_msg, error_msg,
                             allowed_error_codes=None):
        """
        Handles execution of external process
        :param command: command to execute
        :param info_msg: information to be displayed
        :param error_msg: error message
        :param allowed_error_codes: Optional list of allowed error codes
        :return: stdout generated by command
        :rtype: string
        """
        try:
            self.log.info(info_msg)
            self.log.debug('exec command {0}'.format(command))
            stdout = exec_process(command.split()).strip()
        except IOError as error:
            if allowed_error_codes and error.errno in allowed_error_codes:
                self.log.debug("Encountered allowed error {0}".format(
                                                              error.errno))
                stdout = ''
            else:
                self.log.exception(error_msg)
                raise SystemExit(ExitCodes.ERROR)
        for line in stdout.splitlines():
            self.log.debug(line)
        return stdout

    def _handle_exec_process_via_pipes(self, info_msg, error_msg, *commands):
        """
        Handles execution of piped external process
        :param info_msg: information to be displayed
        :param error_msg: error message
        :param command: commands to execute
        :return: stdout generated by command
        :rtype: string
        """
        try:
            self.log.info(info_msg)
            cmds_msg = [' '.join(i) for i in commands]
            cmds_msg = ' | '.join(cmds_msg)
            self.log.debug('exec command {0}'.format(cmds_msg))
            stdout = exec_process_via_pipes(*commands)
        except IOError:
            self.log.exception(error_msg)
            raise SystemExit(ExitCodes.ERROR)
        for line in stdout.splitlines():
            self.log.debug(line)
        return stdout

    def locate_packages(self, os_patch_tempdir, patch_rhel_ver):
        """
        Locates packages subdirectory inside unpacked os patch folder
        :param os_patch_tempdir: unpacked os patch folder
        :param patch_rhel_ver: the RHEL version the patch bundle
        is used for
        :return: full path to packages subdirectory
        :raise ValueError if packages subdirectory was not found
        """
        if patch_rhel_ver == self.rhel8_ver:
            baseos_on_iso = glob(os_patch_tempdir +
                                  '/RHEL/RHEL{0}_BaseOS*/Packages'
                                  .format(self.rhel8_ver))
            appstream_on_iso = glob(os_patch_tempdir +
                                     '/RHEL/RHEL{0}_AppStream*/Packages/'
                                     .format(self.rhel8_ver))
            if baseos_on_iso and appstream_on_iso:
                return baseos_on_iso[0], appstream_on_iso[0]
            error_str = ('Could not locate both Packages subdirectories '
                         'inside {0}'.format(os_patch_tempdir))
        else:
            for walk_root, _, _ in os.walk(os_patch_tempdir):
                if walk_root.endswith(('packages', 'Packages')):
                    return walk_root
            error_str = ('Could not locate packages subdirectory '
                            'inside {0}'.format(os_patch_tempdir))
        raise ValueError(error_str)

    @keyboard_interruptable(callback=import_iso.interrupt_handler)
    def upgrade_litp(self, cfg):
        """
        Upgrades LITP on MS node using executing import_iso script.
        Handles mount and umount and also interruption by the user
        :param cfg: upgrade configuration
        """
        log_header(self.log, 'Upgrade LITP')

        import_iso.set_import_iso_label(LABEL_LITP)

        import_iso.configure_logging(cfg.verbose)
        mnt_point = import_iso.create_mnt_dir()
        do_cleanup = True
        import_process_active = False
        try:
            import_iso.mount(mnt_point, cfg.litp_iso)
            import_process_active = True
            import_iso.litp_import_iso(mnt_point)
            import_iso_version.handle_litp_version_history(mnt_point)
            import_process_active = False
        except (KeyboardInterrupt, SystemExit):
            if import_process_active:
                # Dont unmount/delete the dir as the import is still
                # ongoing in the background, we were only monitoring it...
                do_cleanup = False
            raise
        finally:
            if do_cleanup:
                import_iso.cleanup_mnt_points()

    def check_patch_without_model(self):
        """
        Checks if --patch_rhel was passed previously to upgrade_enm.sh
        without model and sed arguments.
        Reads a file ms_os_patched_done and returns True or False
        """
        should_patch = False
        if isfile(self.ms_patched_done_file):
            _line = open(self.ms_patched_done_file).readline().strip()
            should_patch = _line == 'patch_without_model'
        return should_patch

    def _import_repos(self, cfg):
        """
        Import (using LITP Import) repositories for patch sets on OS
        :param cfg: upgrade configuration
        """
        for patch_file in cfg.os_patch:
            file_execute_command = "file -b " + patch_file
            self.log.info('Unpacking patch file {0}'.format(patch_file))
            stdout = self._handle_exec_process(
                file_execute_command,
                'Executing file command to determine file type for {0}'\
                    .format(patch_file),
                'Problem occurred while trying to determine file type for'
                    + ' {0}.'\
                    .format(patch_file))
            if re.search(ISO_FILE_TYPE, stdout):
                mnt_point = None
                try:
                    import_iso.set_import_iso_label(LABEL_OS_PATCHES)
                    mnt_point = import_iso.create_mnt_dir()
                    import_iso.mount(mnt_point, patch_file)
                    self.log.debug('Mounting patch ISO {0} to {1}'.
                                   format(patch_file, mnt_point))
                    os_patch_config_script = mnt_point \
                                         + '/RHEL/config_patches.sh'
                    self.execute_config_script(os_patch_config_script)
                    self.read_cxp_import(patch_file, mnt_point)
                finally:
                    if mnt_point:
                        import_iso.umount(mnt_point)
                        self.log.info('Removing {0} '.format(mnt_point))
                        import_iso.cleanup_mnt_points()

            elif re.search(TGZ_FILE_TYPE, stdout):
                os_patch_tempdir = ''
                tar = None
                try:
                    os_patch_tempdir = mkdtemp(dir='/software')
                    os_patch_config_script = os_patch_tempdir \
                                         + '/RHEL/config_patches.sh'
                    tar = tarfile.open(patch_file)
                    self.log.debug('Extracting {0} to {1}'.
                                   format(patch_file,
                                          os_patch_tempdir))
                    tar.extractall(path=os_patch_tempdir)
                    self.execute_config_script(os_patch_config_script)
                    self.read_cxp_import(patch_file, os_patch_tempdir)
                finally:
                    if tar:
                        tar.close()
                    try:
                        self.log.info('Removing {0} '.format(
                                                    os_patch_tempdir))
                        shutil.rmtree(os_patch_tempdir)
                    except OSError:
                        pass
            else:
                self.log.error("Filetype for patchset does not match"
                        " .tar.gz or .iso formats!")
                raise SystemExit(ExitCodes.ERROR)

    def execute_config_script(self, os_patch_config_script):
        """
        Checks for presence and properties of config script in extracted patch
        file.
        :param os_patch_config_script: Path to config script in patch file.
        """
        if isfile(os_patch_config_script) and \
                os.access(os_patch_config_script, os.X_OK):
            stdout = self._handle_exec_process(
                os_patch_config_script,
                'Executing patch file config script',
                'Problem occured executing patch file '
                'config script')
            self.log.info('Output from patch file '
                          'config script\n{0}'
                          .format(stdout))

    def read_cxp_import(self, patch_file, os_patch_tempdir):
        # pylint: disable=R0914
        """
        Read patch CXP number from patch version RPM in tarball
        and determine appropriate repo for LITP import.
        :param patch_file: patch file
        :param os_patch_tempdir: directory to which patch has been extracted
        """
        cmd_find_rhel_rpm = ('find {0}/RHEL/ -name '
                             'RHEL_OS_Patch_Set_CXP*').format(os_patch_tempdir)

        rpm_path = self._handle_exec_process(cmd_find_rhel_rpm,
                                             'Determining RHEL Version '
                                             'RPM path',
                                             'Problem determining '
                                             'RPM path')

        if not rpm_path:
            self.log.error('Cannot find RHEL_OS_Patch_Set RPM in '
                           'the archive {0}'.format(patch_file))
            raise SystemExit(ExitCodes.ERROR)

        patch_details = self.\
            _handle_exec_process_via_pipes('Determining CXP '
                                           'Number of Patch Set',
                                           'Problem determining '
                                           'CXP number',
                                           cmd_find_rhel_rpm.split(),
                                           ['xargs', 'rpm2cpio'],
                                           ['cpio', '-i', '--to-stdout'],
                                           ['egrep', '"rhel_version":|"cxp":'])

        patch_cxp_pattern = re.search('"cxp": "(\\d+)"', patch_details)
        if not patch_cxp_pattern:
            self.log.error('Invalid patch file %s, does not contain CXP '
                           'number!' % patch_file)
            raise SystemExit(ExitCodes.ERROR)
        patch_cxp = patch_cxp_pattern.group(1)
        patch_rhel_ver_pattern = re.search('"rhel_version":'
                                           ' "(\\d+.\\d+)"', patch_details)

        if not patch_rhel_ver_pattern:
            self.log.error('Invalid patch file %s, '
                           'does not contain CXP number!' % patch_file)
            raise SystemExit(ExitCodes.ERROR)
        patch_rhel_ver = patch_rhel_ver_pattern.group(1)
        self.rhel_patch_cxps[patch_rhel_ver] = patch_cxp

        if patch_rhel_ver == self.rhel_util.get_latest_version() \
                and not self.rhel7_9_copied:
            self.log.error('A RHEL 7.9 patchset has been detected, but '
                           'the RHEL 7.9 DVD ISO has not been copied '
                           'to the MS')
            self.log.error('Please ensure the RHEL 7.9 DVD ISO is copied to '
                           'the MS by providing the \'--rhel7_9_iso\' '
                           'argument')
            raise SystemExit(ExitCodes.ERROR)

        if patch_rhel_ver not in self.valid_rhel_patch_versions:
            self.log.error('The RHEL patchset information has an invalid '
                           'version')
            raise SystemExit(ExitCodes.ERROR)

        release = self.config.get(self.vers_conf_key_map[patch_rhel_ver] +
                                  '_release')
        updates_repo_dir = self.set_repo_information(release,
                                                        patch_rhel_ver,
                                                        rpm_path)
        if patch_rhel_ver == self.rhel8_ver:
            rhel8_baseos = '{0}/{1}/updates_BaseOS/x86_64/Packages'.format(
                            WEB_ROOT, self.rhel8_ver)
            rhel8_appstream = '{0}/{1}/updates_AppStream/x86_64/Packages' \
                .format(WEB_ROOT, self.rhel8_ver)

            baseos_on_iso, appstream_on_iso = self.locate_packages(
                os_patch_tempdir, patch_rhel_ver)

            if not os.path.isdir(rhel8_baseos):
                self.log.debug('Ensuring directory {0}'.format(rhel8_baseos))
                os.makedirs(rhel8_baseos)
            if not os.path.isdir(rhel8_appstream):
                self.log.debug('Ensuring directory {0}'
                                .format(rhel8_appstream))
                os.makedirs(rhel8_appstream)

            self.log.info('Copying content from {0} to {1}'
                            .format(baseos_on_iso,
                                    rhel8_baseos))
            litp_import_baseos_cmd = '/usr/bin/litp import {0} {1}' \
            .format(baseos_on_iso, rhel8_baseos)
            self._handle_exec_process(litp_import_baseos_cmd,
            'LITP is importing BaseOS packages', 'Problem with litp import')

            self.log.debug('Copying content from RHEL8 Patch AppStream to {0}'
                           .format(rhel8_appstream))
            self.import_appstream_from_iso(appstream_on_iso, rhel8_appstream)
        else:

            import_packages_directory = \
                self.locate_packages(os_patch_tempdir, patch_rhel_ver)

            litp_import_cmd = '/usr/bin/litp import {0} {1}' \
                .format(import_packages_directory,
                        updates_repo_dir)

            self._handle_exec_process(litp_import_cmd,
                                    'LITP is importing packages',
                                    'Problem with litp import')

    def import_appstream_from_iso(self, iso_path, repo_path):
        """
        Determine if the installed litp core version < 2.18.1.
        If so, use rsync for importing the patch bundle AppStream repo
        otherwise use litp import
        :param iso_path: The path to the AppStream repo on the mounted
        patch bundle
        :param repo_path: The directory the AppStream repo will be
        extracted to
        """
        litp_core_ver = get_rpm_info(gethostname(),
                                     "ERIClitpcore_CXP9030418")['version']
        litp_core_comparison = compare_versions(litp_core_ver, '2.18.1')
        if litp_core_comparison == "smaller":
            cmd = 'rsync -rtd --delete-before {0} {1}'.format(
                iso_path, repo_path)
            info_msg, error_msg = 'Copying RHEL8 AppStream content', \
                'Problem copying AppStream content'
        else:
            cmd = '/usr/bin/litp import {0} {1}' \
            .format(iso_path, repo_path)
            info_msg, error_msg = 'LITP is importing Appstream packages', \
                'Problem with litp import'
        self._handle_exec_process(cmd, info_msg, error_msg)

    def set_repo_information(self, release, rhel_ver, rpm_path):
        """
        Set RHEL repo information
        """
        self.log.info('Applying RHEL {0} patch set'
                      .format(rhel_ver))
        updates_repo_dir = '/var/www/html/{0}/updates/x86_64/Packages'\
            .format(rhel_ver)
        patch_set_package_base = 'RHEL_OS_Patch_Set_CXP'

        if rhel_ver not in self.valid_rhel_patch_versions:
            self.log.error('The RHEL patchset information has an invalid '
                           'version')
            raise SystemExit(ExitCodes.ERROR)

        config_key_prefix = self.vers_conf_key_map[rhel_ver]
        patch_set_package_iso = patch_set_package_base + \
                                self.config.get(config_key_prefix +
                                                '_os_patch_cxp_iso')
        version_file = self.config.get(config_key_prefix + '_version_filename')
        history_file = self.config.get(config_key_prefix + '_history_filename')

        if rhel_ver == self.rhel7_ver:
            patch_set_package_tgz_7 = patch_set_package_base + \
                                      self.config.get(
                                          'rhel7_os_patch_cxp_tgz')
            patch_set_package_iso_7 = patch_set_package_base + \
                                       self.config.get(
                                           'rhel7_os_patch_cxp_iso')

            remove_rpm(patch_set_package_tgz_7)
            remove_rpm(patch_set_package_iso_7)
            if not os.path.isdir(updates_repo_dir):
                os.makedirs(updates_repo_dir)
        remove_rpm(patch_set_package_iso)

        self.rhel_os_patch_rpms[rhel_ver] = {
            'rpm_name': "RHEL_OS_Patch_Set_CXP{0}"
                .format(self.rhel_patch_cxps[rhel_ver]),
            'rpm_path': rpm_path,
            'release': release,
            'version_file': version_file,
            'history_file': history_file
        }

        install_rpm(self.rhel_os_patch_rpms[rhel_ver]['rpm_name'],
                    self.rhel_os_patch_rpms[rhel_ver]['rpm_path'])
        return updates_repo_dir

    def write_patched_file(self):
        """
        Write file indicating which patches have been completed
        """
        with open(self.ms_patched_done_file, 'a') as _writer:
            if set(sys.argv).isdisjoint(NOT_ONLY_PATCH):
                _writer.write('patch_without_model\n')

            for version in set(self.rhel_os_patch_rpms) & \
                           set(self.valid_rhel_patch_versions):
                _writer.write('patch_with_CXP{0}\n'
                              .format(self.rhel_patch_cxps[version]))

    def apply_os_patches(self, cfg):
        """
        Applies OS patches on MS node. Unpack patch file, imports using
        LITP import command and upgrades packages on MS node using Yum.
        Checks if reboot is required after packages upgrade and performs
        shutdown according to upgrade options.
        :param cfg: upgrade configuration
        """
        log_header(self.log, 'Apply OS Patches')
        try:
            self._import_repos(cfg)
            self._disable_puppet_in_ms()
            self.rhel_util.ensure_version_symlink(self.rhel7_ver)
            self.rhel_util.ensure_version_symlink(self.rhel8_ver)
            self._handle_exec_process(YUM_CLEAN_ALL_CMD,
                                      'Yum is cleaning cache',
                                      'Problem with yum clean')

            if (self.rhel7_ver in self.rhel_os_patch_rpms and
                    self.check_for_os_patch_updates()):
                self._handle_exec_process(YUM_UPGRADE_USING_UPDATES_REPO_CMD,
                                          'Yum is upgrading packages',
                                          'Problem with yum upgrade')
                self.version_update(self.rhel7_ver)
            else:
                self.log.info('OS Patches are up to date - '
                              'no update needed')

            if self.rhel8_ver in self.rhel_os_patch_rpms:
                self.version_update(self.rhel8_ver)

            self.rhel_util.ensure_version_manifest(self.rhel7_ver)
            self._enable_puppet_in_ms()

            self.write_patched_file()

            self.reboot_required = self.check_reboot_required()
            self.check_and_reboot_celery()
            if self.reboot_required:
                self.disable_puppet_on_nodes()
                self.handle_reboot(cfg)
        except Exception:
            self.log.exception('Apply OS Patches has failed')
            raise SystemExit(ExitCodes.ERROR)

    def _disable_puppet_in_ms(self):
        """
        Disable Puppet on MS
        """
        ms_hostname = os.uname()[1]

        self._handle_exec_process(PUPPET_DISABLE_MS_CMD,
                                  'Puppet is being disabled',
                                  'Problem while disabling Puppet')
        PuppetExecutionProcessor(max_iterations=240,
                                 wait_interval=5).wait([ms_hostname])

    def _enable_puppet_in_ms(self):
        """
        Enable Puppet on MS
        """
        self._handle_exec_process(PUPPET_ENABLE_MS_CMD,
                                  'Puppet is being enabled',
                                  'Problem while enabling Puppet')

    def version_update(self, patch_version):
        """
        Update history version information
        :param patch_version:
        """
        import_iso_version.update_rhel_version_and_history(
            self.rhel_os_patch_rpms[patch_version]['release'],
            self.rhel_os_patch_rpms[patch_version]['version_file'],
            self.rhel_os_patch_rpms[patch_version]['history_file'])

    def check_for_os_patch_updates(self):
        """
        Checks if OS Patches updates are available
        :return: boolean indicating availability of updates
        """
        self.log.debug('Checking if OS Patch updates are available')
        try:
            exec_process(YUM_CHECK_UPGRADE_USING_UPDATES_REPO_CMD.split())
            return False
        except IOError as error:
            if error.errno == 100:
                # updates are available
                return True
            else:
                raise

    def get_postgres_active_host(self):
        ''' Find postgres active host
        '''
        info, _ = Vcs.get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                               '.*postgres_clustered_service',
                                               verbose=False)
        for entry in info:
            if entry[Vcs.H_SERVICE_STATE] == 'ONLINE':
                self.log.info('Active postgres node is {0}'.
                                 format(entry[Vcs.H_SYSTEM]))
                return [entry[Vcs.H_SYSTEM]]

    def postgres_reload(self):
        """
        Reload postgres at postupgrade stage
        """
        p_agent = PostgresAgent()
        phost = self.get_postgres_active_host()
        p_agent.call_postgres_service_reload(phost)

    def harden_neo4j(self):
        """
        Harden Neo4j: PKey stored in Vault, passwords stored in consul
        """
        harden_script = \
            '/opt/ericsson/nms/litp/lib/scripts/neo4j_hardening_password.sh'
        if not os.path.exists(harden_script):
            self.log.info('Neo4j hardening script {0} not found.'.format(
                harden_script))
            return

        confirm_cmd = ['echo', 'YeS']
        harden_cmd = [
            harden_script, '--run_initial_neo4j_hardening']
        out = self._handle_exec_process_via_pipes('Hardening Neo4j',
                                        'Hardening Neo4j has failed',
                                                   confirm_cmd, harden_cmd)
        self.log.info('Neo4j hardening completed: {0}'.format(out))

    def is_puppet_running_on_nodes(self):
        """
        Get Puppet is_running count and compare to zero.
        :rtype: boolean
        :return: True if number Puppets running is non-zero,
                 else False
        """
        info_msg = 'Getting Puppet is_running count ...'
        err_msg = 'Failed to get Puppet is_running count'
        stdout = self._handle_exec_process_via_pipes(info_msg, err_msg,
                    ['mco', 'rpc', 'puppetlock', 'is_running', '2>/dev/null'],
                    ['egrep', '^ *Result: true *$'],
                    ['wc', '-l'])
        running_count = stdout.strip()
        self.log.info('Puppets running: {0}'.format(running_count))
        return '0' != running_count

    def handle_reboot(self, cfg):
        """
        Handles reboot according to upgrade options
        :param cfg: upgrade options
        """
        log_header(self.log, 'System shutdown')
        upgrade_next_step_msg = 'Please continue the upgrade after restart ' \
                                'to propagate the updates to peer nodes'
        if cfg.noreboot:
            self.log.info('Please shutdown the system manually. {0}'.format(
                    upgrade_next_step_msg))
        else:
            timeout = 0
            while self.is_puppet_running_on_nodes():
                if 1800 <= timeout:
                    self.log.warn("Puppet run didn't finish within 30 minutes")
                    break
                elif 0 == timeout % 5:
                    self.log.info(('Have waited {0} seconds for Puppet to '
                                   'stop running').format(timeout))
                time.sleep(3)
                timeout += 3

            shutdown_cmd = '/sbin/shutdown -r now'
            self._handle_exec_process(
                    shutdown_cmd, 'Shutting down the system. ' +
                                  upgrade_next_step_msg,
                    'Shutdown has failed')

    def check_and_reboot_celery(self):
        """
        Checks if Celery reboot is required based on changes to
        RHEL_OS_Patch_Set_CXP9041797 TORF-618805 (Firefox patch).
        Retrieves package info from yum and checks if it is greater than
        1.14.1 and if so then it is restarted
        """
        get_package_cmd = "yum list RHEL_OS_Patch_Set_CXP9041797.noarch"
        package_name = self._handle_exec_process(
            get_package_cmd, 'Getting RHEL_OS_Patch_Set_CXP9041797',
            'Failed Getting RHEL_OS_Patch_Set_CXP9041797')
        try:
            installed_version = re.search(
                r'RHEL_OS_Patch_'r'Set_CXP9041797.noarch'r'\s*([\d.]+)',
                package_name).group(1)
        except AttributeError:
            installed_version = re.search(
                r'RHEL_OS_Patch_'r'Set_CXP9041797.noarch'r'\s*([\d.]+)',
                package_name)

        restart_celery_cmd = "systemctl restart celery"
        restart_celerybeat_cmd = "systemctl restart celerybeat"

        ver_reboot_necessary_from = "1.14.1"
        result = compare_versions(installed_version, ver_reboot_necessary_from)
        if result == "bigger" or result == "equal":
            self._handle_exec_process(
                restart_celery_cmd, 'Restarting Celery',
                'Restarting Celery has failed')
            self._handle_exec_process(
                restart_celerybeat_cmd, 'Restarting Celerybeat',
                'Restarting Celerybeat has failed')
        else:
            self.log.info('No Celery Restart Needed')

    def check_reboot_required(self):
        """
        Checks if reboot is required based on kernel release comparison.
        Retrieves from RPM database last installed kernel package and extracts
        its release. Then extract release of current kernel.
        :return: True if last installed kernel release is different then
        current release, False otherwise
        """

        rpm_query_results = \
            self._handle_exec_process(RPM_QUERY_KERNEL_BY_LAST,
                                      'Query kernel packages',
                                      'Query kernel packages has failed')

        current_kernel_release = uname()[UNAME_INDEX_RELEASE]

        self.log.info('Current kernel release is :               {0}'
                      .format(current_kernel_release))

        lines = rpm_query_results.splitlines()
        last_kernel_release = None
        if lines:
            _match = re.match(EXTRACT_KERNEL_RELEASE_REGEXP, lines[0])
            if _match:
                last_kernel_release = _match.group(1).strip()
                self.log.info('Release of the last installed kernel is : {0}'
                              .format(last_kernel_release))
                if last_kernel_release == current_kernel_release:
                    self.log.info('Reboot is not required '
                                  '- kernel release has not changed')
                    return False
        if last_kernel_release is None:
            self.log.warning('Unable to determine '
                             'the release of last installed kernel')
        self.log.warning('Reboot is required to update the kernel')
        return True

    @staticmethod
    def import_enm_iso_for_upgrade(upgrade_args):
        """
        Imports ENM iso for upgrade
        :param upgrade_args: configuration for import
        :return:
        """
        iso_contents = import_iso.main_flow(upgrade_args.enm_iso,
                                            verbose=upgrade_args.verbose)

        doyler = EnmLmsHouseKeeping()
        doyler.housekeep_images(iso_contents[import_iso.ISO_CONTENTS_IMAGES])
        doyler.housekeep_yum(iso_contents[import_iso.ISO_CONTENTS_YUM])

    def litp_upgrade_deployment(self):
        """
        Executes litp command upgrading ENM deployment
        """
        log_header(self.log, 'Litp Upgrade of /deployment/enm')
        try:
            self.litp.upgrade('/deployments/enm')
        except LitpException as error:
            message = error.get_default_message()
            if message:
                self.log.error('Failed to upgrade deployment: %s' % message)
            self.log.exception('Failed to upgrade deployment')
            raise SystemExit(ExitCodes.ERROR)

    def litp_disable_reboot_tasks(self, cluster_list=None):
        """
        Executes litp command to disable node reboots
        """
        log_header(self.log, 'Disable node reboots')
        properties = {'disable_reboot': 'true'}
        try:
            all_cluster_nodes = self.litp.get_cluster_nodes()
            for disable_reboot_cluster in cluster_list:
                if disable_reboot_cluster in all_cluster_nodes:
                    for node in all_cluster_nodes[disable_reboot_cluster]:
                        if self.litp.exists(
                            all_cluster_nodes[disable_reboot_cluster][node].
                            path + '/upgrade'):
                            self.litp.update(
                                all_cluster_nodes[disable_reboot_cluster][node]
                                .path + '/upgrade', properties)
        except LitpException as error:
            message = error.get_default_message()
            if message:
                self.log.error('Failed to upgrade deployment: %s' % message)
            self.log.exception('Failed to upgrade deployment')
            raise SystemExit(ExitCodes.ERROR)

    def litp_set_global_property(self, name, value):
        """
        Executes litp command to set a global property
        """
        log_header(self.log, 'Update global properties')
        properties = {'key': name, 'value': value}
        try:
            self.log.info("Setting " + name + " to " + value)
            path = '/software/items/config_manager/global_properties'
            self.litp.create(path, name, 'config-manager-property', properties)
        except LitpException as error:
            if 'already exists' in str(error):
                return
            message = error.get_default_message()
            if message:
                self.log.error('Failed to upgrade deployment: %s' % message)
            self.log.exception('Failed to upgrade deployment')
            raise SystemExit(ExitCodes.ERROR)

    def litp_set_cs_initial_online(self, value, cluster_list=None):
        """
        Executes litp command to set  cs_initial_online
        """
        log_header(self.log, 'Update cs_initial_online property')
        properties = {'cs_initial_online': value}
        try:
            deployments = self.litp.get_children('/deployments')
            for _deployment in deployments:
                deployment_id = _deployment['data']['id']
                path = '/deployments/{0}/clusters/'.format(deployment_id)
                clusters = self.litp.get_children(path)
                for cluster in clusters:
                    if cluster['data']['id'] in cluster_list:
                        path = cluster['path']
                        self.litp.update(path, properties, verbose=True)
        except LitpException as error:
            message = error.get_default_message()
            if message:
                self.log.error('Failed to upgrade deployment: %s' % message)
            self.log.exception('Failed to upgrade deployment')
            raise SystemExit(ExitCodes.ERROR)

    def encrypt_passwords(self, upgrade_args):
        """
        Encrypts password required for substitution in model xml.
        Prepare temporary file to store the encrypted passwords
        :param upgrade_args configuration for password encryption
        """
        self.passwords_store_file = NamedTemporaryFile(delete=False)

        class EncryptPasswordArgs(object):  # pylint: disable=R0903
            """
            Wrapper for argument to pass to encrypt()
            """
            verbose = upgrade_args.verbose
            sed_file = upgrade_args.sed_file
            passwords_store = self.passwords_store_file.name
            upgrade = "--upgrade"

        encrypt_passwords.encrypt(EncryptPasswordArgs)

    @staticmethod
    def crypto_service():
        """
        Invokes crypto_service method to create the encryption key
        at the end of upgrade
        """

        class CryptoServiceArgs(object):  # pylint: disable=R0903
            """
            Wrapper for argument to pass to crypto_service()
            """
            verbose = True

        crypto_service.crypto_service(CryptoServiceArgs)

    @staticmethod
    def update_ms_uuid():
        """
        Add root disk uuid to enminst_working.cfg file
        """
        ms_uuid.update_uuid()

    @staticmethod
    def update_ssh_key():
        """
        Generate/Update ssh keys for KVM access
        """
        ssh_key_creation.main([])

    def sub_xml_params(self, upgrade_args):
        """
        Substitutes parameters in XML deployment templates.
        Removes temporary file storing encrypted passwords
        :param upgrade_args configuration for parameters substitution
        """
        if self.passwords_store_file is None:
            raise ValueError('passwords_store_file is not defined')

        if not os.path.isfile(self.passwords_store_file.name):
            raise ValueError('passwords_store_file %s does not exist'
                             % self.passwords_store_file.name)

        log_header(self.log, "Substitute XML parameters")
        try:
            class SubstituteArgs(object):  # pylint: disable=R0903
                """
                Wrapper for argument to pass to substitute()
                """
                verbose = upgrade_args.verbose
                sed_file = upgrade_args.sed_file
                xml_template = upgrade_args.model_xml
                property_file = self.passwords_store_file.name

            substitute_parameters.substitute(SubstituteArgs)
        except Exception:
            self.log.exception("Failed to substitute parameters using "
                               "parameters: %s source: %s"
                               % (upgrade_args.sed_file,
                                  upgrade_args.model_xml)
                               )
            raise SystemExit(ExitCodes.ERROR)
        finally:
            try:
                os.remove(self.passwords_store_file.name)
            except OSError:
                pass
        self.log.info('Substitute XML parameters completed successfully')

    def load_xml(self, upgrade_cfg):
        """
        Prepare arguments and call Deployer to load XML plan
        :param upgrade_cfg: upgrade configuration
        """
        log_header(self.log, 'Load XML Plan')

        self.log.debug('Checking variables used in load_run_plan')

        self.log.info('Deploying ENM using runtime XML deployment %s'
                      % self.runtime_xml_deployment)

        try:
            deployer.deploy(self.runtime_xml_deployment,
                            verbose=upgrade_cfg.verbose,
                            create_run_plan=False,
                            load_plan=True,
                            run_type="ENM Deployment - Load XML Plan")
        except Exception:
            self.log.exception('Failed to execute Load XML Plan')
            raise SystemExit(ExitCodes.ERROR)
        self.log.info('Load XML Plan completed successfully')

    def update_model_vm_images(self):
        """
        Updates LITP model properties changed after ISO import
        """
        log_header(self.log, 'Update LITP vm image properties')

        params_filename = self.config['enminst_working_parameters']

        working_params = Sed(params_filename)
        log_header(self.log, working_params)
        images_list = self.litp.get_children(SOFTWARE_IMAGES_PATH)
        log_header(self.log, images_list)
        for image_item in images_list:
            item = image_item['data']
            self.__update_model_vm_image(working_params, item)

    def __update_model_vm_image(self, params, item):
        """
        Updates model image property if its 'source_uri' value has changed.
        :param params: params dictionary
        :param item: vm image item JSON structure
        """
        item_id = item['id']
        param_name = item_id
        if item_id in ENMUpgrade.MAP_VM_IMAGE_TO_PARAM_NAME:
            param_name = ENMUpgrade.MAP_VM_IMAGE_TO_PARAM_NAME[item_id]
            self.log.warn('VM Image \'{0}\' mapped to property \'{1}\''
                          .format(item_id, param_name))

        new_image_filename = params.get_value(param_name)

        old_source_uri = item[KEY_PROPERTIES][KEY_SOURCE_URI]
        self.log.debug('Old source_uri is \'{0}\''.format(old_source_uri))

        old_url = urlparse(old_source_uri)
        old_image_filename = os.path.basename(old_url.path)
        old_image_dirname = os.path.dirname(old_url.path)

        new_url_path = old_image_dirname + '/' + new_image_filename
        new_url_parts = list(old_url)
        new_url_parts[URL_PATH_INDEX] = new_url_path
        new_source_uri = urlunparse(new_url_parts)
        self.log.debug('New source_uri is \'{0}\''.format(new_source_uri))

        if new_source_uri == old_source_uri:
            self.log.info('VM Image \'{0}\' value \'{1}\' has not changed'
                          .format(item_id, old_image_filename))
        else:
            new_properties = item[KEY_PROPERTIES]
            new_properties[KEY_SOURCE_URI] = new_source_uri
            self.litp.update(SOFTWARE_IMAGES_PATH + '/' + item_id,
                             new_properties, verbose=False)
            _msg = 'VM Image \'{0}\' has changed from \'{1}\' to ' \
                   '\'{2}\''.format(item_id, old_image_filename,
                                    new_image_filename)
            self.log.info(_msg)

    def create_run_plan(self, upgrade_cfg):
        """
        Prepares arguments and calls Deployer to create and run a LITP plan
        :param upgrade_cfg configuration to create and run the plan
        """
        log_header(self.log, 'Create and Run Plan')
        deploy_no_lock_tasks_list = None
        deploy_no_lock_tasks = None

        if self.gossip_upgrade:
            deploy_no_lock_tasks_list = GOSSIP_AFFECTED_CLUSTERS
            deploy_no_lock_tasks = True

        if self.infra_plan:
            deploy_no_lock_tasks_list = INFRASTRUCTURE_CLUSTERS
            deploy_no_lock_tasks = True

        try:
            deployer.deploy(verbose=upgrade_cfg.verbose,
                            create_run_plan=True,
                            load_create_plan=False,
                            run_type="ENM Deployment - Create and Run Plan",
                            no_lock_tasks=deploy_no_lock_tasks,
                            no_lock_tasks_list=deploy_no_lock_tasks_list)

        except LitpException as error:
            handled_exception = error.get_key_value(key='type',
                                                    value='DoNothingPlanError')
            if handled_exception:
                self.log.info('No tasks were generated to run the plan')
            else:
                self.log.exception("Failed to execute create_run_plan")
                raise SystemExit(ExitCodes.ERROR)
        except Exception:
            self.log.exception("Failed to execute create_run_plan")
            raise SystemExit(ExitCodes.ERROR)
        except SystemExit:
            if not self.infra_plan and not self.gossip_upgrade:
                self.litp.restore_model()
                self.persist_stage_data(UPGRADE_PLAN, STATE_FAILED)
            self.log.exception("Failed to execute create_run_plan")
            raise SystemExit(ExitCodes.ERROR)

        self.log.info('Create and Run Plan completed successfully')

    def monitor_plan(self, upgrade_cfg):
        """
        Prepares arguments and calls Deployer to monitor the LITP plan
        :param upgrade_cfg configuration of the running plan
        """
        log_header(self.log, 'Monitor Plan')

        try:
            deployer.monitor(verbose=upgrade_cfg.verbose)
        except Exception:
            self.log.exception("Failed to execute monitor_plan")
            raise SystemExit(ExitCodes.ERROR)

        self.log.info('Monitor Plan completed successfully')

    def post_upgrade(self):
        """
        Executes post upgrade operations
        :return: None
        """
        es_admin_pwd_file = "/opt/ericsson/enminst/bin/esadmin_password_set.sh"
        pib_reset_execution_file = "/ericsson/pib-scripts/scripts/" \
                                   "pib_reset_status_all.sh"
        log_header(self.log, "Post upgrade")
        deployer.Deployer.update_version_and_history()
        switch_dbcluster_groups()
        db_creds = DbNodesSshCredentials()
        db_creds.remove_cred_file()
        litp_backup_state_cron('/etc/cron.d/litp_state_backup',
                               '/ericsson/tor/data/enmbur/lmsdata/')
        cleanup_java_core_dumps_cron('/etc/cron.daily/cleanup_java_core_dumps')
        create_san_fault_check_cron('/etc/cron.d/san_fault_checker')
        self.cleanup_log4j_ec_files()
        nas_type = get_nas_type(self.litp)
        if nas_type == 'veritas':
            create_nasaudit_errorcheck_cron('/etc/cron.d/nasaudit_error_check')
        # noinspection PyBroadException
        try:
            enm_version.display_log_enminst()
        except Exception:  # pylint: disable=W0703
            self.log.warning('Failed to show versions of ENM system. '
                             'This problem does not affect '
                             'status of the upgrade operation.', exc_info=True)
        if os.path.isfile(es_admin_pwd_file):
            self.log.info('es admin password file exists')
            try:
                ret = os.system('sh {0}'.format(es_admin_pwd_file))
                if int(ret) == 0:
                    self.log.info('Execution of esadmin_password_set script '
                                           'successful')
                else:
                    self.log.info('Execution of esadmin_password_set script '
                                           'failed')
            except Exception:  # pylint: disable=W0703
                self.log.warning('Failed to execute '
                                 'esadmin_password_set script', exc_info=True)

        if os.path.isfile(pib_reset_execution_file):
            self.log.info('pib reset status all file exists')
            try:
                ret = os.system('sh {0}'.format(pib_reset_execution_file))
                if int(ret) == 0:
                    self.log.info('Execution of pib_reset_status_all script '
                                  'successful')
                else:
                    self.log.error('Execution of pib_reset_status_all script '
                                  'failed')
            except Exception:  # pylint: disable=W0703
                self.log.error('Failed to execute '
                                 'pib_reset_status_all script', exc_info=True)

    def verify_dd_expanding_nodes(self, cfg):
        """
        Check if the deployment description would result in expanding
        nodes or clusters then raise error and exit script if expansion
        flag is not added.
        :param cfg: parsed configuration parameters
        """
        if cfg.model_xml:
            proposed_dd = load_xml(cfg.model_xml)
            dd_cluster_nodes = {}
            clusters = xpath(proposed_dd, 'vcs-cluster')
            for cluster in clusters:
                nodes = xpath(cluster, 'node')
                dd_cluster_nodes[cluster.get('id')] = len(nodes)

            model_hosts = self.litp.get_cluster_nodes()
            is_expansion = False
            for cluster in dd_cluster_nodes:
                if cluster in model_hosts:
                    if dd_cluster_nodes[cluster] > \
                            len(model_hosts[cluster]):
                        is_expansion = True
                else:
                    is_expansion = True
                if is_expansion:
                    self.log.error("Deployment description would result in an "
                                   "expansion of nodes but expansion flag is "
                                   "not provided with the command")
                    raise SystemExit(ExitCodes.ERROR)

    @classmethod
    def neo4j_pre_check(cls):
        """
        If neo4j is install but not used by dps
        then offline and freeze neo4j
        """
        vcs = Vcs()
        vcs.neo4j_set_state()

    def process_arguments(self, parser, upgrade_args):
        """
        Additional logic to validate command line arguments
        :param parser
        :param upgrade_args: parsed arguments
        """
        log_header(self.log, "Process Upgrade options")

        if upgrade_args.resume:
            args_ok = True

            # --resume should not be accompanied by any of the main params
            for arg in ENMUpgrade.MAIN_UPGRADE_PARAMS:
                if getattr(upgrade_args, arg):
                    parser.error('--resume parameter invalidly used '
                                 'with other parameters')
                    args_ok = False
                    break
        else:
            args_ok = upgrade_args.os_patch or upgrade_args.litp_iso
            args_ok = args_ok or upgrade_args.enm_iso
            args_ok = args_ok or upgrade_args.sed_file
            args_ok = args_ok or upgrade_args.model_xml
            args_ok = args_ok or upgrade_args.rhel7_9_iso

        if not args_ok:
            parser.print_usage()
            raise SystemExit(ExitCodes.INVALID_USAGE)

        if upgrade_args.rhel7_9_iso and upgrade_args.os_patch is None:
            parser.error('RHEL upgrade requires OS Patch (--patch_rhel) '
                         'option to be supplied')

        if upgrade_args.os_patch is None and upgrade_args.noreboot:
            parser.error('Option noreboot is allowed '
                         'only if OS_PATCH is set')

        if upgrade_args.os_patch is not None and \
                len(upgrade_args.os_patch) > 1:
            if filecmp.cmp(upgrade_args.os_patch[0], upgrade_args.os_patch[1]):
                self.log.exception('Same patch file supplied twice')
                raise SystemExit(ExitCodes.ERROR)

        if operator.xor(upgrade_args.sed_file is None,
                        upgrade_args.model_xml is None) and \
                not upgrade_args.internal_model:
            parser.error('Upgrade requires both SED and Model '
                         'XML options')

        if self.check_patch_without_model() and upgrade_args.model_xml:
            self.log.error('Upgrade was previously ran with --patch_rhel '
                           'argument without --model. Upgrade requires '
                           'model and sed args to be removed to complete '
                           'OS patch upgrade of blades.')
            raise SystemExit(ExitCodes.INVALID_USAGE)

        invalid_internal_model = (upgrade_args.enm_iso,
                                  upgrade_args.litp_iso,
                                  upgrade_args.lvm_snapsize,
                                  upgrade_args.model_xml,
                                  upgrade_args.noreboot,
                                  upgrade_args.os_patch,
                                  upgrade_args.regenerate_keys,
                                  upgrade_args.resume)

        if upgrade_args.internal_model and any(invalid_internal_model):
            parser.error('--internal_model_only used invalidly '
                         'with other parameters')
        if not upgrade_args.expansion_upgrade:
            self.verify_dd_expanding_nodes(upgrade_args)

        self.log.info("Arguments processed successfully")

    @staticmethod
    def image_version_cfg(iso):
        """
        Update enminst working config with image versions from ISO
        :param iso: ISO containing ENM images
        :return:
        """
        import_iso.read_config()
        mnt_point = import_iso.create_mnt_dir()
        try:
            import_iso.mount(mnt_point, iso)
            import_iso.update_images(mnt_point)
        finally:
            import_iso.umount(mnt_point, iso)
            import_iso.cleanup_mnt_points()

    def check_upgrade_hw_provisions(self, cfg):
        """
        Merges the current model xml with the upgrade model, finds combined
        VM RAM and CPU usage for each node, and checks availability against
        actual VM RAM and CPU usage on the nodes
        :param cfg: upgrade configuration
        """
        self.log.info('Checking predicted hardware provisions on '
                      'current deployment against: {0}'.
                      format(cfg.model_xml))
        hwr = HwResources(logger_name='enminst')
        try:
            runtime_model = hwr.base_model_xml
            hwr.export_model(runtime_model)
            base_model = load_xml(runtime_model)
            upgrade_model = load_xml(cfg.model_xml)
            base_usage = hwr.get_modeled_vm_resources(base_model)
            combined_usage = hwr.get_modeled_vm_resources(
                    upgrade_model, base_usage)
            vm_resource_usage = hwr.get_blade_vm_resources(
                    combined_usage)

            hostidmappings = hwr.get_modeled_hosts(upgrade_model)
            hostidmappings.update(hwr.get_modeled_hosts(base_model))
            node_state = hwr.get_node_states()

            for hostname in hostidmappings.values():
                if hostname not in node_state:
                    node_state[hostname] = LitpRestClient.ITEM_STATE_INITIAL

            hwr.show_blade_vm_usage(vm_resource_usage, hostidmappings,
                                    node_state, verbose=cfg.verbose)
        except SystemExit:
            self.log.error('VM RAM will be over-provisioned on one '
                           'or more nodes using {0}'.
                           format(cfg.model_xml))
            raise
        self.log.info("Successfully Completed Hardware Resources Healthcheck")

    def copy_runtime_xml(self):
        """
        Copies the runtime xml to a known location so it can be processed
        by dst tool to create file for differences in model xmls
        """
        if os.path.exists(self.runtime_xml_deployment):
            copy_file(self.runtime_xml_deployment, self.prev_dep_xml)

    def copy_previous_xml(self):
        """
        Copies the previous deployment xml back to the runtime xml
        """
        if os.path.exists(self.prev_dep_xml):
            copy_file(self.prev_dep_xml, self.runtime_xml_deployment)

    def prepare_runtime_config(self, cfg):
        """
        Prepares runtime XML model
        :param cfg: upgrade configuration
        """
        self.update_ssh_key()
        self.update_ms_uuid()
        migrate_cleanup_cmd()
        self.deploy_neo4j_uplift_config()
        self.encrypt_passwords(cfg)
        if cfg.enm_iso:
            self.image_version_cfg(cfg.enm_iso)

    def upgrade_applications(self, cfg):
        """
        Upgrade applications
        :param cfg: upgrade configuration
        """
        if cfg.enm_iso:
            if self.gossip_upgrade:
                self.set_consul_flag(JGROUPS_PROTOCOL_MIGRATION)
            self.import_enm_iso_for_upgrade(cfg)
        if cfg.model_xml:
            if cfg.expansion_upgrade:
                set_key_nodes(Sed(cfg.sed_file))
            self.prepare_runtime_config(cfg)
            self.sub_xml_params(cfg)
            copy_custom_banners(cfg)
            unity_model_updates(self.runtime_xml_deployment)
            self.load_xml(cfg)
            self.power_on_new_blades()
            self.remove_items_from_model()
        else:
            self.image_version_cfg(cfg.enm_iso)
            self.update_model_vm_images()

    def is_consul_flag(self, flag):
        """
        Get a flag in consul kv store
        :param flag: name of the flag
        """
        curl_cmd = "curl -X GET -d true "
        curl_url = CONSUL_URL + flag
        self.log.info("Getting consul flag : {0}".format(flag))
        cmd = curl_cmd + curl_url
        self.log.debug("executing : {0}".format(cmd))
        stdout = exec_process(cmd.split())
        if flag in stdout:
            return True
        else:
            return False

    def set_consul_flag(self, flag):
        """
        Set a flag in consul kv store
        :param flag: name of the flag
        """
        curl_cmd = "curl -X PUT -d true "
        curl_url = CONSUL_URL + flag
        self.log.info("Setting consul flag : {0}".format(flag))
        cmd = curl_cmd + curl_url
        self.log.debug("executing : {0}".format(cmd))
        exec_process(cmd.split())

    def delete_consul_flag(self, flag):
        """
        Delete a flag in consul kv store
        :param flag: name of the flag
        """
        curl_cmd = "curl -X DELETE -d true "
        curl_url = CONSUL_URL + flag
        self.log.info("Deleting consul flag : {0}".format(flag))
        cmd = curl_cmd + curl_url
        self.log.debug("executing : {0}".format(cmd))
        exec_process(cmd.split())

    def power_on_new_blades(self):
        """
        Attempt to power on any blades that are not in state 'Applied'.
        :return:
        """
        litp = self.litp
        cfg = read_enminst_config()
        snapper = EnmSnap(cfg)
        node_cred = snapper.get_node_cred()
        model_path = EnmSnap.INFRA_SYSTEMS
        model_object = litp.get_children(model_path)
        for node in model_object:
            obj = LitpObject(None, node['data'], litp.path_parser)
            node_id = obj.get_property('system_name')
            if node_id in node_cred.keys() and obj.state == \
                    LitpRestClient.ITEM_STATE_APPLIED:
                del node_cred[node_id]
        if node_cred:
            redfish = Redfishtool()
            snapper.start_nodes(redfish, node_cred, ignore_if_on=True)
        else:
            self.log.info('No new blades to be powered on')

    def infrastructure_changes(self, cfg):
        """
        Upgrade infra changes before taking snapshot
        :param cfg: upgrade configuration
        :return:
        """
        log_header(self.log, 'Update Infrastructure')
        litp_command_list, plan_required = pre_snap_changes(
            self.runtime_xml_deployment)
        if litp_command_list:
            self.log.info('Update infrastructure is required')
            if self.is_snapshots_supported() and \
                    self.check_snapshots_exists(cfg.verbose):
                self.log.error('Stop execution - unexpected snapshots'
                               ' have been found')
                raise SystemExit(ExitCodes.ERROR)

            for comm in litp_command_list:
                self.log.info('Command to be executed: {0}'.format(comm))
                exec_process(comm.split(' '))

            if plan_required:
                self.infra_plan = True
                self.persist_stage_data(INFRA_PLAN, STATE_START)
                self.log.info("Creating plan")
                self.create_run_plan(cfg)
                self.persist_stage_data(INFRA_PLAN, STATE_END)
                self.infra_plan = False

    @staticmethod
    def remove_deployment_description_file():  # pylint: disable=invalid-name
        """
        Checks if deployment Description file has been copied over
        and removes it.
        :return: None
        """
        dd_path = get_xml_deployment_file()
        if dd_path.startswith('/tmp'):
            delete_file(dd_path)

    @staticmethod
    def gen_stage_data_filename():
        """
        Generate the upgrade_enm stage-data filename
        :return: Stage data absolute file path
        """
        return os.path.join(os.environ['ENMINST_RUNTIME'],
                            'upgrade_enm_stage_data.txt')

    @staticmethod
    def persist_stage_data(stage_name, state):
        """
        Persist the upgrade_enm stage data to file
        :param stage_name: upgrade_enm stage name
        :param state: state reached in stage
        :return: None
        """
        stage_file = ENMUpgrade.gen_stage_data_filename()

        with open(stage_file, 'w') as sfile:
            sfile.write("%s:%s" % (stage_name, state))

    @staticmethod
    def fetch_persisted_stage_data():
        """
        Fetch and extract the contents of the
        persisted upgrade_enm stage data file
        :return: 2-tuple strings, stage-name and state
        """
        stage_file = ENMUpgrade.gen_stage_data_filename()

        line = None
        if os.path.isfile(stage_file):
            with open(stage_file, 'r') as sfile:
                line = sfile.read().strip()

        if line:
            return line.split(':', 1)

        return ('', '')

    def remove_persisted_stage_file(self):
        """
        Remove the persisted upgrade_enm stage file
        :return: None
        """
        stage_file = ENMUpgrade.gen_stage_data_filename()
        self.remove_persisted_file(stage_file)

    @staticmethod
    def remove_persisted_file(filepath):
        """
        Remove a file
        :param filepath: Absolute path to file
        :return: None
        """
        if os.path.isfile(filepath):
            os.remove(filepath)

    @staticmethod
    def gen_params_filename():
        """
        Generate upgrade_enm persistent parameters filename
        :return: Parameters absolute file path
        """
        return os.path.join(os.environ['ENMINST_RUNTIME'],
                            'upgrade_enm_params.txt')

    def remove_persisted_params_file(self):
        """
        Remove the persisted parameters file
        :return: None
        """
        params_file = self.gen_params_filename()
        self.remove_persisted_file(params_file)

    def persist_params(self, parsed_args):
        """
        Persiste upgrade_enm parameters to file
        :param parsed_args: The parsed command line parameters
        :return: None
        """

        params_file = self.gen_params_filename()
        self.remove_persisted_file(params_file)

        args_dict = {}
        for arg in ENMUpgrade.MAIN_UPGRADE_PARAMS:
            if hasattr(parsed_args, arg):
                args_dict[arg] = getattr(parsed_args, arg)

        with open(params_file, 'w') as pfile:
            pickle.dump(args_dict, pfile)

    def fetch_params(self):
        """
        Fetch and extract the persisted upgrade_enm command line parameters
        :return: Dictionary of parameters and values
        """

        params_file = self.gen_params_filename()

        args_dict = {}
        if os.path.isfile(params_file):
            with open(params_file, 'r') as pfile:
                args_dict = pickle.load(pfile)

        return args_dict

    def create_xml_diff_file(self):
        """
        Generate a diff file with a list of item path's to be removed
        :return: None
        """

        if not os.path.isfile(self.prev_dep_xml) or \
                not os.path.isfile(self.runtime_xml_deployment) or \
                not os.path.isfile(self.generate_depl_diff_command):
            self.log.error('File {0}, {1} or {2} not found'.format(
                    self.prev_dep_xml, self.runtime_xml_deployment,
                    self.generate_depl_diff_command))
            raise SystemExit(ExitCodes.ERROR)
        delete_file(self.deploy_diff_out)
        full_gen_depl_diff_command = \
            ''.join([self.generate_depl_diff_command, ' ',
                     self.prev_dep_xml, ' ',
                     self.runtime_xml_deployment, ' ',
                     self.deploy_diff_out])
        self._handle_exec_process(full_gen_depl_diff_command,
                                  'Generating deployment difference file',
                                  'Problem with generating deployment '
                                  'difference file')

    def parse_deploy_diff_output(self):
        """
        Parse the DEPLOYMENT_DIFF_OUTPUT file.
        :return:  list of tuples [(property, path), ...]
        """
        items = []
        with open(self.deploy_diff_out, 'r') as _reader:
            for line in _reader.readlines():
                if line.strip().startswith('y ') and \
                                line.strip().split('/')[-1] \
                                not in ITEM_NOT_FOR_REMOVAL:
                    item = line.strip().split()[1].split('@')
                    if len(item) == 2:
                        items.append((item[1], item[0]))
                    else:
                        items.append((item[0], None))
        return items

    def remove_items_from_model(self):
        """
        Compare previous runtime xml with the new dd and remove difference
        from the model.
        :return: None
        """
        log_header(self.log, 'Remove items from the runtime model')
        self.create_xml_diff_file()
        items = self.parse_deploy_diff_output()
        if not items:
            self.log.info('No items to be removed from the runtime model')
            return
        for path, prop in items:
            if prop:
                if self.litp.delete_property(path, prop):
                    self.log.info('Property \'{0}\' successfully deleted '
                                  'within \'{1}\' item'.format(prop, path))
                else:
                    self.log.info('Property \'{0}\' or item \'{1}\' does not '
                                  'exist in the model'.format(prop, path))
            else:
                if self.litp.delete_path(path):
                    self.log.info('Item \'{0}\' successfully deleted'.format(
                            path))
                else:
                    self.log.info('Item \'{0}\' does not exist in the '
                                  'model'.format(path))
        self.log.info('Runtime model update finished')

    def exec_healthcheck(self, cfg):
        """
        Execute functions from enm_healthcheck
        :param cfg: Upgrade configuration
        """
        if cfg.disable_hc:
            self.log.warning('Health checks have been disabled via CLI')
        else:
            log_header(self.log, 'Executing Healthchecks')
            healthcheck = HealthCheck(logger_name='enminst')
            healthcheck.set_exclude(cfg.disable_hcs)
            healthcheck.pre_checks(verbose=True)
            healthcheck.enminst_healthcheck(verbose=True)

    def resume_failed_upgrade_plan(self, verbose):
        """
        Calls Deployer to resume a failed upgrade software plan.
        :param verbose: True to turn on verbose logging
        """
        log_header(self.log, 'Resume a failed upgrade software plan')

        try:
            deployer.deploy(verbose=verbose,
                            resume_plan=True,
                            run_type="ENM Deployment - Resume Plan")

        except LitpException as error:
            self.log.exception("Failed to execute run_plan --resume: %s" %
                               error.get_default_message())
            raise SystemExit(ExitCodes.ERROR)
        except Exception:
            self.log.exception("Failed to execute run_plan --resume")
            raise SystemExit(ExitCodes.ERROR)

        self.persist_stage_data(UPGRADE_PLAN, STATE_END)
        self.log.info('Resume a failed upgrade software plan '
                      'completed successfully')

    def verify_dd_not_reducing_nodes(self, cfg):
        """
         Check if the deployment description would result in a reduction in
        nodes or clusters.
        :param cfg: parsed configuration parameters
        """
        if cfg.model_xml:
            proposed_dd = load_xml(cfg.model_xml)

            dd_cluster_nodes = {}
            clusters = xpath(proposed_dd, 'vcs-cluster')
            for cluster in clusters:
                nodes = xpath(cluster, 'node')
                dd_cluster_nodes[cluster.get('id')] = len(nodes)

            model_hosts = self.litp.get_cluster_nodes()
            for cluster in model_hosts:
                if cluster in dd_cluster_nodes:
                    if dd_cluster_nodes[cluster] < \
                            len(model_hosts[cluster]):
                        msg = 'WARNING: This deployment description contains' \
                              ' less nodes than expected. Loading this ' \
                              'Deployment Description ' \
                              'will result in node deletion. Please verify ' \
                              'you specified the correct deployment ' \
                              'description.'
                        strong_confirmation_or_exit(cfg.assumeyes,
                                                    'Upgrade', msg)
                else:
                    msg = 'WARNING: This deployment description contains' \
                          ' less clusters than expected.Loading this ' \
                          'Deployment Description will' \
                        'result in cluster deletion. Please verify you ' \
                        'specified the correct deployment description.'
                    strong_confirmation_or_exit(cfg.assumeyes, 'Upgrade', msg)

    def verify_gossip_router_upgrade(self, cfg):
        """
         Check if the deployment description would result in the introduction
         of Gossip Router
        :param cfg: parsed configuration parameters
        """
        log_header(self.log, 'Verify if Gossip Router Upgrade')
        gossip_in_dd = False
        gossip_applied_in_model = True

        if cfg.model_xml:
            proposed_dd = load_xml(cfg.model_xml)
            clustered_services = xpath(proposed_dd, 'vcs-clustered-service')
            for clustered_service in clustered_services:
                if clustered_service.get('id').lower() == \
                                'gossiprouter_clustered_service':
                    gossip_in_dd = True
                    self.log.info('Gossip Router SG in DD')
                    break
        else:
            self.log.debug('No Gossip Router SG in DD')

        if self.litp.exists(GOSSIP_SG_VPATH):
            item = self.litp.get(GOSSIP_SG_VPATH, log=False)
            if item['state'] == "Initial":
                gossip_applied_in_model = False
        else:
            gossip_applied_in_model = False

        if gossip_in_dd and not gossip_applied_in_model:
            msg = 'WARNING: This deployment description involves ' \
                  'the introduction of Gossip Router SG. Loading ' \
                  'this Deployment Description ' \
                  'will result in an upgrade with downtime !!!'
            strong_confirmation_or_exit(cfg.assumeyes,
                                        'Upgrade', msg)
            self.gossip_upgrade = True
        elif self.litp.exists(GOSSIP_SG_VPATH):
            self.log.debug('Gossip Router SG is in LITP Model')

    def enable_serialport_service(self):
        """
        Enable and start serial port service in lms
        """
        enable_serialport_cmd = \
            '/usr/bin/systemctl enable serial-getty@ttyS0.service'
        start_serialport_cmd = \
            '/usr/bin/systemctl start serial-getty@ttyS0.service'
        self._handle_exec_process(enable_serialport_cmd,
              'LITP enabling service "serial-getty@ttySO.service"',
              'Problem with enabling service "serial-getty@ttySO.service"')
        self._handle_exec_process(start_serialport_cmd,
              'LITP starting service "serial-getty@ttySO.service"',
              'Problem with starting service "serial-getty@ttySO.service"')

    def execute_standard_upgrade(self, cfg):  # pylint: disable=R0915
        """
        If not resuming upgrade_enm.py, execute all [standard] stages
        :param cfg: parsed configuration parameters
        :return True if OS patches applied, False otherwise
        """
        patch_set_package_base = "RHEL_OS_Patch_Set_CXP"
        self.verify_dd_not_reducing_nodes(cfg)
        self.verify_gossip_router_upgrade(cfg)
        self.log.info("Upgrade has been started")
        import_iso.configure_logging(False)
        self.enable_puppet_on_nodes()
        self.check_postgres_uplift_req()
        self.check_setup_neo4j_uplift(cfg)
        self.enable_serialport_service()
        self.exec_healthcheck(cfg)

        if cfg.model_xml:
            if cfg.disable_hc:
                self.log.warning('Hardware provisioning checks have been '
                                 'disabled via CLI')
            else:
                self.check_upgrade_hw_provisions(cfg)

            self.validate_enm_deployment_xml()
            self.copy_runtime_xml()
            try:
                self.prepare_runtime_config(cfg)
                self.sub_xml_params(cfg)
                unity_model_updates(self.runtime_xml_deployment)
                self.create_xml_diff_file()
                self.check_db_node_removed()
                enm_snapshots.create_removed_blades_info_file()
                self.infrastructure_changes(cfg)
            finally:
                self.copy_previous_xml()

        self.prepare_snapshot(cfg)

        if cfg.regenerate_keys:
            self.regenerate_ssh_keys()

        rhel7_information = self.get_cxp_values('rhel7_release')
        if rhel7_information is not None:
            self.rhel_patch_cxps[self.rhel7_ver] = rhel7_information
        else:
            # Checking if the RHEL 7 patchset package is installed for
            # either ISO or TGZ patches.
            if check_package_installed(patch_set_package_base + \
                self.config.get("rhel7_os_patch_cxp_tgz")) or \
            check_package_installed(patch_set_package_base + \
            self.config.get("rhel7_os_patch_cxp_iso")):
                self.log.error("Release file ericrhel7_release not found!")
                raise SystemExit(ExitCodes.ERROR)

            self.log.debug("Release file rhel7_release not found and could not"
                           " find any rhel7 patchset package.")

        if self.rhel_util.is_latest_version():
            self.rhel7_9_copied = True
        elif cfg.rhel7_9_iso:
            self.copy_rhel_os(cfg)
            self.rhel7_9_copied = True

        rhel8_information = self.get_cxp_values('rhel8_release')
        if rhel8_information:
            self.rhel_patch_cxps[self.rhel8_ver] = rhel8_information

        if cfg.os_patch and not self.all_patches_applied():
            self.log.debug('Patches in ms_os_patched not done'
                           ' or file not found')
            self.check_patches_done(cfg)

            if len(cfg.os_patch) > 0:
                self.log.debug("Patches to be applied still.")
                self.apply_os_patches(cfg)
                if self.reboot_required:
                    return True

        self.enable_puppet_on_nodes()

        (stage, state) = self.fetch_persisted_stage_data()
        if stage == UPGRADE_PLAN and state == STATE_FAILED:
            self.log.info("ISO already copied")
        else:
            if cfg.litp_iso:
                self.upgrade_litp(cfg)
            if cfg.enm_iso or cfg.model_xml:
                self.upgrade_applications(cfg)

            self.litp_upgrade_deployment()
            if self.gossip_upgrade:
                self.litp_disable_reboot_tasks(GOSSIP_AFFECTED_CLUSTERS)
                self.litp_set_cs_initial_online('off', \
                                                GOSSIP_AFFECTED_CLUSTERS)
                self.litp_set_global_property(VMS_WITHOUT_JGROUPS,
                                              VMS_WITHOUT_JGROUPS_VALUE)

        self.persist_stage_data(UPGRADE_PLAN, STATE_START)
        self.create_run_plan(cfg)
        self.persist_stage_data(UPGRADE_PLAN, STATE_END)
        return False

    def enable_puppet_on_nodes(self):
        """
        Using MCO enable Puppet agent on nodes
        """
        self._puppet_action_on_nodes('enable')

    def disable_puppet_on_nodes(self):
        """
        Using MCO disable Puppet agent on nodes
        """
        self._puppet_action_on_nodes('disable')

    def _puppet_action_on_nodes(self, action):
        """
        Execute a Puppet disable|enable command on non-master nodes.
        :param action: Action verb "enable" or "disable"
        :type action: str
        :return: None
        """
        cmd = PUPPET_ACTION_NON_MASTER_CMD_TEMPLATE.format(action)
        info_msg = 'Will {0} Puppet on nodes'.format(action)
        error_msg = 'Failed to {0} Puppet on nodes'.format(action)
        self._handle_exec_process(cmd, info_msg, error_msg,
                                  allowed_error_codes=[2])

    def check_postgres_uplift_req(self):
        """
        Check if Postgres needs a version uplift and /ericsson/postgres
        has enough space for uplift.
        """
        self.log.info("Beginning of Postgres pre version "
                         "uplift requirements check")
        pg_service = PostgresService()
        pg_service.pg_pre_uplift_checks()

    def check_setup_neo4j_uplift(self, cfg):
        """
        Check if Neo4j Uplift to 4.* needed and if so
        set and validate Neo4j credentials for Uplift
        """
        self.log.debug('check_setup_neo4j_uplift')
        if not cfg.model_xml:
            self.log.info('DD xml not provided, no Neo4j Uplift needed')
            return
        force_creds_check = os.environ.get('FORCE_NEO4J_UPLIFT_CREDS_CHECK',
                                           False) == 'true'
        neo4j_cluster = Neo4jClusterOverview()
        uplift_needed = neo4j_cluster.is_neo4j_4_in_dd(cfg) and \
                        neo4j_cluster.need_uplift() or \
                        neo4j_cluster.need_uplift_4x(cfg)

        if uplift_needed:
            self.log.info('Neo4j Uplift is needed.')
        else:
            self.log.info('Neo4j Uplift not needed, proceed with Upgrade')
            if not force_creds_check:
                return

        if force_creds_check:
            self.log.info('Environment flag '
                          'FORCE_NEO4J_UPLIFT_CREDS_CHECK=true')

        if not neo4j_cluster.is_single_mode():
            self.log.info('Neo4j Cluster mode credentials needed')
            if os.path.exists(FORCE_SSH_KEY_ACCESS_FLAG_PATH):
                self.log.warning('Flag "%s" found, ssh key will be used '
                                 'for Neo4j Uplift access instead of '
                                 'passwords' %
                                 FORCE_SSH_KEY_ACCESS_FLAG_PATH)
            else:
                nodes_user_cred = neo4j_cluster.check_sed_credentials(cfg)
                self.create_neo4j_cred_file(nodes_user_cred)
        else:
            self.log.info('Neo4j Single mode, no credentials needed')

        log_header(self.log, 'Executing Neo4j Uplift Healthchecks')
        healthcheck = HealthCheck(logger_name='enminst')
        healthcheck.neo4j_uplift_healthcheck(cfg)

    def create_neo4j_cred_file(self, credentials):
        """
        Creates Neo4j credentials file dbcreds.yaml for Uplift
        to be able to connect Neo4j cluster's db nodes to run
        uplift procedure
        """
        self.log.debug('create_neo4j_cred_file')
        neo4j_dbcred_file = "/ericsson/tor/data/neo4j/dbcreds.yaml"
        try:
            with open(neo4j_dbcred_file, 'w') as cred_file:
                yaml.dump(credentials, cred_file, indent=4,
                    default_flow_style=False)
        except IOError as error:
            self.log.error("Failed to update credentials file: {0}".format(
                error))
            raise SystemExit(ExitCodes.ERROR)

    def deploy_neo4j_uplift_config(self):
        """ Deploy Neo4j uplift data file with Neo4j lun size.
        Required to find out by how much Neo4j filesystem can be extended.
        """
        neo4j_cluster = Neo4jClusterOverview()
        if neo4j_cluster.need_uplift():
            self.log.info("Deploy Neo4j uplift config")
            uplift_data_dir = "/ericsson/tor/data/neo4j/uplift"
            if not os.path.exists(uplift_data_dir):
                try:
                    os.mkdir(uplift_data_dir)
                except (OSError, IOError) as error:
                    self.log.error("Failed to create %s directory"
                                   % uplift_data_dir)
                    raise SystemExit(error)
                self.log.info("Successfully created %s" % uplift_data_dir)

            neo4j_lun = Neo4jLun(neo4j_cluster.is_single_mode())
            lun_size = neo4j_lun.size

            with open(os.path.join(uplift_data_dir, "data.json"),
                      "w+") as data_file:
                data_file.write(dumps({'lun_size': '%sb'
                                       % (int(lun_size.num_bytes) * 0.95)}))
            self.log.info("Successfully deployed %s"
                          % os.path.join(uplift_data_dir, "data.json"))

    def validate_enm_deployment_xml(self):
        """
        Ensures that enm_deployment.xml contains valid xml
        """
        xml = XMLValidator()
        if os.path.exists(self.runtime_xml_deployment):
            self.log.info("Validating {0}".format(self.runtime_xml_deployment))
            try:
                xml.validate(self.runtime_xml_deployment, self.litp_xsd)
            except:
                raise SystemExit(ExitCodes.ERROR)

    def copy_rhel_os(self, cfg):  # pylint: disable=R0915
        """
        Copy RHEL DVD ISO content, create OS repo and install package upgrades
        :param cfg: parsed configuration parameters
        """
        log_header(self.log, 'Copy RHEL OS')

        rhel_os = '{0}/{1}/os/x86_64'.format(WEB_ROOT, self.rhel7_ver)
        rhel_os_pkg = '{0}/Packages'.format(rhel_os)
        rhel_updates = '{0}/{1}/updates/x86_64/Packages'.format(WEB_ROOT,
                                                                self.rhel7_ver)
        mnt_point = None
        import_iso.set_import_iso_label(LABEL_RHEL)

        try:
            if not os.path.isdir(rhel_os):
                self.log.debug('Ensuring directory {0}'.format(rhel_os))
                os.makedirs(rhel_os)
                self.log.debug('Ensuring directory {0}'.format(rhel_updates))
                os.makedirs(rhel_updates)

            self.log.debug('Creating temporary mount point for RHEL DVD ISO')
            mnt_point = import_iso.create_mnt_dir()

            self.log.debug('Mounting RHEL DVD ISO at {0}'.format(mnt_point))
            import_iso.mount(mnt_point, cfg.rhel7_9_iso)

            self.log.debug('Copying content from RHEL DVD ISO to {0}'
                           .format(rhel_os))
            cmd = 'rsync -rtd {0}/ {1}'.format(mnt_point, rhel_os)
            self._handle_exec_process(cmd, 'Copying RHEL ISO content',
                                           'Problem copying RHEL ISO content')

            self.log.debug('Creating repository {0}'.format(rhel_os_pkg))
            cmd = 'createrepo -C {0}'.format(rhel_os_pkg)
            self._handle_exec_process(cmd, 'Creating OS repository',
                                           'Problem creating OS repository')

            self.log.debug('Creating repository {0}'.format(rhel_updates))
            cmd = 'createrepo -C {0}'.format(rhel_updates)
            self._handle_exec_process(cmd, 'Creating Updates repository',
                                      'Problem creating Updates repository')

            self._disable_puppet_in_ms()
        except OSError as error:
            self.log.error('Error creating directories/symlink for RHEL '
                           'OS/Updates directories')
            self.log.error('RHEL OS copy failed')
            raise SystemExit(error)
        except (SystemExit, Exception) as error:
            self.log.error('RHEL OS copy failed')
            raise SystemExit(error)
        finally:
            import_iso.umount(mnt_point)
            self.log.info('Removing {0} '.format(mnt_point))
            import_iso.cleanup_mnt_points()

    def check_patches_done(self, cfg):
        """
        Check which patch sets have been previously applied
        during this upgrade and remove them from params.
        :param cfg: configuration
        """
        if os.path.isfile(self.ms_patched_done_file):
            for patch_set in cfg.os_patch:
                patch_done = self.patch_previously_applied(patch_set)

                if patch_done:
                    cfg.os_patch.remove(patch_set)

    def all_patches_applied(self):
        """
        Check all patches have alread been applied.
        Checking against ms_patch_done_file.
        :return boolean
        """
        all_patches_applied = False
        patches = set()

        if not os.path.isfile(self.ms_patched_done_file):
            self.log.debug("ms_os_patched not found")
            return all_patches_applied

        for cxp in self.rhel_patch_cxps.values():
            self.log.debug('Adding patch_with_CXP{0} '
                           'to cxp set patches'.format(cxp))
            patches.add('patch_with_CXP{0}'.format(cxp))

        with open(self.ms_patched_done_file) as done_file:
            content = done_file.read().splitlines()
            self.log.debug("Lines in content set: {0}".format(len(content)))
            self.log.debug("Checking if patches is subset of set content")
            if patches.issubset(set(content)):
                all_patches_applied = True
                self.log.debug("patches is subset of set content")

        return all_patches_applied

    def patch_previously_applied(self, os_patch):
        """
        Check if given tarball patchset has already been applied.
        Checking against ms_patch_done_file.
        :return boolean
        """
        # Need to check whether the os patch file is a TAR file or an
        # ISO image
        self.log.info('Unpacking patch file {0}'.format(os_patch))
        stdout = self._handle_exec_process(
            "file -b " + os_patch,
            'Executing file command to determine file type for {0}'\
                .format(os_patch),
            'Problem occurred while trying to determine file type for'
                + ' {0}.'\
                .format(os_patch))

        patch_set_ver = ''
        if re.search(ISO_FILE_TYPE, stdout):
            mnt_point = None
            try:
                import_iso.set_import_iso_label(LABEL_OS_PATCHES)
                mnt_point = import_iso.create_mnt_dir()
                self.log.debug('Mounting patch ISO {0} to {1}'.
                               format(os_patch, mnt_point))
                import_iso.mount(mnt_point, os_patch)
                for cxp in self.rhel_patch_cxps.values():
                    match_cxp = re.compile('RHEL_OS_Patch_Set_CXP{0}*'\
                                    .format(cxp))
                    for _, _, filenames in os.walk(mnt_point):
                        if [match.group(0) for filename in filenames for match
                                in [match_cxp.search(filename)] if match]:
                            patch_set_ver = 'patch_with_CXP{0}'.format(cxp)
            finally:
                if mnt_point:
                    import_iso.umount(mnt_point)
                    self.log.info('Removing {0} '.format(mnt_point))
                    import_iso.cleanup_mnt_points()
        elif re.search(TGZ_FILE_TYPE, stdout):
            patch_set = tarfile.open(os_patch)
            package_names = patch_set.getnames()
            for cxp in self.rhel_patch_cxps.values():
                match_cxp = re.compile('RHEL_OS_Patch_Set_CXP{0}*'.format(cxp))
                if [match.group(0) for pkg in package_names for match in
                        [match_cxp.search(pkg)] if match]:
                    patch_set_ver = 'patch_with_CXP{0}'.format(cxp)
                    break
        else:
            self.log.error('The RHEL patchset information has an invalid '
                           'version')
            raise SystemExit(ExitCodes.ERROR)

        if patch_set_ver:
            with open(self.ms_patched_done_file) as done_file:
                if patch_set_ver in done_file.read():
                    return True

        return False

    def execute_post_upgrade_steps(self):
        """
        Execute all post upgrade software plan stages
        :return
        """
        # read persisted params file and retrieve sed file parameter
        self.post_upgrade()
        self.remove_persisted_stage_file()
        self.remove_persisted_params_file()
        self.rhel_util.clean_repos()
        self.postgres_reload()
        self.remove_deployment_description_file()
        ENMUpgrade.neo4j_pre_check()
        self.crypto_service()
        self.harden_neo4j()
        self.log.info("System successfully upgraded")
        return True

    def execute_stages(self, cfg):
        """
        Executes stages of upgrade
        :param cfg: configuration
        :type cfg: Namespace
        """
        upgrade_finished = False
        try:
            if self._is_model_only_upgrade(cfg):
                self._update_vmimage_version()
            if cfg.resume:
                (stage, state) = self.fetch_persisted_stage_data()
                if stage == UPGRADE_PLAN and state == STATE_START:
                    self.resume_failed_upgrade_plan(cfg.verbose)
                    self.gossip_upgrade = self.is_consul_flag(
                                          JGROUPS_PROTOCOL_MIGRATION)
                else:
                    self.log.error('Upgrade software plan did not '
                                   'previously fail. Unable to resume')
                    raise SystemExit(ExitCodes.ERROR)
            else:
                do_standard_upgrade = False
                (stage, state) = self.fetch_persisted_stage_data()
                if stage == UPGRADE_PLAN and state == STATE_START:
                    plan_state = deployer.get_plan_state().lower()

                    if plan_state == 'running' or plan_state == 'stopping':
                        self.monitor_plan(cfg)
                        self.persist_stage_data(UPGRADE_PLAN, STATE_END)
                    elif plan_state != 'successful':
                        do_standard_upgrade = True
                else:
                    do_standard_upgrade = True

                if do_standard_upgrade:
                    os_patches_applied = self.execute_standard_upgrade(cfg)
                    if os_patches_applied:
                        return
            if self.gossip_upgrade:
                self.post_gossip_router_upgrade(cfg)
            upgrade_finished = self.execute_post_upgrade_steps()
        except:
            self.log.exception("System upgrade failed")
            raise
        finally:
            if upgrade_finished:
                remove_snapshots_indicator_file()
                delete_file(self.ms_patched_done_file)
                delete_file(self.prev_dep_xml)

    @staticmethod
    def store_and_set_pib(param, new_value, existing_value):
        """
        Stores the existing pib value and sets the new pib value.
        Kicks off self-deleting cron to reset to existing pib value
        :param param: the PIB property
        :param new_value: the new value.
        :param existing_value: the old value
        """
        params_file = import_iso.get_cfg_file()
        pibcfg = EnminstWorking(params_file)
        pibcfg.set_site_key(param, existing_value)
        pibcfg.write()
        h_utils.set_pib_param(param, new_value)
        h_utils.create_pib_param_set_cron(param,
                                          existing_value,
                                          PIB_CRON_DELTA,
                                          param + '_pib_cron_file')

    def post_gossip_router_upgrade(self, cfg):  # pylint: disable=R0915,R0914
        """
        Executes post gossip_router upgrade steps
        :param cfg: configuration
        :type cfg: Namespace
        """

        fm_avail = False
        try:
            exec_process('/bin/grep "fmemergency_ips=" '
                         '/ericsson/tor/data/global.properties',
                         use_shell=True)
            fm_avail = True
        # grep returns non-zero if fmemergency not present in global.properties
        except IOError:
            fm_avail = False

        # if fm availability is installed run pre_rollback procedure to prevent
        # fm downtime during bounce procedure
        if fm_avail:
            try:
                self.log.info("FM Availability is present, "
                              "performing pre-rollback step.")
                command = "/bin/bash /opt/ericsson/fallback/bin/installer.sh" \
                          " -pr -s {0} -n {1}"\
                    .format(cfg.sed_file, 'fb_node1')
                exec_process(command, use_shell=True)
            except IOError:
                self.log.error('Failed to execute pre-rollback step for '
                               'FM Availability')

        self.litp_set_cs_initial_online('on', GOSSIP_AFFECTED_CLUSTERS)
        switch_dbcluster_groups()
        self.delete_consul_flag(JGROUPS_PROTOCOL_MIGRATION)
        self.log.info("Setting preonline trigger")
        pop = PreOnlineProvisioner()
        pop.set_preonline_trigger()
        # need to sleep before power-off otherwise VCS main.cf can get corrupt
        existing_reloadtimeout = h_utils.read_pib_param('reLoadTimeOut')

        time.sleep(60)

        bouncer = EnmBouncer()
        downtime_start = datetime.now()
        self.log.info("Powering off nodes")
        bouncer.bounce_clusters(GOSSIP_AFFECTED_CLUSTERS,
                                        'off', 120, True)
        try:
            vcs = Vcs()
            postgres_host = self.get_postgres_active_host()

            if len(postgres_host):
                self.log.info("Offlining Postgres SG.")
                vcs.hagrp_offline(".*postgres_clustered_service",
                                  postgres_host[0],
                                  Vcs.ENM_DB_CLUSTER_NAME,
                                  -1)
                self.log.info("Onlining Postgres SG.")
                vcs.hagrp_online(".*postgres_clustered_service",
                                  postgres_host[0],
                                  Vcs.ENM_DB_CLUSTER_NAME,
                                  -1)
        except SystemExit:  # pylint: disable=W0703
            self.log.error('Failed to offline/online Postgres SG',
                              exc_info=True)
        self.log.info("Powering on nodes")
        bouncer.bounce_clusters(GOSSIP_AFFECTED_CLUSTERS,
                                        'on', 120, True)
        self.log.info("Waiting {0} seconds before post bounce service check".
                      format(POST_BOUNCE_SLEEP_SECONDS))
        time.sleep(POST_BOUNCE_SLEEP_SECONDS)

        self.log.info("Starting post upgrade bounce service health check")
        healthcheck = HealthCheck(logger_name='enminst')

        start_time = datetime.now()
        max_wait_time_in_minutes = POST_BOUNCE_TIMEOUT_SECONDS // 60

        while True:
            try:
                healthcheck.vcs_service_group_healthcheck(
                                cfg.verbose)
                break
            except SystemExit:
                self.log.error('Post upgrade bounce service health'
                                ' check failed.')
                try:
                    self._handle_exec_process(POST_RESTORE_SCRIPT,
                               'Executing post upgrade bounce faulted service'
                               ' check', 'Post upgrade bounce faulted service'
                               ' check failed.')
                except SystemExit:
                    self.log.error('Post upgrade bounce faulted service check'
                                   ' failed.')

            duration = datetime.now() - start_time
            if duration.seconds > POST_BOUNCE_TIMEOUT_SECONDS:
                self.log.error('Post upgrade bounce health check timeout.'
                               ' Please verify service health check manually.')
                pop.unset_preonline_trigger()
                self.store_and_set_pib('reLoadTimeOut', '35',
                               existing_reloadtimeout)
                return

            formatted_duration = str(duration).split('.')[0]
            remaining_time = max_wait_time_in_minutes - (
                duration.seconds // 60)
            self.log.info('Time elapsed [hh:mm:ss]: {0} . '
                           'Operation will timeout in about {1} minutes'
                           .format(formatted_duration, remaining_time))

            time.sleep(MONITORING_POST_BOUNCE_SLEEP_SECONDS)
        downtime_end = datetime.now()
        downtime = downtime_end - downtime_start
        self.log.info("Total estimated time for cluster bounce is {0}".
                      format(downtime))
        self.log.info("Unsetting preonline trigger")
        pop.unset_preonline_trigger()
        self.store_and_set_pib('reLoadTimeOut', '35',
                               existing_reloadtimeout)
        self.log.info("System successfully bounced")

        #Perform postrollback if fm availability is present
        if fm_avail:
            try:
                self.log.info('FM Availability is present '
                              'Migrating FM traffic back to ENM.')
                command = '/bin/bash /opt/ericsson/fallback/bin/installer.sh' \
                          ' -po -s {0} -n {1}'\
                    .format(cfg.sed_file, 'fb_node1')
                exec_process(command, use_shell=True)
                self.log.info('Successfully migrated traffic back to ENM.')
            except IOError:
                self.log.error('Failed migrating traffic back to ENM, Please'
                               'excecute post-rollback step manually.')

    @staticmethod
    def _is_model_only_upgrade(cfg):
        """
        Returns whether the upgrade is model only
        (no OS patches, no LITP/ENM ISO)
        :param cfg: configuration
        :type cfg: Namespace
        """
        return cfg.model_xml and cfg.sed_file and not cfg.os_patch and \
            not cfg.litp_iso and not cfg.enm_iso

    def _update_vmimage_version(self):
        """
        Replaces the VM images version in enminst_working.cfg with the contents
        from the VM repo, assuming they exist.
        """

        # location of enminst_working.cfg file
        cfg_file = import_iso.get_cfg_file()
        # list of images in /var/www/html/ENM
        img_list = EnmLmsHouseKeeping().get_repo_images().get('ENM', [])
        if img_list:
            self.log.debug("Updating enminst_working.cfg with these VM"
                           " images:" + ', '.join(img_list))
            import_iso.update_working_params(cfg_file, img_list)

    def check_db_node_removed(self):
        """
        Check if there is db node to be removed as part of the upgrade
        """
        if h_utils.db_node_removed():
            self.log.error('Stop execution - removal of db node(s) '
                           'in the upgrade xml is not supported')
            raise SystemExit(ExitCodes.ERROR)

    def get_cxp_values(self, release_name):
        """
        Assigns the correct CXP to patch CXP's.
        """
        cxp_info = None
        rhel_release = self.config.get(release_name)
        if os.path.isfile(rhel_release):
            with open(rhel_release) as json_file:
                try:
                    cxp_info = load(json_file)
                except ValueError:
                    self.log.error("Patchset release file %s has invalid JSON"
                                   " syntax!" % rhel_release)
                    raise SystemExit(ExitCodes.ERROR)
            return cxp_info['cxp']
        else:
            self.log.debug("Release file %s not found." % release_name)

    def cleanup_log4j_ec_files(self):
        """
        Delete files from MS since the log4jshell correction is no longer
        required.
        """
        log4j_ec_files = ['/etc/cron.d/log4shellmitigation',
                          '/root/log4shellmitigation.sh',
                          '/var/log/log4shell_output.log']

        for ec_file in log4j_ec_files:
            if os.path.exists(ec_file):
                self.log.info("Removing file {0}".format(ec_file))
                os.remove(ec_file)
            else:
                self.log.debug("File {0} not found".format(ec_file))


def create_parser():
    """
    Creates and configures parser to process command line arguments
    :return:
    """
    upgrade_epilog = textwrap.dedent('''
Examples:
Upgrade using OS_PATCH, LITP_ISO, ENM_ISO, SED & MODEL
# %(prog)s --sed /var/tmp/sed-<version>.txt \
--model /var/tmp/deployment-<version>.xml \
--patch_rhel /var/tmp/rhel-oss-patches-<version>.iso
--litp_iso /var/tmp/ERIClitp_CXP9024296-<version>.iso \
--enm_iso /var/tmp/ERICenm_CXP9027091-<version>.iso
- Rerun command when control returned to end user after MS patches applied.

Upgrade using LITP and ENM_ISO with SED and MODEL
# %(prog)s --sed /var/tmp/sed-<version>.txt \
--model /var/tmp/deployment-<version>.xml \
--litp_iso /var/tmp/ERIClitp_CXP9024296-<version>.iso \
--enm_iso /var/tmp/ERICenm_CXP9027091-<version>.iso

Upgrade using ENM_ISO with SED and MODEL
# %(prog)s --sed /var/tmp/sed-<version>.txt \
--model /var/tmp/deployment-<version>.xml \
--enm_iso /var/tmp/ERICenm_CXP9027091-<version>.iso

Upgrade using ENM_ISO only
# %(prog)s --enm_iso /var/tmp/ERICenm_CXP9027091-<version>.iso

Upgrade using LITP_ISO
# %(prog)s --litp_iso /var/tmp/ERIClitp_CXP9024296-<version>.iso

Upgrade using SED and MODEL
# %(prog)s --sed /var/tmp/sed-<version>.txt \
--model /var/tmp/deployment-<version>.xml

Update LITP model only with SED changes
# %(prog)s --sed /var/tmp/sed-<version>.txt  --internal_model_only

Upgrade RHEL OS only across ENM Deployment
# %(prog)s --rhel7_9_iso /var/tmp/RHEL79_Media_CXP9041796-<version>.iso

Upgrade using OS Patches only across ENM Deployment
- Single patch set:
# %(prog)s --patch_rhel /var/tmp/rhel-oss-patches-<version>.iso
- Multiple patch sets (space separated):
# %(prog)s --patch_rhel /var/tmp/RHEL79_OS_Patch_Set_CXP9041797-x.x.x.iso
                            /var/tmp/RHEL88_OS_Patch_Set_CXP9043482-x.x.x.iso
- Rerun command when control returned to end user after MS patches applied.

''')
    arg_parser = \
        ArgumentParser(prog="upgrade_enm.sh",
                       formatter_class=RawDescriptionHelpFormatter,
                       epilog=upgrade_epilog)

    arg_parser.add_argument('-v', '--verbose', dest='verbose',
                            default=False, action='store_true',
                            help='Verbose logging')

    arg_parser.add_argument('-y', '--assumeyes', dest='assumeyes',
                            default=False, action='store_true',
                            help='Answer yes for all questions')
    arg_parser.add_argument('--lvm_snapsize',
                            dest=ENMUpgrade.PARAM_LVM_SNAPSIZE,
                            type=int, default=None,
                            help='Optional argument to specify LVM snap size')
    arg_parser.add_argument('--regenerate_keys',
                            dest=ENMUpgrade.PARAM_REGENERATE_KEYS,
                            action='store_true',
                            required=False,
                            help='Regenerate SSH key for VMs')
    arg_parser.add_argument('--dhc', dest=ENMUpgrade.PARAM_DISABLE_HC,
                            default=False, action='store_true',
                            help='Internal Use Only.')
    arg_parser.add_argument('--hc_exclude', dest=ENMUpgrade.PARAM_EXCLUDE_HCS,
                            required=False,
                            type=lambda x:
                            is_valid_hc_list(arg_parser, '--hc_exclude', x),
                            help='Internal Use Only.')
    arg_parser.add_argument('--internal_model_only',
                            dest=ENMUpgrade.PARAM_INTERNAL_MODEL,
                            default=False, action='store_true',
                            help='Update only the LITP model from the SED')
    arg_parser.add_argument('--expansion_upgrade', dest='expansion_upgrade',
                            default=False, required=False, action='store_true',
                            help='Indicates that this is an expansion ')

    os_patches_group = arg_parser.add_argument_group('OS patch options')

    os_patches_group.add_argument('-p', '--patch_rhel',
                                  dest=ENMUpgrade.PARAM_OS_PATCH,
                                  metavar='OS_PATCH',
                                  nargs='+',
                                  required=False,
                                  type=lambda x:
                                  is_valid_file(arg_parser, 'OS_PATCH', x),
                                  help='Path(s) to OS Patch file(s). '
                                       'Can accept up to 3 patch files, '
                                       'must be seperated by a space'
                                  )

    litp_upgrade_group = arg_parser.add_argument_group('LITP upgrade options')
    litp_upgrade_group.add_argument('-l', '--litp_iso',
                                    dest=ENMUpgrade.PARAM_LITP_ISO,
                                    metavar='LITP_ISO',
                                    required=False,
                                    type=lambda x:
                                    is_valid_file(arg_parser, 'LITP_ISO', x),
                                    help='Path to LITP ISO file'
                                    )

    os_patches_group.add_argument(CMD_OPTION_NOREBOOT_SHORT, '--noreboot',
                                  dest=ENMUpgrade.PARAM_NOREBOOT,
                                  default=False,
                                  action='store_true',
                                  required=False,
                                  help='Avoid automatic reboot of ENM MS node'
                                  )

    enm_group = arg_parser.add_argument_group('ENM upgrade options', )

    enm_group.add_argument('-s', '--sed', dest=ENMUpgrade.PARAM_SED_FILE,
                           metavar='SED', required=False,
                           type=lambda x:
                           is_valid_file(arg_parser, 'SED', x),
                           help='Path of Site Engineering Document'
                                ' file to be used'
                                ', require XML parameter')
    enm_group.add_argument('-m', '--model', dest=ENMUpgrade.PARAM_MODEL_XML,
                           metavar='XML', required=False,
                           type=lambda x:
                           is_valid_file(arg_parser, 'Model XML', x),
                           help='Path of Deployment Model XML file'
                                ' to be used'
                                ', require SED parameter')
    enm_group.add_argument('-e', '--enm_iso', dest=ENMUpgrade.PARAM_ENM_ISO,
                           metavar='ENM_ISO', required=False,
                           type=lambda x:
                           is_valid_file(arg_parser, 'ENM_ISO', x),
                           help='Path of ENM ISO file')
    enm_group.add_argument('-r', '--rhel7_9_iso',
                           dest=ENMUpgrade.PARAM_RHEL_ISO,
                           metavar='RHEL_ISO', required=False,
                           type=lambda x:
                           is_valid_file(arg_parser, 'RHEL_ISO', x),
                           help='Path to RHEL 7.9 DVD ISO file')
    enm_group.add_argument('--resume',
                           dest='resume',
                           default=False,
                           required=False,
                           action='store_true',
                           help='Resume failed upgrade software plan. '
                                'Only the --verbose and --assumeyes '
                                'arguments may be used with this '
                                '--resume argument')

    return arg_parser


# =============================================================================
# Main
# =============================================================================
def main(args):
    """
    Main application function
    :param args: arguments to be processed
    """
    init_enminst_logging()
    log = logging.getLogger('enminst')
    parser = create_parser()
    parsed_args = parser.parse_args(args[1:])
    if parsed_args.verbose:
        set_logging_level(log, 'DEBUG')

    enm_upgrade = ENMUpgrade()
    enm_upgrade.process_arguments(parser, parsed_args)

    if parsed_args.resume:
        label = "Resumption of Upgrade is going to start."
        enm_upgrade.persisted_params = enm_upgrade.fetch_params()
    else:
        label = "Upgrade is going to start."
        enm_upgrade.persist_params(parsed_args)

    strong_confirmation_or_exit(parsed_args.assumeyes, 'Upgrade', label)
    log_cmdline_args("upgrade_enm.sh", args)

    if parsed_args.internal_model:
        args = ['upgrade_enm_internal_model_only.py', parsed_args.sed_file]
        update_litp(args)
    else:
        enm_upgrade.execute_stages(parsed_args)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
