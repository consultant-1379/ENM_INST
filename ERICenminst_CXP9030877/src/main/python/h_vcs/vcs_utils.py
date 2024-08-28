"""
This module provides some VCS discovery functions and helper funtions to
sort/filter table data.

The sort/filter data format is as follows:
    A row is a dictionary where the key is the colum name and the value
    is the cell value e.g.
        { 'col_A': 'value_col_A_row_1', 'col_B': 'value_col_B_row_1' }

    A table is then a list of row dictionaries e.g.
          [
            { 'col_A': 'value_col_A_row_1', 'col_B': 'value_colB_row_1' }
            ,
            { 'col_A': 'value_col_A_row_2', 'col_B': 'value_colB_row_2' }
          ]

    The headers for the data above would be the list:
        [ 'col_A', 'col_B' ]

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
from datetime import timedelta
from re import search, match
from time import mktime, localtime
from commands import getstatusoutput

from h_logging.enminst_logger import init_enminst_logging
from h_puppet.h_puppet import discover_peer_nodes
from h_puppet.mco_agents import EnminstAgent
from h_util.h_utils import screen, ExitCodes

VCS_AVAIL_ACTIVE_STANDBY = 'active-standby'
VCS_AVAIL_PARALLEL = 'parallel'
VCS_AVAIL_STANDALONE = 'standalone'
VCS_NA = 'N/A'

VCS_GRP_SVS_STATE_UNKNOWN = 'Unknown'
VCS_GRP_SVS_STATE_ONLINE = 'ONLINE'
VCS_GRP_SVS_STATE_OFFLINE = 'OFFLINE'

LOGGER = init_enminst_logging()


class VcsStates(object):  # pylint: disable=too-few-public-methods
    """
    Struct for VCS states
    """
    OFFLINE = 'OFFLINE'
    ONLINE = 'ONLINE'
    FAULTED = 'FAULTED'
    PARTIAL = 'PARTIAL'
    STARTING = 'STARTING'
    STOPPING = 'STOPPING'
    EXITED = 'EXITED'
    RUNNING = 'RUNNING'
    POWERED_OFF = 'POWERED OFF'

    TAG_ANY = 'any'

    VCS_CLEAR_STATES = [FAULTED]


class VcsCodes(object):
    """
    Struct for various VCS error/warning/message codes
    """

    def __init__(self):
        super(VcsCodes, self).__init__()

    KEY_VCS_CODE = 0
    KEY_DESCRIPTION = 1
    KEY_EXIT_CODE = 2

    V_16_1_10191 = ('V-16-1-10191',
                    'Cannot switch, group not active anywhere in cluster.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_10206 = ('V-16-1-10206',
                    'Group dependencies are not met for group on system.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_10446 = ('V-16-1-10446',
                    'This is informative message printed whenever a service '
                    'group goes offline on a system.',
                    ExitCodes.VCS_GROUP_OFFLINE)

    V_16_1_10447 = ('V-16-1-10447',
                    'A service group has gone online on a system.',
                    ExitCodes.OK)

    V_16_1_10600 = ('V-16-1-10600',
                    'Cannot connect to VCS engine.',
                    ExitCodes.VCS_SYSCLSTR_OFFLINE)

    V_16_1_10805 = ('V-16-1-10805',
                    'Connection timed out.',
                    ExitCodes.VCS_OPERATION_TIMEDOUT)

    V_16_1_40156 = ('V-16-1-40156',
                    'Cannot online group. No target system found',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40200 = ('V-16-1-40200',
                    'Group can not be temporarily frozen and persistently '
                    'frozen at the same time.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40201 = ('V-16-1-40201',
                    'Group is not temporarily frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40202 = ('V-16-1-40202',
                    'Group is not persistently frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40204 = ('V-16-1-40204',
                    'System is not temporarily frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40205 = ('V-16-1-40205',
                    'System is not persistently frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40206 = ('V-16-1-40206',
                    'System is already persistently frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40207 = ('V-16-1-40207',
                    'System is already temporarily frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40208 = ('V-16-1-40208',
                    'Group is already temporarily frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40209 = ('V-16-1-40209',
                    'Group is already persistently frozen.',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_10011 = ('No answer from node',
                    ExitCodes.VCS_INVALID_ACTION)

    V_16_1_40229 = ('V-16-1-40229',
                    'Group is already online.',
                    ExitCodes.VCS_INVALID_ACTION)

    @staticmethod
    def is_error(error_type, exception):
        """
        Check if the exception is a VCS error i.e. contains the error message
        :param error_type: The error type to check for
        :param exception: The exception to check
        :type exception: Exception
        :return:
        """
        return error_type[0] in str(exception)

    @staticmethod
    def to_string(error):
        """
        Convert an error tuple to a string

        :param error: The error to convert e.g. ``VcsCodes.V_16_1_40201``
        :type error: tuple
        :returns: String representation of the error
        :rtype: str
        """
        return '{0} {1}'.format(error[VcsCodes.KEY_VCS_CODE],
                                error[VcsCodes.KEY_DESCRIPTION])


def sort_tab_data(celldata, sortkeys, headers):
    """
    Sort table data.

    :param celldata: The table data
    :param sortkeys: Comma separated list of colum headers to sort by. If a
    sort header can't be found in the cell data it is ignored.
    :type sortkeys: None|str
    :param headers: List of table headers
    :return: Sorted table data
    """
    if sortkeys is None:
        return celldata
    _sort = True
    key_list = sortkeys.split(',')
    for key in key_list:
        if key not in headers:
            screen('Cant sort using \'{0}\''.format(key))
            _sort = False
    if _sort is False:
        return celldata
    sorted_list = celldata
    for key in key_list:
        sorted_list = sorted(sorted_list, key=lambda k: k[key])
    return sorted_list


def report_tab_data(report_type, headers, table_data, verbose=True):
    """
    Print formatted table data padding cells to the max value length
    in a column.

    :param report_type: Report header.
    :type report_type: str || None
    :param headers: List of column headers
    :type headers: list
    :param table_data: Table data
    :type table_data: list(dict)
    :param verbose: Log level to report at
    """
    max_cell_lengths = []
    for index in xrange(0, len(headers)):
        max_cell_lengths.append(len(headers[index]))

    for row in table_data:
        for index in xrange(0, len(headers)):
            header_length = len(str(row[headers[index]]))
            if header_length > max_cell_lengths[index]:
                max_cell_lengths[index] = header_length

    formatter = ''
    breakers = []
    for index in xrange(0, len(headers)):
        formatter += '{values[' + str(index) + ']:>' + str(
            max_cell_lengths[index] + 2) + '}'
    for length in max_cell_lengths:
        breakers.append('-' * length)

    header_line = formatter.format(values=headers)
    title_format = '{0:^' + str(len(header_line)) + '}'
    if report_type:
        screen(formatter.format(values=breakers))
        screen(title_format.format(report_type))
    screen(formatter.format(values=breakers), verbose=verbose)
    screen(header_line, verbose=verbose)
    screen(formatter.format(values=breakers), verbose=verbose)
    for row in table_data:
        props = []
        for i in xrange(0, len(headers)):
            props.append(row[headers[i]])
        screen(formatter.format(values=props), verbose=verbose)
    screen(formatter.format(values=breakers), verbose=verbose)


def filter_tab_data(row_data, filter_exp, prop_name):
    """
    Filter table data by a column values
    :param row_data: Table data
    :type row_data: list(dict)
    :param filter_exp: The filter regex (what the values be matched against)
    :param prop_name: The column to filter on
    :return: Filtered data
    """
    if filter_exp is None:
        return row_data
    else:
        filter_bits = filter_exp.split(',')

        def _remove(cell_data):
            """
            Remove an element
            :param cell_data: The array index data
            :return:
            """
            for filterexp in filter_bits:
                if prop_name not in cell_data:
                    continue
                if isinstance(cell_data[prop_name], list):
                    for text in cell_data[prop_name]:
                        if search(filterexp, text):
                            return True
                else:
                    if search(filterexp, cell_data[prop_name]):
                        return True
            return False

        return [vcso for vcso in row_data if _remove(vcso)]


class VcsException(Exception):
    """
    VCS operation failed.
    """
    pass


def match_filter(regex, string):
    """
    Handle matching data.

    :param regex: The regex to match with. If None match is True
    :type regex: None|str
    :param string: The string to match against
    :type string: None|str|list
    :return: If the regex matches or not
    :rtype: bool
    """
    if type(string) is list:
        for val in string:
            if match_filter(regex, val):
                return True
        return False
    else:
        if not string:
            if not regex:
                return True
            else:
                return False
    if not regex or search(regex, string):
        return True
    else:
        return False


def get_avail_type(vcs_parallel, system_count):
    """
    Get the availabilty type based on being parallel group value and number
    of systems that group in on.

    Standalone    : Parallel == 1 && system_count == 1
    ActiveStandby : Parallel == 0 && system_count == 2
    Parallel      : Parallel == 1 && system_count > 1

    :param vcs_parallel: VCS groups Parallel value (0 or 1)
    :type vcs_parallel: int
    :param system_count: Number of systems the VCS group is defined on
    :type system_count: int
    :return: The groups availabilty type
    """
    if int(vcs_parallel) == 1:
        if system_count == 1:
            return VCS_AVAIL_STANDALONE
        else:
            return VCS_AVAIL_PARALLEL
    else:
        return VCS_AVAIL_ACTIVE_STANDBY


def get_group_avail_type(active, standby, num_systems):
    """
    Get the availability type base on the active/standby number and
    number of nodes the group can be on.
    If active==1 && standby==0 && num_systems==1 => STANDALONE
    If active==1 && standby==1 && num_systems==2 => ActiveStandby
    If active>1 && standby==0: && num_systems>1 => Parallel

    :param active: Number of nodes the group will be active on
    :param standby: Number of nodes the group will be active on
    :param num_systems: Number of systems the group can be on
    :returns: The group availability type
    :rtype: str
    """
    _type = None
    if active == 1:
        if standby == 0:
            _type = VCS_AVAIL_STANDALONE
        elif standby == 1:
            _type = VCS_AVAIL_ACTIVE_STANDBY
    elif active >= 2 and standby == 0:
        _type = VCS_AVAIL_PARALLEL
    if not _type:
        raise ValueError('Unkown HA type for {0}:{1}:{2}'
                         ''.format(active, standby, num_systems))
    return _type


def discover_vcs_clusters(cluster_filter):
    """
    Find all VCS clusters on puppet agent nodes

    :param cluster_filter: Limit results to those matching this regex
    :type cluster_filter: str|None
    :return: list
    """
    enminst = EnminstAgent()
    clusters = {}
    for peer in discover_peer_nodes():
        cluster = enminst.haclus_list(peer)
        if not match_filter(cluster_filter, cluster):
            continue
        if cluster not in clusters:
            clusters[cluster] = []
        clusters[cluster].append(peer)
    return clusters


def add_uptime_data(dis_groups, group_name, group_history, system,
                    enminst_agent):
    """
    Add group history data.
    :param dis_groups: Dictionary holding all groups
    :param group_name: The group name
    :param group_history: Result of previous history queries
    :param system: The system to get the history for
    :param enminst_agent: ENMINST mco agent class
    :return:
    """
    if group_name not in group_history:
        hist = enminst_agent.hagrp_history(vcs_system=system)
        if hist:
            group_history.update(hist)
        else:
            group_history[group_name] = []
    if group_name in group_history:
        event_list = group_history[group_name]
        last_onlined = None
        for event in reversed(event_list):
            if event['id'] == 'V-16-1-10447':
                event_system = event['info'].split(' ')[-1:][0]
                if system == event_system:
                    last_onlined = event
                    break
        if last_onlined:
            _ts = mktime(last_onlined['ts'])
            delta = timedelta(
                seconds=mktime(localtime()) - _ts)
            dis_groups[group_name]['systems'][system][
                'uptime'] = str(delta)
    else:
        dis_groups[group_name]['systems'][system][
            'uptime'] = VCS_NA


def get_vcs_group_info(system_name, groups=None, include_uptimes=False):
    """
    Get a list of VCS groups (and group data) on a system

    :param groups: List of group names to restrict search to.
    :param system_name: VCS system
    :type system_name: str
    :param include_uptimes: Include group uptimes in data if it can be found.
    :type include_uptimes: bool
    :return: dict
    """
    enminst = EnminstAgent()
    if not groups:
        groups = enminst.hagrp_list(system_name)
    dis_groups = {}
    group_history = {}
    vcs_data = enminst.hagrp_display(groups, system_name)
    for group_name, group_info in vcs_data.items():
        dis_groups[group_name] = {
            'type': VCS_NA,
            'systems': {},
            'global': {}
        }
        system_count = 0
        for system in group_info.keys():
            if system == 'global':
                dis_groups[group_name]['global'] = group_info['global']
                continue
            system_count += 1
            state = group_info[system]['State'].replace('|',
                                                        ' ').strip().split(' ')
            dis_groups[group_name]['systems'][system] = {'state': state,
                                                         'uptime': '-1'}
            if len(state) == 1 and state[0] == VCS_GRP_SVS_STATE_ONLINE:
                if include_uptimes:
                    add_uptime_data(dis_groups, group_name, group_history,
                                    system, enminst)
        dis_groups[group_name]['type'] = get_avail_type(
            group_info['global']['Parallel'], system_count)
    return dis_groups


def _filter_property(vcs_list, filter_list, prop_name):
    """
    Method used to execute filters
    :param vcs_list:
    :param filter_list:
    :param prop_name:
    :return:
    """

    if filter_list is None:
        return vcs_list
    else:
        states = filter_list.split(',')

        def _remove(_vcso):
            """
            Remove an entry
            :param _vcso: Properties containing a STATE entry
            :return:
            """
            for _state in states:
                if isinstance(_vcso[prop_name], list):
                    for _value in _vcso[prop_name]:
                        if match(_state, _value):
                            return True
                else:
                    if match(_state, _vcso[prop_name]):
                        return True
            return False

        return [vcso for vcso in vcs_list if _remove(vcso)]


def filter_systems_by_name(vcs_list, system_filter):
    """
    Filter system data by ``Name`` key
    :param vcs_list: Data to filter, requires a 'Name' key
    :type vcs_list: dict
    :param system_filter: Filter by system name value
    :type system_filter: str|None
    :return:
    """
    filtered = _filter_property(vcs_list, system_filter, 'Name')
    LOGGER.debug('Filtered systems by name \'{0}\''
                 ' to {1}'.format(system_filter, filtered))
    return filtered


def filter_groups_by_state(vcs_list, state_filter=None):
    """
    Filter group data by ``State`` key
    :param vcs_list: Data to filter, requires a 'State' key
    :type vcs_list: list
    :param state_filter: Filter by state value
    :type state_filter: str|None
    :return:
    """
    filtered = _filter_property(vcs_list, state_filter, 'State')
    if state_filter:
        LOGGER.debug('Filtered group states by \'{0}\' '
                     'to {1}'.format(state_filter, filtered))
    return filtered


def filter_groups_by_systems(vcs_list, system_filter=None):
    """
    Filter group data by ``System`` key
    :param vcs_list: Data to filter, requires a 'System' key
    :type vcs_list: list
    :param system_filter: Filter by system value
    :type system_filter: str|None
    :return:
    """
    filtered = _filter_property(vcs_list, system_filter, 'System')
    if system_filter:
        LOGGER.debug('Filtered groups systems by \'{0}\''
                     ' to {1}'.format(system_filter, filtered))
    return filtered


def filter_groups_by_name(vcs_list, group_filter=None):
    """
    Filter group data by ``Name`` key
    :param vcs_list: Data to filter, requires a 'Name' key
    :type vcs_list: list
    :param group_filter: Filter by group name value
    :type group_filter: str|None
    :return:
    """
    filtered = _filter_property(vcs_list, group_filter, 'Name')
    if group_filter:
        LOGGER.debug('Filtered groups by name \'{0}\''
                     ' to {1}'.format(group_filter, filtered))
    return filtered


def filter_systems_by_state(vcs_system_list, state_filter=None):
    """
    Filter system data by ``State`` key
    :param vcs_system_list: Data to filter, requires a 'State' key
    :type vcs_system_list: list
    :param state_filter: Filter by system state
    :type state_filter: str|None
    :return:
    """
    filtered = _filter_property(vcs_system_list, state_filter, 'State')
    if state_filter:
        LOGGER.debug('Filtered system states by \'{0}\' '
                     'to {1}'.format(state_filter, filtered))
    return filtered


def get_group_info(group=None, system=None, mco_host=None,
                   sort_key=None, states=None):
    """
    Find info on group
    :param group: group name
    :param system: system name
    :param mco_host: host name
    :param sort_key: sort method
    :param states: state
    :return:
    """
    enmagent = EnminstAgent()
    headers, grpstates = enmagent.hagrp_state(mco_host=mco_host)
    grpstates = filter_groups_by_state(grpstates, states)
    grpstates = filter_groups_by_systems(grpstates, system)
    grpstates = filter_groups_by_name(grpstates, group)
    grpstates = sort_tab_data(grpstates, sort_key, headers)

    LOGGER.debug('Found the following groups {0}'.format(grpstates))
    return headers, grpstates


def get_system_info(mco_host=None, sort_key=None, states=None):
    """
    Get system information
    :param mco_host: host
    :param sort_key: method of sort
    :param states: state
    :return:
    """
    enmagent = EnminstAgent()
    headers, sysstates = enmagent.hasys_state(mco_host=mco_host)
    sysstates = filter_groups_by_state(sysstates, state_filter=states)
    sysstates = sort_tab_data(sysstates, sort_key, headers)
    LOGGER.debug('Found the following systems {0}'.format(sysstates))
    return headers, sysstates


def check_systems_exist(system_filter, mco_host=None):
    """
    Ensure system exists
    :param system_filter:
    :param mco_host:
    :raise SystemExit:
    """
    if system_filter:
        _, systems = get_system_info(mco_host=mco_host)
        filtered = filter_systems_by_name(systems, system_filter=system_filter)
        if len(filtered) == 0:
            LOGGER.error('No system matching \'{0}\' found '
                         'in any clusters!'.format(system_filter))
            raise SystemExit(ExitCodes.VCS_SYSTEM_NOT_FOUND)


def is_dps_using_neo4j():
    '''
    Check global.properties if DPS switched to Neo4j or still on Versant
    '''
    dps_using_ne4j = '/usr/bin/timeout 20s '\
        '/bin/grep -q "dps_persistence_provider=neo4j" ' \
        '/ericsson/tor/data/global.properties'
    exit_code = getstatusoutput(dps_using_ne4j)[0]
    LOGGER.debug('Get dps_using_neo4j in global.prop: {0}'.format(exit_code))
    if exit_code == 0:
        return True
    return False
