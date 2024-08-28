import os
from mock import patch, MagicMock
from unittest2 import TestCase

from h_rhel7.rh7_pre_upgrade import ITEM_TYPE_VCS_CLUSTERED_SERVICE, \
                                    ITEM_TYPE_VIP, pre_rollover_changes
from h_litp.litp_rest_client import LitpRestClient, LitpException


class TestRh7PreUpgrade(TestCase):

    @patch('h_rhel7.rh7_pre_upgrade.create_item')
    @patch('h_rhel7.rh7_pre_upgrade.LitpRestClient.exists')
    @patch('h_rhel7.rh7_pre_upgrade.LitpRestClient.get')
    @patch('h_rhel7.rh7_pre_upgrade._get_parent_path')
    @patch('h_rhel7.rh7_pre_upgrade.get_xml_element_properties')
    @patch('h_rhel7.rh7_pre_upgrade.get_model_path')
    @patch('h_rhel7.rh7_pre_upgrade.xpath')
    @patch('h_rhel7.rh7_pre_upgrade.load_xml')
    def test_pre_rollover_changes(self, mock_load_xml, mock_xpath,
            mock_get_model_path, mock_get_props, mock_get_parent_path,
            mock_litp_get, mock_litp_exists, mock_create_item):
        """
        Test cases:
        """
        def mock_xpath_func(root, change_type):
            if change_type in [ITEM_TYPE_VIP,
                               ITEM_TYPE_VCS_CLUSTERED_SERVICE]:
                return [MagicMock(type=change_type)] * 3
            else:
                return []

        def mock_create_item_func(node, change_type, model_path):
            return ('litp create -t {0} -p {1}'.format(change_type,
                                                       model_path), None)

        def mock_get_props_func(node):
            return (next(vip_properties) if node.type == ITEM_TYPE_VIP
                    else next(cs_properties))


        def mock_litp_get_func(model_path, log):
            properties = (next(vip_properties) if model_path.endswith('vip')
                          else next(cs_properties))
            if properties == 'LitpException':
                raise LitpException(404, {})
            else:
                return {'state': LitpRestClient.ITEM_STATE_APPLIED,
                        'properties': properties
                       }

        def mock_get_model_path_func(node):
            if node.type == ITEM_TYPE_VIP:
                return '/deployments/d1/clusters/c1/services/cs1/vip'
            else:
                return '/deployments/d1/clusters/c1/services/cs1'

        mock_xpath.side_effect = mock_xpath_func
        mock_create_item.side_effect = mock_create_item_func
        mock_get_props.side_effect = mock_get_props_func
        mock_litp_get.side_effect = mock_litp_get_func
        mock_get_model_path.side_effect = mock_get_model_path_func

        cs_properties = iter([
            {'node_list': 'n1,n2', 'active': 2, 'standby': 0},
            {'node_list': 'n1,n2', 'active': 2, 'standby': 0}, # same
            {'node_list': 'n1,n2', 'active': 2, 'standby': 0},
            {'node_list': 'n2,n1', 'active': 2, 'standby': 0}, # same
            {'node_list': 'n1', 'active': 1, 'standby': 0},
            {'node_list': 'n1,n2', 'active': 2, 'standby': 0}, # contraction
            {'node_list': 'n1,n2', 'active': 2, 'standby': 0},
            'LitpException'                                    # new
                            ])
        vip_properties = iter([
            {'network_name': 'internal', 'ipaddress': '10.11.12.13'},
            {'network_name': 'internal', 'ipaddress': '10.11.12.13'}, # same
            {'network_name': 'internal', 'ipaddress': '10.11.12.14'},
            {'network_name': 'internal', 'ipaddress': '10.11.12.15'}, # update
            {'network_name': 'internal', 'ipaddress': '10.11.12.16'},
            'LitpException'                                           # new
                             ])

        expected_commands = [
                'litp update -p /deployments/d1/clusters/c1/services/cs1/vip '
                '-o ipaddress=10.11.12.14',
                'litp create -t vip -p /deployments/d1/clusters/c1/services/'
                'cs1/vip',
                'litp update -p /deployments/d1/clusters/c1/services/cs1 '
                '-o active=1 node_list=n1',
                            ]

        comm_list = pre_rollover_changes('dd.xml')
        self.assertEqual(expected_commands, comm_list)
