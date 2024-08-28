"""
Provided LLT Healthcheck information.
Low Latency Transfer (LLT) and Low Priority (LPR)
network interfaces are reported upon.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import re
from h_puppet.mco_agents import LltStatAgent
from h_util.h_utils import ExitCodes
from h_logging.enminst_logger import init_enminst_logging

NIC_STATUS_HEALTHY = 'UP'


class LltHealthCheck(object):   # pylint: disable=R0903
    """
    Class to handle fetching & processing lltstat data
    """

    def __init__(self):
        """
        Main Health Checker constructor.
        """
        self.logger = init_enminst_logging()

    class LltNic(object):  # pylint: disable=R0903
        """
        Class to manage processed network-interface lltstat data.
        """

        def __init__(self, name, status, mac):
            """
            Constructor
            :param name: NIC name string
            :param status: NIC status string
            :param mac: Optional NIC MAC string
            """
            object.__init__(self)
            self.name = name
            self.status = status
            self.mac = mac

        def is_healthy(self):
            """
            Boolean method to determine if the NIC is healthy.
            :return: True if NIC is considered healthy, False otherwise.
            """
            return self.status == NIC_STATUS_HEALTHY

        def __repr__(self):
            """
            Represent a LltNic instance.
            :return: A string representation of a LltNic object.
            """
            txt = "NIC:%s Status:%s" % \
                  (self.name, self.status)

            if self.mac:
                txt += " MAC: %s" % self.mac
            txt += "\n"
            return txt

    class LltNode(object):  # pylint: disable=R0903
        """
        Class to manage processed node lltstat data.
        """
        def __init__(self, hostname, llt_nics):
            """
            Constructor
            :param hostname: Node hostname.
            :param llt_nics: List of LltNic instances.
            """
            object.__init__(self)
            self.hostname = hostname
            self.llt_nics = llt_nics

        def is_healthy(self):
            """
            Boolean method to determine if all the NICs are healthy.
            :return: True if all NICs are healthy, False otherwise.
            """
            return not self.llt_nics == [] and \
                   all(nic.is_healthy() for nic in self.llt_nics)

        def __repr__(self):
            txt = "  Hostname %s\n" % self.hostname
            for nic in self.llt_nics:
                txt += "    %s" % nic
            return txt

    class LltClusterReport(object):  # pylint: disable=R0903
        """
        Class to handle processing cluster lltstat report data.
        """
        GRP_HOSTNAME = 'hostname'
        GRP_NIC = 'nic'
        GRP_STATUS = 'status'
        GRP_MAC = 'mac'
        NODE_PATTERN = r'^ *\*{0,1} *[0-9]+ +(?P<%s>[^\s]+) +OPEN *$' % \
                       GRP_HOSTNAME
        NIC_PATTERN = r'^ *(?P<%s>[^\s]+) +(?P<%s>%s|DOWN)(?P<%s>.*)$' % \
                      (GRP_NIC, GRP_STATUS, NIC_STATUS_HEALTHY, GRP_MAC)

        def __init__(self, hostname, llt_cluster_data, llt_deployment):
            """
            Constructor
            :param hostname: Hostname of Node providing lltstat report.
            :param llt_cluster_data: raw multiline lltstat cluster report.
            :param llt_deployment: LltDeployment instance.
            """
            object.__init__(self)
            self.llt_cluster_data = llt_cluster_data
            self.llt_nodes = []

            self.llt_cluster_name = \
                     llt_deployment.get_cluster_name_for_host(hostname)

            self.node_regexp = \
                     re.compile(LltHealthCheck.LltClusterReport.NODE_PATTERN)
            self.nic_regexp = \
                     re.compile(LltHealthCheck.LltClusterReport.NIC_PATTERN)

            self.process_cluster_data()

        def __eq__(self, other):
            """
            Check this instance for equality with another.
            :param other: Other LltClusterReport instance.
            :return: True if instances are equal, False otherwise.
            """
            # TORF-334377 - Compare cluster data rather than cluster name
            # for a more robust comparison.
            # Replace * with a space for comparison.
            # * in the output represents the node that the
            # output is gathered from which we can disregard.
            return self.llt_cluster_data.replace('*', ' ') == \
                   other.llt_cluster_data.replace('*', ' ')

        def is_healthy(self):
            """
            Boolean method to determine if all the llt_nodes are healthy.
            :return: True if all llt_nodes are healthy, False otherwise.
            """
            return all(node.is_healthy() for node in self.llt_nodes)

        def add_lltnode(self, hostname, llt_node_nics):
            """
            Add a new LltNode instance.
            :param hostname: New lltnode host name.
            :param llt_node_nics: List of LltNics.
            :return: None
            """
            if hostname and llt_node_nics:
                self.llt_nodes.append(LltHealthCheck.LltNode(hostname,
                                                             llt_node_nics))

        @staticmethod
        def get_tokens_from_line(line, regexp, group_names):
            """
            Match a line string to a regular expression
            and extract group values.
            :param line: Line string to match.
            :param regexp: regular-expression instance.
            :param group_names: expected groups keys in matched regexp.
            :return: List of group values.
            """

            group_values = []
            match = regexp.search(line)
            if match:
                parts = match.groupdict()
                if parts:
                    for group_key in group_names:
                        if group_key in parts.keys():
                            group_value = parts[group_key].strip()
                        else:
                            group_value = ''
                        group_values.append(group_value)

            return group_values

        def process_cluster_data(self):
            """
            Parse/process the lltstat data reported by a node.
            """

            handling_new_node = False
            current_hostname = None
            node_nics = []

            if not self.llt_cluster_data:
                return

            for line in self.llt_cluster_data.splitlines():
                line = line.strip()

                matches = LltHealthCheck.LltClusterReport.get_tokens_from_line(
                            line, self.node_regexp,
                            [LltHealthCheck.LltClusterReport.GRP_HOSTNAME])
                if matches and len(matches) == 1:
                    if handling_new_node:
                        self.add_lltnode(current_hostname, node_nics)

                    handling_new_node = True
                    current_hostname = matches[0]
                    node_nics = []
                else:
                    matches = \
                     LltHealthCheck.LltClusterReport.get_tokens_from_line(
                                    line, self.nic_regexp,
                                  [LltHealthCheck.LltClusterReport.GRP_NIC,
                                   LltHealthCheck.LltClusterReport.GRP_STATUS,
                                   LltHealthCheck.LltClusterReport.GRP_MAC])
                    if matches and len(matches) == 3:
                        if handling_new_node:
                            node_nics.append(LltHealthCheck.LltNic(matches[0],
                                                                   matches[1],
                                                                   matches[2]))

            if handling_new_node:
                self.add_lltnode(current_hostname, node_nics)
                handling_new_node = False
                current_hostname = None
                node_nics = []

        def __repr__(self):
            txt = "Cluster report for %s\n" % self.llt_cluster_name
            for node in self.llt_nodes:
                txt += "%s" % node
            return txt

    class LltDeployment(object):  # pylint: disable=R0903
        """
        Class to handle processing deployment lltstat data.
        """
        def __init__(self, mco_agent):
            """
            Constructor.
            :param mco_agent: MCO agent instance on which to run actions.
            """
            object.__init__(self)
            self.mco_agent = mco_agent
            self.llt_cluster_reports = []
            self.llt_cluster_names = {}

            self.init_cluster_names()
            self.init_deployment_data()

        def init_cluster_names(self):
            """
            Initialize cluster names/IDs from 'haclus_list' MCO action.
            return: None.
            """

            cluster_name_data = self.mco_agent.get_cluster_list()

            for hostname, cluster_name in cluster_name_data.items():
                if cluster_name:
                    self.llt_cluster_names[hostname] = cluster_name.strip()

        def get_cluster_name_for_host(self, hostname):
            """
            Get a cluster name for a hostname
            :param hostname: reporting cluster host name
            :return: String cluster name
            """
            if hostname in self.llt_cluster_names.keys():
                return self.llt_cluster_names[hostname]

            return '<unknown>'

        def init_deployment_data(self):
            """
            Initialize and process full deployment data
            return: None
            """
            deployment_data = self.mco_agent.get_lltstat_data()

            if deployment_data:
                self.process_deployment_data(deployment_data)

        def add_cluster_report(self, cluster_report, add_duplicates=False):
            """
            Add a cluster_report to the current list of llt_cluster_reports.
            :param cluster_report: LltClusterReport instance.
            :param add_duplicates: Boolean indicating if duplicate
            cluster reports should be added to the list.
            :return: None.
            """
            if add_duplicates:
                self.llt_cluster_reports.append(cluster_report)
            else:
                if cluster_report not in self.llt_cluster_reports:
                    self.llt_cluster_reports.append(cluster_report)

        def process_deployment_data(self, deployment_data):
            """
            Process full lltstat deployment data.
            :param deployment_data: Full lltstat MCO output.
            :return: None.
            """

            for hostname, llt_cluster_data in deployment_data.items():
                if llt_cluster_data:
                    report = LltHealthCheck.LltClusterReport(hostname,
                                                        llt_cluster_data, self)
                    self.add_cluster_report(report)

        def is_healthy(self):
            """
            Boolean method to determine if the deployment is healthy.
            :return: True if the deployment is healthy, False otherwise.
            """

            clusters_with_reports = [cluster_report.llt_cluster_name
                             for cluster_report in self.llt_cluster_reports]

            for cluster_name in self.llt_cluster_names.values():
                if cluster_name not in clusters_with_reports:
                    return False

            return not self.llt_cluster_reports == [] and \
                all(report.is_healthy() for report in self.llt_cluster_reports)

        def __repr__(self):
            txt = ''
            for report in self.llt_cluster_reports:
                txt += "%s" % report
            return txt

    def verify_health(self, verbose=False):
        """
        Verify the health of the LLT heartbeat network interfaces.
        :param verbose: Turn on verbose logging.
        :return: None.
        """

        if verbose:
            self.logger.debug("Verifying LLT heartbeat network interfaces")

        llt_deployment = LltHealthCheck.LltDeployment(LltStatAgent())

        msg = "Deployment:\n%s" % llt_deployment
        self.logger.debug(msg)
        if verbose:
            print msg

        if not llt_deployment.is_healthy():
            raise SystemExit(ExitCodes.ERROR)

        return True
