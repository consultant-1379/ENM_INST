"""
Health checks for consul cluster
"""
##############################################################################
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from urllib2 import urlopen, URLError, HTTPError
from h_util.h_utils import ExitCodes
from h_logging.enminst_logger import init_enminst_logging
from h_puppet.mco_agents import EnminstAgent
from h_litp.litp_rest_client import LitpRestClient
import json

SVC_NODES = '/deployments/enm/clusters/svc_cluster/nodes'
CONFIG_FILE = '/etc/consul.d/agent/config.json'


class ConsulHC(object):
    """
    Class containing health checks for consul cluster
    """
    def __init__(self, verbose=False):
        self.consul_members = 'http://kvstore:8500/v1/agent/members'
        self.consul_leader = 'http://kvstore:8500/v1/status/leader'
        self.consul_members_old = 'http://localhost:8500/v1/agent/members'
        self.consul_leader_old = 'http://localhost:8500/v1/status/leader'

        self.logger = init_enminst_logging(logger_name='enmhealthcheck')
        self.enminst_agent = EnminstAgent()
        self.verbose = verbose

    def check_consul_members(self):
        """
        Checks consul members status is alive(1)
        """
        retry_count = 3
        retries = 0
        json_data = self.consul_get_url_data(self.consul_members,
                                             self.consul_members_old)
        consul_dict = dict()
        failed_list = []

        for i in range(0, len(json_data)):
            if json_data[i]['Tags'].get('port'):
                consul_dict[json_data[i]['Name']] = [json_data[i]['Status']]

        self.check_members_count(consul_dict, CONFIG_FILE)
        litp_rest_client = LitpRestClient()
        svc_nodes = litp_rest_client.get_items_by_type(SVC_NODES, 'node', [])
        consul_hostnames = [node['data']['properties']['hostname'] for node in
                         svc_nodes]
        consul_hostnames.append(litp_rest_client.get_lms().get_property(
                                                            'hostname'))
        for agent, status in consul_dict.items():
            if agent in consul_hostnames and status != [1]:
                failed_list.append(agent)

        while failed_list and retries < retry_count:
            retries += 1
            self.logger.info('Restarting consul agents for: {0}. '
                             'Retry attempt {1} of 3.'
                             .format(', '.join(failed_list), retries))
            for rpc_hosts in list(failed_list):
                rpc_results = self.enminst_agent.consul_service_restart(
                                            [rpc_hosts])
                if 'err' in rpc_results.keys() \
                        or len(rpc_results[rpc_hosts]) > 0 \
                        and 'errors' in rpc_results[rpc_hosts].keys():
                    self.logger.info("Failed to restart consul "
                                     "service on {0}: {1}"
                                     .format(rpc_hosts,
                                     rpc_results['err'] if 'err'
                                     in rpc_results.keys()
                                     else rpc_results[rpc_hosts]['errors']))
                elif rpc_hosts in failed_list:
                    #If success remove instance from failed_list
                    failed_list.remove(rpc_hosts)
                    self.logger.info("Succesfully restarted consul on {0}"
                                     .format(rpc_hosts))
        if failed_list:
            if self.verbose:
                self.logger.info('Following consul agents are not alive: '
                                 ' "{0}"'.format(', '.join(failed_list)))
            raise SystemExit(ExitCodes.ERROR)

    def check_consul_leader(self):
        """
        Checks that a consul leader exists.
        """
        json_data = self.consul_get_url_data(self.consul_leader,
                    self.consul_leader_old)

        if not json_data:
            if self.verbose:
                self.logger.info('No consul leader exists')
            raise SystemExit(ExitCodes.ERROR)

    def consul_get_url_data(self, url, url_old):
        """
        Gets data from provided url
        :param url
        :type str
        :return json data
        :type json object
        """
        try:
            response = urlopen(url)
        except (HTTPError, URLError) as ex:
            try:
                response = urlopen(url_old)
            except (HTTPError, URLError) as ex:
                if self.verbose:
                    self.logger.info('Request "{1}" failed with Error "{1}"'.
                        format(str(ex), url))
                raise SystemExit(ExitCodes.ERROR)
        else:
            retcode = response.getcode()
            if retcode != 200:
                if self.verbose:
                    self.logger.info('Request "{1}" failed with return code '
                                     '"{1}"'.format(retcode, url))
                raise SystemExit(ExitCodes.ERROR)
        return json.load(response)

    def check_members_count(self, members_dict, cfg_file):
        """
        Checks that the number of nodes in kv store matches
        the expected number of nodes in config file
        :param members_dict
        :type dictionary
        :param cfg_file
        :type string
        """
        config_file = open(cfg_file)
        config_data = json.load(config_file)
        config_file.close()
        kv_node_count = len(members_dict)
        expected_node_count = config_data["bootstrap_expect"]
        if kv_node_count < expected_node_count:
            if self.verbose:
                self.logger.info('Consul cluster size "{0}" is running '\
                                'outside the expected number of nodes "{1}"'
                                .format(kv_node_count, expected_node_count))
            raise SystemExit(ExitCodes.ERROR)

    def healthcheck_consul(self):
        """
        Runs Consul healthchecks
        """
        self.check_consul_leader()
        self.check_consul_members()
