"""
SED functionality specific to a chassis expansion
"""
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import logging

from h_util.h_utils import Sed
from h_expansion.expansion_utils import is_valid_ip_address,\
    OnboardAdministratorHandler

LOGGER = logging.getLogger("enminst")


class ExpansionSedHandler(object):
    """
    Class to retrieve required SED entries from the SED
    """
    def __init__(self, target_sed):
        self.sed = Sed(target_sed)

    def get_sed_entry(self, sed_param):
        """
        Function that searches the SED for a specific parameter and returns
        its value if found.
        :param sed_param: The SED parameter to search for.
        :return: The value of the SED parameter.
        """
        try:
            sed_value = self.sed[sed_param]
        except KeyError:
            LOGGER.error('Failed to get parameter {0} from SED'
                         .format(sed_param))
            raise

        if not sed_value:
            LOGGER.error('No value found for SED parameter {0}'
                         .format(sed_param))
            raise Exception('No value found for SED parameter')

        return sed_value

    def get_sed_entries_for_node(self, peer_node):
        """
        Function that converts the peer node name to the SED naming convention
        and gets the associated entries in the SED.
        :param peer_node: The peer node name, e.g. svc-1.
        :return: Dictionary of SED values for the peer node.
        """
        node_name_details = peer_node.split('-')

        sed_node_name = '{clust}_node{num}'.format(clust=node_name_details[0],
                                                   num=node_name_details[1])

        node_sed_entries = self.sed.get_node_config(sed_node_name)

        if not node_sed_entries:
            LOGGER.error('No SED entries found for node {0}'.format(peer_node))
            raise Exception('Failed to find SED entries for node {0}'
                            .format(peer_node))

        return node_sed_entries

    def get_enclosure_oa_info(self, enclosure):
        """
        Function that gets the Onboard Administrator login parameters for
        a specific enclosure.
        :param enclosure: The enclosure number, e.g. enclosure1.
        :return: An OA object containing IP addresses, username and password.
        """
        enclosure_info = self.sed.get_node_config(enclosure)

        if not enclosure_info:
            LOGGER.error('Failed to get {0} information from the SED'
                         .format(enclosure_info))
            raise Exception('Failed to get enclosure information from SED')

        oa_ip1 = enclosure_info.get('OAIP1')
        oa_ip2 = enclosure_info.get('OAIP2')
        oa_username = enclosure_info.get('username')
        oa_password = enclosure_info.get('password')

        if None in (oa_ip1, oa_ip2, oa_username, oa_password):
            LOGGER.error('Failed to get {0} OA details from the SED'
                         .format(enclosure))
            raise Exception('Failed to get {0} OA details from the SED'
                            .format(enclosure))

        return OnboardAdministratorHandler(oa_ip1,
                                           oa_ip2,
                                           oa_username,
                                           oa_password)

    def get_ilo_ip_address_for_node(self, peer_node):
        """
        Function that gets the iLO IP address from the SED for a particular
        peer node.
        :param peer_node: The peer node name, e.g. svc-1.
        :return: The iLO IP entry for that node in the SED.
        """
        LOGGER.info('Getting iLO IP address for node {0}'.format(peer_node))

        node_sed_entries = self.get_sed_entries_for_node(peer_node)
        sed_ilo_ip = node_sed_entries.get('ilo_IP')

        if not sed_ilo_ip:
            LOGGER.error('No iLO IP found in the SED for node %s', peer_node)
            raise Exception('Failed to find iLO IP in SED')

        if not is_valid_ip_address(sed_ilo_ip):
            LOGGER.error('%s iLO IP %s is not a valid IP Address',
                         peer_node, sed_ilo_ip)
            raise Exception('iLO IP Address {0} is invalid'.format(sed_ilo_ip))

        return sed_ilo_ip

    def get_peer_node_ilo_ip_addresses(self, peer_nodes):
        """
        Function that creates a dictionary of peer nodes to iLO IP addresses.
        :param peer_nodes: List of peer nodes in the deployment.
        :return: Dictionary with the peer node name as key and the
        iLO IP as value.
        """
        peer_node_ilo_dict = {}

        for node in peer_nodes:
            dest_ilo = self.get_ilo_ip_address_for_node(node)
            peer_node_ilo_dict[node] = dest_ilo

        return peer_node_ilo_dict

    def get_peer_node_serial_number(self, peer_node):
        """
        Function that gets the serial number of a peer node from the SED.
        :param peer_node: The peer node name, e.g. svc-1.
        :return: The serial number for that node in the SED.
        """
        node_sed_entries = self.get_sed_entries_for_node(peer_node)
        sed_serial = node_sed_entries.get('serial')

        if not sed_serial:
            LOGGER.error('No serial number found in the SED for node {0}'
                         .format(peer_node))
            raise Exception('Failed to find serial number in SED')

        return sed_serial

    def get_peer_serials_for_nodes(self, peer_nodes):
        """
        Function that creates a dictionary of peer nodes to serial number.
        :param peer_nodes: List of peer nodes in the deployment.
        :return: Dictionary with the peer node name as key and the
        serial number as value.
        """
        peer_node_serial_dict = {}

        for node in peer_nodes:
            serial_no = self.get_peer_node_serial_number(node)
            peer_node_serial_dict[node] = serial_no

        return peer_node_serial_dict
