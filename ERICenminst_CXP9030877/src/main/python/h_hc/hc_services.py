"""
Service health check actions
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
# Name    : hc_services.py
# Purpose : The purpose of this script is check the state
# of certain services within the deployment.
# ********************************************************************
import logging
import socket

from h_litp.litp_rest_client import LitpRestClient
from h_puppet.mco_agents import EnminstAgent
from h_util.h_utils import exec_process
from h_vcs.vcs_utils import filter_systems_by_state, report_tab_data


class Services(object):
    """
    Linux service health checks
    """
    DEFAULT_MCO_TIMEOUT = 30
    MCO = '/usr/bin/mco '
    PING = '/bin/ping '
    H_SYSTEM = 'System'
    H_STATE = 'State'
    H_SERVICE_NAME = 'Service'
    H_LEVEL = 'Run Level'
    STATE_OFFLINE = 'OFFLINE'
    STATE_ONLINE = 'ONLINE'
    STATE_NOTRUNNING = 'NOT RUNNING'

    SERVER_STATE_TABLE_HEADER = [H_SYSTEM, H_STATE]
    SERVICE_STATE_TABLE_HEADER = [H_SYSTEM, H_SERVICE_NAME, H_STATE, H_LEVEL]

    NODE_SERVICE_LIST = [
        'ddc', 'mcollective', 'puppet', 'sshd', 'vcs'
    ]

    MS_SERVICE_LIST = [
        'cobblerd', 'ddc', 'httpd', 'litpd',
        'mcollective', 'puppet', 'sshd', 'postfix'
    ]

    def __init__(self, logger_name='enminst'):
        self.log = logging.getLogger(logger_name)
        self.logger_name = logger_name
        super(Services, self).__init__()
        self.ssh = None
        self.__litp = LitpRestClient()
        self.lms_hostname = socket.gethostname()

    def litp(self):
        """
        Get a reference the the LITP rest client
        Done like this so tests can stub out LITP

        :returns: LitpRestClient instance
        :rtype: LitpRestClient
        """
        return self.__litp

    @staticmethod
    def _get_service_status_struct(hostname, service, state, runlevel):
        """
        Function Description:
        Matches headers with the values passed & used to generate a table
        :param: hostname
        :param: service
        :param: state (either running/not running)
        """
        return {Services.H_SYSTEM: hostname, Services.H_SERVICE_NAME: service,
                Services.H_STATE: state, Services.H_LEVEL: runlevel}

    @staticmethod
    def _get_node_status_struct(system_name, state):
        """
        Function Description:
        Matches headers with the values passed
        :param: hostname
        :param: state (either running/not running)
        """
        return {Services.H_SYSTEM: system_name,
                Services.H_STATE: state}

    def verify_node_status(self, systemstate_filter,
                           verbose=False):
        """
        Function Description:
        From the rows & headers passed from the function '_ping_nodes'
        depending on the verbose value a table will be printed to the
        screen.
        :param systemstate_filter:
        :param verbose:
        """
        headers, rows, pings_ok = self._ping_nodes()
        rows = filter_systems_by_state(rows, state_filter=systemstate_filter)
        report_tab_data(None, headers, rows, verbose=verbose)
        return pings_ok

    def verify_service_status(self, systemstate_filter,
                              verbose=False):
        """
        Function Description:
        From the rows & headers passed from the function 'service_check'
        depending on the verbose value a table will be printed to the
        screen. If a row value is in an offline/stopped state, it will be set
        to 'NOT RUNNING' and report an IOError
        :param systemstate_filter:
        :param verbose:
        :raise IOError:
        """
        headers, rows = self._get_runlevels()
        rows = filter_systems_by_state(rows, state_filter=systemstate_filter)
        report_tab_data(None, headers, rows, verbose=verbose)
        error_service = []
        for item in rows:
            _state = item[Services.H_STATE]
            _level = item[Services.H_LEVEL]
            if _state != Services.STATE_ONLINE or _level != '3':
                error_service.append(item)
        if error_service:
            if verbose:
                report_tab_data(None, headers, error_service, verbose=True)
            raise IOError

    def source_nodes(self):
        """
        Get a list of all nodes modeled in LITP

        :returns: List of all nodes in LITP model
        :rtype: str[]
        """
        return self.source_node_states().keys()

    def source_node_states(self):
        """
        Get a list of all nodes in LITP and their model state (Applied,
         Initial, etc.)

        :returns: Nodes and their model state
        :rtype: dict
        """
        return self.litp().get_node_states()

    def _ping_nodes(self):
        """
        Function Description:
        Checks that each node is alive and active
        :return : table with list of active nodes
        """
        system_data = []
        _ping_errors = 0
        nodes = self.source_node_states()
        for node, model_state in nodes.items():
            if model_state == LitpRestClient.ITEM_STATE_INITIAL:
                self.log.warning(
                    'Node {0} not installed, skipping.'.format(node))
                state = LitpRestClient.ITEM_STATE_INITIAL
                _ping_errors += 1
            else:
                try:
                    exec_process(['ping', '-c', '4', node])
                    state = Services.STATE_ONLINE
                except IOError:
                    self.log.error('Unable to ping node: {0}'.format(node))
                    state = Services.STATE_OFFLINE
                    _ping_errors += 1
            sysstruct = Services._get_node_status_struct(node, state)
            system_data.append(sysstruct)
        _noerrors = _ping_errors == 0
        return Services.SERVER_STATE_TABLE_HEADER, system_data, _noerrors

    @staticmethod
    def check_unknown_node(hostname, node_state, system_data):
        """
        Check the state of an unknown node i.e. it's listed in the model
        but mcollective knows nothing about it.

        :param hostname: The node hostname
        :param node_state: The node state in the LITP mode.
        :param system_data: List to append the data to

        """
        if node_state == LitpRestClient.ITEM_STATE_INITIAL:
            _state = LitpRestClient.ITEM_STATE_INITIAL
        else:
            try:
                exec_process(['ping', '-c', '4', hostname])
                _state = 'MCollective Unresponsive'
            except IOError:
                _state = 'Host Unavailable'
        system_data.append(Services._get_service_status_struct(
            hostname, 'N/A', _state, '-'))

    @staticmethod
    def service_status(hostname, node_runlevels, service_status,
                       system_data):
        """
        Using the parameters passed, build a list of services
        along with the status of the service on each node

        :param hostname: The node hostname
        :type - str
        :param node_runlevels: List of all node runlevels
        :type - dict
        :param service_status: Based on exit_code prints service status
        :type - dict
        :param system_data: List to append the data to
        :type - list

        """
        for service_name, exit_code in service_status.items():
            if exit_code == 0:
                state = Services.STATE_ONLINE
            else:
                state = Services.STATE_NOTRUNNING
            system_data.append(
                Services._get_service_status_struct(
                    hostname, service_name, state,
                    node_runlevels[hostname]))

    def check_known_node_services(self, hostname, node_runlevel,
                                  system_data):
        """
        Verify that a node known to mcollective is at the correct runlevel and
        the list of services passed in are online.

        :param hostname: The node hostname
        :type - str
        :param node_runlevel: List of all node runlevels
        :type - list
        :param system_data: List to append the data to
        :type - list

        """
        if node_runlevel[hostname] != '3':
            self.log.error('Node {0} is not at expected run level {1}'
                           ''.format(hostname, '3'))
        enminst_agent = EnminstAgent()
        if hostname == self.lms_hostname:
            ms_service_status = enminst_agent.check_service(
                ','.join(self.MS_SERVICE_LIST), hostname)
            self.service_status(hostname, node_runlevel, ms_service_status,
                                system_data)
        else:
            node_service_status = enminst_agent.check_service(
                ','.join(self.NODE_SERVICE_LIST), hostname)
            self.service_status(hostname, node_runlevel, node_service_status,
                                system_data)

    def _get_runlevels(self):
        """
        For each node in the deployment check (1) their runlevel & (2) if
         pre-selected services should be online
        :return: Table
        """
        system_data = []
        enminst_agent = EnminstAgent()

        node_runlevels = enminst_agent.runlevel()
        nodes = self.source_node_states()
        for modeled_node, node_state in nodes.items():
            if modeled_node not in node_runlevels:
                self.check_unknown_node(modeled_node, node_state, system_data)
            else:
                self.check_known_node_services(modeled_node, node_runlevels,
                                               system_data)
        return Services.SERVICE_STATE_TABLE_HEADER, system_data
