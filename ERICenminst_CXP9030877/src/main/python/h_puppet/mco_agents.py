# pylint: disable=C0302
"""
The primary goal of this module is to provide wrapper classes for
various MCO agents and action they can provide.

To see a list of installed agents on a system, run 'mco plugin doc'
To see what actions an agent provides, run 'mco plugin doc <agent_name>'
e.g. mco plugin doc enminst

Only required agents/actions should be defined in this module.

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
import re
from json import dumps
from time import strptime
from collections import OrderedDict

from h_logging.enminst_logger import init_enminst_logging
from h_puppet import discover_peer_nodes
from litp.core.rpc_commands import run_rpc_command


class McoAgentException(Exception):
    """
    MCO agent operation failed.
    """

    def __init__(self, *args):
        """ Make the original dict data available as part of the exception.
        """
        super(McoAgentException, self).__init__(*args)
        self.data = {}
        if args and isinstance(args[0], dict):
            self.data = args[0]

    @property
    def err(self):
        """ Return the actual error message from the MCO returned data
        :return: str
        """
        return self.data.get('err', next((v.get('errors')
                                          for v in self.data.values()
                                          if isinstance(v, dict)), str(self)))


class VcsCmdApiException(Exception):
    """
    MCO VCS rpc operation failed.
    """
    pass


class BaseAgent(object):
    """
    Base MCO agent class.
    """

    def __init__(self, agent_name):
        """
        Constructor

        :param agent_name: The MCO agent name
        :type agent_name: str
        """
        self.__agent = agent_name

    def mco_exec(self,  # pylint: disable=too-many-arguments,too-many-locals
                 command, args, mco_exec_host,
                 errkey='retcode', stdoutkey='out',
                 rpc_command_timeout=None,
                 ignore_agent_errors=False):
        """
        Execute an agent action

        :param command: The action name
        :type command: str
        :param args: list of agent arguement args
        :type args: list()
        :param mco_exec_host: The host to execute the agent command on
        :type mco_exec_host: str[]|str|None
        :param errkey: The key to use to check for error responses
        :type errkey: str
        :param stdoutkey: The key containing command output (if any)
        :type stdoutkey: str
        :param rpc_command_timeout: RPC command execution timeout
        :type rpc_command_timeout: None|int
        :param ignore_agent_errors: Should agent error be ignored or not
        :type ignore_agent_errors: bool
        :returns: Result of remote agent command
        :rtype: str | dict
        """
        if not mco_exec_host:
            rpc_hosts = []
        elif type(mco_exec_host) is list:
            rpc_hosts = mco_exec_host
        else:
            rpc_hosts = [mco_exec_host]

        map_args = {}
        if args:
            for line in args:
                name, value = line.split('=', 1)
                map_args[name] = value
        rpc_results = run_rpc_command(rpc_hosts, self.__agent,
                                      command, map_args,
                                      timeout=rpc_command_timeout,
                                      retries=0)
        return_results = {}
        for sender, rpc_data in rpc_results.items():
            if rpc_data['errors']:
                raise McoAgentException(rpc_results)

            sender_data = rpc_data['data']
            # Check the agents return code
            if not ignore_agent_errors and int(
                    sender_data[errkey]) != 0:
                exception_data = dict(sender_data)
                exception_data['node'] = sender
                raise McoAgentException(exception_data)
            return_results[sender] = sender_data[stdoutkey]
        if not mco_exec_host or type(mco_exec_host) is list:
            return return_results
        else:
            return return_results[mco_exec_host]

    @staticmethod
    def get_exec_system(system, mco_host):
        """
        Source hostname of vcs node
        :param system
        :param mco_host
        :return
        """
        if mco_host:
            return mco_host
        else:
            return system


class EnminstAgent(BaseAgent):  # pylint: disable=R0904
    """
    Wrapper for the enminst mco agent
    """
    MCO = '/usr/bin/mco'
    AGENT = 'enminst'
    ACT_HAGRP_CLEAR = 'hagrp_clear'
    ACT_HAGRP_OFFLINE = 'hagrp_offline'
    ACT_HAGRP_WAIT = 'hagrp_wait'
    ACT_HAGRP_SWITCH = 'hagrp_switch'
    ACT_HASYS_STATE = 'hasys_state'

    def __init__(self):
        """
        Constructor
        """
        super(EnminstAgent, self).__init__('enminst')
        self.logger = init_enminst_logging()

    def haclus_list(self, node):
        """
        Get a list of VCS clusters (if any) on a node

        :param node: The node(s) to run this action on
        :type node: str[]|str
        :return: list(str)
        """
        return str(self.mco_exec('haclus_list', None, node)).strip()

    def hagrp_list(self, vcs_system):
        """
        Get a list of VSC groups on a vcs system
        :param vcs_system: The VCS system to run this action on
        :type vcs_system: str
        :return: list(str)
        """
        stdout = str(self.mco_exec('hagrp_list', None, vcs_system))
        group_list = []
        for line in stdout.split('\n'):
            line = line.strip()
            if len(line) == 0:
                continue
            group_name = line.split()[0].strip()
            if group_name not in group_list:
                group_list.append(group_name)
        return group_list

    def hagrp_display(self, groups, vcs_system):
        """
        Get attributes for VCS group/groups on a VCS system (hagrp -display)

        :param groups: Comma seperate list of groups to get info on
        :type groups: str
        :param vcs_system: The VCS system to run this action on
        :type vcs_system: str
        :return: dict()
        """
        stdout = self.mco_exec('hagrp_display',
                               ['groups={0}'.format(','.join(groups))],
                               vcs_system)
        group_data = {}
        if 'VCS ERROR' in ''.join(stdout):
            raise McoAgentException(stdout)

        for group_info in stdout:
            lines = group_info.split('\n')[1:]
            for line in lines:
                _match = re.search(r'^(.*?)\s+(.*?)\s+(.*?)\s+(.*)', line)
                group_name = _match.group(1)
                attribute = _match.group(2)
                system = _match.group(3)
                if '' == system:
                    system = _match.group(4)
                    value = ''
                else:
                    value = _match.group(4)
                if group_name not in group_data:
                    group_data[group_name] = {}
                if system not in group_data[group_name]:
                    group_data[group_name][system] = {}
                group_data[group_name][system][attribute] = value
        return group_data

    def hagrp_history(self, group_name=None, vcs_system=None):
        """
        Get VCS events for a group

        :param group_name: The VCS group name
        :type group_name: str
        :param vcs_system: The VCS system to run this action on
            :type vcs_system: str
        :return: dict
        """
        args = []
        if group_name:
            args = ['group={0}'.format(group_name)]
        event_time_format = '%a %b %d %H:%M:%S %Y'
        data = self.mco_exec('hagrp_history', args, vcs_system)
        for group, events in data.items():
            for event in events:
                event['ts'] = strptime(event['date'], event_time_format)
            data[group] = sorted(events, key=lambda k: k['ts'])
        return data

    @staticmethod
    def get_states(vcs_state_string):
        """
        get_states returns state value based on filter passed
        :param vcs_state_string: state
        :return
        """
        return filter(None, vcs_state_string.strip().split('|'))

    def _vcs_state(self, state_command, vcs_host):
        """
        _vcs_state is used to generate the state of the system
        :param state_command
        :param vcs_host
        :return: headers, systems
        """
        if vcs_host:
            mco_exec_host = vcs_host
        else:
            mco_exec_host = discover_peer_nodes()[0]
        states = str(self.mco_exec(state_command, None,
                                   mco_exec_host)).split('\n')
        headers = states[0].split(' ')
        headers = filter(None, headers)
        headers = [str(h).translate(None, '#') for h in headers]
        systems = []
        for system in states[1:]:
            props = system.split(' ')
            props = filter(None, props)
            if len(props) == 0:
                continue
            sysmap = {}
            for i in xrange(0, len(props)):
                sysmap[headers[i]] = props[i]
            systems.append(sysmap)
        return headers, systems

    def hasys_state(self, mco_host=None):
        """
        hasys_state used to generate the state of system
        :param mco_host: host name
        :return:
        """
        keyheaders = ['Name', 'State']
        _, systems = self._vcs_state('hasys_state', mco_host)

        states = []
        for system in systems:
            states.append(
                {
                    keyheaders[0]: system['System'],
                    keyheaders[1]: EnminstAgent.get_states(system['Value'])
                }
            )
        return keyheaders, states

    def hagrp_state(self, mco_host=None):
        """
        hagrp_state used to generate the state of group services on host
        :param mco_host: host name
        :return:
        """
        keyheaders = ['Name', 'System', 'State']
        _, groups = self._vcs_state('hagrp_state', mco_host)
        states = []
        for group in groups:
            states.append(
                {
                    keyheaders[0]: group['Group'],
                    keyheaders[1]: group['System'],
                    keyheaders[2]: EnminstAgent.get_states(group['Value'])
                }
            )
        return keyheaders, states

    def hagrp_clear(self, group_name, system):
        """
        Clear selected group name
        :param group_name:  VCS group name
        :param system: VCS host
        :raise ioe:
        """
        args = ['group_name={0}'.format(group_name)]
        try:
            self.mco_exec('hagrp_clear', args, system)
        except Exception as ioe:
            self.logger.error("Unable to clear service group: {0} in the "
                              "cluster".format(group_name))
            raise ioe

    def hagrp_switch(self, group_name, to_system, mco_host):
        """
        Switch hagrp from one system to another
        :param group_name: The VCS group name
        :param to_system: The system to swtich the group to
        :param mco_host: Override the MCO target, default is ``to_system``
        :raise ioe:
        """
        args = ['group_name={0}'.format(group_name)]
        if to_system:
            args.append('system={0}'.format(to_system))
        try:
            self.mco_exec('hagrp_switch', args, mco_host)
        except Exception as error:  # pylint: disable=broad-except
            if error.args and type(error.args[0]) is dict:
                raise McoAgentException(error.args[0]['err'])
            else:
                raise

    def hagrp_freeze(self, group_name, group_system, persistent=False):
        """
        Freeze a VCS group.

        :param group_name: The groups to freeze
        :type group_name: str
        :param group_system: A system the group is assigned to.
        :type group_system: str
        :param persistent: Should the freeze be maintained after a system
        is rebooted.

        :type persistent: bool

        """
        args = ['group_name={0}'.format(group_name)]
        litp_vcs_api = VcsCmdApiAgent()
        if persistent:
            args.append('persistent=true')
            litp_vcs_api.haconf_makerw(group_system)
        try:
            self.mco_exec('hagrp_freeze', args, group_system)
        except McoAgentException:
            # Dont log anything, just forward on the error, let whatevers
            # calling this log the error if needed
            raise
        except Exception:
            self.logger.exception("Unable to freeze group: {0} "
                                  .format(group_name))
            raise
        finally:
            if persistent:
                litp_vcs_api.haconf_makero(group_system)

    def hagrp_unfreeze(self, group_name, group_system, persistent=False):
        """
        UnFreeze a VCS group.

        :param group_name: The groups to unfreeze
        :type group_name: str
        :param group_system: A system the group is assigned to.
        :type group_system: str
        :param persistent: Should the unfreeze be maintained after a system
        is rebooted.

        :type persistent: bool

        """
        args = ['group_name={0}'.format(group_name)]
        litp_vcs_api = VcsCmdApiAgent()
        if persistent:
            args.append('persistent=true')
            litp_vcs_api.haconf_makerw(group_system)
        try:
            self.mco_exec('hagrp_unfreeze', args, group_system)
        except McoAgentException:
            # Dont log anything, just forward on the error, let whatevers
            # calling this log the error if needed
            raise
        except Exception:
            self.logger.exception("Unable to unfreeze group: {0} "
                                  .format(group_name))
            raise
        finally:
            if persistent:
                litp_vcs_api.haconf_makero(group_system)

    def hasys_freeze(self, vcs_system, persistent=False, evacuate=False):
        """
        Freeze a VCS system.

        :param vcs_system: The system to freeze
        :type vcs_system: str
        :param persistent: Should the freeze be maintained after a system
        :param evacuate: If VCS evacuate is to be performed on the system
        is rebooted.

        :type persistent: bool

        """
        args = ['system={0}'.format(vcs_system)]
        litp_vcs_api = VcsCmdApiAgent()

        try:
            if evacuate:
                args.append('evacuate=true')

            if persistent:
                args.append('persistent=true')
                litp_vcs_api.haconf_makerw(vcs_system)
            self.mco_exec('hasys_freeze', args, vcs_system)
        except IOError:
            self.logger.exception('Unable to freeze system {0}'
                                  ''.format(vcs_system))
            raise
        finally:
            if persistent:
                litp_vcs_api.haconf_makero(vcs_system)

    def hasys_unfreeze(self, vcs_system, persistent=False):
        """
        Unfreeze a VCS system.

        :param vcs_system: The system to unfreeze
        :type vcs_system: str
        :param persistent: Should the unfreeze be maintained after a system
        is rebooted.

        :type persistent: bool

        """
        args = ['system={0}'.format(vcs_system)]
        litp_vcs_api = VcsCmdApiAgent()
        try:
            if persistent:
                args.append('persistent=true')
                litp_vcs_api.haconf_makerw(vcs_system)
            self.mco_exec('hasys_unfreeze', args, vcs_system)
        except IOError:
            self.logger.exception('Unable to unfreeze system {0}'
                                  ''.format(vcs_system))
            raise
        finally:
            if persistent:
                litp_vcs_api.haconf_makero(vcs_system)

    def hasys_display(self, system_list, mco_host=None):
        """
        Get system(s) VCS attributes.

        :param system_list: List of systems to get the attributes for,
        :type system_list: list
        :param mco_host: The VCS system to offline the group on
        :returns: Map of systems and their VCS attributes.
        :rtype: dict
        """
        if mco_host:
            call_host = mco_host
        else:
            call_host = system_list[0]
        stdout = self.mco_exec('hasys_display',
                               ['systems={0}'.format(','.join(system_list))],
                               call_host)
        system_data = {}
        for system, data in stdout.items():
            system_data[system] = {}
            for line in data.split('\n')[1:]:
                _match = re.search(r'^(.*?)\s+(.*?)\s+(.*)', line)
                system, attribute, att_value = _match.groups()
                system_data[system][attribute] = att_value
        return system_data

    def hagrp_offline(self, group_name, system, mco_host=None):
        """
        Offline selected group name
        :param group_name:  VCS group name
        :param system: VCS host
        :param mco_host: The VCS system to offline the group on
        :raise ioe:
        """
        args = ['group_name={0}'.format(group_name)]
        if system:
            args.append('system={0}'.format(system))
        try:
            self.mco_exec('hagrp_offline', args,
                          self.get_exec_system(system, mco_host))
        except Exception as ioe:
            self.logger.error("Unable to offline service group: {0} in the "
                              "cluster".format(group_name))
            raise ioe

    def hagrp_online(self, group_name, system, propagate=False,
                     mco_host=None):
        """
        Online selected group name
        :param group_name:  VCS group name
        :param system: VCS host to online the group on
        :param propagate: If ``True`` all of its required child groups are
        also brought online.

        :param mco_host: Override the MCO target, default is ``system``
        """
        args = ['group_name={0}'.format(group_name)]
        if system:
            args.append('system={0}'.format(system))
        if propagate:
            args.append('propagate=true')
        try:
            stdout = self.mco_exec('hagrp_online', args,
                                   self.get_exec_system(system, mco_host))
            if 'V-16-1-40229' in stdout:
                raise McoAgentException(stdout)
        except IOError as ioe:
            self.logger.error('Unable to online service group '
                              '{0}'.format(group_name))
            raise ioe

    def lvs_list(self, hosts, lv_opts):
        """
        Get LVM information from nodes
        :param hosts: List of mcollective hosts to get the LVM data
        :type hosts: str[]
        :param lv_opts: Comma seperated list of logical volume fields to get,
        see ``lvs -o help`` for possible values.

        :returns: Map of host and LVM data
        :rtype dict
        """
        return self.mco_exec('lvs_list', ['lv_opts={0}'.format(lv_opts)],
                             mco_exec_host=hosts)

    def get_mem(self):
        """
        Get provided memory value from nodes

        :returns: Map of host and memory data
        :rtype dict
        """
        return self.mco_exec('get_mem', None, None)

    def get_cores(self):
        """
        Get number of cores from nodes


        :returns: Map of host and cores data
        :rtype dict
        """
        return self.mco_exec('get_cores', None, None)

    def get_fs_usage(self):
        """
        Get fs usage nodes

        :returns: Map of each nodes filesystem usage
        :rtype dict
        """
        return self.mco_exec('get_fs_usage', None, None)

    def get_stale_mounts(self):
        """
        Finds stale mounts on nodes

        :returns: Map of stale mounts on each node
        :rtype dict
        """
        return self.mco_exec('get_stale_mounts', None, None)

    def update_initial_credentials(self, nodes, user, new_pass):
        """
        Sets the password for a user with an expired password
        on a list of nodes

        :param nodes: a list of nodes
        :param user: a str containing the username
        :param new_pass: a str containing the new password
        :returns: Map of return values, stdout and errors
        :return: dict
        """
        return self.mco_exec('update_initial_credentials',
                             ['user={0}'.format(user),
                              'new_pass={0}'.format(new_pass)],
                             mco_exec_host=nodes,
                             ignore_agent_errors=True)

    def scan_device_tree(self, hosts=None):
        """
        Scan devices in the operating system device tree
        :param hosts: List of hosts where scan to be running
        :returns:
        """
        return self.mco_exec('vxdisk_scandisks', None, mco_exec_host=hosts)

    def runlevel(self, hosts=None):
        """
        Get the OS run level for a blade
        :param hosts: List of hosts to check at once. If not set, all known
        hosts are checked
        :returns: Map of hostname to runlevel state
        :rtype: dict
        """
        return self.mco_exec('runlevel', None, mco_exec_host=hosts)

    def service_list(self, run_level, hosts=None):
        """
        Get a list of OS services that are configured to run at a certain
        OS runlevel
        :param run_level: The runlevel to use
        :param hosts: List of hosts to check at once. If not set, all known
        hosts are checked
        :returns: Map of host to service list
        :rtype: dict
        """
        return self.mco_exec('service_list',
                             ['run_level={0}'.format(run_level)],
                             mco_exec_host=hosts)

    def check_service(self, service, hosts=None):
        """

        :param service:
        :param hosts: List of hosts to check at once. If not set, all known
        hosts are checked
        :returns: Map of host to service states
        :rtype: dict
        """
        return self.mco_exec('check_service',
                             ['service={0}'.format(service)],
                             mco_exec_host=hosts)

    def create_lv_snapshots(self, snap_info, snap_hosts):
        """
        Create LV snapshots of node local volumes
        :param snap_info:
        :type snap_info: dict
        :param snap_hosts:
        :type snap_hosts: str[]
        :return:
        """
        args = ['snap_info={0}'.format(dumps(snap_info))]
        return self.mco_exec('create_lv_snapshots', args,
                             mco_exec_host=snap_hosts)

    def delete_lv_snapshots(self, snap_tag, snap_hosts):
        """
        Delete LV snapshot with specific tag

        :param snap_tag: The snapshot tag
        :type snap_tag: str
        :param snap_hosts: Hosts to execute the lvremove on
        :type snap_hosts: str[]
        :returns: Output of lvremove on hosts
        :rtype: dict
        """
        args = ['tag_name={0}'.format(snap_tag)]
        return self.mco_exec('delete_lv_snapshots', args,
                             mco_exec_host=snap_hosts)

    def restore_lv_snapshots(self, snap_tag, snap_hosts):
        """
        Restore LV snapshot with specific tag

        :param snap_tag: The snapshot tag
        :type snap_tag: str
        :param snap_hosts: Hosts to execute the lvconvert on
        :type snap_hosts: str[]
        :returns: Output of lvconvert on hosts
        :rtype: dict
        """
        args = ['tag_name={0}'.format(snap_tag)]
        return self.mco_exec('restore_lv_snapshots', args,
                             mco_exec_host=snap_hosts)

    def execute_sync_command(self, snap_hosts):
        """
        Execute sync command to flush filesystem buffers
        to disk prior to hard reboot of nodes

        :param snap_hosts: Hosts to execute the sync on
        :type snap_hosts: str[]
        :returns: Output of sync on hosts
        :rtype: dict
        """
        return self.mco_exec('execute_sync_command', None,
                             mco_exec_host=snap_hosts)

    def vxfenclearpre(self, node):
        """
        Remove SCSI3 registrations and reservations from disks.

        :param node: The node to clear the keys on.
        :returns: stdout of the vxfenclearpre command
        :rtype: str
        """
        return self.mco_exec('vxfenclearpre', None, mco_exec_host=node,
                             ignore_agent_errors=True)

    def migrate_elasticsearch_indexes(self, node):
        """
        Migrates the Elasticsearch 2.1 indexes to Elasticsearch 5.6

        :return:
        """
        command = 'migrate_elasticsearch_indexes'
        return self.mco_exec(command, None, mco_exec_host=node)

    def get_redundancy_level(self, hosts=None):
        """
        Get the number of paths to each disk
        :param nodes: list of nodes to get the paths from
        :return: stdout of the MP command
        """
        command = 'get_redundancy_level'
        return self.mco_exec(command, None, mco_exec_host=hosts)

    def get_mco_fact_disk_list(self, hosts=None):
        """
        Get mco facts and dev_mapper directory list
        :param nodes: list of nodes to get the paths from
        :return: stdout of the MP command
        """
        return self.mco_exec('get_mco_fact_disk_list',
                             None,
                             mco_exec_host=hosts)

    def get_mp_bind_names_config(self, hosts=None):
        """
        Get multipath friendly names config
        :param nodes: list of nodes to get the paths from
        :return: stdout of the MP command
        """
        return self.mco_exec('get_mp_bind_names_config',
                             None,
                             mco_exec_host=hosts)

    def shutdown_host(self, node):
        """
        Issue a shutdown -h now on 'node'
        :param node: The node(s) to run this action on
        :type node: str[]|str
        :return: list(str)
        """
        return str(self.mco_exec('safe_shutdown', None, node)).strip()

    def consul_service_restart(self, node):
        """
        Issues an consul service restart on the node provided
        :param command:
        :param node:
        :rtype: dict
        """
        try:
            stdout = self.mco_exec('consul_service_restart', None,
                                   mco_exec_host=node)
        except McoAgentException as error:
            return error.args[0]
        return stdout

    def get_lvm_conf_global_filter(self, node):
        """
        Run the get_lvm_conf_global_filter mco action
        :param node: The node to run this action on
        :type node: str
        :returns: The contents of the global_filter lvm.conf entry
        :rtype: str
        """
        return self.mco_exec('get_lvm_conf_global_filter', None,
            mco_exec_host=node)

    def get_lvm_conf_filter(self, node):
        """
        Run the get_lvm_conf_filter mco action
        :param node: The node to run this action on
        :type node: str
        :returns: The contents of the filter lvm.conf entry
        :rtype: str
        """
        return self.mco_exec('get_lvm_conf_filter', None, mco_exec_host=node)

    def get_grub_conf_lvs(self, node):
        """
        Run the get_grub_conf_lvs mco action
        :param node: The node to run this action on
        :type node: str
        :returns: LVs present in grub.conf file
        :rtype: str
        """
        return self.mco_exec('get_grub_conf_lvs', None, mco_exec_host=node)

    def get_active_and_prime_bond_mbr(self, node):
        """
        Run the get_active_and_prime_bond_mbr mco action and
        process the output.
        :param node: The node to run this action on
        :type node: str
        :returns: The active and primary bond member from the bond0 file
        :rtype: dict
        """
        stdout = self.mco_exec('get_active_and_prime_bond_mbr',
                                    None,
                                    mco_exec_host=node)
        member_dict = OrderedDict()
        remove = r'\([\w\s]*\)'
        # Removes content in brackets from primary member line
        processed_stdout = re.sub(remove, '', stdout).strip().split('\n')
        for line in processed_stdout:
            line = line.replace('Currently ', '')
            line = line.replace('Slave', 'Member')
            split_line = line.split(': ')
            member_dict[split_line[0]] = split_line[1].strip()
        return member_dict

    def get_bond_interface_info(self, node):
        """
        Run the get_bond_interface_info mco action and
        process the output.
        :param node: The node to run this action on
        :type node: str
        :returns: list of bond interface details
        :rtype: list
        """
        stdout = self.mco_exec('get_bond_interface_info',
                                    None,
                                    mco_exec_host=node)
        interfaces_list = []

        for interface in stdout.split('--'):  # pylint: disable=E1103
            interface_details = OrderedDict()
            lines = interface.strip().split('\n')

            for line in lines:
                line = line.replace('Slave', 'Member')
                split_line = line.split(': ')
                interface_details[split_line[0]] = split_line[1]
            interfaces_list.append(interface_details)
        return interfaces_list


class VcsCmdApiAgent(BaseAgent):
    """
    Wrapper for the vcs_cmd_api mco agent
    """

    def __init__(self):
        super(VcsCmdApiAgent, self).__init__('vcs_cmd_api')
        self.logger = init_enminst_logging()

    def hagrp_wait(self, group_name, system, state,
                   timeout=60):
        """
        Wait function; used to ensure service goes into correct state
        :param group_name: VCS group name
        :param system: vcs host
        :param state: the state we want the service to go to
        :param timeout: timeout
        """
        args = ['group_name={0}'.format(group_name),
                'state={0}'.format(state),
                'node_name={0}'.format(system),
                'timeout={0}'.format(timeout)]
        rpc_timout = timeout + 5
        self.mco_exec('hagrp_wait', args, system,
                      rpc_command_timeout=rpc_timout)

    def haconf_makerw(self, vcs_system):
        """
        Change VCS to read-write mode.

        :param vcs_system: The node to make the call to
        :type vcs_system: str
        """
        args = ['haaction=makerw', 'read_only=false']
        try:
            self.mco_exec('haconf', args, vcs_system)
        except IOError:
            self.logger.exception('Unable to change VCS to read-write mode')
            raise

    def haconf_makero(self, vcs_system):
        """
        Change VCS to read-only mode.

        :param vcs_system: The node to make the call to
        :type vcs_system: str
        """
        args = ['haaction=dump', 'read_only=true']
        try:
            self.mco_exec('haconf', args, vcs_system)
        except IOError:
            self.logger.exception('Unable to change VCS to read-only mode')
            raise

    def lock(self, vcs_system, switch_timeout):
        """
        LITP lock a node.

        :param vcs_system: The node to lock
        :type vcs_system: str
        :param switch_timeout: The time to wait for the failover groups
        to offline during switch
        :type switch_timeout: int
        """
        try:
            action_args = [
                'sys={0}'.format(vcs_system),
                'switch_timeout={0}'.format(switch_timeout)
            ]
            self.mco_exec('lock', action_args, vcs_system)
        except IOError:
            self.logger.exception('Unable to lock system {0}'
                                  ''.format(vcs_system))
            raise

    def unlock(self, vcs_system, nic_wait_timeout=300):
        """
        LITP unlock a node.

        :param vcs_system: The node to unlock
        :type vcs_system: str
        :param nic_wait_timeout: The time to wait for the NICs to be up
        :type nic_wait_timeout: int
        """
        try:
            action_args = [
                'sys={0}'.format(vcs_system),
                'nic_wait_timeout={0}'.format(nic_wait_timeout)
            ]
            self.mco_exec('unlock', action_args, vcs_system)
        except IOError:
            self.logger.exception('Unable to unlock system {0}'
                                  ''.format(vcs_system))
            raise


class FilemanagerAgent(BaseAgent):
    """
    Wrapper for the filemanager mco agent
    """

    def __init__(self):
        super(FilemanagerAgent, self).__init__('filemanager')

    def exists(self, file_path, nodes):
        """
        Check if a file exists on 1 or more nodes
        :param file_path: Path to a file
        :type file_path: str
        :param nodes: List of nodes to check
        :type nodes: str[]
        :returns: Map of host->boolean on files existance
        :rtype: dict
        """
        return self.mco_exec('exist', ['file={0}'.format(file_path)], nodes)

    def move(self, src, dest, node, command_timeout=None):
        """
        Rename SOURCE to DEST, or move SOURCE(s) to DIRECTORY
        :param src: Path to source file
        :type src: str
        :param dest: Path to destination file / directory
        :type dest: str
        :param node: mco agent node name
        :type node: str
        :param command_timeout: Command timeout
        :type command_timeout: None / int
        """
        self.mco_exec('move', ['src={0}'.format(src), 'dest={0}'.format(dest)],
                      node, rpc_command_timeout=command_timeout)

    def copy_file(self, src, dest, hosts):
        """
        Make a copy of a file on host(s)
        :param src: Path of file to copy
        :param dest: Path to copy file to
        :param hosts: List of hosts to copy the file on. If not set, all known
        MCO hosts are used.
        :returns: Result of file copy on target hosts
        :rtype: dict
        """
        return self.mco_exec('copy_file',
                             ['src={0}'.format(src),
                              'dest={0}'.format(dest)],
                             mco_exec_host=hosts)

    def delete(self, file_path, hosts):
        """
        Delete a file
        :param file_path: Path of file to delete
        :param hosts: List of hosts to delete the file on. If not set, all
        known MCO hosts are used.
        :returns: Result of file deletion on target hosts
        :rtype: dict
        """
        return self.mco_exec('delete',
                             ['file={0}'.format(file_path)],
                             mco_exec_host=hosts)


class LltStatAgent(BaseAgent):
    """
    Wrapper for the lltstat mco agent
    """

    def __init__(self):
        super(LltStatAgent, self).__init__('enminst')
        self.logger = init_enminst_logging()

    def get_lltstat_data(self):
        """
        Collect the lltstat data
        :returns: Map of host->lltstat data
        :rtype: dict
        """
        return self.mco_exec('lltstat_active', None, None,
                             ignore_agent_errors=True)

    def get_cluster_list(self):
        """
        Collect the cluster details
        :returns: Map of host->cluster data
        :rtype: dict
        """
        return self.mco_exec('haclus_list', None, None,
                             ignore_agent_errors=True)


class PostgresAgent(BaseAgent):
    """
    Wrapper for the postgres mco agent
    """

    def __init__(self):
        super(PostgresAgent, self).__init__('postgres')
        self.logger = init_enminst_logging()

    def call_postgres_service_reload(self, host):
        """
        Calls service reload procedure
        :returns: None
        """
        self.mco_exec('service_reload', None,
                      mco_exec_host=host)


class PostgresMcoAgent(BaseAgent):
    """
    Wrapper for the postgres enminst mco agent
    """

    def __init__(self, host=None):
        super(PostgresMcoAgent, self).__init__('enminst')
        self.logger = init_enminst_logging()
        self.host = host

    def get_postgres_mnt_perc_used(self):
        """
        Get postgres mount percentage of space used
        :return: str
        """
        return self.mco_exec('postgres_mount_perc_used', None, self.host)


class Neo4jClusterMcoAgent(BaseAgent):
    """
    Wrapper for the Neo4j cluster mco agent.
    """

    def __init__(self, host):
        super(Neo4jClusterMcoAgent, self).__init__('enminst')
        self.host = host

    def get_cluster_overview(self):
        """
        Calls cluster overview from Neo4j active db host via mco task
        :return: dictionary representing Neo4j cluster
        :rtype: str
        """
        return self.mco_exec('neo4j_cluster_overview', None, self.host,
                             rpc_command_timeout=120)


class Neo4jFilesystemMcoAgent(BaseAgent):
    """ Runs puppet deployed python script on db host
    to get Neo4j filesystem information """
    def __init__(self):
        super(Neo4jFilesystemMcoAgent, self).__init__('enminst')
        self.logger = init_enminst_logging()

    def get_filesystem_status(self, host, args):
        """ Get Neo4j filesystem information
        :param host: db host
        :param args: expecting san arguments
        :return: dict
        """
        return self.mco_exec('pre_uplift_space_check', args, host)

    def has_file(self, host, file_path):
        """ Check whether a given file exists or not
        :param host: db host
        :param file_path: file_path
        :returns: dict
        :rtype: str
        """
        return self.mco_exec('has_file', ["file_path=%s" % file_path],
                             mco_exec_host=host)

    # pylint: disable=R0913
    def check_ssh_connectivity(self, host, to_host, user, password=None,
                               key_filename=None, sudo=False):
        """ Check whether a given file exists or not
        :param host: db host
        :param to_host: to_host
        :param user: user
        :param password: password
        :param key_filename: key_filename
        :param sudo: bool
        :returns: str
        :rtype: str
        """
        args = [
            'host=%s' % to_host,
            'user=%s' % user
        ]
        if password:
            args.append('password=%s' % password)
        if key_filename:
            args.append('key_filename=%s' % key_filename)
        if sudo:
            args.append('sudo=true')
        try:
            return self.mco_exec('check_ssh_connectivity', args,
                                 mco_exec_host=host,
                                 rpc_command_timeout=20)
        except McoAgentException as err:
            self.logger.debug("check_ssh_connectivity failed: %s" % err)
            if sudo:
                msg = 'No answer from node %s' % host
                if msg in err.err:
                    raise McoAgentException('%s. Passwordless sudo '
                                            'not properly set on %s, perhaps?'
                                            % (err.err, to_host))
            raise


class EnmPreCheckAgent(BaseAgent):  # pylint: disable=R0904
    """
    Wrapper for the ENM PreCheck MCO agent
    """

    def __init__(self, timeout=None):
        super(EnmPreCheckAgent, self).__init__('enminst')
        self.logger = init_enminst_logging()
        self.timeout = timeout

    def get_replication_status(self, host, base_dn, password):
        """
        Get OpenDJ replication status
        :param host: hostname
        :param base_dn: BaseDN
        :param password: password
        :returns: Output from dsreplication status command
        :rtype: dict
        """
        return self.mco_exec('dsreplication_status',
                             ['baseDN=%s' % base_dn,
                              'password=%s' % password,
                              'host=%s' % host],
                             mco_exec_host=host,
                             ignore_agent_errors=True,
                             rpc_command_timeout=self.timeout)

    def boot_partition_test(self, host):
        """
        Run the boot_partition_test mco action
        :param host: hostname
        :returns: Output from boot_partition_test command
        :rtype: string
        """
        return self.mco_exec('boot_partition_test', None, mco_exec_host=host,
                             ignore_agent_errors=True, stdoutkey='err',
                             rpc_command_timeout=self.timeout)

    def boot_partition_test_cleanup(self, host):
        """
        Run the boot_partition_test_cleanup mco action
        :param host: hostname
        :returns: Output from boot_partition_test_cleanup command
        :rtype: string
        """
        return self.mco_worker(host, 'boot_partition_test_cleanup')

    def boot_partition_mount(self, host):
        """
        Run the boot_partition_mount mco action
        :param host: hostname
        :returns: Output from boot_partition_mount command
        :rtype: string
        """
        return self.mco_worker(host, 'boot_partition_mount')

    def install_packages(self, host, package):
        """
        Run the install_packages mco action
        :param host: hostname
        :param package: package name
        :returns: Output from install_packages command
        :rtype: string
        """
        args = ['package={0}'.format(package)]
        return self.mco_exec('install_packages', args, mco_exec_host=host,
                             rpc_command_timeout=self.timeout)

    def remove_packages(self, host, package):
        """
        Run the remove_packages mco action
        :param host: hostname
        :returns: Output from remove_packages command
        :rtype: string
        """
        args = ['package={0}'.format(package)]
        return self.mco_exec('remove_packages', args, mco_exec_host=host,
                             ignore_agent_errors=True,
                             rpc_command_timeout=self.timeout)

    def upgrade_packages(self, host, package):
        """
        Run the upgrade_packages mco action
        :param host: hostname
        :returns: Output from remove_packages command
        :rtype: string
        """
        args = ['package={0}'.format(package)]
        self.logger.info(
            'Running Mco Upgrade Packages on host {0} with package {1} with '\
                'args {2}; timeout is set to {3}'.format(
                    host, package, args, self.timeout))
        return self.mco_exec('upgrade_packages', args, mco_exec_host=host,
                             rpc_command_timeout=self.timeout)

    def downgrade_packages(self, host, package):
        """
        Run the downgrade_packages mco action
        :param host: hostname
        :param package: package name
        :returns: Output from downgrade_packages command
        :rtype: string
        """
        args = ['package={0}'.format(package)]
        return self.mco_exec('downgrade_packages', args, mco_exec_host=host,
                             rpc_command_timeout=self.timeout)

    def get_available_package_versions(self, host, package):
        """
        Run the get_available_package_versions mco action
        :param host: hostname
        :param package: package name
        :returns: Output from get_available_package_versions command
        :rtype: string
        """
        args = ['package={0}'.format(package)]
        return str(self.mco_exec('get_available_package_versions',
                                 args, mco_exec_host=host,
                                 rpc_command_timeout=self.timeout))

    def get_package_info(self, host, package):
        """
        Run the get_package_info mco action
        :param host:
        :param package:
        :return:
        """
        args = ['package={0}'.format(package)]
        return str(self.mco_exec('get_package_info', args, mco_exec_host=host,
                                 rpc_command_timeout=self.timeout))

    def lvm_conf_backups_cleanup(self, host):
        """
        Run the lvm_conf_backups_cleanup mco action
        :param host: hostname
        :returns: Output from lvm_conf_backups_cleanup command
        :rtype: string
        """
        return self.mco_worker(host, 'lvm_conf_backups_cleanup')

    def get_lvm_conf_global_filter(self, host):
        """
        Run the get_lvm_conf_global_filter mco action
        :param host: hostname
        :returns: Output from get_lvm_conf_global_filter command
        :rtype: string
        """
        return self.mco_worker(host, 'get_lvm_conf_global_filter')

    def backup_lvm_conf(self, host):
        """
        Run the backup_lvm_conf mco action
        :param host: hostname
        :returns: Output from backup_lvm_conf command
        :rtype: string
        """
        return self.mco_worker(host, 'backup_lvm_conf')

    def update_lvm_conf_global_filter(self, host):
        """
        Run the update_lvm_conf_global_filter mco action
        :param host: hostname
        :returns: Output from update_lvm_conf_global_filter command
        :rtype: string
        """
        return self.mco_worker(host, 'update_lvm_conf_global_filter')

    def add_lvm_nondb_filter(self, host):
        """
        Run the  add_lvm_non_db_filters mco action
        :param host: hostname
        :returns: Output from add_lvm_nondb_filter command
        :rtype: string
        """
        return self.mco_worker(host, 'add_lvm_nondb_filter')

    def add_lvm_nondb_global_filter(self, host):
        """
        Run the add_lvm_nondb_global_filter mco action
        :param host: hostname
        :returns: Output from add_lvm_nondb_global_filter command
        :rtype: string
        """
        return self.mco_worker(host, 'add_lvm_nondb_global_filter')

    def physical_volume_scan(self, host):
        """
        Run the physical_volume_scan mco action
        :param host: hostname
        :returns: Output from physical_volume_scan command
        :rtype: string
        """
        return self.mco_worker(host, 'physical_volume_scan')

    def get_count_dmsetup_deps_non_dm(self, host):
        """
        Run the get_count_dmsetup_deps_non_dm mco action
        :param host: hostname
        :returns: Output from get_count_dmsetup_deps_non_dm command
        :rtype: string
        """
        return self.mco_worker(host, 'get_count_dmsetup_deps_non_dm')

    def stop_vcs_and_reboot(self, host):
        """
        Run the stop_vcs_and_reboot mco action
        :param host: hostname
        :returns: Output from stop_vcs_and_reboot command
        :rtype: string
        """
        return self.mco_worker(host, 'stop_vcs_and_reboot')

    def mco_worker(self, host, action):
        """
        Run a named MCo action
        :param host: hostname
        :param action: mco action
        :return: Output from mco action command
        :rtype: string
        """
        return self.mco_exec(action, None, mco_exec_host=host,
                             ignore_agent_errors=True,
                             rpc_command_timeout=self.timeout)


class PuppetAgent(BaseAgent):
    """
    Wrapper for Puppet related actions
    """

    def __init__(self):
        super(PuppetAgent, self).__init__('puppet')
        self.logger = init_enminst_logging()

    def status(self):
        """
        Returns status of Puppet in the nodes
        :return: Output from mco action command
        :rtype: string
        """
        return self.mco_exec(
            'status', None, None, stdoutkey='enabled', ignore_agent_errors=True
        )
