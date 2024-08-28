# pylint: disable=W1401
"""
This class identifies a node that is in a vcs EXITED state within the
streaming clusters (str_cluster, ebs_cluster, esn_cluster, asr_cluster)
and runs gabconfig -x on those nodes. This gabconfig option is the
'Seed control port' option. This option affords protection from pre-existing
network partitions. The control port (port a) propagates the  seed to all
configured systems. This is done to allow streaming racks to still form a
cluster during RHEL7 uplift Rollback, and not rely on the minimum
system_count set in /etc/gabtab
"""
##############################################################################
# COPYRIGHT Ericsson AB 2021
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import logging
import re
import os

from h_logging.enminst_logger import init_enminst_logging
from h_snapshots.lvm_snapshot import LVMManager
from h_util.h_utils import exec_process
from h_vcs.vcs_cli import Vcs
from h_vcs.vcs_utils import filter_systems_by_state, VcsStates
from h_snapshots.lvm_snapshot import RHEL7_NODE_LIST_FILE
from h_util.h_utils import ExitCodes


class GabconfigX(object):
    """
    GabconfigX
    """
    def __init__(self):
        self.log = logging.getLogger('enminst')

    def set_cluster_seed_control(self, node):
        """
         Run the gabconfig command on relevant nodes using mco

        :param node: Node from cluster to run command on
        :type String
        """
        cmd = 'mco rpc enminst set_cluster_seed_control -I ' + node
        self.log.info("Running [{0}]".format(cmd))
        out = exec_process(cmd, use_shell=True)
        self.log.info(out)

    def get_single_running_node(self, cluster):
        """
        Find a single hostname in a cluster that is in vcs state EXITED

        :param cluster: cluster to find hostname
        :type String
        :return: A hostname from the cluster
        :rtype: String
        """
        vcs = Vcs()
        _, rows = vcs.get_cluster_system_status(cluster_filter=cluster)
        rows = filter_systems_by_state(rows, state_filter=VcsStates.EXITED)

        if rows == []:
            self.log.info("Cluster {0} does not exist in this deployment."
                          " Skipping".format(cluster))
            return None
        else:
            hostname = rows[0]['System']
            self.log.info("Cluster {0} has node {1} in {2} state"
                          .format(cluster, hostname, VcsStates.EXITED))
            return hostname


def main():
    """
    Main function
    This function will only allow the script to run if the RHEL7 node list file
    exists, otherwise it will exit 0 as it will need to run in CI environments
    for non rhel uplift related rollbacks. This function searches for streaming
    racks in the deployment and sets the cluster seed control on the relevant
    ones.
    :return:
    """

    gabx = GabconfigX()
    if os.path.isfile(RHEL7_NODE_LIST_FILE):
        lvm = LVMManager()
        local_disk_nodes = lvm.get_nodes_using_local_storage(ignore_states=[])
        streaming_clusters = []
        for rack in local_disk_nodes.keys():
            match = re.search('/deployments/enm/clusters/(\S+)/nodes.*',
                              rack.path)
            streaming_clusters.append(match.group(1))

        streaming_clusters = list(set(streaming_clusters))

        init_enminst_logging()

        for cluster in streaming_clusters:
            running_node = gabx.get_single_running_node(cluster)
            if running_node != None:
                gabx.set_cluster_seed_control(running_node)
    else:
        gabx.log.info('Rhel7 node list file doesnt exist ... Exiting')
        raise SystemExit(ExitCodes.OK)


if __name__ == '__main__':
    main()
