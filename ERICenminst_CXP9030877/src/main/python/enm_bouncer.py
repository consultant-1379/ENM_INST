# pylint: disable=R0801,R0914,R0912,R0201
"""
enm_bouncer Power-off Power-On ENM Peer Nodes
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
# Name    : enm_bouncer.py
# Purpose : Power-off Power-On ENM Peer Nodes.
# ********************************************************************
from h_util.h_utils import (ExitCodes, get_env_var, exec_process)
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import (init_enminst_logging,
                                       set_logging_level)
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from enm_upgrade_prechecks import EnmPreChecks
import sys
import logging
from h_litp.litp_rest_client import LitpRestClient
from litp.core.base_plugin_api import BasePluginApi
from litp.core.model_manager import ModelManager
import time
from copy import deepcopy
from multiprocessing.pool import ThreadPool
import textwrap
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


BOUNCE_SLEEP_TIME = 60
BATCH_SLEEP_TIME = 720


class EnmBouncerException(Exception):
    """
    Enm Bouncer failure
    """
    pass


class EnmBouncer(object):
    """
    Provide mechanism to Bounce ENM nodes
    """

    def __init__(self, logger_name='enminst'):
        """
        Initialise LitpRestClient, ModelManager and BasePluginApi
        """
        self.log = logging.getLogger(logger_name)
        self.rest = LitpRestClient()
        self.model_manager = ModelManager()
        self.base_api = BasePluginApi(self.model_manager)
        self.is_virt = EnmPreChecks()
        self.cluster_nodes = self.rest.get_cluster_nodes()
        self.seeds = {}

    def get_sys_bmcs(self):
        """
        Obtain system BMC information from the LITP model

        :return: Collection of nodes / BMC information
        {node : [iLo_ip_address, iLo_username, iLo_password]}
        :rtype: dict
        """
        self.log.info('Get systems BMC information')
        systems = []
        sys_bmc = {}
        path = '/infrastructure/systems'
        items = self.rest.get_items_by_type(path, 'blade', [])
        for item in items:
            systems.append(item['data']['properties']['system_name'])
        for node in systems:
            path = '/infrastructure/systems/{0}_system/bmc'.format(node)
            item = self.rest.get(path, log=False)
            pass_key = item['properties']['password_key']
            username = item['properties']['username']
            raw_password = self.base_api.get_password(pass_key, username)
            sys_bmc[node] = {'iloaddress': item['properties']['ipaddress'],
                           'username': username, 'password': raw_password}
        return sys_bmc

    def get_cluster_seed(self, node):
        """
         Obtain Node count seed from gabconfig

        :param node: Node from cluster to be bounced
        :type String
        :return: seed
        :type int
        """
        seed = 0
        cmd = 'mco rpc enminst cluster_seed -t10 -I ' + node
        out = exec_process(cmd, use_shell=True)
        for line in out.splitlines():
            if 'out:' in line:
                seed = int(line.split(':')[-1].strip())
                return seed
        return seed

    def fetch_cluster_seeds(self, clusters):
        """
         Obtain Node count seed for all clusters

        :param clusters: List of clusters to be bounced
        :type list:
        """
        for cluster in clusters:
            node = self.cluster_nodes[cluster].values(
                        )[0].get_property('hostname')
            if cluster not in self.seeds:
                self.seeds[cluster] = self.get_cluster_seed(node)

    def bounce_nodes(self, nodes, action, timeout=60):
        """
        bounce given nodes
        :param nodes: nodes to be bounced
        :type nodes: List of nodes
        :param action: bounce action
        :type action: 'bounce' | 'on' | 'off'
        """
        sys_bmc = self.get_sys_bmcs()
        bounce_bmc_nodes = {}
        for cluster in self.cluster_nodes.values():
            for node in cluster.values():
                if node.get_property('hostname') in nodes or \
                   node.item_id in nodes:
                    bounce_bmc_nodes[node.item_id] = sys_bmc[node.item_id]

        self._bounce_nodes(bounce_bmc_nodes, action, timeout)

    def bounce_clusters(self, clusters, action, timeout=60, seeded=False):
        """
        bounce given clusters
        :param clusters: clusters to be bounced
        :type clusters: List of clusters
        :param action: bounce action
        :type action: 'bounce' | 'on' | 'off'
        :param timeout: command timeout
        :type int:
        :param seeded: stagger power-on
        :type Boolean:
        """
        sys_bmc = self.get_sys_bmcs()
        all_cluster_nodes = self.rest.get_cluster_nodes()
        clusters_to_bounce = {}
        count = 0

        for bounce_cluster in clusters:
            if bounce_cluster in all_cluster_nodes:
                bounce_bmc_nodes = {}
                for node in all_cluster_nodes[bounce_cluster]:
                    bounce_bmc_nodes[node] = sys_bmc[node]
                    count = count + 1

                if bounce_bmc_nodes:
                    clusters_to_bounce[bounce_cluster] = bounce_bmc_nodes

        if not clusters_to_bounce:
            self.log.info("No Nodes found to bounce")
            return
        self.log.info("Found {0} Nodes to bounce.".format(count))
        for key, value  in clusters_to_bounce.items():
            self.log.info("Processing cluster: {0} \nnodes: {1}".format(
                key, value.keys()))
        if seeded and (action == 'bounce' or action == 'off'):
            self.fetch_cluster_seeds(clusters_to_bounce)

        self._bounce_clusters(clusters_to_bounce, action, timeout, seeded)

    def _bounce_clusters(self, clusters_to_bounce, action, timeout=60,
                         seeded=False):
        """
        process nodes
        :param bounce_bmc_nodes: bmc of nodes to be bounced
        :type dictionary: nodes to bmcs
        :param action: bounce action
        :type action: 'bounce' | 'on' | 'off'
        """
        all_bounce_bmc_nodes = {}
        if action == 'bounce' or action == 'off':
            for cluster, bounce_bmc_nodes in clusters_to_bounce.items():
                all_bounce_bmc_nodes.update(bounce_bmc_nodes)
            self.process_nodes(self.power_off_node, all_bounce_bmc_nodes,
                                timeout)
            if action == 'bounce':
                self.log.info("Sleep for {0} seconds before Powering-on nodes".
                              format(BOUNCE_SLEEP_TIME))
                time.sleep(BOUNCE_SLEEP_TIME)

        all_bounce_bmc_nodes = {}
        if action == 'bounce' or action == 'on':
            # Chassis has issues handling > 1 request at a time to power-on
            if not seeded:
                for cluster, bounce_bmc_nodes in clusters_to_bounce.items():
                    all_bounce_bmc_nodes.update(bounce_bmc_nodes)
                self.process_nodes(self.power_on_node, all_bounce_bmc_nodes,
                                    timeout, num_of_threads=1)
            else:
                # we can tagger the bounce-on by using the cluster's
                #seed threshold value.
                for cluster, bounce_bmc_nodes in clusters_to_bounce.items():
                    seed = self.seeds[cluster]
                    count = 0
                    for key, value in bounce_bmc_nodes.items():
                        count = count + 1
                        all_bounce_bmc_nodes[key] = value
                        del bounce_bmc_nodes[key]
                        if count == seed:
                            break

                self.log.info("Power-on first batch of seeded nodes")
                self.process_nodes(self.power_on_node, all_bounce_bmc_nodes,
                                timeout, num_of_threads=1)

                self.log.info("Power-on second batch of seeded nodes")
                all_bounce_bmc_nodes = {}
                for cluster, bounce_bmc_nodes in clusters_to_bounce.items():
                    all_bounce_bmc_nodes.update(bounce_bmc_nodes)

                if all_bounce_bmc_nodes:
                    self.log.info(
                        "Sleep for {0} seconds before Powering-on second"
                        " batch of seeded nodes".format(BATCH_SLEEP_TIME))
                    time.sleep(BATCH_SLEEP_TIME)
                    self.process_nodes(self.power_on_node,
                                    all_bounce_bmc_nodes,
                                    timeout, num_of_threads=1)
                else:
                    self.log.info("No nodes in second batch to process.")

    def _bounce_nodes(self, bounce_bmc_nodes, action, timeout=60):
        """
        process nodes
        :param bounce_bmc_nodes: bmc of nodes to be bounced
        :type dictionary: nodes to bmcs
        :param action: bounce action
        :type action: 'bounce' | 'on' | 'off'
        """
        if not bounce_bmc_nodes:
            self.log.info("No Nodes found to bounce")
            return
        if action == 'bounce' or action == 'off':
            self.process_nodes(self.power_off_node, bounce_bmc_nodes, timeout)
            if action == 'bounce':
                self.log.info("Sleep for {0} seconds before Powering-on nodes".
                              format(BOUNCE_SLEEP_TIME))
                time.sleep(BOUNCE_SLEEP_TIME)
        if action == 'bounce' or action == 'on':
            # Chassis has issues handling > 1 request at a time to power-on
            self.process_nodes(self.power_on_node, bounce_bmc_nodes,
                                timeout, num_of_threads=1)

    def process_nodes(self, func,  # pylint: disable=R0914,R0912
                       sys_bmcs, timeout=60, num_of_threads=20):
        """
        Process all the managed nodes in threads
        :param func: Function to invoke
        :type func: function()
        :param sys_bmc: nodes ip,user name,password
        :type sys_bmc: dict()
        :param num_of_threads: number of threads in pool
        :type num_of_threads: int
        :param timeout: timeout to wait for Redfish command to succeed
        :type timeout: int
        """
        temp_node_bmc = deepcopy(sys_bmcs)
        tpool = ThreadPool(processes=num_of_threads)
        thread_results = []

        def report(result):
            """
            Add results to list
            :param result: Thread result tuple
            :return:
            """
            thread_results.append(result)

        try:
            for node in temp_node_bmc:
                tpool.apply_async(func, args=(
                    node, temp_node_bmc, timeout), callback=report)
            tpool.close()
            tpool.join()
        except KeyboardInterrupt:
            tpool.terminate()
            raise
        if not thread_results:
            raise EnmBouncerException('Process {0} threads did not return'
                                   ' any result'.format(func))
        all_ok = True
        for success, exception, node in thread_results:
            if not success:
                all_ok = False
                if exception:
                    self.log.error('{0}'.format(exception))
        if not all_ok:
            raise EnmBouncerException('{0} failed'.format(func))

        if len(temp_node_bmc) != len(thread_results):
            node_results = dict(temp_node_bmc)
            for success, exception, node in thread_results:
                del node_results[node]
            for node in node_results:
                self.log.error('Process node thread for {0} did not '
                                  'return any result'.format(node))
            raise EnmBouncerException('All the shutdown nodes threads did not '
                                   'return with result')
        self.log.info('All the nodes are processed successfully')

    def get_vapp_pod_address(self, pod_address="", gateway_name=""):
        """
        Get vapp pod address
        :param pod_address: The vapp pod address
        :type pod_address: string
        :param gateway_name: The name of the vapp gateway
        :type gateway_name: string
        :return: vapp pod address
        :type: string
        """
        url_for_gateway = "https://atvpnspp24.athtem.eei." \
        "ericsson.se/Vms/gateway_hostname"
        gateway_request = requests.get(url_for_gateway)

        if gateway_request.status_code == 200:
            self.log.debug("Getting URL for Vapp Gateway")
            gateway_name = gateway_request.content
        else:
            self.log.error("HTTP {0} - Error Retrieving Vapp Gateway URL"
                .format(gateway_request.status_code))

        # Get the vapp pod address
        pod_address_request = requests.get("https://ci-portal.seli.wh." \
            "rnd.internal.ericsson.com/getSpp/?gateway=" + gateway_name)

        if pod_address_request.status_code == 200:
            self.log.debug("Getting Vapp Pod address")
            pod_address = pod_address_request.content
        else:
            self.log.error("HTTP {0} - Error Retrieving Vapp Pod Address"
                .format(pod_address_request.status_code))

        return pod_address

    def vapp_power_action(self, node, action, pod_address):
        """
        Power on/off nodes on a vapp
        :param node: node name to be shut down or powered on
        :type node: string
        :param action: action to taken on the node
        :type action: string
        :param pod_address: pod address of the vapp
        :type pod_address: string
        :return request object of action
        :type request object

        """
        node_action_request = requests.get(pod_address + "Vms/power" + \
        action + "_api/vm_name:" + node + ".xml")

        if node_action_request.status_code == 200:
            self.log.debug("Powering {0} {1}".format(action, node))
        else:
            self.log.error("HTTP {0} - Error Powering {1} {2}"
                .format(node_action_request.status_code, action, node))

        return node_action_request

    def power_off_node(self,  # pylint: disable=R0915
                       node, node_bmc, timeout):
        """
        Power off the managed node
        :param node: The node to power off
        :type node: string
        :param node_bmc: nodes ip,user name,password
        :type node_bmc: dict()
        :param timeout: timeout to wait for power off command to succeed
        :type timeout: int
        :return: result with node name
        :type: tuple
        """
        try:
            ilo_address = node_bmc[node]['iloaddress']
            username = node_bmc[node]['username']
            password = node_bmc[node]['password']

            virt_env = False

            if self.is_virt.is_virtual_environment():
                virt_env = True
                power_status = True
                pod_address = self.get_vapp_pod_address()
                self.log.debug('Power status of {0}/{1} is {2}'.
                        format(node, ilo_address, power_status))
            else:
                power_status = power_status_rf(ilo_address,
                                                   username,
                                                   password)

                if power_status is None:
                    self.log.error("Error Retrieving {0} power status"
                                       .format(node))
                else:
                    self.log.debug('Power status of {0}/{1} is {2}'.
                                format(node, ilo_address, power_status))

            if power_status:

                self.log.info('Powering off system {0}/{1}, timeout={2} '
                              'seconds'.format(node, ilo_address,
                                                        timeout))

                error = True
                retries = 0
                max_retries = 2
                while retries < max_retries:
                    retries += 1
                    error = False
                    if virt_env:
                        power_off_req = self.vapp_power_action(node, "off",
                            pod_address)

                        if power_off_req.status_code == 200:
                            self.log.debug('Power off {0}/{1}, \
                            attempt {2}/{3}'.
                            format(node, ilo_address, retries, max_retries))
                        else:
                            self.log.error("HTTP {0} - Error Powering" \
                            "off {1}".format(power_off_req.status_code, node))

                    else:
                        output = power_action_rf(ilo_address, username,
                            password, "ForceOff")

                        if output is None:
                            self.log.error("Error Powering off Node {0}"
                                .format(node))
                        else:
                            self.log.debug('Power off {0}/{1}, output={2}'.
                            format(node, ilo_address, output))

                        if 'Power is off' not in output:
                            error = True
                            time.sleep(10)
                        else:
                            error = False
                            break

                if error:
                    msg = 'Failed to power off {0}. {1}'.format(node, output)
                    raise EnmBouncerException(msg)

                timeout_start = time.time()
                while True:
                    if time.time() > timeout_start + timeout:
                        raise EnmBouncerException('Timeout waiting for node'
                              ' {0} to power off'.format(node))

                    if virt_env:
                        power_status = False
                    else:
                        power_status = power_status_rf(ilo_address,
                                                   username,
                                                   password)

                        if power_status is None:
                            self.log.error("Error Retrieving {0} power status"
                                       .format(node))
                        else:
                            self.log.debug('Power status of {0}/{1} is {2}'.
                                    format(node, ilo_address, power_status))
                    if not power_status:
                        break

                    time.sleep(2)
            else:
                self.log.info('System {0} is already powered off'.
                                 format(node))
        except Exception as err:  # pylint: disable=W0703
            self.log.error('System {0} power off failed with error {1}'
                              .format(node, str(err)))
            return False, str(err), node
        return True, None, node

    def power_on_node(self,  # pylint: disable=R0913,R0915
                      node, node_bmc, timeout):
        """
        Power on managed node
        :param node: The node to power up
        :type node: string
        :param node_bmc: nodes ip,user name,password
        :type node_bmc: dict()
        :param timeout: timeout to wait for power on command to succeed
        :type timeout: int
        :return: Result and node name
        :type: tuple
        """
        try:
            ilo_address = node_bmc[node]['iloaddress']
            username = node_bmc[node]['username']
            password = node_bmc[node]['password']
            virt_env = False
            if self.is_virt.is_virtual_environment():
                virt_env = True
                power_status = False
                pod_address = self.get_vapp_pod_address()
                self.log.debug('Power status of {0}/{1} is {2}'.
                        format(node, ilo_address, power_status))

            else:
                power_status = power_status_rf(ilo_address,
                                            username,
                                            password)

                if power_status is None:
                    self.log.error("Error Retrieving {0} power status"
                                       .format(node))
                else:
                    self.log.debug('Power status of {0}/{1} is {2}'.
                        format(node, ilo_address, power_status))

            if power_status:
                self.log.info('System {0} is already powered on.'.
                                     format(node))
                return True, None, node

            self.log.info('Powering on system {0}/{1}, timeout={2} '
                          'seconds'.format(node, ilo_address, timeout))

            retries = 0
            max_retries = 2
            while retries < max_retries:
                retries += 1
                error = False
                self.log.debug('Power on {0}/{1}, attempt {2}/{3}'.
                        format(node, ilo_address, retries, max_retries))

                if virt_env:
                    power_on_req = self.vapp_power_action(node, "on",
                        pod_address)

                    if power_on_req.status_code == 200:
                        self.log.debug('Power on {0}/{1}, \
                        attempt {2}/{3}'.
                        format(node, ilo_address, retries, max_retries))
                    else:
                        self.log.error("HTTP {0} - Error Powering" \
                        "on {1}".format(power_on_req.status_code, node))

                else:
                    output = power_action_rf(ilo_address, username,
                        password, "On")

                    if output is None:
                        self.log.error("Error Powering on Node {0}"
                                .format(node))
                    else:
                        self.log.debug('Power on {0}/{1}, output={2}'.
                        format(node, ilo_address, output))

                    if 'Power is on' not in output and  \
                       'Powering on' not in output:
                        error = True
                        time.sleep(10)
                    else:
                        error = False
                        break

            if error:
                msg = 'Failed to power on {0}. {1}'.format(node, output)
                raise EnmBouncerException(msg)

            timeout_start = time.time()
            while True:
                if time.time() > timeout_start + timeout:
                    raise EnmBouncerException('Timeout waiting for node {0}'
                                           ' to power on'.format(node))
                if virt_env:
                    status = True
                else:
                    status = power_status_rf(ilo_address,
                                                   username,
                                                   password)
                    if status is None:
                        self.log.error("Error Retrieving {0} power status"
                                       .format(node))
                    else:
                        self.log.debug('Power status of {0}/{1} is {2}'.
                                format(node, ilo_address, status))
                if status:
                    break

                time.sleep(2)
        except Exception as err:  # pylint: disable=W0703
            self.log.error('System {0} power on failed with error {1}'
                              ''.format(node, str(err)))
            return False, str(err), node
        return True, None, node


def power_status_rf(ilo_address, username, password):
    """

    Power Status of a node
    :param ilo_address: ilo address of the node
    :type ilo_address: string
    :param username: ilo username for the node
    :type username: string
    :param password: ilo password of the node
    :type password: string
    :return: True or False
    :type: boolean

    """
    url_start = "https://"
    response = requests.get(url_start + ilo_address + "/redfish/v1/Systems/1",
        verify=False, auth=(username, password))
    if response.status_code == 200:
        if response.json()[u'PowerState'] == "On":
            return True

        if response.json()[u'PowerState'] == "Off":
            return False
    else:
        return None


def power_action_rf(ilo_address, username, password, power_command):
    """
    Power On a node using Redfish API cal;
    :param ilo_address: ilo address of the node
    :type ilo_address: string
    :param username: ilo username for the node
    :type username: string
    :param password: ilo password of the node
    :type password: string
    :param power_command: Command to performed on the node
    :type power_command: string
    :return:
    :type: string
    """
    on_dict = {"On": "Powering on",
               "ForceOff": "Powering off"
              }

    already_on_dict = {"On": "Power is on",
                       "ForceOff": "Power is off"
                      }

    url_start = "https://"
    body = {"ResetType": power_command}
    redfish_url = "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/"
    response = requests.post(url_start + ilo_address + redfish_url,
    verify=False, json=body, auth=(username, password))

    if response.status_code == 200:
        if response.json().get('Messages'):
            ilo4_response = response.json()[u'Messages'][0]['MessageID']

            if ilo4_response.startswith('Base') \
                and ilo4_response.endswith('Success'):
                return on_dict[power_command]

        if response.json()['error']['@Message.ExtendedInfo'][0]['MessageId']:
            ilo5_response = response.json(
                )['error']['@Message.ExtendedInfo'][0]['MessageId']

            if ilo5_response.startswith('Base') \
                and ilo5_response.endswith('Success'):
                return on_dict[power_command]

    if response.status_code == 400:
        if response.json().get('Messages'):
            ilo4_response = response.json()[u'Messages'][0]['MessageArgs'][0]

            if ilo4_response == already_on_dict[power_command]:
                return already_on_dict[power_command]

        if response.json()['error']['@Message.ExtendedInfo'][0]['MessageArgs']:
            ilo5_response = response.json(
                )['error']['@Message.ExtendedInfo'][0]['MessageArgs'][0]

            if ilo5_response == already_on_dict[power_command]:
                return already_on_dict[power_command]


def create_argument_parser():
    """
    Creates and configures parser to process command line arguments
    :return: argument parser instance
    :rtype ArgumentParser
    """

    enm_bouncer_epilog = textwrap.dedent('''
Examples:
Bounce the svc_cluster and scp_cluster
# %(prog)s --action bounce\
 --clusters svc_cluster scp_cluster

Power Off the nodes with hostnames node1 and node2
# %(prog)s --action off\
 --nodes node1 node2
''')

    parser = ArgumentParser(prog="enm_bouncer.py",
                        description='power off/on clusters or nodes',
                        formatter_class=RawDescriptionHelpFormatter,
                        epilog=enm_bouncer_epilog)

    group1 = parser.add_mutually_exclusive_group(required=True)
    group1.add_argument('--clusters', metavar=('cluster'), nargs='+',
                    default=[],
                    help="Space separated list of cluster item_ids\
                    to power off/on e.g svc-cluster")
    group1.add_argument('--nodes', metavar=('node'), nargs='+',
                    default=[],
                    help="Space separated list of hostnames\
                    to power off/on")

    parser.add_argument('--action', dest='action',
                    choices=['bounce', 'on', 'off'],
                    help="enm_bouncer action i.e.\n"\
                    "'bounce' will turn all instances off then all on.\n"\
                    "'on' will just turn all instances on.\n" \
                    "'off' will just turn all instances off.")

    parser.add_argument('--seeded', dest='seeded',
                           default=False,
                           required=False,
                           action='store_true',
                           help="Use vcs_seed_threshold property "\
                    "of vcs-cluster item to stagger the cluster power-on")

    parser.add_argument('--timeout', dest='timeout',
                    type=int,
                    help="Time in seconds, to wait for power status change",
                    default=60)

    return parser


def bounce(options):
    """
    Execute bounce operation depending on the arguments given.
    :param options: arg options
    :type args: args
    """
    logger = init_enminst_logging()
    try:
        log_level = get_env_var('LOG_LEVEL')
        set_logging_level(logger, log_level)
    except KeyError:
        set_logging_level(logger, 'DEBUG')

    logger.info('Beginning ENM bouncer')

    bouncer = EnmBouncer()

    if options.clusters:
        bouncer.bounce_clusters(options.clusters, options.action,
                                 options.timeout, options.seeded)
    if options.nodes:
        bouncer.bounce_nodes(options.nodes, options.action, options.timeout)


def main(args):
    """
    Main function for bounce operation..
    :param args: Main CLI args
    :type args: list(str)
    """
    arg_parser = create_argument_parser()
    options = arg_parser.parse_args(args)
    try:
        bounce(options)
    except SystemExit as error:
        if error.args[0] == ExitCodes.INVALID_USAGE:
            arg_parser.print_help()
        else:
            raise

if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
