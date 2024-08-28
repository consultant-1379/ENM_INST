"""
This class allows a user to reinstall streaming rack hardware that is listed in
/ericsson/custom/rhel7_node_list_file.txt. This is for the purposes of
Snapshot Rollback after a failed RHEL7 uplift. Any streaming racks that
attempted to uplift have to be reinstalled using this script.
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
import os

from h_util.h_utils import exec_process, keyboard_interruptable, \
                            get_enable_cron_on_expiry_cmd, \
                            ExitCodes, cmd_DISABLE_CRON_ON_EXPIRY
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpException
from h_logging.enminst_logger import init_enminst_logging
import logging
from h_snapshots.lvm_snapshot import RHEL7_NODE_LIST_FILE
from os.path import exists
from simplejson import load
from enm_upgrade_prechecks import EnmPreChecks


class ReinstallPeerNodes(object):
    """
    ReinstallPeerNodes
    """
    RHEL7_SYSTEM_AUTH = os.path.join(os.sep, 'etc', 'pam.d', 'password-auth')

    def __init__(self):
        self.log = logging.getLogger('enminst')
        self.litp = LitpRestClient()

    def update_kickstart_template(self, command):
        """
        Update kickstart.erb to prevent cron job failures due to password
        expiry. Required to keep cron jobs working during reinstall
        :param command: The command to perform on the kickstart.erb file.
        :type action: String
        :return: None
        """
        try:
            exec_process(command, use_shell=True)
        except IOError as error:
            self.log.exception('Error updating kickstart template using '
                                   'command {0}'.format(command))
            raise SystemExit(error)

    def reinstall(self):
        """
        Reads the contents of rhel7_node_list_file.txt, restores those nodes to
        Initial in the model, and runs Create/Run plan.
        """

        precheck = EnmPreChecks()
        precheck.check_litp_model_synchronized()

        self.log.info('This is a RHEL migration Rollback')
        if os.path.isfile(RHEL7_NODE_LIST_FILE):
            self.log.info('Reading the contents of {0}'
                          .format(RHEL7_NODE_LIST_FILE))
            rhel7_node_list = self.\
                load_list_from_file(RHEL7_NODE_LIST_FILE)

            try:
                node_details = self.get_hostname_details(rhel7_node_list)
                self.set_nodes_to_initial(node_details)
                self.update_kickstart_template(
                    get_enable_cron_on_expiry_cmd(
                    ReinstallPeerNodes.RHEL7_SYSTEM_AUTH))
                self.create_run_plan()
                self.update_kickstart_template(
                    cmd_DISABLE_CRON_ON_EXPIRY)
            except LitpException as err:
                self.log.exception("Failed to execute create_run_plan: "
                                   "{0}".format(err))
                raise SystemExit(ExitCodes.ERROR)
        else:
            self.log.error('{0} doesnt exist ... Exiting'
                           .format(RHEL7_NODE_LIST_FILE))
            raise SystemExit(ExitCodes.ERROR)

    def get_hostname_details(self, node_list):
        """
        Get the node name and cluster from node_list passed in

        :param node_list: A list of streaming racks to be reinstalled -
        i.e. ['ieatebs1', 'ieatebs2']
        :type list
        :return: A Dictionary of node name and cluster -
        i.e. {'str-1':'str_cluster', 'str-2':'str_cluster'}
        :rtype: dict
        """
        all_cluster_nodes = self.litp.get_cluster_nodes()
        hostname_details = {}

        for hostname in node_list:
            for cluster, nodes in all_cluster_nodes.items():
                for node, details in nodes.items():
                    if hostname == details.get_property('hostname'):
                        hostname_details[node] = cluster
        return hostname_details

    def set_nodes_to_initial(self, hostname_details):
        """
        Set the streaming racks to Initial in the litp model for the
        details passed in.

        :param hostname_details: A dict of streaming racks to be reinstalled
        - i.e. {'str-1':'str_cluster', 'str-2':'str_cluster'}
        :type dict
        """
        for node, cluster in hostname_details.items():
            node_path = '/deployments/enm/clusters/{0}/nodes/{1}/' \
                .format(cluster, node)
            self.log.info('Running command: litp prepare_restore -p {0}'
                          .format(node_path))
            prepare_restore = ['/usr/bin/litp', 'prepare_restore', '-p',
                               node_path]

            try:
                exec_process(prepare_restore)
            except IOError as error:
                self.log.exception('An error occurred setting {0} to '
                                   'state \'Initial\''.format(node))
                raise SystemExit(error)

    def create_run_plan(self):
        """
        Creates and Runs a litp plan based on the tasks generated.
        """
        try:
            self.litp.create_plan('plan')
            self.litp.set_plan_state('plan', 'running')
            self.litp.monitor_plan('plan')
        except LitpException as error:
            self.log.error('Litp Create/Run plan failed ...')
            raise SystemExit(error)

    @staticmethod
    def load_list_from_file(filename):
        """
        Load a file to a list
        :param filename: the file to load
        Load list of streaming racks from a file to be reinstalled
        :returns: list of streaming racks that attempted RHEL7 uplift
        :rtype: list
        """

        if exists(filename):
            with open(filename, 'r') as _reader:
                str_list = load(_reader)
            return str_list
        else:
            return None


def reinstall_peer_nodes_interrupt():
    """
    Show a specific message if the script gets interrupted by a CTRL-C

    """
    logger = logging.getLogger('enminst')()
    logger.trace.info('Streaming rack reinstall was interrupted, '
                      'Please re-run again to ensure everything is completed')


@keyboard_interruptable(callback=reinstall_peer_nodes_interrupt)
def main():
    """
    Main function
    :return:
    """
    init_enminst_logging()
    rpn = ReinstallPeerNodes()
    rpn.reinstall()
    if os.path.isfile(RHEL7_NODE_LIST_FILE):
        os.remove(RHEL7_NODE_LIST_FILE)


if __name__ == '__main__':
    main()
