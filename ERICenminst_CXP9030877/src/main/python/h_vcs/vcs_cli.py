# pylint: disable=too-many-lines
"""
Main goal of this module is to provide some high level VCS information like
what Groups are in what cluster, status of groups/services.
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
import os
import re
import sys
import traceback
from argparse import ArgumentParser
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
from os.path import dirname, join, exists

from datetime import datetime

from h_litp.litp_rest_client import LitpObject, LitpRestClient
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging
from h_puppet.h_puppet import discover_peer_nodes
from h_puppet.mco_agents import McoAgentException, EnminstAgent, \
    VcsCmdApiAgent
from h_util.h_utils import ExitCodes, screen
from h_vcs.vcs_utils import VcsCodes, get_vcs_group_info, VcsException, \
    VCS_AVAIL_PARALLEL, \
    VCS_AVAIL_STANDALONE, VCS_AVAIL_ACTIVE_STANDBY, \
    filter_tab_data, \
    sort_tab_data, report_tab_data, VCS_GRP_SVS_STATE_ONLINE, \
    VCS_GRP_SVS_STATE_UNKNOWN, VCS_GRP_SVS_STATE_OFFLINE, match_filter, \
    VcsStates, filter_systems_by_state, get_group_info, \
    filter_groups_by_name, filter_groups_by_systems, get_group_avail_type, \
    VCS_NA, is_dps_using_neo4j


class Vcs(object):  # pylint: disable=R0904
    """
    VCS commands

    """
    STATE_FROZEN_TEMP = 'Temp'
    STATE_FROZEN_PERM = 'Perm'
    STATE_UNFROZEN = '-'
    STATE_INVALID = 'Invalid'
    STATE_UNDEFINED = 'Undefined'
    SYSTEM_STATE_RUNNING = 'RUNNING'
    STATE_OK = 'OK'
    H_CLUSTER = 'Cluster'
    H_GROUP = 'Group'
    H_SYSTEM = 'System'
    H_TYPE = 'HAType'
    H_SERVICE_STATE = 'ServiceState'
    H_GROUP_STATE = 'GroupState'
    H_SYSTEM_STATE = 'State'
    H_UPTIME = 'Uptime'
    H_FROZEN = 'Frozen'
    H_LITP_SERVICE_TYPE = 'ServiceType'
    H_NAME = 'Name'
    H_DEPS = 'Dependencies'

    ENM_DB_CLUSTER_NAME = 'db_cluster'
    VCS_GROUPNAME_PREFIX = 'Grp_CS_'
    H_ONLINE_TIMEOUT = 'online_timeout'
    H_OFFLINE_TIMEOUT = 'offline_timeout'
    H_ONLINE_RETRY = 'online_retry'
    H_OFFLINE_RETRY = 'offline_retry'

    VCS_GROUP_TABLE_HEADERS = [H_CLUSTER, H_GROUP, H_SYSTEM, H_TYPE,
                               H_LITP_SERVICE_TYPE, H_SERVICE_STATE,
                               H_GROUP_STATE, H_FROZEN]
    VCS_SYSTEMS_TABLE_HEADERS = [H_SYSTEM, H_SYSTEM_STATE, H_CLUSTER,
                                 H_FROZEN]
    DEFAULT_MCO_TIMEOUT = 20

    # Date format from "hamsg" command. Sample: "Mon Oct 24 14:09:43 2016"
    HAMSG_DATE_FORMAT = '%a %b %d %H:%M:%S %Y'

    def __init__(self):
        self.logger = init_enminst_logging()

    def info(self, message):
        """
        Log a message at level INFO.
        :param message: The message to log
        :return:
        """
        self.logger.info(message)

    def warning(self, message):
        """
        Log a message at level WARNING.
        :param message: The message to log
        :return:
        """
        self.logger.warning(message)

    def exception(self, msg):
        """
        Log a message at level ERROR and include the stack trace.
        :param msg: The message to log
        :return:
        """
        self.logger.exception(msg)

    @staticmethod
    def get_litp_client():
        """
        Get an instance of the LitpRestClient

        :returns: LitpRestClient instance
        :rtype: LitpRestClient
        """
        return LitpRestClient()

    @staticmethod
    def write_csv(output_file, headers, celldata):
        """
        Write table data to a file

        :param output_file: The output file
        :type output_file: str
        :param headers: List of column headers
        :type headers: list
        :param celldata: List of rows (each row is a dict() )
        :type celldata: list( dict )
        """
        output_file = output_file
        _pdir = dirname(output_file)
        if not _pdir or _pdir == '':
            _pdir = os.environ['HOME']
            output_file = join(_pdir, output_file)
        if not exists(_pdir):
            os.makedirs(_pdir)
        with open(output_file, 'w') as _fp:
            for header in headers:
                _fp.write(header)
                _fp.write(',')
            _fp.write('\n')
            for row in celldata:
                for header in headers:
                    _fp.write(row[header])
                    _fp.write(',')
                _fp.write('\n')

    @staticmethod
    def _get_frozen_type(temp_frozen, perm_frozen):
        """
        Get a text representation of the freeze type (temp|perm)
        :param temp_frozen: Boolean indicating if temp frozen
        :param perm_frozen: Boolean indicating if perm frozen
        :return:
        """
        if temp_frozen:
            return Vcs.STATE_FROZEN_TEMP
        elif perm_frozen:
            return Vcs.STATE_FROZEN_PERM
        else:
            return Vcs.STATE_UNFROZEN

    @staticmethod
    def _get_group_struct(cluster_name, group_name,  # pylint: disable=R0913
                          sysname, availtype, srvstates, gpstate,
                          temp_frozen, perm_frozen, modeled_service_type):
        """
        Get a struct representing the input data
        :param cluster_name: The VCS cluster name
        :param group_name: The VCS group name
        :param sysname: The system the group is on
        :param availtype: The group availability type
        :param srvstates: The group VCS state on the system
        :param gpstate: The group availability state
        :param temp_frozen: Is the goup temporarily frozen
        :param perm_frozen: Is the goup permanently frozen
        :param modeled_service_type: The service type (vm, lsb, etc)
        :return:
        """
        _frozen = Vcs._get_frozen_type(temp_frozen, perm_frozen)

        return {Vcs.H_CLUSTER: cluster_name,
                Vcs.H_GROUP: group_name,
                Vcs.H_SYSTEM: sysname,
                Vcs.H_TYPE: availtype,
                Vcs.H_SERVICE_STATE: srvstates,
                Vcs.H_GROUP_STATE: gpstate,
                Vcs.H_FROZEN: _frozen,
                Vcs.H_LITP_SERVICE_TYPE: modeled_service_type}

    @staticmethod
    def _get_system_struct(system_name, sysstate, cluster_name,
                           temp_frozen, perm_frozen):
        """
        Get a struct representing the input data
        :param system_name: The system name
        :param sysstate: The system VCS state
        :param cluster_name: The cluster the system is in
        :param temp_frozen: Is the goup temporarily frozen
        :param perm_frozen: Is the goup permanently frozen
        :return:
        """
        _frozen = Vcs._get_frozen_type(temp_frozen, perm_frozen)
        return {Vcs.H_SYSTEM: system_name,
                Vcs.H_SYSTEM_STATE: sysstate,
                Vcs.H_CLUSTER: cluster_name,
                Vcs.H_FROZEN: _frozen}

    @staticmethod
    def _get_service_resource_type(resource_list, vm_types, litp):
        """
        Get the service type i.e. vm, lsb, etc.

        :param resource_list: List of modeled resources in the VCS group
        :type resource_list: list
        :param vm_types: VM model item types
        :type vm_types: list
        :param litp: LITP REST api
        :type litp: LitpRestClient
        :returns: The service type i.e. a vm, lsb or mixed
        :rtype: str
        """
        app_type = None
        for _app in resource_list:
            app = LitpObject(None, _app['data'],
                             litp.path_parser)
            if app.item_type in vm_types:
                if app_type and app.item_type != 'vm':
                    app_type = 'mixed'
                else:
                    app_type = 'vm'
            else:
                if app_type and app_type != app.item_type:
                    app_type = 'mixed'
                else:
                    app_type = 'lsb'
        return app_type

    @staticmethod
    def _get_hostname_vcs_aliases():
        """
        Get a mapping of modeled node ids to hostnames

        :returns: dict(hostname=>id), dict(id=>hostname)
        :rtype: dict, dict
        """
        litp = Vcs.get_litp_client()
        system_aliases_kbs = {}
        system_aliases_kbm = {}
        for deployment in litp.get_children('/deployments'):
            for cluster in litp.get_children(
                    '{0}/clusters'.format(deployment['path'])):
                for node in litp.get_children(
                        '{0}/nodes'.format(cluster['path'])):
                    nobj = LitpObject(None, node['data'], litp.path_parser)
                    hostname = nobj.get_property('hostname')
                    system_aliases_kbs[hostname] = nobj.item_id
                    system_aliases_kbm[nobj.item_id] = hostname
        return system_aliases_kbs, system_aliases_kbm

    @staticmethod
    def _get_modeled_clusters(cluster_filter=None):
        """
        Get a list of modeled clusters and the nodes in each one

        :param cluster_filter: Only get info on clusters matching this
        :type cluster_filter: str (regex)
        :returns: Map containing cluster & node info, key is the cluster name
        and value is a list() of nodes (hostnames)

        :rtype: dict
        """
        litp = Vcs.get_litp_client()
        modeled_clusters = {}
        deployments = litp.get_children('/deployments')
        for deployment in deployments:
            p_clusters = '{0}/clusters'.format(deployment['path'])
            clusters = litp.get_children(p_clusters)
            for cluster in clusters:
                clusterid = LitpObject(None, cluster['data'],
                                       litp.path_parser).item_id
                if not match_filter(cluster_filter, clusterid):
                    continue
                modeled_clusters[clusterid] = []
                p_nodes = '{0}/nodes'.format(cluster['path'])
                cluster_nodes = litp.get_children(p_nodes)
                for node in cluster_nodes:
                    nobj = LitpObject(None, node['data'], litp.path_parser)
                    modeled_clusters[clusterid].append(
                            nobj.get_property('hostname'))
        return modeled_clusters

    @staticmethod
    def _get_modeled_node_states():
        """
        Get the model item state of all nodes in the LITP model

        :returns: Map of nodes and their model item state e.g Applied/Initial
        :rtype: dict
        """
        return Vcs.get_litp_client().get_node_states()

    @staticmethod
    def _get_modeled_groups():
        """
        Get a list of modeled VCS groups

        :returns: VCS clusters and their contained clusters
        """
        litp = Vcs.get_litp_client()
        deployments = litp.get_children('/deployments')

        mclusters = {}
        vclusters = {}
        for deployment in deployments:
            clusters = litp.get_children(
                    '{0}/clusters'.format(deployment['path']))
            for cluster in clusters:
                cobj = LitpObject(None, cluster['data'], litp.path_parser)
                mclusters[cobj.item_id] = {}
                vclusters[cobj.item_id] = {}
                for service in litp.get_children(
                        '{0}/services'.format(cobj.path)):
                    sobj = LitpObject(cobj, service['data'], litp.path_parser)
                    mclusters[cobj.item_id][sobj.item_id] = sobj
                    pointer = sobj.item_id.replace('-', '_')
                    if pointer != sobj.item_id:
                        mclusters[cobj.item_id][pointer] = sobj
                    vcs_name = Vcs._to_vcs_name(cobj.item_id, pointer)
                    vclusters[cobj.item_id][vcs_name] = sobj
        return mclusters, vclusters

    @staticmethod
    def _to_model_name(vcs_cluster, vcs_group_name):
        """
        Get the model name for a VCS group

        :param vcs_cluster: The VCS cluster name
        :param vcs_group_name:  The VCS group name
        :returns: The model name for the VCS group
        :rtype: str
        """
        _index = len(Vcs.VCS_GROUPNAME_PREFIX) + len(vcs_cluster) + 1
        return vcs_group_name[_index:]

    @staticmethod
    def _to_vcs_name(group_cluster_id, group_model_id):
        """
        Get the VCS name for the group
        :param group_cluster_id: The item-id of the LITP cluster the group is
         in
        :param group_model_id: The item-id of the LITP group
        :return:
        """
        return '{0}{1}_{2}'.format(Vcs.VCS_GROUPNAME_PREFIX,
                                   group_cluster_id, group_model_id)

    @staticmethod
    def _get_view_string(real, aliases, view_type):
        """
        Get the string to display based on the view type

        :param real: The physical name e.g. a hostname
        :type real: str
        :param aliases: An alias for the device e.g. LITP model ID
        :type aliases: dict|str
        :param view_type: How the data should be displayed (by physical or
        alias ID). If ``v`` the physical text is used, if ``m`` the alias is
        used, if ``x`` the the physical & alias are returned (
        seperated by a forward slash)

        :type view_type: str (v|m|x)

        :returns: The string to display
        :rtype: str
        """
        if view_type == 'm':
            if type(aliases) is dict:
                return aliases.get(real, real)
            else:
                return aliases
        elif view_type == 'x':
            if type(aliases) is dict:
                alias = aliases.get(real, real)
            else:
                alias = aliases
            return '{0}/{1}'.format(real, alias)
        else:
            return real

    @staticmethod
    def _get_modeled_group_timeouts(cluster_name, group_name):
        """
        Get the online/offline VCS timeouts for a group

        :param cluster_name: The VCS cluster name
        :type: str
        :param group_name: The modeled VCS group name
        :type group_name: str
        :returns: {Vcs.H_ONLINE_TIMEOUT: N, Vcs.H_OFFLINE_TIMEOUT: N}
        :rtype: dict
        """
        litp = Vcs.get_litp_client()
        deployments = litp.get_children('/deployments')
        for deployment in deployments:
            serv_path = '{0}/clusters/{1}/services'.format(deployment['path'],
                                                           cluster_name)
            services = litp.get_children(serv_path)
            for service in services:
                obj = LitpObject(None, service['data'], litp.path_parser)
                # vcs and model names arnt a 1:1 match ....
                if obj.item_id.replace('-', '_') == group_name:
                    return {
                        Vcs.H_ONLINE_TIMEOUT:
                            obj.get_property(Vcs.H_ONLINE_TIMEOUT),
                        Vcs.H_OFFLINE_TIMEOUT:
                            obj.get_property(Vcs.H_OFFLINE_TIMEOUT),
                    }
        return {Vcs.H_ONLINE_TIMEOUT: '600', Vcs.H_OFFLINE_TIMEOUT: '600'}

    @staticmethod
    def _get_modeled_group_retry_limit():
        """
        Get the VCS groups online/offline retry count
        :returns: {Vcs.H_ONLINE_RETRY: N, Vcs.H_OFFLINE_RETRY: N}
        :rtype: dict
        """
        return {Vcs.H_ONLINE_RETRY: '3', Vcs.H_OFFLINE_RETRY: '3'}

    @staticmethod
    def _get_modeled_group_types():
        """
        Get a list of modeled VCS groups and the service type (vm or lsb)

        :returns: Collection of modeled VCS groups
        :rtype: dict
        """
        vm_type = ['reference-to-vm-service', 'vm-service']
        litp = Vcs.get_litp_client()
        group_types = {}

        deployments = litp.get_children('/deployments')
        for deployment in deployments:
            clusters = litp.get_children(
                    '{0}/clusters'.format(deployment['path']))
            for cluster in clusters:
                services = litp.get_children(
                        '{0}/services'.format(cluster['path']))
                for _service in services:
                    service = LitpObject(None, _service['data'],
                                         litp.path_parser)
                    sdata = {'type': '',
                             'node_list':
                                 service.get_property('node_list').split(',')}

                    applications = litp.get_children(
                            '{0}/applications'.format(service.path))
                    if applications:
                        app_type = Vcs._get_service_resource_type(applications,
                                                                  vm_type,
                                                                  litp)
                    else:
                        runtimes = litp.get_children(
                                '{0}/runtimes'.format(service.path))
                        app_type = Vcs._get_service_resource_type(
                                runtimes, vm_type, litp)
                    sdata['type'] = app_type

                    group_types[service.item_id.replace('-', '_')] = sdata
                    group_types[
                        service.get_property('name').replace(
                                '-', '_')] = sdata
        return group_types

    @staticmethod
    def _filter_clusters(cluster_filter, group_filter, system_filter,
                         vcs_group_info, node_aliases):
        """
        Remove entries not matching filters

        :param cluster_filter: Regex to match for clusters to keep
        :param group_filter:  Regex to match for groups to keep
        :param system_filter: Regex to match for groups that belong to systems
        :param vcs_group_info: List of VCS groups to filter.
        :param node_aliases: VCS system aliases; model_id => hostname
        :return:
        """
        filtered_clusters = {}
        for cluster_name, cluster_groups in vcs_group_info.items():
            if match_filter(cluster_filter, cluster_name):
                filtered_groups = {}
                cluster_systems = set()
                for group_name, obj in cluster_groups.items():
                    if match_filter(group_filter, group_name):
                        nodelist = obj.get_property('node_list').split(',')
                        real_names = [node_aliases[s] for s in nodelist if
                                      True]
                        if match_filter(system_filter, real_names):
                            cluster_systems.update(real_names)
                            filtered_groups[group_name] = obj
                if filtered_groups:
                    filtered_clusters[cluster_name] = {
                        'groups': filtered_groups,
                        'systems': list(cluster_systems)
                    }
        return filtered_clusters

    @staticmethod
    def _build_parallel_group_info(cluster_name,  # pylint: disable=R0913,R0914
                                   view_group_name,
                                   group_data, node_aliases, view_type,
                                   uptimes, temp_frozen, perm_frozen,
                                   litp_type):
        """
        Build a list of data structs that will be displayed

        :param cluster_name: The VCS group cluster
        :param view_group_name: The name of the group
        :param group_data: All the group data
        :param node_aliases: System aslias (modelid: hostname)
        :param view_type: How the data should be displayed
        :param uptimes: Include group uptimes
        :param temp_frozen: Flag to indicate if the group is temp frozen
        :param perm_frozen: Flag to indicate if the group is perm frozen
        :param litp_type: The resource type e.g. vm or lsb
        :returns: List of structs that will be displayed
        :rtype: list
        """
        online_count = 0
        rows = []
        for sysname, statedata in group_data['systems'].items():
            sgstate = statedata['state']

            v_system = Vcs._get_view_string(sysname,
                                            node_aliases,
                                            view_type)

            row_data = Vcs._get_group_struct(cluster_name,
                                             view_group_name,
                                             v_system,
                                             group_data['type'],
                                             ','.join(sgstate),
                                             VCS_GRP_SVS_STATE_UNKNOWN,
                                             temp_frozen,
                                             perm_frozen,
                                             litp_type)
            if uptimes:
                row_data[Vcs.H_UPTIME] = statedata['uptime']
            rows.append(row_data)
            if len(sgstate) == 1:
                if sgstate[0] == VCS_GRP_SVS_STATE_ONLINE:
                    online_count += 1
        for row in rows:
            if online_count == len(group_data['systems']):
                row[Vcs.H_GROUP_STATE] = Vcs.STATE_OK
            else:
                row[Vcs.H_GROUP_STATE] = Vcs.STATE_INVALID
        return rows

    @staticmethod
    def _build_activestandby_group_info(  # pylint: disable=R0913,R0914
            cluster_name, view_group_name, group_data, node_aliases,
            view_type, uptimes, temp_frozen, perm_frozen, litp_type):
        """
        Build a list of data structs that will be displayed

        :param cluster_name: The VCS group cluster
        :param view_group_name: The name of the group
        :param group_data: All the group data
        :param node_aliases: System aslias (modelid: hostname)
        :param view_type: How the data should be displayed
        :param uptimes: Include group uptimes
        :param temp_frozen: Flag to indicate if the group is temp frozen
        :param perm_frozen: Flag to indicate if the group is perm frozen
        :param litp_type: The resource type e.g. vm or lsb
        :returns: List of structs that will be displayed
        :rtype: list
        """
        active_count = 0
        standby_count = 0
        rows = []

        for sysname, statedata in group_data['systems'].items():

            v_system = Vcs._get_view_string(sysname,
                                            node_aliases,
                                            view_type)

            sgstate = statedata['state']
            row_data = Vcs._get_group_struct(cluster_name,
                                             view_group_name,
                                             v_system,
                                             group_data['type'],
                                             ','.join(sgstate),
                                             VCS_GRP_SVS_STATE_UNKNOWN,
                                             temp_frozen,
                                             perm_frozen,
                                             litp_type)
            if uptimes:
                row_data[Vcs.H_UPTIME] = statedata['uptime']
            rows.append(row_data)
            if len(sgstate) == 1:
                if sgstate[0] == VCS_GRP_SVS_STATE_ONLINE:
                    active_count += 1
                elif sgstate[0] == VCS_GRP_SVS_STATE_OFFLINE:
                    row_data[Vcs.H_UPTIME] = '-'
                    standby_count += 1
        for row in rows:
            if active_count == 1 and standby_count == 1:
                row[Vcs.H_GROUP_STATE] = Vcs.STATE_OK
            else:
                row[Vcs.H_GROUP_STATE] = Vcs.STATE_INVALID
        return rows

    @staticmethod
    def add_groupstatus_row(cluster_data,  # pylint: disable=R0913
                            group_data, cluster_name, group_name, view_type,
                            group_service_types, aliase_keyreal, uptimes):
        """
        Contruct a struct containing data for the get_cluster_group_status
        function

        :param cluster_data:
        :param group_data: The group data to display
        :param cluster_name: The cluster name
        :param group_name: The group name
        :param view_type: The view type (by VCS name or model name)
        :param group_service_types: The group service type e.g. vm/lsb/etc.
        :param aliase_keyreal: System aslias (modelid: hostname)
        :param uptimes: Include group uptimes
        :return:
        """
        perm_frozen = bool(int(group_data['global']['Frozen']))
        temp_frozen = bool(int(group_data['global']['TFrozen']))
        if group_name == '-':
            litp_group_name = '-'
            litp_type = '-'
        else:
            s_index = group_name.index(cluster_name) + len(cluster_name)
            litp_group_name = group_name[s_index + 1:]
            litp_type = group_service_types.get(litp_group_name,
                                                {}).get('type', '-')
        v_group_name = Vcs._get_view_string(group_name,
                                            litp_group_name,
                                            view_type)

        if group_data['type'] in [VCS_AVAIL_PARALLEL, VCS_AVAIL_STANDALONE,
                                  VCS_NA]:
            rows = Vcs._build_parallel_group_info(cluster_name,
                                                  v_group_name,
                                                  group_data,
                                                  aliase_keyreal,
                                                  view_type,
                                                  uptimes,
                                                  temp_frozen,
                                                  perm_frozen,
                                                  litp_type)
            cluster_data.extend(rows)
        elif group_data['type'] == VCS_AVAIL_ACTIVE_STANDBY:
            rows = Vcs._build_activestandby_group_info(cluster_name,
                                                       v_group_name,
                                                       group_data,
                                                       aliase_keyreal,
                                                       view_type,
                                                       uptimes,
                                                       temp_frozen,
                                                       perm_frozen,
                                                       litp_type)
            cluster_data.extend(rows)
        else:
            raise VcsException('Unknown mode {0}'.format(group_data['type']))

    @staticmethod
    def get_cluster_group_status(  # pylint: disable=R0912,R0913,R0914,R0915
            cluster_filter=None, group_filter=None, system_filter=None,
            uptimes=False, view_type=None, verbose=True):
        """
        Get details on VCS groups in VCS clusters.

        :param cluster_filter: Limit results to clusters matching this regex.
        :type cluster_filter: str
        :param group_filter: Limit results to groups matching this regex.
        :type group_filter: str
        :param system_filter: Limit results to system states matching
        this regex.
        :type system_filter: str || None
        :param uptimes: Include VCS group uptimes if available.
        :type uptimes: bool
        :param view_type: The view type being used i.e. how to format the
        output data; by LITP or VCS naming
        :type view_type: str
        :param verbose: Enable verbose output to stdout
        :type verbose: bool
        :rtype: dict[]
        """

        _, all_groups_vcsid = Vcs._get_modeled_groups()
        aliase_keyreal, aliases_keymodel = Vcs._get_hostname_vcs_aliases()
        group_service_types = Vcs._get_modeled_group_types()

        _filtered_clusters = Vcs._filter_clusters(cluster_filter, group_filter,
                                                  system_filter,
                                                  all_groups_vcsid,
                                                  aliases_keymodel)

        cluster_data = []

        initial_state_groups = {}
        other_state_groups = {}
        # Remove any groups that are in the Initial state in LITP,
        # They haven't been created in VCS yet, these Initial groups
        # are added to the report list as state 'Undefined'
        for cluster, groups in _filtered_clusters.items():
            for group_name, group_data in groups['groups'].items():
                if group_data.properties.get('deactivated') == 'true':
                    continue
                if group_data.state == LitpRestClient.ITEM_STATE_INITIAL:
                    insert_map = initial_state_groups
                else:
                    insert_map = other_state_groups
                if cluster not in insert_map:
                    insert_map[cluster] = {
                        'systems': groups['systems'],
                        'groups': {}
                    }
                insert_map[cluster]['groups'][group_name] = group_data

        known_hosts = discover_peer_nodes()
        for cluster_name in other_state_groups.keys():
            system_list = other_state_groups[cluster_name]['systems']
            system_list = sorted(system_list)
            modeled_groups = other_state_groups[cluster_name]['groups']

            request_count = 0
            group_data = None
            for system in system_list:
                request_count += 1
                if system not in known_hosts:
                    screen('WARNING: MCO undiscovered cluster host {0}'.format(
                            system))
                    continue
                screen('Getting groups from cluster {0} '
                       'on system {1}'.format(cluster_name, system),
                       verbose=verbose)
                try:
                    gps = modeled_groups.keys()
                    group_data = get_vcs_group_info(system, groups=gps,
                                                    include_uptimes=uptimes)
                    break
                except McoAgentException as error:
                    if VcsCodes.is_error(VcsCodes.V_16_1_10600, error):
                        screen('WARNING: System {0} unavailable'
                               .format(system))
                        continue
                    elif VcsCodes.is_error(VcsCodes.V_16_1_10011, error):
                        screen('WARNING: System {0} powered off'
                               .format(system))
                        continue
                    else:
                        raise
            if not group_data and request_count == len(system_list):
                screen('WARNING: Could not get any group information from '
                       'any systems belonging to the cluster {0}: {1}'
                       ''.format(cluster_name, ', '.join(system_list), ))
                gdata = {
                    'global': {'Frozen': '0', 'TFrozen': '0'},
                    'type': 'N/A', 'systems': {}
                }
                for sysname in system_list:
                    gdata['systems'][sysname] = {'state': '-', 'uptime': 0}

                Vcs.add_groupstatus_row(cluster_data,
                                        gdata, cluster_name,
                                        '-', view_type,
                                        group_service_types,
                                        aliase_keyreal, uptimes)
                continue
            for group_name, data in group_data.items():
                Vcs.add_groupstatus_row(cluster_data,
                                        data, cluster_name,
                                        group_name, view_type,
                                        group_service_types,
                                        aliase_keyreal, uptimes)

        for cluster_name in initial_state_groups.keys():
            init_groups = initial_state_groups[cluster_name]['groups']
            for group_name, data in init_groups.items():
                for sysname in data.get_property('node_list').split(','):
                    s_index = group_name.index(cluster_name) + \
                              len(cluster_name)
                    litp_group_name = group_name[s_index + 1:]
                    v_group_name = Vcs._get_view_string(group_name,
                                                        litp_group_name,
                                                        view_type)

                    row_data = Vcs._get_group_struct(cluster_name,
                                                     v_group_name,
                                                     aliases_keymodel[sysname],
                                                     'N/A',
                                                     'N/A',
                                                     Vcs.STATE_UNDEFINED,
                                                     False,
                                                     False,
                                                     'N/A')
                    cluster_data.append(row_data)
        headers = list(Vcs.VCS_GROUP_TABLE_HEADERS)
        if uptimes and Vcs.H_UPTIME not in headers:
            headers.append(Vcs.H_UPTIME)
        return cluster_data, headers

    @staticmethod
    def verify_cluster_group_status(  # pylint: disable=R0913,R0914
            cluster_filter, group_filter, group_type, system_filter,
            groupstate_filter, systemstate_filter, sort_keys=None,
            csvfile=None, show_uptime=False, view_type=None, verbose=True):
        """
        Verify VCS clusters/group are in valid states.

        If any VCS groups (after filtering) are not in the OK state a
        SystemExit error is raised.

        :param cluster_filter: Limit results to clusters matching this regex.
        :type cluster_filter: str || None
        :param group_filter: Limit results to groups matching this regex.
        :type group_filter: str || None
        :param group_type: Limit results to group types matching this regex.
        :type group_type: str || None
        :param system_filter: Limit results to systems matching this regex.
        :type system_filter: str || None
        :param groupstate_filter: Limit results to group states matching
        this regex.
        :type groupstate_filter: str || None
        :param systemstate_filter: Limit results to system states matching
        this regex.
        :type systemstate_filter: str || None
        :param sort_keys: Sort the output table on these keys
        :type sort_keys: str || None
        :param csvfile: Write data to a csv file instead of screen.k
        :type csvfile: str
        :param show_uptime: Limit results to clusters matching this regex.
        :type show_uptime: bool
        :param view_type: The view type being used i.e. how to format the
        output data; by LITP or VCS naming

        :type view_type: str
        :param verbose: Enable verbose output to stdout
        :type verbose: bool
        :return:
        """
        gfilter = group_filter or '{0}.*'.format(Vcs.VCS_GROUPNAME_PREFIX)
        info, headers = Vcs.get_cluster_group_status(cluster_filter, gfilter,
                                                     system_filter,
                                                     uptimes=show_uptime,
                                                     view_type=view_type,
                                                     verbose=verbose)
        info = filter_tab_data(info, system_filter, Vcs.H_SYSTEM)
        info = filter_tab_data(info, group_type, Vcs.H_TYPE)
        info = filter_tab_data(info, groupstate_filter, Vcs.H_GROUP_STATE)
        info = filter_tab_data(info, systemstate_filter, Vcs.H_SERVICE_STATE)
        if sort_keys:
            info = sort_tab_data(info, sort_keys, headers)
        if csvfile:
            Vcs.write_csv(csvfile, headers, info)
            screen('Wrote details to {0}'.format(csvfile))
        else:
            report_tab_data(None, headers, info, verbose=verbose)
        invalid_groups = False

        vm_info = Vcs.neo4j_health_check(info)
        for row in vm_info:
            if 'versant_clustered_service' in row[Vcs.H_GROUP]:
                if is_dps_using_neo4j():
                    screen('Neo4j in use, skip Versant SG')
                    continue

            if row[Vcs.H_GROUP_STATE] in [Vcs.STATE_INVALID,
                                          Vcs.STATE_UNDEFINED]:
                invalid_groups = True
                break

        if not invalid_groups:
            for row in info:
                if row[Vcs.H_FROZEN] in [Vcs.STATE_FROZEN_TEMP,
                        Vcs.STATE_FROZEN_PERM] and \
                        'versant_clustered_service' \
                        not in row[Vcs.H_GROUP]:
                    invalid_groups = True
                    break

        if invalid_groups:
            raise SystemExit(ExitCodes.VCS_INVALID_STATE)

    @staticmethod
    def neo4j_health_check(service_groups):
        """
        If neo4j is install but not used by dps
        then offline and freeze neo4j
        """
        neo4j_cluster_information = Vcs.get_cluster_group_status(
            Vcs.ENM_DB_CLUSTER_NAME,
            '.*neo4j_clustered_service',
            verbose=False)
        if not neo4j_cluster_information[0]:
            # Neo4j SG not installed
            return service_groups
        if is_dps_using_neo4j():
            # DPS is using neo4j
            return service_groups

        # DPS not using neo4j.
        service_groups[:] = [s for s \
            in service_groups if 'neo4j_clustered_service' not in s['Group']]
        return service_groups

    @staticmethod
    def is_sg_persistently_frozen(cluster_name, sg_name):
        """
        Check if SG persistently frozen
        :param cluster_name: VCS cluster name
        :param sg_name: SG name
        :return: True if SG persistently frozen, False otherwise
        :rtype: Boolean
        """
        info, _ = Vcs.get_cluster_group_status(cluster_name,
                                               sg_name, verbose=False)
        for entry in info:
            if entry[Vcs.H_FROZEN] != 'Perm':
                screen('{0} is not persistently frozen on node is {1}'.
                       format(sg_name, entry['System']))
                return False
        return True

    @staticmethod
    def _cluster_system_row(cluster_name, state_data, system_data,
                            aliase_keyreal, view_type):
        """
        Create a table row for VCS system data
        :param cluster_name: VCS cluster name
        :param state_data: System state data
        :param system_data: System details
        :param aliase_keyreal: Host to name aliases
        :param view_type: View type
        :returns: Row for show_tabbed_data
        :rtype: dict
        """
        system_name = state_data[Vcs.H_NAME]
        system_state = ','.join(state_data[Vcs.H_SYSTEM_STATE])
        system_info = system_data[system_name]
        if system_state == VcsStates.RUNNING:
            perm_frozen = bool(int(system_info['Frozen']))
            temp_frozen = bool(int(system_info['TFrozen']))
        else:
            perm_frozen = temp_frozen = None
        v_system = Vcs._get_view_string(system_name,
                                        aliase_keyreal,
                                        view_type)
        return Vcs._get_system_struct(
                v_system, system_state,
                cluster_name, temp_frozen, perm_frozen)

    @staticmethod
    def _cluster_system_errors(mco_comms_errors,  # pylint: disable=R0913
                               systems_skipped,
                               vcs_system_errors,
                               cluster_name, system_list,
                               aliase_keyreal, view_type,
                               row_data):
        """
        Insert a row for systems that are not in a RUNNING state
        :param mco_comms_errors: Number of hosts skipped because MCO
        doesnt know about them

        :param systems_skipped: Total number of skipped systems
        :param vcs_system_errors: VCS errors when getting info from systems
        :param cluster_name: Cluster name
        :param system_list: Total system list
        :param aliase_keyreal: Aliases
        :param view_type: View type
        :param row_data: List to add the row too.
        :return:
        """
        if mco_comms_errors == systems_skipped:
            screen('WARNING: Could not get any system information'
                   ' from any systems belonging to the cluster'
                   ' {0}: {1}'.format(
                    cluster_name, ', '.join(system_list)))
        for sysname in system_list:
            v_system = Vcs._get_view_string(sysname,
                                            aliase_keyreal,
                                            view_type)
            if sysname in vcs_system_errors:
                error = vcs_system_errors[sysname]
                if VcsCodes.is_error(VcsCodes.V_16_1_10600, error):
                    _state = VcsStates.EXITED
                elif VcsCodes.is_error(VcsCodes.V_16_1_10011, error):
                    _state = VcsStates.POWERED_OFF
                else:
                    raise error
            else:
                _state = VCS_NA
            row_data.append(
                    Vcs._get_system_struct(
                            v_system, _state,
                            cluster_name, None, None))

    @staticmethod
    def get_cluster_system_status(  # pylint: disable=R0914
            cluster_filter=None, view_type=None):
        """
        Get cluster system states.

        :param cluster_filter: Limit to systems matched by the filter
        :type cluster_filter: str (regex)
        :param view_type: The view type being used i.e. how to format the
        output data; by LITP or VCS naming
        :type view_type: str
        :returns: States of the systems in a cluster
        :rtype tuple(dict, dict)
        """
        aliase_keyreal, _ = Vcs._get_hostname_vcs_aliases()
        clusters = Vcs._get_modeled_clusters(cluster_filter)
        modeled_node_states = Vcs._get_modeled_node_states()
        enminst = EnminstAgent()
        row_data = []
        known_hosts = discover_peer_nodes()
        screen('{0}: {1} peer nodes found.'
               .format('INFO' if known_hosts else 'WARNING', len(known_hosts)))
        vcs_system_errors = {}
        undefined_systems = []
        for cluster_name, system_list in clusters.items():
            system_list = sorted(system_list)
            mco_comms_errors = 0
            systems_skipped = 0
            for _system in system_list:
                mstate = modeled_node_states.get(_system, '')
                if _system not in known_hosts:
                    if mstate == LitpRestClient.ITEM_STATE_INITIAL:
                        _statedata = {
                            Vcs.H_NAME: _system,
                            Vcs.H_SYSTEM_STATE: [Vcs.STATE_UNDEFINED]}
                        _systemdata = {
                            _system: {'Frozen': 0, 'TFrozen': 0}
                        }
                        undefined_systems.append(
                                Vcs._cluster_system_row(
                                        cluster_name,
                                        _statedata,
                                        _systemdata,
                                        aliase_keyreal,
                                        view_type))
                    else:
                        mco_comms_errors += 1
                        screen('WARNING: MCO undiscovered cluster host {0}'
                               .format(_system))
                        systems_skipped += 1
                        continue
                else:
                    try:
                        _, system_states = enminst.hasys_state(_system)
                        system_data = enminst.hasys_display(system_list,
                                                            mco_host=_system)
                    except McoAgentException as error:
                        systems_skipped += 1
                        vcs_system_errors[_system] = error
                        continue
                    for state_data in system_states:
                        row_data.append(
                                Vcs._cluster_system_row(
                                        cluster_name,
                                        state_data,
                                        system_data,
                                        aliase_keyreal,
                                        view_type))
                    break
            if systems_skipped == len(system_list):
                Vcs._cluster_system_errors(
                        mco_comms_errors,
                        systems_skipped,
                        vcs_system_errors,
                        cluster_name, system_list, aliase_keyreal,
                        view_type, row_data)
        for undef_sys in undefined_systems:
            row_data.append(undef_sys)
        return Vcs.VCS_SYSTEMS_TABLE_HEADERS, row_data

    @staticmethod
    def verify_cluster_system_status(cluster_filter,  # pylint: disable=R0913
                                     systemstate_filter, sort_keys=None,
                                     csvfile=None, view_type=None,
                                     verbose=False):
        """
        Verify VCS cluster systems are in valid states.

        :param cluster_filter: Limit results to clusters matching this regex.
        :type cluster_filter: str || None
        :param systemstate_filter: Limit results to system states matching
        this regex.
        :type systemstate_filter: str || None
        :param sort_keys: Sort the output table on these keys
        :type sort_keys: str || None
        :param csvfile: Write data to a csv file instead of screen.
        :type csvfile: str
        :param view_type: The view type being used i.e. how to format the
        output data; by LITP or VCS naming
        :type view_type: str
        :param verbose: Enable verbose output to stdout
        :type verbose: bool
        """

        headers, rows = Vcs.get_cluster_system_status(cluster_filter,
                                                      view_type=view_type)
        rows = filter_systems_by_state(rows, state_filter=systemstate_filter)

        if sort_keys:
            rows = sort_tab_data(rows, sort_keys, headers)
        if csvfile:
            Vcs.write_csv(csvfile, headers, rows)
            screen('Wrote details to {0}'.format(csvfile))
        else:
            report_tab_data(None, headers, rows, verbose=verbose)

        invalid_system_states = False
        for row in rows:
            if row[Vcs.H_SYSTEM_STATE] != Vcs.SYSTEM_STATE_RUNNING or row[
                Vcs.H_FROZEN] in [Vcs.STATE_FROZEN_PERM,
                                  Vcs.STATE_FROZEN_TEMP]:
                invalid_system_states = True
                break
        if invalid_system_states:
            raise SystemExit(ExitCodes.VCS_INVALID_STATE)

    @staticmethod
    def show_history(cluster_filter=None,  # pylint: disable=R0914
                     group_filter=None, sort_by_date=False):
        """
        Display VCS history.

        :param cluster_filter: The VCS cluster the groups are part of
        :type cluster_filter: str
        :param group_filter: Limit results to groups matching this regex
        :type group_filter: str
        :param sort_by_date: Sort output by date and time rather than group
        :type group_filter: bool
        """
        _, all_groups_vcsid = Vcs._get_modeled_groups()
        _, aliases_keymodel = Vcs._get_hostname_vcs_aliases()
        agent = EnminstAgent()

        # We build up a sequence of tuples:
        #   (timestamp, message)
        # We may optionally then sort the list by timestamp, before outputting.
        history_data = []

        for cluster_name, groups in all_groups_vcsid.items():
            if not match_filter(cluster_filter, cluster_name):
                continue

            for group_name, data in groups.items():
                if not match_filter(group_filter, group_name):
                    continue

                nodelist = data.get_property('node_list').split(',')
                real_names = [aliases_keymodel[s] for s in nodelist if
                              True]
                events = agent.hagrp_history(group_name, real_names[0])
                if group_name not in events:
                    screen('Could not find any history for '
                           '{0}'.format(group_name))
                else:
                    for event in events[group_name]:
                        history_data.append((event['date'], event['info']))

        if sort_by_date:
            history_data.sort(
                key=lambda x: datetime.strptime(x[0], Vcs.HAMSG_DATE_FORMAT))

        for record in history_data:
            screen('{0} {1}'.format(record[0], record[1]))

    def hagrp_clear(self, group_name_filter, cluster_filter, system_filter):
        """
        Clear VCS group name
        :param group_name_filter: filter groups
        :param cluster_filter: Limit results to clusters matching this regex.
        :type cluster_filter: str || None
        :param system_filter: filter names
        """
        to_check = self._get_action_groups(group_name_filter,
                                           system_filter,
                                           cluster_filter)
        enminst_agent = EnminstAgent()
        any_cleared = False
        for group in to_check:
            clear = False
            for state in group[Vcs.H_SYSTEM_STATE]:
                if state in VcsStates.VCS_CLEAR_STATES:
                    clear = True
                    break
            if clear:
                any_cleared = True
                group_name = group[Vcs.H_NAME]
                group_system = group[Vcs.H_SYSTEM]
                self.logger.info('Clearing {0} on '
                                 '{1}'.format(group_name, group_system))
                enminst_agent.hagrp_clear(group_name, group_system)
        if not any_cleared:
            self.logger.info('No groups needed clearing.')

    @staticmethod
    def _search_for_groups(cluster_name,  # pylint: disable=R0914
                           group_name_filter, vcs_query_systems,
                           modeled_groups,
                           mco_cluster_data):
        """
        Get a list of VCS groups that match filters.

        :param cluster_name: The cluster name
        :type cluster_name: str
        :param group_name_filter: Search for groups in the cluster that
         match a regex.

        :type group_name_filter: str
        :param vcs_query_systems: The VCS systems the group can be on
        :type vcs_query_systems: list
        :param modeled_groups: List of LITP modeled groups
        :type modeled_groups: dict
        :returns: List of groups matching filters.
        :rtype: list
        """
        vcs_fnic = '(?!Grp_NIC_).*'
        # first remove Grp_NIC groups
        cluster_groups = filter_groups_by_name(mco_cluster_data,
                                               group_filter=vcs_fnic)
        # and then take the desired ones
        cluster_groups = filter_groups_by_name(cluster_groups,
                                               group_name_filter)
        cluster_groups = filter_groups_by_systems(cluster_groups,
                                                  '|'.join(vcs_query_systems))
        action_groups = []
        for group_info in cluster_groups:
            vcs_name = group_info[Vcs.H_NAME]
            data = {
                Vcs.H_NAME: vcs_name,
                Vcs.H_SYSTEM: group_info[Vcs.H_SYSTEM],
                Vcs.H_CLUSTER: cluster_name,
                Vcs.H_SYSTEM_STATE: group_info[Vcs.H_SYSTEM_STATE]
            }

            model_name = Vcs._to_model_name(cluster_name, vcs_name)
            if model_name in modeled_groups[cluster_name]:
                mgroup = modeled_groups[cluster_name][model_name]
            else:
                raise VcsException(
                        'No modeled group found called {0}'.format(model_name))
            active = int(mgroup.get_property('active'))
            standby = int(mgroup.get_property('standby'))
            num_systems = len(mgroup.get_property('node_list').split(','))
            data[Vcs.H_TYPE] = get_group_avail_type(active, standby,
                                                    num_systems)
            data[Vcs.H_ONLINE_TIMEOUT] = mgroup.get_property(
                    Vcs.H_ONLINE_TIMEOUT, '600')
            data[Vcs.H_OFFLINE_TIMEOUT] = mgroup.get_property(
                    Vcs.H_OFFLINE_TIMEOUT, '600')
            data[Vcs.H_ONLINE_RETRY] = mgroup.get_property(
                    Vcs.H_ONLINE_RETRY, '3')
            data[Vcs.H_OFFLINE_RETRY] = mgroup.get_property(
                    Vcs.H_OFFLINE_RETRY, '3')

            data[Vcs.H_DEPS] = []
            _deps = mgroup.get_property('dependency_list')
            if _deps:
                data[Vcs.H_DEPS] = _deps.split(',')

            action_groups.append(data)
        return action_groups

    def _filter_action_groups(self, system_filter, modeled_clusters):
        """
        Remove any groups that are not on a system matching the ststem filter
        expression

        :param system_filter: System name filter (regex)
        :param modeled_clusters: Modeled group dict()
        :returns:
        :rtype: dict
        """
        filtered_clusters = {}
        if system_filter:
            if system_filter == 'any':
                filtered_clusters = modeled_clusters
            else:
                for cname, slist in modeled_clusters.items():
                    filtered = []
                    for sname in slist:
                        if match_filter(system_filter, sname):
                            filtered.append(sname)
                    if filtered:
                        filtered_clusters[cname] = filtered
            if not filtered_clusters:
                self.logger.error('No systems found matching filter '
                                  '"{0}"'.format(system_filter))
                raise SystemExit(ExitCodes.VCS_SYSTEM_NOT_FOUND)
        else:
            filtered_clusters = modeled_clusters
        return filtered_clusters

    def _get_action_groups(self, group_name_filter, system_filter,
                           cluster_name):
        """
        Get a list of VCS groups that match the input filters.

        :param group_name_filter: Regex to filter group names
        :type group_name_filter: str|None
        :param system_filter: Regex to filter systems
        :type system_filter: str|None
        :param cluster_name: Regex to filter clusters
        :type cluster_name: str|None

        :returns: List of VCS groups matching input filters.
        :rtype: list
        """
        modeled_clusters = Vcs._get_modeled_clusters(cluster_name)
        modeled_groups, _ = Vcs._get_modeled_groups()
        if not modeled_clusters:
            self.logger.error('No clusters found matching cluster filter '
                              '"{0}"'.format(cluster_name))
            raise SystemExit(ExitCodes.VCS_CLUSTER_NOT_FOUND)

        filtered_clusters = self._filter_action_groups(system_filter,
                                                       modeled_clusters)

        action_groups = []
        mco_cached_data = {}
        for cname, csystems in filtered_clusters.items():
            if csystems[0] not in mco_cached_data:
                _, cluster_groups = get_group_info(mco_host=csystems[0])
                mco_cached_data[csystems[0]] = cluster_groups
            else:
                cluster_groups = mco_cached_data[csystems[0]]
            # csystems does not contain a list of regex but a list of hostnames
            # For that reason we need to add the regex filter back in
            # search_for_groups
            # Otherwise we could face a situation in which the opration
            # should be run in svc1 and ends up running in svc1 AND svc10
            csystems = self._add_regex_filter(csystems)
            found_matches = self._search_for_groups(cname, group_name_filter,
                                                    csystems, modeled_groups,
                                                    cluster_groups)
            action_groups.extend(found_matches)
        if not action_groups:
            self.logger.error('No live groups found matching any filter(s)!')
            raise SystemExit(ExitCodes.VCS_GROUP_NOT_FOUND)
        return action_groups

    @staticmethod
    def _add_regex_filter(string_list):
        """
        adds begin and end delimiters to each string in the list if required
        :param string_list: List of strings that need adding regex delimiters
        :returns: List of strings with regex delimiters
        """
        ret = []
        for regex_style_string in string_list:
            if not regex_style_string.startswith('^'):
                regex_style_string = '^' + regex_style_string
            if not regex_style_string.endswith('$'):
                regex_style_string = regex_style_string + '$'
            ret.append(regex_style_string)
        return ret

    @staticmethod
    def _get_action_systems(system_filter):
        """
        Get a list of VCS systems
        :param system_filter: Limit systems to those that match this regex
        :returns: List of VCS systems across all modeled clusters
        """
        modeled_clusters = Vcs._get_modeled_clusters()
        system_list = []
        for systems in modeled_clusters.values():
            for system in systems:
                if match_filter(system_filter, system):
                    system_list.append(system)
        return system_list

    def wait_vcs_state(self, group_name, group_system, state, wait_timeout):
        """
        Wait for a VCS groups to change state

        :param group_name: The VCS group
        :type group_name: str
        :param group_system:  The system to wait for the state change on
        :type group_system: str
        :param state: The state to wait for
        :type state: str
        :param wait_timeout: Timeout to wait before raising an error
        :type wait_timeout: int|str

        :returns: If the state changes within the timeout then (True, None)
        otherwise (False, The Error)

        :rtype: tuple
        """
        # noinspection PyBroadException
        try:
            litp_agent = VcsCmdApiAgent()
            self.logger.info(
                    'Waiting for {group} to go {state} on {system} '
                    '(timeout={timeout})'.format(group=group_name,
                                                 state=state,
                                                 system=group_system,
                                                 timeout=wait_timeout))
            start_time = datetime.now().replace(microsecond=0)
            try:
                litp_agent.hagrp_wait(group_name, group_system, state,
                                      timeout=wait_timeout)
            except McoAgentException as error:
                if VcsCodes.is_error(VcsCodes.V_16_1_10805, error):
                    return False, 'Timedout waiting for {0} to go ' \
                                  '{1}'.format(group_name, state)
                else:
                    return False, str(error)
            total_time = datetime.now().replace(microsecond=0) - start_time
            _, remainder = divmod(total_time.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.logger.info(
                    'Group {group} now {state} on {system} '
                    '({taken})'.format(group=group_name,
                                       state=state,
                                       system=group_system,
                                       taken='{0}m:{1}s'.format(minutes,
                                                                seconds)))

            return True, None
        except Exception:  # pylint: disable=broad-except
            return False, traceback.format_exc()

    @staticmethod
    def filter_activestandby(all_groups, check_group):
        """
        Check if ``all_groups`` already contains an entry for an
        active-standby group.

        :param all_groups: List of groups to check
        :type all_groups: list
        :param check_group: The group to check for
        :type check_group: dict
        :returns: ``True`` is there's already a group entry (but for another
        system), ``False`` otherwise

        :rtype: bool
        """
        _name = check_group[Vcs.H_NAME]
        _system = check_group[Vcs.H_SYSTEM]
        group_type = check_group[Vcs.H_TYPE]
        check_state = VCS_GRP_SVS_STATE_ONLINE
        if group_type == VCS_AVAIL_ACTIVE_STANDBY:
            other_side = None
            for _gp in all_groups:
                _group_name = _gp[Vcs.H_NAME]
                _group_system = _gp[Vcs.H_SYSTEM]
                if _group_name == _name and _group_system != _system:
                    other_side = _gp
                    break
            if other_side:
                return other_side[Vcs.H_SYSTEM_STATE] == [check_state]
            else:
                return False
        else:
            return False

    def online_services(self, autoclear,  # pylint: disable=R0913,R0914
                        cluster_filter, enminst_agent, thread_pool,
                        thread_results, timeout, to_online, wait_tasks):
        """
        functionality to online group/individual service groups
        :param autoclear: If ``True`` clear FAULTED groups. If ``False`` a
        warning is logged and the group skipped.

        :type wait_tasks: list
        :param wait_tasks: list appended to contain service(s) info
        :param cluster_filter: Regex to filter clusters
        :type cluster_filter: str
        :param timeout: Override the modeled online wait timeout for the
        groups

        :type timeout: int|str
        :param to_online: list of service groups to online
        :param thread_pool: Thread pool being used to execute tasks
        :param thread_results: tuble to insert thread results into for
        later usage.

        :param enminst_agent: The EnmInst MCO agent class.
        """
        for group in to_online:
            group_name = group[Vcs.H_NAME]
            group_system = group[Vcs.H_SYSTEM]
            needs_clear = False
            for state in group[Vcs.H_SYSTEM_STATE]:
                if state in VcsStates.VCS_CLEAR_STATES:
                    needs_clear = True
            if needs_clear:
                if autoclear:
                    self.logger.info('Clearing {0} on '
                                     '{1}'.format(group_name,
                                                  group_system))
                    enminst_agent.hagrp_clear(group_name, group_system)
                else:
                    msg = 'Group {0} on system {1} needs to be cleared, ' \
                          'state ' \
                          '|{2}|'.format(group_name, group_system,
                                         ','.join(
                                                 group[Vcs.H_SYSTEM_STATE]))
                    thread_results.append((False, msg))
                    continue
            if int(timeout) != -1:
                online_timeout = timeout
            else:
                online_timeout = group[Vcs.H_ONLINE_TIMEOUT]
                online_timeout = int(online_timeout) * int(
                        group[Vcs.H_ONLINE_RETRY])
            enminst_agent = EnminstAgent()
            self.logger.info('Onlining {0} on {1}'.format(group_name,
                                                          group_system))
            try:
                propagate = group[Vcs.H_DEPS] != []
                enminst_agent.hagrp_online(group_name, group_system,
                                           propagate=propagate)
            except McoAgentException as error:
                if VcsCodes.is_error(VcsCodes.V_16_1_40229, error):
                    self.warning(
                            '{0} is already online in cluster.'.format(
                                    group_name))
                    continue
                raise
            wait_tasks.append((group_name,
                               group_system,
                               group[Vcs.H_TYPE],
                               online_timeout,
                               cluster_filter,))

        def report(result):
            """
            Append thread result to buffer
            :param result: Thread result tuple
            :return:
            """
            thread_results.append(result)

        for wtaskinfo in wait_tasks:
            thread_pool.apply_async(self.online_wait, args=wtaskinfo,
                                    callback=report)

    @staticmethod
    def _vcs_list_to_map(vcs_group_list):
        """
        Convert a list of VCS groups to a map. The key is the group name and
        values are the groups' data
        :param vcs_group_list: Result of _get_action_groups()
        :rtype: dict
        """
        group_map = {}
        for _group in vcs_group_list:
            group_name = _group[Vcs.H_NAME]
            if group_name not in group_map:
                group_map[group_name] = {
                    Vcs.H_TYPE: _group[Vcs.H_TYPE],
                    'systems': {}
                }
            group_system = _group[Vcs.H_SYSTEM]
            if group_system not in group_map[group_name]['systems']:
                group_map[group_name]['systems'][group_system] = _group
        return group_map

    @staticmethod
    def _filter_group_map(group_map, system_filter):
        """
        Remove groups that are not on a system matching the system filter
        Also handles the active-standby case of a group being online on
        another system
        :param group_map: Group map (result of _vcs_list_to_map)
        :param system_filter: System name regex
        :return:
        """
        groups_to_online = []
        for group_name in group_map.keys():
            group_info = group_map[group_name]
            group_ha_type = group_info[Vcs.H_TYPE]
            if group_ha_type == VCS_AVAIL_ACTIVE_STANDBY:
                # Remove any active-standby groups that have one
                # side already online
                instance_online = False
                offline_sys_group = None
                for group_system, group_data in group_info['systems'].items():
                    sys_state = group_data[Vcs.H_SYSTEM_STATE]
                    if sys_state == [VCS_GRP_SVS_STATE_ONLINE]:
                        instance_online = True
                    elif match_filter(system_filter, group_system):
                        offline_sys_group = group_data
                if not instance_online and offline_sys_group:
                    groups_to_online.append(offline_sys_group)
            else:
                # Go through other types (parallel/standalone) and get
                # the group on the system matching the filter passed in
                for group_system in group_info['systems'].keys():
                    if match_filter(system_filter, group_system):
                        group_data = group_info['systems'][group_system]
                        g_state = group_data[Vcs.H_SYSTEM_STATE]
                        if g_state != [VcsStates.ONLINE]:
                            groups_to_online.append(group_data)
        return groups_to_online

    def hagrp_online(self, group_name_filter,  # pylint: disable=R0913,R0914
                     system_filter, cluster_filter, timeout, autoclear=False):
        """
        Online VCS groups and wait for them to go ONLINE.

        :param group_name_filter: Regex to filter group names
        :type group_name_filter: str
        :param system_filter: Regex to filter systems
        :type system_filter: str
        :param cluster_filter: Regex to filter clusters
        :type cluster_filter: str
        :param timeout: Override the modeled online wait timeout for the
        groups
        :type timeout: int|str

        :param autoclear: If ``True`` clear FAULTED groups. If ``False`` a
        warning is logged and the group skipped.

        :return:
        """
        if not cluster_filter:
            cluster_filter = re.search(r'Grp_CS.(.*?)_cluster', \
                                        group_name_filter).group(1)
        all_groups = self._get_action_groups(group_name_filter,
                                             None,
                                             cluster_filter)
        # rearrange the all_groups to make filtering easier
        group_map = self._vcs_list_to_map(all_groups)

        groups_to_online = self._filter_group_map(group_map, system_filter)

        if not groups_to_online:
            self.logger.info('Found no groups to online '
                             '(either filters are too restrictive or target '
                             'groups are already '
                             '{0}).'.format(VcsStates.ONLINE))
            return

        enminst_agent = EnminstAgent()
        wait_tasks = []
        thread_results = []

        self.logger.info('Onlining {0} group(s)'.format(len(groups_to_online)))
        thread_pool = ThreadPool(processes=cpu_count() * 3)
        try:
            self.online_services(autoclear, cluster_filter, enminst_agent,
                                 thread_pool, thread_results, timeout,
                                 groups_to_online, wait_tasks)
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise
        thread_pool.close()
        thread_pool.join()
        all_ok = True
        for success, exception in thread_results:
            if not success:
                all_ok = False
                self.logger.error('{0}'.format(exception))
        if not all_ok:
            raise SystemExit(ExitCodes.VCS_INVALID_STATE)

    def online_wait(self, group_name, group_system,  # pylint: disable=R0913
                    group_type, online_timeout, cluster_filter):
        """
        Wait for a group to go to the ONLINE state
        :param group_name: The VCS group name
        :param group_system: The VCS system the group is onlining on
        :param group_type: The group availability type
        :param online_timeout: Max time to wait for the group to online
        :param cluster_filter: Limit searched to a particular cluster
        :return:
        """
        try:
            return self.wait_vcs_state(group_name, group_system,
                                       VcsStates.ONLINE,
                                       online_timeout)
        except McoAgentException as error:
            # lazy checks:
            #   - active-standby, there's already a process ONLINING
            #       on another system: V_16_1_40156
            if VcsCodes.is_error(VcsCodes.V_16_1_40156, error):
                if group_type == VCS_AVAIL_ACTIVE_STANDBY:
                    gp_info = self._get_action_groups(group_name, None,
                                                      cluster_filter)
                    for group in gp_info:
                        if group[Vcs.H_SYSTEM] != group_system:
                            self.logger.warning(
                                    'Group {0} is already online on {1}.'
                                    ''.format(group_name,
                                              group[Vcs.H_SYSTEM]))
                            return True, None
            return False, str(error)

    def hagrp_offline(self, group_name_filter,  # pylint: disable=R0914
                      system_filter, cluster_filter, timeout):
        """
        Offline VCS groups and wait for them to go ONLINE.

        :param group_name_filter: Regex to filter group names
        :type group_name_filter: str
        :param system_filter: Regex to filter systems
        :type system_filter: str
        :param cluster_filter: Regex to filter clusters
        :type cluster_filter: str
        :param timeout: Override the modeled offline wait timeout for the
        groups
        :type timeout: int|str

        :return:
        """
        to_offline = self._get_action_groups(group_name_filter,
                                             system_filter,
                                             cluster_filter)

        to_offline[:] = [gp for gp in to_offline if
                         gp[Vcs.H_SYSTEM_STATE] != [VcsStates.OFFLINE]]
        if not to_offline:
            self.logger.info('Found no groups to offline '
                             '(either filters are too restrictive or target '
                             'groups are already '
                             '{0}).'.format(VcsStates.OFFLINE))
            return

        self.logger.info('Offlining {0} group(s)'.format(len(to_offline)))
        enminst_agent = EnminstAgent()
        wait_tasks = []
        thread_pool = ThreadPool(processes=cpu_count() * 3)
        thread_results = []
        try:
            for group in to_offline:
                if timeout != -1:
                    offline_timeout = timeout
                else:
                    offline_timeout = group[Vcs.H_OFFLINE_TIMEOUT]
                    offline_timeout = int(offline_timeout) * int(
                            group[Vcs.H_OFFLINE_RETRY])

                group_name = group[Vcs.H_NAME]
                group_system = group[Vcs.H_SYSTEM]
                self.logger.info('Offlining {0} on {1}'.format(group_name,
                                                               group_system))
                enminst_agent.hagrp_offline(group_name, group_system)
                wait_tasks.append((group_name, group_system, VcsStates.OFFLINE,
                                   offline_timeout,))

            def report(result):
                """
                Append thread result to buffer
                :param result: Thread result tuple
                :return:
                """
                thread_results.append(result)

            for wtaskinfo in wait_tasks:
                thread_pool.apply_async(self.wait_vcs_state, args=wtaskinfo,
                                        callback=report)
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise
        thread_pool.close()
        thread_pool.join()
        all_ok = True

        for success, exception in thread_results:
            if not success:
                all_ok = False
                self.logger.error('{0}'.format(exception))
        if not all_ok:
            raise SystemExit(ExitCodes.VCS_INVALID_STATE)

    def hagrp_switch(self, group_name_filter,  # pylint: disable=R0912,R0914
                     system_filter, cluster_filter, timeout):
        """
        Switch service groups
        :param group_name_filter: filter names
        :param system_filter: filter systems
        :param cluster_filter: Limit results to clusters matching this regex.
        :type cluster_filter: str || None
        :param timeout: timeout
        :return:
        """
        to_switch = self._get_action_groups(group_name_filter,
                                            system_filter,
                                            cluster_filter)
        if not to_switch:
            self.logger.info('Found no groups to switch '
                             '(either filters are too restrictive or target '
                             'groups are all '
                             '{0}).'.format(VcsStates.OFFLINE))
            return

        switch_info = {}
        for group in to_switch:
            # Can only switch active-standby groups
            if group[Vcs.H_TYPE] != VCS_AVAIL_ACTIVE_STANDBY:
                continue
            group_name = group[Vcs.H_NAME]
            if group[Vcs.H_SYSTEM_STATE] == [VcsStates.OFFLINE]:
                if group_name in switch_info:
                    # Already have an offline entry, both instance are
                    # offline, cant switch
                    self.logger.info('Cannot switch {0} not active anywhere '
                                     'in cluster'.format(group_name))
                    del switch_info[group_name]
                else:
                    # This side is offline, use this as the -to value
                    switch_info[group_name] = group
        if not switch_info:
            self.logger.info('Found no groups to switch '
                             '(either filters are too restrictive or no {0} '
                             'groups available to switch.)'
                             ''.format(VCS_AVAIL_ACTIVE_STANDBY))
            return

        agent = EnminstAgent()
        thread_pool = ThreadPool(processes=cpu_count() * 3)
        thread_results = []

        def report(result):
            """
            Add thread results to the result list
            :param result: Thread result
            :return:
            """
            thread_results.append(result)

        self.logger.info('Switching {0} group(s)'.format(len(switch_info)))
        try:
            for group_name, target in switch_info.items():
                target_system = target[Vcs.H_SYSTEM]
                msg = 'Switching {0} to {1}'.format(group_name, target_system)
                self.logger.info(msg)
                try:
                    agent.hagrp_switch(group_name, target_system,
                                       target_system)
                except McoAgentException as error:
                    report((False, str(error)))
                    continue

                if timeout != -1:
                    switch_timeout = timeout
                else:
                    switch_timeout = int(target[Vcs.H_OFFLINE_TIMEOUT]) * int(
                            target[Vcs.H_OFFLINE_RETRY])
                    switch_timeout += int(target[Vcs.H_ONLINE_TIMEOUT]) * int(
                            target[Vcs.H_ONLINE_RETRY])

                thread_pool.apply_async(self.wait_vcs_state,
                                        args=(group_name,
                                              target_system,
                                              VcsStates.ONLINE,
                                              switch_timeout,),
                                        callback=report)
        except KeyboardInterrupt:
            thread_pool.terminate()
            raise
        thread_pool.close()
        thread_pool.join()
        all_ok = True

        for success, exception in thread_results:
            if not success:
                all_ok = False
                self.logger.error('{0}'.format(exception))
        if not all_ok:
            raise SystemExit(ExitCodes.VCS_INVALID_STATE)

    def _freeze_unfreeze_group(self,  # pylint: disable=R0913,R0914
                               group_filter, persistent, action_type, warnings,
                               system_filter=None):
        """
        Freeze/Unfreeze a VCS group

        :param group_filter: The group to (un)freeze.
        :param persistent: Should the (un)freeze be persistent or not
        :param action_type: One of ``freeze`` or ``unfreeze``
        :param warnings: List of VCS errors to show as warnings rather than
        errors.

        :param system_filter: The VCS system to make the (un)freeze call on.
        """
        if action_type == 'freeze':
            cap_action = 'Freezing'
            cap_action_comp = 'Froze'
        else:
            cap_action = 'Unfreezing'
            cap_action_comp = 'Unfroze'

        if not group_filter:
            raise VcsException('No group name/filter passed!')

        groups_list = self._get_action_groups(group_filter, system_filter,
                                              None)
        completed_groups = []
        for group in groups_list:
            group_name = group[Vcs.H_NAME]
            if group_name in completed_groups:
                continue
            group_system = group[Vcs.H_SYSTEM]
            agent = EnminstAgent()
            try:
                self.info('{0} {1}'.format(cap_action, group_name))
                if action_type == 'freeze':
                    agent.hagrp_freeze(group_name, group_system,
                                       persistent=persistent)
                else:
                    agent.hagrp_unfreeze(group_name, group_system,
                                         persistent=persistent)
                self.info('{0} {1}'.format(cap_action_comp, group_name))
                completed_groups.append(group_name)
            except McoAgentException as error:
                warning_only = False
                for checktype in warnings:
                    if VcsCodes.is_error(checktype, error):
                        self.warning(
                                checktype[VcsCodes.KEY_DESCRIPTION])
                        warning_only = True
                        break
                if not warning_only:
                    self.exception('Could not {0} {1}'.format(action_type,
                                                              group_name))
                    raise
                else:
                    completed_groups.append(group_name)

    def freeze_group(self, group_name, persistent, group_system=None):
        """
        Freeze a VCS group.

        :param group_name: The group to freeze
        :type group_name: str
        :param persistent: Should the freeze be maintained after a system
        is rebooted.

        :type persistent: bool
        :param group_system: A system the group in assigned to.
        :type group_system: str

        """
        warnings = [VcsCodes.V_16_1_40200, VcsCodes.V_16_1_40208,
                    VcsCodes.V_16_1_40209]
        self._freeze_unfreeze_group(group_name, persistent, 'freeze',
                                    warnings, system_filter=group_system)

    def unfreeze_group(self, group_name, persistent, group_system=None):
        """
        Unfreeze a VCS group.

        :param group_name: The group to unfreeze
        :type group_name: str
        :param group_system: A system the group is assigned to.
        :type group_system: str
        :param persistent: Should the unfreeze be maintained after a
        system is rebooted.

        :type persistent: bool

        """
        warnings = [VcsCodes.V_16_1_40201, VcsCodes.V_16_1_40202]
        self._freeze_unfreeze_group(group_name, persistent, 'unfreeze',
                                    warnings, system_filter=group_system)

    def freeze_system(self, system_filter, persistent, evacuate=False):
        """
        Freeze a VCS system.

        :param system_filter: The system to freeze
        :type system_filter: str
        :param persistent: Should the freeze be maintained after a system
        is rebooted.
        :param evacuate: If the system should be evacuated
        :type persistent: bool

        """
        systems_list = self._get_action_systems(system_filter)
        agent = EnminstAgent()
        for system_name in systems_list:
            try:
                self.logger.info('Freezing system {0}'.format(system_name))
                agent.hasys_freeze(system_name, persistent, evacuate)
                self.logger.info('Froze {0}'.format(system_name))
            except McoAgentException as error:
                warnings = [VcsCodes.V_16_1_40206, VcsCodes.V_16_1_40207]
                for checktype in warnings:
                    if VcsCodes.is_error(checktype, error):
                        self.logger.warning(
                                checktype[VcsCodes.KEY_DESCRIPTION])
                        return
                self.logger.exception('Could not unfreeze {0}'
                                      .format(system_name))
                raise

    def unfreeze_system(self, system_filter, persistent):
        """
        Unfreeze a VCS system.

        :param system_filter: The system to unfreeze
        :type system_filter: str
        :param persistent: Should the unfreeze be maintained after a system
        is rebooted.

        :type persistent: bool

        """
        systems_list = self._get_action_systems(system_filter)
        agent = EnminstAgent()
        for system_name in systems_list:
            try:
                self.logger.info('Unfreezing system {0}'.format(system_name))
                agent.hasys_unfreeze(system_name, persistent)
                self.logger.info('Unfroze {0}'.format(system_name))
            except McoAgentException as error:
                warnings = [VcsCodes.V_16_1_40204, VcsCodes.V_16_1_40205]
                for checktype in warnings:
                    if VcsCodes.is_error(checktype, error):
                        self.logger.warning(
                                checktype[VcsCodes.KEY_DESCRIPTION])
                        return
                self.logger.exception('Could not unfreeze {0}'
                                      .format(system_name))
                raise

    @staticmethod
    def is_system_frozen(system_name, system_states):
        """
        Check is a system is frozen (temp/perm)
        :param system_name: The VCS system name
        :param system_states: The VCS system states (get_cluster_system_status)
        :returns: `True` is frozen, `False` otherwise
        """
        for sys_state in system_states:
            if system_name == sys_state[Vcs.H_SYSTEM]:
                return sys_state[Vcs.H_FROZEN] != '-'
        return False

    def lock(self, vcs_system, switch_timeout):
        """
        LITP lock a node.

        :param vcs_system: The node to lock
        :type vcs_system: str
        :param switch_timeout: The time to wait for the failover groups
        to offline during switch
        :type switch_timeout: int
        """
        unfiltered_names = Vcs._get_action_systems(vcs_system)
        if not unfiltered_names:
            raise VcsException(
                    'Could not find a VCS system matching "{0}"'.format(
                            vcs_system))

        if switch_timeout == -1:
            vcs_groups, _ = Vcs.get_cluster_group_status(
                    system_filter=vcs_system, verbose=False)
            lock_switch_timeout = 0
            for vcsgroup in vcs_groups:
                if vcsgroup[Vcs.H_TYPE] == VCS_AVAIL_ACTIVE_STANDBY:
                    if match_filter(vcs_system, vcsgroup[Vcs.H_SYSTEM]):
                        if switch_timeout == -1:
                            timeouts = Vcs._get_modeled_group_timeouts(
                                    vcsgroup[Vcs.H_CLUSTER],
                                    Vcs._to_model_name(
                                            vcsgroup[Vcs.H_CLUSTER],
                                            vcsgroup[Vcs.H_GROUP]))
                            lock_switch_timeout += int(
                                    timeouts[Vcs.H_OFFLINE_TIMEOUT])
        else:
            lock_switch_timeout = switch_timeout
        agent = VcsCmdApiAgent()
        _, system_states = Vcs.get_cluster_system_status()

        exit_error = False
        for system_name in unfiltered_names:
            # Check to see if the system is frozen, it if is then it
            # cant be locked
            if Vcs.is_system_frozen(system_name, system_states):
                self.logger.error(
                        'Cant lock {0} as it is frozen!'.format(system_name))
                exit_error = True
            else:
                self.logger.info('Locking {0}'.format(system_name))
                agent.lock(system_name, lock_switch_timeout)
                self.logger.info('System {0} locking.'.format(system_name))
        if exit_error:
            raise SystemExit(ExitCodes.VCS_SYSTEM_FROZEN)

    def unlock(self, vcs_system, nic_wait_timeout):
        """
        LITP unlock a node.

        :param vcs_system: The node to unlock
        :type vcs_system: str
        :param nic_wait_timeout: The time to wait for the NICs to be up
        :type nic_wait_timeout: int
        """
        # vcs_system can be a regex
        unfiltered_names = Vcs._get_action_systems(vcs_system)
        if not unfiltered_names:
            raise VcsException(
                    'Could not find a VCS system matching "{0}"'.format(
                            vcs_system))
        agent = VcsCmdApiAgent()
        if nic_wait_timeout == -1:
            nic_wait_timeout = 300
        for system_name in unfiltered_names:
            self.logger.info('Unlocking {0}'.format(system_name))
            agent.unlock(system_name, nic_wait_timeout)
            self.logger.info('System {0} unlocking.'.format(system_name))

    @staticmethod
    def node_name_to_vcs_system(node_name):
        """
        Map node name into VCS system name.

        :param node_name: The node name (e.g. "db-1")
        :type node_name: str
        :returns: vcs_system: The VCS system name (e.g. "ieatlms4891-1")
        :rtype vcs_system: str
        """
        _, node_name_to_vcs_system = Vcs._get_hostname_vcs_aliases()
        return node_name_to_vcs_system[node_name]

    def neo4j_set_state(self):
        '''
          Offline Neo4j SG if DPS still using Versant
          Online Neo4j SG if DPS switched to Neo4j
        '''
        neo4j_cluster_information = self.get_neo4j_cluster_information()

        if not neo4j_cluster_information[0]:
            self.logger.info("Neo4j SG not installed")
            return

        if is_dps_using_neo4j():
            self.logger.info("DPS is using neo4j, online it.")
            self.neo4j_unfreeze_online(neo4j_cluster_information)
            return
        else:
            self.logger.info("DPS NOT using neo4j. Neo4j going offline")
            self.neo4j_offline_freeze(neo4j_cluster_information)

    def get_neo4j_cluster_information(self):
        '''
        Gets Neo4j cluster info
        '''
        neo4j_cluster_information = self.get_cluster_group_status(
            Vcs.ENM_DB_CLUSTER_NAME,
            '.*neo4j_clustered_service',
            verbose=False)
        self.logger.info("get_neo4j_cluster_information called")
        neo4j_cluster_information = neo4j_cluster_information[:-1]

        return neo4j_cluster_information

    def neo4j_offline_freeze(self, neo4j_cluster_information):
        '''
        Offline Neo4j SG first and then persistently freeze it.
        This is needed if Versant database still in use by DPS.
        '''
        agent = EnminstAgent()
        for systems in neo4j_cluster_information:
            for neo4j in systems:
                if neo4j['ServiceState'] == VCS_GRP_SVS_STATE_ONLINE:
                    self.hagrp_offline(neo4j['Group'],
                                      neo4j['System'],
                                      neo4j['Cluster'],
                                      720)
                else:
                    self.logger.info('{0} is not {1} on {2} '.format(
                        neo4j['Group'], VCS_GRP_SVS_STATE_ONLINE,
                        neo4j['System']))
        if neo4j_cluster_information[0][0]['Frozen'] == Vcs.STATE_UNFROZEN:
            agent.hagrp_freeze(neo4j_cluster_information[0][0]['Group'],
                               neo4j_cluster_information[0][0]['System'],
                               persistent=True)
        else:
            self.logger.info('{0} found is already frozen'.format(
                neo4j_cluster_information[0][0]['Group']))

    def neo4j_unfreeze_online(self, neo4j_cluster_information):
        '''
        Persistently unfreeze Neo4j SG and online it.
        This is needed if Neo4j getting in use after data
        migration from Versant
        '''
        agent = EnminstAgent()
        if (neo4j_cluster_information[0][0]['Frozen'] == Vcs.STATE_FROZEN_TEMP
            or neo4j_cluster_information[0][0][
                        'Frozen'] == Vcs.STATE_FROZEN_PERM):
            agent.hagrp_unfreeze(neo4j_cluster_information[0][0]['Group'],
                                 neo4j_cluster_information[0][0]['System'],
                                 persistent=True)
        else:
            self.logger.info('{0}  found is not frozen'.format(
                neo4j_cluster_information[0][0]['Group']))
        for systems in neo4j_cluster_information:
            for neo4j in systems:
                if neo4j['ServiceState'] == VCS_GRP_SVS_STATE_OFFLINE:
                    self.hagrp_online(neo4j['Group'],
                                    '',
                                     neo4j['Cluster'],
                                     -1)
                else:
                    self.logger.info('{0} is not {1} on {2} '.format(
                        neo4j['Group'], VCS_GRP_SVS_STATE_OFFLINE,
                        neo4j['System']))


def create_arg_parser():
    """
    Create stdin argument parser
    :returns: Instance of an ArgumentParser
    :type: ArgumentParser
    """
    arg_parser = ArgumentParser(description='VCS HealthChecks.')

    main_options = arg_parser.add_mutually_exclusive_group(required=True)
    main_options.add_argument('--groups', action='store_true',
                              help='Display and check cluster(s) groups '
                                   'status.')
    main_options.add_argument('--systems', action='store_true',
                              help='Display and check cluster(s) system '
                                   'status.')
    main_options.add_argument('--online', action='store_true',
                              help='Online a VCS group')
    main_options.add_argument('--clear', action='store_true',
                              help='Clear a VCS group\'s faulted state')
    main_options.add_argument('--offline', action='store_true',
                              help='Offline a VCS group')
    main_options.add_argument('--restart', action='store_true',
                              help='Restart a VCS group')
    main_options.add_argument('--switch', action='store_true',
                              help='Switch VCS group')
    main_options.add_argument('--history', action='store_true',
                              help='Display event history.')
    main_options.add_argument('--unfreeze', action='store_true',
                              help='Unfreeze a service group or system '
                                   '(reenables onlining, offlining, and '
                                   'failover).', )
    main_options.add_argument('--freeze', action='store_true',
                              help='Freeze a service group or system (disable '
                                   'onlining, offlining, and failover)')
    main_options.add_argument('--unlock', action='store_true',
                              help='Unlock a LITP locked node. This will '
                                   'persistently unfreeze the node and ONLINE'
                                   ' groups that are assigned to the system.')
    main_options.add_argument('--lock', action='store_true',
                              help='Lock a node. This will evacuate all groups'
                                   ' on the node and then freeze the node'
                                   ' persistently.')

    report_flags = arg_parser.add_argument_group(
            'Report Options',
            description='Options that can be used to format report outputs.'
                        ' (--groups, --systems)')
    report_flags.add_argument('--sort', dest='sort_keys',
                              metavar='columns',
                              help='Sort the output data by a column')
    report_flags.add_argument('--csv', dest='csv',
                              metavar='output_file',
                              help='Write table data to csv file.')
    report_flags.add_argument('--uptime', dest='uptime', action='store_true',
                              help='Include uptimes if possible.'
                                   ' (--groups only)')

    history_flags = arg_parser.add_argument_group(
            'History Options',
            description='Options that can be used to format history'
                        '(--history) output. '
                        'The only general options that will format output'
                        ' are (-g <group>, -c <cluster>)')
    history_flags.add_argument('--by-date', action='store_true',
                               help='Sort history by date, not group.')

    flags = arg_parser.add_argument_group('General Options')
    flags.add_argument('-g', dest='vcs_group',
                       help='The VCS group to limit checks to.')
    flags.add_argument('-c', dest='vcs_cluster',
                       help='The VCS cluster to limit checks to.')
    flags.add_argument('-s', dest='vcs_system',
                       help='The VCS system to limit checks to.')
    flags.add_argument('-t', dest='avail_type',
                       help='The VCS group types to limit checks to.')
    flags.add_argument('-a', dest='system_state',
                       help='The VCS system states to limit display'
                            ' results to.')
    flags.add_argument('-b', dest='group_state',
                       help='The VCS group states to limit display'
                            ' results to.')
    flags.add_argument('-f', dest='auto_clear',
                       default=False, action='store_true',
                       help='Clear FAULTED groups automatically '
                            'when (re)starting')
    flags.add_argument('-m', dest='timout',
                       help='Operation timeout (seconds)',
                       default=-1,
                       type=int)
    flags.add_argument('-p', dest='persistent', default=False,
                       action='store_true',
                       help='Make VCS changes persistent.')
    flags.add_argument('-I', dest='include_host')

    flags.add_argument('-vt', dest='view_type', choices=['v', 'm', 'x'],
                       default='v',
                       help='How the resources are displayed. If \'v\' then '
                            'the VCS names are used, if \'m\' then the '
                            'LITP model names are used, \'x\' both VCS and '
                            'modeled names are displayed (separated by a '
                            'forward slash).')
    return arg_parser


def check_usage(args):
    """
    Check input arguments for usage errors.
    :param args: Input arguments from cli
    :return:
    """
    arg_parser = create_arg_parser()
    if len(args) == 0:
        arg_parser.print_help()
        raise SystemExit(ExitCodes.INVALID_USAGE)

    prog_options = arg_parser.parse_args(args)

    if prog_options.by_date and not prog_options.history:
        arg_parser.error("--by-date can only be used with --history")
        raise SystemExit(ExitCodes.INVALID_USAGE)

    if prog_options.vcs_group:
        prog_options.vcs_group = '^{0}$'.format(prog_options.vcs_group)
    if prog_options.vcs_cluster:
        prog_options.vcs_cluster = '^{0}$'.format(prog_options.vcs_cluster)
    if prog_options.vcs_system:
        prog_options.vcs_system = '^{0}$'.format(prog_options.vcs_system)
    return prog_options, arg_parser


def main(args):  # pylint: disable=too-many-statements,too-many-branches
    """
    Handle sys.argv & usages
    :param args: sys.argv
    :type args: list

    """
    prog_options, arg_parser = check_usage(args)

    vcs = Vcs()
    if prog_options.groups:
        vcs.verify_cluster_group_status(
                cluster_filter=prog_options.vcs_cluster,
                group_filter=prog_options.vcs_group,
                group_type=prog_options.avail_type,
                system_filter=prog_options.vcs_system,
                groupstate_filter=prog_options.group_state,
                systemstate_filter=prog_options.system_state,
                sort_keys=prog_options.sort_keys,
                csvfile=prog_options.csv,
                show_uptime=prog_options.uptime,
                view_type=prog_options.view_type)
    elif prog_options.systems:
        vcs.verify_cluster_system_status(
                cluster_filter=prog_options.vcs_cluster,
                systemstate_filter=prog_options.system_state,
                sort_keys=prog_options.sort_keys,
                csvfile=prog_options.csv,
                view_type=prog_options.view_type,
                verbose=True)
    elif prog_options.unfreeze:
        if prog_options.vcs_group:
            act_system = prog_options.include_host or prog_options.vcs_system
            vcs.unfreeze_group(prog_options.vcs_group,
                               group_system=act_system,
                               persistent=prog_options.persistent)
        elif prog_options.vcs_system:
            vcs.unfreeze_system(prog_options.vcs_system,
                                persistent=prog_options.persistent)
        else:
            arg_parser.error('No group or system to unfreeze '
                             '(-g or -s option)!')
    elif prog_options.freeze:
        if prog_options.vcs_group:
            act_system = prog_options.include_host or prog_options.vcs_system
            vcs.freeze_group(prog_options.vcs_group,
                             group_system=act_system,
                             persistent=prog_options.persistent)
        elif prog_options.vcs_system:
            vcs.freeze_system(prog_options.vcs_system,
                              persistent=prog_options.persistent)
        else:
            arg_parser.error('No group or system to freeze'
                             '(-g or -s option)!')
    elif prog_options.lock:
        if not prog_options.vcs_system:
            arg_parser.error('No system to lock (-s option)!')
        vcs.lock(prog_options.vcs_system, prog_options.timout)
    elif prog_options.unlock:
        if not prog_options.vcs_system:
            arg_parser.error('No system to unlock (-s option)!')
        vcs.unlock(prog_options.vcs_system, prog_options.timout)
    elif prog_options.history:
        args_ok = prog_options.vcs_system is None
        args_ok = args_ok and prog_options.avail_type is None
        args_ok = args_ok and prog_options.system_state is None
        args_ok = args_ok and prog_options.group_state is None
        args_ok = args_ok and not prog_options.auto_clear
        args_ok = args_ok and prog_options.timout is -1
        args_ok = args_ok and not prog_options.persistent
        args_ok = args_ok and prog_options.include_host is None
        args_ok = args_ok and prog_options.view_type is 'v'
        if not args_ok:
            arg_parser.error('For history, the only general options that'
                             ' will format output are'
                             ' (-g <group>, -c <cluster>)')

        vcs.show_history(
            cluster_filter=prog_options.vcs_cluster,
            group_filter=prog_options.vcs_group or 'Grp_CS_.*',
            sort_by_date=prog_options.by_date)
    elif prog_options.online:
        if not prog_options.vcs_group and not prog_options.vcs_system and \
                not prog_options.vcs_cluster:
            arg_parser.error('Need a Cluster, System or Group to online!')
        vcs.hagrp_online(prog_options.vcs_group,
                         prog_options.vcs_system,
                         prog_options.vcs_cluster,
                         prog_options.timout,
                         prog_options.auto_clear)

    elif prog_options.offline:
        if not prog_options.vcs_group and not prog_options.vcs_system and \
                not prog_options.vcs_cluster:
            arg_parser.error('Need a Cluster, System or Group to offline!')
        vcs.hagrp_offline(prog_options.vcs_group,
                          prog_options.vcs_system,
                          prog_options.vcs_cluster,
                          prog_options.timout)

    elif prog_options.restart:
        if not prog_options.vcs_group and not prog_options.vcs_system and \
                not prog_options.vcs_cluster:
            arg_parser.error('Need a Cluster, System or Group to restart!')
        vcs.hagrp_offline(prog_options.vcs_group,
                          prog_options.vcs_system,
                          prog_options.vcs_cluster,
                          prog_options.timout)
        vcs.hagrp_online(prog_options.vcs_group,
                         prog_options.vcs_system,
                         prog_options.vcs_cluster,
                         prog_options.timout,
                         prog_options.auto_clear)

    elif prog_options.clear:
        if not prog_options.vcs_group and not prog_options.vcs_system and \
                not prog_options.vcs_cluster:
            arg_parser.error('Need a Cluster, System or Group to online!')
        vcs.hagrp_clear(prog_options.vcs_group,
                        prog_options.vcs_cluster,
                        prog_options.vcs_system)

    elif prog_options.switch:
        if not prog_options.vcs_group and not prog_options.vcs_system and \
                not prog_options.vcs_cluster:
            arg_parser.error('Need a Cluster, System or Group to online!')
        vcs.hagrp_switch(prog_options.vcs_group,
                         prog_options.vcs_system,
                         prog_options.vcs_cluster, prog_options.timout)


if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
