import os
from mock import patch
from unittest2 import TestCase

from h_expansion.expansion_sed_utils import ExpansionSedHandler


class TestExpansionSedHandler(TestCase):
    def setUp(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        target_sed = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_sed')

        self.sed_handler = ExpansionSedHandler(target_sed)

    def tearDown(self):
        pass

    def test_get_sed_entries_for_node(self):
        node_details = self.sed_handler.get_sed_entries_for_node('db-1')

        self.assertIsNotNone(node_details)

    def test_get_sed_entries_for_node_exception(self):
        self.assertRaises(Exception,
                          self.sed_handler.get_sed_entries_for_node,
                          'db-10')

    def test_get_oa_info_from_sed(self):
        oa_info = self.sed_handler.get_enclosure_oa_info('enclosure1')

        self.assertIsNotNone(oa_info)

        self.assertEqual(oa_info.ip_1, '10.36.49.160')
        self.assertEqual(oa_info.ip_2, '10.36.49.161')
        self.assertEqual(oa_info.user, 'root')
        self.assertEqual(oa_info.passwd, 'shroot12')

    def test_get_oa_info_from_sed_no_exception(self):
        # Test an exception is thrown when no enclosure is found
        self.assertRaises(Exception,
                          self.sed_handler.get_enclosure_oa_info,
                          'enclosure3')

        # Test an exception is thrown when all OA values are not found
        self.assertRaises(Exception,
                          self.sed_handler.get_enclosure_oa_info,
                          'enclosure2')

    def test_get_ilo_ip_address_for_node(self):
        ilo_ip = self.sed_handler.get_ilo_ip_address_for_node('db-1')

        self.assertEqual(ilo_ip, '10.36.49.170')

    def test_get_ilo_ip_address_for_node_exception(self):
        # Test an exception is thrown when no iLO IP is found
        with patch('h_expansion.expansion_sed_utils.ExpansionSedHandler'
                   '.get_sed_entries_for_node', return_value={}):
            self.assertRaises(Exception,
                              self.sed_handler.get_ilo_ip_address_for_node,
                              'db-1')

        # Test an exception is thrown when the iLO IP is invalid
        with patch('h_expansion.expansion_sed_utils.ExpansionSedHandler'
                   '.get_sed_entries_for_node',
                   return_value={'ilo_IP': '10.260.34.390'}):
            self.assertRaises(Exception,
                              self.sed_handler.get_ilo_ip_address_for_node,
                              'db-1')

    def test_get_peer_node_ilo_ip_addresses(self):
        nodes = ['db-1', 'db-2']

        expected_dict = {'db-1': '10.36.49.170', 'db-2': '10.36.49.167'}

        sed_ilo_dict = self.sed_handler.get_peer_node_ilo_ip_addresses(nodes)

        self.assertEqual(sed_ilo_dict, expected_dict)

    def test_get_peer_node_serial_number(self):
        expected_serial = 'CZ3328JJT6'
        found_serial = self.sed_handler.get_peer_node_serial_number('db-2')

        self.assertEqual(expected_serial, found_serial)

    def test_get_peer_node_serial_number_exception(self):
        self.assertRaises(Exception,
                          self.sed_handler.get_peer_node_serial_number,
                          'db-1')

    def test_get_sed_entry(self):
        expected_value = 'athtem.eei.ericsson.se'

        value_found = self.sed_handler.get_sed_entry('dns_domainName')

        self.assertEqual(expected_value, value_found)

    def test_get_sed_entry_exception(self):
        # Test an exception is thrown when no value is found
        self.assertRaises(KeyError,
                          self.sed_handler.get_sed_entry,
                          'LMS_domain')

    def test_get_sed_entry_exception_no_value(self):
        # Test an exception is thrown when no value is found
        self.assertRaises(Exception,
                          self.sed_handler.get_sed_entry,
                          'enclosure2_username')

    def test_get_peer_serials_for_nodes(self):
        nodes = ['svc-2', 'db-2']

        expected_serials = {'svc-2': 'CZ36071H37', 'db-2': 'CZ3328JJT6'}

        actual_serials = self.sed_handler.get_peer_serials_for_nodes(nodes)

        self.assertEqual(expected_serials, actual_serials)
