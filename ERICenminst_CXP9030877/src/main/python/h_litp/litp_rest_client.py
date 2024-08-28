# pylint: disable=C0302
"""
REST api for LITP deployment model actions
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

import httplib
import logging
import os
import pwd
import socket
import sys
import textwrap
from argparse import ArgumentParser
from base64 import encodestring
from collections import defaultdict
from hashlib import md5
from json import dumps, loads
from os.path import exists
from time import time, sleep

from h_litp.litp_utils import UNIX_CONNECTION
from h_litp.litp_utils import get_connection_type
from h_litp.litp_utils import read_litprc, LitpException, LitpObject
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import Formatter, ExitCodes, keyboard_interruptable


class PlanWatcherException(Exception):
    """
    Plan operation failed.
    """
    pass


class UnixSocketConnection(httplib.HTTPConnection):
    """
    Object to substitute TCP/IP transport with a Unix socket.
    """

    def __init__(self, path):
        self.path = path
        # '' is a placeholder
        httplib.HTTPConnection.__init__(self, '')

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)


class PlanMonitor(object):
    """
    Class to monitor a plan
    """
    TASKS_STATES = ['Initial', 'Running', 'Success', 'Failed', 'Stopped']

    def __init__(self, client=None, verbose=False):
        self.mainlog = init_enminst_logging(logger_name='enminst')
        if client:
            self.litp = client
        else:
            self.litp = LitpRestClient()
        self.phases = {}
        self.phase_tasks = {}
        self.task_state_counts = defaultdict(int)
        # At the moment verbose does nothing, it's left here as a hook.
        self._verbose_output = verbose

    def monitorinfo(self, message):
        """
        Log a monitor message
        :param message: The message to log
        :return:
        """
        self.mainlog.info(message)

    def error(self, message):
        """
        Log an error message
        :param message: The message to log
        :return:
        """
        self.mainlog.error(message)

    def merge_model(self, root, initial=False):
        """
        Merge the previously read model with a newly read version
        :param root: The root element of the new model
        :param initial: Flag to indicate if this is the first merge or not
        """
        self.task_state_counts.clear()
        return self._do_phasetask_merge(root, initial=initial)

    @staticmethod
    def format_task(task, from_state=None):
        """
        Format a string with the task info

        :param task: The task to format
        :param from_state: The previpus state of the task
        :returns: Formatted text about the task.
        :rtype: str[]
        """

        def format_state_string(_state):
            """
            Colour format a state string
            :param _state: The state value
            :returns: Coloured state string
            """
            if _state in Formatter.PLAN_STATE_COLORMAP:
                task_color = Formatter.PLAN_STATE_COLORMAP[_state]
            else:
                task_color = Formatter.PLAN_STATE_COLORMAP['default']
            return Formatter.format_color(_state, task_color)

        str_state = format_state_string(task.state)
        if from_state:
            psc = format_state_string(from_state)
            task_state = '{pstate}>{state}'.format(pstate=psc, state=str_state)
        else:
            task_state = '{state}'.format(state=str_state)
        task_state = 'Task: ' + task_state
        infostring = [task_state, '  Item: ' + task.task_item]

        infoprefix = '  Info: '
        pad = ' ' * len(infoprefix)
        wlines = textwrap.wrap(task.description, 53)
        infostring.append(infoprefix + wlines[0])
        for line in wlines[1:]:
            infostring.append(pad + line)
        return infostring

    def _do_phasetask_merge(self, node, initial=False):
        """
        Merge one model with another
        :param node: The point in the model to state the merge from
        :param initial: If this is the first time the modelhas been read then
        set this to `True`
        :return:
        """
        state_changes = False
        if node.item_type == 'phase':
            self.phases[node.path] = node.item_id
        elif node.item_type == 'task':
            task_phase = node.parent.parent.item_id
            if task_phase not in self.phase_tasks:
                self.phase_tasks[task_phase] = {}

            self.task_state_counts[node.state] += 1

            if not initial and node.item_id in self.phase_tasks[task_phase]:
                old_task = self.phase_tasks[task_phase][node.item_id]
                ostate = old_task.state
                if node.state != ostate:
                    state_changes = True
                    for line in self.format_task(node, from_state=ostate):
                        self.monitorinfo(line)

            self.phase_tasks[task_phase][node.item_id] = node

        for child in node.children.values():
            if self._do_phasetask_merge(child):
                state_changes = True

        return state_changes

    def get_phase_ids(self):
        """
        Get a list of phases by ID
        :return:
        """
        return sorted(self.phases.values())

    def get_phase_tasks_ids(self, phase_id):
        """
        Get a list of task IDs in a particular phase
        :param phase_id: The phase ID
        :return:
        """
        return sorted(self.phase_tasks[phase_id])

    def get_phase_task(self, phaseid, taskid):
        """
        Get a task
        :param phaseid: The phase the task is in
        :param taskid: The task ID
        :return:
        """
        return self.phase_tasks[phaseid][taskid]

    def get_active_phases(self):
        """
        Get a list of IDs of phases with running tasks.
        :return: sorted list of active phases' IDs
        :rtype: list
        """
        active_phases = set()
        for phaseid, tasks in self.phase_tasks.items():
            for task in tasks.values():
                if task.state.lower() == 'running':
                    try:
                        active_phases.add(int(phaseid))
                    except ValueError:
                        pass
        return sorted(active_phases)

    def show_model(self):
        """
        Log the model
        :return:
        """
        for phaseid in self.get_phase_ids():
            self.monitorinfo('Phase {id}'.format(id=phaseid))
            for taskid in self.get_phase_tasks_ids(phaseid):
                task = self.get_phase_task(phaseid, taskid)
                for fmtline in self.format_task(task):
                    self.monitorinfo(fmtline)

    def get_task_state_count(self):
        """
        Get a total count of each task type in the plan
        :return:
        """
        return self.task_state_counts

    def is_plan_running(self):
        """
        Get if the plan is running or not
        :return:
        :rtype: bool
        """
        state = self.litp.get_plan_state('plan')
        return state.lower() == 'running'

    def show_failed_plan(self, active_phases=None):
        """
        Log a failed tasks in a plan
        :param active_phases: A list of active phases with failed tasks
        :type active_phases: list
        :return:
        """
        if active_phases is None:
            active_phases = []
        total = 0
        logstrings = []
        for phaseid, tasks in self.phase_tasks.items():
            suppress_phase_header = False
            for task in tasks.values():
                if task.state.lower() == 'failed':
                    if not suppress_phase_header:
                        logstrings.append('Phase-{0}'.format(phaseid))
                        suppress_phase_header = True
                    logstrings.extend(self.format_task(task))
                    total += 1
        if total:
            self.monitorinfo('The plan has failed, failed tasks are:')
            for line in logstrings:
                self.monitorinfo(line)
        else:
            self.error('The plan has failed but no tasks marked as Failed!')
        self.plan_overview('Failed', active_phases)

    def show_running_tasks(self):
        """
        Log any running tasks
        :return:
        """
        logstrings = []
        total = 0
        for phaseid, tasks in self.phase_tasks.items():
            suppress_phase_header = False
            for task in tasks.values():
                if task.state.lower() == 'running':
                    if not suppress_phase_header:
                        logstrings.append('Phase-{0}'.format(phaseid))
                        suppress_phase_header = True
                    logstrings.extend(self.format_task(task))
                    total += 1
        if total:
            for line in logstrings:
                self.monitorinfo(line)

    def get_root(self, plan_name):
        """
        Get the root item in a plan

        :param plan_name: The name of the plan to retrieve the data on
        :returns:
        :rtype: LitpObject
        """
        get_path = '/plans/{0}?recurse_depth=1000'.format(plan_name)
        try:
            data = self.litp.get(get_path, log=False)
            return LitpObject(None, data, self.litp.path_parser)
        except LitpException as error:
            if error.args[0] == httplib.NOT_FOUND:
                raise LitpException('No plan called \'{0}\' '
                                    'found!'.format(plan_name))
            raise

    def plan_overview(self, plan_state=None, active_phases=None):
        """
        Log the overview of a plan i.e. total task count and number of each
        task type
        :param plan_state: The state of the plan
        :type plan_state: basestring
        :param active_phases: A list of IDs of active phases
        :type active_phases: list
        :return:
        """
        if active_phases is None:
            active_phases = []
        info_list = []
        insert_info = lambda msg: info_list.insert(0, msg)
        total_tasks = 0
        task_counts = self.get_task_state_count()

        for _state in PlanMonitor.TASKS_STATES:
            total_tasks += task_counts[_state]
            info_list.append('{0}: {1}'.format(_state, task_counts[_state]))
        insert_info('TotalTasks: {count}'.format(count=total_tasks))

        if plan_state:
            insert_info('PlanState: {state}'.format(state=plan_state))
        if active_phases:
            insert_info('Active Phase(s): {active}'.format(
                active=', '.join(str(phase_id) for phase_id in active_phases)))
        else:
            insert_info('Active Phase(s): -')
        insert_info('Total Phases: {total}'.format(
            total=len(self.phase_tasks)))
        overview = ' | '.join(info_list)
        self.monitorinfo(overview.strip())

    def log_plan(self, plan_state, active_phases=None):
        """
        Log a complete plan (phases, tasks and overview)
        :param plan_state: The plans state e.g. Running/Failed/etc.
        :param active_phases: A list of IDs of active phases
        :return:
        """
        self.monitorinfo('SHOW_PLAN BEGIN')
        if active_phases is None:
            active_phases = []
        for phaseid, tasks in self.phase_tasks.items():
            self.monitorinfo('Phase {0} tasks:'.format(phaseid))
            for task in tasks.values():
                for _msg in self.format_task(task):
                    self.monitorinfo('  ' + _msg)
        self.plan_overview(plan_state, active_phases=active_phases)
        self.monitorinfo('SHOW_PLAN END')

    def plan_started(self, wait_start_ts, initial_state_timeout):
        """
        Determine if the plan has started or not.
        :param wait_start_ts: Timestamp to use to calculate if the max
         wait time has been reached
        :param initial_state_timeout: Max time to give the plan to go a
        running state
        :return:
        """
        if wait_start_ts:
            if time() - wait_start_ts >= initial_state_timeout:
                self.monitorinfo('RUN_PLAN END')
                msg = 'Timedout wait for the plan to ' \
                      'change from Initial state!'
                self.monitorinfo(msg)
                raise LitpException(ExitCodes.PLAN_START_TIMEOUT,
                                    msg)
        else:
            self.monitorinfo('Waiting for plan to switch '
                             'from Initial state.')
            return False
        return True

    def plan_state_changing(self, wait_start_ts, state_timeout, from_state):
        """
        Determine if the plan has (re)started or not.
        :param wait_start_ts: Timestamp to use to calculate if the max
         wait time has been reached
        :param state_timeout: Max time to give the plan to go a
        running state
        :return:
        """
        if wait_start_ts and (time() - wait_start_ts >= state_timeout):
            self.monitorinfo('RUN_PLAN END')
            msg = 'Timedout wait for the plan to ' \
                  'change from %s state!' % from_state
            self.monitorinfo(msg)
            raise LitpException(ExitCodes.PLAN_START_TIMEOUT, msg)

        self.monitorinfo('Waiting for plan to switch '
                         'from %s state.' % from_state)
        return False

    #pylint: disable=too-many-branches
    def monitor_plan_progress(self, plan_name, delay,
                              state_timeout=300,
                              resume_plan=False):
        """
        Monitor a plan and wait for it to stop executing tasks i.e the plan
        state attribute changes from Initial/Running to
        Failed/Stopped/Successfull.

        If the plan stops due to failed task(s) those failed task(s) will get
        logged.
        :param plan_name: The plan to monitor
        :type plan_name: str
        :param delay: Delay between plan checks
        :type delay: int
        :param state_timeout : Wait N seconds for the plan to go from
         state ``Initial`` or ``Failed`` to another state as on larger
         deployments the plan can take a bit to ``Running`` after
         the 'litp run_plan' command has been issued.
        :type state_timeout: int
        :param resume_plan : Has the upgrade Plan been resumed
        :type resume_plan: boolean
        """
        plan_state = None
        active_phases = []
        wait_start_ts = None
        wait_resume_ts = 0
        plan_to_be_resumed = resume_plan

        while True:
            first_run = plan_state is None
            root = self.get_root(plan_name)
            plan_state = root.state
            state_changes = self.merge_model(root, first_run)
            active_phases = self.get_active_phases()

            if first_run:
                self.log_plan(plan_state, active_phases=active_phases)
                self.monitorinfo('RUN_PLAN BEGIN')
                self.monitorinfo('Current running tasks:')
                self.show_running_tasks()
                self.monitorinfo('-' * 30)

            if plan_state == LitpRestClient.PLAN_STATE_INITIAL:
                if not self.plan_started(wait_start_ts,
                                        state_timeout):
                    wait_start_ts = time()
                    continue

            elif plan_state == LitpRestClient.PLAN_STATE_SUCCESSFUL:
                if not first_run:
                    self.monitorinfo('RUN_PLAN END')
                    self.log_plan(plan_state)
                    self.monitorinfo('Plan completed successfully.')
                break

            elif plan_state == LitpRestClient.PLAN_STATE_FAILED:
                if plan_to_be_resumed:
                    if not wait_resume_ts:
                        wait_resume_ts = time()
                    if not self.plan_state_changing(wait_resume_ts,
                                                    state_timeout,
                                                    'Failed'):
                        sleep(2)
                        continue

                self.monitorinfo('RUN_PLAN END')
                self.log_plan(plan_state, active_phases=active_phases)
                self.show_failed_plan(active_phases=active_phases)
                raise LitpException(ExitCodes.PLAN_FAILED,
                                    'Plan execution failed')

            elif plan_state == LitpRestClient.PLAN_STATE_RUNNING:
                plan_to_be_resumed = False
                if state_changes:
                    self.plan_overview(active_phases=active_phases)
                sleep(delay)

            elif plan_state in [LitpRestClient.PLAN_STATE_STOPPED,
                                LitpRestClient.PLAN_STATE_STOPPING]:
                self.monitorinfo('RUN_PLAN END')
                self.log_plan(plan_state, active_phases=active_phases)
                raise LitpException(ExitCodes.PLAN_STOPPED,
                                    'Plan is stopping/stopped!')

            else:
                raise LitpException(ExitCodes.UNKNOWN_PLAN_STATE,
                                    'Unknown plan state {0}'.format(
                                            plan_state))


class LitpRestClient(object):  # pylint: disable=R0902,R0904
    """
    This class provides a mechanism to interact with LITP via REST calls,
    while also supplying functions to perform tasks via LITP
    """
    PLAN_STATE_INITIAL = 'initial'
    PLAN_STATE_RUNNING = 'running'
    PLAN_STATE_STOPPING = 'stopping'
    PLAN_STATE_STOPPED = 'stopped'
    PLAN_STATE_FAILED = 'failed'
    PLAN_STATE_SUCCESSFUL = 'successful'
    PLAN_STATE_INVALID = 'invalid'

    ITEM_STATE_INITIAL = "Initial"
    ITEM_STATE_APPLIED = "Applied"
    ITEM_STATE_UPDATED = "Updated"
    ITEM_STATE_FORREMOVAL = "ForRemoval"
    ITEM_STATE_REMOVED = "Removed"
    PLAN_RUNNING_STATES = [PLAN_STATE_RUNNING, PLAN_STATE_STOPPING]

    TASK_STATE_INITIAL = 'Initial'
    TASK_STATE_RUNNING = 'Running'
    TASK_STATE_SUCCESS = 'Success'
    TASKS_STATES = [TASK_STATE_INITIAL, TASK_STATE_RUNNING,
                    TASK_STATE_SUCCESS, 'Failed', 'Stopped']

    DEFAULT_LITPD_HOST = 'localhost'
    DEFAULT_LITPD_PORT = 9999
    DEFAULT_REST_VERSION = 'v1'
    DEFAULT_PLAN_DELAY = 60
    HEADER_CONTENT_TYPE = 'Content-Type'
    HEADER_CONTENT_LENGTH = 'content-length'
    CONTENT_TYPE_XML = 'application/xml'
    CONTENT_TYPE_JSON = 'application/json'

    RETRY_INTERVAL = 6
    MAX_ATTEMPTS = 10

    def __init__(self, litpd_host=DEFAULT_LITPD_HOST,
                 litpd_port=DEFAULT_LITPD_PORT,
                 litp_version=DEFAULT_REST_VERSION):
        self.litpd_host = socket.gethostbyname(litpd_host)
        self.litpd_port = litpd_port
        self.litp_version = litp_version
        self.base_rest_path = '/litp/rest/{0}'.format(self.litp_version)
        self.config_rest_path = '/litp/config/'
        self.logging_rest_path = '/litp/logging/'
        self.maintenance_rest_path = '/litp/maintenance'
        self.snapshot_resth_path = '/snapshots'
        self.base_xml_path = '/litp/xml'
        self.log = logging.getLogger('enminst')
        (litprc_data, self.connection_type, self.unix_socket_path) = \
            self.get_litprc_and_connection_type(
            self.RETRY_INTERVAL, self.MAX_ATTEMPTS)
        self.auth_header = self.get_auth_header(litprc_data)

    @staticmethod
    def xstr(data):
        """
        Converts a specified dictionary to a string
        :param data: dictionary to be converted
        :return: A string built from the specified dictionary
        """
        if data is None:
            return '{}'
        return str(data)

    def set_debug(self, log_level):
        """
        Sets the LITP log level to the specified value
        :param log_level: LITP log level
        :type log_level: str
        """
        props = {'force_debug': 'false'}
        if log_level == 'debug':
            props['force_debug'] = 'true'
        self.update(self.logging_rest_path, props, verbose=False)

    def path_parser(self, href_path):
        """
        Convert the LITP rest api path to a model path (the LITP rest path
        contains the LITP server host:port info in it)
        :param href_path: LITP REST response path
        :returns: Model path
        """
        return href_path[href_path.index(self.base_rest_path) + len(
                self.base_rest_path):]

    def update(self, node_path, i_property, verbose=True):
        """
        Updates the LITP model at a defined path with a defined property
        :param node_path: path in the LITP model where the update will be made
        :param i_property: model property being changed
        :param verbose: trigger specifying whether to log the litp update
        command. Default is true
        """
        if verbose:
            self.log.info('litp update -p {0} -o {1}'
                          .format(node_path, self.xstr(i_property)))
        self.https_request('PUT', node_path, data={'properties': i_property})

    def delete_property(self, model_path, i_property):
        """
        delete the LITP model at a defined path with a defined property
        :param model_path: path in the LITP model where the update will be made
        :param i_property: model property being deleted
        command. Default is true
        :return: True if property deleted. False if property or path does not
        exist.
        :rtype: bool
        """
        if not self.exists(model_path):
            return False
        data = self.get(model_path, log=False)
        data_obj = LitpObject(None, data, self.path_parser)
        if data_obj.get_property(i_property):
            self.update(model_path, i_property=dict.fromkeys([i_property]),
                        verbose=False)
            return True
        else:
            return False

    def delete_path(self, model_path):
        """
        delete the LITP model at a defined path
        :param model_path: path in the LITP model where the update will be made
        :return: True if path deleted. False if path does not exist.
        :rtype: bool
        """
        if self.exists(model_path):
            self.https_request('DELETE', model_path)
            return True
        else:
            return False

    def exists(self, model_path):
        """
        Check if a path exists.
        :param model_path:  The path to check
        :type model_path: str
        :returns: ``True`` if the path exists, ``False`` otherwise
        :rtype: bool
        """
        try:
            self.https_request('GET', model_path, log_results=False)
            return True
        except LitpException as error:
            _code = error.args[0]
            if _code == httplib.NOT_FOUND:
                return False
            else:
                raise error

    def create(self, parent_node, object_id, object_type, properties=None):
        """
        Create an item.

        :param parent_node: The parent node
        :type parent_node: str
        :param object_id: The new objects id
        :type object_id: str
        :param object_type: The new objects item-type
        :type object_type: str
        :param properties: Any properties to set when creating
        :type properties: dict
        :returns: The path of the newly created item
        :rtype: str
        """
        node_path = '{0}/{1}'.format(parent_node, object_id)
        if self.exists(node_path) is False:
            data = {'id': object_id, 'type': object_type}
            if properties is not None:
                data['properties'] = properties
            self.https_request('POST', parent_node, data=data)
        else:
            raise LitpException('Path {path} already exists'
                                ''.format(path=node_path), httplib.CONFLICT)
        return node_path

    def inherit(self, model_path, source_path, properties=None):
        """
        Link an node to another

        :param model_path: The target node
        :type model_path: str
        :param source_path: The source path to inherit from
        :type source_path: str
        :param properties: Any properties to override
        :type properties: dict
        """
        path, oid = model_path.rsplit('/', 1)
        data = {'id': oid, 'inherit': source_path}
        if properties:
            data['properties'] = properties
        self.https_request('POST', path, data=data)

    def upgrade(self, node_path, verbose=True):
        """
        Upgrades packages in the specified node
        or in the whole cluster/deployment
        :param node_path: path in the LITP model to the specified node
        or the whole cluster/deployment
        :param verbose: trigger specifying wheter to log the litp update
        command. Default is true
        """
        upgrade_path = "/litp/upgrade"

        if verbose:
            self.log.info('litp upgrade -p {0}'.format(node_path))
        data = {'path': node_path, 'hash': md5(str(time())).hexdigest()}
        self.https_request('POST', upgrade_path, data=data, base_rest_path='')

    def export_model_to_xml(self, xml_output_file, model_path='/'):
        """
        Export an entire or part of a deployment model to a single XML file
        :param model_path: path in the model from which you want exported. '/'
        would be the full model
        :param xml_output_file: XML file to export the model to
        """
        if self.exists(model_path):
            xml_string = self.https_request('GET', model_path,
                                            base_rest_path=self.base_xml_path,
                                            content_type=LitpRestClient
                                            .CONTENT_TYPE_XML,
                                            log_results=False)
            with open(xml_output_file, 'w') as _writer:
                _writer.writelines(xml_string)
        else:
            raise LitpException('Path {path} does not exist'
                                ''.format(path=model_path), httplib.NOT_FOUND)

    def get_litprc_and_connection_type(self, retry_interval, max_attempts):
        """
        Read the .litprc file and determine the type of connection

        This will retry a number of times if there is no .litprc file and
        the connection type is not UNIX, to allow for a delay in initialisation
        after reboot.

        :param retry_interval: number of seconds between retries
        :type retry_interval: int
        :param max_attempts: maximum number of attempts to establish
        connection details
        :type max_attempts: int
        :return: tuple of litprc data, connection type and connection details
          - litprc_data is a dictionary with litp-admin login credentials and
            path to file
          - connection type is either TCP_CONNECTION or UNIX_CONNECTION
          - connection details is either None or path to unix socket
        """
        for attempt in range(max_attempts + 1):
            litprc_data = read_litprc()
            (connection_type, unix_socket_path) = \
                                        get_connection_type(litprc_data)
            if connection_type != UNIX_CONNECTION and \
                                        litprc_data.file_missing:
                if attempt == max_attempts:
                    msg = 'File {0} not found'.format(litprc_data.path)
                    self.log.exception(msg)
                    raise IOError(1, msg)
                msg = 'Failed to gather connection details. Retrying'\
                ' {0}/{1}'.format(attempt + 1, max_attempts)
                self.log.debug(msg)
                sleep(retry_interval)
            else:
                msg = 'Connection type is {0}'.format(connection_type)
                self.log.debug(msg)
                break
        return (litprc_data, connection_type, unix_socket_path)

    def get_auth_header(self, litprc_data):
        """
        Prepare auth header beforehand.

        Auth header depends on connection type because Unix socket connection
        accepts anything without actually checking; by convention Posix
        user username is sent to Unix socket.
        TCP connection requires valid credentials encoded for Basic-Auth.

        Raises exceptions in case of missing credentials.

        :param litprc_data: instance of LitprcConfig
        :return: dictionary with Authorization header
        """
        if self.connection_type == UNIX_CONNECTION:
            username = pwd.getpwuid(os.getuid()).pw_name
            password = ''
        else:
            if 'username' not in litprc_data:
                msg = 'No username entry in {0} file'.format(
                                    litprc_data.path)
                self.log.exception(msg)
                raise LitpException(1, msg)
            elif 'password' not in litprc_data:
                msg = 'No password entry in {0} file'.format(
                                    litprc_data.path)
                self.log.exception(msg)
                raise LitpException(1, msg)
            username = litprc_data['username']
            password = litprc_data['password']
        plain = username + ':' + password
        digest = encodestring(plain)
        header = {
            'Authorization': 'Basic ' + digest.strip()
        }
        return header

    def get_headers(self, content_type, content_length=0):
        """
        Build header information to be used in the LITP REST call
        :param content_type: the type the content to be passed via REST will be
        :param content_length: the length of the data to be passed in the REST
        call. Default length is 0
        :return: the header to be used in the REST call
        """
        headers = {LitpRestClient.HEADER_CONTENT_TYPE: content_type,
                   LitpRestClient.HEADER_CONTENT_LENGTH: content_length}
        headers.update(self.auth_header)
        return headers

    def get_https_connection(self):
        """
        Get a HTTPS connection
        :return:
        """
        if self.connection_type == UNIX_CONNECTION:
            return UnixSocketConnection(self.unix_socket_path)
        if sys.version_info < (2, 7):
            return httplib.HTTPSConnection(self.litpd_host, self.litpd_port)
        if sys.version_info >= (2, 7):
            from ssl import _create_unverified_context
            return httplib.HTTPSConnection(self.litpd_host, self.litpd_port,
                                       context=_create_unverified_context())

    @staticmethod
    def _get_body(data):
        """
        Get the body for a http request.
        :param data: The raw data to put in the http request body
        :returns tuple(content-length, http_body):
        """
        content_length = 0
        body = None
        if data:
            if isinstance(data, str):
                body = data
            else:
                body = dumps(data)
            content_length = len(body)
        return content_length, body

    def _request(self,  # pylint: disable=R0913
                 connection, request_type, rest_path, body, headers):
        """
        Execute a http request
        :param connection: The connection type UNIX or TCP local constants
        :param request_type: The request type e.g. GET, PUT...
        :param rest_path: The REST path
        :param body: Body of the request
        :param headers: Request headers
        :returns: The request response
        """
        try:
            connection.request(request_type, rest_path, body=body,
                               headers=headers)
            return connection.getresponse()
        except httplib.HTTPException as httpe:
            self.log.exception('General HTTP error sending request to '
                               'LITP at {0}'.format(rest_path))
            raise LitpException(1, {'error': str(httpe), 'reason': httpe})
        except socket.gaierror as error:
            self.log.exception('HTTP connection error whilst executing request'
                               ' to LITP at {0}'.format(rest_path))
            raise LitpException({'error': error})

    def _request_result(self, http_response, model_path):
        """
        Get the results of a http request. Handle general errors
        :param http_response: The raw http response object
        :param model_path: The path in the model the request was made to
        :returns: The LITP data
        """
        response_data = http_response.read()
        if http_response.status == httplib.BAD_REQUEST:
            raise LitpException(http_response.status, response_data)
        elif http_response.status == httplib.UNAUTHORIZED:
            raise LitpException(http_response.status,
                                'Unauthorized access')
        content_type = http_response.getheader(
                LitpRestClient.HEADER_CONTENT_TYPE)

        if content_type == LitpRestClient.CONTENT_TYPE_JSON:
            try:
                results = loads(response_data)
            except ValueError as error:
                self.log.debug('Could not parse returned data '
                               'from request: {0}'.format(str(error)))
                results = response_data
        elif content_type == LitpRestClient.CONTENT_TYPE_XML:
            self.log.debug('Retrieved data in XML format')
            results = response_data
        else:
            self.log.debug('Retrieved data in RAW format')
            results = response_data

        if http_response.status not in [httplib.OK, httplib.CREATED,
                                        httplib.ACCEPTED]:
            if type(results) is dict and 'messages' in results \
                    and results['messages']:
                messages = results['messages']
            else:
                messages = [response_data]
            raise LitpException(http_response.status,
                                {'reason': http_response.reason,
                                 'path': model_path,
                                 'messages': messages})
        return results

    def https_request(self,  # pylint: disable=too-many-arguments
                      request_type, model_path, data=None,
                      content_type=CONTENT_TYPE_JSON,
                      base_rest_path=None, log_results=True):
        """
        Build a json file to be passed to LITP via REST that will tell LITP
        what needs to be done
        :param request_type: the type of HTTP method to use
        :param model_path: the path in the LITP model that will be interacted
        with
        :param data: the data to pass to LITP via REST
        :param content_type: the format the data will be in. Default is json
        :param base_rest_path: the rest path in LITP
        :param log_results: flag determining if the rest calls and results
        should be logged
        :return: the results from the REST call
        """
        if base_rest_path is None:
            base_rest_path = self.base_rest_path
        rest_path = '{0}{1}'.format(base_rest_path, model_path)
        if log_results:
            self.log.debug('HTTPS {0} request @ {1}'
                           .format(request_type, rest_path))
        content_length, body = self._get_body(data)

        connection = self.get_https_connection()
        headers = self.get_headers(content_type, content_length)
        response = self._request(connection, request_type, rest_path,
                                 body, headers)
        results = self._request_result(response, model_path)

        if log_results:
            self.log.debug(results)
        return results

    def load_xml(self, load_point, xml_file, merge=True):
        """
        Loads a deployment model XML into LITP at a defined point
        :param load_point: path in the LITP model where the update will be made
        :param xml_file: deployment model XML to load
        :param merge: flag to trigger if the merge option is to be used when
        loading the model XML into LITP. Default is true
        """
        if not exists(xml_file):
            raise LitpException('File {0} not found.'.format(xml_file))
        data = open(xml_file).read()
        data = data.strip()
        url = load_point
        if merge:
            url += "?merge=true"
        self.https_request('POST', url, data=data,
                           base_rest_path=self.base_xml_path,
                           content_type=LitpRestClient.CONTENT_TYPE_XML)

    def create_plan(self, plan_name, no_lock_tasks=None,
                     no_lock_tasks_list=None):
        """
        Creates a LITP plan
        :param plan_name: name of the plan to create
        :param no_lock_tasks: Boolean to indicate whether or not to generate
        lock/unlock tasks.
        :param no_lock_tasks_list: list of cluster Item Ids for which no
        lock/unlock tasks will be generate.
        """
        if no_lock_tasks:
            self.https_request('POST', '/plans',
                           data={'id': plan_name,
                                 'type': 'plan',
                                 'no-lock-tasks': 'True',
                                 'no-lock-tasks-list': no_lock_tasks_list})
        else:
            self.https_request('POST', '/plans',
                           data={'id': plan_name, 'type': 'plan'})

    def create_snapshot(self, name='snapshot'):
        """
        Create a LITP plugin based filesystem snapshot.

        :param name: The snapshot name
        :type name: str
        """
        self.https_request('POST', '/snapshots/{0}'.format(name),
                           data={'type': 'snapshot-base'})

    def restore_model(self):
        """
        Restores litp model to last stable state
        :return:
        """
        data = {'properties': {'update_trigger': 'yes'}}
        self.https_request('PUT', '/litp/restore_model',
                           data=data)

    def remove_snapshot(self, name='snapshot', force=False):
        """
        Remove a named LITP plugin based filesystem snapshot.
        :param name: The named snapshot to remove.
        :type name: str
        :param force: Force the removal of the snapshot
        :param force: bool
        """
        properties = {'properties': {
            'force': force,
            'action': 'remove'}
        }
        self.https_request('PUT', '/snapshots/{0}'.format(name),
                           data=properties)

    def restore_snapshot(self, name='snapshot', force=False):
        """
        Restore a named LITP plugin based filesystem snapshot.
        :param name: The named snapshot to restore
        :type name: str
        :param force: Force the restore.
        :type force: bool
        """
        properties = {'properties': {
            'force': str(force).lower()}
        }
        self.https_request('PUT', '/snapshots/{0}'.format(name),
                           data=properties)

    def list_snapshots(self):
        """
        Get a list of modeled LITP snapshots.

        :returns: A list of modeled snapshots in /snapshots
        :rtype: str[]
        """
        snap_names = []
        for snapshot in self.get_children('/snapshots'):
            snap_names.append(snapshot['data']['id'])
        return snap_names

    def get_plan_status(self, plan_name):
        """
        Retrieve the status of a defined LITP plan
        :param plan_name: name of the plan to query
        :return: Status of all tasks in the specified plan
        """
        plan_path = '/plans/{0}'.format(plan_name)
        phase_path = '{0}/phases'.format(plan_path)
        phase_list = self.get_children(phase_path)
        if not phase_list:
            self.log.info('No phases found in plan \'{0}\'!'
                          .format(phase_path))
            return []
        plan_status = []
        for phase in phase_list:
            task_path = '{0}/tasks'.format(phase['path'])
            tasks = self.get_children(task_path)
            for task in tasks:
                task_info = self.get(task['path'], log=False)
                plan_status.append({
                    'path': task['path'],
                    'state': task_info['state'],
                    'description': task_info['description']
                })
        return plan_status

    def get_children(self, model_path, verbose=False):
        """
        Retrieve all the tasks within each phase
        :param verbose: Display calls
        :param model_path: Path to the phases in a LITP plan
        :return: all tasks within each phase of the LITP plan
        """
        data = self.get(model_path, log=verbose)
        child_paths = []
        if '_embedded' in data:
            for child in data['_embedded']['item']:
                if model_path == '/':
                    _path = '/{1}'.format(model_path, child['id'])
                else:
                    _path = '{0}/{1}'.format(model_path, child['id'])
                child_paths.append({'path': _path, 'data': child})
        return child_paths

    def get(self, model_path, log=True):
        """
        Show elements of the model under a given path
        :param model_path: Path to query in the LITP plan
        :param log: Flag specifying whether to log the attributes of the
        specified model path. Default is true
        :return: elements under a given LITP path
        """
        if log:
            self.log.info('litp show -p {0}'.format(model_path))
        return self.https_request('GET', model_path, log_results=log)

    def set_plan_state(self, plan_name, state, resume=False):
        """
        Set the state of a LITP plan via REST
        :param plan_name: Name of the LITP plan to manipulate
        :param state: State to change the plan to
        :param resume: Resume a failed upgrade plan
        """
        plan_path = '/plans/{0}'.format(plan_name)
        data = {'properties': {'state': state}}

        if resume and state == 'running':
            data['properties']['resume'] = 'true'

        self.https_request('PUT', plan_path, data=data)

    def get_plan_state(self, plan_name, verbose=True):
        """
        Get the current state of a LITP plan
        :param verbose: Verbose logging
        :param plan_name: Name of the plan to check
        :return: the current state of the LITP plan queried
        """
        plan_path = '/plans/{0}'.format(plan_name)
        data = self.https_request('GET', plan_path, log_results=verbose)
        return data['properties']['state']

    @staticmethod
    def log_stdout(message):
        """
        Print a message to standard out
        :param message: the message to be printed
        """
        print(message)  # pylint: disable=superfluous-parens

    def monitor_plan(self, plan_name, verbose=False, resume_plan=False):
        """
        Monitor a plan and block until the plan finished or fails
        :param plan_name: Name of the plan to monitor
        """

        watcher = PlanMonitor(self, verbose=verbose)
        delay = LitpRestClient.DEFAULT_PLAN_DELAY
        watcher.monitor_plan_progress(plan_name, delay,
                                      resume_plan=resume_plan)

    def show_plan(self, plan_name):
        """
        Log a plan
        :param plan_name: Name of the plan to display
        """
        watcher = PlanMonitor(self)
        root = watcher.get_root(plan_name)
        plan_state = root.state
        watcher.merge_model(root, True)
        watcher.log_plan(plan_state)

    def is_plan_running(self, plan_name):
        """
        Check is a plan running or not.

        :param plan_name: The plan to check
        :type plan_name: str
        :returns: True if a plan is running, False otherwise
        :rtype: bool
        """
        plan_path = '/plans/{0}'.format(plan_name)
        if self.exists(plan_path):
            plan_state = self.get_plan_state(plan_name, verbose=False)
            return plan_state.lower() in LitpRestClient.PLAN_RUNNING_STATES
        else:
            return False

    def get_items_by_type(self, path, item_type, items):
        """
        Obtain a list of specified item types from the LITP model. The list
        only includes items with Applied state
        :param path: A path to search in the LITP model
        :type path: str
        :param item_type: Item type, e.g. san-emc
        :type item_type: str
        :param items: An initial list of items, it can be an empty list
        :items type: list
        :return: A list of particular item types
        :rtype: list
        """
        try:
            for item in self.get_children(path):
                is_itemtype = item['data']['item-type-name'] == item_type
                is_applied = item['data'][
                                 'state'] == LitpRestClient.ITEM_STATE_APPLIED
                if is_itemtype and is_applied:
                    items.append(item)
                else:
                    self.get_items_by_type(item['path'], item_type, items)
        except LitpException as err:
            self.log.exception(err)
            raise
        return items

    def get_all_items_by_type(self, path, item_type, items):
        """
        Obtain a list of specified item types from the LITP model. The list
        only includes all items regardless of state
        :param path: A path to search in the LITP model
        :type path: str
        :param item_type: Item type, e.g. san-emc
        :type item_type: str
        :param items: An initial list of items, it can be an empty list
        :items type: list
        :return: A list of particular item types
        :rtype: list
        """
        try:
            for item in self.get_children(path):
                if item['data']['item-type-name'] == item_type:
                    items.append(item)
                else:
                    self.get_all_items_by_type(item['path'], item_type, items)
        except LitpException as err:
            self.log.exception(err)
            raise
        return items

    def get_deployment_clusters(self):
        """
        Obtain cluster IDs from the LITP model

        :return: Mapping of clusters in deployments
        :rtype: dict
        """
        deployment_clusters = {}
        deployments = self.get_children('/deployments')
        for _deployment in deployments:
            deployment_id = _deployment['data']['id']
            path = '/deployments/{0}/clusters/'.format(deployment_id)
            clusters = self.get_children(path)
            cluster_names = []
            for cluster in clusters:
                cluster_names.append(cluster['data']['id'])
            deployment_clusters[deployment_id] = cluster_names
        return deployment_clusters

    def get_deployment_cluster_list(self):
        """
        Gets all the clusters in a deployment
        :return: clusters in deployment
        :rtype: list
        """
        deployment_clusters = []
        modelled_clusters = self.get_deployment_clusters()
        for _, clusters in modelled_clusters.items():
            for cluster in clusters:
                deployment_clusters.append(cluster)
        return deployment_clusters

    def get_cluster_nodes(self):
        """
        Get list of clusters and nodes in each cluster

        :return: Map of clusters with nodes in each one
        :rtype: dict
        """
        clusters = self.get_deployment_clusters()
        clustered_nodes = {}
        for did, clusters in clusters.items():
            for cluster_name in clusters:
                clustered_nodes[cluster_name] = {}
                nodes_path = '/deployments/{0}/clusters/{1}/nodes'.format(
                        did, cluster_name)
                nodes = self.get_children(nodes_path, verbose=False)
                for node in nodes:
                    node = LitpObject(None, node['data'], self.path_parser)
                    clustered_nodes[cluster_name][node.item_id] = node
        return clustered_nodes

    def get_lms(self):
        """
        Get the LMS model item
        :returns: LitpObject for the LMS
        :rtype: LitpObject
        """
        lms_data = self.get('/ms', log=False)
        return LitpObject(None, lms_data, self.path_parser)

    def get_node_states(self):
        """
        Get model states on nodes (blades)

        :returns: Model states of nodes e.g Applied/Initial/etc.
        :rtype: dict
        """
        clusters = self.get_cluster_nodes()
        states = {}
        for cluster in clusters.values():
            for node in cluster.values():
                states[node.get_property('hostname')] = node.state
        lms = self.get_lms()
        states[lms.get_property('hostname')] = lms.state
        return states

    def is_in_maintenance_mode(self):
        """
        Get litp maintenance mode state
        :returns: True if litp in maintenance mode
        :rtype: bool
        """
        maintenance_data = self.get(self.maintenance_rest_path, log=False)
        maint_obj = LitpObject(None, maintenance_data, self.path_parser)
        return maint_obj.get_bool_property("enabled")

    def disable_maintenance_mode(self):
        """
        Set litp maintenance mode to disabled
        """
        self.update(self.maintenance_rest_path,
                    {'enabled': 'false'}, verbose=False)


def create_arg_parser():
    """
    Create an ArgumentParser
    :return:
    """
    parser = ArgumentParser()
    parser.add_argument('--monitor_plan', default=False,
                        action='store_true',
                        help='Wait for a running plan to complete.')
    return parser


@keyboard_interruptable()
def main(args):
    """
    Main function
    :param args:
    :return:
    """
    arg_parser = create_arg_parser()
    parsed_args = arg_parser.parse_args(args)
    if parsed_args.monitor_plan:
        litp = LitpRestClient()
        litp.monitor_plan('plan')
    else:
        arg_parser.print_help()


if __name__ == '__main__':
    main(sys.argv[1:])
