"""
The purpose of this wrapper script is to find out if a modelled xml deployment
will have enough hardware resources (CPU and RAM) if customisations should
happen to the model
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2016 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : hw_resources.py
# Purpose : The purpose of this wrapper script is to find out if a modelled
# xml deployment will have enough hardware resources (CPU and RAM) if
# customisations should happen to the model
# ********************************************************************
import argparse
import logging
import sys
import textwrap
import h_litp.litp_utils as litp_utils
from operator import itemgetter
from os.path import join
from re import match
from tempfile import gettempdir

from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging
from h_puppet.mco_agents import EnminstAgent
from h_util.h_utils import ExitCodes
from h_vcs.vcs_utils import report_tab_data, sort_tab_data
from h_xml.xml_utils import load_xml, \
    get_xml_element_properties, xpath, get_parent


class HwResources(object):
    """
    Class containing hardware resources logic
    """

    H_SERVICE = 'Service'
    H_STATE = 'State'
    H_NODE = 'Node'
    H_RAMU = 'RAM used (MB)'
    H_CPUU = 'CPUs used'
    STATE_NOK = 'NOK'
    STATE_OK = 'OK'

    S_HEADER = ['Cluster', H_NODE, H_SERVICE, H_CPUU, H_RAMU]
    B_HEADER = ['Cluster', H_NODE, H_CPUU, 'CPU over-provision ratio',
                H_RAMU, 'RAM available (MB)', H_STATE]
    T_HEADERS = [H_NODE, H_CPUU, H_RAMU]

    def __init__(self, logger_name='hwresources'):
        self.logger_name = logger_name
        self.logger = logging.getLogger(logger_name)
        self.agent = EnminstAgent()
        self.base_model_xml = join(gettempdir(), 'exported.xml')
        self.__litp = LitpRestClient()

    def litp(self):
        """
        Get a reference the the LITP rest client
        Done like this so tests can stub out LITP

        :returns: LitpRestClient instance
        :rtype: LitpRestClient
        """
        return self.__litp

    def get_modeled_vm_resources(self,  # pylint: disable=R0914,R0912
                                 xml_document, current_usage=None):
        """
        Get hardware resources by loading in an xml document.
        Also get hardware resources by loading in an upgrade TO model and
        upgrade FROM resource usage. For Upgrade, customised services and
        their hardware resources must be included in the hardware resource
        usage of the Upgrade TO model.

        For further explanation on how this method traverses the model,
        and why it is the best solution see TORF-217934

        :param xml_document: load xml item
        :type xml_document: Element
        :param current_usage: Merge an upgrade model with a model
        :type current_usage: dict of dict
        :returns: Dictionary of found elements
        :rtype: dict
        """
        path = litp_utils.get_dd_xml_file()
        if not path:
            path = litp_utils.get_xml_deployment_file()
        vm_services = xpath(xml_document, 'vm-service')
        resource_usage = {}
        to_model_services = []
        for vm_service in vm_services:
            service = vm_service.get('id')
            inherited_vm = xpath(xml_document,
                                  'vm-service-inherit',
                                  {'source_path': '/software/services/'
                                                  '{0}'.format(service)})
            if not inherited_vm:
                lmsnode = get_parent(vm_service, 'ms')
                if lmsnode is None:
                    self.logger.info("Could not find a clustered service "
                                     "inheriting from {0}".format(service))
                continue
            else:
                inherited_vm = inherited_vm[0]
                vcs_cluster = get_parent(inherited_vm, 'vcs-cluster')
                cluster_name = vcs_cluster.get('id')
                clustered_service = get_parent(
                        inherited_vm, 'vcs-clustered-service')
                model_node_list = get_xml_element_properties(
                        clustered_service)['node_list'].split(',')

            if cluster_name not in resource_usage:
                resource_usage[cluster_name] = {}

            properties = get_xml_element_properties(vm_service)

            if not current_usage:
                is_custom = litp_utils.is_custom_service(vm_service, path)
            else:
                is_custom = False

            resource_usage[cluster_name][service] = \
                {'node_list': model_node_list,
                 'cpus': int(properties['cpus']),
                 'ram': int(properties['ram'][:-1]),
                 'custom': is_custom}

        if current_usage:
            for services in resource_usage.values():
                for service_name in services:
                    to_model_services.append(service_name)
            for cluster, services in current_usage.items():
                for service_name, properties in services.items():
                    if (service_name not in to_model_services) \
                            and properties['custom']:
                        customised_service = {service_name: properties}
                        resource_usage[cluster].update(customised_service)
        return resource_usage

    @staticmethod
    def get_blade_vm_resources(vm_usage):
        """
        Sum up hardware resources per blade

        :param vm_usage: Dictionary of data resources got from the model
        :type vm_usage: dict
        :returns: Sum of found elements per node
        :rtype: dict
        """
        _blade_usage = {}
        for cluster_name, services in vm_usage.items():
            _blade_usage[cluster_name] = {}
            for service, data in services.items():  # pylint: disable=W0612
                for node in data['node_list']:
                    if node not in _blade_usage[cluster_name]:
                        _blade_usage[cluster_name][node] = {
                            'cpus': 0,
                            'ram': 0
                        }
                    _blade_usage[cluster_name][node]['cpus'] += data['cpus']
                    _blade_usage[cluster_name][node]['ram'] += data['ram']
        return _blade_usage

    @staticmethod
    def show_layout(usage,  # pylint: disable=R0914
                    _services=True, _resources=True):
        """
        Prints the hardware resources being used per service
        according to the model

        :param usage: Dictionary of data resources got from the model
        :type usage: dict
        :param _services: Boolean that decides whether to show services tabbed
        data
        :type _services: bool
        :param _resources: Boolean that decides whether to show resources
        tabbed data
        :type _resources: bool
        """
        service_data = []
        node_total_usage = {}

        for cluster_name, services in usage.items():
            for service, resources in services.items():
                ram = resources['ram']
                cpu = resources['cpus']
                node_list = resources['node_list']
                for node in node_list:
                    row = [cluster_name, node, service, cpu, ram]
                    dictionary = dict(zip(HwResources.S_HEADER, row))
                    service_data.append(dictionary)
                    if node not in node_total_usage:
                        node_total_usage[node] = {'cpus': 0, 'ram': 0}
                    node_total_usage[node]['cpus'] += cpu
                    node_total_usage[node]['ram'] += ram
        service_data.sort(key=itemgetter(HwResources.H_NODE))
        if _services:
            report_tab_data(None, HwResources.S_HEADER, service_data)

        node_data = []
        for node, total_usage in node_total_usage.items():
            node_data.append(dict(zip(HwResources.T_HEADERS,
                                      [node,
                                       total_usage['cpus'],
                                       total_usage['ram']])
                                  ))
        sort_tab_data(node_data, 'RAM used (MB)', HwResources.T_HEADERS)
        if _resources:
            report_tab_data(None, HwResources.T_HEADERS, node_data)

    @staticmethod
    def is_hostname_sed_key(value):
        """
        Returns a match object if the value passed in is found between two sets
        of %%. Finds out whether a hostname belongs to the current
        deployment or not. Otherwise returns None

        :param value: Dictionary of hostname to node id mappings
        :type value: str
        """
        return match('%%.*%%', value)  # pylint: disable=R0914

    def show_blade_vm_usage(self,  # pylint: disable=R0914,R0912
                            modeled_usage, hostidmappings,
                            node_state, verbose=True):
        """
        Prints the hardware resources being used per node according to the
        model. Gets actual hardware resources using get_actual_mem() and
        get_actual_cpus(). If memory exceeds actual memory, the system will
        exit. If CPUs are over-provisioned by a ratio more than 4 a warning
        message will appear.

        :param modeled_usage: Dictionary of data resources got from the model,
        using to_blade_usage
        :type modeled_usage: dict
        :param hostidmappings:
        :type hostidmappings: dict
        :param verbose: displays resource usage table when true
        :type verbose: bool
        """
        hw_data = []
        exceed_use = any_checked = False

        actual_ram_dict = actual_cpu_dict = {}
        for value in hostidmappings.values():
            if not HwResources.is_hostname_sed_key(value):
                actual_ram_dict = self.get_actual_mem()
                actual_cpu_dict = self.get_actual_cpus()
                break

        ram_over_prov_list = []
        for cluster_name, nodes in modeled_usage.items():
            for node, resources in nodes.items():
                hostname = hostidmappings[node]
                modeled_ram = resources['ram']
                modeled_cpu = resources['cpus']
                state = HwResources.STATE_OK
                ram_available = '-'
                cpu_provision_ratio = '-'
                if HwResources.is_hostname_sed_key(hostname):
                    self.logger.debug('{0} is not not deployed, '
                                      'can\'t verify resources.'.format(node))
                else:
                    any_checked = True
                    physical_ram = actual_ram_dict.get(hostname, 0)
                    physical_cpu = actual_cpu_dict.get(hostname, 0)
                    self.logger.debug('Checking model hardware resources '
                                      'against actual hardware resources on '
                                      '{0}'.format(node))
                    if node_state[hostname] == \
                            LitpRestClient.ITEM_STATE_INITIAL:
                        state = LitpRestClient.ITEM_STATE_INITIAL
                    elif modeled_ram >= physical_ram:
                        exceed_use = True
                        state = HwResources.STATE_NOK
                        ram_over_prov_list.append(node)

                    if physical_cpu > 0:
                        opr = (float(modeled_cpu) / physical_cpu)
                        cpu_provision_ratio = '%.2g' % opr
                    if physical_ram > 0:
                        ram_available = physical_ram - modeled_ram
                row = [cluster_name, node, modeled_cpu, cpu_provision_ratio,
                       modeled_ram, ram_available, state]
                dictionary = dict(zip(HwResources.B_HEADER, row))
                hw_data.append(dictionary)

        hw_data = sort_tab_data(hw_data, 'RAM used (MB),Cluster',
                                HwResources.B_HEADER)

        if verbose:
            report_tab_data(None, HwResources.B_HEADER, hw_data)
        if any_checked:
            if exceed_use:
                self.logger.error('RAM Over Provisioned on: {0}'.
                                  format(', '.join(ram_over_prov_list)))
                raise SystemExit(ExitCodes.ERROR)

    @staticmethod
    def get_modeled_hosts(doc):
        """
        Get a dictionary of nodeId's to hostnames.
        i.e. {'svc-1':'ieatrcxb6035' ...}

        :param doc: xml model to get hostnames from
        :type doc: Element
        :returns: Dictionary of hostnames to nodeId's
        :rtype: dict
        """
        nodes = xpath(doc, 'node') + xpath(doc, 'ms')
        host_dict = {}
        for node in nodes:
            node_prop = get_xml_element_properties(node)
            node_id = node.get('id')
            hostname = node_prop['hostname']
            host_dict[hostname] = node_id

        return dict((y, x) for x, y in host_dict.iteritems())

    def get_actual_mem(self):
        """
        Get memory info from nodes on the current deployment using mco
        agent get_mem

        :returns: Dictionary of nodes and their memory usage
        :rtype: dict
        """
        nodes_mem_dict = {}

        host_info = self.agent.get_mem()
        for sender_name, agent_value in host_info.items():
            convert_to_mb = int(agent_value) / 1024
            agent_value = convert_to_mb
            nodes_mem_dict[sender_name] = agent_value
        return nodes_mem_dict

    def get_actual_cpus(self):
        """
        Get CPU info from nodes on the current deployment using mco
        agent get_cores

        :returns: Dictionary of nodes and their CPU usage
        :rtype: dict
        """
        nodes_cpu_dict = {}
        host_info = self.agent.get_cores()

        for sender_name, agent_value in host_info.items():
            nodes_cpu_dict[sender_name] = int(agent_value)
        return nodes_cpu_dict

    def export_model(self, output_file):
        """
        Export the current LITP model to a file in XML format
        :param output_file: Path of output file

        """
        self.litp().export_model_to_xml(output_file)

    def get_node_states(self):
        """
        Get the states of all nodes in the LITP model

        :returns: Mapping of node ID to model state
        :rtype: dict
        """
        return self.litp().get_node_states()


MAND_ARGS = textwrap.dedent('''
Mandatory arguments:
  -s, --services        Show resource usage of VM\'s on each node. When no
                        model is passed the current model is exported
  -r, --resources       Calculate what RAM/CPU will be required to run all
                        assigned VM\'s on a node. When no model is passed the
                        current model is exported. RAM is shown in MB
''')


def main(args):
    """
    Main fucntion
    :param args: sys args
    :return:
    """

    init_enminst_logging('hwresources')
    hw = HwResources()  # pylint: disable=C0103

    parser = argparse.ArgumentParser(prog="hw_resources.sh",
                                     usage='%(prog)s (-s | -r) '
                                           '[optional argument]',
                                     description=MAND_ARGS,
                                     formatter_class=argparse.
                                     RawTextHelpFormatter,
                                     add_help=False)

    view_options = parser.add_mutually_exclusive_group(required=True)
    view_options.add_argument('-s', '--services', action='store_true',
                              help=argparse.SUPPRESS)
    view_options.add_argument('-r', '--resources', action='store_true',
                              help=argparse.SUPPRESS)

    parser.add_argument('-m', '--model', dest='base_model',
                        metavar='[base_model]',
                        help='Pass in a deployment description XML and use '
                             'this as\nthe base model.')

    parser.add_argument('-um', '--ug_model', dest='upgrade_model',
                        metavar='upgrade_model',
                        help='Pass in a deployment description XML, which '
                             'will merge\nwith the base model XML to generate '
                             'a combined total\nresource usage.')
    parser.add_argument("-h", "--help", action="help",
                        help="show this help message and exit")

    if len(args) == 0:
        parser.print_help()
        raise SystemExit(2)

    optargs = parser.parse_args(args)

    node_state = {}
    if optargs.base_model:
        hw.base_model_xml = optargs.base_model
    else:
        hw.logger.info('Exporting model ...')
        hw.export_model(hw.base_model_xml)
        node_state = hw.get_node_states()

    base_doc = load_xml(hw.base_model_xml)
    base_usage = hw.get_modeled_vm_resources(base_doc)

    if optargs.upgrade_model:
        upgrade_doc = load_xml(optargs.upgrade_model)
        combined_usage = hw.get_modeled_vm_resources(upgrade_doc, base_usage)
        vm_resource_usage = hw.get_blade_vm_resources(combined_usage)
        modeled_hosts = hw.get_modeled_hosts(upgrade_doc)
        for hostname in modeled_hosts.values():
            if hostname not in node_state:
                node_state[hostname] = LitpRestClient.ITEM_STATE_INITIAL
        live_hosts = hw.get_modeled_hosts(base_doc)
        modeled_hosts.update(live_hosts)
        vm_layout = combined_usage
    else:
        vm_resource_usage = hw.get_blade_vm_resources(base_usage)
        vm_layout = base_usage
        modeled_hosts = hw.get_modeled_hosts(base_doc)

    if optargs.resources and optargs.base_model:
        hw.show_layout(vm_layout, _services=False)
    else:
        if optargs.resources:
            hw.show_blade_vm_usage(vm_resource_usage, modeled_hosts,
                                   node_state)
        else:
            hw.show_layout(vm_layout)


if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
