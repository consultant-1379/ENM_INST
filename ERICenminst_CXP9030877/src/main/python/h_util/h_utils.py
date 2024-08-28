# pylint: disable=C0302, C0103
"""
Module containing general utility functions
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
import functools
import logging
import os
import socket
import pwd
import re
import shutil
import sys
import filecmp
import glob
import gettext
import paramiko
import yum
import pexpect
import json
import imp
from distutils.version import LooseVersion
from ConfigParser import SafeConfigParser, NoOptionError
from base64 import standard_b64decode, standard_b64encode
from gettext import NullTranslations
from datetime import datetime, timedelta
from os.path import exists, join
from re import match
from subprocess import Popen, PIPE, STDOUT
from Crypto.Cipher import AES
try:
    import redfish  # pylint: disable=import-error
    # pylint: disable=import-error
    from redfish.rest.v1 import BadRequestError, RetriesExhaustedError, \
        DecompressResponseError
except ImportError:
    pass

ENC_KEY = 'tgh[wo94h[0ht0-we'
DEPLOYMENT_DIFF_OUTPUT = 'deployment_diff_output'
CLOUD_MANUFACTURERS = ['vmware', 'virtualbox', 'kvm', 'qemu', 'red hat']
LOG = logging.getLogger('enminst')
PIB_CMD = 'python /ericsson/pib-scripts/etc/config.py'
DEFAULT_PIB_APP_SERVER_ADDRESS = 'svc-1-sps:8080'
ENMINST_HOME = '/opt/ericsson/enminst/'
TMP_SED_DIR = '/software/vol1'
EDP_GEN_SED = 'ansible_tmp_sed.txt'
EDP_SED_FILEPATH = '{0}/{1}'.format(TMP_SED_DIR, EDP_GEN_SED)
OPT_ERIC = os.path.join(os.sep, 'opt', 'ericsson')
NMS_LITP = os.path.join(OPT_ERIC, 'nms', 'litp')
LITP_ETC_DIR = os.path.join(NMS_LITP, 'etc')
LITP_PUPPET_DIR = os.path.join(LITP_ETC_DIR, 'puppet')
KICKSTART_ERB = os.path.join(LITP_PUPPET_DIR, 'modules', 'cobbler',
                              'templates', 'kickstart.erb')
cmd_DISABLE_CRON_ON_EXPIRY = 'if [ -f  {0}.bak ]; then '\
                             'mv -f {0}.bak {0}; '\
                             'fi'.format(KICKSTART_ERB)
LITP_ERB_TEMPLATES = '/opt/ericsson/nms/litp/etc/puppet/modules/litp/files/'


class ExitCodes(object):  # pylint: disable=too-few-public-methods
    """
    Class containing variables to use if exiting with a specific code
    """

    def __init__(self):
        super(ExitCodes, self).__init__()

    OK = 0  # pylint: disable=invalid-name
    ERROR = 1
    INVALID_USAGE = 2
    INVALID_VCS_STATE = 3
    VCS_OPERATION_TIMEDOUT = 9
    VCS_CLEAR_STATE = 10
    VCS_GROUP_OFFLINE = 11
    VCS_SYSTEM_NOT_FOUND = 12
    VCS_GROUP_NOT_FOUND = 13
    VCS_INVALID_ACTION = 14
    VCS_SYSCLSTR_OFFLINE = 15
    VCS_CLUSTER_NOT_FOUND = 16
    VCS_SYSTEM_FROZEN = 17
    VCS_INVALID_STATE = 20
    LITP_MAINT_MODE = 21
    LITP_NO_SNAPS_EXIST = 22
    LITP_NO_NAMED_SNAPS_EXIST = 23
    LITP_SNAPS_EXIST = 24
    LITP_SNAP_ERROR = 25
    TIMEOUT = 41
    INTERRUPTED = 42
    INVALID_SNAPSHOTS = 43
    PLAN_FAILED = 44
    PLAN_STOPPED = 45
    UNKNOWN_PLAN_STATE = 46
    PLAN_START_TIMEOUT = 47
    TEARDOWN_FUNCTION_ERROR = 48
    LOAD_PLAN_FAILED = 49
    CREATE_PLAN_FAILED = 50


def check_package_installed(rpm_name):
    """
    Checks if rpm package is installed.
    :param rpm_name: Name of rpm to check
    :return: True if package found, false if not found
    """
    try:
        yum_base = yum.YumBase()
        return yum_base.isPackageInstalled(rpm_name)
    except (yum.Errors.YumBaseError) as yum_err:
        LOG.error('YUM error when checking {0} rpm'.format(rpm_name))
        LOG.error(yum_err)
        raise
    finally:
        yum_base.closeRpmDB()


def compare_versions(first_version, second_version):
    """
    Compare 2 rpm versions
    :param first_version: regex match object e.g "1.4.51"
    :type first_version: str
    :param second_version: regex match object e.g "1.23.5"
    :type second_version: str
    :return "bigger", "smaller" or "equal"
    """
    act_first_version = LooseVersion(first_version)
    act_second_version = LooseVersion(second_version)

    if act_first_version > act_second_version:
        return "bigger"
    elif act_second_version > act_first_version:
        return "smaller"
    return "equal"


def remove_rpm(rpm_name):
    """
    Removes provided rpm
    :param rpm_name: The rpm name to remove
    :type rpm_name: str
    :return:
    """
    try:
        yum_base = yum.YumBase()
        if not yum_base.isPackageInstalled(rpm_name):
            LOG.info('rpm {0} is not installed'.format(rpm_name))
            yum_base.closeRpmDB()
            return
        LOG.info('Removing rpm {0}'.format(rpm_name))
        yum_base.remove(name=rpm_name)
        yum_base.resolveDeps()
        yum_base.buildTransaction()
        yum_base.processTransaction()
    except yum.Errors.YumBaseError:
        LOG.info('YUM failed to remove {0} rpm'.format(rpm_name))
        raise
    finally:
        yum_base.closeRpmDB()


def install_rpm(rpm_name, rpm_path=''):
    """
    install provided rpm
    :param rpm_name: The rpm name to install
    :type rpm_name: str
    :param rpm_path: Path to the rpm
    :type rpm_path: str
    :return:
    """
    try:
        yum_base = yum.YumBase()
        if not rpm_path:
            packages_list = \
                [pkg.__str__().split('-') for pkg in
                 yum_base.pkgSack.returnPackages()]
            for rpm_name_in_repo in packages_list:
                if rpm_name in rpm_name_in_repo[0]:
                    break
            else:
                LOG.error("rpm {0} is not in yum repo's!"
                          .format(rpm_name))
                raise KeyError("rpm {0} is not in yum repo's!"
                               .format(rpm_name))
        if yum_base.isPackageInstalled(rpm_name):
            LOG.info('rpm {0} is already installed'
                     .format(rpm_name))
            yum_base.closeRpmDB()
            return
        else:
            LOG.info('Installing rpm {0}'.format(rpm_name))
            if rpm_path:
                yum_base.installLocal(rpm_path)
            else:
                yum_base.install(name=rpm_name)
        yum_base.resolveDeps()
        yum_base.buildTransaction()
        yum_base.processTransaction()
        if not yum_base.isPackageInstalled(rpm_name):
            LOG.error('YUM failed to install {0} rpm'.format(rpm_name))
            yum_base.closeRpmDB()
            raise yum.Errors.InstallError('rpm {0} failed to install'.
                                          format(rpm_name))
    except (yum.Errors.InstallError) as yum_err:
        LOG.error('YUM install failed of {0} rpm'.format(rpm_name))
        LOG.error(yum_err)
        raise
    finally:
        yum_base.closeRpmDB()


def get_rpm_info(host_name, rpm_name=None, rpm_path=None):
    """
    Get name, version and release of RPM.
    :param host_name: The hostname where the RPM is installed
    :type host_name: str
    :param rpm_name: The name of an installed RPM
    :type rpm_name: str
    :param rpm_path: The path of an RPM on the filesystem
    :type rpm_path: str
    :return: dict containing RPM name, version and release
    """
    if rpm_name and rpm_path or not rpm_name and not rpm_path:
        raise ValueError("Call with one and only one of rpm_name, rpm_path")

    if rpm_name:
        LOG.info("Querying installed RPM {0} on LMS {1}".format(rpm_name,
                                                                host_name))
        args = '-q'
        rpm = rpm_name
    elif rpm_path:
        LOG.info("Querying RPM file {0} on LMS {1}".format(rpm_path,
                                                           host_name))
        args = '-qp'
        rpm = rpm_path

    rpm_cmd = ['rpm',
               args,
               '--queryformat',
               'name=%{Name},version=%{VERSION},release=%{RELEASE}',
               rpm]

    try:
        out = exec_process(rpm_cmd)
    except IOError as error:
        LOG.exception(error)
        raise

    return dict(key_val.split('=') for key_val in out.split(','))


def get_rpm_install_size(rpm_name=None, rpm_path=None):
    """
    Get the size of the specific RPM to check if there is space
    available to install
    :param rpm_name:
    :param rpm_path:
    :return: rpm_size
    """
    try:
        if rpm_name:
            LOG.info("Querying size of RPM: {0}".format(rpm_name))
            args = '-qi'
            rpm = rpm_name

        elif rpm_path:
            LOG.info("Querying size of RPM: {0}".format(rpm_path))
            args = '-qip'
            rpm = rpm_path

        rpm_cmd = ['rpm',
                   args,
                   '--queryformat',
                   'size=%{longsize}',
                   rpm]
        out = exec_process(rpm_cmd)
        rpm_size = out.split('=')[-1]
        return rpm_size

    except IOError as error:
        LOG.exception(error)


def get_lms_free_space():
    """
    Get the space available on the filesystem specified
    :return: space_available
    """
    filesystem = '/'
    try:
        LOG.info("Querying amount of available "
                 "space on filesystem{0}".format(filesystem))

        cmd = ['df', '-B1', filesystem]

        awk_cmd = ['awk', '$NF== "/" {print $3}']

        filesystem_size = exec_process_via_pipes(cmd, awk_cmd)

        return filesystem_size
    except IOError as error:
        LOG.exception(error)


def kill_processes_dir(path):
    """
    Kill processes holding resources at a given path

    :param path: path on filesystem to kill processes
    :type path: str
    """
    cmd_lsof = ['lsof']
    cmd_grep = ['grep', path]
    cmd_awk = ['awk', '{print $2}']
    cmd_xargs = ['xargs', 'kill', '-9']
    commands = [cmd_lsof, cmd_grep, cmd_awk, cmd_xargs]
    try:
        LOG.info('Executing: {0}'.format(' | '.join(map(str, commands))))
        exec_process_via_pipes(cmd_lsof, cmd_grep, cmd_awk, cmd_xargs)
    except IOError:
        pass


def _handle_exec_process(command, info_msg, error_msg, quiet=False):
    """
    Handles execution of external process
    :param command: command to execute
    :param info_msg: information to be displayed
    :param error_msg: error message
    :return: stdout generated by command
    :rtype string
    """
    try:
        if quiet == False:
            LOG.info(info_msg)
        LOG.debug('exec command {0}'.format(command))
        stdout = exec_process(command.split()).strip()
    except IOError:
        if quiet == False:
            LOG.exception(error_msg)
        raise SystemExit(ExitCodes.ERROR)
    for line in stdout.splitlines():
        LOG.debug(line)
    return stdout


def _exec_curl_command(curl_command, retries=2, hide_output=False):
    """
    Executes a curl command and return the response
    :return:
    """
    no_output = '>/dev/null 2>&1'
    err_message = ""
    if hide_output:
        curl_command = '{0} {1}'.format(curl_command.strip(), no_output)
    while retries > 0:
        try:
            response = os.system(curl_command)
            return response
        except (OSError, IOError) as err:
            retries -= 1
            if retries == 0:
                err_message = "Error running curl command: {0}. Error: {1}"\
                          .format(curl_command, err)
    raise SystemExit(err_message)


def exec_process(command, ignore_error=False, sudo=None, environ=None,
                 stderr=STDOUT, use_shell=False):
    # pylint: disable=R0913
    """
    Execute a system process.
    :param command: The command to execute
    :type command: str[]
    :param ignore_error: Should error be ignored or not
    :param sudo: Run the command via this user
    :param environ: Environment variables to pass to the process
    :param stderr: Where stderr should be redirected to
    :param use_shell: If set to True causes Popen to use shell
                      to exec process.
    :return:
    """
    process = Popen(command, stderr=stderr, stdout=PIPE, env=environ,
                    preexec_fn=switch_user(sudo), shell=use_shell)
    stdout = process.communicate()[0]
    if process.returncode != 0 and not ignore_error:
        raise IOError(process.returncode, stdout, command)
    return stdout


def exec_process_retry(cmd, retry_errors, retry_count,
                       error_msg='A problem occurred running command',
                       use_shell=True):
    """
    This function has a retry mechanism handling specific IOErrors
    depending on the IOError message.
    :param cmd: The command to be executed
    :param retry_errors: A list of regular expressions that will be
                            checked against the exception message.
    :type retry_errors: str[]
    :param retry_count: number of retry attempts
    :type retry_count: int
    :param error_msg: A specific error message that will be logged
    :type : str
    :param use_shell: The specified command will be executed through the shell
    :type : bool
    :returns: std_out from exec_process
    :raises: IOError if exception message is unknown or if retry
            limit is reached
    """
    retries = 0
    last_retry_error = IOError()
    while retries <= retry_count:
        try:
            return exec_process([' '.join(cmd)], use_shell=use_shell)
        except IOError as error:
            last_retry_error = error
            LOG.debug('{0}: {1}'.format(error_msg, str(error)))
            should_retry = False
            for retry_error in retry_errors:
                if re.match(retry_error, str(error)):
                    LOG.debug('Known issue, going to retry command...')
                    should_retry = True
                    retries += 1
                    break
            if not should_retry:
                LOG.exception('Unexpected type of error running command')
                raise
    LOG.error('Retry limit reached ({0}) for running command.'
              ''.format(retries))
    raise last_retry_error


def delete_file(filename):
    """
    Delete a file
    :param filename: Path of the file to delete
    :return:
    """
    if exists(filename):
        try:
            os.remove(filename)
            LOG.info('Removed {0}'.format(filename))
        except OSError as ioe:
            LOG.warn('Problem removing {0} OS error {1}'.format(filename, ioe))


def copy_file(source, dest):
    """
    Copy file from source to destination.
    :param source: Source file
    :param dest: Destination file
    """
    LOG.info('Copying {0} to {1}'.format(source, dest))
    try:
        shutil.copy2(source, dest)
    except IOError:
        LOG.exception('Unable to copy {0} to {1}'.format(source, dest))
        raise


def exec_process_via_pipes(*commands):
    """
    Execute commands in pipes

    :param commands arbitrary number of commands
    :return: string containing output from execution of the lst command
    """
    if len(commands) == 0:
        raise ValueError("Empty command tuple passed")
    processes = [Popen(commands[0], stdout=PIPE, stderr=STDOUT)]
    index_popen = 1
    while index_popen < len(commands):
        processes.append(Popen(commands[index_popen],
                               stdin=processes[index_popen - 1].stdout,
                               stdout=PIPE))
        index_popen += 1
    index_close = 0
    last_process_index = len(commands) - 1
    while index_close < last_process_index:
        # Allow process to receive
        # a SIGPIPE if next process exits.
        processes[index_close].stdout.close()
        index_close += 1
    stdout = processes[last_process_index].communicate()[0]

    if processes[last_process_index].returncode != 0:
        raise IOError(processes[last_process_index].returncode,
                      processes[last_process_index].stdout)
    return stdout


def screen(message, verbose=True):
    """
    Log a message to stdout
    :param message: The message to log
    :param verbose: Can be disabled if `False`
    :return:
    """
    if verbose:
        print(message)  # pylint: disable=superfluous-parens


def get_env_var(var_name):
    """
    Get an Environment variable.
    If the variable is not found a KeyError is raised.

    :param var_name: The OS environment variable name
    :type var_name: str
    :rtype: str
    """
    if var_name not in os.environ:
        raise KeyError(var_name)
    else:
        return os.environ[var_name]


def wstderr(message):
    """
    Write to stderr

    :param message: The string to write
    :type message: str
    """
    sys.stderr.write(message)
    sys.stderr.write('\n')
    sys.stderr.flush()


def read_enminst_config(cfg_file=None):
    """
    Reads an .ini format configuration file - cfg_file.
    By default looks for '../etc/enminst_cfg.ini' if no file is provided.
    Creates a dictionary with the items of the ENM_INST_CONFIG section.
    If any of the items is overshadowed by an environment variable with the
    same name, it uses the value from the environment instead.
    :param cfg_file: path to config file
    :return: dictionary with the items of the ENM_INST_CONFIG section.
    """
    if not cfg_file:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        cfg_file = os.path.join(base_dir, 'etc', 'enminst_cfg.ini')

    cfg_reader = SafeConfigParser()
    read_files = cfg_reader.read(cfg_file)
    if not read_files:
        raise SystemExit('Failed to read config file {0}'.format(cfg_file))

    for key in cfg_reader.options('ENM_INST_CONFIG'):
        try:
            if os.environ[key.upper()]:
                cfg_reader.set('ENM_INST_CONFIG', key, os.environ[key.upper()])
        except KeyError:
            pass

    result = dict(cfg_reader.items('ENM_INST_CONFIG'))
    return result


def get_sed_nodetypes(sed):
    """
    Get a map of the nodes types in the SED and the count for each e.g.
    {'db': 2, 'svc': 4} or {'db': 2, 'svc': 2, '
    scp': 2}

    This looks for keys matching the regex "(.*?)_node[0-9]+_hostname" in the
    SED and if the value is not empty increment the group(1) count.


    :param sed: The SED to count the node type in
    :type sed: Sed
    :returns: A map containing a count for each node type in the SED
    """
    hostname_keys = sed.find_keys('^.*?_node[0-9]+_hostname')
    nodetypes = {}
    for hostname_key in hostname_keys:
        hostname_value = sed.get_value(hostname_key)
        if not hostname_value:
            continue
        ntype = hostname_key.split('_')[0]
        if ntype in nodetypes:
            nodetypes[ntype] += 1
        else:
            nodetypes[ntype] = 1
    return nodetypes


def format_sed_key(nodetype, node_index, keyname):
    """
    Get the Site Engineering key for a nodes,
    format is <type>_node<index>_<key>
    :param nodetype: The nodes type e.g. svc, db, etc.
    :param node_index: The node index
    :param keyname: The key name e.g. hostname
    :returns: The SED key for the particular node
    """
    return '{0}_node{1}_{2}'.format(nodetype, node_index, keyname)


def _match_path(regex):
    """
    Get a list of removed nodes or clusters by inspecting
    the DEPLOYMENT_DIFF_OUTPUT file
    :return: list of node or cluster vpaths that are being removed
    """
    config = read_enminst_config()
    matched_paths = []
    deploy_diff_output_file = config.get(DEPLOYMENT_DIFF_OUTPUT)
    if os.path.exists(deploy_diff_output_file):
        with open(deploy_diff_output_file, 'r') as _reader:
            for line in _reader.readlines():
                _match = re.match(regex, line)
                if _match:
                    vpath = line.split()[1].strip()
                    matched_paths.append(vpath)
    return matched_paths


def get_removed_nodes():
    """
    Get a list of removed nodes by setting and returning a pattern
    :return: string path
    """
    return _match_path('^y /deployments/.+/clusters/.+/nodes/[^/]+$')


def get_removed_clusters():
    """
    Get a list of removed clusters by setting and returning a pattern
    :return: string path
    """
    return _match_path('^y /deployments/.+/clusters/(.*_cluster)$')


def delete_matching_files(path, extension):
    """
    Function Description:
    This function removes a file based on the path and ext[ension]
    passed, using the delete_file function.
    :param path: File path to where file is stored
    :param ext: File extension
    """
    for filename in glob.glob1(path, extension):
        cobbler_file = join(path, filename)

        logging.info('Removing {0}'.format(cobbler_file))
        delete_file(cobbler_file)


class Formatter(object):  # pylint: disable=too-few-public-methods
    """
    Log formatter to set bash colour codes on log messages
    """
    ENDC = '\033[0m'

    BG_GREEN = '\033[42m'
    BG_GRAY = '\033[47m'

    FG_RED = '\033[31m'
    FG_BROWN = '\033[33m'
    FG_YELLOW = '\033[1;33m'
    FG_CYAN = '\033[36m'
    FG_WHITE = '\033[1;37m'
    FG_GRAY = '\033[0;37m'

    VALUE_INC = FG_BROWN
    VALUE_DEC = FG_CYAN
    VALUE_NOC = FG_YELLOW
    VALUE_KEY = FG_WHITE

    PLAN_STATE_COLORMAP = {
        'Success': FG_CYAN,
        'Running': '{0}{1}'.format(FG_GRAY, BG_GREEN),
        'Initial': FG_YELLOW,
        'Failed': '{0}{1}'.format(FG_RED, BG_GRAY),
        'default': FG_WHITE
    }

    @staticmethod
    def format_color(text, color):
        """
        Wrap text in bash colour code blocks
        :param text: The text to wrap
        :param color: The colour to use
        :return: Wrapped text
        """
        return '{0}{1}{2}'.format(color, text, Formatter.ENDC)


class Sed(dict):  # pylint: disable=too-many-public-methods
    """
    Class to access SED parameters
    """
    SK_HOSTNAME = 'hostname'
    SK_IPINTERNAL = 'IP_internal'
    SK_ILO_IP = 'ilo_IP'
    SK_ILO_USERNANE = 'iloUsername'
    SK_ILO_PASSWORD = 'iloPassword'

    def __init__(self, sed_file):
        """
        Read the SED file and store in memory

        :param sed_file: Path to SED file
        :type sed_file: str|None
        """
        super(Sed, self).__init__()
        self._sedfile = sed_file
        if sed_file:
            self._load(self._sedfile)

    @property
    def sed(self):
        """
        Get all the SED data.

        :rtype Sed | dict
        """
        return self

    @sed.setter
    def sed(self, values):
        """
        Clear and set the Sed data from a source other than a file

        :param values: SED keys and values to set.
        """
        self.clear()
        self.update(values)

    def get_file(self):
        """
        Get the path of the loaded SED

        :returns: Path of SED file loaded
        :rtype: str
        """
        return self._sedfile

    def _load(self, filepath):
        """
        Load the sed file into memory, removing any commented out lines
        :param filepath: Path to the file to load
        :return:
        """
        if not exists(filepath):
            raise IOError('File {0} not found!'.format(filepath))
        with open(filepath, 'r') as _sed:
            lines = _sed.readlines()
        for line in lines:
            line = line.strip()
            if not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key:
                    self[key] = value or None

    def get_value(self, key_name, default=None, error_if_not_set=False):
        """
        Get a value from the SED.
        If the key is not found and a default is specified, the default is
        returned. If the key is not found and no default was passed, a
        KeyError is raised.

        :param key_name: The SED key
        :type key_name: str
        :param default: A default value to return if the key is not in the SED
        :type default: str
        :param error_if_not_set: Raise an error if the value of the key is
        not set
        :return: The value of the key in the SED.
        :rtype: str
        """
        if key_name in self:
            _value = self[key_name]
            if not _value and error_if_not_set:
                raise ValueError('No value for key \'{0}\' found in SED '
                                 '{1}'.format(key_name, self._sedfile))
            else:
                return _value
        elif default:
            return default
        else:
            raise KeyError('No key \'{0}\' found in SED '
                           '{1}'.format(key_name, self._sedfile))

    def find_keys(self, key_filter):
        """
        Find keys in a SED file based on a regular expression

        :param key_filter: The reggex to match keys on
        :type key_filter: str
        :rtype: list
        """
        matched_keys = []
        for key_name in self.keys():
            if match(key_filter, key_name):
                matched_keys.append(key_name)
        return matched_keys

    def has_site_key(self, key_name):
        """
        Check if the SED has a key defined
        :param key_name: The key to check for
        :returns: `True` is the key is defined, `False` otherwise
        :rtype: bool
        """
        return key_name in self

    @staticmethod
    def get_network_key(network_name):
        """
        Get the Sed network key postfix for a network i.e. services -> IP
        All other networks are <network> -> IP_<network>
        :param network_name: The network name
        :returns: The Sed key postfix to use to look up a nodes network info.
        :rtype: str
        """
        if network_name == 'services':
            return 'IP'
        else:
            return 'IP_{0}'.format(network_name.lower())

    @staticmethod
    def modelid_to_sedid(model_id):
        """
        Convert a modeled node ID to a Sed Id e.g. svc-1 -> svc_node1
        :param model_id: The nodes model ID
        :returns: The prefix of the keys in the Sed that relate to the modeled
         node.
        :rtype: str
        """
        model_id_parts = model_id.split('-')
        return '{0}_node{1}'.format(model_id_parts[0],
                                    model_id_parts[1])

    def subset(self, key_filter):
        """
        Get a subset of the Sed data with the returned data using the SED
        values as keys in the dict.

        :param key_filter: regex group filter
        :returns: Sed object with matching subnet values.
        :rtype: Sed
        """
        matcher = re.compile(key_filter)
        sub_data = Sed(None)
        for _key in self.keys():
            _match = matcher.search(_key)
            if _match:
                sub_data[_match.group(1)] = self.get(_key)
        return sub_data

    def get_node_config(self, node_id):
        """
        Get the Sed node keys/values for a particular node-id e.g svc-1
        The returned Sed object keys are the values from the loaded
        text file and their values are the text file keys

        :param node_id: The node ID e.g. db-1
        :returns: Sed object with matching subnet values.
        :rtype: Sed
        """
        return self.subset('{0}_(.*)'.format(node_id))

    def get_key_for_value(self, value):
        """
        Get the Key for value
        :param value: The value to search for
        :type value: str
        :returns: The Key for the value
        :type: str
        """
        for _key, _value in self.items():
            if _value == value:
                return _key
        return None

    @staticmethod
    def get_last_applied_sed():
        """ Get last applied SED filepath from cmd_arg.log last line """
        cmd_arg_log = "/opt/ericsson/enminst/log/cmd_arg.log"
        if not os.path.exists(cmd_arg_log):
            raise IOError("File %s don't exist" % cmd_arg_log)

        cmd = "/bin/grep '\\-s' %s | tail -n 1" % cmd_arg_log
        cmd_out = exec_process(cmd, use_shell=True).split()

        try:
            index = cmd_out.index('-s')
        except ValueError:
            index = cmd_out.index('--sed')

        sed_path = cmd_out[index + 1]
        if not os.path.exists(sed_path):
            raise IOError("File %s don't exist" % sed_path)
        return sed_path


class EnminstWorking(Sed):  # pylint: disable=too-many-public-methods
    """
    Helper class to manipulate the enminst working config file
    """

    def __init__(self, cfgfile):
        if not exists(cfgfile):
            open(cfgfile, 'a').close()
        super(EnminstWorking, self).__init__(cfgfile)

    def set_site_key(self, key, value):
        """
        Set a key to a value in the working config memory copy
        :param key: The key name
        :param value: The key value
        :return:
        """
        self[key] = value

    def write(self):
        """
        Write the working config memory copy back to file
        :return:
        """
        with open(self._sedfile, 'w') as ofile:
            for _key, _value in self.items():
                ofile.write('{0}={1}\n'.format(_key, _value))


def switch_user(username):
    """
    Callback to switch to a user before executing a command
    :param username: The user to switch to
    :return:
    """
    if username is None:
        return None

    def elevate_cb():
        """
        Switch to a user
        :return:
        """
        try:
            user = pwd.getpwnam(username)
        except KeyError:
            raise NameError('No such user %s' % username)
        uid, gid = user.pw_gid, user.pw_gid

        os.setregid(uid, gid)
        os.setreuid(user.pw_uid, user.pw_uid)

    return elevate_cb


def is_valid_file(parser, arg_name, filename):
    """
    Checks if given filename is real file
    :param parser: parser to communicate errors
    :param arg_name: name of parser arguments
    :param filename: filename to check
    :return: filename if file is valid
    or notifies password about error otherwise
    """
    if not os.path.isfile(filename):
        parser.error("The %s file %s does not exist!" % (arg_name, filename))
    else:
        return filename


def is_valid_hc_list(parser, arg_name, hc_list):
    """
    Checks if given filename is real file
    :param parser: parser to communicate errors
    :param arg_name: name of parser arguments
    :param hc_list: list of hc to check
    :return: hc_list to exclude
    """
    if hc_list != 'multipath_active_healthcheck':
        parser.error("Argument %s limited only to "
                     "multipath_active_healthcheck" % arg_name)
    else:
        return hc_list


def keyboard_interruptable(callback=None):
    """
    Dectorator to mark that if the execution of the method is stopped
    using CTRL-C (KeyboardInterrupt) that a SystemExit error with an exit
    code of 42 (ExitCodes.INTERRUPTED) is raised.

    If a callback function is passed then that function will get called
    before the SystemExit is raised (e.g. that logs some specific message)

    :param callback: The callback function to call, can be None.
    """

    def actual_decorator(interruptable_method):
        """
        Decorator
        :param interruptable_method: Method to wrap
        :return:
        """

        @functools.wraps(interruptable_method)
        def wrapper(*args, **kwargs):
            """
            Wrapper
            :param args: args
            :param kwargs: kwargs
            :return:
            """
            try:
                return interruptable_method(*args, **kwargs)
            except KeyboardInterrupt:
                try:
                    if callback:
                        callback()
                finally:
                    raise SystemExit(ExitCodes.INTERRUPTED)

        return wrapper

    return actual_decorator


def touch(fname):
    """
    Creates filename or updates its access and modified times
    :param fname: filename to touch
    """
    try:
        os.utime(fname, None)
    except OSError:
        open(fname, 'a').close()


def file_modification_date(filename):
    """
    Reads file modification date converts it to datetime
    :param filename: filename to inspect
    :return: datetime of last file modification
    """
    _mtime = os.path.getmtime(filename)
    return datetime.fromtimestamp(_mtime)


def is_physical_environment():
    """
    Check if application runs in cloud environment
    (managed by virtual provider)
    :return: True if cloud environment was detected
    """
    stdout = exec_process('/usr/sbin/dmidecode -s system-manufacturer'.split())
    system_manufacturer = stdout.strip().lower()
    LOG.debug('System manufacturer: {0}'.format(system_manufacturer))
    for provider in CLOUD_MANUFACTURERS:
        if provider in system_manufacturer:
            return False
    return True


def query_strong_yes_no(question):
    """
    Asks a YeS/no question via raw_input() and return their answer.
    Case sensitivity for YeS response is checked.
    :param question string that is presented to the user.
    :type question : str
    :return True if the answer was "YeS" or False if the the answer was "no"
    :rtype bool
    """
    valid_yes = ["YeS"]
    valid_no = ["no", "n"]
    prompt = " [YeS] to confirm or [no|n] to cancel"

    while True:
        LOG.info(question + prompt)
        user_answer = raw_input()
        LOG.info("Your answer was: {0}".format(user_answer))
        if user_answer in valid_yes:
            return True
        case_insensitive_answer = user_answer.lower()
        if case_insensitive_answer in valid_no:
            return False
        else:
            LOG.info("Please respond with " + prompt)


def strong_confirmation_or_exit(assumeyes, operation_label, operation_message):
    """
    Asks user for confirmation before operation starts.
    If user do not wish to continue then exits from application.
    :param assumeyes: decides if confirmation is needed
    :param operation_label: string to print in front of message
    """
    if assumeyes:
        LOG.info("Option -y|--assumeyes passed to the script. "
                 "Skipped asking for confirmation.")
        return

    LOG.info(operation_message)
    if query_strong_yes_no("Do you wish to continue?"):
        LOG.info(operation_label + " was confirmed by the user")
    else:
        LOG.info(operation_label + " stopped by the user")
        raise SystemExit(ExitCodes.OK)


def time_delta(start_time, end_time=None):
    """
    Get the delta between 2 timestamps as a tuple of (hours, minutes, seconds)
    :param start_time: The start timestamp
    :param end_time: The end timestamp. If ``None`` the current
    ``datetime.now()`` is used when the function is called.

    :returns: A tuple containing the time delta in (hours, minutes, seconds)
    :rtype: tuple(int, int int)
    """
    if end_time:
        delta_time = end_time - start_time
    else:
        _now = datetime.now().replace(microsecond=0)
        delta_time = _now - start_time
    hours, remainder = divmod(delta_time.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    hours += delta_time.days * 24
    return hours, minutes, seconds


def litp_backup_state_cron(cron_file, backup_dir):
    """
    Creates cron.d file to run script to backup litp state
    """

    cron_str = '*/10 * * * * root ' \
               '[ -f /opt/ericsson/nms/litp/bin/litp_state_backup.sh ] && ' \
               '/opt/ericsson/nms/litp/bin/litp_state_backup.sh ' + \
               backup_dir + '\n'

    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir)
        except OSError:
            LOG.exception('An error occurred creating directory {0}'
                          .format(backup_dir))
            raise

    with open(cron_file, 'w') as _writer:
        _writer.write(cron_str)


def cleanup_java_core_dumps_cron(cron_file):
    """
    Creates cron.daily file to run script to cleanup java dumps & core files
    :param cron_file: cron file to write command into
    :return:
    """

    cron_str = '#!/bin/sh\n' \
               'find /ericsson/enm/dumps -type f -mtime +30 ' \
               r'\( -name \*.hprof -o -name core.\* \) -exec rm -f {} \; ' + \
               '\n'

    with open(cron_file, 'w') as _writer:
        _writer.write(cron_str)
    os.chmod(cron_file, 0755)


def create_san_fault_check_cron(cron_file):
    """
    Creates cron.d file to run script to check SAN alerts
    """

    cron_str = '*/15 * * * * root /opt/ericsson/enminst/bin/' \
               'san_fault_check.sh \n'

    with open(cron_file, 'w') as _writer:
        _writer.write(cron_str)


def create_nasaudit_errorcheck_cron(cron_file):
    """
    Creates cron.d file to run script to check NAS Audit errors
    """

    cron_str = '0 */4 * * * root /opt/ericsson/enminst/bin/' \
               'nasaudit_error_check.sh \n'

    with open(cron_file, 'w') as _writer:
        _writer.write(cron_str)


def sanitize(raw_string):
    """
    Sanitizes a string by inserting escape characters to make it
    shell-safe.

    :param raw_string: The string to sanitise
    :type raw_string: string

    :returns: The escaped string
    :rtype: string
    """
    spec_chars = '''"`$'(\\)!~#<>&*;| '''
    escaped = ''.join([c if c not in spec_chars else '\\' + c
                       for c in raw_string])
    return escaped


def db_node_removed():
    """
    Is there a db node to be removed in the DEPLOYMENT_DIFF_OUTPUT file
    as part of this upgrade
    :return: bool whether there is a db node to be removed
    """
    db_node_regex = '^y /deployments/.+/clusters/db_cluster/nodes/[^/]+$'
    config = read_enminst_config()
    deploy_diff_output_file = config.get(DEPLOYMENT_DIFF_OUTPUT)
    if os.path.exists(deploy_diff_output_file):
        with open(deploy_diff_output_file, 'r') as _reader:
            for line in _reader.readlines():
                _match = re.match(db_node_regex, line)
                if _match:
                    return True
    return False


def create_ssh_client(host, username, password, port=22):
    """
    Create ssh connection and return paramiko ssh client object
    :param host server to connect to
    :param username server to authenticate as
    :param password password for authentication
    :param port server port to connect to
    """
    LOG.debug('Create ssh connection to {0}@{1}'.format(username, host))
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password, port=port)
    except Exception as err:
        LOG.exception("An error happened while trying to connect to {0}@{1}"
                      " : {2}".format(username, host, err))
        raise
    return ssh


def _pexpect_execute_remote_command(command, password,
                                    timeout=10, tries=2):
    """
    Executes a provided command using pexpect to handle password handling
    :param command: command to be run
    :type str:
    :param password: password for user
    :type str:
    :param timeout: pexpect timeout
    :type int:
    :param tries: number of times to attempt to run the command
    :type int:
    :return: output from command
    :rtype str:
    """
    if not isinstance(timeout, int) and not isinstance(tries, int):
        raise TypeError("A supplied argument is "\
                        "not of the correct type: {0}, {1}"
                        .format(timeout, tries))
    while tries > 0:
        try:
            child = pexpect.spawn(command)
            response = child.expect(['password: ',
                                     'continue connecting (yes/no)?'],
                                    timeout=timeout)
            if response == 0:
                child.sendline(password)
                return _handle_pexpect_response(child)
            elif response == 1:
                child.sendline('yes')
                child.expect('password: ', timeout=timeout)
                child.sendline(password)
                return _handle_pexpect_response(child)
        except (IOError, OSError, pexpect.EOF, pexpect.TIMEOUT):
            tries -= 1
        except InvalidCredentialsError:
            raise InvalidCredentialsError()
        except pexpect.ExceptionPexpect as err:
            raise IOError("Pexpect Error: {0}".format(err))
    raise IOError('Command Failed: {0}'.format(command))


def _handle_pexpect_response(child, timeout=10):
    """
    Handles pexpect response and validates credentials
    :param child: pexpect spawn instance
    :timeout: pexpect timeout
    :return: output from child
    """
    response = child.expect([pexpect.EOF, 'password: '], timeout=timeout)
    if response == 0:
        return _parse_pexpect_return_code(child.before)
    elif response == 1:
        raise InvalidCredentialsError()


def _parse_pexpect_return_code(response):
    """
    Parses the response from a pexpect command
    to check it's return code.
    If Return Code is 0 - returns response
    If Return code not 0 - raises IOError
    :param response: Response from pexpect command
    :type str:
    :return: response after parsing
    :rtype str:
    """
    response = response.strip("\r\n")
    response_list = response.split("\r\n")
    for item in response_list:
        if re.search(r'Return Code:(|.)\s0\b', item):
            response_list.remove(item)
            return "\r\n".join(response_list)
        elif re.search(r'Return Code:', item):
            response_list.remove(item)
            raise IOError("\r\n".join(response_list))
    # Query not set up to check Return Code, so just return
    return "\r\n".join(response_list)


def ping(address):
    """
    Ping an address
    :param address: IPV4 address to ping
    :type address: str
    :returns: True if the address is pingable, False otherwise
    :rtype bool
    """
    try:
        exec_process(['ping', '-c', '1', address])
        return True
    except IOError:
        return False


class Decryptor(object):
    """
    Class to decrypt login credentials stored in password file
    """

    SECURITY_CONF_FILE_PATH = '/etc/litp_security.conf'
    FILE_DEXIST_ERR = '{0} file does not exist'.format(SECURITY_CONF_FILE_PATH)

    def __init__(self):
        super(Decryptor, self).__init__()

    def get_key_and_password_files(self):
        """
        Read the key and password files from litp security configuration file
        :return: tuple: path to key file, path to password file
        """
        if not os.path.exists(self.SECURITY_CONF_FILE_PATH):
            raise os.error(self.FILE_DEXIST_ERR)
        parser = SafeConfigParser()
        parser.read(self.SECURITY_CONF_FILE_PATH)

        return parser.get("keyset", "path"), parser.get("password", "path")

    def decrypt(self, key_file, data):
        """
        Decript the passed in data with a provided key
        :param key_file: File that stores the key used to encrypt/decrypt data
        :param data: Encrypted data
        :return: Decrypted data
        """

        key = self.read_key(key_file)

        decryptor = AES.new(key, AES.MODE_CFB, '0' * AES.block_size,
                            segment_size=128)

        return decryptor.decrypt(standard_b64decode(data)).rstrip(chr(3))

    def get_password(self, service, user):
        """
        Retrieve the user's password for the provided service
        :param service: Service
        :param user: User
        :return: Returns the decripted password
        """

        key_file, pass_file = self.get_key_and_password_files()

        config_parser = SafeConfigParser()
        config_parser.optionxform = str
        config_parser.read(pass_file)
        b64_username = standard_b64encode(user).replace('=', '')
        try:
            enc_password = config_parser.get(service, b64_username)
        except NoOptionError:
            enc_password = config_parser.get(service, user)
        return self.decrypt(key_file, enc_password)

    @staticmethod
    def read_key(key_file):
        """
        Reads the stored key from the key file
        :param key_file: path to key file
        :return: encryption key stored in file
        """
        with open(key_file, 'r') as _reader:
            key = standard_b64decode(_reader.readlines()[0])
        return key


class Redfishtool(object):
    """
        Class to run Redfish REST requests against a Redfish API
    """
    retries_exhausted_message = "Max number of retries exhausted"
    decompress_error_message = "Decompressing response failed."
    CLOUD_REDFISH_PATH = '/opt/ericsson/nms/litp/bin/redfishtool.cloud'

    @staticmethod
    def is_cloud_env():
        """
        Check the current env. Use Redfish Cloud tool if
        it is cloud env.
        """
        try:
            if os.path.isfile(Redfishtool.CLOUD_REDFISH_PATH) and \
                    os.access(Redfishtool.CLOUD_REDFISH_PATH, os.X_OK):
                return True
        except OSError:
            return False
        else:
            return False

    def login(self, ilo_address, username, password):
        """
        Create a Redfish Client at the ip address given and
        logs in with the given username and password.
        :param ilo_address: iLO address
        :param username: iLO username
        :param password: iLO password
        :return: redfish_client
        :type: redfish_client
        """
        preamble = 'login: '
        if self.is_cloud_env():
            redfish_tool = imp.load_source('redfishtool',
                                           self.CLOUD_REDFISH_PATH)

            redfish_obj = redfish_tool.RedfishClient(
                base_url=ilo_address, username=username,
                password=password, default_prefix='/redfish/v1')
        else:
            redfish_obj = redfish.redfish_client(
                base_url='https://' + ilo_address, username=username,
                password=password, default_prefix='/redfish/v1')
        try:
            redfish_obj.login()
            return redfish_obj
        except redfish.rest.v1.InvalidCredentialsError as exception:
            self.exception_handler(exception, preamble,
                                   "Invalid credentials provided for BMC")
        except RetriesExhaustedError as exception:
            self.exception_handler(exception, preamble,
                                   self.retries_exhausted_message)

    def toggle_power(self, ilo_address, username, password, reset_type):
        """
        Login and Toggle power on the node
        :param ilo_address: iLO address
        :param username: iLO username
        :param password: iLO password
        :param reset_type: value to be set for ResetType parameter in the body
        :return: Output from redfish rest call
        :rtype: str
        """

        preamble = '._toggle_power: '
        redfish_obj = self.login(ilo_address, username, password)
        try:
            body = {"ResetType": reset_type}
            response = redfish_obj.post("/redfish/v1/Systems/1/Actions"
                                        "/ComputerSystem.Reset/", body=body)
        except RetriesExhaustedError as exception:
            self.exception_handler(exception, preamble,
                                   self.retries_exhausted_message)
        except DecompressResponseError as exception:
            self.exception_handler(exception, preamble,
                                   self.decompress_error_message)
        finally:
            Redfishtool.logout(redfish_obj)

        if response.status == 200:
            LOG.debug(preamble + "Power {0} Outcome: Success"
                              .format(reset_type))
            return response.status
        else:
            error = self.get_error_message(response)
            if response.status == 400 and \
                    'InvalidOperationForSystemState' in error:
                msg = "Power {0} Outcome: system is already in power {0} " \
                      "state".format(reset_type)
                LOG.debug(preamble + msg)
            else:
                msg = "Power {0} Outcome: Failure, status:{1} : '{2}'".format(
                    reset_type, response.status, error)
                self.exception_handler(msg, preamble, msg)

    def _get_system_json(self, ilo_address, username, password, preamble):
        """
        Get the JSON associated with System 1
        :param ilo_address: iLO address
        :param username: iLO username
        :param password: iLO password
        :param preamble: Logging preamble
        :return: JSON associated with /redfish/v1/Systems/1
        :type: dict
        """
        redfish_obj = self.login(ilo_address, username, password)
        try:
            response = redfish_obj.get("/redfish/v1/Systems/1")
        except RetriesExhaustedError as exception:
            self.exception_handler(exception, preamble,
                                   self.retries_exhausted_message)
        except DecompressResponseError as exception:
            self.exception_handler(exception, preamble,
                                   self.decompress_error_message)
        finally:
            Redfishtool.logout(redfish_obj)
        return response

    def power_status(self, ilo_address, username, password):
        """
        Returns Power status of a blade.
        :param ilo_address: iLO address
        :param username: iLO username
        :param password: iLO password
        :return: status True if powered on, False if powered off
        :type: boolean
        """

        preamble = '.power_status: '
        response = self._get_system_json(ilo_address, username,
                                    password, preamble)
        if response.status == 200:
            LOG.debug(preamble + "Get Power Status: Success")
            try:
                power_status_response = json.loads(response.text)
            except UnicodeDecodeError as exception:
                LOG.warn('Problem decoding power status response: {0}'
                         .format(str(exception)))
                power_status_response = json.loads(
                    response.text, "ISO-8859-1")
            return power_status_response["PowerState"] == "On"
        else:
            error = self.get_error_message(response)
            msg = "Power Status Outcome: Failure, status:{0} : '{1}'".format(
                response.status, error)
            self.exception_handler(msg, preamble, msg)

    def finished_post(self, ilo_address, username, password):
        """
        Returns PostState of a blade.
        :param ilo_address: iLO address
        :param username: iLO username
        :param password: iLO password
        :return: status True if PostState is FinishedPost,
                False if another PostState
        :type: boolean
        """
        preamble = '.post_state: '
        response = self._get_system_json(ilo_address, username,
                                         password, preamble)
        if response.status == 200:
            LOG.debug(preamble + "Get Post State: Success")
            try:
                json_data = json.loads(response.text)
            except UnicodeDecodeError as exception:
                LOG.warn('Problem decoding PostState response: {0}'
                         .format(str(exception)))
                json_data = json.loads(
                    response.text, "ISO-8859-1")
            if "Hpe" in json_data["Oem"]:
                return json_data["Oem"]["Hpe"]["PostState"] == "FinishedPost"
            return json_data["Oem"]["Hp"]["PostState"] == "FinishedPost"
        else:
            error = self.get_error_message(response)
            msg = "PostState Outcome: Failure, status:{0} : '{1}'".format(
                response.status, error)
            self.exception_handler(msg, preamble, msg)

    @staticmethod
    def exception_handler(exception, preamble, message):
        """
        Logs the message and raises a Redfish Tool Exception
        """
        LOG.error(preamble + message)
        raise RedfishToolException(exception)

    @staticmethod
    def logout(redfish_obj):
        """
        logs out from the redfish api
        """
        try:
            redfish_obj.logout()
        except BadRequestError:
            excep_msg = "Bad request error. Invalid session resource"
            LOG.error("log out :" + excep_msg)

    @staticmethod
    def get_error_message(response):
        """Get error message
        :param response: Response from redfish rest APIs
        """
        try:
            response_dict = response.dict
            extended_info = response_dict["error"]["@Message.ExtendedInfo"][0]
            if "Message" in extended_info:
                message = str(extended_info["Message"])
            else:
                message = str(extended_info["MessageId"])
            return message
        except (KeyError, ValueError):
            return response


class Translator(object):  # pylint: disable=R0903
    """
    Object to allow for message translation
    """

    def __init__(self, module):
        self.module = module
        self.tran = None
        self.setup()

    def _(self, msg):
        """
        Get the translated text from the given key
        :param msg: Key of desired message
        :return: Translated text based on locale
        """
        if isinstance(self.tran, NullTranslations):
            self.setup()
        return self.tran.ugettext(msg)

    def _u(self, msg):  # pylint: disable=C0103
        """
        Get the uppercased text from the given key
        :param msg: Key of desired message
        :return: Translated text based on locale
        """
        return self._(msg).upper()

    def setup(self):
        """
        Set the locale directory where the translations are stored
        :return:
        """
        locale_dir = '/opt/ericsson/enminst/share/locale'
        if 'ENMINST_LOCALE_DIR' in os.environ:
            locale_dir = os.environ.get('ENMINST_LOCALE_DIR')
        self.tran = gettext.translation(
            self.module, localedir=locale_dir, fallback=True, languages=['en'])


class RHELUtil(object):
    """
    Class which provides RHEL upgrade functions
    """

    def __init__(self, repo_root):
        self.repo_root = repo_root
        self.log = logging.getLogger('enminst')

    @staticmethod
    def get_current_version():
        """
        Return the current version of RHEL
        """
        with open('/etc/redhat-release') as rh_rel:
            match_str = r'(\s\d\.\d{1,2}(\.\d{1,4})?\s)'
            data = rh_rel.readline()
            current = re.search(match_str, data)
            return current.groups()[0].lstrip().rstrip()

    @staticmethod
    def get_latest_version():
        """
        Return the latest version of RHEL specified in config
        """
        return read_enminst_config().get('rhel7_ver')

    def is_latest_version(self):
        """
        Check that the OS is latest version of RHEL specified
        """
        latest = False
        if RHELUtil.get_current_version() == RHELUtil.get_latest_version():
            latest = True

        if latest and \
                os.path.isdir('{0}/{1}'.format(self.repo_root,
                                               RHELUtil.get_latest_version())):
            return True
        return False

    def ensure_version_symlink(self, version):
        """
        Ensure correct symlink for RHEL version
        """
        major_ver = version.split('.')[0]
        symlink_path = '{0}/{1}'.format(self.repo_root, major_ver)
        if os.path.isdir(symlink_path):
            self.log.debug('Unlinking old RHEL symlink {0}'
                           .format(symlink_path))
            os.unlink(symlink_path)

        self.log.debug('Creating symlink to RHEL {0} repositories {1}'
                       .format(version, symlink_path))
        cmd = 'ln -sf {0}/{1} {2}'.format(self.repo_root, version,
                                          symlink_path)
        _handle_exec_process(cmd, 'Creating symlink to RHEL '
                                  'repositories', 'Problem creating '
                                  'symlink to RHEL repositories')

    def ensure_version_manifest(self, version):
        """
        Ensures puppet enforces the current RHEL version's directory
        structure and symbolic links
        """
        self.log.debug('Ensuring Puppet manifests contain RHEL {0} paths'
                       .format(version))
        manifest_path = '/opt/ericsson/nms/litp/etc/puppet/modules/' \
                        'litp/manifests/ms_node.pp'
        cached_catalog_path = '/var/lib/puppet/client_data/catalog/' \
                              '{0}.json'.format(socket.gethostname().lower())
        latest = '{0}/{1}'.format(self.repo_root, version)

        for pp_path in [manifest_path, cached_catalog_path]:
            with open(pp_path, 'r') as pp_man:
                data = pp_man.read()
                match_str = r'({0}/\d\.\d{{1,2}})' \
                    .format(self.repo_root.replace('/', r'\/'))
                current = re.search(match_str, data)

                if current and current.groups()[0] != latest:
                    current = current.groups()[0].replace('/', r'\/')
                    latest_replace = latest.replace('/', r'\/')
                    cmd = 'sed -i s/{0}/{1}/g {2}' \
                        .format(current, latest_replace, pp_path)
                    _handle_exec_process(cmd, 'Ensuring puppet enforces RHEL '
                                              '{0} paths in file {1}'
                                         .format(version, pp_path),
                                         'Problem ensuring puppet '
                                         'enforces RHEL {0} paths in file {1}'
                                         .format(version, pp_path))

    def clean_repos(self):
        """
        Removes old RHEL repositories
        """
        config = read_enminst_config()
        valid_major_vers = []
        valid_repos = []
        for key, val in config.items():
            if re.match('^rhel[0-9]+_ver$', key):
                if val.split('.')[0] not in valid_major_vers:
                    valid_major_vers.append(val.split('.')[0])
                valid_repos.append(val)
        for major_ver in valid_major_vers:
            for repo in glob.glob('{0}/{1}.*'
                                  .format(self.repo_root, major_ver)):
                if (repo.split('/')[-1] not in valid_repos and
                    re.match('^[0-9]+\\.[0-9]+$', repo.split('/')[-1]) and
                    os.path.isdir(repo)):
                    self.log.info('Removing {0} '.format(repo))
                    try:
                        shutil.rmtree(repo)
                    except OSError:
                        pass

BASIC_ORDINALS = {
    1: "st",
    2: "nd",
    3: "rd",
    11: "th",
    12: "th",
    13: "th",
}


def to_ordinal(number):
    """
    Concatenates a given number with an appropriate ordinal
    :param number:
    :return: string number with ordinal postfix
    """
    return "%s%s" % (number, BASIC_ORDINALS.get(int(str(number)[-2:]),
                             BASIC_ORDINALS.get(int(str(number)[-1:]), "th")))


class InvalidCredentialsError(Exception):
    """
    Simple Exception to indicate an
    Invalid User or Password
    """
    pass


def set_pib_param(name, value, server=None):
    """
    Set a Platform Integration Bridge property
    :param name: name of the pib property
    :param value: value or the pib property
    :param server: app_server_address
    :return stdout string
    """
    if not server:
        server = DEFAULT_PIB_APP_SERVER_ADDRESS

    pib_cmd = PIB_CMD + ' update --app_server_address=' + server + \
    ' --name=' + name + ' --value=' + value

    LOG.info("Setting pib property: {0} to {1}".format(name, value))
    LOG.debug("executing : {0}".format(pib_cmd))
    return exec_process(pib_cmd.split()).strip()


def read_pib_param(name, server=None):
    """
    Read a Platform Integration Bridge property
    :param name: name of the pib property
    :param value: value or the pib property
    :param server: app_server_address
    :return stdout string
    """
    if not server:
        server = DEFAULT_PIB_APP_SERVER_ADDRESS

    pib_cmd = PIB_CMD + ' read --app_server_address=' + server + \
    ' --name=' + name

    LOG.info("Reading pib property: {0}".format(name))
    LOG.debug("executing : {0}".format(pib_cmd))
    return exec_process(pib_cmd.split()).strip()


def create_pib_param_set_cron(name, value, delta, cron_file):
    """
    Creates cron.d file to run script to reset pib_param
    :param name: name of the pib property
    :param value: value for the pib property
    :param delta: minutes in future when cron job will trigger,
                  should be int <= 60
    :param cron_file: name of the cron file to create
    """
    full_cron_path = '/etc/cron.d/' + cron_file
    _now = datetime.now()
    _now_plus_delta = _now + timedelta(minutes=delta)
    cron_minutes = _now_plus_delta.minute
    cron_str = str(cron_minutes) + ' * * * * root ' + \
    'PYTHONPATH=' + ENMINST_HOME + 'lib ' + ENMINST_HOME + 'bin/pib_set.py ' +\
    name + ' ' + value + ' ' + \
    cron_file + ' > /tmp/pib_cron.log 2>&1\n'

    LOG.info('Creating cron ' + full_cron_path + ' entry=' + cron_str)

    with open(full_cron_path, 'w') as _writer:
        _writer.write(cron_str)


class RedfishToolException(Exception):
    """
    Simple Exception to indicate that an exception
    has been raised from RedfishTool
    """
    pass


def is_exist_edp_sed_file():
    """
    Returns True if EDP generated the SED file /software/vol1/, False
    otherwise
    :return: bool
    """

    if os.path.exists(EDP_SED_FILEPATH) and os.path.isfile(EDP_SED_FILEPATH):
        return True

    return False


def get_edp_generated_sed(regex_str=''):
    """
    Returns the values from the EDP generated SED if provided a regex key,
    returns whole sed otherwise
    :params regex_str: optional regex to match for in the Sed
    :type: str
    :return: str
    """

    if not is_exist_edp_sed_file():
        LOG.warning('SED file "{0}" not found'.format(EDP_SED_FILEPATH))
        return {}

    sed = Sed(EDP_SED_FILEPATH)
    if regex_str:
        sed_keys = sed.find_keys(regex_str)
        return dict(
            (sed_key, sed.get_value(sed_key))
            for sed_key in sed_keys if sed.get_value(sed_key)
        )

    return sed


def get_nas_type_sed(sed):
    """
    Get the NAS type when a Sed instance (sed file) is passed in.
    If this is not present, return 'veritas'.
    :params sed: Sed
    :return: str
    """
    try:
        result = sed.get_value('nas_type')
    except KeyError:
        result = 'veritas'
    return result


def get_nas_type(litp_rest_client):
    """
    Gets the NAS type from the model. If this is not present, return 'veritas'.
    :param litp_rest_client: LitpRestClient instance
    :return: nas_type string
    """
    nas_info = litp_rest_client.get_all_items_by_type(
        '/infrastructure/storage/storage_providers/', 'sfs-service', [])
    try:
        nas_type = nas_info[0]['data']['properties']['nas_type']
    except (KeyError, IndexError):
        nas_type = 'veritas'
    return nas_type


def is_env_on_rack():
    """
    Check if Litp model indicate RACK deployment type,
    returns True is Env is RACK deployment
    :params:
    :return: bool
    """
    from h_litp.litp_rest_client import LitpRestClient, LitpException

    litp_rest_cli = LitpRestClient()

    litp_property = \
        "/software/items/config_manager/global_properties/enm_deployment_type"
    property_val = None
    try:
        items = litp_rest_cli.get(litp_property, log=False)
        property_val = items["properties"]["value"]
    except LitpException:
        LOG.info('enm_deployment_type not found in litp model ')

    return True if property_val is not None and \
                   re.match(r'.*ENM_On_Rack_Servers$', property_val) \
           else False


def migrate_cleanup_cmd():  # pylint: disable=too-many-locals
    """
    Migrate vm-service cleanup_command property in LITP model
    :return: None
    """
    from h_litp.litp_rest_client import LitpRestClient
    from h_litp.litp_utils import is_custom_service

    LOG.debug("Migrate cleanup_command property in LITP Model.")
    litp_rest_cli = LitpRestClient()

    vsvcs = litp_rest_cli.get_all_items_by_type('/software/services',
                                                'vm-service', [])

    if not vsvcs:
        return

    pattern = r'^/sbin/service ' + \
              r'(?P<sname>[^ ]+) +(?P<action>[^ ]+)(?P<remainder>.*)$'
    regexp = re.compile(pattern)

    vm_utils_cmd = os.path.join(os.sep, 'usr', 'share',
                                'litp_libvirt', 'vm_utils')

    dd_path = os.path.join(os.sep, 'opt', 'ericsson', 'enminst', 'runtime',
                           'enm_deployment.xml')

    for vsvc in vsvcs:
        mock_svc_element = {'id': vsvc['data']['id']}
        if not is_custom_service(mock_svc_element, dd_path):
            continue
        sname = None
        action = None
        remainder = ''
        vcmd = vsvc['data']['properties']['cleanup_command']
        pattern_match = regexp.search(vcmd)
        if pattern_match:
            parts = pattern_match.groupdict()
            if parts:
                if 'sname' in parts.keys():
                    sname = parts['sname']
                if 'action' in parts.keys():
                    action = parts['action']
                if 'remainder' in parts.keys():
                    remainder = parts['remainder']

                if sname and action and action != 'stop':
                    new_vcmd = '{0} {1} stop-undefine{2}'.format(
                                            vm_utils_cmd, sname, remainder)
                    properties = {'cleanup_command': new_vcmd}
                    LOG.debug('Migrating {0} to {1}'.format(vsvc['path'],
                                                        new_vcmd))
                    litp_rest_cli.update(vsvc['path'], properties)


def get_enable_cron_on_expiry_cmd(pam_auth_file):
    """
    Get the command string to update kickstart to enable crons on password
    expiry.
    :param pam_auth_file: Relevant RHEL6 or RHEL7 pam auth file.
    :type pam_auth_file: string
    :return: nested sed command
    :rtype: string
    """
    return 'grep pam_unix.so {0}; if [ $? -ne 0 ]; then '\
        'sed -i.bak \'$i grep pam_access.so {1}; if [ $? -ne 0 ]; then '\
        'sed -i.bak '\
        '\'\\\'\'s/account     required      pam_unix.so/account'\
        '     required      pam_access.so\\\\n'\
        'account  [success=1 default=ignore] pam_succeed_if.so'\
        ' service in crond quiet use_uid\\\\n'\
        'account     required      pam_unix.so /g\'\\\'\' {1}; fi\''\
        ' {0}; fi'.format(KICKSTART_ERB, pam_auth_file)


def _copy_as_template(sed, banner_key, target):
    """
    Copy message (optional) file (ssh login banner or motd) from location
    set in SED to LITP files directory.

    :param sed: ENM Site Engineering Description file
    :param banner_key: either "custom_login_banner" or "custom_motd_banner"
    SED format is: custom_motd_banner=file://<path>
                   custom_login_banner=file://<path>
    e.g:
    custom_motd_banner=file:///var/tmp/motd_custom_banner
    custom_login_banner=file:///var/tmp/ssh_custom_banner
    :param target: Target file, either
    "issue.net.custom" for "custom_login_banner" or
    "motd.custom" for "custom_motd_banner"

    :return: True if a custom file was copied into the LITP files
    directory, False otherwise.
    If the custom message file matches an existing target file in the
    LITP templates directory, no changes are made i.e return False
    """
    banner_file = None
    if sed.has_site_key(banner_key):
        banner_file = sed.get_value(banner_key)

    _diff = False
    if banner_file:
        if banner_file.startswith('file://'):
            banner_file = banner_file.replace(
                'file://', '')
        dest_file = join(LITP_ERB_TEMPLATES, target)
        if exists(dest_file):
            _diff = filecmp.cmp(banner_file, dest_file, False)
        else:
            _diff = True

        if _diff:
            shutil.copyfile(banner_file, dest_file)
    return _diff


def copy_custom_banners(cfg):
    """
    Copies custom SSH login banner and/or motd message so LITP can sync
    these out to the peers/VMs

    Looks for 'custom_login_banner' and 'custom_motd_banner' entries in
    the SED. If either of those are set then the files are copied to
    /opt/ericsson/nms/litp/etc/puppet/modules/litp/files/ and renamed
    to
        motd.custom
        issue.net.custom

    :param cfg: upgrade configuration
    """
    _sed = Sed(cfg.sed_file)
    _copy_as_template(_sed,
                      'custom_login_banner',
                      'issue.net.custom')
    _copy_as_template(_sed,
                      'custom_motd_banner',
                      'motd.custom')
