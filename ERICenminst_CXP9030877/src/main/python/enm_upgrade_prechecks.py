# pylint: disable=C0302
"""
Check and apply ENM pre-requisites
"""
##############################################################################
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################

import re
import sys
import textwrap
import subprocess
import os
import time
import random
import grp
import pwd
import ConfigParser
import requests

from argparse import ArgumentParser, RawTextHelpFormatter

from h_litp.litp_utils import main_exceptions
from h_litp.litp_rest_client import LitpRestClient
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_puppet.mco_agents import EnmPreCheckAgent, McoAgentException
from h_puppet.mco_agents import EnminstAgent
from h_puppet.h_puppet import puppet_trigger_wait
from h_util.h_utils import Translator, ExitCodes, exec_process, Sed, \
                           _exec_curl_command, get_edp_generated_sed, \
                           is_env_on_rack, get_nas_type
from h_vcs.vcs_utils import is_dps_using_neo4j
from h_vcs.vcs_utils import report_tab_data
from enm_grub_cfg_check import GrubConfCheck
from h_hc.hc_san import SanHealthChecks
from san_fault_check import SanFaultCheck
from clean_san_luns import SanCleanup


class EnmPreChecks(object):  # pylint: disable=R0904
                             # pylint: disable=R0902
    """
    Class to perform ENM upgrade pre checks
    """

    PARAM_VERBOSE = 'verbose'
    PARAM_ALL = 'upgrade_prerequisites_check'
    PARAM_ASSUMEYES = 'assumeyes'
    PARAM_ACTION = 'action'

    ACTION_CHOICES = ['storage_setup_check',
                      'san_alert_check',
                      'check_lvm_conf_non_db_nodes',
                      'check_grub_cfg_lvs',
                      'litp_model_synchronized_check',
                      'elastic_search_status_check',
                      'opendj_replication_check',
                      'unmount_iso_image_check',
                      'remove_packages',
                      'apply_puppet_timeouts',
                      'check_fallback_status',
                      'remove_seed_file_after_check',
                      'check_https_port_ilo_available',
                      'deactivate_ombs_backup',
                      'restart_puppet_services',
                      PARAM_ALL]

    AFFIRMATIVE = True
    VCS_TOOL = '/opt/ericsson/enminst/bin/vcs.bsh'
    CLUSTER_TYPE = 'db_cluster'
    NON_DB_CLUSTER_TYPES = ['svc_cluster', 'evt_cluster', 'scp_cluster']
    DEVICE_PATH = 'r|^/dev/sd.*|'
    LVM_CONF = '/etc/lvm/lvm.conf'
    BOS_CONF = '/opt/ericsson/itpf/bur/etc/bos.conf'
    FALLBACK_SED = '/ericsson/tor/data/fallback/fallback.sed'
    PING_TIMEOUT = 600
    LITP_TIMEOUT = 3600
    CMD_TIMEOUT = 300
    VIRTUAL_PROVIDERS = ['vmware', 'virtualbox', 'kvm', 'qemu', 'red hat']
    CXP_NO = 'ERICenminst_CXP9030877'
    BUR_USER = 'brsadm'    # BackUp and Restore user
    BUR_GROUP = 'brsadm'
    PACKAGES_FOR_REMOVAL = ["perl-Compress-Raw-Zlib"]

    RUN_INTERVAL_VALUE = '1800'
    CONFIG_TIMEOUT_VALUE = '1720'
    PUPPET_LOCK_TIMEOUT_VALUE = '1980'
    MAX_ITERATIONS_VALUE = '1000'
    SEARCH_PATTERN = r"{0}\s*=\s*([0-9]+)"
    REPLACE_PATTERN = r"({0}\s*=\s*)[0-9]+"
    MANIFEST_SEARCH_PATTERN = r"setting => '{0}',\s*value\s*=>\s*('[0-9]+')"
    MANIFEST_REPLACE_PATTERN = r"(setting => '{0}',\s*value\s*=>\s*)'[0-9]+'"
    MAX_ITERATIONS_SEARCH_PATTERN = \
        r"def __init__\(self, max_iterations=([0-9]+)"
    MAX_ITERATIONS_REPLACE_PATTERN = \
        r"(def __init__\(self, max_iterations=)[0-9]+"

    DP_ENM_ISO_VERSION_CUTOFF = '2.19.117'
    DP_ENM_VERSION_PATH = '/etc/enm-version'
    DP_SEED_CONF_FILE_PATH = '/ericsson/tor/data/domainProxy/seed.conf'
    SYSTEMCTL = '/usr/bin/systemctl'

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
            self._wait_for = seconds
            self._start_time = EnmPreChecks.Timeout.time()

        @staticmethod
        def time():
            """
            Get the current time
            :return: The current time
            :rtype: int
            """
            return time.time()

        @staticmethod
        def sleep(seconds):
            """
            Sleep for a fixed time
            :param seconds: sleep interval
            :type seconds: int
            :return: None
            """
            time.sleep(seconds)

        def has_elapsed(self):
            """
            Check if the maximum Timeout time has elapsed
            :return: Boolean True if Timeout seconds have elapsed
            """
            return self.get_elapsed_time() >= self._wait_for

        def get_elapsed_time(self):
            """
            Get the time difference between now and start of Timeout
            :return: Time difference
            :rtype: int
            """
            return int(EnmPreChecks.Timeout.time() - self._start_time)

        def get_remaining_time(self):
            """
            Get the time remaining in this Timeout
            :return: Time remaining
            :rtype: int
            """
            return int(self._wait_for - self.get_elapsed_time())

    class DbService(object):
        """
        Class for parsed DB service data
        """
        tokens = ['group', 'system', 'ha_type',
                  'svc_type', 'svc_state', 'grp_state']

        def __init__(self):
            """
            Initialize a new DB service instance
            :return: None
            """
            self.group = ''
            self.system = ''
            self.ha_type = ''
            self.svc_type = ''
            self.svc_state = ''
            self.grp_state = ''

        def __repr__(self):
            """
            Create a printable representation of this DbService object
            :return: String representation of object
            :rtype: string
            """
            return ("%s Group:%s System:%s HAType:%s " + \
                    "SvcType:%s SvcState:%s GrpState:%s") % \
                   (self.__class__.__name__, self.group, self.system,
                    self.ha_type, self.svc_type,
                    self.svc_state, self.grp_state)

        def is_valid(self):
            """
            Determine if DB service state is valid
            :return: Boolean True if group-state is ok, False otherwise
            """
            return self.grp_state == 'OK'

        @staticmethod
        def get_regexp_pattern(cluster_type, clustered_service, system):
            """
            Get regular expression pattern used to parse a DbNode
            from one VCS command.
            :param cluster_type: Cluster type
            :type cluster_type: string
            :param clustered_service: Clustered service name
            :type clustered_service: string
            :param system: system name
            :type system: string
            :return: regexp string
            :rtype: string
            """
            return (r'^\s*%s\s+' +
                    r'(?P<%s>%s)\s+' +
                    r'(?P<%s>%s)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'.*$') % \
                    (cluster_type,
                     EnmPreChecks.DbService.tokens[0], clustered_service,
                     EnmPreChecks.DbService.tokens[1], system,
                     EnmPreChecks.DbService.tokens[2],
                     EnmPreChecks.DbService.tokens[3],
                     EnmPreChecks.DbService.tokens[4],
                     EnmPreChecks.DbService.tokens[5])

    class DbNode(object):
        """
        Class for parsed DB node data
        """
        tokens = ['system', 'ha_type', 'svc_type', 'svc_state']

        def __init__(self):
            """
            Initialize a new DB node instance
            :return: None
            """
            self.system = ''
            self.ha_type = ''
            self.svc_type = ''
            self.svc_state = ''

        def __repr__(self):
            """
            Create a printable representation of this DbNode object
            :return: String representation of object
            :rtype: string
            """
            return "%s System:%s State:%s" % \
                   (self.__class__.__name__, self.system, self.svc_state)

        def is_online(self):
            """
            Determine if DB node state is online
            :return: Boolean True if state is online, False otherwise
            """
            return self.svc_state == 'ONLINE'

        @staticmethod
        def get_regexp_pattern(cluster_type, clustered_service):
            """
            Get regular expression pattern used to parse a DbNode
            from one VCS command.
            :param cluster_type: Cluster type
            :type cluster_type: string
            :param clustered_service: Clustered service name
            :type clustered_service: string
            :return: regexp string
            :rtype: string
            """
            return (r'^\s*%s\s+' +
                    r'%s\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'.*$') % \
                    (cluster_type, clustered_service,
                     EnmPreChecks.DbNode.tokens[0],
                     EnmPreChecks.DbNode.tokens[1],
                     EnmPreChecks.DbNode.tokens[2],
                     EnmPreChecks.DbNode.tokens[3])

    class ReplNode(object):
        """
        Class for parsed Replication node data
        """

        tokens = ['server', 'entries', 'enabled',
                  'ds_id', 'rs_id', 'rs_port', 'mc_count']

        def __init__(self):
            """
            Initialize a new Repl node instance
            :return: None
            """
            self.server = ''
            self.entries = ''
            self.enabled = 'false'
            self.ds_id = ''
            self.rs_id = ''
            self.rs_port = ''
            self.mc_count = '0'

        def is_enabled(self):
            """
            Determine if ReplNode enabled value is 'true'
            :return: Boolean True if enabled is 'true', False otherwise
            """
            return self.enabled == 'true'

        def __repr__(self):
            """
            Create a printable representation of a ReplNode
            :return: String representation of object
            :rtype: string
            """
            return "{%s Server:%s Entries:%s Enabled:%s DS:%s RS:%s MC:%s}" % \
                    (self.__class__.__name__,
                     self.server, self.entries, self.enabled,
                     self.ds_id, self.rs_id, self.mc_count)

        @staticmethod
        def get_regexp_pattern(ldap_root):
            """
            Get regular expression pattern to parse a ReplNode
            from dsreplication output.
            :param ldap_root: LDAP-root
            :type ldap_root: string
            :return: regexp string
            :rtype: string
            """
            return (r'^%s\s+:\s+' +
                    r'(?P<%s>[^\s]+):4444\s+:\s+' +
                    r'(?P<%s>[0-9]+)\s+:\s+' +
                    r'(?P<%s>[^\s]+)\s+:\s+' +
                    r'(?P<%s>[0-9]+)\s+:\s+' +
                    r'(?P<%s>[0-9]+)\s+:\s+' +
                    r'(?P<%s>[0-9]+)\s+:\s+' +
                    r'(?P<%s>[0-9]+)\s+:' +
                    r'.*$') % \
                    (ldap_root,
                     EnmPreChecks.ReplNode.tokens[0],
                     EnmPreChecks.ReplNode.tokens[1],
                     EnmPreChecks.ReplNode.tokens[2],
                     EnmPreChecks.ReplNode.tokens[3],
                     EnmPreChecks.ReplNode.tokens[4],
                     EnmPreChecks.ReplNode.tokens[5],
                     EnmPreChecks.ReplNode.tokens[6])

    class System(object):
        """
        Class for parsed Node data
        """

        tokens = ['name', 'state', 'cluster']

        def __init__(self):
            """
            Initialize a new System instance
            :return: None
            """
            self.name = ''
            self.state = ''
            self.cluster = ''

        def __repr__(self):
            """
            Create a printable representation of this System object
            :return: String representation of object
            :rtype: string
            """
            return "%s Name:%s State:%s Cluster:%s" % \
                   (self.__class__.__name__, self.name,
                    self.state, self.cluster)

        def is_running(self):
            """
            Determine if System is running
            :return: Boolean True if state is 'RUNNING', False otherwise
            """
            return self.state == 'RUNNING'

        @staticmethod
        def get_regexp_pattern(cluster_type):
            """
            Get regular expression pattern to parse a System
            vcs.bsh output.
            :param cluster_type: (eg - db_cluster)
            :type ldap_root: string
            :return: regexp string
            :rtype: string
            """
            return (r'^\s*(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>[^\s]+)\s+' +
                    r'(?P<%s>%s)\s+' +
                    r'.*$') % \
                    (EnmPreChecks.System.tokens[0],
                     EnmPreChecks.System.tokens[1],
                     EnmPreChecks.System.tokens[2], cluster_type)

    def __init__(self):
        """
        Initialise an EnmPreChecks instance
        """
        self.log = init_enminst_logging('enm_prechecks')
        self.processed_args = None
        self.parser = None
        self.global_properties = {}
        self.mco_agent = EnmPreCheckAgent(timeout=EnmPreChecks.CMD_TIMEOUT)
        self.enminst_agent = EnminstAgent()
        self.current_action = ''
        self.indent = ' '
        self._ = Translator(EnmPreChecks.CXP_NO)._
        # pylint: disable=W0212
        # pylint: disable=C0103
        self._u = Translator(EnmPreChecks.CXP_NO)._u

    def set_verbosity_level(self):
        """
        Set the logging verbosity level based on the 'verbose' parameter
        :return: None
        """

        if getattr(self.processed_args, EnmPreChecks.PARAM_VERBOSE, False):
            set_logging_level(self.log, 'DEBUG')

    def print_action_heading(self, text, print_heading_with_appendages=True):
        """
        Print a bolded heading
        :param text: Text to print
        :type text: string
        :param print_heading_with_appendages: add the prefix and suffix
                                              to the heading text
        :type print_heading_with_appendages: boolean
        :return: None
        """

        if print_heading_with_appendages:
            all_text = "({0}) {1} ...".format(self.current_action, text)
        else:
            all_text = text

        hyphen_line = '-' * len(all_text)
        self.log.info(hyphen_line)
        self.log.info(all_text)
        self.log.info(hyphen_line)

    def print_success(self, text):
        """
        Print a green success line
        :param text: Text to print
        :type text: string
        :return: None
        """
        all_text = "***** PASSED: %s *****" % text
        self.log.info(self.indent + all_text)

    def print_error(self, text, add_suffix=True):
        """
        Print a red error line
        :param text: Text to print
        :type text: string
        :param add_suffix: should the standard suffix be appended
        :type add_suffix: boolean
        :return: None
        """

        if add_suffix:
            suffix = (' Do not proceed with the upgrade. ' + \
                      'For more information, contact your local ' + \
                      'Ericsson support team.')
            all_text = "***** FAILED: %s %s *****" % (text, suffix)
        else:
            all_text = "***** FAILED: %s *****" % text

        self.log.error(self.indent + all_text)

    def print_message(self, text):
        """
        Print a simple message
        :param text: Text to print
        :type text: string
        :return: None
        """
        self.log.info(self.indent + text)

    def assert_return_code(self, return_code, text, allowed_codes=None):
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
            msg = self._('FAILED_TO_RUN_COMMAND').format(text)
            self.print_error(msg)
            sys.exit(1)

    def log_mco_action(self, action_key, system, **kwargs):
        """
        Method to log MCO agent::action details
        :param action_key: MCO action key/name
        :type action_key: string
        :param system: system/host name
        :type system: string
        :param kwargs: keyword arguments to action
        :type kwargs: dict
        :return: None
        """

        if not getattr(self.processed_args, EnmPreChecks.PARAM_VERBOSE, False):
            return

        action_map = {'get_replication_status': 'dsreplication_status'}

        action_name = action_key
        if action_key in action_map.keys():
            action_name = action_map[action_key]

        args = ''
        if kwargs:
            args = ' '.join(['%s="%s"' % (i, kwargs[i]) for i in kwargs])

        text = ("Running mco agent::action like:  mco rpc -I %s enminst %s %s"
                % (system, action_name, args))
        self.log.debug(text)

    def run_command(self, command, timeout_secs=CMD_TIMEOUT, do_logging=True):
        """
        Thin wrapper to call subprocess.Popen
        :param command: Command string to execute
        :type command: string
        :param timeout_secs: seconds to wait before timing out command
        :type timeout_secs: integer
        :param do_logging: Boolean, default True, indiciating if
                           logging should be performed
        :type do_logging: boolean
        :return: returncode, STDOUT text
        :rtype: 2-type: int, string
        """

        if do_logging:
            self.log.debug("Will run command: %s" % command)

        stdout = ''
        process = None

        command_to_log = command if do_logging else '<hidden>'
        timeout = EnmPreChecks.Timeout(timeout_secs)

        try:
            process = subprocess.Popen(command,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       shell=True)
        except OSError as oe_err:
            msg = self._('ERROR_PROCESSING_COMMAND').format(command_to_log,
                                               oe_err.errno, oe_err.strerror)
            self.print_error(msg)
            sys.exit(1)

        while process.poll() is None and not timeout.has_elapsed():
            timeout.sleep(0.5)

        if process.poll() is None and timeout.has_elapsed():
            msg = self._('TIMEOUT_OUT_COMMAND').format(command_to_log)
            self.print_error(msg)
            sys.exit(1)

        stdout, _ = process.communicate()
        cleaned_stdout = stdout.strip()

        if do_logging:
            self.log.debug('Return code: %d Output: "%s"' %
                           (process.returncode, cleaned_stdout))

        return process.returncode, cleaned_stdout

    def check_litp_model_synchronized(self):
        """
        Action handler to check if there are unapplied LITP model changes.
        :return: None
        """
        msg = self._u('CHECKING_MODEL_SYCHRONIZED_WITH_DEPLOYMENT')
        self.print_action_heading(msg)

        if self.is_virtual_environment():
            return

        return_code, stdout = self.run_command('litp create_plan',
                                    timeout_secs=EnmPreChecks.LITP_TIMEOUT)

        if "DoNothingPlanError" not in stdout:
            self.assert_return_code(return_code,
                                    'LITP model synchronization check')

        if return_code == 1 and "DoNothingPlanError" in stdout:
            msg = self._('MODEL_SYNCHRONIZED')
            self.print_success(msg)
        else:
            msg = self._('MODEL_NOT_SYNCHRONIZED')
            self.print_error(msg)
            sys.exit(1)

    def check_https_port_ilo_available(self):
        """
        Checks if the HTTPS port is available on the iLO for REST requests
        :return: None
        """

        regex = '.*_ilo_IP'
        substr = '_ilo_IP'
        ilo_available = True
        msg = self._u('CHECKING_HTTPS_PORT_iLO_AVAILABLE')
        self.print_action_heading(msg)
        # -k ignore insecure certificate
        curl_binary = '/usr/bin/curl -k'
        success_message = 'iLO HTTPS Success for Node "{0}"'
        failure_message = 'iLO HTTPS check Failed! No response from iLO IP '\
                          'address "{0}" - Node "{1}". The iLO '\
                          'must be configured to listen on and allow '\
                          'requests on HTTPS (443) Port.'

        # get EDP generated SED from /tmp
        ilo_ipaddrs = get_edp_generated_sed(regex)
        if not ilo_ipaddrs:
            msg = 'No iLO IP addresses found, skipping HTTPS check...'
            self.print_message(msg)
            return

        for node_name, ilo_ip in ilo_ipaddrs.iteritems():
            response = _exec_curl_command(
                '{0} https://{1}'.format(curl_binary, ilo_ip),
                hide_output=True
            )
            if response == 0:
                msg = success_message.format(node_name.split(substr)[0])
                self.print_success(msg)
            else:
                msg = failure_message.format(
                    ilo_ip, node_name.split(substr)[0]
                )
                self.print_error(msg)
                ilo_available = False

        if not ilo_available:
            msg = self._('HTTPS PORT UNAVAILABLE ON iLO')
            self.print_error(msg)
            sys.exit(1)

    def is_virtual_environment(self):
        """
        Check if runtime environment is a Virtual Environment.
        :return: True if provider is a Virtual provider, False otherwise.
        :rtype: boolean
        """

        command = '/usr/sbin/dmidecode -s system-manufacturer'
        return_code, response = self.run_command(command)

        self.assert_return_code(return_code, 'manufacturer check')

        system_provider = response.strip().lower()

        if any(provider in system_provider
               for provider in EnmPreChecks.VIRTUAL_PROVIDERS):
            msg = self._('VIRTUAL_ENVIRONMENT_DETECTED').format(
                                                        self.current_action)
            self.print_message(msg)
            return True

        return False

    def prompt_user_boolean(self, prompt_text):
        """
        Prompt the user with a yes/no question
        :param prompt_text: Prompt text to present to User
        :type prompt_text: string
        :return: Boolean indicating +ive or -ive User input
        :rtype: boolean
        """

        self.log.debug("Prompting user: %s" % prompt_text)

        if getattr(self.processed_args, self.PARAM_ASSUMEYES, False):
            self.log.debug("Option -y|--assumeyes passed to the script. "
                           "Skipped asking for confirmation.")
            return EnmPreChecks.AFFIRMATIVE

        reply = None
        yes_word = 'YeS'
        no_char = 'n'
        valid_resposes = [yes_word, no_char]

        full_prompt_text = ' ' + prompt_text + \
                           ' [' + yes_word + '|' + no_char + ']: '

        while reply not in valid_resposes:
            reply = str(raw_input(full_prompt_text)).strip()

        if reply:
            self.log.debug("Reply to prompt: %s" % reply)
            if reply == yes_word:
                return EnmPreChecks.AFFIRMATIVE

        return False

    def get_mounts_on_mount_dir(self, mount_dir):
        """
        Get mounts mounted to a mount directory
        :param mount_dir: Mount directory
        :type mount_dir: string
        :return: Nothing if no mounts, a list of matching mounts otherwise
        :rtype: None or list
        """

        return_code, output = self.run_command('/bin/mount')
        self.assert_return_code(return_code, 'mount')

        if not output:
            return

        output_lines = [line.strip() for line in output.splitlines()]

        search_string1 = " on %s/.+ " % mount_dir
        nested_mounts = [line for line in output_lines
                         if re.search(search_string1, line)]

        if nested_mounts:
            msg = self._('NESTED_MOUNTS_FOUND').format(mount_dir)
            self.print_error(msg)
            sys.exit(1)

        search_string2 = " on %s " % mount_dir
        return [line for line in output_lines if search_string2 in line]

    def unmount_iso_image(self):
        """
        Action handler to unmount ISO image
        :return: None
        """

        mount_dir = '/mnt'

        msg = self._u('CHECKING_FOR_MOUNTED_IMAGE').format(mount_dir)
        self.print_action_heading(msg)

        matching_mounts1 = self.get_mounts_on_mount_dir(mount_dir)

        if not matching_mounts1:
            msg = self._('MOUNT_DIRECTORY_NOT_USED').format(mount_dir)
            self.print_success(msg)
            self.assert_mount_dir_empty(mount_dir)
        else:
            msg = self._('MOUNT_DIRECTORY_IS_USED').format(mount_dir)
            user_reply = self.prompt_user_boolean(msg)

            if user_reply is EnmPreChecks.AFFIRMATIVE:
                mount_count = len(matching_mounts1)
                self.log.info("Positive User response, unmounting the "
                              "%d %s mount(s) ..." % (mount_count, mount_dir))
                command2 = "/bin/umount %s" % mount_dir
                while mount_count:
                    return_code, _ = self.run_command(command2)
                    mount_count -= 1
                    self.assert_return_code(return_code, 'umount check')

                matching_mounts2 = self.get_mounts_on_mount_dir(mount_dir)

                if not matching_mounts2:
                    msg = self._('SUCCESSFULLY_UNMOUNTED').format(
                                                        mount_dir)
                    self.print_success(msg)
                    self.assert_mount_dir_empty(mount_dir)
                else:
                    msg = self._('MOUNT_DIRECTORY_IS_BUSY').format(
                                                        mount_dir)
                    self.print_error(msg)
                    sys.exit(1)
            else:
                msg = self._('UNMOUNT_MANUALLY').format(self.current_action)
                self.print_message(msg)

    @staticmethod
    def _replace_puppet_timeout_values(file_path, match_pattern,
                                       replacement_pattern, new_value):
        """
        A utility to replace timeout values related to TORF-317429
        :param file_path: file to be modified
        :type file_path: string
        :param match_pattern: regex pattern to search for
        :type match_pattern: string
        :param replacement_pattern: regex pattern to be used for replacement
        :type replacement_pattern: string
        :param new_value: the new value in case the old one is smaller
        :type new_value: string
        :return: True if a replacement happened, otherwise False
        :rtype: bool
        """
        values_changed = False
        with open(file_path) as file_handle:
            contents = file_handle.read()

            matches = re.search(
                match_pattern,
                contents, re.MULTILINE)

            if matches is not None and \
                    int(matches.group(1).replace("'", "")) <\
                    int(new_value.replace("'", "")):
                contents = re.sub(replacement_pattern, r"\g<1>" +
                                  new_value, contents, 1)
                values_changed = True

        with open(file_path, 'w') as file_handle:
            file_handle.write(contents)

        return values_changed

    def apply_puppet_timeouts(self):
        """
        Apply longer puppet timeouts in case of old low values from older
        versions. See TORF-317429.
        :return: None
        """
        msg = self._('CHECKING IF PUPPET TIMEOUT VALUES ARE LONG ENOUGH')
        self.print_action_heading(msg)
        values_changed = EnmPreChecks._replace_puppet_timeout_values(
            '/etc/puppet/puppet.conf',
            self.SEARCH_PATTERN.format('runinterval'),
            self.REPLACE_PATTERN.format('runinterval'),
            self.RUN_INTERVAL_VALUE
        )

        values_changed = EnmPreChecks._replace_puppet_timeout_values(
            '/etc/puppet/puppet.conf',
            self.SEARCH_PATTERN.format('configtimeout'),
            self.REPLACE_PATTERN.format('configtimeout'),
            self.CONFIG_TIMEOUT_VALUE
        ) or values_changed

        values_changed = EnmPreChecks._replace_puppet_timeout_values(
            '/opt/ericsson/nms/litp/etc/puppet/modules/litp/manifests/'
            'litp_puppet_conf.pp',
            self.MANIFEST_SEARCH_PATTERN.format('runinterval'),
            self.MANIFEST_REPLACE_PATTERN.format('runinterval'),
            "'" + self.RUN_INTERVAL_VALUE + "'"
        ) or values_changed

        values_changed = EnmPreChecks._replace_puppet_timeout_values(
            '/opt/ericsson/nms/litp/etc/puppet/modules/litp/manifests/'
            'litp_puppet_conf.pp',
            self.MANIFEST_SEARCH_PATTERN.format('configtimeout'),
            self.MANIFEST_REPLACE_PATTERN.format('configtimeout'),
            "'" + self.CONFIG_TIMEOUT_VALUE + "'"
        ) or values_changed

        values_changed = EnmPreChecks._replace_puppet_timeout_values(
            '/opt/ericsson/nms/litp/lib/litp/core/puppet_manager.py',
            self.SEARCH_PATTERN.format('PUPPET_LOCK_TIMEOUT'),
            self.REPLACE_PATTERN.format('PUPPET_LOCK_TIMEOUT'),
            self.PUPPET_LOCK_TIMEOUT_VALUE
        ) or values_changed

        values_changed = EnmPreChecks._replace_puppet_timeout_values(
            '/opt/ericsson/nms/litp/lib/litp/core/rpc_commands.py',
            self.MAX_ITERATIONS_SEARCH_PATTERN,
            self.MAX_ITERATIONS_REPLACE_PATTERN,
            self.MAX_ITERATIONS_VALUE
        ) or values_changed

        if values_changed:
            msg = self._('A timeout value has been changed. '
                         'The puppet sync command will be run. '
                         'This can take several minutes per node to complete.')
            self.print_message(msg)
            exec_process('service litpd restart',
                             use_shell=True)
            try:
                exec_process('/opt/ericsson/enminst/bin/puppet.bsh --sync',
                             use_shell=True)
            except IOError:
                msg = self._("Retrying puppet.bsh --sync")
                self.print_message(msg)
                exec_process('/opt/ericsson/enminst/bin/puppet.bsh --sync',
                             use_shell=True)

        msg = self._('Puppet timeout checks have completed')
        self.print_success(msg)

    def remove_packages(self):
        """
        Removes PACKAGES_FOR_REMOVAL if they are installed on the MS
        or any peer nodes. See TORF-311051.
        :return: None
        """
        for package in EnmPreChecks.PACKAGES_FOR_REMOVAL:
            msg = self._('REMOVING %s' % package.upper())
            self.print_action_heading(msg)
            msg = self._('Removing %s if installed on Management '\
                         'Server' % package)
            self.print_message(msg)
            command = "yum remove -y %s" % package
            self.run_command(command)
            msg = self._('Removing %s if installed on Peer Nodes' % package)
            self.print_message(msg)
            nodes = self.get_nodes()
            for node in nodes:
                self.run_mco_agent_action('remove_packages', node, package)
            msg = self._('%s REMOVED' % package.upper())
            self.print_success(msg)

    def perform_service_action(self, services, action):
        """
        Perform a specified action on a list of services
        :param services: A list of  services
        :param action: The action to perform
        (start, stop, restart)
        :return: None
        """
        action_mappings = {
            "start": "Starting",
            "stop": "Stopping",
            "restart": "Restarting"
        }

        action_message = action_mappings.get(action)
        if not action_message:
            raise ValueError("Invalid action: {0}".format(action))

        for service in services:
            self.log.info('{0} Service {1}'.format(action_message, service))
            command = self.SYSTEMCTL + ' {0} {1}'.format(action, service)
            return_code, response = self.run_command(command)

            if return_code == 0:
                self.log.info('Service {0} {1} : successful'.
                              format(service, action))
            else:
                msg = '{0} service {1} : {2}'.\
                       format(action_message, service, response)
                self.print_error(msg, add_suffix=False)
                sys.exit(1)

    def restart_puppet_services(self):
        """
        Restart the Puppet components to guarantee
        a stable operation during the upgrade
        :return: None
        """
        msg = self._('RESTARTING PUPPET SERVICES')
        self.print_action_heading(msg)

        # Check if litp plan is running
        self.log.info('Checking if litp plan is running')
        litp = LitpRestClient()
        if litp.is_plan_running('plan'):
            msg = self._('A plan is currently running, wait for it to '
                         'complete before restarting puppet services.')
            self.print_error(msg, add_suffix=False)
            sys.exit(1)
        self.log.info('No running litp plan found')

        # Check for running catalogs
        self.log.info('Waiting for ongoing catalog runs to complete')
        puppet_trigger_wait(False, self.log.debug)
        self.log.info('Catalog runs have completed')

        # Restart puppet components
        monitor_services = ['puppetdb_monitor', 'puppetserver_monitor']
        puppet_services = ['puppetdb', 'puppetserver']
        self.perform_service_action(monitor_services, "stop")
        self.perform_service_action(puppet_services, "restart")
        self.perform_service_action(monitor_services, "start")
        msg = self._('RESTARTING OF PUPPET SERVICES WAS SUCCESSFUL')
        self.print_success(msg)

    def get_nodes(self):
        """
        Gets all the nodes in a deployment
        :return: nodes
        :rtype: list
        """
        nodes = []
        litp_rest_client = LitpRestClient()
        deployment_clusters = litp_rest_client.get_deployment_cluster_list()
        for cluster in deployment_clusters:
            nodes.extend(
                self.get_running_systems_by_cluster(cluster))
        return nodes

    def assert_mount_dir_empty(self, mount_dir):
        """
        Assert the mount directory is empty
        :param mount_dir: Mount directory path
        :type mount_dir: string
        :return: None
        """
        try:
            assert [] == os.listdir(mount_dir)
        except AssertionError:
            msg = self._('DIRECTORY_NOT_EMPTY').format(mount_dir)
            self.print_message(msg)

    def create_and_read_ombs_conf(self):
        """
        Create a Configuration Parser and read the BOS conf file
        :return: Config Parser object
        """
        self.log.debug('Reading configuration in "%s"' % EnmPreChecks.BOS_CONF)

        if not os.path.exists(EnmPreChecks.BOS_CONF):
            msg = self._('OMBS_CONF_ERROR').format(EnmPreChecks.BOS_CONF,
                                                   'File not found')
            self.print_error(msg)
            sys.exit(1)

        conf = ConfigParser.SafeConfigParser()
        conf.read(EnmPreChecks.BOS_CONF)
        return conf

    def ombs_lock_file_exists(self, lock_file):
        """
        Check if a lock file exists
        :param lock_file: Lock file path
        :return: True if lock file exists, False otherwise
        :rtype: boolean
        """
        self.log.debug('Checking for existence of lock file "%s"' % lock_file)
        return os.path.exists(str(lock_file))

    def seed_conf_file_exists(self, seed_conf_file):
        """
        Check if a seed_conf_file exists
        :param seed_conf_file: seed_conf_file path
        :return: True if seed_conf_file exists, False otherwise
        :rtype: boolean
        """
        self.log.debug('Checking for existence of seed_conf file '
                ' "%s"' % seed_conf_file)
        return os.path.exists(str(seed_conf_file))

    def deactivate_ombs_backup(self):
        """
        Action handler to deactivate OMBS backup
        :return: None
        """
        msg = self._u('DEACTIVATING_OMBS_BACKUP')
        self.print_action_heading(msg)

        bos_config = self.create_and_read_ombs_conf()

        section = 'precondition'
        param_name = 'system_backup_lock_file'

        try:
            lock_file = bos_config.get(section, param_name)
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as ex:
            msg = self._('OMBS_CONF_ERROR').format(EnmPreChecks.BOS_CONF,
                                                   str(ex))
            self.print_error(msg)
            sys.exit(1)

        if not lock_file:
            text = "Value missing for parameter '%s' in section '%s'" % \
                   (param_name, section)
            msg = self._('OMBS_CONF_ERROR').format(EnmPreChecks.BOS_CONF, text)
            self.print_error(msg)
            sys.exit(1)

        if self.ombs_lock_file_exists(lock_file):
            msg = self._('OMBS_BACKUP_IS_INACTIVE')
            self.print_success(msg)
        else:
            self.create_backup_lock_file(lock_file)

    def create_backup_lock_file(self, lock_file):
        """
        Create a lock file to deactivate OMBS Backup
        :param lock_file: path to lock file
        :type lock_file: string
        :return: None
        """
        try:
            with open(str(lock_file), "w") as file_handle:
                file_handle.write('Existence of this file prevents '
                                  'the ENM system backup\n')

                os.fchown(file_handle.fileno(),
                          pwd.getpwnam(EnmPreChecks.BUR_USER).pw_uid,
                          grp.getgrnam(EnmPreChecks.BUR_GROUP).gr_gid)

            self.log.debug('Successfully created %s' % lock_file)
            msg = self._('OMBS_BACKUP_DEACTIVATED')
            self.print_success(msg)
        except IOError as ex1:
            self.log.debug('Error while trying to write to %s. %s' %
                          (lock_file, str(ex1)))
            msg = self._('ERROR_WHILE_DEACTIVATING_OMBS_BACKUP')
            self.print_error(msg)
            sys.exit(1)
        except KeyError as ex2:
            self.log.debug('Error changing user and group ownership '
                           'on file %s: %s' % (lock_file, str(ex2)))
            msg = self._('OMBS_BACKUP_SET_OWNER_FAILED').format(lock_file)
            self.print_message(msg)

    @staticmethod
    def gen_cs_group_pattern(cluster_type, clustered_service):
        """
        Generate a clustered-service group name pattern
        :param cluster_type: cluster type name
        :type cluster_type: string
        :param clustered_service: clustered-service name
        :type clustered_service: string
        :return: clustered-service group name pattern
        :rtype: string
        """

        gname = r"Grp_CS_%s_" % cluster_type
        if clustered_service in ('neo4j', 'ALL'):
            gname += r'(sg_)?'

        if clustered_service == 'ALL':
            gname += r'[^\s]+'
        else:
            gname += clustered_service

        if clustered_service in ('modeldeployment', 'ALL'):
            gname += r'_cluster(ed)?'
        else:
            gname += r'_clustered'

        gname += r'_service'

        if clustered_service in ('modeldeployment', 'versant', 'ALL'):
            gname += r'(_1)?'

        return gname

    def run_mco_agent_action(self, action_key, system, *args, **kwargs):
        """
        Run the enminst MCO agent with a particular action
        :param action_key: MCO action key/name
        :type action_key: string
        :param system: system/host name
        :type system: string
        :param args: optional arguments to action handler
        :type args: list
        :param kargs: optional keyword arguments to this method
        :type kargs: dict
        :return: MCO agent action response
        :rtype: string
        """
        if 'mco_agent_object' in kwargs:
            mco_object = kwargs.get('mco_agent_object')
        else:
            mco_object = self.mco_agent

        action_handler = getattr(mco_object, action_key, None)

        if kwargs.get('do_logging', True):
            self.log_mco_action(action_key, system)
        if kwargs.get('mco_timeout'):
            self.mco_agent.timeout = kwargs.get('mco_timeout')
        try:
            return action_handler(system, *args)
        except McoAgentException as ex:
            exit_required = True
            action_data = ex.args[0]

            for error in kwargs.get('non_exit_errors', []):
                if action_data.get('retcode') == 1 and \
                        (action_data.get('out') == error
                         or action_data.get('err') == error):
                    exit_required = False
                    raise

            if exit_required:
                msg = self._('FAILED_TO_RUN_MCO_ACTION').format(
                                                    action_key, str(ex))
                self.print_error(msg)
                sys.exit(1)
        finally:
            self.mco_agent.timeout = self.CMD_TIMEOUT

    def check_opendj_replication(self):   # pylint: disable=R0915,R0914
        """
        Action handler to check OpenDJ
        :return: None
        """

        msg = self._u('CHECKING_OPENDJ_REPLICATION')
        self.print_action_heading(msg)

        if self.is_virtual_environment():
            return

        properties_file = '/ericsson/tor/data/global.properties'
        opendj_nodes = self.get_db_nodes_by_service('opendj')

        self.log.debug("VCS OpenDJ node data: %s" % opendj_nodes)

        if len(opendj_nodes) < 2 or \
           any(not node.is_online() for node in opendj_nodes):
            msg = self._('OPENDJ_NOT_ONLINE_ON_TWO_NODES')
            self.print_error(msg, add_suffix=False)
            sys.exit(1)

        cleartext_password = self.get_cleartext_password(properties_file)

        if not cleartext_password:
            msg = self._('OPENDJ_PASSWORD_CANNOT_BE_RETRIEVED').format(
                                                        properties_file)
            self.print_error(msg)
            sys.exit(1)

        ldap_root = self.get_ldap_root(properties_file)
        if not ldap_root:
            msg = self._('OPENDJ_LDAP_ROOT_CANNOT_BE_RETRIEVED').format(
                                                        properties_file)
            self.print_error(msg)
            sys.exit(1)

        a_db_node = opendj_nodes[random.randint(0, len(opendj_nodes) - 1)]

        self.log.debug('Requesting replication data from DB node "%s"' %
                       a_db_node.system)

        self.log_mco_action('get_replication_status',
                            a_db_node.system,
                            baseDN=ldap_root,
                            password='xxxx',
                            host=a_db_node.system)

        response = self.run_mco_agent_action('get_replication_status',
                                             a_db_node.system,
                                             ldap_root, cleartext_password,
                                             do_logging=False)

        if "monitor_replication......FAIL" in response:
            msg = self._('OPENDJ_REPLICATION_CHECK_FAILURE')
            self.print_error(msg)
            sys.exit(1)
        if "monitor_replication......OK" in response:
            msg = self._('OPENDJ_REPLICATION_INTACT')
            self.print_success(msg)
        else:
            repl_nodes = EnmPreChecks.process_data(response,
                     'ReplNode',
                     EnmPreChecks.ReplNode.get_regexp_pattern(ldap_root))

            self.log.debug("Replication nodes %s" % repl_nodes)

            if len(repl_nodes) < 2:
                msg = self._('OPENDJ_REPL_NODES_NOT_FOUND')
                self.print_error(msg)
                sys.exit(1)

            repl1 = repl_nodes[0]
            repl2 = repl_nodes[1]

            msg_suffix = self._('REFER_TO_OPENDJ_SECTION_OF_GUIDE')

            errors = 0
            if repl1.entries != repl2.entries:
                msg = self._('MISMATCH_IN_NUMBER_OF_OPENDJ_ENTRIES') + \
                   (msg_suffix)
                self.print_error(msg)
                errors += 1
            if repl1.enabled != repl2.enabled or not repl1.is_enabled():
                msg = self._('REPLICATION_NOT_ENABLED_ON_BOTH_NODES') + \
                   (msg_suffix)
                self.print_error(msg)
                errors += 1
            if repl1.mc_count != repl2.mc_count or repl1.mc_count != '0':
                msg = self._('MC_IS_NOT_ZERO_ON_BOTH_NODES') + (msg_suffix)
                self.print_error(msg)
                errors += 1

            if errors:
                sys.exit(1)
            msg = self._('OPENDJ_REPLICATION_INTACT')
            self.print_success(msg)

    # pylint: disable=R0201
    def check_fallback_vms(self, ip_address, use_dp1_test):
        """
        Command to check if service is UP
        :param ip_address: ip to contact
        :param use_dp1_test: boolean to either check the DP1 or DP2 endpoint
        :return: response from the curl
        """
        if use_dp1_test:
            context_url_path = '/mediationservice/res/health'
            http_port = '8080'
        else:
            context_url_path = '/enm-dp-akka-cluster/bootstrap/seed-nodes'
            http_port = '8558'

        cluster_url = 'http://%s:%s%s' \
                      % (ip_address, http_port, context_url_path)
        if ip_address:
            try:
                reply = requests.get(cluster_url)
                response = reply.status_code
                return response
            except requests.exceptions.RequestException:
                response = 'connectionError'
                return response
        else:
            raise ValueError('IP Parsing went wrong empty ip-address')

    def check_fallback_status(self):
        """
        Action handler to check fallback cluster health
        :return: None
        """
        msg = self._u('CHECKING_FALLBACK')
        self.print_action_heading(msg)
        self.log.info('Checking if file %s exists' % EnmPreChecks.FALLBACK_SED)

        if os.path.isfile(EnmPreChecks.FALLBACK_SED):

            try:
                sed = Sed(EnmPreChecks.FALLBACK_SED)

                self.log.info('Retrieving IPs from file: %s' \
                              % EnmPreChecks.FALLBACK_SED)

                ip_re = re.compile('^fb_dpmediation_.*_ip_internal$|' \
                                   '^fb_dpmediation_internal$')

                ips = dict((k, v) for k, v in sed.items() if ip_re.match(k))
                self.log.info('Returned IP-Addresses: %s' % ips)

                for ip_key, ip_address in ips.items():
                    self.log.info('Checking %s, IP: %s' % (ip_key, ip_address))

                    response = self.check_fallback_vms(ip_address, True)

                    if response != 200:
                        response = self.check_fallback_vms(ip_address, False)
                        if response != 200:
                            if response == 'connectionError':
                                msg = self._('FALLBACK_CHECK_FAILED_CONNECTION'
                                             '_ERROR')
                                self.print_error(msg, add_suffix=False)
                                sys.exit(1)
                            else:
                                msg = self._('FALLBACK_CHECK_FAILED')
                                self.print_error(msg, add_suffix=False)
                                sys.exit(1)
                else:  # pylint: disable=W0120
                    msg = self._('FALLBACK_IS_ONLINE_CHECK_WAS_SUCCESSFUL')
                    self.print_success(msg)

            except ValueError as ex:
                self.log.error(ex)
                msg = self._('FALLBACK_CHECK_FAILED_CANNOT_FIND_IP_ADDRESS')
                self.print_error(msg, add_suffix=False)
                sys.exit(1)
        else:
            msg = self._('SKIPPING_FALLBACK_CHECK_AS_FILE_DOES_NOT_EXIST')
            self.print_success(msg)

    def remove_seed_file_after_check(self):
        """
        Remove the seed.conf depending on the enm version
        :return: None
        """
        msg = self._('DP_CHECKING_ENM_VERSION')
        self.print_action_heading(msg)
        if self.seed_conf_file_exists(EnmPreChecks.DP_SEED_CONF_FILE_PATH):
            msg = self._('DP_CONF_SEED_FILE_DOES_EXIST').format(
                         EnmPreChecks.DP_SEED_CONF_FILE_PATH)
            self.print_message(msg)
            try:
                with open(EnmPreChecks.DP_ENM_VERSION_PATH) as file_handler:
                    raw_enm_version = file_handler.readlines()[0]
                enm_iso_version = re.search(r"\d\.\d*\.\d*", raw_enm_version)\
                    .group(0)
                if (EnmPreChecks.convert_to_tuple(enm_iso_version) <
                    EnmPreChecks.convert_to_tuple(
                        EnmPreChecks.DP_ENM_ISO_VERSION_CUTOFF) and
                        is_env_on_rack()):
                    msg = self._('DP_REMOVE_CONF_SEED_FILE').format(
                        EnmPreChecks.DP_SEED_CONF_FILE_PATH,
                        enm_iso_version,
                        EnmPreChecks.DP_ENM_ISO_VERSION_CUTOFF)
                    self.print_message(msg)
                    cmd = ("rm -rf " + EnmPreChecks.DP_SEED_CONF_FILE_PATH)
                    self.run_command(cmd)
                else:
                    msg = self._('DP_RETAIN_CONF_SEED_FILE').format(
                        EnmPreChecks.DP_SEED_CONF_FILE_PATH,
                        enm_iso_version,
                        EnmPreChecks.DP_ENM_ISO_VERSION_CUTOFF)
                    self.print_message(msg)
            except IOError as ex1:
                self.log.debug('Error while trying to read file to %s. %s' %
                           (EnmPreChecks.DP_ENM_VERSION_PATH, str(ex1)))
                msg = self._('DP_ERROR_WHILE_CHECKING_ENM_VERSION')
                self.print_error(msg)
                sys.exit(1)
        else:
            msg = self._('DP_CONF_SEED_FILE_DOES_NOT_EXIST').format(
                        EnmPreChecks.DP_SEED_CONF_FILE_PATH)
            self.print_message(msg)

        msg = self._('DP_CHECKING_ENM_VERSION_COMPLETED')
        self.print_success(msg)

    @staticmethod
    def convert_to_tuple(enm_version):
        """
        Convert a string to Tuple for version comparison
        :param enm_version: a string representation of the enm version
        :return: the tuple of the enm version
        :rtype: tuple
        """
        return tuple(map(int, enm_version.split('.')))

    def check_elasticsearch_status(self):
        """
        Action to check health status of Elasticsearch
        """
        msg = self._u('CHECKING_ELASTICSEARCH')
        self.print_action_heading(msg)

        err_suffix = msg = self._('REFER_TO_ELASTICSEARCH_BUR_SAG')

        service = 'elasticsearch'
        online_entries = [d for d in self.get_db_nodes_by_service(service)
                          if d.is_online()]
        if online_entries:
            self.log.debug(online_entries)
            msg = self._('ELASTICSEARCH_IS_RUNNING').format(
                                            online_entries[0].system)
            self.print_success(msg)
        else:
            msg = self._('ELASTICSEARCH_STATUS_CHECK_FAILED')
            self.print_error(msg + err_suffix, add_suffix=False)
            sys.exit(1)

        corrupted_indexes = self.check_for_corrupted_indexes(err_suffix)

        if not corrupted_indexes:
            msg = self._('ELASTICSEARCH_INDEXES_ARE_HEALTHY')
            self.print_success(msg)
        else:
            msg = self._('ELASTICSEARCH_INDEXES_ARE_CORRUPTED').format(
                   ', '.join(corrupted_indexes),
                   ('are' if len(corrupted_indexes) > 1 else 'is'))
            self.print_error(msg + err_suffix, add_suffix=False)
            sys.exit(1)

    def check_for_corrupted_indexes(self, err_suffix):
        """
        Check if any Elasticsearch indexes are faulted.
        :param err_suffix: Error message suffix
        :type err_suffix: string
        :return: List of corrupted index string names
        :rtype: list of strings
        """
        msg = self._('CHECKING_ELASTICSEARCH_INDEXES')
        self.print_message(msg)

        cmd = 'curl -s elasticsearch:9200/_cat/indices?v'
        return_code, index_data = self.run_command(cmd)
        self.assert_return_code(return_code, 'elasticsearch curl')

        rows = index_data.splitlines()
        if len(rows) < 2 and rows[0].startswith('health '):
            msg = self._('COULD_NOT_RETRIEVE_HEALTH_OF_ELASTICSEARCH_INDEXES')
            self.print_error(msg + err_suffix, add_suffix=False)
            sys.exit(1)

        corrupted_states = ('yellow ', 'red ')
        corrupted_indexes = []

        for line in rows:  # pylint: disable=E1101
            line = line.strip()
            if line.lower().startswith(corrupted_states):
                corrupted_indexes.append(line.split()[2])
        return corrupted_indexes

    @staticmethod
    def process_data(data, node_classname, pattern):
        """
        Parse command output data
        :param data: STDOUT data
        :type data: string
        :param node_classname: Class to create node
        :type node_classname: string
        :param pattern: Regular expression pattern
        :type pattern: string
        :return: List of nodes
        :rtype: list of objects
        """

        regexp = re.compile(pattern)
        nodes = []

        node_class = getattr(EnmPreChecks, node_classname)

        for line in data.splitlines():
            line = line.strip()
            match = regexp.search(line)
            if match:
                parts = match.groupdict()
                if parts:
                    if all(token in parts.keys()
                           for token in node_class.tokens):
                        node = node_class()
                        for token in node_class.tokens:
                            setattr(node, token, parts[token])
                        nodes.append(node)

        return nodes

    def get_db_systems_by_service(self, service):
        """
        Get the DB cluster node system names.
        Systems are sorted by their service state to minimize
        Versant-Neo4j service disruption. "OFFLINE" nodes are placed first
        :param service: clustered service name
        :type service: string
        :return: List of system names
        :rtype: list of strings
        """

        db_nodes = self.get_db_nodes_by_service(service)

        sorted_db_nodes = sorted(db_nodes, key=lambda n: n.svc_state)
        sorted_db_node_systems = [dbnode.system for dbnode in sorted_db_nodes]
        db_node_systems = sorted(set(sorted_db_node_systems),
                                 key=sorted_db_node_systems.index)

        self.log.debug("DB systems with %s service: %s" %
                       (service, db_node_systems))

        return db_node_systems

    def get_services_by_db_system(self, system):
        """
        Get the services running on a given DB cluster node
        :param system: DB node system name
        :type system: system
        :return: DbService instances created from output of vcs.bsh command
        :rtype: list
        """
        command = (EnmPreChecks.VCS_TOOL +
                   ' --groups' +
                   ' -c ' + EnmPreChecks.CLUSTER_TYPE +
                   ' -s %s' % system)

        return_code, response = self.run_command(command)
        self.assert_return_code(return_code, 'VCS services check',
                                [ExitCodes.OK, ExitCodes.VCS_INVALID_STATE])

        return EnmPreChecks.process_data(response, 'DbService',
                 EnmPreChecks.DbService.get_regexp_pattern(
                   EnmPreChecks.CLUSTER_TYPE,
                   EnmPreChecks.gen_cs_group_pattern(EnmPreChecks.CLUSTER_TYPE,
                                                     'ALL'),
                   system))

    def get_running_systems_by_cluster(self, cluster_type):
        """
        Get a list of System names within a given cluster
        where their state is 'RUNNING'
        :param cluster_type: Name of cluster to query
        :type cluster_type: string
        :return: A list of system names within the given cluster
        :rtype: list
        """
        command = (EnmPreChecks.VCS_TOOL +
                    ' --systems' +
                    ' -c ' + cluster_type)

        return_code, response = self.run_command(command)
        self.assert_return_code(return_code, 'Get %s nodes check'\
                                % cluster_type,
                                                    [ExitCodes.OK])

        systems = EnmPreChecks.process_data(response, 'System',
                    EnmPreChecks.System.get_regexp_pattern(cluster_type))

        return [system.name for system in systems if system.is_running()]

    def get_db_nodes_by_service(self, service):
        """
        Get the DB cluster nodes
        :param service: clustered service name
        :type service: string
        :return: List of DbNode instances
        :rtype: list of objects
        """

        clustered_service = EnmPreChecks.gen_cs_group_pattern(\
                                           EnmPreChecks.CLUSTER_TYPE, service)

        command = (EnmPreChecks.VCS_TOOL +
                   ' --groups' +
                   ' -c ' + EnmPreChecks.CLUSTER_TYPE +
                   ' -g "' + clustered_service + '"')

        return_code, response = self.run_command(command)
        self.assert_return_code(return_code, 'VCS check',
                                [ExitCodes.OK])

        return EnmPreChecks.process_data(
                   response, 'DbNode',
                   EnmPreChecks.DbNode.get_regexp_pattern(
                                 EnmPreChecks.CLUSTER_TYPE, clustered_service))

    def handle_boot_partition(self, system):
        """
        Handle mounting of /boot partition
        :param system: node system name
        :type system: string
        :return: None
        """

        if not self.is_boot_partition_writable(system):

            msg = self._('BOOT_PARTITION_NOT_AVAILABLE').format(system)
            self.print_message(msg)

            self.run_mco_agent_action('boot_partition_mount', system)

            if self.is_boot_partition_writable(system):
                msg = self._('BOOT_PARTITION_AVAILABLE').format(system)
                self.print_success(msg)
            else:
                msg = self._('BOOT_PARTITION_REMAINS_UNAVAILABLE').format(
                                                                    system)
                self.print_error(msg)
                sys.exit(1)

    def is_boot_partition_writable(self, system):
        """
        Is the /boot partition mounted and writable
        :param system: node system name
        :type system: string
        :return: True if /boot is mounted and writable else False
        :rtype: boolean
        """

        response = self.run_mco_agent_action('boot_partition_test', system)
        self.log.debug("/boot partition test response: %s" % response)
        self.run_mco_agent_action('boot_partition_test_cleanup', system)

        # pylint: disable=E1103
        return 'copied' in response.lower()

    def san_alert_check(self):
        """
        Action handler to check if there are any critical alerts
        on the SAN and to detect NAS server imbalance on unityxt SAN.
        """
        msg = self._u('CHECKING_SAN_STORAGE_FOR_ALERTS')
        self.print_action_heading(msg)

        critical_alerts_found = False
        nas_imbalance_detected = False
        try:
            SanHealthChecks().san_critical_alert_healthcheck()
        except SystemExit:
            critical_alerts_found = True

        rest = LitpRestClient()
        nas_type = get_nas_type(rest)

        if not nas_type == 'unityxt':
            self.log.debug('SKIPPING NAS SERVER IMBALANCE CHECK. '
                           'Only applicable to ENM on Rackmount '
                           'Servers.')
        else:
            san_fault_check = SanFaultCheck()
            san_cleanup = SanCleanup()
            san_info = san_cleanup.get_san_info()
            for san in san_info:
                try:
                    san_fault_check.check_nas_servers(san_info, san)
                except Exception as error:  # pylint: disable=W0703
                    self.print_error(error)
                    sys.exit(1)
                nas_fault = san_fault_check.nas_server_fault
                if nas_fault:
                    nas_imbalance_detected = True

        if critical_alerts_found or nas_imbalance_detected:
            failure_msg = self._('SAN_ALERT_CHECK_FAILED')
            self.print_error(failure_msg)
            if critical_alerts_found:
                self.print_message('There are critical alerts'
                                   ' on the SAN Storage.')
            if nas_imbalance_detected:
                self.print_message('NAS server imbalance detected.')
            sys.exit(1)

        self.print_message('Successfully Completed SAN alert Healthcheck')

    def add_lvm_conf_filter(self, system):
        """
        Handle adding filters to /etc/lvm/lvm.conf on the non db-nodes
        :param system: node system name
        :type system: string
        :return: None
        """

        self.run_mco_agent_action('lvm_conf_backups_cleanup', system)
        self.run_mco_agent_action('backup_lvm_conf', system)
        self.run_mco_agent_action('add_lvm_nondb_filter', system)
        self.run_mco_agent_action('add_lvm_nondb_global_filter', system)
        self.run_mco_agent_action('lvm_conf_backups_cleanup', system)

    def check_lvm_conf_non_db_nodes(self):
        """
        Action handler to check the lvm conf on the non db nodes.
        :return: None
        """

        non_db_systems = []
        positive_msg_key = "LVM CONF FILES ON NON DB NODES UPDATED"
        msg = self._u('CHANGING LVM.CONF FILES ON NON DB NODES')
        if not is_env_on_rack():
            self.print_action_heading(msg)

        if self.is_virtual_environment():
            return

        self.log.debug("STARTING NODE CHECK")
        for cluster in EnmPreChecks.NON_DB_CLUSTER_TYPES:
            system_list = self.get_running_systems_by_cluster(cluster)
            self.log.info("System list: {0}".format(system_list))
            if system_list:
                non_db_systems.extend(system_list)

        if not non_db_systems:
            msg = self._('NO NON DB CLUSTER SYSTEMS FOUND') \
                .format(self.current_action)
            self.print_message(msg)
            return

        self.log.debug("NON DB SYSTEMS {0}".format(non_db_systems))
        for system in non_db_systems:
            self.log.debug("Systems: {0}".format(system))
            if not is_env_on_rack():
                self.add_lvm_conf_filter(system)
                msg = self._(positive_msg_key)
                self.print_action_heading(msg)

    def handle_lvm_conf_global_filter(self, system):
        """
        Handle /etc/lvm/lvm.conf global_filter
        :param system: node system name
        :type system: string
        :return: None
        """

        pv_scan1 = self.run_mco_agent_action('physical_volume_scan', system)
        self.log.debug("pvscan #1: %s" % pv_scan1)

        self.run_mco_agent_action('lvm_conf_backups_cleanup', system)
        response = self.run_mco_agent_action('get_lvm_conf_global_filter',
                                             system)

        self.log.debug("%s global_filter: %s" %
                       (EnmPreChecks.LVM_CONF, response))

        if len(response.splitlines()) != 1:  # pylint: disable=E1103
            msg = self._('CORRUPTED_PROPERTIES_FILE').format(
                        EnmPreChecks.LVM_CONF, system)
            self.print_error(msg)
            sys.exit(1)

        if EnmPreChecks.DEVICE_PATH in response:
            msg = self._('CONFIG_FILE_IS_COMPLETE').format(
                  EnmPreChecks.LVM_CONF, system)
            self.print_success(msg)
        else:
            self.run_mco_agent_action('backup_lvm_conf', system)
            self.run_mco_agent_action('update_lvm_conf_global_filter', system)
            response = self.run_mco_agent_action('get_lvm_conf_global_filter',
                                                 system)

            if EnmPreChecks.DEVICE_PATH in response:
                msg = self._('CONFIG_FILE_SUCCESSFULLY_UPDATED').format(
                        EnmPreChecks.LVM_CONF, system)
                self.print_success(msg)

                pv_scan2 = self.run_mco_agent_action('physical_volume_scan',
                                                     system)
                self.log.debug("pvscan #2: %s" % pv_scan2)

                if pv_scan1 == pv_scan2:
                    msg = self._('PVSCAN_COMPARISON_CORRECT').format(
                                    EnmPreChecks.LVM_CONF, system)
                    self.print_success(msg)
                else:
                    msg = self._('PVSCAN_COMPARISON_FAILED').format(
                                               EnmPreChecks.LVM_CONF,
                                               system,
                                               EnmPreChecks.LVM_CONF,
                                               system)
                    self.print_error(msg)
                    sys.exit(1)
            else:
                msg = self._('CONFIG_FILE_NOT_IN_CORRECT_FORMAT').format(
                                       EnmPreChecks.LVM_CONF,
                                       system, system)
                self.print_error(msg)
                sys.exit(1)

            self.run_mco_agent_action('lvm_conf_backups_cleanup', system)

    def check_grub_cfg_lvs(self):
        """
        Action handler to check grub.cfg LVs matching LVs in model.
        :return: None
        """
        table_headers = ['Cluster', 'Node', 'VG', 'Grub State',
                         'Missing LV', 'Extra LV']

        msg = self._u('CHECKING_ALL_LVs_ARE_IN_GRUB.CFG')
        self.print_action_heading(msg)
        if is_env_on_rack():
            self.print_message('SKIPPING THE CHECK '
                'NOT applicable to ENM on Rackmount Servers.')
            return

        self.print_message('STARTING GRUB.CFG LV CHECK')
        grub_conf_check = GrubConfCheck()
        detailed_report = grub_conf_check.report_lvs()
        check_failed = grub_conf_check.grub_lvs_check_failed
        if getattr(self.processed_args, EnmPreChecks.PARAM_VERBOSE, False):
            report_tab_data(None, table_headers, detailed_report)
        if not check_failed:
            success_msg = self._('GRUB.CFG_LV_CHECK_PASSED')
            self.print_success(success_msg)
        else:
            failure_msg = self._('GRUB.CFG_LV_CHECK_FAILED')
            self.print_message('There is one or more mismatch between LVs in'
                          ' the model and LVs in grub.cfg ')
            self.print_error(failure_msg)
            sys.exit(1)
        self.print_message('Successfully Completed grub.cfg Healthcheck')

    def handle_dmsetup_and_reboot(self, system, node_checker):
        """
        Handle dmsetup and perform a reboot
        :param system: node system name
        :type system: string
        :param node_checker: function to check state of node
        :type node_checker: function
        :return: None
        """

        msg = self._('NON_MULTIPATHED_VOLUMES_PRESENT').format(system)
        user_reply = self.prompt_user_boolean(msg)

        if user_reply is EnmPreChecks.AFFIRMATIVE:

            msg = self._('REBOOTING_AND_WAITING_TWO_MINUTES').format(
                                                                system)
            self.print_message(msg)
            self.run_mco_agent_action(
                'stop_vcs_and_reboot', system)
            time.sleep(120)

            if node_checker(system):
                response = self.get_non_dev_mapper_count(system)

                if '0' != response.strip():
                    msg = self._('ERRORS_IN_VOLUME_MULTIPATHING').format(
                                                                    system)
                    self.print_error(msg)
                    sys.exit(1)
                else:
                    msg = self._('LVM_MULTIPATH_CORRECTLY_SETUP').format(
                                                                    system)
                    self.print_success(msg)
            else:
                msg = self._('REBOOT_FAILURE').format(system)
                self.print_error(msg)
                sys.exit(1)

    def check_db_disk_storage_setup(self):
        """
        Action handler to check storage setup on db nodes.
        Versant or Neo4j nodes are checked first in order to
        minimize Versant-Neo4j service disruption
        """

        if is_dps_using_neo4j():
            service = 'neo4j'
        else:
            service = 'versant'

        msg = self._u('CHECKING_DISK_STORAGE')
        self.print_action_heading(msg)

        if self.is_virtual_environment():
            return

        all_db_systems = self.get_running_systems_by_cluster(
                                                    EnmPreChecks.CLUSTER_TYPE)

        if not all_db_systems:
            msg = self._('NO_DB_SVC_SYSTEMS_FOUND').format(self.current_action)
            self.print_message(msg)
            return

        current_db_systems = self.get_db_systems_by_service(service)

        non_current_db_systems = [system_name for system_name in all_db_systems
                                    if system_name not in current_db_systems]

        # We need to ensure that DB nodes on which Versant or Neo4j is running
        # get serviced first. all_db_systems is reassigned here to preserve
        # this ordering.
        all_db_systems = list(current_db_systems) + non_current_db_systems

        for system in all_db_systems:
            self.handle_boot_partition(system)
            if not is_env_on_rack():
                self.handle_lvm_conf_global_filter(system)

        self.check_disks_device_mapper(all_db_systems)

    def check_disks_device_mapper(self, systems):
        """
        Check the device-mapper state of node disks
        :param systems: list of system names
        :type systems: list
        :return: None
        """

        dbs_with_non_dm_disks = 0
        non_dm_disks_found = {}
        node_checker = self.is_reachable_node
        positive_msg_key = 'NO_ACTION_REQUIRED_FOR_LVM_MULTIPATHING'

        for system in systems:
            response = self.get_non_dev_mapper_count(system)
            non_dm_disks_found[system] = '0' != response.strip()
            if non_dm_disks_found[system]:
                dbs_with_non_dm_disks += 1

        if dbs_with_non_dm_disks == 0 or (dbs_with_non_dm_disks == 3 and \
            is_env_on_rack()):
            for system in systems:
                msg = self._(positive_msg_key).format(system)
                self.print_success(msg)
            return
        elif dbs_with_non_dm_disks > 1:
            node_checker = self.is_vcs_healthy

        for system in non_dm_disks_found.keys():
            if non_dm_disks_found[system]:
                self.handle_dmsetup_and_reboot(system, node_checker)
            else:
                msg = self._(positive_msg_key).format(system)
                self.print_success(msg)

    def get_non_dev_mapper_count(self, system):
        """
        Get the non-device-mapper count for the system
        :param system: node system name
        :type system: string
        :return: response from MCO agent
        :rtype: string
        """
        response = self.run_mco_agent_action('get_count_dmsetup_deps_non_dm',
                                             system)
        self.log.debug("Non device mapper device count: %s" % response)
        return response

    def services_valid_on_node(self, hostname):
        """
        Check if node services are valid after reboot
        :param hostname: Hostname to check
        :type hostname: string
        :return: Boolean True if services are valid, False otherwise
        """

        valid = False
        timeout = EnmPreChecks.Timeout(EnmPreChecks.PING_TIMEOUT)

        while not (valid or timeout.has_elapsed()):

            if timeout.get_elapsed_time() % 5 == 0:

                services = self.get_services_by_db_system(hostname)
                remaining_time = timeout.get_remaining_time()

                valid = all(service.is_valid() for service in services)
                self.log.debug("Services on DB node %s: %s. %d secs left" %
                               (hostname, services, remaining_time))

                if not valid:
                    timeout.sleep(1)

        return valid

    def is_reachable_node(self, hostname):
        """
        Check if a node is reachable after reboot
        :param hostname: Hostname to check
        :type hostname: string
        :return: Boolean True if node is reachable, False otherwise
        """

        reachable = False
        timeout = EnmPreChecks.Timeout(EnmPreChecks.PING_TIMEOUT)

        while not (reachable or timeout.has_elapsed()):

            if timeout.get_elapsed_time() % 5 == 0:

                command = 'mco ping -I %s' % hostname
                response, _ = self.run_command(command)
                remaining_time = timeout.get_remaining_time()

                self.log.debug("mco pinged node %s, %d secs left, rc %s" %
                               (hostname, remaining_time, response))

                if response in (0, 1):
                    reachable = True
                else:
                    timeout.sleep(1)

        return reachable

    def is_vcs_healthy(self, hostname):
        """
        Check that a DB node is healthy for VCS
        ie. is the node pingable, does VCS report the node
        as RUNNING and all service groups "OK" on that node
        :param hostname: DB node system name
        :type hostname: string
        :return: True if all 3 checks pass, False otherwise
        :rtype: boolean
        """
        return all([self.is_reachable_node(hostname),
                    self.is_vcs_running_on_node(hostname),
                    self.services_valid_on_node(hostname)])

    def is_vcs_running_on_node(self, hostname):
        """
        Check if VCS is running on a node after reboot
        :param hostname: Hostname to check
        :type hostname: string
        :return: Boolean True if node is reachable, False otherwise
        """
        vcs_running = False
        mco_action = 'hasys_state'
        err_string = 'VCS ERROR V-16-1-10600 Cannot connect to VCS engine'

        timeout = EnmPreChecks.Timeout(EnmPreChecks.PING_TIMEOUT)

        while not (vcs_running or timeout.has_elapsed()):
            if timeout.get_elapsed_time() % 5 == 0:
                sleep_required = True
                try:
                    response = self.run_mco_agent_action(mco_action,
                                    hostname,
                                    mco_agent_object=self.enminst_agent,
                                    non_exit_errors=[err_string])
                except McoAgentException:
                    pass
                else:
                    _, states = response
                    remaining_time = timeout.get_remaining_time()

                    self.log.debug("%s node %s, %d secs left, response %s"
                         % (mco_action, hostname, remaining_time, states))

                    if states:
                        for state in states:
                            if state['Name'] == hostname and \
                               state['State'] == ['RUNNING']:
                                vcs_running = True
                                sleep_required = False
                                break

                if sleep_required:
                    timeout.sleep(1)

        return vcs_running

    def load_global_properties(self, properties_file):
        """
        Load global properties on demand
        :param properties_file: Path to properties file
        :type properties_file: string
        :return: None
        """

        with open(properties_file) as myfile:
            for line in myfile.readlines():
                line = line.strip()
                key, value = line.partition("=")[::2]
                self.global_properties[key.strip()] = value.strip()

    def get_ldap_root(self, properties_file):
        """
        Get the LDAP-root property value
        :param properties_file: Path to global properties file
        :type properties_file: string
        :return: LDAP-root property value
        :rtype: string
        """

        if not self.global_properties:
            self.load_global_properties(properties_file)

        return self.global_properties.get('COM_INF_LDAP_ROOT_SUFFIX', None)

    def get_cleartext_password(self, properties_file):
        """
        Get the cleartext OpenDJ password
        :param properties_file: Path to global properties file
        :type properties_file: string
        :return: Cleartext OpenDJ password if found
        :rtype: string
        """

        if not self.global_properties:
            self.load_global_properties(properties_file)

        enc_password = None

        if 'LDAP_ADMIN_PASSWORD' in self.global_properties.keys():
            enc_password = self.global_properties.get('LDAP_ADMIN_PASSWORD')

        if enc_password:
            openssl_decrypter = '/usr/bin/openssl ' + \
                                'enc -a -d -aes-128-cbc -salt -kfile ' + \
                                '/ericsson/tor/data/idenmgmt/opendj_passkey'

            command = "/bin/echo %s | %s" % (enc_password, openssl_decrypter)
            return_code, response = self.run_command(command, do_logging=False)
            self.assert_return_code(return_code, 'password decrypt')

            if response:
                return response.strip()

    def create_arg_parser(self):
        """
        Create an argument parser
        :return: None
        """

        this_script = 'enm_upgrade_prechecks.sh'
        usage = '%s [-h] [-a action [action ...]] [-y] [-v]' % \
                this_script

        epilog = textwrap.dedent('''
# %(prog)s --action storage_setup_check            -> Check storage setup
# %(prog)s --action litp_model_synchronized_check  -> Check the LITP model is \
synchronized with the deployment
# %(prog)s --action elastic_search_status_check    -> Check Elasticsearch \
state and status of indexes
# %(prog)s --action opendj_replication_check       -> Check OpenDJ \
replication status
# %(prog)s --action unmount_iso_image_check        -> Check for ISO image and \
unmount if present
# %(prog)s --action apply_puppet_timeouts          -> Apply longer \
puppet timeouts in case of old low values from older versions.
# %(prog)s --action remove_packages                -> Removes \
packages for removal and their dependencies
# %(prog)s --action deactivate_ombs_backup         -> Deactivate OMBS backup
# %(prog)s --action check_fallback_status          -> Check fallback cluster
is healthy
# %(prog)s --action remove_seed_file_after_check   -> Remove the seed.conf \
depending on the enm version
# %(prog)s --action check_https_port_ilo_available -> Check HTTPS port \
available for the iLO
# %(prog)s --action check_grub_cfg_lvs             -> Checks LVs in \
the model are present in grub.cfg. NOT applicable to ENM on Rackmount Servers.
# %(prog)s --action san_alert_check                -> Check if there are any \
critical alerts on the SAN.
# %(prog)s --action restart_puppet_services        -> Restart Puppet Services
# %(prog)s --action upgrade_prerequisites_check    -> Run all upgrade \
prechecks except deactivate_ombs_backup
# %(prog)s without any action parameter is the same as specifying \
action parameter upgrade_prerequisites_check
''')

        self.parser = ArgumentParser(prog=this_script,
                                     usage=usage,
                                     formatter_class=RawTextHelpFormatter,
                                     epilog=epilog,
                                     add_help=False)

        text = ('Where action can be one of:\n- %s') % \
                '\n- '.join(EnmPreChecks.ACTION_CHOICES)

        optional_group1 = self.parser.add_argument_group('optional arguments')

        optional_group1.add_argument('--help', '-h',
                                     action='help',
                                     help='Show this help message and exit')

        optional_group1.add_argument('--action', '-a',
                                     nargs='+',
                                     default=[EnmPreChecks.PARAM_ALL],
                                     choices=EnmPreChecks.ACTION_CHOICES,
                                     metavar=EnmPreChecks.PARAM_ACTION,
                                     help=text)

        optional_group1.add_argument('--assumeyes', '-y',
                                     dest=EnmPreChecks.PARAM_ASSUMEYES,
                                     default=False,
                                     action='store_true',
                                     help='Answer yes for all questions')

        optional_group1.add_argument('--verbose', '-v',
                                     dest=EnmPreChecks.PARAM_VERBOSE,
                                     default=False,
                                     action='store_true',
                                     help='Enable verbose logging')

    def process_actions(self, arguments):
        """
        Process the actions
        :return: None
        """

        print_summary_on_success = False

        if EnmPreChecks.PARAM_ALL in arguments:
            actions = EnmPreChecks.ACTION_CHOICES[:-1]
            print_summary_on_success = True
        elif 'deactivate_ombs_backup' in arguments:
            actions = ['deactivate_ombs_backup']
        else:
            actions = sorted(set(arguments), key=arguments.index)

        handlers = [self.check_db_disk_storage_setup,
                    self.san_alert_check,
                    self.check_lvm_conf_non_db_nodes,
                    self.check_grub_cfg_lvs,
                    self.check_litp_model_synchronized,
                    self.check_elasticsearch_status,
                    self.check_opendj_replication,
                    self.unmount_iso_image,
                    self.remove_packages,
                    self.apply_puppet_timeouts,
                    self.check_fallback_status,
                    self.remove_seed_file_after_check,
                    self.check_https_port_ilo_available,
                    self.deactivate_ombs_backup,
                    self.restart_puppet_services]

        action_handlers = dict(zip(EnmPreChecks.ACTION_CHOICES[:-1],
                                   handlers))

        for action in actions:
            self.current_action = action
            action_handlers[action]()

        if print_summary_on_success:
            msg = self._('ALL_PRECHECKS_SUCCESS')
            self.print_action_heading(msg, print_heading_with_appendages=False)


def main(args):
    """
    Main function
    :return: None
    """

    enm_prechecks = EnmPreChecks()
    enm_prechecks.create_arg_parser()
    enm_prechecks.processed_args = enm_prechecks.parser.parse_args(args[1:])
    enm_prechecks.set_verbosity_level()

    if not enm_prechecks.processed_args.action:
        enm_prechecks.parser.print_help()
        raise SystemExit(2)

    enm_prechecks.process_actions(enm_prechecks.processed_args.action)

if __name__ == '__main__':
    main_exceptions(main, sys.argv)
