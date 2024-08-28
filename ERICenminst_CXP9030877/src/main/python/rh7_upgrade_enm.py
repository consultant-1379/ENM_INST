# pylint: disable=C0302,R0914,R0915,W0403,W0212,R0902,R0912,R0903
"""
RHEL 7.9 ENM Upgrader tool
"""
##############################################################################
# COPYRIGHT Ericsson AB 2021
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################

import sys
import glob
import os
import re
import shutil
import time
import textwrap
import subprocess
import tarfile
import platform
import datetime
import tempfile
import collections
import simplejson
from argparse import ArgumentParser, RawTextHelpFormatter
from contextlib import closing
from lxml import etree
from base64 import standard_b64encode

import import_iso
from import_iso_version import ENM_HISTORY_FILENAME, \
                               ENM_VERSION_FILENAME, \
                               LITP_RELEASE_FILENAME

from pwd import getpwnam
from grp import getgrnam

from h_infra.pre_upgrade_infra import ITEM_TYPE_SFS_FILESYSTEM
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import main_exceptions, LitpException
from h_puppet.mco_agents import McoAgentException
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_puppet.h_puppet import puppet_trigger_wait
from encrypt_passwords import EncryptPassword
from h_util.h_postgres import PostgresService
from substitute_parameters import Substituter
from h_xml.xml_utils import load_xml, xpath, get_xml_element_properties
from h_infra import pre_upgrade_infra as infra_check
from h_util.h_housekeeping import EnmLmsHouseKeeping
from h_util.h_utils import RHELUtil, copy_file, \
                           litp_backup_state_cron, \
                           cleanup_java_core_dumps_cron, \
                           create_san_fault_check_cron, \
                           create_nasaudit_errorcheck_cron, \
                           migrate_cleanup_cmd, \
                           get_enable_cron_on_expiry_cmd, \
                           cmd_DISABLE_CRON_ON_EXPIRY
from enm_snapshots import manage_snapshots, \
                          create_snapshots_indicator_file
from enm_upgrade_prechecks import EnmPreChecks
from enm_healthcheck import HealthCheck
from h_snapshots.lvm_snapshot import MIGRATION_LOCK_FILE
from h_rhel7.rh7_pre_upgrade import pre_rollover_changes, \
                                    ITEM_TYPE_VCS_CLUSTERED_SERVICE
from switch_db_groups import switch_dbcluster_groups
from h_vcs.vcs_cli import Vcs
from upgrade_enm import ENMUpgrade, unity_model_updates
from deployer import Deployer


class Rh7EnmUpgrade(object):
    """
    RHEL 7 ENM Upgrader tool
    """
    OPT_ERIC = os.path.join(os.sep, 'opt', 'ericsson')
    ENM_INST_DIR = os.path.join(OPT_ERIC, 'enminst')
    ENM_RT_DIR = os.path.join(ENM_INST_DIR, 'runtime')
    ENM_DD = os.path.join(ENM_RT_DIR, 'enm_deployment.xml')
    ENM_PREVIOUS_DD = os.path.join(ENM_RT_DIR, 'previous_enm_deployment.xml')
    EXPORTED_ENM_FROM_STATE_DD = os.path.join(ENM_RT_DIR,
                                      'exported_enm_from_state_deployment.xml')
    DELTA_OUTPUT = os.path.join(ENM_RT_DIR, 'output_enm_deployment.txt')
    NMS_LITP = os.path.join(OPT_ERIC, 'nms', 'litp')
    LITP_MN_LIBVIRT = os.path.join(NMS_LITP, 'lib', 'litpmnlibvirt',
                                   'litp_libvirt_adaptor.py')
    LITP_RT_DIR = os.path.join(NMS_LITP, 'runtime')
    LITP_ETC_DIR = os.path.join(NMS_LITP, 'etc')
    LITP_PUPPET_DIR = os.path.join(LITP_ETC_DIR, 'puppet')
    MCO_LIST_BACKUP = os.path.join(os.sep, 'var', 'tmp', 'mco_list_backup')
    CRON_DIR = os.path.join(os.sep, 'etc', 'cron.d')
    HTML_DIR = os.path.join(os.sep, 'var', 'www', 'html')
    RHEL7_SYSTEM_AUTH = os.path.join(os.sep, 'etc', 'pam.d', 'system-auth')
    POSTGRES_ROOT_CERT = os.path.join(os.sep, 'root', '.postgresql',
                                       'root.crt')

    # The RHEL7.9 Uplift point will be major version 3.
    # The major version is part of the LITP R State number.
    # For R State 'R3EZ09' the major digit will be '3'.
    RHEL7_UPLIFT_LITP_VERSION = 3
    CMD_TIMEOUT = 4 * 60 * 60  # 4h

    # Match ERIClitpcore cherrypy_server.py response.timeout
    PLAN_TIMEOUT = 2 * 60 * 60  # 2h

    PARAM_VERBOSE = 'verbose'
    PARAM_ACTION = 'action'
    PARAM_ENM_TO_STATE = 'to_state_enm'
    PARAM_LITP_TO_STATE = 'to_state_litp'
    PARAM_MODEL = 'model'
    PARAM_SED = 'sed'
    PARAM_LITP_TO_VER = 'to_state_litp_version'
    PARAM_HYBRID = 'hybrid_state'
    PARAM_RESUME = 'resume'

    ACTION_CHOICES = ['get_upgrade_type',
                      'validate_deployment',
                      'create_backup',
                      'process_restored_data',
                      'rh7_uplift',
                      'perform_checks',
                      'complete_sfha_uplift']

    class Timeout(object):
        """
        Class to manage a timer/timeout
        """
        def __init__(self, seconds):
            """
            Initialise a new Timeout
            :param seconds: Seconds for which this Timeout should run
            :type seconds: int
            """
            self._expired = False
            self._wait_for = seconds
            self._start_time = Rh7EnmUpgrade.Timeout.get_time()

        def expire(self):
            """
            Mark the Timeout as complete/expired
            :return: None
            """
            self._expired = True

        @staticmethod
        def get_time():
            """
            Get the current time
            :return: The current time
            :rtype: int
            """
            return time.time()

        @staticmethod
        def sleep_for(seconds):
            """
            Sleep for a fixed time
            :param seconds: sleep interval
            :type seconds: int
            :return: None
            """
            time.sleep(seconds)

        def has_concluded(self):
            """
            has the timeout time elapsed or has it been expired
            :return: Boolean indicating of Timeout concluded
            :rtype: bool
            """
            return self.has_time_elapsed() or self._expired

        def has_time_elapsed(self):
            """
            Check if the maximum Timeout time has elapsed
            :return: Boolean True if Timeout seconds have elapsed
            """
            return self.get_time_elapsed() >= self._wait_for

        def get_time_elapsed(self):
            """
            Get the time difference between now and start of Timeout
            :return: Time difference
            :rtype: int
            """
            return int(Rh7EnmUpgrade.Timeout.get_time() - self._start_time)

        def get_remaining_time(self):
            """
            Get the time remaining in this Timeout
            :return: Time remaining
            :rtype: int
            """
            return int(self._wait_for - self.get_time_elapsed())

    class PushedFile(object):
        """
        Class to hold files that need to be pushed to nodes
        """
        def __init__(self, src, dest, node_list, consul_key):
            """
            Initialise a new PushedFile
            :param src: The file source
            :type src: string
            :param dest: The file destination
            :type dest: string
            :param node_list: The list of nodes to push the file to.
            :type node_list: list
            :param consul_key: The key for the consul kv store
            :type consul_key: string

            """
            self.src = src
            self.dest = dest
            self.node_list = node_list
            self.consul_key = consul_key

    def __init__(self, cmd_args=None):
        """
        Constructor
        :param cmd_args: Command line arguments
        :type cmd_args: list
        :return: None
        """
        self.cmd_args = cmd_args
        self.log = init_enminst_logging('enminst')
        self.parser = None
        self.current_stage = None
        self.indent = ''
        self.litp = None
        self.processed_args = None
        self.mco_peer_list = None
        self.mco_backup_list = None
        self.deps_clusters_nodes = collections.OrderedDict()
        self.the_to_state_dd = ''
        self.to_state_enm_iso_mnt_dir = os.path.join(os.sep, 'media', 'ENM')
        self.to_state_sgmnts_data = None
        self.tracker = os.path.join(Rh7EnmUpgrade.ENM_RT_DIR,
                                    '.rh7_uplift_tracker')
        self.disruptor = os.path.join(Rh7EnmUpgrade.ENM_RT_DIR,
                                    '.exit_after_stage')
        self.plugin_api_context = None
        self.sfha_nodes = None
        self.last_plan_do_nothing_plan = False

    def _init_node_data(self):
        """
        Initialize LITP deployment, cluster, node data
        :return: None
        """

        if not self.litp:
            self.litp = LitpRestClient()

        dep_clusters = self.litp.get_deployment_clusters()
        clus_nodes = self.litp.get_cluster_nodes()

        self.deps_clusters_nodes = collections.OrderedDict()
        for dep in dep_clusters.keys():
            self.deps_clusters_nodes[dep] = collections.OrderedDict()
            for clus in dep_clusters[dep]:
                self.deps_clusters_nodes[dep][clus] = clus_nodes[clus].keys()

    def _init_plugin_api_context(self, conf_file=None, timeout=30):
        """
        Instantiate PluginApiContext instance
        :return: None
        """
        try:
            # pylint: disable=F0401,E0611
            from litp.core import scope
            from litp.core.model_manager import ModelManagerNextGen
            from litp.core.nextgen.plugin_manager import PluginManager
            from litp.core.plugin_context_api import PluginApiContext
            from litp.data.db_storage import DbStorage, get_engine
            from litp.data.data_manager import DataManager
            import cherrypy
        except ImportError as ierror:
            msg = 'Failed to import LITP module(s): {0}'.format(ierror)
            self._print_error(msg)
            sys.exit(1)

        if not conf_file:
            conf_file = os.path.join(os.sep, 'etc', 'litpd.conf')

        cherrypy.config.update(conf_file)
        model_manager = ModelManagerNextGen()
        plugin_manager = PluginManager(model_manager)

        plugin_manager.add_extensions(os.path.join(Rh7EnmUpgrade.LITP_ETC_DIR,
                                                   'extensions'))

        db_storage = DbStorage(get_engine(cherrypy.config))
        data_manager = DataManager(db_storage.create_session())
        scope.data_manager = data_manager
        data_manager.configure(model_manager)
        self.plugin_api_context = PluginApiContext(model_manager)

        timeout = Rh7EnmUpgrade.Timeout(timeout)
        from sqlalchemy.exc import ProgrammingError
        ms_qitem = None
        while not timeout.has_concluded():
            try:
                ms_qitem = self.plugin_api_context.query_by_vpath('/ms')
            except ProgrammingError as p_e:
                self.log.debug(
                    'PluginApiContext query_by_vpath failure: {0}'.format(p_e))
                timeout.sleep_for(1)
            else:
                timeout.expire()

        if not ms_qitem:
            msg = 'Error initializing PluginApiContext'
            self._print_error(msg)
            sys.exit(1)

    def _get_verbose_param(self):
        """
        Get verbose parameter value
        :return: True if verbose enabled else False
        :rtype: bool
        """
        return getattr(self.processed_args, Rh7EnmUpgrade.PARAM_VERBOSE, False)

    def _get_resume_param(self):
        """
        Get resume parameter value
        :return: True if resume is specified else False
        :rtype: bool
        """
        return getattr(self.processed_args, Rh7EnmUpgrade.PARAM_RESUME, False)

    def set_verbosity_level(self):
        """
        Set the logging verbosity level based on the 'verbose' parameter
        :return: None
        """

        if self._get_verbose_param():
            set_logging_level(self.log, 'DEBUG')

    def get_psql_host_option(self):
        """
        Get the psql host option
        :return: Correct host option.
        :rtype: string
        """
        if os.path.exists(Rh7EnmUpgrade.POSTGRES_ROOT_CERT):
            return ' -h ' + self._get_hostname()
        else:
            return ''

    def _assert_rhel_version(self, expected_ver):
        """
        Assert the Platform is a specific version
        :param expected_ver: Expected RHEL OS version
        :type expected_ver: string
        :return: None
        """
        self.log.debug("Assert the Platform version is '{0}'"
                       .format(expected_ver))

        ver_names = {'6.10': 'Santiago',
                     '7.9': 'Maipo'}

        version = platform.dist()
        for idx, expected_val in enumerate(['redhat',
                                            expected_ver,
                                            ver_names[expected_ver]]):
            try:
                assert expected_val == version[idx]
            except AssertionError:
                msg = 'Unexpected Platform info: {0}'.format(version[idx])
                self._print_error(msg)
                sys.exit(1)

    def create_arg_parser(self):
        """
        Create an argument parser
        :return: None
        """

        this_script = 'rh7_upgrade_enm.sh'
        usage = (this_script + ' --action <action> [-h] [-v] ' +
                 '[--{0} <rstate-version>] ' +
                 '[--{1} <path>] ' +
                 '[--{2} <path>] ' +
                 '[--{3} <path>] ' +
                 '[--{4} <path>] ' +
                 '[--{5}] [--{6}]'
                ).format(Rh7EnmUpgrade.PARAM_LITP_TO_VER,
                         Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
                         Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
                         Rh7EnmUpgrade.PARAM_MODEL,
                         Rh7EnmUpgrade.PARAM_SED,
                         Rh7EnmUpgrade.PARAM_HYBRID,
                         Rh7EnmUpgrade.PARAM_RESUME)

        epilog = textwrap.dedent('''
# %(prog)s --action {0} --{1} <rstate-version>
    -> Determine ENM Upgrade type
# %(prog)s --action {2} \
--{3} <path of LITP model file>
    -> Validate deployment before uplift
# %(prog)s --action {4}
    -> Create backup data
# %(prog)s --action {5}
    -> Process restored data
# %(prog)s --action {6} \
--{3} <path of LITP model file>
  --{7} <path of SED>
  --{8} <path of To-state ENM ISO>
  --{9} <path of To-state LITP ISO>
    -> Perform RHEL 7.9 uplift
# %(prog)s --action {10}
    -> Perform Upgrade prechecks and Health checks
# %(prog)s --action {11}
    -> Complete SFHA uplift (VX DG/DL upgrade, enable selinux, reboot DB nodes)
'''.format(Rh7EnmUpgrade.ACTION_CHOICES[0], Rh7EnmUpgrade.PARAM_LITP_TO_VER,
           Rh7EnmUpgrade.ACTION_CHOICES[1], Rh7EnmUpgrade.PARAM_MODEL,
           Rh7EnmUpgrade.ACTION_CHOICES[2],
           Rh7EnmUpgrade.ACTION_CHOICES[3],
           Rh7EnmUpgrade.ACTION_CHOICES[4],
           Rh7EnmUpgrade.PARAM_SED,
           Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
           Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
           Rh7EnmUpgrade.ACTION_CHOICES[5],
           Rh7EnmUpgrade.ACTION_CHOICES[6]))

        self.parser = ArgumentParser(prog=this_script,
                                     usage=usage,
                                     formatter_class=RawTextHelpFormatter,
                                     epilog=epilog,
                                     add_help=False)

        text = 'Where action can be one of:\n- {0}'.format(
                '\n- '.join(Rh7EnmUpgrade.ACTION_CHOICES))

        required_group = self.parser.add_argument_group('required arguments')

        required_group.add_argument('--action',
                                    dest=Rh7EnmUpgrade.PARAM_ACTION,
                                    default='',
                                    help=text)

        optional_group = self.parser.add_argument_group('optional arguments')

        optional_group.add_argument('--help', '-h',
                                    action='help',
                                    help='Show this help message and exit')

        optional_group.add_argument('--verbose', '-v',
                                    dest=Rh7EnmUpgrade.PARAM_VERBOSE,
                                    default=False,
                                    action='store_true',
                                    help='Enable verbose logging')

        string_args = [{'arg': Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
                        'help': 'To-state ENM ISO path'},
                       {'arg': Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
                        'help': 'To-state LITP ISO path'},
                       {'arg': Rh7EnmUpgrade.PARAM_MODEL,
                        'help': 'To-state LITP model path'},
                       {'arg': Rh7EnmUpgrade.PARAM_SED,
                        'help': 'To-state Site Engineering Document'},
                       {'arg': Rh7EnmUpgrade.PARAM_LITP_TO_VER,
                        'help': 'To-state LITP r-state version'}]

        for string_arg in string_args:
            optional_group.add_argument('--{0}'.format(string_arg['arg']),
                                        dest=string_arg['arg'],
                                        default=False,
                                        help=string_arg['help'])

        bool_args = [{'arg': Rh7EnmUpgrade.PARAM_HYBRID,
                      'help': 'Hybrid state'},
                     {'arg': Rh7EnmUpgrade.PARAM_RESUME,
                      'help': 'Resume uplift'}]
        for bool_arg in bool_args:
            optional_group.add_argument('--{0}'.format(bool_arg['arg']),
                                        dest=bool_arg['arg'],
                                        default=False,
                                        action='store_true',
                                        help=bool_arg['help'])

    def _assert_return_code(self, return_code, text, allowed_codes=None):
        """
        Assert a return code from a command is as expected
        :param return_code: the command return code
        :type return_code: integer
        :param text: text for formatted error message
        :type text: string
        :param allowed_codes: list of allowed return codes
        :type allowed_codes: list of integers
        :return: None
        :rtype: None

        """
        allowed_return_codes = allowed_codes if allowed_codes else [0]

        try:
            assert return_code in allowed_return_codes
        except AssertionError:
            msg = 'Failed to run command, error: ' + text
            self._print_error(msg)
            sys.exit(1)

    def _print_warning(self, text):
        """
        Print a warning line
        :param text: Text to print
        :type text: string
        :return: None
        """
        all_text = '*****'
        if self.current_stage:
            all_text += ' (stage {0}/{1}):'.format(self.current_stage['idx'],
                                                   self.current_stage['label'])

        all_text += ' {0} *****'.format(text)
        self.log.warn(all_text)

    def _print_error(self, text, add_suffix=True):
        """
        Print an error line
        :param text: Text to print
        :type text: string
        :param add_suffix: should the standard suffix be appended
        :type add_suffix: bool
        :return: None
        """

        all_text = '***** FAILED'

        if self.current_stage:
            all_text += ' (stage {0}/{1})'.format(self.current_stage['idx'],
                                                  self.current_stage['label'])

        all_text += ': {0}'.format(text)

        if add_suffix:
            suffix = ('Do not proceed with the uplift. For more information, '
                      'contact your local Ericsson support team.')
            all_text += '. {0}'.format(suffix)

        all_text += ' *****'

        self.log.error(all_text)

    def _print_message(self, text):
        """
        Print a simple message
        :param text: Text to print
        :type text: string
        :return: None
        """
        self.log.info(self.indent + text)

    def process_action(self):
        """
        Process the action
        :return: None or return from handler
        :rtype: None or string
        """

        if not self.processed_args.action:
            self.parser.print_help()
            sys.exit(2)

        if self.processed_args.action not in Rh7EnmUpgrade.ACTION_CHOICES:
            msg = 'Action must be 1 of {0}'.format(
                    ', '.join(Rh7EnmUpgrade.ACTION_CHOICES))
            self._print_error(msg)
            sys.exit(1)

        if Rh7EnmUpgrade.ACTION_CHOICES[0] != self.processed_args.action:
            if self.processed_args.to_state_litp_version:
                msg = '"{0}" only allowed with the "{1}" action'\
                           .format(Rh7EnmUpgrade.PARAM_LITP_TO_VER,
                                   Rh7EnmUpgrade.ACTION_CHOICES[0])

                self._print_error(msg)
                sys.exit(1)
        else:
            if not self.processed_args.to_state_litp_version:
                msg = '"{0}" required with the "{1}" action'\
                           .format(Rh7EnmUpgrade.PARAM_LITP_TO_VER,
                                   Rh7EnmUpgrade.ACTION_CHOICES[0])

                self._print_error(msg)
                sys.exit(1)

        if self.processed_args.action not in (Rh7EnmUpgrade.ACTION_CHOICES[1],
                                              Rh7EnmUpgrade.ACTION_CHOICES[4]):
            for arg in [Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
                        Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
                        Rh7EnmUpgrade.PARAM_MODEL,
                        Rh7EnmUpgrade.PARAM_SED,
                        Rh7EnmUpgrade.PARAM_HYBRID,
                        Rh7EnmUpgrade.PARAM_RESUME]:
                if getattr(self.processed_args, arg, False):
                    msg = '"{0}" not allowed with the "{1}" action'\
                          .format(arg, self.processed_args.action)
                    self._print_error(msg)
                    sys.exit(1)
        else:
            if self.processed_args.action == Rh7EnmUpgrade.ACTION_CHOICES[1]:
                for arg in [Rh7EnmUpgrade.PARAM_MODEL]:
                    if not getattr(self.processed_args, arg, False):
                        msg = '"{0}" required with the "{1}" action'\
                              .format(arg, Rh7EnmUpgrade.ACTION_CHOICES[1])
                        self._print_error(msg)
                        sys.exit(1)
                for arg in [Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
                            Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
                            Rh7EnmUpgrade.PARAM_SED,
                            Rh7EnmUpgrade.PARAM_HYBRID,
                            Rh7EnmUpgrade.PARAM_RESUME]:
                    if getattr(self.processed_args, arg, False):
                        msg = '"{0}" not allowed with the "{1}" action'\
                              .format(arg, Rh7EnmUpgrade.ACTION_CHOICES[1])
                        self._print_error(msg)
                        sys.exit(1)
            elif self.processed_args.action == Rh7EnmUpgrade.ACTION_CHOICES[4]:
                for arg in [Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
                            Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
                            Rh7EnmUpgrade.PARAM_MODEL,
                            Rh7EnmUpgrade.PARAM_SED]:
                    if not getattr(self.processed_args, arg, False):
                        msg = '"{0}" required with the "{1}" action'\
                              .format(arg, Rh7EnmUpgrade.ACTION_CHOICES[4])
                        self._print_error(msg)
                        sys.exit(1)

        for arg in [Rh7EnmUpgrade.PARAM_ENM_TO_STATE,
                    Rh7EnmUpgrade.PARAM_LITP_TO_STATE,
                    Rh7EnmUpgrade.PARAM_MODEL,
                    Rh7EnmUpgrade.PARAM_SED]:
            arg_val = getattr(self.processed_args, arg, False)
            if arg_val and not os.path.exists(arg_val):
                msg = 'Invalid path "{0}" for parameter "{1}"'.format(arg_val,
                                                                      arg)
                self._print_error(msg)
                sys.exit(1)

        handlers = [self._get_upgrade_type,
                    self._validate_deployment,
                    self._create_backup_data,
                    self._process_restored_data,
                    self._do_rh7_uplift,
                    self._perform_checks,
                    self._cmplt_sfha_uplift]

        action_handlers = dict(zip(Rh7EnmUpgrade.ACTION_CHOICES,
                                   handlers))

        action_handlers[self.processed_args.action]()

    def _print_success(self, text):
        """
        Print a success line
        :param text: Text to print
        :type text: string
        :return: None
        """
        all_text = '***** PASSED: {0} *****'.format(text)
        self.log.info(self.indent + all_text)

    @staticmethod
    def _get_hostname():
        """
        Get the hostname
        :return: Node hostname
        :rtype: string
        """
        return platform.node()

    def _get_backup_litp_state(self):
        """
        Create backup LITP DB.
        :return: Absolute path to LITP backup file
        :rtype: string
        """

        if not os.path.exists(Rh7EnmUpgrade.LITP_RT_DIR):
            try:
                os.mkdir(Rh7EnmUpgrade.LITP_RT_DIR)
            except OSError:
                msg = 'Failed to create directory {0}'.format(
                                                    Rh7EnmUpgrade.LITP_RT_DIR)
                self._print_error(msg)
                sys.exit(1)
            else:
                self.log.debug('Created {0}'.format(Rh7EnmUpgrade.LITP_RT_DIR))

        litp_state_backup_exe = os.path.join(Rh7EnmUpgrade.NMS_LITP,
                                         'bin', 'litp_state_backup.sh')
        cmd = litp_state_backup_exe + ' ' + Rh7EnmUpgrade.LITP_RT_DIR
        return_code, stdout = self._run_command(cmd,
                                        timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, cmd + ':' + stdout)
        filepath = stdout.split(' ')[-1]

        if not filepath:
            files = glob.glob(os.path.join(Rh7EnmUpgrade.LITP_RT_DIR,
                                           'litp_backup_*'))
            if files:
                filepath = max(files, key=os.path.getctime)

        if filepath:
            self.log.debug('LITP backup file: {0}'.format(filepath))

        return filepath

    def _export_litp_model(self, vpath, xml_file):
        """
        Do an export of the LITP model.
        :param vpath: The vpath to export from
        :type vpath: string
        :param xml_file: XML file to which to export.
        :type xml_file: string
        """
        cmd = "litp export -p {0} -f {1}".format(vpath, xml_file)
        return_code, _ = self._run_command(cmd,
                            timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code,
                     'Export LITP deployment model to {0}'.format(xml_file))

    def _get_mco_peer_list(self):
        """
        Function to get the list of Peer Nodes from the 'mco find' command.
        :return: mco_peer_list
        :rtype: string
        """
        cmd = "/usr/bin/mco find -W puppet_master=false"
        return_code, mco_peer_list = self._run_command(cmd,
                                       timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, cmd + ' : ' + mco_peer_list)

        return mco_peer_list

    def _create_mco_peer_list_backup(self):
        """
        Save the list of Peer Nodes in a backup file for comparison during
        the uplift.
        :return: None
        """
        self.log.debug("Backup the mco Peer Node list to {0}"
                       .format(Rh7EnmUpgrade.MCO_LIST_BACKUP))
        self._write_to_file(Rh7EnmUpgrade.MCO_LIST_BACKUP,
                            self._get_mco_peer_list())

    def _run_command_set(self, cmds, cmd_desc_preamble):
        """
        Run set of commands
        :param cmds: Command to run
        :type cmds: list
        :param cmd_desc_preamble: Command description preamble
        :type cmd_desc_preamble: string
        :return: None
        """
        for cmd in cmds:
            return_code, _ = self._run_command(cmd,
                                      timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
            msg = cmd_desc_preamble + ': ' + cmd
            self._assert_return_code(return_code, msg)

    def _run_command(self, command, timeout_secs=CMD_TIMEOUT, do_logging=True):
        """
        Thin wrapper to call subprocess.Popen
        :param command: Command string to execute
        :type command: string
        :param timeout_secs: seconds to wait before timing out command
        :type timeout_secs: integer
        :param do_logging: Boolean, default True, indiciating if
                           logging should be performed
        :type do_logging: bool
        :return: returncode, STDOUT text
        :rtype: 2-tuple: int, string
        """

        if do_logging:
            self.log.info('Will run command: {0}'.format(command))

        stdout = ''
        process = None

        command_to_log = command if do_logging else '<hidden>'
        timeout = Rh7EnmUpgrade.Timeout(timeout_secs)

        try:
            process = subprocess.Popen(command,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       shell=True)
        except OSError as oe_err:
            msg = ('Error processing command {0}, {1}, {2}'
                   .format(command_to_log, oe_err.errno, oe_err.strerror))
            self._print_error(msg)
            sys.exit(1)

        while process.poll() is None and not timeout.has_time_elapsed():
            timeout.sleep_for(0.5)

        if process.poll() is None and timeout.has_time_elapsed():
            msg = 'Command timed out, {0}'.format(command_to_log)
            self._print_error(msg)
            sys.exit(1)

        stdout, _ = process.communicate()
        cleaned_stdout = stdout.strip()
        if do_logging:
            self.log.debug('Return code: {0}, Output: "{1}"'
                           .format(process.returncode, cleaned_stdout))

        return process.returncode, cleaned_stdout

    def _run_rpc_mco(self, command):
        """
        Run an RPC MCO command (1 command with possibly multiple hosts)
        :param command: Command string to execute
        :type command: string
        :return: returncode, results
        :rtype: 2-tuple: int, dict
        """

        def _find_errors(node_result):
            """
            Extract errors from result
            :param node_result: Node specific result
            :type node_result: dict
            :return: node result
            :rtype: string
            """
            if node_result['statuscode'] != 0:
                return u"{0}".format(node_result.get('err', 'unknown'))

            if 'data' in node_result.keys() and \
               'retcode' in node_result['data'].keys():
                if node_result['data']['retcode'] != 0 and \
                   'err' in node_result['data'].keys():
                    return u"{0}".format(node_result['data']['err'])
            return u""

        if not command.startswith('mco rpc '):
            msg = 'Not a valid mco rpc command: {0}'.format(command)
            self._print_error(msg)
            sys.exit(1)

        if '--json' not in command:
            command += ' --json'

        returncode, stdout = self._run_command(command)

        results = {}
        try:
            output = simplejson.loads(stdout.decode('UTF8'))
        except ValueError as err:
            output = [{'sender': 'unknown',
                       'data': {},
                       'statuscode': 1,
                       'err': err}]
        for node_result in iter(output):
            results[str(node_result['sender'])] = {
                        'data': node_result['data'],
                        'errors': _find_errors(node_result)}
        return returncode, results

    @staticmethod
    def _get_elect_files():
        """
        Returns a list of ELECT policies and associated crons if
        any policies exits. Else returns an empty list
        """
        elect_files = []
        policy_path = os.path.join(Rh7EnmUpgrade.OPT_ERIC,
                                   'elasticsearch', 'policies')
        if not os.path.isdir(policy_path):
            return elect_files
        policies = os.listdir(policy_path)
        elect_files = [ef for policy in policies for ef in
                       (os.path.join(policy_path, policy),
                        os.path.join(Rh7EnmUpgrade.CRON_DIR,
                                     os.path.splitext(policy)[0]))]
        return elect_files

    @staticmethod
    def _create_tarfile(tar_name, data_dir):
        """
        Create a named tarfile, with data from a given data directory.
        :param tar_name: tar file name
        :type tar_name: string
        :param data_dir: Data directory (path)
        :type data_dir: string
        :return: None
        """
        tar = tarfile.open(tar_name, mode='w:gz')
        for artifact in glob.glob(data_dir):
            tar.add(artifact, arcname='./')
        tar.close()

    @staticmethod
    def _gen_esmon_backup_name():
        """
        Generate ESMon backup filename
        :return: ESMon backup filename
        :rtype: string
        """
        return os.path.join(os.sep, 'ericsson', 'enm', 'dumps',
                            'esmon_vol_data_backup.tgz')

    def _get_backup_esmon_data(self):
        """
        Backup ESMon data
        :return: ESMon backup name
        :rtype: string
        """
        vg_name = 'vg_root'
        vol_name = 'vg1_fs_data'

        esmon_svc_name = 'esmon'
        device = os.path.join(os.sep, 'dev', vg_name, vol_name)

        bkup_name = Rh7EnmUpgrade._gen_esmon_backup_name()
        mnt_dir = os.path.join(os.sep, 'mnt', 'tmp_esmon_data')

        cmds1 = [Rh7EnmUpgrade.LITP_MN_LIBVIRT + \
                 ' {0} stop-undefine --stop-timeout=45'.format(esmon_svc_name),
                 'mkdir -p {0}'.format(mnt_dir),
                 'mount {0} {1}'.format(device, mnt_dir)]

        cmd_desc_preamble = 'Prepare ESMon data for backup'
        self._run_command_set(cmds1, cmd_desc_preamble)

        self.log.debug('Creating ESMon data Tar {0}'.format(bkup_name))

        Rh7EnmUpgrade._create_tarfile(bkup_name, mnt_dir)

        cmds2 = ['umount {0}'.format(mnt_dir),
                 'rmdir {0}'.format(mnt_dir),
                 'service {0} start'.format(esmon_svc_name)]

        cmd_desc_preamble = 'Cleanup after backing up ESMon data'
        self._run_command_set(cmds2, cmd_desc_preamble)

        msg = 'ESMon data successfully backed up {0}'.format(bkup_name)
        self._print_success(msg)

        return bkup_name

    def _assert_files_exist(self, file_data):
        """
        Assert all file paths exist
        :param file_data: file data
        :type file_data: list of dicts
        :return: None
        """
        paths = set([entry['path'] for entry in file_data])
        for path in paths:
            if not os.path.exists(path):
                msg = 'File not found: {0}'.format(path)
                self._print_error(msg)
                sys.exit(1)

    def _create_users(self, file_data):
        """
        Create POSIX users
        :param file_data: file data
        :type file_data: list of dicts
        :return: None
        """

        known_users = {'litp-admin': {'id': '1000',
                                    'groups': 'celery,litp-admin,litp-access'},
                       'rabbitmq': {'comment': '"RabbitMQ messaging server"',
                                    'home': '/var/lib/rabbitmq'},
                       'postgres': {'id': '26',
                                    'comment': '"PostgreSQL Server"',
                                    'home': '/var/lib/pgsql'},
                       'celery': {'comment': 'Celery user',
                             'groups': 'litp-admin,celery,puppet,litp-access'},
                       'puppet': {'id': '52',
                                  'comment': 'Puppet',
                                  'home': '/var/lib/puppet',
                                  'shell': '/sbin/nologin'},
                       'puppetdb': {'comment': '"PuppetDB daemon"',
                                    'home': '/usr/share/puppetdb',
                                    'shell': '/sbin/nologin'}}

        for kuser, kattrs in known_users.iteritems():
            for (kattr, kvalue) in (('comment', kuser),
                                    ('home', '/home/{0}'.format(kuser)),
                                    ('shell', '/bin/bash')):
                if not kattr in kattrs.keys():
                    kattrs[kattr] = kvalue

        users = set([entry['user'] for entry in file_data])

        self.log.debug('Ensuring users exist: {0}'.format(users))

        cmds = []
        for user in users:
            try:
                _ = getpwnam(user).pw_uid,
            except KeyError:
                cmd = 'useradd -m -r {0}'.format(user)
                if user in known_users.keys():
                    for (label, param) in (('id', '-u'),
                                           ('groups', '-G')):
                        if label in known_users[user].keys():
                            cmd += ' {0} {1}'.format(param,
                                                     known_users[user][label])

                    for (label, param) in (('comment', '-c'),
                                           ('shell', '-s'),
                                           ('home', '-d')):
                        cmd += ' {0} {1}'.format(param,
                                                 known_users[user][label])

                cmds.append(cmd)
        if cmds:
            msg = 'Create system users'
            self._run_command_set(cmds, msg)

    def _create_groups(self, file_data):
        """
        Create POSIX groups
        :param file_data: file data
        :type file_data: list of dicts
        :return: None
        """

        fixed_group_ids = {'litp-admin': '1000',
                           'postgres': '26',
                           'puppet': '52'}

        groups = set([entry['group'] for entry in file_data])

        self.log.debug('Ensuring groups exist: {0}'.format(groups))

        cmds = []
        for group in groups:
            try:
                _ = getgrnam(group).gr_gid
            except KeyError:
                cmd = 'groupadd -r {0}'.format(group)
                if group in fixed_group_ids.keys():
                    cmd += ' -g {0}'.format(fixed_group_ids[group])
                cmds.append(cmd)
        if cmds:
            msg = 'Create system groups'
            self._run_command_set(cmds, msg)

    @staticmethod
    def _chmod_file(path, mode):
        """
        Change mode on a file
        :param path: path to file
        :type path: string
        :param mode: target mode
        :type mode: string
        :return: None
        """
        target_mode_str = mode.lstrip('0')
        if target_mode_str != str(oct(os.stat(path).st_mode)[-3:]):
            target_mode_int = int(target_mode_str, 8)
            os.chmod(path, target_mode_int)

    @staticmethod
    def _get_restored_files():
        """
        Get the restored files data
        :return: restored files data
        :rtype: string
        """
        # Path  User  Group  Mode
        file_data_str = \
"""/opt/ericsson/nms/litp/keyset/keyset1 root litp-admin 0440
/etc/puppetdb/ssl puppetdb puppetdb 0700
/etc/puppetdb/ssl/ca.pem puppetdb puppetdb 0600
/etc/puppetdb/ssl/private.pem puppetdb puppetdb 0600
/etc/puppetdb/ssl/public.pem puppetdb puppetdb 0600"""

        return file_data_str

    @staticmethod
    def _gen_file_data(file_data_str):
        """
        Convert a file data string into structured data
        :return: structured file data
        :rtype: list of dicts
        """
        return [dict(zip(['path', 'user', 'group', 'mode'],
                         line.split(' ', 4)))
                for line in file_data_str.splitlines()]

    def _restore_file_attrs(self):
        """
        Set the file ownership and mode on certain files
        :return: None
        """

        file_data = Rh7EnmUpgrade._gen_file_data(
                           Rh7EnmUpgrade._get_restored_files())

        self._assert_files_exist(file_data)

        self._create_groups(file_data)
        self._create_users(file_data)

        for file_info in file_data:
            self.log.debug('Ensuring correct attributes on {0}'.format(
                                                            file_info['path']))

            if os.path.isdir(file_info['path']):
                cmds = ['chown {0}.{1} {2}'.format(file_info['user'],
                                                   file_info['group'],
                                                   file_info['path']),
                        'chmod {0} {1}'.format(file_info['mode'],
                                               file_info['path'])]
                msg = 'Restore attributes on folder {0}'.format(
                                                             file_info['path'])
                self._run_command_set(cmds, msg)
            else:
                self._chown_file(file_info['path'],
                                 file_info['user'],
                                 file_info['group'])

                Rh7EnmUpgrade._chmod_file(file_info['path'],
                                          file_info['mode'])

    @staticmethod
    def _get_all_non_plugin_repo_paths():
        """
        Get the list of all non plugin repository paths
        :return: List of repo paths
        :rtype: list of strings
        """

        litp_path = os.path.join(Rh7EnmUpgrade.HTML_DIR, 'litp')
        html_repodata_path = os.path.join(Rh7EnmUpgrade.HTML_DIR, 'repodata')

        return [os.path.join(os.path.split(root)[0], '')
              for root, _, files in os.walk(Rh7EnmUpgrade.HTML_DIR)
              for filename in files
              if filename == 'repomd.xml' and not os.path.join(
                  root, filename).startswith(litp_path)
                  and not root == html_repodata_path]

    @staticmethod
    def _get_enm_repo_names_from_paths():
        """
        Get the list of ENM repository names
        :return: List of repo names
        :rtype: list of strings
        """
        suffix = '_rhel7/'
        repo_names = []
        for repo_path in Rh7EnmUpgrade._get_all_non_plugin_repo_paths():
            if repo_path.endswith(suffix):
                repo_names.append(os.path.basename(os.path.normpath(repo_path)
                                                   )[:-(len(suffix) - 1)]
                                  )
        return repo_names

    def _refresh_yum_repos(self):
        """
        Refresh / recreate yum repos after data has been restored
        :return: None
        """

        def _format_create_repo_cmd(path):
            """
            Format a create-repo command
            :param path: subfolder of yum public dir
            :type path: Directory path
            :return: fully formatted create-repo command
            :rtype: string
            """
            return 'createrepo {0}'.format(path)

        repo_paths = Rh7EnmUpgrade._get_all_non_plugin_repo_paths()

        cmds = ['yum clean metadata'] + \
               [_format_create_repo_cmd(
                  os.path.join(Rh7EnmUpgrade.HTML_DIR, folder))
                 for folder in ('litp', 'litp_plugins')] + \
               [_format_create_repo_cmd(path)
                 for path in repo_paths
                 if '7.9' not in path and '_rhel7' not in path and\
                 '6.10' not in path and '7.6' not in path] + \
               [_format_create_repo_cmd(os.path.join(Rh7EnmUpgrade.HTML_DIR,
                                        os.path.join(version, folder,
                                                     'x86_64', 'Packages')))
                for folder in ('os', 'updates')
                for version in ('6.10', '7.6')
                if os.path.exists(os.path.join(Rh7EnmUpgrade.HTML_DIR,
                                               version, folder,
                                               'x86_64', 'Packages'))]

        msg = 'Refresh yum repositories'
        self._run_command_set(cmds, msg)

    def _create_symlinks(self):
        """
        Ensure symlinks to OS folders exist.
        :return: None
        """
        for (src, dst) in (('7.9', '7'),
                           ('6.10', '6')):
            spath = os.path.join(Rh7EnmUpgrade.HTML_DIR, src, '')
            dpath = os.path.join(Rh7EnmUpgrade.HTML_DIR, dst)
            if not os.path.islink(dpath):
                if os.path.exists(spath):
                    os.symlink(spath, dpath)
                else:
                    msg = ('Cannot create symlink {0} -> {1} as the source ' +
                           'does not exist').format(dpath, spath)
                    self._print_error(msg)
                    sys.exit(1)

    def _reload_sentinel_licesnses(self):
        """
        Reload Sentinel Licenses
        :return: None
        """
        service = ['sentinel']
        self._process_lms_services(service, 'stop')
        self._process_lms_services(service, 'start')

    def _process_restored_data(self):
        """
        Action handler to process data restored to MS
        """
        self._assert_rhel_version('7.9')

        self._restore_file_attrs()
        self._refresh_yum_repos()
        self._create_symlinks()
        self._reload_sentinel_licesnses()

        msg = 'Restored data successfully processed'
        self._print_success(msg)

    def _is_valid_r_state(self, r_state):
        """
        Validate the provided string is a valid 'R' State.
        :param r_state: The R State to check.
        :rtype r_state: string
        :return: True if the R State is valid, False otherwise
        :rtype: bool
        """
        self.log.debug("Validate R State {0}".format(r_state))
        return re.match(
            r'r[0-9]{1,3}[a-z]{1,2}[0-9]{0,2}(?:.*)', r_state, re.IGNORECASE)

    def _get_rhel_version_on_ms(self):
        """
        Get the RHEL version of the MS.
        :return: the RHEL version of the MS.
        :rtype: string
        """
        self.log.debug("Get the RHEL version of the MS.")

        # Get the RedHat release of the MS.
        ms_rhel = RHELUtil.get_current_version()
        self.log.debug("The MS has RHEL Version '{0}'".format(ms_rhel))
        return ms_rhel

    def _get_rhel_version_on_nodes(self):
        """
        Get the RHEL version and State of each peer node in the deployment.
        :return: peer_node_rhel_dict
        :rtype: dictionary
        """
        self.log.debug("Get the RHEL version and State of each Peer Node.")

        if not self.litp:
            self.litp = LitpRestClient()

        # Get the list of Peer Node profiles from the LITP Model.
        profiles = self.litp.get_all_items_by_type(
            '/deployments', 'reference-to-os-profile', [])

        # Loop through the list of Peer Node profiles and get the RedHat
        # version for each node.
        peer_node_rhel_dict = {}
        for profile in profiles:
            node = profile['path'].split('/')[-2]
            peer_node_rhel_dict[node] = \
                [profile['data']['properties']['version'],
                 profile['data']['state']]

        self.log.debug("The Peer Nodes with their RHEL versions and state are:"
                       "{0}".format(peer_node_rhel_dict))
        return peer_node_rhel_dict

    def _get_upgrade_type(self):
        """
        Determine and print the upgrade type.
        There are three possible upgrade types:
           RHEL7   -> RHEL7 Upgrade
           RHEL6   -> RHEL7 Uplift
           RHEL6+7 -> RHEL7 Hybrid (RHEL7 MS + RHEL6 Peer Nodes)
           RHEL6   -> RHEL6 Upgrade (Legacy)
        The parameter RHEL7_UPLIFT_LITP_VERSION will determine the RHEL7 Uplift
        point.

        :return: None
        """
        self.log.debug("Entering get_upgrade_type")

        # Get the To-state LITP Major version.
        litp_to_state_version = self.processed_args.to_state_litp_version
        self.log.debug("The To-state LITP version is '{0}'"
                       .format(litp_to_state_version))

        if not self._is_valid_r_state(litp_to_state_version):
            msg = ("The To-state R Version '{0}' is not in the correct format"
                   .format(litp_to_state_version))
            self._print_error(msg)
            sys.exit(1)

        litp_major_regex = r'^R(?P<major>[0-9]{1,3})(?:.*)'
        litp_to_state_match = re.match(
            litp_major_regex, litp_to_state_version, re.IGNORECASE)
        to_state_litp_major_version = int(litp_to_state_match.group('major'))
        self.log.debug("LITP To-state R version is '{0}' with Major version "
                       "'{1}'".format(litp_to_state_version,
                                      to_state_litp_major_version))

        self.log.debug("Designated RHEL7 LITP Uplift Major Version is '{0}'"
                       .format(self.RHEL7_UPLIFT_LITP_VERSION))

        # Get the From-state LITP Major version.
        current_litp_version =\
            self._read_file(LITP_RELEASE_FILENAME).split()[-1]
        self.log.debug("The Current LITP version is '{0}'"
                       .format(current_litp_version))

        if not self._is_valid_r_state(current_litp_version):
            msg = ("The current LITP R Version '{0}' is not in the correct "
                   "format".format(current_litp_version))
            self._print_error(msg)
            sys.exit(1)

        current_match = re.match(
            litp_major_regex, current_litp_version, re.IGNORECASE)
        current_litp_major_version = int(current_match.group('major'))
        self.log.debug("LITP From-state R-version is '{0}' with Major version "
                       "'{1}'".format(current_litp_version,
                                      current_litp_major_version))

        # Compare the Major versions of the From-state and To-state against the
        # Uplift Point and Print the upgrade type.
        # It may also be necessary to compare the Peer Node RHEL versions.
        if (current_litp_major_version < self.RHEL7_UPLIFT_LITP_VERSION) and\
                (self.RHEL7_UPLIFT_LITP_VERSION <=
                 to_state_litp_major_version):
            upgrade_type = "2 (RH7 uplift)"
        else:
            # Find the RHEL version on each Peer node
            peer_node_rhel_dict = self._get_rhel_version_on_nodes()

            if (self.RHEL7_UPLIFT_LITP_VERSION <=
                    current_litp_major_version) and \
                    all(node_rhel[0] == "rhel7" and node_rhel[1] == "Applied"
                        for node_rhel in peer_node_rhel_dict.values()):
                upgrade_type = "3 (RH7 upgrade off)"
            elif (self.RHEL7_UPLIFT_LITP_VERSION <=
                    current_litp_major_version) and \
                    (any(node_rhel[0] == 'rhel6'
                         for node_rhel in peer_node_rhel_dict.values()) or
                     any(node_rhel[0] == 'rhel7'
                         for node_rhel in peer_node_rhel_dict.values()
                         if node_rhel[1] == "Initial") or
                     any(node_rhel[0] == 'rhel7'
                         for node_rhel in peer_node_rhel_dict.values()
                         if node_rhel[1] == "Updated")):
                upgrade_type = "4 (RH6-RH7 hybrid)"
            else:
                upgrade_type = "1 (Legacy Upgrade)"

        self.log.debug("This Upgrade type will be: {0}".format(upgrade_type))
        print upgrade_type

    def _chk_postgres_uplift_req(self):
        """
        Check if Postgres needs a version uplift and /ericsson/postgres
        has enough space for uplift.
        """
        self.log.debug("Beginning of Postgres version uplift "
                       "requirements check")

        pg_service = PostgresService()
        if not pg_service.is_contactable():
            self._print_error("Failure. Unable to contact Postgres service.")
            sys.exit(1)

        if not pg_service.need_uplift():
            self.log.debug("PostgreSQL server version {0} and is up-to-date."
                           .format(pg_service.version))
            return

        self.log.debug("PostgreSQL server version {0}. Version uplift "
                       "is required.".format(pg_service.version))

        if not pg_service.can_uplift():
            self._print_error("Not enough space on {0} filesystem to run "
                              "Postgres version uplift. "
                              "Need at least 50%% free, got {1}%% occupied."
                              .format(pg_service.pg_mount,
                                      pg_service.perc_space_used))
            sys.exit(1)
        self.log.debug("{0} filesystem has enough space to uplift Postgres "
                       "to newer version.".format(pg_service.pg_mount))

    @staticmethod
    def _get_stage_data(action):
        """
        Get the list of uplift stages
        :param action: action name for which stage data will be returned
        :type action: string
        :return: stage data
        :rtype: list of dicts
        """

        # "Updates to the order in this list may also result in the necessity
        # to update dictionary 'stage_checker_map' in
        # _upgrd_pre_chks_and_hlth_chks ()"
        if action == Rh7EnmUpgrade.ACTION_CHOICES[4]:
            return [
                    {'idx': '01',
                     'label': 'mco-conn-setup',
                     'hndlr': '_restore_mco_conn'},
                    {'idx': '02',
                     'label': 'import-to-state-enm',
                     'hndlr': '_import_to_state_enm'},
                    {'idx': '03',
                     'label': 'create-to-state-dd',
                     'hndlr': '_create_to_state_dd'},
                    {'idx': '04',
                     'label': 'create-to-state-dd-segments',
                     'hndlr': '_create_to_state_dd_sgmnts'},
                    {'idx': '05',
                     'label': 'load-segments-for-ms-redeploy',
                     'hndlr': '_load_sgmnts_ms_redeploy'},
                    {'idx': '06',
                     'label': 'redeploy-ms',
                     'hndlr': '_redeploy_ms'},
                    {'idx': '07',
                     'label': 'post-process-restored-data',
                     'hndlr': '_post_process_restored_data'},
                    {'idx': '08',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '09',
                     'label': 'infra-plan',
                     'hndlr': '_do_infra_plan'},
                    {'idx': '10',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '11',
                     'label': 'take-snapshots',
                     'hndlr': '_take_snaps'},
                    {'idx': '12',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '13',
                     'label': 'infoscale-plan',
                     'hndlr': '_do_infoscale_plan'},
                    {'idx': '14',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '15',
                     'label': 'pre-nodes-push-artifacts',
                     'hndlr': '_pre_nodes_push_artifacts'},
                    {'idx': '16',
                     'label': 'pre-nodes-redeployment-plan',
                     'hndlr': '_pre_redeploy_nodes'},
                    {'idx': '17',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '18',
                     'label': 'load-to-state-model',
                     'hndlr': '_load_to_state_model'},
                    {'idx': '19',
                     'label': 'rolling-nodes-redeploy',
                     'hndlr': '_redeploy_nodes'},
                    {'idx': '20',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '21',
                     'label': 'post-nodes-redeployment-plan',
                     'hndlr': '_post_redeploy_nodes'},
                    {'idx': '22',
                     'label': 'upgrade-prechecks-and-health-checks',
                     'hndlr': '_upgrd_pre_chks_and_hlth_chks'},
                    {'idx': '23',
                     'label': 'post-upgrade-steps',
                     'hndlr': '_post_upgrd'}
                   ]
        elif action == Rh7EnmUpgrade.ACTION_CHOICES[6]:
            return [
                    {'idx': '101',
                     'label': 'assert-uplift-done',
                     'hndlr': '_assert_uplift_p1_done'},
                    {'idx': '102',
                     'label': 'assert-password-age',
                     'hndlr': '_assert_passwd_age'},
                    {'idx': '103',
                     'label': 'unset-pam-config',
                     'hndlr': '_unset_pam_config'},
                    {'idx': '104',
                     'label': 'assert-unique-sfha-cluster',
                     'hndlr': '_assert_uniq_cluster'},
                    {'idx': '105',
                     'label': 'upgrade-vx-version',
                     'hndlr': '_upgrd_vx_ver'},
                    {'idx': '106',
                     'label': 'enable-selinux',
                     'hndlr': '_enable_selinux'},
                    {'idx': '107',
                     'label': 'reboot-sfha-nodes',
                     'hndlr': '_reboot_nodes'},
                    {'idx': '108',
                     'label': 'switch-db-groups',
                     'hndlr': '_switch_db_grps_stage'},
                    {'idx': '109',
                     'label': 'create-crons',
                     'hndlr': '_create_crons'},
                    {'idx': '110',
                     'label': 'perform-completion-healthchecks',
                     'hndlr': '_perform_cmpltn_hlthchcks'}
                   ]

    def _do_rh7_uplift(self):
        """
        Action handler to perform the RH7.9 uplift
        """
        self._assert_rhel_version('7.9')

        # Ensure the script is being run as 'root'
        if os.geteuid() != 0:
            self._print_error("This script must be run as the root user")
            sys.exit(1)

        self._run_action_stages(1, 'Upgrade')
        # Do NOT modify the Uplift success message!. It is used by EDP.
        self._print_success('RH7 uplift completed successfully')

    def _run_action_stages(self, first_idx, desc):
        """
        Run the stages for an action
        :param first_idx: expected first index for this action
        :type first_idx: int
        :param desc: action description
        :type desc: string
        :return: None
        """

        stage_data = Rh7EnmUpgrade._get_stage_data(self.processed_args.action)
        start_stage = self._get_start_idx(stage_data)

        if first_idx == start_stage:
            self.execute_ddp_log('{0} has been started'.format(desc))
            self._update_cmd_arg_log()

        for stage in sorted(stage_data, key=lambda x: x['idx']):

            if int(stage['idx']) >= start_stage:
                self.log.debug('Will run stage {0} {1}'.format(stage['idx'],
                                                               stage['label']))
                hndlr = getattr(self, stage['hndlr'], None)
                if not hndlr:
                    self.log.info('Stage {0} missing!'.format(stage['idx']))
                    sys.exit(1)
                else:
                    self.current_stage = stage
                    hndlr()

        self.current_stage = None

    def _read_stg_from_file(self, filepath):
        """
        Read the stage number from the file
        :return: Stage index
        :rtype: string
        """
        content = ''
        if filepath and os.path.exists(filepath):
            content = self._read_file(filepath, log_contents=True)
        return content

    def _read_trckr_stg_idx(self):
        """
        Read the tracker file last completed stage
        :return: Last successful stage index
        :rtype: string
        """
        return self._read_stg_from_file(self.tracker)

    def _read_dsrptr_stg_idx(self):
        """
        Read the disruptor file exit stage
        :return: stage number at which to exit
        :rtype: string
        """
        return self._read_stg_from_file(self.disruptor)

    def _get_start_idx(self, stage_data):
        """
        Determine the correct stage-data index at which to commence.
        :param stage_data: defined uplift stages
        :type stage_data: list of dicts
        :return: stage start index
        :rtype: int
        """

        def _get_idx_by_label(sdata, label):
            """
            Get stage data index by stage label
            :param sdata: stage data
            :type sdata: list of dicts
            :param label: stage label
            :type label: string
            :return: stage index
            :rtype: int
            """
            for stage in sdata:
                if label == stage['label']:
                    return int(stage['idx'])
            return 0

        def _get_label_by_idx(sdata, idx):
            """
            Get stage data label by stage index
            :param sdata: stage data
            :type sdata: list of dicts
            :param idx: stage index
            :type index: int
            :return: stage label
            :rtype: string
            """
            for stage in sdata:
                if idx == int(stage['idx']):
                    return stage['label']
            return 0

        last_stage = 0
        try:
            last_stage = int(self._read_trckr_stg_idx())
        except ValueError as _:
            pass

        if last_stage:
            start_idx = last_stage + 1
        else:
            start_idx = int(stage_data[0]['idx'])

        if getattr(self.processed_args, Rh7EnmUpgrade.PARAM_HYBRID, False):
            label = 'take-snapshots'
            start_idx = _get_idx_by_label(stage_data, label)
            if start_idx and (last_stage + 1) != start_idx:
                msg = ('{0} parameter used but last stage '
                       'run was not {1}').format(Rh7EnmUpgrade.PARAM_HYBRID,
                                                 label)
                self._print_error(msg)
                sys.exit(1)

        elif self._get_resume_param():
            label = _get_label_by_idx(stage_data, start_idx)
            if label and label not in ['infra-plan', 'redeploy-ms',
                             'rolling-nodes-redeploy']:

                start_idx = _get_idx_by_label(stage_data,
                                       'rolling-nodes-redeploy')

        if start_idx > int(stage_data[-1]['idx']):
            msg = ('There was a previous successful RHEL 7.9 uplift. ' +
                   'Nothing to do!')
            self._print_error(msg)
            sys.exit(1)

        return start_idx

    def _validate_deployment(self):
        """
        Action handler to validate deployment before uplift
        """
        self._assert_rhel_version('6.10')

        # Call pre Postgres uplift requirements checks
        self._chk_postgres_uplift_req()

        self._print_success('Deployment validated for uplift')

    def _perform_checks(self):
        """
        Action handler to perform the Upgrade prechecks and Health checks
        """
        (upc_data, hc_data) = Rh7EnmUpgrade._get_chks_data()

        self._do_upgrd_prechks(upc_data, sum(upc_data.keys()))

        # Set flag to skip NAS in health check 0x10: 'node_fs'
        HealthCheck.NAS_RUN_FS_USAGE_CHECK = False

        # Skip NAS health check 0x2: 'nas'
        self._do_health_chks(hc_data, sum(hc_data.keys()) - 0x2)

        msg = ('Upgrade prechecks and Health checks passed ' +
               'for action {0}').format(Rh7EnmUpgrade.ACTION_CHOICES[5])
        self._print_success(msg)

    @staticmethod
    def _gen_ms_rpc_cmd(action, *args):
        """
        Generate MS only ENMInst RPC command
        :param action: enminst agent action name
        :type action: string
        :param args: varying additional arguments
        :type args: iterable of strings
        :return: complete MCO RPC command
        :rtype: string
        """
        return ('mco rpc -W puppet_master=false ' +
                'enminst {0} '.format(action) +
                ' ' .join(args))

    def _assert_passwd_age(self):
        """
        Assert users litp-admin and root have non-expired passwords
        on all peer nodes
        :return: None
        """
        self._print_stage_start()
        for usr in ('litp-admin', 'root'):
            cmd = Rh7EnmUpgrade._gen_ms_rpc_cmd('is_user_password_expired',
                                                'user={0}'.format(usr))

            msg = None
            _, results = self._run_rpc_mco(cmd)
            if any([result.get('errors', False)
                    for result in results.values()]):
                msg = ('Errors getting password age for User {0}, {1}'
                       .format(usr, results))
            elif any(['True' == u"{0}".format(
                                      result.get('data').get('out', None))
                    for result in results.values()]):
                msg = 'Password is expired for User {0}'.format(usr)

            if msg:
                self._print_error(msg)
                sys.exit(1)

        msg = 'Password ages verified'
        self._print_stage_success(msg)

    def _unset_pam_config(self):
        """
        Unset PAM config. from PXE R-plan (re)install
        :return: None
        """

        self._print_stage_start()
        cmd = Rh7EnmUpgrade._gen_ms_rpc_cmd('restore_pam_settings')

        _, results = self._run_rpc_mco(cmd)
        if any([result.get('errors', False) for result in results.values()]):
            msg = 'Failed to unset PAM config: {0}'.format(results)
            self._print_error(msg)
            sys.exit(1)

        msg = 'PAM config. restored'
        self._print_stage_success(msg)

    def _remove_trkr(self):
        """
        Remove tracker file
        :return: None
        """
        self._remove_file(self.tracker)

    def _cmplt_sfha_uplift(self):
        """
        Action handler to complete the uplift of SFHA/DB nodes.
        (ie upgrade VX DG and FS DL versions, enable selinux, reboot nodes)
        """

        self._assert_rhel_version('7.9')

        self._run_action_stages(-1, 'Complete SFHA uplift')
        msg = 'SFHA nodes uplift completed successfully'
        self._print_success(msg)
        self._remove_trkr()

    # ---- Stage handlers start ----

    def _perform_cmpltn_hlthchcks(self):
        """
        Perform complete-sfha-uplift action healthchecks.
        :return: None
        """

        self._print_stage_start()
        (_, hc_data) = Rh7EnmUpgrade._get_chks_data()
        stage_hcs = sum(hc_data.keys()) - 0x4  # storagepool HC
        self._do_health_chks(hc_data, stage_hcs)

        msg = ('Uplift completion Health checks passed '
               'for action {0}').format(Rh7EnmUpgrade.ACTION_CHOICES[6])
        self._print_stage_success(msg)

    def _create_crons(self):
        """
        Create Cron entries
        :return: None
        """

        self._print_stage_start()
        msg = 'Creating Cron entries for: '
        msg += ', '.join(['LITP backup',
                          'Cleanup Java cores',
                          'SAN fault checker',
                          'NAS audit error checker'])
        self._print_message(msg)

        litp_backup_state_cron(os.path.join(Rh7EnmUpgrade.CRON_DIR,
                                            'litp_state_backup'),
                               os.path.join(os.sep, 'ericsson', 'tor',
                                        'data', 'enmbur', 'lmsdata' + os.sep))
        cleanup_java_core_dumps_cron(os.path.join(os.sep, 'etc',
                                      'cron.daily', 'cleanup_java_core_dumps'))
        create_san_fault_check_cron(os.path.join(Rh7EnmUpgrade.CRON_DIR,
                                                 'san_fault_checker'))
        create_nasaudit_errorcheck_cron(os.path.join(Rh7EnmUpgrade.CRON_DIR,
                                                     'nasaudit_error_check'))
        msg = 'Created crons'
        self._print_stage_success(msg)

    def _assert_uplift_p1_done(self):
        """
        Assert that the first (main) part of the uplift completed
        :return: None
        """

        self._print_stage_start()
        uplift_action = Rh7EnmUpgrade.ACTION_CHOICES[4]
        final_stage = Rh7EnmUpgrade._get_stage_data(uplift_action)[-1]['idx']
        cmpltd_stage = self._read_trckr_stg_idx()
        if not cmpltd_stage:
            cmpltd_stage = '<not available>'

        try:
            assert final_stage == cmpltd_stage
        except AssertionError:
            msg = ('Uplift did not previously complete successfully. '
                   'Stage {0} reached only, stage {1} (End) '
                   'must be completed.'.format(cmpltd_stage, final_stage))
            self._print_error(msg)
            sys.exit(1)

        msg = 'Uplift part1 verified'
        self._print_stage_success(msg)

    def _assert_uniq_cluster(self):
        """
        Ensure only one cluster present
        :return: None
        """

        self._print_stage_start()
        if not self.sfha_nodes:
            self.sfha_nodes = self._get_sfha_nodes()

        clusters = set(ndata['cluster']
                       for ndata in self.sfha_nodes.values())

        count_clusters = len(clusters)
        try:
            assert 1 == count_clusters
        except AssertionError:
            msg = 'One cluster expected, {0} found'.format(count_clusters)
            self._print_error(msg)
            sys.exit(1)

        msg = 'Single unique SFHA cluster verified'
        self._print_stage_success(msg)

    def _enable_selinux(self):
        """
        Enable SElinux on SFHA nodes
        :return: None
        """

        self._print_stage_start()
        if not self.sfha_nodes:
            self.sfha_nodes = self._get_sfha_nodes()

        self._set_selinux_on_nodes(self.sfha_nodes.keys())
        msg = 'Enabled SElinux on SFHA nodes'
        self._print_stage_success(msg)

    def _reboot_nodes(self):
        """
        Reboot SFHA nodes
        :return: None
        """

        self._print_stage_start()
        if not self.sfha_nodes:
            self.sfha_nodes = self._get_sfha_nodes()

        self._ordered_reboot_nodes(self.sfha_nodes.values()[0]['cluster'],
                                   self.sfha_nodes)

        msg = 'Rebooted SFHA nodes'
        self._print_stage_success(msg)

    def _set_selinux_on_nodes(self, hostnames, mode='enforcing'):
        """
        Run the MCO agent::action set_selinux on the nodes
        :param hostnames: node hostnames
        :type hostnames: list of strings
        :param mode: selinux mode (disabled, enforcing or permissive)
        :type mode: string
        :return: None
        """
        cmd = 'mco rpc {0} enminst set_selinux mode={1}'.format(
                 ' '.join(['-I {0}'.format(host) for host in hostnames]),
                  mode)

        _, results = self._run_rpc_mco(cmd)
        if any([result.get('errors', False) for result in results.values()]):
            msg = ('Failed to set selinux on nodes: {0}'
                   .format(results))
            self._print_error(msg)
            sys.exit(1)

    def _ordered_reboot_nodes(self, cluster_vpath, node_data):
        """
        Reboot nodes in order
        :param cluster_vpath: Vpath of cluster to reboot
        :type cluster_vpath: string
        :param node_data: dict of node hostname mapped to node data
        :type node_data: dict
        :return: None
        """

        if not self.plugin_api_context:
            self._init_plugin_api_context()

        cluster_qitem = self.plugin_api_context.query_by_vpath(cluster_vpath)
        reboot_order = cluster_qitem.node_upgrade_ordering

        if not reboot_order:
            reboot_order = sorted([str(node_info['node-id'])
                                   for node_info in node_data.values()])

        self.log.debug('Reboot order: {0}'.format(reboot_order))

        for node_id in reboot_order:
            for (hostname, data) in node_data.iteritems():
                if node_id == data['node-id']:
                    cmd = 'litp create_reboot_plan -p {0}'.format(data['node'])
                    msg = 'Rebooting node {0} {1}, using: {2}'.format(node_id,
                                                                 hostname, cmd)
                    return_code, _ = self._run_command(cmd)
                    self._assert_return_code(return_code, msg)
                    desc = hostname + ' Reboot'
                    self._run_litp_plan(desc)
                    self._monitor_litp_plan(desc)
                    break

    def _upgrd_vx_ver_on_sfha_nodes(self, sfha_nodes):
        """
        Run the VX Upgrade MCO agent action on the SFHA nodes
        :param sfha_nodes: SFHA node hostnames
        :type sfha_nodes: list of strings
        :return: None
        """
        vx_dg_target_ver = '240'  # DiskGroup v240
        vx_dl_target_ver = '13'   # FS Disk Layout v13
        cmd = ('mco rpc {0} enminst upgrade_dg_versions ' +
               'dg_target_ver={1} dl_target_ver={2}').format(
                    ' '.join(['-I {0}'.format(node) for node in sfha_nodes]),
                    vx_dg_target_ver, vx_dl_target_ver)

        _, results = self._run_rpc_mco(cmd)
        if any([result['errors'] for result in results.values()]):
            msg = ('Failed to upgrade Veritas DG/DL versions: {0}'
                   .format(results))
            self._print_error(msg)
            sys.exit(1)

    def _upgrd_vx_ver(self):
        """
        Upgrade VX DiskGroup versions
        :return: None
        """

        self._print_stage_start()
        if not self.sfha_nodes:
            self.sfha_nodes = self._get_sfha_nodes()

        self._upgrd_vx_ver_on_sfha_nodes(self.sfha_nodes.keys())

        msg = 'Upgraded VX DG and FS DL versions on SFHA nodes'
        self._print_stage_success(msg)

    def _print_stage_start(self):
        """
        Print a Stage start message
        :return: None
        """
        if not self.current_stage:
            msg = 'Commencing UNKNOWN stage, self.current_stage not set'
            self._print_warning(msg)
        else:
            now = datetime.datetime.now()
            msg = ('----- Commencing stage {0} {1} at {2} -----'
                   .format(self.current_stage['idx'],
                           self.current_stage['label'], now))
            self._print_message(msg)

    def _print_stage_success(self, text=''):
        """
        Print Stage Success outcome
        :param text: additional text to log
        :type text: string
        :return: None
        """
        self._print_stage_end('SUCCESS', text)

        if self.current_stage:
            if self.tracker:
                self._write_to_file(self.tracker,
                                    self.current_stage['idx'])

            exit_stage = self._read_dsrptr_stg_idx()

            if exit_stage == self.current_stage['idx']:
                self._remove_file(self.disruptor)
                msg = ('Uplift disrupted at stage {0}, exiting. '
                       'Not a real uplift failure').format(exit_stage)
                self._print_stage_failure(msg)
                sys.exit(1)

    def _print_stage_failure(self, text=''):
        """
        Print Stage Failure outcome
        :param text: additional text to log
        :type text: string
        :return: None
        """
        self._print_stage_end('FAILURE', text)

    def _print_stage_end(self, outcome, text=''):
        """
        Print Stage End outcome
        :param outcome: SUCCESS or FAILURE
        :type outcome: string
        :param text: additional text to log
        :type text: string
        :return: None
        """
        if not self.current_stage:
            msg = 'Finished UNKNOWN stage, self.current_stage not set'
            self._print_warning(msg)
            msg = text
        else:
            now = datetime.datetime.now()
            msg = ('Finished stage {0} {1} at {2}. {3}'
                   .format(self.current_stage['idx'],
                           self.current_stage['label'], now, text))

        if 'SUCCESS' == outcome:
            self._print_success(msg)
        elif 'FAILURE' == outcome:
            self._print_error(msg)

    def _mount_to_state_litp_iso(self, mnt_dir):
        """
        Mount the LITP To-state ISO
        :param mnt_dir: target LITP ISO mount directory
        :type mnt_dir: string
        :return: None
        """
        litp_iso = getattr(self.processed_args,
                           Rh7EnmUpgrade.PARAM_LITP_TO_STATE, False)
        self.log.debug('Will mount LITP ISO {0} to {1}'.format(litp_iso,
                                                               mnt_dir))
        self._mount_iso(litp_iso, mnt_dir)

    def _mount_to_state_enm_iso(self, mnt_dir):
        """
        Mount the ENM To-state ISO
        :param mnt_dir: target ENM ISO mount directory
        :type mnt_dir: string
        :return: None
        """
        enm_iso = getattr(self.processed_args,
                          Rh7EnmUpgrade.PARAM_ENM_TO_STATE, False)
        self.log.debug('Will mount ENM ISO {0} to {1}'.format(enm_iso,
                                                              mnt_dir))
        self._mount_iso(enm_iso, mnt_dir)

    def _mount_iso(self, iso_path, mnt_dir):
        """
        Mount an ISO
        :param iso_path: Path to ISO file
        :type iso_path: string
        :param mnt_dir: Mount directory
        :type mnt_dir: string
        :return: None
        """
        if not os.path.exists(mnt_dir):
            os.makedirs(mnt_dir)
            self.log.debug('Created mount directory {0}'.format(mnt_dir))

        if not os.path.ismount(mnt_dir):
            cmd = 'mount -o loop {0} {1}'.format(iso_path, mnt_dir)
            return_code, _ = self._run_command(cmd)
            self._assert_return_code(return_code, cmd)

    @staticmethod
    def _is_present_infoscale_el6_pkgs(mnt_dir):
        """
        Check if VRTS RH6 packages are available
        :param mnt_dir: LITP ISO mount directory
        :type mnt_dir: string
        :return: True if VRTS packages found, else False
        :rtype: bool
        """
        return (True
                if glob.glob(Rh7EnmUpgrade._gen_vrts_pkgs_pattern(mnt_dir))
                else False)

    @staticmethod
    def _gen_vrts_pkgs_pattern(mnt_dir):
        """
        Generate the VRTS packages pattern
        :param mnt_dir: LITP ISO mount directory
        :type mnt_dir: string
        :return: VRTS packages pattern
        :rtype: string
        """
        return os.path.join(mnt_dir, 'litp', '3pp_el6', 'VRTS*.rpm')

    def _fetch_infoscale_el6_pkgs(self, mnt_dir, dst_dir):
        """
        Copy the RH6 Infoscale RPMs
        :param mnt_dir: LITP ISO mount directory
        :type mnt_dir: string
        :param dst_dir: path to folder where RH6 packages should be copied to
        :type dst_dir: string
        :return: None
        """
        pattern = Rh7EnmUpgrade._gen_vrts_pkgs_pattern(mnt_dir)

        self.log.debug('Copying RHEL6 Infoscale packages '
                       'from {0} to {1}'.format(mnt_dir, dst_dir))

        self._cp_files(pattern, dst_dir)

    def _cp_files(self, src, dst_dir):
        """
        Copy files from A to B
        :param src: Source of files
        :type src: string
        :param dst_dir: destination directory for file
        :type dst_dir: string
        :return: None
        """

        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
            self.log.debug('Created target folder {0}'.format(dst_dir))

        cmd = 'cp -r {0} {1}'.format(src, dst_dir)
        return_code, _ = self._run_command(cmd)
        self._assert_return_code(return_code, cmd)

    def _remove_el6_pkgs(self, dst_dir):
        """
        Remove the RH6 Infoscale RPMs
        :param dst_dir: Directory path with packages
        :type dst_dir: string
        :return: None
        """
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
            self.log.debug('Removed Infoscale RHEL6 '
                           'packages folder {0}'.format(dst_dir))

    def _umount_iso(self, desc, mnt_dir, rm_mnt_dir=True):
        """
        Unmount an ISO
        :param desc: Description of mounted ISO
        :type desc: string
        :param mnt_dir: ISO mount directory
        :type mnt_dir: string
        :param rm_mnt_dir: remove mount directory
        :type rm_mnt_dir: bool
        :return: None
        """
        self.log.debug('Will unmount {0} ISO from {1}'.format(desc, mnt_dir))

        if os.path.exists(mnt_dir):
            return_code = 0
            if os.path.ismount(mnt_dir):
                cmd = 'umount {0}'.format(mnt_dir)
                return_code, _ = self._run_command(cmd)
                self._assert_return_code(return_code, cmd)

            if rm_mnt_dir and 0 == return_code:
                try:
                    os.rmdir(mnt_dir)
                except OSError as os_err:
                    msg = ('Failed to delete {0} mount directory {1}: {2} {3}'
                           .format(desc, mnt_dir,
                                   os_err.errno, os_err.strerror))
                    self.log.debug(msg)

    def _get_node_upgrd_vpaths(self):
        """
        Get the vpaths for 'node' upgrade items
        :return: list of node upgrade vpaths
        :rtype: list of strings
        """
        if not self.deps_clusters_nodes:
            self._init_node_data()

        return [os.path.join(os.sep, 'deployments', d,
                             'clusters', c, 'nodes', n, 'upgrade')
                for d in self.deps_clusters_nodes.keys()
                for c in self.deps_clusters_nodes[d].keys()
                for n in self.deps_clusters_nodes[d][c]]

    def _set_dplymnts_upgrd(self):
        """
        Set Upgrade on the deployments
        :return: None
        """
        if not self.deps_clusters_nodes:
            self._init_node_data()

        cmds = ['litp upgrade -p {0}'.format(os.path.join(os.sep,
                                                          'deployments', d))
                for d in self.deps_clusters_nodes.keys()]

        self._run_command_set(cmds,
                              'Upgrade deployments')

    def _set_upgrd_props(self, prop_names):
        """
        Set the Upgrade Item properties
        :param prop_names: property names
        :type prop_names: list of strings
        :return: None
        """
        prop_val = 'true'

        self.log.debug("Setting upgrade properties '{0} to {1}".format(
                                                        prop_names, prop_val))

        self._set_dplymnts_upgrd()

        cmds = ['litp update -p {0} -o {1}={2}'.format(vpath,
                                                       prop_name, prop_val)
                for vpath in self._get_node_upgrd_vpaths()
                for prop_name in prop_names]
        self._run_command_set(cmds,
                              'Set {0} to {1}'.format(prop_names, prop_val))

    def _unset_upgrd_props(self, prop_names):
        """
        Unset the Upgrade Item properties
        :param prop_names: property names
        :type prop_names: list of strings
        :return: None
        """
        self.log.debug("Unsetting upgrade properties '{0}'".format(prop_names))

        cmds = ['litp update -p {0} -d {1}'.format(vpath, prop_name)
                for vpath in self._get_node_upgrd_vpaths()
                for prop_name in prop_names]
        self._run_command_set(cmds, 'Unset {0}'.format(prop_names))

    def _mng_plugins(self, action, pkgs):
        """
        Manage troublesome Plugins
        :param action: yum action to perform (install or remove)
        :type action: string
        :param pkgs: the packages to perform the action on.
        :type : string array
        :return: None
        """
        pkgs_str = ' '.join(pkgs)

        self.log.debug('Will {0} packages: {1}'.format(action, pkgs_str))

        cmd = 'yum {0} -y {1}'.format(action, pkgs_str)
        return_code, _ = self._run_command(cmd)
        self._assert_return_code(return_code, cmd)

    def _import_to_state_enm(self):
        """
        Stage: import the To-state ENM ISO
        :return: None
        """
        self._print_stage_start()

        self._mount_to_state_enm_iso(self.to_state_enm_iso_mnt_dir)

        ver_file = os.path.join(self.to_state_enm_iso_mnt_dir, '.version')
        if os.path.exists(ver_file):
            enm_ver = self._read_file(ver_file).strip('\r\n')
        else:
            enm_ver = '<unknown>'

        self._umount_iso('ENM', self.to_state_enm_iso_mnt_dir)

        enm_iso = getattr(self.processed_args,
                          Rh7EnmUpgrade.PARAM_ENM_TO_STATE, False)

        contents = import_iso.main_flow(enm_iso,
                                        verbose=self._get_verbose_param(),
                                        iso_label='to-state-ENM')

        hkeeper = EnmLmsHouseKeeping()
        hkeeper.housekeep_images(contents[import_iso.ISO_CONTENTS_IMAGES])
        hkeeper.housekeep_yum(contents[import_iso.ISO_CONTENTS_YUM])

        msg = 'Imported ENM ISO, version {0}'.format(enm_ver)
        self._print_stage_success(msg)

    def _take_snaps(self):
        """
        Stage: take snapshots
        :return: None
        """

        def _do_snap_action(desc, action, verbose):
            """
            Do snapshot action, with exception handling
            :param desc: Action description
            :type desc: string
            :param action: Snapshot action
            :type action: string
            :param verbose: verbose logging
            :type verbose: bool
            :return: None
            """
            try:
                manage_snapshots(action=action, verbose=verbose)
            except BaseException as err:
                msg = '{0} snapshots failed: {1}'.format(desc, str(err))
                self._print_error(msg)
                raise

        self._print_stage_start()
        verbose = self._get_verbose_param()

        if getattr(self.processed_args, Rh7EnmUpgrade.PARAM_HYBRID, False):
            _do_snap_action('Removing', 'remove_snapshot', verbose)

        self.create_lockfile()

        _do_snap_action('Creating', 'create_snapshot', verbose)
        create_snapshots_indicator_file()

        self._print_stage_success()

    def _pre_rollover_mng_plugins(self, action):
        """
        Manage troublesome Plugins during pre rollover Plan
        :param action: yum action to perform (install or remove)
        :type action: string
        :return: None
        """

        pkgs = ['ERIClitppackage_CXP9030581',
                'ERIClitpdhcpservice_CXP9031640',
                'ERIClitpnetwork_CXP9030513',
                'ERIClitphosts_CXP9030589']

        self._mng_plugins(action, pkgs)

        plugins = os.path.join(Rh7EnmUpgrade.HTML_DIR, 'litp_plugins', '*.rpm')
        enm_pkgs = [os.path.splitext(os.path.basename(rpm))[0].split('-')[0]
                    for rpm in glob.glob(plugins)
                    if 'api' not in rpm and 'CXP9030788' not in rpm]
        unique_enm_pkgs = list(set(enm_pkgs))
        if not unique_enm_pkgs:
            self._print_stage_failure('No ENM plugins to be removed')
        else:
            self._mng_plugins(action, unique_enm_pkgs)

    def _do_infoscale_plan(self):
        """
        Stage: run the Infoscale RH6 uplift Plan
        :return: None
        """
        self._print_stage_start()

        mnt_dir = os.path.join(os.sep, 'media', 'LITP')
        dst_dir = os.path.join(Rh7EnmUpgrade.HTML_DIR, '3pp_el6')

        self._mount_to_state_litp_iso(mnt_dir)

        if not Rh7EnmUpgrade._is_present_infoscale_el6_pkgs(mnt_dir):
            msg = 'VRTS packages not found at {0}'.format(mnt_dir)
            self._print_stage_failure(msg)
            sys.exit(1)

        self._fetch_infoscale_el6_pkgs(mnt_dir, dst_dir)

        pkgs = ['ERIClitpyum_CXP9030585',
                'ERIClitpnetwork_CXP9030513',
                'ERIClitpopendj_CXP9031976']

        prop_name = 'ha_manager_only'
        self._set_upgrd_props([prop_name])
        self._mng_plugins('remove', pkgs)
        desc = 'Infoscale'
        self._create_litp_plan(desc)
        self._run_litp_plan(desc)
        self._monitor_litp_plan(desc)
        self._unset_upgrd_props([prop_name])
        self._mng_plugins('install', pkgs)
        self._umount_iso('LITP', mnt_dir)
        self._remove_el6_pkgs(dst_dir)

        msg = 'RH6 Infoscale deployed to nodes'
        self._print_stage_success(msg)

    @staticmethod
    def _get_xml_software_services(xml_doc):
        """
        Get software service details from XML doc
        :param xml_doc: path of XML doc to be searched
        :type xml_doc: string
        :return: dictionary of services, key is vpath and value is properties
        :rtype: dictionary
        """
        service_property_types = ['cleanup_command', 'start_command',
                                  'status_command', 'stop_command']

        def get_vpath(element):
            """
            Use the parent_map to get the elements vpath
            :param element: element to get vpath of
            :type element: lxml.etree._Element
            :return: vpath of element
            :rtype: string
            """
            elements = []
            while element != root:
                elements.append(element.attrib['id'])
                element = parent_map[element]
            elements.append('')
            return '/'.join(elements[::-1])

        tree = etree.parse(xml_doc)
        root = tree.getroot()
        parent_map = dict((child, parent) for parent in tree.iter()
                          for child in parent)
        services_collection = next(item for item in root.iter()
                                   if isinstance(item.tag, basestring)
                                   and 'software-services' in item.tag)
        services = {}
        for service in services_collection.getchildren():
            properties = dict((prop.tag, prop.text)
                              for prop in service.getchildren()
                              if prop.tag in service_property_types)
            services[get_vpath(service)] = properties
        return services

    @staticmethod
    def _item_collection_compare(from_items, to_items):
        """
        Compare from and to collection of items
        :param from_items: from state items
        :type from_items: dictionary, key is item vpath and value is item
                                      properties
        :param to_items: to state items
        :type to_items: dictionary, key is item vpath and value is item
                                    properties
        :return: sets of added, removed and modified item vpaths
        :rtype: tuple of sets
        """
        from_keys = set(from_items.keys())
        to_keys = set(to_items.keys())
        shared_keys = from_keys.intersection(to_keys)
        removed = from_keys - to_keys
        added = to_keys - from_keys
        modified = set(item for item in shared_keys
                       if from_items[item] != to_items[item])
        return added, removed, modified

    def _update_software_services(self):
        """
        Set modified software services items to Updated and set APD so that
        a task is created in R-1 Plan.
        :return: modified service vpaths
        :rtype: set
        """
        from_dd_services = Rh7EnmUpgrade._get_xml_software_services(
                                                Rh7EnmUpgrade.ENM_PREVIOUS_DD)
        to_dd_services = Rh7EnmUpgrade._get_xml_software_services(
                                                Rh7EnmUpgrade.ENM_DD)
        _, _, modified = Rh7EnmUpgrade._item_collection_compare(
                                                          from_dd_services,
                                                          to_dd_services)
        for service_vpath in modified:
            self._set_model_state(service_vpath, 'Updated', recurse=False)
            self._set_vcs_clustered_service_apd(service_vpath, 'f')
        return modified

    def _pre_nodes_push_artifacts(self):
        """
        Stage: push artifacts required for pre rollover (R-1) Plan.
        :return: None
        """
        self._print_stage_start()
        self._push_scripts()
        self._print_stage_success(
            'Pre-rollover Plan dependencies pushed successfully')

    def _pre_redeploy_nodes(self):
        """
        Stage: do pre rollover (R-1) Plan to do required VCS tasks
        :return: None
        """
        self._print_stage_start()
        properties = ['pre_os_reinstall', 'os_reinstall']
        self._set_upgrd_props(properties)

        migrate_cleanup_cmd()

        # Set modified software services state to Updated
        modified_services = self._update_software_services()

        # Find and update items for R-1 Plan
        cmd_list = pre_rollover_changes(Rh7EnmUpgrade.ENM_DD)
        cmd_list_filtered = []

        for cmd in cmd_list:
            if ' standby=' in cmd and ' active=' in cmd and \
                ' node_list=' not in cmd:
                args = cmd.split('-o')[-1:][0].strip().split(' ')
                if len(args) > 2:
                    cmd_minus_attr = cmd.split('-o')[0] + '-o '
                    for arg in args:
                        if 'standby' not in arg and 'active' not in arg:
                            cmd_minus_attr = cmd_minus_attr + str(arg)
                    cmd_list_filtered.append(cmd_minus_attr)
                else:
                    self.log.debug("Filtering command {0}".format(cmd))
            else:
                cmd_list_filtered.append(cmd)

        self._run_command_set(
            cmd_list_filtered, "LITP create and update commands "
                                        "before pre-rollover Plan")

        # Find delete items/properties for R-1 Plan
        self._create_xml_diff_file(Rh7EnmUpgrade.ENM_PREVIOUS_DD,
                                   Rh7EnmUpgrade.ENM_DD)
        removable_items = self._parse_deploy_diff_output()
        # Filter removable_items by regex to get clustered_services

        regex = r'/deployments/[a-zA-Z0-9\-\._]+/clusters/[a-zA-Z0-9\-\._]+'\
                r'/services/[a-zA-Z0-9\-\._]+$'

        cs_items_to_remove = [item for item in removable_items
                              if re.search(regex, item[0])]
        self._remove_items_from_model(cs_items_to_remove)

        if modified_services or cmd_list_filtered or cs_items_to_remove:
            # Remove plugins so non vcs tasks are not created
            self._pre_rollover_mng_plugins('remove')

            # Create the R-1 Plan with no-lock-tasks and run it
            desc = 'R-1'
            if self._create_litp_plan(desc, nlt=True, dnpe_allowed=True):
                self._run_litp_plan(desc)
                self._monitor_litp_plan(desc)
            else:
                self.log.debug("No pre-rollover Plan needed")
                self.last_plan_do_nothing_plan = True

            # Post R-1 Plan re-install plugins
            self._pre_rollover_mng_plugins('install')

        else:
            self.last_plan_do_nothing_plan = True

        self._unset_upgrd_props(properties)
        self._print_stage_success('Pre-rollover Plan was successful')

    # pylint: disable=R0913
    def _create_litp_plan(self, desc, ilt=False, nlt=False,
                          dnpe_allowed=False):
        """
        Create a LITP Plan
        :param desc: Plan description
        :type desc: string
        :param ilt: Should initial-lock-tasks be enabled
        :type ilt: bool
        :param nlt: Should no-lock-tasks be enabled
        :type nlt: bool
        :dnpe_allowed: DoNothingPlanError allowed
        :type dnpe_allowed: bool
        :return: boolean indicating if a Plan was created or not
        :rtype: bool
        """
        cmd = 'litp create_plan'
        cmd += ' --initial-lock-tasks' if ilt else ''
        cmd += ' --no-lock-tasks' if nlt else ''

        self.log.debug('Creating LITP {0} Plan, using: {1}'.format(desc, cmd))
        return_code, output = self._run_command(cmd,
                                    timeout_secs=Rh7EnmUpgrade.PLAN_TIMEOUT)
        self.log.debug('Create LITP {0} Plan returned: {1}'.format(desc,
                                                                  return_code))

        if (0 != return_code and dnpe_allowed and
                'DoNothingPlanError' in output):
            return False

        self._assert_return_code(return_code, cmd)
        return True

    def _run_litp_plan(self, desc, resume=False):
        """
        Run a LITP Plan
        :param desc: Plan description
        :type desc: string
        :param resume: Should an existing Plan be resumed
        :type resume: bool
        :return: None
        """
        cmd = 'litp run_plan'
        cmd += ' --resume' if resume else ''
        self.log.debug('Running LITP {0} Plan, using: {1}'.format(desc, cmd))
        return_code, _ = self._run_command(cmd)
        self.log.debug('LITP {0} Plan returned: {1}'.format(desc, return_code))
        self._assert_return_code(return_code, cmd)

    def _monitor_litp_plan(self, desc, resume=False):
        """
        Monitor LITP Plan execution
        :param desc: Plan description
        :type desc: string
        :param resume: resume Plan boolean
        :type resume: bool
        :return: None
        """
        if not self.litp:
            self.litp = LitpRestClient()

        self.log.debug('Monitoring LITP {0} Plan (resume={1})'.format(desc,
                                                                      resume))
        try:
            self.litp.monitor_plan('plan', resume_plan=resume)
        except LitpException:
            msg = 'LITP {0} Plan execution failed'.format(desc)
            self._print_error(msg)
            sys.exit(1)

        msg = 'LITP {0} Plan completed successfully'.format(desc)
        self._print_message(msg)

    def _load_to_state_model(self):
        """
        Stage: load To-state LITP model for peer os reinstall Plan
        :return: None
        """
        self._print_stage_start()

        if not self.litp:
            self.litp = LitpRestClient()

        profiles = self.litp.get_all_items_by_type(
            '/deployments', 'reference-to-os-profile', [])
        self._set_model_state('', 'Initial')

        for profile in profiles:
            self.litp.delete_path(profile['path'])

        self._load_model(Rh7EnmUpgrade.ENM_DD)
        self._create_xml_diff_file(Rh7EnmUpgrade.ENM_PREVIOUS_DD,
                                   Rh7EnmUpgrade.ENM_DD)
        self._remove_items_from_model(self._parse_deploy_diff_output())

        msg = 'Successfully loaded the To-state LITP model'
        self._print_stage_success(msg)

    def _update_kickstart_template(self, command):
        """
        Update kickstart.erb to prevent or allow cron job failures due to
        password expiry. Required to keep cron jobs working during uplift.
        :param command: Command to perform on the kickstart.erb file.
        :type action: String
        :return: None
        """
        return_code, _ = self._run_command(command)
        self._assert_return_code(return_code, command)

    def _remove_dupe_es_resources(self):
        """
        Remove duplicate Elasticsearch resources from main.cf
        See TORF-583891
        """
        if not self.sfha_nodes:
            self.sfha_nodes = self._get_sfha_nodes()

        crc32_hashes = {'dg': {'1-app': 'c22c5abd', '2-app': '118e850d'},
                        'mnt': {'1-app': '3c5968b4', '2-app': 'b6a6c449'},
                        'ip': {'1-app': '822195a7', '2-app': '4fd13a77'}}
        remove_app = '1-app'

        sfha_host = self.sfha_nodes.keys()[0]

        cmd_preamble1 = 'mco rpc -I {0} enminst '.format(sfha_host)

        dg_for_removal = 'DG_db_cluster_elasticsearch_clustered_service__{0}'.\
                         format(crc32_hashes['dg'][remove_app])
        display_cmd = cmd_preamble1 + \
                      'hares_display resource=Res_{0}'.format(dg_for_removal)

        _, results = self._run_rpc_mco(display_cmd)

        if any([result['errors'] for result in results.values()]):
            match_string = dg_for_removal + ' does not exist'
            if any([match_string in result['errors']
                   for result in results.values()]):
                msg = ('Duplicate Diskgroup resource Res_{0} NOT found, '
                       'nothing to remove').format(dg_for_removal)
                self._print_message(msg)
                return
            else:
                msg = 'Unexpected error(s), continuing: {0}'.format(results)
                self._print_message(msg)

        cmd_preamble2 = 'mco rpc -I {0} vcs_cmd_api '.format(sfha_host)

        cmd_tmplt1 = cmd_preamble2 + \
                     'hares_unlink parent=Res_{0} child=Res_{1}'
        cmd_tmplt2 = cmd_preamble1 + \
                     'hares_delete_no_offline resource=Res_{0}'

        resdata = [('App_db_cluster_elasticsearch_elasticsearch',
                    'Mnt_db_cluster_elasticsearch_clustered_service_{0}'.
                                      format(crc32_hashes['mnt'][remove_app])),
                   ('Mnt_db_cluster_elasticsearch_clustered_service_{0}'.
                                      format(crc32_hashes['mnt'][remove_app]),
                    dg_for_removal),
                   ('App_db_cluster_elasticsearch_elasticsearch',
                    'IP_db_cluster_elasticsearch_clustered_service__{0}'.
                                      format(crc32_hashes['ip'][remove_app])),
                   ('IP_db_cluster_elasticsearch_clustered_service__{0}'.
                                      format(crc32_hashes['ip'][remove_app]),
                    'NIC_Proxy_db_cluster_elasticsearch_clustered_s_cd8e72bb')]

        cmd1 = cmd_preamble2 + 'haconf haaction=makerw read_only=False'
        cmd2 = cmd_preamble2 + 'haconf haaction=dump read_only=True'

        cmds = [cmd1] + \
               [cmd_tmplt1.format(parent, child)
                for (parent, child) in resdata] + \
               [cmd_tmplt2.format(resdata[idx][1])
                for idx in 2, 0, 1] + \
               [cmd2]

        for cmd in cmds:
            # Fire and forget - no error handling - ignore failures
            rcode, output = self._run_rpc_mco(cmd)
            msg = 'Duplicate ES Res removal: "{0}", RC: {1}, Output: {2}'.\
                  format(cmd, rcode, output)
            self._print_message(msg)

    def _redeploy_nodes(self):
        """
        Stage: create and run the LITP 'rolling-over-node-redeploy' Plan.
        :return: None
        """
        self._print_stage_start()

        flag1 = 'os_reinstall'
        flag2 = 'rh7_uplift_opendj'

        desc = 'R'
        resume = getattr(self.processed_args, Rh7EnmUpgrade.PARAM_RESUME,
                         False)
        if not resume:
            # Set the flags
            self._set_upgrd_props([flag1])
            self._do_consul_action('put', flag2)

            self._update_kickstart_template(
                get_enable_cron_on_expiry_cmd(
                    Rh7EnmUpgrade.RHEL7_SYSTEM_AUTH))

            # Create the 'rolling-over-node-redeploy' Plan with
            # '--initial-lock-tasks' for all nodes
            self._create_litp_plan(desc, ilt=True)

        # Run and monitor the 'rolling-over-node-redeploy' Plan
        self._run_litp_plan(desc, resume=resume)
        self._monitor_litp_plan(desc, resume=resume)

        # Unset the flags
        self._unset_upgrd_props([flag1])
        self._do_consul_action('delete', flag2)

        self._update_kickstart_template(
            cmd_DISABLE_CRON_ON_EXPIRY)
        self._remove_dupe_es_resources()

        msg = 'Successfully redeployed all nodes'
        self._print_stage_success(msg)

    def _post_redeploy_nodes(self):
        """
        Stage: do post rollover (R+1) Plan to clean-up
        the NAS/SFS shares and filesystems
        :return: None
        """
        self._print_stage_start()

        # Find the SFS item types for removal from the LITP model
        self._create_xml_diff_file(Rh7EnmUpgrade.ENM_PREVIOUS_DD,
                                   Rh7EnmUpgrade.ENM_DD)
        items = self._parse_deploy_diff_output(
            types_filter=[ITEM_TYPE_SFS_FILESYSTEM])

        if items:
            self._remove_items_from_model(items)

            # Create the R+1 Plan and run it
            desc = 'R+1'
            if self._create_litp_plan(desc, dnpe_allowed=True):
                self._run_litp_plan(desc)
                self._monitor_litp_plan(desc)
            else:
                self.log.debug("No post-rollover Plan needed")
                self.last_plan_do_nothing_plan = True
        else:
            self.last_plan_do_nothing_plan = True

        self._print_stage_success('Post-rollover stage was successful')

    def _do_consul_action(self, action, consul_param, value=''):
        """
        Perform a consul action.
        :param action: The action used with consul, e.g. 'put'
        :type action: String
        :param consul_param: Consul parameter to set or unset
        e.g. 'rh7_uplift_opendj'
        :type consul_param: String
        :param value: Consul values - not needed atm but may
        be used in future
        :type value: String
        :return: None
        """
        ms_node = self._get_hostname()
        command = "/usr/bin/consul kv {0} -http-addr=" \
                  "http://{1}:8500 {2} {3}" \
            .format(action, ms_node, consul_param, value)
        return_code, _ = self._run_command(command)
        self._assert_return_code(return_code, command)

    def _get_ms_uuid_val(self, extra_data):
        """
        Get the MS disk0 UUID
        :param extra_data: Data dict to be populated with UUID.
        :type extra_data: dict
        :return: None
        """
        self.log.debug('Getting MS disk UUID')
        cmd = ('ls -l /dev/disk/by-id/ | ' +
               'grep -E "wwn-0x.*$(basename $(readlink -f ' +
                     '/dev/disk/by-path/pci-0000:??:??.?-scsi-0:?:0:0))$" | ' +
               'sed -E -e "s/^.* wwn-0x([a-zA-Z0-9]+) .*$/\\1/"')
        return_code, stdout = self._run_command(cmd)
        if 0 == return_code:
            extra_data['uuid_ms_disk0'] = stdout

    def _get_to_state_iso_qcow_names(self, extra_data):
        """
        Get the To-state ISO .qcow2 image names
        :param extra_data: Data dict to be populated with names.
        :type extra_data: dict
        :return: None
        """
        self._mount_to_state_enm_iso(self.to_state_enm_iso_mnt_dir)

        self.log.debug('Getting qcow image names')
        for (ekey, cxp) in \
               (('ERICrhel79lsbimage', 'ERICrhel79lsbimage_CXP9041915'),
                ('ERICrhel79jbossimage', 'ERICrhel79jbossimage_CXP9041916'),
                ('ERICsles15image', 'ERICsles15image_CXP9041763')):
            cmd = 'find {0}/images/ENM/ -type f -name "{1}*.qcow2"'\
                    .format(self.to_state_enm_iso_mnt_dir, cxp)
            return_code, stdout = self._run_command(cmd)
            if 0 == return_code:
                extra_data[ekey] = os.path.basename(stdout)

        self._umount_iso('ENM', self.to_state_enm_iso_mnt_dir)

    def _write_working_file(self, content):
        """
        Write content to enminst_working.cfg
        :param content: text content for file
        :type content: string
        :return: None
        """
        filename = os.path.join(Rh7EnmUpgrade.ENM_RT_DIR,
                                'enminst_working.cfg')
        self.log.debug('Will populate {0}'.format(filename))
        self._write_to_file(filename, content, user='root', group='root')

    def _create_to_state_dd(self):
        """
        Stage: create To-state Deployment Description XML
        :return: None
        """

        self._print_stage_start()

        the_to_state_sed = getattr(self.processed_args,
                                   Rh7EnmUpgrade.PARAM_SED)
        the_to_state_dd_tmplt = getattr(self.processed_args,
                                        Rh7EnmUpgrade.PARAM_MODEL)

        os.environ['ENMINST_RUNTIME'] = Rh7EnmUpgrade.ENM_RT_DIR

        vm_priv_key_file = os.path.join(os.sep, 'root', '.ssh',
                                        'vm_private_key.pub')

        if not os.path.exists(vm_priv_key_file):
            msg = 'File not found: {0}'.format(vm_priv_key_file)
            self._print_error(msg)
            sys.exit(1)

        verbose = self._get_verbose_param()

        subr = Substituter(verbose=verbose)
        self.the_to_state_dd = subr.output_xml

        extra_data = {'vm_ssh_key': 'file://{0}'.format(vm_priv_key_file)}
        self._get_to_state_iso_qcow_names(extra_data)
        self._get_ms_uuid_val(extra_data)

        tmp_file1 = tempfile.NamedTemporaryFile().name
        content = ''
        for (param, value) in extra_data.iteritems():
            content += '{0}={1}\n'.format(param, value)
        self._write_to_file(tmp_file1, content)
        subr.enminst_working = tmp_file1

        self._write_working_file(content)

        tmp_file2 = tempfile.NamedTemporaryFile().name
        cryptr = EncryptPassword(the_to_state_sed, tmp_file2, verbose)
        cryptr.encrypt_configmanager_passwords()

        subr.build_full_file(the_to_state_sed, tmp_file2)
        self.log.debug('Interpolating DD template ' +
                '{0} with SED {1} and extra data'.format(the_to_state_dd_tmplt,
                                                         the_to_state_sed))
        the_xml = subr.replace_values(subr.read_file(the_to_state_dd_tmplt))

        subr.verify_xml(the_xml)
        subr.write_file(the_xml)

        self._remove_file(tmp_file1)
        self._remove_file(tmp_file2)
        unity_model_updates(Rh7EnmUpgrade.ENM_DD)

        msg = ('Creation of finalized To-state DD/LITP model '
               'completed successfully')
        self._print_stage_success(msg)

    def _do_infra_plan(self):
        """
        Stage: create and run Infrastructure Plan
        :return: None
        """

        def dict_compare(dict1, dict2):
            """
            Compare two dictionaries
            :param dict1: the first dictionary
            :type dict1: dict
            :param dict2: the second dictionary
            :type dict2: dict
            :return: 2-tuple of dictionary deltas: items added, items modified
            :rtype: 2-tuple: set, dict
            """
            d1_keys = set(dict1.keys())
            d2_keys = set(dict2.keys())
            shared_keys = d1_keys.intersection(d2_keys)

            added = d1_keys - d2_keys

            modified = {}
            for skey in shared_keys:
                if dict1[skey] != dict2[skey]:
                    modified[skey] = (dict1[skey], dict2[skey])

            return added, modified

        self._print_stage_start()

        desc = 'Infra'

        pkgs = ['ERIClitpvcs_CXP9030870']
        prop_name = 'infra_update'

        if not self.litp:
            self.litp = LitpRestClient()

        resume = self._get_resume_param()

        if not resume:
            if not self.the_to_state_dd:
                self.the_to_state_dd = Rh7EnmUpgrade.ENM_DD

            for dd_file in (self.EXPORTED_ENM_FROM_STATE_DD,
                        self.the_to_state_dd):
                if not os.path.exists(dd_file):
                    msg = 'File "{0}" does not exist'.format(dd_file)
                    self._print_error(msg)
                    sys.exit(1)

            from_root = load_xml(self.EXPORTED_ENM_FROM_STATE_DD).getroot()
            to_root = load_xml(self.the_to_state_dd).getroot()

            key_delimiter = '::'

            from_items_dict = {}
            to_items_dict = {}

            for ctype in infra_check.CHANGE_TYPES:
                for (the_root, the_dict) in ((from_root, from_items_dict),
                                         (to_root, to_items_dict)):
                    for fitem in xpath(the_root, ctype):
                        ckey = "{0}{1}{2}".format(ctype, key_delimiter,
                                            infra_check.get_model_path(fitem))

                        the_dict[ckey] = {}
                        for key, val in get_xml_element_properties(
                            fitem).items():
                            if key in infra_check.CHANGE_TYPE_PROPERTIES[
                                ctype]:
                                the_dict[ckey][key] = val

            added, modified = dict_compare(to_items_dict, from_items_dict)

            self.log.debug("New items added: {0}".format(added))
            self.log.debug("Items modified: {0}".format(modified))

            if added or modified:
                clis = self._gen_infra_plan_delta_clis(added,
                                                   modified,
                                                   to_root,
                                                   key_delimiter)

                if clis:
                    cli_file = 'infra_plan_clis.sh'
                    self._write_to_file(cli_file, clis)

                    cmd = 'sh {0}'.format(cli_file)
                    return_code, _ = self._run_command(cmd)
                    msg = 'Run infrastructure Plan CLIs in {0}'.format(
                        cli_file)
                    self._assert_return_code(return_code, msg)
                    self._remove_file(cli_file)
                    self._mng_plugins('remove', pkgs)
                    self._set_upgrd_props([prop_name])

                    if self._create_litp_plan(desc, nlt=True,
                                              dnpe_allowed=True):
                        self._run_litp_plan(desc)
                        self._monitor_litp_plan(desc)
                    else:
                        self.log.debug("DNPE, no {0} Plan needed".format(desc))
                        self.last_plan_do_nothing_plan = True

                    self._unset_upgrd_props([prop_name])
                    self._mng_plugins('install', pkgs)
                else:

                    self.log.debug("No clis, no {0} Plan needed".format(desc))
                    self.last_plan_do_nothing_plan = True

            else:
                self.log.debug("No delta, no {0} Plan needed".format(desc))
                self.last_plan_do_nothing_plan = True

        else:
            self._run_litp_plan(desc, resume=resume)
            self._monitor_litp_plan(desc, resume=resume)
            self._unset_upgrd_props([prop_name])
            self._mng_plugins('install', pkgs)

        msg = 'Infrastructure delta completed'
        self._print_stage_success(msg)

    def _gen_infra_plan_delta_clis(self, added, modified, xml_root, delimiter):
        """
        Generate Infrastructure Plan "delta" CLIs
        (ie LITP 'create' and 'update' commands)
        :param added: items to be added
        :type added: set of itemtype::model-path strings
        :param modified: modified items
        :type modified: dict
        :param xml_root: XML doc root for To-state DD
        :type xml_root: root Element
        :param delimter: compound dict key delimiter
        :type delimiter: string
        :return: delta CLIs
        :rtype: string
        """

        def _get_item_by_itemtype_and_vpath(xml_root, itemtype, vpath):
            """
            Get XML item by ItemType and vpath
            :param xml_root: XML doc root for To-state DD
            :type xml_root: root Element
            :param itemtype: LITP ItemType
            :type itemtype: string
            :param vpath: LITP item vpath
            :type vpath: string
            :return: LITP XML item
            :rtype: list
            """
            for titem in xpath(xml_root, itemtype):
                if vpath == infra_check.get_model_path(titem):
                    return titem

        def _process_delta(compound_key, xml_root, litp_rest):
            """
            Process a modified or added delta
            :param compound_key: compound key of itemtype and vpath
            :type compound_key: string
            :param xml_root: XML doc root for To-state DD
            :type xml_root: root Element
            :param litp_rest: LITP Rest client
            :type litp_rest: LitpRestClient
            :return: 4-tuple: itemtype, vpath, properties, valid-infra-delta
            :rtype: 4-tuple: string, string, dict, bool
            """
            ctype, path = compound_key.split(delimiter, 1)
            item = _get_item_by_itemtype_and_vpath(xml_root, ctype, path)
            props = get_xml_element_properties(item)
            valid_delta = (('file-system' != ctype) or
                           ('type' in props.keys() and
                            'vxfs' == props['type'] and
                        litp_rest.exists(infra_check._get_parent_path(item))))
            return ctype, path, props, valid_delta

        clis = ''

        for compound_key in added:
            ctype, path, props, valid_delta = _process_delta(compound_key,
                                                             xml_root,
                                                             self.litp)
            if valid_delta:
                params = ' '.join("{0}={1}".format(k, v)
                                  for (k, v) in props.items())
                clis += 'litp create -t {0} -p {1} -o {2}\n'.format(ctype,
                                                                    path,
                                                                    params)

        for (compound_key, delta) in modified.items():
            ctype, path, _, valid_delta = _process_delta(compound_key,
                                                         xml_root,
                                                         self.litp)
            if valid_delta:
                params = ' '.join("{0}={1}".format(k, v)
                                  for (k, v) in delta[0].items())
                clis += 'litp update -p {0} -o {1}\n'.format(path, params)

        if clis:
            self.log.debug("Infrastructure Plan delta CLIs: {0}".format(clis))
        else:
            self.log.debug('No Infrastructure Plan delta CLIs created')

        return clis

    def _process_lms_services(self, services, action):
        """
        Perform a provided systemd action on a list of services.
        :param services: List of systemd services
        :type services: list
        :param action: The systemd action
        :type action: string
        :return: None
        """
        self._run_command_set(["/usr/bin/systemctl {0} {1}".format(action, svc)
                               for svc in services],
                              '{0} systemd services'.format(action))

        if action is 'start':
            self._wait_for_services(services)

    def _wait_for_services(self, services):
        """
        Wait for all services to become active
        :param services: List of systemd services
        :type services: list
        :return: None
        """

        timeout_secs = 120
        interval = 3.0

        time.sleep(10)
        timeout = Rh7EnmUpgrade.Timeout(timeout_secs)

        results = {}
        while not timeout.has_time_elapsed():
            results.clear()
            for svc in services:
                cmd = ('/usr/bin/systemctl ' +
                       'is-active --quiet {0}'.format(svc))
                results[svc], _ = self._run_command(cmd)

            if any(results.values()):
                timeout.sleep_for(interval)
            else:
                return

        if timeout.has_time_elapsed() and any(results.values()):
            msg = 'Service(s) did not become active ' + \
                  'in {0} seconds: {1}'.format(
                           timeout_secs,
                           ' '.join([svc
                                     for svc, result in results.iteritems()
                                     if result]))
            self._print_error(msg)
            sys.exit(1)

    def _create_hollow_manifests(self):
        """
        Create hollow Puppet Plugins Manifest files. This is necessary to
        prevent any errors from the manifest files when Puppet runs at this
        stage of the Uplift. At this point of the Uplift there will not be any
        manifest files from the nodes so it will be necessary to create them
        using the mco backup file.
        :return: None
        """
        self.log.debug("Hollow out the manifest files")

        # Create the strings for the hollow files
        manifest_node_template = """node "{0}" {{

    class {{'litp::mn_node':
        ms_hostname => "{1}",
        cluster_type => "NON-CMW"
        }}
}}"""

        # Get the MS hostname
        ms_hostname = self._get_hostname().lower()

        # Ensure the backup file has been restored
        if not os.path.isfile(Rh7EnmUpgrade.MCO_LIST_BACKUP):
            msg = ('Backup File not found: {0}'
                   .format(Rh7EnmUpgrade.MCO_LIST_BACKUP))
            self._print_error(msg)
            sys.exit(1)

        # Read the contents of the backup file and save them for later use
        self.mco_backup_list = sorted(
            self._read_file(Rh7EnmUpgrade.MCO_LIST_BACKUP).splitlines())
        self.log.debug("Backup mco Peer Node list: {0}"
                       .format(self.mco_backup_list))

        # Loop through and Create hollow Puppet Plugins Manifest files.
        # Ensure the User is 'celery' and group is 'puppet' for each file.
        litp_puppet_manifest_dir = os.path.join(Rh7EnmUpgrade.LITP_PUPPET_DIR,
                                                'manifests', 'plugins')
        for host in self.mco_backup_list:
            host = host.lower()
            full_path = "{0}.pp".format(os.path.join(litp_puppet_manifest_dir,
                                                     host))
            if ms_hostname != host:
                basic_man = manifest_node_template.format(host, ms_hostname)

                self.log.debug("Create hollow version of file '{0}' with user "
                               "'celery' and group 'puppet'".format(full_path))
                self.log.debug('Write the following :\n{0}'.format(basic_man))
                self._write_to_file(
                    full_path, basic_man, user="celery", group="puppet")

    def _compare_mco_backup_list(self):
        """
        Compare the Backed Up MCO list with the current list. Ensure that they
        are the same. Fail if they differ.
        This method should be used after '_create_hollow_manifests', otherwise
        'self.mco_backup_list' will not be populated.
        :return: None
        """
        self.log.debug("Compare the Backed up and current mco Peer Node lists")

        self.log.debug("Backup mco Peer Node list: {0}"
                       .format(self.mco_backup_list))

        # Get the current Peer Node list and store them for later use
        self.mco_peer_list = sorted(self._get_mco_peer_list().splitlines())
        self.log.debug("Current mco Peer Node list: {0}"
                       .format(self.mco_peer_list))

        # Ensure the backed up Peer Node list is the same as the current list
        if self.mco_backup_list != self.mco_peer_list:
            msg = ("The Backup and Current Peer Node lists differ. "
                   "Backup: {0}. Current {1}"
                   .format(self.mco_backup_list, self.mco_peer_list))
            self._print_error(msg)
            sys.exit(1)
        self.log.debug("Current Peer Node list is the same as the list in the "
                       "backup file.")

    def _trigger_puppet_and_wait(self):
        """
        Trigger the Peer nodes to pick up the latest Puppet manifests.
        :return: node
        """
        self.log.debug("Trigger Puppet and wait for nodes: {0}"
                       .format(self.mco_peer_list))

        # Trigger a Puppet run by incrementing the LITP Catalog version.
        puppet_trigger_wait(True, self.log.info, self.mco_peer_list)

    def _restore_mco_conn(self):
        """
        Restore the MCO Connectivity. Stop the services, hollow out selected
        manifest files, and start the services.
        :return: None
        """
        self._print_stage_start()

        # Stop the selected services.
        services = ['puppet', 'puppetserver', 'puppetdb', 'rabbitmq-server',
                    'mcollective', 'litpd']
        self._process_lms_services(services, 'stop')

        # Hollow out the manifest files.
        self._create_hollow_manifests()

        # Start all except the 'puppet' service to avoid conflicts when we
        # explicitly kick the puppet agent
        self._process_lms_services(services[1:], 'start')

        # Kick the puppet agent as we need it to apply config before proceeding
        cmd = '/usr/bin/puppet agent --test'
        self._run_command(cmd)

        # Now start the 'puppet' service
        self._process_lms_services(services[:1], 'start')

        # Ensure the current Peer Node list is the same as the backed up list
        self._compare_mco_backup_list()

        # Clear the LITP Puppet Cache
        self._trigger_puppet_and_wait()

        msg = 'MCO Connectivity has been restored successfully'
        self._print_stage_success(msg)

    @staticmethod
    def _gen_sgmnts_data():
        """
        Generate To-state Segments data.
        :return: dict of vpath mapped to filepath
        :rtype: dict
        """
        xml_segments = [('/software', 'software'),
             ('/infrastructure/systems/management_server', 'ms_infra_systems'),
             ('/infrastructure/storage/storage_profiles/ms_storage_profile',
                                                  'ms_infra_storage_profile'),
             ('/infrastructure/networking/routes', 'infra_routes'),
             ('/infrastructure/storage/nfs_mounts', 'infra_nfs_mounts'),
             ('/infrastructure/storage/managed_files', 'infra_managed_files'),
             ('/infrastructure/storage/storage_providers',
                                                    'infra_storage_providers'),
             ('/infrastructure/system_providers', 'infra_system_providers'),
             ('/infrastructure/service_providers', 'infra_service_providers'),
             ('/infrastructure/items', 'infra_items'),
             ('/ms', 'ms')]

        data = {}
        for (vpath, fname) in xml_segments:
            data[vpath] = os.path.join(Rh7EnmUpgrade.ENM_RT_DIR,
                                       'to_state_' + fname + '.xml')
        return data

    def _create_to_state_dd_sgmnts(self):
        """
        Stage: create To-state DD segments
        :return: None
        """

        self._print_stage_start()

        if not self.the_to_state_dd:
            self.the_to_state_dd = Rh7EnmUpgrade.ENM_DD

        if not os.path.exists(self.the_to_state_dd):
            msg = '{0} not found'.format(self.the_to_state_dd)
            self._print_error(msg)
            sys.exit(1)

        purge_cmds = ['systemctl stop litpd.service',
                      '/usr/local/bin/litpd.sh --purgedb',
                      'systemctl start litpd.service']

        cmds = purge_cmds + \
            ['litp load -p / -f {0} --merge'.format(self.the_to_state_dd)]

        if not self.to_state_sgmnts_data:
            self.to_state_sgmnts_data = Rh7EnmUpgrade._gen_sgmnts_data()

        for (vpath, fpath) in self.to_state_sgmnts_data.iteritems():
            cmds.append('litp export -p {0} -f {1}'.format(vpath, fpath))

        pp_cmd = self._post_process_ms_sgmt()
        if pp_cmd:
            cmds.append(pp_cmd)

        cmds.extend(purge_cmds)

        self._run_command_set(cmds, 'Create To-state DD segments')

        msg = 'To-state DD segments created'
        self._print_stage_success(msg)

    def _post_process_ms_sgmt(self):
        """
        Post process the MS segment to remove the sshd-config item XML
        :return: command to remove item from XML
        :rtype: string
        """
        cmd = None

        if '/ms' in self.to_state_sgmnts_data.keys():
            cmd = (r"sed -i -e '/^ *<litp:sshd-config .*$/d' " +
                          r"-e '/^ *<permit_root_login>.*$/d' " +
                          r"-e '/^ *<\/litp:sshd-config> *$/d' " +
                          self.to_state_sgmnts_data['/ms'])
        return cmd

    def _load_sgmnts_ms_redeploy(self):
        """
        Stage: load XML segments for MS Redeploy Plan
        :return: None
        """
        self._print_stage_start()

        self._restore_litp_state()
        self._update_apd()
        self._migrate_forwarding_delay()
        self._purge_persistent_tasks()

        if not self.to_state_sgmnts_data:
            self.to_state_sgmnts_data = Rh7EnmUpgrade._gen_sgmnts_data()

        for (vpath, fpath) in self.to_state_sgmnts_data.iteritems():
            vpath = '/' + '/'.join(vpath.split(os.path.sep)[1:-1])
            self._load_model(fpath, vpath)
        # Do the /ms delta for the items and properties that need be deleted
        self._create_xml_diff_file(Rh7EnmUpgrade.ENM_PREVIOUS_DD,
                                   Rh7EnmUpgrade.ENM_DD)
        items = self._parse_deploy_diff_output()
        self._remove_items_from_model(items, ms_only=True)
        # Do the /ms delta for the model-package items that need to be deleted
        self._create_xml_diff_file(Rh7EnmUpgrade.EXPORTED_ENM_FROM_STATE_DD,
                                   Rh7EnmUpgrade.ENM_DD)
        items = self._parse_model_packages_from_diff()
        self._remove_items_from_model(items)
        self._migrate_repo_urls()
        # Set /deployments to Applied in preparation for the LITP create_plan
        self._set_model_state('/deployments', 'Applied')
        msg = 'RH7 XML segments for MS redeploy loaded'
        self._print_stage_success(msg)

    def _restore_litp_state(self):
        """
        Restore backed up LITP DB.
        :return: None
        """

        litp_dump = 'litp_db.dump'
        files = glob.glob(os.path.join(Rh7EnmUpgrade.LITP_RT_DIR,
                                       'litp_backup_*'))
        latest_litp_backup = max(files, key=os.path.getctime)
        self.log.debug("Extracting {0} from {1}.".format(litp_dump,
                                                         latest_litp_backup))

        with closing(tarfile.open(latest_litp_backup, 'r:gz')) as tarball:
            self._restore_litp_db(tarball, tarball.getmember(litp_dump),
                                  'litp')

    def _restore_litp_db(self, tarball, dump, db_name):
        """
        Execute the pg_restore on backup LITP DB.
        param tarball: litp_backup tarball
        type tarball: tarfile
        param dump: litp_db.dump
        type dump: TarInfo object
        param db_name: LITP db name
        type dump: string
        :return: None
        """
        self.log.debug("Restoring the LITP DB.")

        cmd = "su - postgres -c '/usr/bin/pg_restore{0} -d {1} -c'".format(
                                                self.get_psql_host_option(),
                                                db_name)

        proc = subprocess.Popen(cmd,
                                shell=True,
                                stdout=subprocess.PIPE,
                                stdin=subprocess.PIPE)

        with closing(tarball.extractfile(dump)) as dump_file:
            stdout, stderr = proc.communicate(dump_file.read())
            self._assert_return_code(proc.returncode,
                                     cmd + ':' + str(stdout) + str(stderr))

    def _update_apd(self):
        """
        Update all APD flags
        :return: None
        """
        cmd = 'sudo su - postgres -c "psql -d litp{0} -c '\
            '\\\"update model set '\
            'applied_properties_determinable=\'t\' where model_id=\'LIVE\' '\
            'and class_name=\'ModelItem\'\\\"\"'.format(
            self.get_psql_host_option())

        return_code, _ = self._run_command(cmd,
                                    timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, 'Update all APD flags')

        msg = 'Updated all APD flags successfully.'
        self._print_message(msg)

    def _migrate_repo_urls(self):
        """
        Migrate yum repo urls in LITP model
        :return: None
        """
        self.log.debug("Migrate repo url properties in LITP Model.")
        if not self.litp:
            self.litp = LitpRestClient()
        enm_repo_names = Rh7EnmUpgrade._get_enm_repo_names_from_paths()
        # get all source itmes of type yum-repository and vm-yum-repo

        yum_repos = self.litp.get_all_items_by_type(
                            '/software', 'yum-repository', [])
        vm_yum_repos = self.litp.get_all_items_by_type('/ms',
                                            'vm-yum-repo', [])
        vm_yum_repos = vm_yum_repos + self.litp.get_all_items_by_type(
                            '/software', 'vm-yum-repo', [])

        for yum_repo in yum_repos:
            ms_url_path = yum_repo['data']['properties']['ms_url_path']
            segs = ms_url_path.split('/')
            for name in enm_repo_names:
                if name == segs[1]:  # migrate
                    segs[1] += '_rhel7'
                    ms_url_path = '/'.join(segs)
                    properties = {'ms_url_path': ms_url_path}
                    self.litp.update(yum_repo['path'], properties)
                    break

        for vm_yum_repo in vm_yum_repos:
            base_url = vm_yum_repo['data']['properties']['base_url']
            segs = base_url.split('/')
            for name in enm_repo_names:
                if name == segs[3]:  # migrate
                    segs[3] += '_rhel7'
                    base_url = '/'.join(segs)
                    properties = {'base_url': base_url}
                    self.litp.update(vm_yum_repo['path'], properties)
                    break

    def _migrate_forwarding_delay(self):
        """
        Migrate forwarding_delay property in LITP model
        :return: None
        """
        self.log.debug("Migrate forwarding_delay property in LITP Model.")
        if not self.litp:
            self.litp = LitpRestClient()

        bridges = self.litp.get_items_by_type('/deployments', 'bridge', [])
        bridges = bridges + self.litp.get_items_by_type('/ms', 'bridge', [])
        # Reset / to Initial
        self._set_model_state('', 'Initial')

        for bridge in bridges:
            updated_value = None
            fdelay = int(bridge['data']['properties']['forwarding_delay'])
            if fdelay <= 3:
                updated_value = '4'
            if fdelay > 30:
                updated_value = '30'

            if updated_value:
                properties = {'forwarding_delay': updated_value}
                self.litp.update(bridge['path'], properties)

    def _purge_persistent_tasks(self):
        """
        Purge LITP DB persisted tasks
        :return: None
        """
        # delete all
        cmd = 'sudo su - postgres -c \"psql -d litp{0} -c '\
            '\\\"delete from persisted_tasks\\\"\"'.format(
            self.get_psql_host_option())

        return_code, _ = self._run_command(cmd,
                                    timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, 'Purge DB persisted tasks')

        msg = 'DB persisted tasks successfully purged.'
        self._print_message(msg)

    def _load_model(self, file_name, path='/'):
        """
        Load LITP model
        param file_name: XML file name
        type file_name: string
        param path: starting vpath
        type path: string
        :return: None
        """

        if not os.path.exists(file_name):
            msg = '{0} not found'.format(file_name)
            self._print_error(msg)
            sys.exit(1)

        cmd = 'litp load -p {0} -f {1} --merge'.format(path, file_name)

        return_code, _ = self._run_command(cmd,
                                    timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code,
                                 'Load {0} LITP model XML'.format(file_name))

        msg = '{0} LITP model loaded successfully.'.format(file_name)
        self._print_message(msg)

    def _create_xml_diff_file(self, from_state_xml, to_state_xml):
        """
        Generate a diff file with a list of item path's to be removed
        param from_state_xml: XML file name
        type from_state_xml: string
        param to_state_xml: XML file name
        type to_state_xml: string
        :return: None
        """

        dd_delta_tool = os.path.join(Rh7EnmUpgrade.OPT_ERIC, 'dstutilities',
                                     'bin', 'dst_dd_delta_generator.sh')
        if not os.path.isfile(from_state_xml) or \
           not os.path.isfile(to_state_xml) or \
           not os.path.isfile(dd_delta_tool):

            msg = 'File {0}, {1} or {2} not found'.format(from_state_xml,
                                                          to_state_xml,
                                                          dd_delta_tool)
            self._print_error(msg)
            sys.exit(1)
        self._remove_file(Rh7EnmUpgrade.DELTA_OUTPUT)
        cmd = ' '.join([dd_delta_tool,
                        from_state_xml,
                        to_state_xml,
                        Rh7EnmUpgrade.DELTA_OUTPUT])
        return_code, _ = self._run_command(cmd,
                                    timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, 'Run create_xml_diff_file')
        msg = 'Created XML diff file {0}.'.format(Rh7EnmUpgrade.DELTA_OUTPUT)
        self._print_message(msg)

    def _parse_model_packages_from_diff(self):
        """
        Parse the DELTA_OUTPUT file to identify removable model_packages.
        :return: list of tuples [(path, property), ...]
        """
        items = []
        regex = re.compile('^n /software/items/model_package/packages')
        with open(Rh7EnmUpgrade.DELTA_OUTPUT, 'r') as _reader:
            for line in _reader.readlines():
                if regex.search(line):
                    item = line.strip().split()[1]
                    cmd = "litp show -p {0} | grep type: ".format(item)
                    _, stdout = self._run_command(cmd)
                    item_type = stdout.split(' ')[-1]
                    if item_type == 'model-package':
                        items.append((item, None))
        return items

    def _parse_deploy_diff_output(self, types_filter=None):
        """
        Parse the DELTA_OUTPUT file to identify items and properties that could
        be removed.
        :type types_filter: list
        :return: list of tuples [(path, property), ...]
        """
        if types_filter is None:
            types_filter = []
        items = []
        with open(Rh7EnmUpgrade.DELTA_OUTPUT, 'r') as _reader:
            for line in _reader.readlines():
                if line.strip().startswith('y '):
                    item = line.strip().split()[1].split('@')
                    if types_filter:
                        cmd = "litp show -p {0} | grep type: ".format(
                            item[-1])
                        _, stdout = self._run_command(cmd)
                        item_type = stdout.split(' ')[-1]
                    if not types_filter or item_type in types_filter:
                        if len(item) == 2:
                            items.append((item[1], item[0]))
                        else:
                            items.append((item[0], None))
        return items

    def _remove_items_from_model(self, items, ms_only=False):
        """
        Remove items and properties from the LITP model.
        :param items: item paths to be removed
        type items: list
        param ms_only: ms filter
        type ms_only: bool
        :return: None
        """
        if not items:
            self.log.debug('No items or properties to be removed from the '
                           'runtime LITP model')
        else:
            if not self.litp:
                self.litp = LitpRestClient()

            for path, prop in items:
                if not ms_only or \
                   (ms_only and (path.startswith('/ms/') or
                                 path.startswith('/software/images/'))):
                    if prop:
                        if "_map" in prop:
                            continue
                        if self.litp.delete_property(path, prop):
                            self.log.debug(
                                "Property '{0}' successfully deleted "
                                "within '{1}' item".format(prop, path))
                        else:
                            self.log.debug(
                              "Property '{0}' or item '{1}' does "
                              "not exist in the LITP model".format(prop, path))

                    else:
                        if self.litp.delete_path(path):
                            self.log.debug("Item '{0}' successfully "
                                      "deleted".format(path))
                        else:
                            self.log.debug("Item '{0}' does not exist in the "
                                      "LITP model".format(path))
            self.log.info('Runtime LITP model update finished')

    def _set_model_state(self, vpath, state, recurse=True):
        """
        Set <vpath> LITP model items to <state>
        param vpath: The LITP model item's vpath can be ''
        type items: string
        param state : The LITP model item's state to set
        type state: string
        param recurse : Should items under vpath be updated
        type recurse: Boolean
        :return: None
        """

        cmd = 'sudo su - postgres -c \"psql -d litp{0} -c \\\"update model '\
              'set state=\'{1}\' where vpath {2} \'{3}{4}\' and '\
              'model_id=\'LIVE\'\\\"\"'.format(self.get_psql_host_option(),
                                               state,
                                               'like' if recurse else '=',
                                               vpath, '%' if recurse else '')
        return_code, _ = self._run_command(cmd,
            timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, 'Run _set_model_state')
        msg = 'Ran _set_model_state {0} {1} {2}'.format(vpath, state, recurse)
        self._print_message(msg)

    def _set_vcs_clustered_service_apd(self, vpath, state):
        """
        Set applied_properties_determinable to <state> on the
        vcs_clustered_service that is grandparent of the item that inherits
        service <vpath>.
        param vpath: service LITP model item's vpath
        type vpath: string
        param state : APD state to set ('t' or 'f')
        type state: string
        :return: None
        """
        cmd = 'sudo su - postgres -c \"psql -d litp{0} -c \\\"update model '\
              'set applied_properties_determinable=\'{1}\' where model_id='\
              '\'LIVE\' and item_type_id=\'{2}\' and vpath in '\
              '(select grandparent.vpath from model child '\
              'inner join model parent on child.parent_vpath = parent.vpath '\
              'and child.model_id = parent.model_id '\
              'inner join model grandparent on parent.parent_vpath = '\
              'grandparent.vpath and parent.model_id = grandparent.model_id '\
              'where child.model_id=\'LIVE\' and child.source_vpath=\'{3}\')'\
              '\\\"\"'.format(self.get_psql_host_option(),
                              state, ITEM_TYPE_VCS_CLUSTERED_SERVICE, vpath)

        return_code, _ = self._run_command(cmd,
            timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        msg = 'Run _set_vcs_clustered_service_apd({0}, {1})'.format(vpath,
                                                                    state)
        self._assert_return_code(return_code, msg)

    def _redeploy_ms(self):
        """
        Stage: run the Redeploy MS Plan
        :return: None
        """
        self._print_stage_start()
        resume = self._get_resume_param()

        pkgs = ['ERIClitpmodeldeployment_CXP9031595',
                'ERIClitpvcs_CXP9030870',
                'ERIClitpopendj_CXP9031976']

        prop_name = 'redeploy_ms'
        desc = 'MS Redeploy'

        if not resume:
            self._set_upgrd_props([prop_name])
            self._mng_plugins('remove', pkgs)
            # Set /deployments to Applied in preparation for the create_plan
            self._set_model_state('/deployments', 'Applied')
            self._create_litp_plan(desc)

        self._run_litp_plan(desc, resume=resume)
        self._monitor_litp_plan(desc, resume=resume)

        self._unset_upgrd_props([prop_name])
        self._mng_plugins('install', pkgs)
        msg = 'RH7 MS Redeployed'
        self._print_stage_success(msg)

    def _post_process_restored_data(self):
        """
        Post process restored data stage of RHEL7 uplift
        :return: None
        """
        self._print_stage_start()
        self._restore_esmon_data()
        msg = 'Post processing of restored was successful'
        self._print_stage_success(msg)

    def _restore_esmon_data(self):
        """
        Stop esmon vm, restore data from the tar.gz onto its volume and
        restart the vm
        :return: None
        """
        services = ['puppet']
        self._process_lms_services(services, 'stop')

        esmon_svc_name = 'esmon'
        esmon_volume = os.path.join(os.sep, 'dev', 'mapper',
                                    'vg_root-vg1_fs_data')
        mount_point = tempfile.mkdtemp()
        volume_mount_cmd = 'mount {0} {1}'.format(esmon_volume, mount_point)
        esmon_data_path = Rh7EnmUpgrade._gen_esmon_backup_name()
        volume_umount_cmd = 'umount {0}'.format(esmon_volume)

        self.log.debug('Stopping esmon vm')
        undefine_cmd = Rh7EnmUpgrade.LITP_MN_LIBVIRT + \
        ' {0} stop-undefine --stop-timeout=45'.format(esmon_svc_name)
        return_code, _ = self._run_command(undefine_cmd)
        self._assert_return_code(return_code, undefine_cmd)

        return_code, _ = self._run_command(volume_mount_cmd)
        self._assert_return_code(return_code, volume_mount_cmd)

        self.log.debug('Extracting data to {0}'.format(mount_point))
        with closing(tarfile.open(esmon_data_path, 'r:gz')) as tar_data:
            tar_data.extractall(mount_point)

        return_code, _ = self._run_command(volume_umount_cmd)
        self._assert_return_code(return_code, volume_umount_cmd)
        shutil.rmtree(mount_point)

        self.log.debug('Starting esmon vm')
        self._change_svc_state(esmon_svc_name, 'start')

        self._process_lms_services(services, 'start')
        self._print_message('ESMon data restored')

    def _change_svc_state(self, svc, desired_state, system='systemd'):
        """
        Change state of a service
        :param svc: name of the service
        :type svc: string
        :param desired_state: desired state
        :type desired_state: string
        :param system: systemd v sysV
        :type system: string
        :return: None
        """

        if 'systemd' == system:
            cmd = '/usr/bin/systemctl {0} {1}.service'.format(desired_state,
                                                              svc)
        elif 'sysv' == system:
            cmd = '/sbin/service {0} {1}'.format(svc, desired_state)

        rcode, _ = self._run_command(cmd)
        self._assert_return_code(rcode, cmd)

    @staticmethod
    def _get_chks_data():
        """
        Get Upgrade precheck and Health check data
        :return: 2-tuple of two dicts
        :rtype: 2-tuple
        """

        # When adding extra checks consider updating
        # _upgrd_pre_chks_and_hlth_chks and _perform_checks

        # Upgrade precheck (UPC) masks
        upc_data = {0x1: 'storage_setup_check',
                    0x2: 'check_lvm_conf_non_db_nodes',
                    0x4: 'elastic_search_status_check',
                    0x8: 'opendj_replication_check',
                    0x10: 'unmount_iso_image_check',
                    0x20: 'check_fallback_status',
                    0x40: 'remove_seed_file_after_check'}
                #   0x80: 'litp_model_synchronized_check'

        # Health check (HC) masks
        hc_data = {0x1: 'san_alert',
                   0x2: 'nas',
                   0x4: 'storagepool',
                   0x8: 'stale_mount',
                   0x10: 'node_fs',
                   0x20: 'puppet_enabled',
                   0x40: 'system_service',
                   0x80: 'vcs_cluster',
                   0x100: 'vcs_llt_heartbeat',
                   0x200: 'vcs_service_group',
                   0x400: 'consul',
#                  0x800: 'multipath_active',
#                  0x1000: 'fcaps',
#                  0x2000: 'ombs_backup',
                   0x4000: 'hw_resources'}

        return (upc_data, hc_data)

    def _upgrd_pre_chks_and_hlth_chks(self):
        """
        Stage: run the Upgrade prechecks and Health checks
        :return: None
        """

        (upc_data, hc_data) = Rh7EnmUpgrade._get_chks_data()

        no_upcs = 0x0
        seven_upcs = 0x7F

        twelve_hcs = 0x47FF
        eleven_hcs = 0x47FD  # no NAS HC

        stage_checker_map = {'08': (seven_upcs, twelve_hcs),
                             '10': (seven_upcs, twelve_hcs),
                             '12': (seven_upcs, twelve_hcs),
                             '14': (seven_upcs, eleven_hcs),
                             '17': (seven_upcs, (twelve_hcs, eleven_hcs)),
                             '20': (no_upcs, twelve_hcs),
                             '22': (no_upcs, (twelve_hcs, eleven_hcs))}

        self._print_stage_start()

        if not self.current_stage:
            msg = 'Unable to determine current stage identity. Cannot continue'
            self._print_error(msg)
            sys.exit(1)

        stage_id = self.current_stage['idx']
        stage_attrs = '{0} / {1}'.format(stage_id, self.current_stage['label'])

        try:
            stage_masks = stage_checker_map[stage_id]
        except KeyError:
            msg = ('Current stage {0} is not a recognised stage for ' +
                   'Upgrade prechecks or Health checks').format(stage_attrs)
            self._print_error(msg)
            sys.exit(1)

        if stage_masks[0]:
            self._do_upgrd_prechks(upc_data, stage_masks[0])

        if stage_masks[1]:
            if type(stage_masks[1]) == tuple:
                if self.last_plan_do_nothing_plan:
                    stage_hcs = stage_masks[1][1]
                else:
                    stage_hcs = stage_masks[1][0]
            else:
                stage_hcs = stage_masks[1]

            self._do_health_chks(hc_data, stage_hcs)

        self.last_plan_do_nothing_plan = False
        self._print_stage_success()

    def _do_upgrd_prechks(self, upc_data, stage_upcs):
        """
        Perform Upgrade prechecks
        :param upc_data: Upgrade precheck data, mapping UPC mask to UPC name
        :type upc_data: dict, key hex number, value UPC name
        :param stage_upcs: bit mask indicating UPCs required for current stage
        :type stage_upcs: int
        :return: None
        """

        upg_prechecker = EnmPreChecks()
        upg_prechecker.create_arg_parser()
        args = ['--assumeyes', '--action']
        args.extend([name for (mask, name) in upc_data.iteritems()
                     if bool(stage_upcs & mask)])

        if self._get_verbose_param():
            args.append('--verbose')

        upg_prechecker.processed_args = upg_prechecker.parser.parse_args(args)
        upg_prechecker.set_verbosity_level()

        actions = upg_prechecker.processed_args.action
        self.log.debug("Upgrade precheck action(s): {0}".format(actions))

        try:
            upg_prechecker.process_actions(actions)
        except SystemExit:
            msg = 'Upgrade PreCheck(s) failed'
            self._print_error(msg)
            raise

    def _do_health_chks(self, hc_data, stage_hcs):
        """
        Perform the Health checks
        :param hc_data: Health check data, mapping HC mask to HC name
        :type hc_data: dict, key hex number, value HC shortened name
        :param stage_hcs: bit mask indicating HCs required for current stage
        :type stage_hcs: int
        :return: None
        """

        verbose = self._get_verbose_param()

        hchecker = HealthCheck()
        actions = ['{0}_healthcheck'.format(name)
                   for (mask, name) in hc_data.iteritems()
                   if bool(stage_hcs & mask)]
        self.log.debug("Health check action(s): {0}".format(actions))
        for action in actions:
            try:
                getattr(hchecker, action)(verbose=verbose)
            except SystemExit:
                msg = '{0} Health check failed'.format(action)
                self._print_error(msg)
                raise

    def _get_sfha_nodes(self):
        """
        Get the SFHA (ie DB) node hostnames and vpaths
        :return: dict of DB hostname mapped to vpath
        :rtype: dict, key string, value string
        """

        if not self.deps_clusters_nodes:
            self._init_node_data()

        sfha_nodes = {}
        for dep in self.deps_clusters_nodes.keys():
            for clus in self.deps_clusters_nodes[dep].keys():
                cpath = os.path.join(os.sep, 'deployments', dep,
                                             'clusters', clus)
                cmd = 'litp show -p {0} -o cluster_type'.format(cpath)
                _, stdout = self._run_command(cmd)
                if 'sfha' in stdout:
                    for node in self.deps_clusters_nodes[dep][clus]:
                        npath = os.path.join(cpath, 'nodes', node)
                        cmd = 'litp show -p {0} -o hostname'.format(npath)
                        retcode, stdout = self._run_command(cmd)
                        if 0 == retcode:
                            sfha_nodes[stdout] = {'node-id': node,
                                                  'node': npath,
                                                  'cluster': cpath}
        return sfha_nodes

    @staticmethod
    def _clean_yum_repos():
        """
        Cleanup any RH6 yum repositories
        :return: None
        """
        repo_folders = Rh7EnmUpgrade._get_enm_repo_names_from_paths()

        for folder in repo_folders:
            for variant in ('', '_rhel6'):
                dpath = os.path.join(Rh7EnmUpgrade.HTML_DIR, folder + variant)
                if os.path.exists(dpath):
                    shutil.rmtree(dpath)

    def _switch_db_grps_stage(self):
        """
        Stage to switch DB cluster CS groups.
        :return: None
        """
        self._print_stage_start()
        self._switch_db_grps()
        msg = 'Switched DB CS groups'
        self._print_stage_success(msg)

    def _switch_db_grps(self):
        """
        Call to switch DB cluster CS groups.
        :return: None
        """
        self._print_db_status('BEFORE')

        try:
            switch_dbcluster_groups()
        except SystemExit as se_error:
            msg = 'Failed to switch DB cluster groups: {0}'.\
                                                  format(str(se_error))
            self._print_error(msg)
            sys.exit(1)

        self._print_db_status('AFTER')

    def _print_db_status(self, stage_indicator):
        """
        Format and print DB cluster status information
        :param stage_indicator: Word indicating if this is before or after
                                the rebalancing request
        :type stage_indicator: string
        :return: None
        """

        if not self._get_verbose_param():
            return

        msg = '{0} DB node rebalancing:\n'.format(stage_indicator)
        (vgroups, headings) = Vcs().get_cluster_group_status(
                                        cluster_filter=Vcs.ENM_DB_CLUSTER_NAME,
                                        verbose=False)

        max_lens = [max([len(vgrp[hkey])
                         for vgrp in vgroups] +
                        [len(hkey)])
                    for hkey in headings]

        msg += ' '.join([headings[idx].ljust(max_lens[idx])
                         for idx in xrange(0, len(headings))]) + '\n'

        for vgrp in vgroups:
            msg += ' '.join([vgrp[headings[idx]].ljust(max_lens[idx])
                             for idx in xrange(0, len(headings))]) + '\n'

        self._print_message(msg)

    def _remove_files(self):
        """
        Remove a set of files
        :return: None
        """
        rfiles = [os.path.join(Rh7EnmUpgrade.ENM_RT_DIR, rfile)
                  for rfile in ('upgrade_enm_stage_data.txt',
                                'upgrade_enm_params.txt')]

        rfiles.append(os.path.join(os.sep, 'ericsson', 'tor', 'data',
                                   'neo4j', 'dbcreds.yaml'))

        model_xml = getattr(self.processed_args, Rh7EnmUpgrade.PARAM_MODEL, '')
        if model_xml.startswith('/tmp/') and model_xml.endswith('.xml'):
            rfiles.append(model_xml)

        rfiles.extend(Rh7EnmUpgrade._gen_sgmnts_data().values())
        rfiles.append(Rh7EnmUpgrade._gen_esmon_backup_name())

        for rfile in rfiles:
            self._remove_file(rfile)

    def _run_procedures(self):
        """
        Run Post Upgrade [remote] procedures:
        1. PostgreSQL reload
        2. Neo4j precheck
        3. esadmin_password_set.sh
        4. hw_comm.sh
        :return: None
        """

        self._print_message('Will run "PostgreSQL reload"')
        try:
            ENMUpgrade().postgres_reload()
        except McoAgentException as mae:
            msg = 'Failed to reload PostgreSQL: {0}'.format(str(mae))
            self._print_warning(msg)

        procs = [{'exe': os.path.join(Rh7EnmUpgrade.ENM_INST_DIR,
                                      'bin', 'esadmin_password_set.sh'),
                  'desc': 'Set ES admin password',
                  'cmd': None},
                 {'exe': os.path.join(Rh7EnmUpgrade.OPT_ERIC, 'hw_comm',
                                      'bin', 'hw_comm.sh'),
                  'desc': 'Disable IPMI Hardware commissioning',
                  'cmd': '{0} configure_ipmi -o disable {1}'}]

        procs[1]['cmd'] = procs[1]['cmd'].format(procs[1]['exe'],
                                                 getattr(self.processed_args,
                                                      Rh7EnmUpgrade.PARAM_SED))

        for proc in procs:
            if not os.path.isfile(proc['exe']):
                self.log.debug("{0} not found, skipping".format(proc['exe']))
                continue

            cmd = proc['cmd'] if proc['cmd'] else proc['exe']
            ret = 0
            self._print_message('Will run "{0}": {1}'.format(proc['desc'],
                                                             cmd))
            try:
                ret = os.system(cmd)
            except Exception as error:  # pylint: disable=W0703
                msg = 'Failed to execute {0}: {1}'.format(proc['desc'],
                                                          str(error))
                self._print_warning(msg)

            msg = 'Execution of "{0}" '.format(proc['desc'])
            if 0 == int(ret):
                msg += 'successful'
                self._print_message(msg)
            else:
                msg += 'failed with {0}'.format(ret)
                self._print_warning(msg)

    def _update_logs(self):
        """
        Update enm-version and history files
        :return: None
        """
        self.log.debug('Updating Version and History')
        try:
            Deployer.update_version_and_history()
        except IOError as ioe:
            msg = 'Failed to update Version and History: {0}'.format(str(ioe))
            self._print_warning(msg)

    def _update_cmd_arg_log(self):
        """
        Update cmd_arg.log file
        :return: None
        """
        # For the command-args-log only,
        # masquerade as the [standard] upgrade script
        cmd_str = './upgrade [rh7_upgrade_enm.sh]'
        if self.cmd_args:
            cmd_str += ' ' + ' '.join(self.cmd_args[1:])
        cmd_str += '\n'

        cmd_log = os.path.join(Rh7EnmUpgrade.ENM_INST_DIR,
                               'log', 'cmd_arg.log')
        self.log.debug('Updating {0}'.format(cmd_log))
        try:
            with open(cmd_log, 'a') as lfile:
                lfile.write(cmd_str)
        except IOError as ioe:
            msg = 'Failed to update {0}: {0}'.format(cmd_log, str(ioe))
            self._print_warning(msg)

    def execute_ddp_log(self, text):
        """
        For DDP and ADU, this text must be logged by a method
        with a name beginning with execute_
        :param text: Text to log
        :type text: string
        """
        self.log.info(text)

    def _post_upgrd(self):
        """
        Stage: run Post-Upgrade steps
        :return: None
        """

        self._print_stage_start()
        Rh7EnmUpgrade._clean_yum_repos()
        self._switch_db_grps()
        self._remove_files()
        self._run_procedures()
        self._update_logs()

        msg = 'Ran Post-Upgrade steps'
        self._print_stage_success(msg)

        self.execute_ddp_log('System successfully upgraded')

    # ---- Stage handlers end ----

    def _create_backup_data(self):
        """
        Create backup data:
        1. Node .pem (cert) files
        2. Keyring
        3. Password shadow
        4. Deployment description XML
        5. MCO MS and Node list
        :return: None
        """

        def  _verify_files_exist(mfiles):
            """
            Verify mandatory files exist as non-zero bytes
            :param mfiles: list of file paths to verify
            :type mfiles: list
            :return: None
            """
            for mfile in mfiles:
                if not os.path.exists(mfile) or (0 == os.path.getsize(mfile)):
                    msg = '{0} not found or size 0 bytes'.format(mfile)
                    self._print_error(msg)
                    sys.exit(0)

        self._assert_rhel_version('6.10')

        # Mandatory backup files - static
        man_bk_files = [Rh7EnmUpgrade.ENM_DD,
                     '/etc/mcollective/server_public.pem',
                     '/etc/mcollective/server_private.pem',
                     os.path.join(Rh7EnmUpgrade.NMS_LITP, 'keyset', 'keyset1'),
                     os.path.join(Rh7EnmUpgrade.LITP_ETC_DIR, 'litp_shadow'),
                     '/root/.ssh/vm_private_key',
                     '/root/.ssh/vm_private_key.pub',
                     ENM_VERSION_FILENAME]
        _verify_files_exist(man_bk_files)

        esmon_bkup = self._get_backup_esmon_data()
        litp_bkup = self._get_backup_litp_state()
        self._export_litp_model('/', Rh7EnmUpgrade.EXPORTED_ENM_FROM_STATE_DD)
        self._create_mco_peer_list_backup()
        copy_file(Rh7EnmUpgrade.ENM_DD,
                                  Rh7EnmUpgrade.ENM_PREVIOUS_DD)

        # Mandatory backup files - dynamic
        extra_man_bk_files = [Rh7EnmUpgrade.EXPORTED_ENM_FROM_STATE_DD,
                              Rh7EnmUpgrade.ENM_PREVIOUS_DD,
                              litp_bkup, esmon_bkup,
                              Rh7EnmUpgrade.MCO_LIST_BACKUP]

        _verify_files_exist(extra_man_bk_files)
        man_bk_files.extend(extra_man_bk_files)

        # Optional backup files
        secure_cli_base = os.path.join(os.sep, 'root', 'SecuredCLI')
        opt_bk_files = [ENM_HISTORY_FILENAME,
                        os.path.join(Rh7EnmUpgrade.ENM_INST_DIR,
                                     'log', 'cmd_arg.log'),
                        secure_cli_base + 'SecurityFile.xml',
                        secure_cli_base + 'XMLEncrypted.key']

        enminst_log = os.path.join(os.sep, 'var', 'log', 'enminst.log')
        elogs = [elog for elog in glob.glob(enminst_log + '*')
                 if not elog.endswith('.rhel6')]
        for elog in elogs:
            elog_rh6 = elog + '.rhel6'
            if os.path.exists(elog_rh6):
                self._remove_file(elog_rh6)

            copy_file(elog, elog_rh6)
            opt_bk_files.append(elog_rh6)

        opt_bk_files.extend(self._get_elect_files())

        for ofile in opt_bk_files[:]:
            if not os.path.exists(ofile) or (0 == os.path.getsize(ofile)):
                msg = '{0} not found or size 0 bytes .. skipping'.format(ofile)
                self._print_message(msg)
                opt_bk_files.remove(ofile)

        # Mandatory backup directories
        man_bk_dirs = ['/var/lib/puppet/ssl/',
                       '/etc/puppetdb/ssl/',
                       '/etc/rabbitmq/ssl/',
                       '/opt/SentinelRMSSDK/licenses/',
                       '/var/spool/cron/']
        man_bk_dirs.extend(Rh7EnmUpgrade._get_yum_repo_bkup_dirs())

        # Optional backup directories
        opt_bk_dirs = []

        emc_path = '/root/.emc/'
        if os.path.exists(emc_path):
            opt_bk_dirs.append(emc_path)

        # Put them all together
        bkup_text = ('\n'.join(['F {0}'.format(f)
                                for f in man_bk_files + opt_bk_files]) + '\n' +
                     '\n'.join(['D {0}'.format(d)
                                for d in man_bk_dirs + opt_bk_dirs]) + '\n')

        filename = os.path.join(Rh7EnmUpgrade.ENM_RT_DIR,
                                'rh7_upgrade_data_backup_list.txt')
        self._write_to_file(filename, bkup_text)

        msg = 'Contract/manifest file {0} created'.format(filename)
        self._print_success(msg)

    @staticmethod
    def _get_yum_repo_bkup_dirs():
        """
        Get a list of yum repo subfolder absolute paths
        to be included in the set of directories to be backed up.
        :return: Directory paths to backup
        :rtype: list of strings
        """
        folders = Rh7EnmUpgrade._get_all_non_plugin_repo_paths()

        subfolders = ['images', 'vm_scripts']
        folders.extend(['{0}/{1}/'.format(
            Rh7EnmUpgrade.HTML_DIR, folder)
            for folder in subfolders])
        return folders

    def _remove_file(self, rfile):
        """
        Remove a file
        :param rfile: File absolute path, to be removed
        :type rfile: string
        :return: None
        """

        self._print_message('Removing file {0}'.format(rfile))
        try:
            os.remove(rfile)
        except (OSError, IOError) as ex:
            if 2 != ex.errno:
                self._print_error("Failed to remove file: {0}".format(rfile))
                raise

    def _write_to_file(self, filename, content, user=None, group=None):
        """
        Write content to (output) file. If setting the user and group then both
        need to be provided.
        :param filename: Path to the file
        :type filename: string
        :param content: Content to write in the file
        :type content: string
        :param user: The new user name
        :type user: string
        :param group: The new group name
        :type group: string
        :return: None
        """

        try:
            with open(filename, 'w') as ofile:
                ofile.write(content)

                if user and group:
                    self._chown_file(filename, user, group, ofile.fileno())

        except IOError:
            self._print_error("Could not write to file '{0}'"
                              .format(filename))
            sys.exit(1)

    def _chown_file(self, filename, user, group, fileno=0):
        """
        Change ownership on a file
        :param filename: Path to the file
        :type filename: string
        :param user: The user name
        :type user: string
        :param group: The group name
        :type group: string
        :param fileno: File number/descriptor
        :type fileno: int
        :return: None
        """

        def _chown_fd(self, fname, descriptor, user, group):
            """
            Change ownership on a file by file descriptor
            :param fname: Path to the file
            :type fname: string
            :param descriptor: File descriptor
            :type descriptor: int
            :param user: The user name
            :type user: string
            :param group: The group name
            :type group: string
            :return: None
            """
            try:
                os.fchown(descriptor,
                          getpwnam(user).pw_uid,
                          getgrnam(group).gr_gid)
            except KeyError:
                self._print_error('Could not set file ownership on {0}'
                                  .format(fname))
                sys.exit(1)

        if fileno:
            _chown_fd(self, filename, fileno, user, group)
        else:
            with open(filename, 'r') as file_handle:
                _chown_fd(self, filename, file_handle.fileno(), user, group)

    def _read_file(self, file_path, log_contents=False):
        """
        Read the contents of a file. Only for small files!
        :param file_path: Path to file
        :type file_path: string
        :param log_contents: should read contents be logged
        :type log_contents: bool
        :return: The contents of the file.
        :rtype: string
        """
        if not log_contents:
            self.log.debug("Reading file {0}".format(file_path))

        try:
            with open(file_path, 'r') as rfile:
                contents = rfile.read()
        except IOError:
            self._print_error("Could not read the file '{0}'"
                              .format(file_path))
            sys.exit(1)
        except Exception as s_err:
            self._print_error("Exception occurred: '{0}'".format(s_err))
            sys.exit(1)

        if log_contents:
            self.log.debug('Read file {0}: {1}'.format(file_path, contents))

        return contents

    def create_lockfile(self):
        """
        Create tracking file indicating that RHEL migration is in progress
        :return: None
        """
        self._write_to_file(MIGRATION_LOCK_FILE, '')
        self.log.info("Lockfile created: {0}".format(MIGRATION_LOCK_FILE))

    def _push_scripts(self):
        """
        Push service related scripts that are required for main.cf update.
        :return: None
        """
        pf_list = []
        if not self.litp:
            self.litp = LitpRestClient()

        nodes = self.litp.get_all_items_by_type('/deployments', 'node', [])

        neo4jbur_cs_vpath = os.path.join(os.sep, 'deployments', 'enm',
                                         'clusters', 'db_cluster', 'services',
                                         'sg_neo4jbur_clustered_service')
        if self.litp.exists(neo4jbur_cs_vpath):
            neo4jbur_cs = self.litp.get(neo4jbur_cs_vpath)

            node_ids = neo4jbur_cs['properties']['node_list'].split(',')
            hostnames = [node['data']['properties']['hostname']
                         for node in nodes
                         if node['data']['id'] in node_ids]
            self.log.debug('Neo4j hosts: {0}'.format(','.join(hostnames)))

            neo4jbur_command_dst = os.path.join(os.sep, 'ericsson', '3pp',
                                'neo4j', 'dbscripts', 'neo4jbur_sg_service.sh')
            neo4jbur_command_src = os.path.join(Rh7EnmUpgrade.LITP_PUPPET_DIR,
                         'modules', 'neo4j', 'templates', 'neo4jbur_rhel7.erb')
            neo4jbur_consul_key = "enminst/neo4jbur_script"

            pf_list.append(Rh7EnmUpgrade.PushedFile(neo4jbur_command_src,
                                                    neo4jbur_command_dst,
                                                    hostnames,
                                                    neo4jbur_consul_key))

        vm_services = self.litp.get_all_items_by_type('/deployments',
                                    'reference-to-vm-service', [])
        all_node_ids = []
        for service in vm_services:
            node_ids = eval(service['data'][
                'properties']['node_hostname_map']).keys()
            all_node_ids += node_ids

        all_node_ids_set = set(all_node_ids)

        hostnames = [node['data']['properties']['hostname']
                     for node in nodes
                     if node['data']['id'] in all_node_ids_set]

        vcs_lsb_vm_status_consul_key = "enminst/vcs_lsb_vm_status_script"

        vcs_lsb_vm_status_command_dst = os.path.join(os.sep, 'usr', 'share',
                                                   'litp', 'vcs_lsb_vm_status')
        vcs_lsb_vm_status_command_src = os.path.join(
                                      Rh7EnmUpgrade.LITP_PUPPET_DIR, 'modules',
                                      'vcs', 'files', 'vcs_lsb_vm_status')

        pf_list.append(Rh7EnmUpgrade.PushedFile(vcs_lsb_vm_status_command_src,
                                                vcs_lsb_vm_status_command_dst,
                                                hostnames,
                                                vcs_lsb_vm_status_consul_key))

        vm_utils_command_dst = os.path.join(os.sep, 'usr', 'share',
                                            'litp_libvirt', 'vm_utils')
        vm_utils_command_src = os.path.join(Rh7EnmUpgrade.LITP_PUPPET_DIR,
                                    'modules', 'libvirt', 'files', 'vm_utils')

        vm_utils_consul_key = "enminst/vm_utils_script"

        pf_list.append(Rh7EnmUpgrade.PushedFile(vm_utils_command_src,
                                                vm_utils_command_dst,
                                                hostnames,
                                                vm_utils_consul_key))

        for pushed_file in pf_list:
            self._push_file(pushed_file)

    def _push_file(self, push_file):
        """
        Push the files to the required peer nodes
        :param push_file: PushedFile Object
        :type push_file: PushedFile Object
        :return: None
        """
        self.log.debug('Pushing file {0} to {1}'.format(push_file.src,
                                                        push_file.node_list))

        contents = standard_b64encode(self._read_file(push_file.src))

        self.log.debug('Creating consul key {0}'.format(push_file.consul_key))
        self._do_consul_action('put', push_file.consul_key, contents)

        url = 'consul_url=http://ms-1:8500/v1/kv/{0}'.format(
                                                          push_file.consul_key)
        cmd = "mco rpc filemanager pull_file '{0}' 'file_path={1}'".format(
                                    url, push_file.dest)

        for hostname in push_file.node_list:
            cmd += " -I {0} ".format(hostname)

        return_code, stdout = self._run_command(cmd,
                                       timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
        self._assert_return_code(return_code, cmd + ':' + stdout)

        self._do_consul_action('delete', push_file.consul_key)
        self.log.debug('Deleted consul key {0}'.format(push_file.consul_key))


def main(args):
    """
    Main function
    :return: None
    """
    upgrader = Rh7EnmUpgrade(args)
    upgrader.create_arg_parser()
    upgrader.processed_args = upgrader.parser.parse_args(args[1:])
    upgrader.set_verbosity_level()
    upgrader.log.debug('{0} called with: {1}'.format(args[0], args[1:]))
    upgrader.process_action()


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
