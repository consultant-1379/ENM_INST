import os

from h_expansion.expansion_sed_utils import ExpansionSedHandler
from h_litp.litp_utils import LitpException
from unittest2 import TestCase
from mock import patch, call, mock_open, MagicMock

from h_expansion.expansion_utils import is_valid_ip_address, \
    OnboardAdministratorHandler, progress_bar, sleep_and_write_char, \
    display_time, report_file_ok, get_info_from_network_output, \
    get_bays_from_server_output, get_ilo_bays_from_ebipa_output, LitpHandler, \
    get_blades_from_litp, Blade, get_blade_info, ExpansionException
from test_expansion_boot_utils import show_server_output
from test_validate_expansion_sed import dummy_get_blades_to_move

report_file = """
Enclosure report generated at 07-September-2020 14:30

DETAILS OF BLADES TO BE MOVED
==============================

|System Name| |Serial Number| |Src iLO IP Address| |Dst iLO IP Address| |Src Bay| |Dst Bay| |Host Name|
=======================================================================================================
    db-2        CZ36092PBA         10.141.5.64          10.141.5.66         9   Unknown     ieatrcxb5271
   scp-2        CZ3542KBRW         10.141.5.65          10.141.5.65        13   Unknown     ieatrcxb4959
   svc-2        CZ3702A3WX         10.141.5.66          10.141.5.64        10   Unknown     ieatrcxb5483
   svc-4        CZ35294PAT         10.141.5.67          10.141.5.67        11   Unknown     ieatrcxb5485
   svc-6        CZ35294PAY         10.141.5.68          10.141.5.68        12   Unknown     ieatrcxb4856


DETAILS OF DESTINATION ENCLOSURE
================================
HPE BladeSystem Onboard Administrator
(C) Copyright 2006-2019 Hewlett Packard Enterprise Development LP

ieatc7000-196oa1 [SCRIPT MODE]> SHOW SERVER NAMES


Bay Server Name                                       Serial Number   Status   Power   UID Partner
--- ------------------------------------------------- --------------- -------- ------- --- -------
  1 [Absent]
  2 [Absent]
  3 [Absent]
  4 [Absent]
  5 [Absent]
  6 [Absent]
  7 [Absent]
  8 [Absent]
  9 [Absent]
 10 [Absent]
 11 [Absent]
 12 [Absent]
 13 [Absent]
 14 [Absent]
 15 HP ProLiant BL460c Gen9                           [Unknown]       Other    Off     Off
 16 HP ProLiant BL460c Gen9                           [Unknown]       Other    Off     Off
Totals: 2 server blades installed, 0 powered on.

ieatc7000-196oa1 [SCRIPT MODE]>
"""

oa_network_info = """
Enclosure Network Settings:

        - - - - - IPv6 Information - - - - -
        IPv6: Enabled
        DHCPv6: Enabled
        Router Advertisements: Enabled
        Stateless address autoconfiguration (SLAAC): Enabled

Onboard Administrator #1 Network Information:
        Name: ieatc7000-249oa1

        - - - - - IPv4 Information - - - - -
        DHCP: Disabled
        DHCP-Supplied Domain Name: Enabled
        Domain Name:
        IPv4 Address: 10.141.5.32
        Netmask: 255.255.252.0
        Gateway Address: 10.141.4.1
        Static IPv4 DNS 1: 159.107.173.3
        Static IPv4 DNS 2: 159.107.173.12

        - - - - - IPv6 Information - - - - -
        Link-local Address: fe80::fe15:b4ff:fe1b:63d3/64
        Static Address: Not Set
        DHCPv6 Address: (Not Set)
        Stateless address autoconfiguration (SLAAC) Addresses:
                (Not Set)
        Static IPv6 DNS 1: Not Set
        Static IPv6 DNS 2: Not Set
        IPv6 Dynamic DNS: Disabled
        IPv6 Static Default Gateway: Not set
        IPv6 Current Default Gateway: Not set
        IPv6 Static Route: Not Set

        - - - - - General Information - - - - -
        Active IPv4 DNS Servers:
                Primary:         159.107.173.3
                Secondary:       159.107.173.12
        Active IPv6 DNS Servers:
                Primary:         Not Set
                Secondary:       Not Set

        MAC Address: FC:15:B4:1B:63:D3
        Link Settings: Auto-Negotiation, 1000 Mbps, Full Duplex
        Link Status: Active
        Enclosure IP Mode: Disabled

        - - - - - Advanced Settings - - - - -
        User-Supplied Domain Name: Not Set
        """

show_ebipa_server = """
EBIPA Device Server Settings
Bay Enabled EBIPA/Current   Netmask         Gateway         DNS             Domain
--- ------- --------------- --------------- --------------- --------------- ------
  1   Yes   10.141.5.40     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.40                                     159.107.173.12
 1A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 1B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  2   Yes   10.141.5.41     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.41                                     159.107.173.12
 2A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 2B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  3   Yes   10.141.5.42     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.42                                     159.107.173.12
 3A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 3B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  4   Yes   10.141.5.43     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.43                                     159.107.173.12
 4A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 4B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  5   Yes   10.141.5.44     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.44                                     159.107.173.12
 5A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 5B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  6   Yes   10.141.5.45     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.45                                     159.107.173.12
 6A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 6B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  7   Yes   10.141.5.46     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.46                                     159.107.173.12
 7A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 7B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  8   Yes   10.141.5.47     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.47                                     159.107.173.12
 8A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 8B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
  9    No                                                   159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 9A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 9B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 10    No                                                   159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
10A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
10B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 11    No                                                   159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
11A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
11B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 12    No                                                   159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
12A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
12B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 13    No                                                   159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
13A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
13B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 14   Yes   10.141.5.53     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.53                                     159.107.173.12
14A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
14B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 15   Yes   10.141.5.54     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.54                                     159.107.173.12
15A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
15B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
 16   Yes   10.141.5.55     255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
            10.141.5.55                                     159.107.173.12
16A    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
16B    No                   255.255.252.0   10.141.4.1      159.107.173.3   athtem.eei.ericsson.se
                                                            159.107.173.12
"""

active_output = """
Onboard Administrator #1 Status:

        Name:   ieatc7000-196oa1

        Role:   Active

        UID:    Off

        Status: OK

        Diagnostic Status:

                Internal Data                            OK

                Firmware Mismatch                        OK
"""

cluster_nodes = {'scp_cluster': {'scp-1': None, 'scp-2': None},
                 'svc_cluster': {'svc-1': None, 'svc-2': None, 'svc-3': None,
                                 'svc-4': None},
                 'db_cluster': {'db-1': None, 'db-2': None}}


class TestExpansionUtils(TestCase):
    def setUp(self):
        self.oa = OnboardAdministratorHandler('10.10.10.10', '10.10.10.11',
                                              'oa_user', 'passwd')

    def test_get_info_from_network_output(self):
        gateway, netmask = get_info_from_network_output(oa_network_info)

        self.assertEqual(gateway, '10.141.4.1')
        self.assertEqual(netmask, '255.255.252.0')

    def test_get_info_from_network_output_fail_gateway(self):
        self.assertRaises(ExpansionException, get_info_from_network_output, '')

    def test_get_info_from_network_output_fail_netmask(self):
        self.assertRaises(ExpansionException, get_info_from_network_output, 'Gateway Address: 1.1.1.1')

    def test_get_bays_from_server_output(self):
        bays_serials = get_bays_from_server_output(show_server_output)

        exp_output = {'11': '[Unknown]', '10': '[Unknown]', '13': '[Unknown]',
                      '12': '[Unknown]', '15': '[Unknown]', '16': '[Unknown]',
                      '9': '[Unknown]'}

        self.assertEqual(bays_serials, exp_output)

    def test_get_bays_from_server_output_fail(self):
        self.assertRaises(IndexError, get_bays_from_server_output, "1\n2\n3")

    def test_get_ilo_bays_from_ebipa_output(self):
        exp_bays = {'10.141.5.47': '8', '10.141.5.46': '7', '10.141.5.45': '6',
                    '10.141.5.44': '5', '10.141.5.43': '4', '10.141.5.42': '3',
                    '10.141.5.41': '2', '10.141.5.40': '1', '10.141.5.54': '15',
                    '10.141.5.53': '14', '159.107.173.3': '13', '10.141.5.55': '16'}

        ilo_bays = get_ilo_bays_from_ebipa_output(show_ebipa_server)

        self.assertEqual(ilo_bays, exp_bays)

    def test_get_ilo_bays_from_ebipa_output_none(self):
        ilo_bays = get_ilo_bays_from_ebipa_output('1\n2\n3')
        self.assertEqual(ilo_bays, {})

    @patch('h_expansion.expansion_utils.LitpHandler')
    def test_get_blades_from_litp(self, m_litp):
        mock_handler = MagicMock()
        mock_handler.enm_system_names = ['scp-1', 'scp-2', 'svc-1', 'svc-2',
                                         'svc-3', 'svc-4', 'db-1', 'db-2']

        m_litp.return_value = mock_handler
        m_litp.return_value.get_hostname.side_effect = ['ieatrcxbscp2',
                                                        'ieatrcxbsvc2',
                                                        'ieatrcxbsvc4',
                                                        'ieatrcxbdb2']

        bmc_props = [{'ipaddress': '10.141.5.40', 'username': 'root',
                      'password_key': 'key-for-scp_node2_ilo'},
                     {'ipaddress': '10.141.5.42', 'username': 'root',
                      'password_key': 'key-for-svc_node2_ilo'},
                     {'ipaddress': '10.141.5.44', 'username': 'root',
                      'password_key': 'key-for-svc_node4_ilo'},
                     {'ipaddress': '10.141.5.46', 'username': 'root',
                      'password_key': 'key-for-db_node2_ilo'}]
        m_litp.return_value.get_ilo_properties.side_effect = bmc_props

        blades = get_blades_from_litp(False)

        self.assertEqual(m_litp.return_value.get_hostname.call_count, 4)
        self.assertEqual(m_litp.return_value.get_hostname.call_args_list,
                         [call('scp-2'), call('svc-2'), call('svc-4'),
                          call('db-2')])

        self.assertEqual(m_litp.return_value.get_ilo_properties.call_count, 4)
        self.assertEqual(m_litp.return_value.get_ilo_properties.call_args_list,
                         [call('scp-2'), call('svc-2'), call('svc-4'),
                          call('db-2')])

        self.assertTrue(isinstance(blades[0], Blade))

    @patch('h_expansion.expansion_utils.LitpHandler')
    def test_get_blades_from_litp_rollback(self, m_litp):
        mock_handler = MagicMock()
        mock_handler.enm_system_names = ['scp-1', 'scp-2', 'svc-1', 'svc-2',
                                         'svc-3', 'svc-4', 'db-1', 'db-2']

        m_litp.return_value = mock_handler
        m_litp.return_value.get_hostname.side_effect = ['ieatrcxbscp2',
                                                        'ieatrcxbsvc2',
                                                        'ieatrcxbsvc4',
                                                        'ieatrcxbdb2']

        bmc_props = [{'ipaddress': '10.141.5.40', 'username': 'root',
                      'password_key': 'key-for-scp_node2_ilo'},
                     {'ipaddress': '10.141.5.42', 'username': 'root',
                      'password_key': 'key-for-svc_node2_ilo'},
                     {'ipaddress': '10.141.5.44', 'username': 'root',
                      'password_key': 'key-for-svc_node4_ilo'},
                     {'ipaddress': '10.141.5.46', 'username': 'root',
                      'password_key': 'key-for-db_node2_ilo'}]
        m_litp.return_value.get_ilo_properties.side_effect = bmc_props

        blades = get_blades_from_litp(True)

        self.assertEqual(m_litp.return_value.get_hostname.call_count, 4)
        self.assertEqual(m_litp.return_value.get_hostname.call_args_list,
                         [call('scp-2'), call('svc-2'), call('svc-4'),
                          call('db-2')])

        self.assertEqual(m_litp.return_value.get_ilo_properties.call_count, 4)
        self.assertEqual(m_litp.return_value.get_ilo_properties.call_args_list,
                         [call('scp-2'), call('svc-2'), call('svc-4'),
                          call('db-2')])

        self.assertTrue(isinstance(blades[0], Blade))

    @patch('h_expansion.expansion_utils.get_blades_from_litp')
    @patch('h_expansion.expansion_utils.get_bays_from_server_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_get_blade_info(self, m_server_names, m_server_out, m_get_blades):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        target_sed = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_sed')

        peer_nodes = ['scp-1', 'scp-2', 'svc-1', 'svc-2', 'svc-3', 'svc-4', 'db-2']

        m_get_blades.return_value = dummy_get_blades_to_move()

        sed_handler = ExpansionSedHandler(target_sed)
        ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
        serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

        blades = get_blade_info(self.oa, ilo_dict, serial_dict)

        self.assertTrue(m_server_names.called)
        self.assertTrue(m_server_out.called)
        self.assertTrue(m_get_blades.called)

        self.assertEqual(len(blades), 4)
        self.assertTrue(isinstance(blades[0], Blade))

    @patch('h_expansion.expansion_utils.get_blades_from_litp')
    @patch('h_expansion.expansion_utils.get_bays_from_server_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_get_blade_info_rollback(self, m_server_names, m_server_out, m_get_blades):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        target_sed = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_sed')

        peer_nodes = ['scp-1', 'scp-2', 'svc-1', 'svc-2', 'svc-3', 'svc-4', 'db-2']

        m_get_blades.return_value = dummy_get_blades_to_move()

        sed_handler = ExpansionSedHandler(target_sed)
        ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
        serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

        blades = get_blade_info(self.oa, ilo_dict, serial_dict, rollback=True)

        self.assertTrue(m_server_names.called)
        self.assertTrue(m_server_out.called)
        self.assertTrue(m_get_blades.called)

        self.assertEqual(len(blades), 4)
        self.assertTrue(isinstance(blades[0], Blade))

    @patch('h_expansion.expansion_utils.get_blades_from_litp')
    @patch('h_expansion.expansion_utils.get_bays_from_server_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_get_blade_info_missing(self, m_server_names, m_server_out, m_get_blades):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        target_sed = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_sed')

        peer_nodes = ['scp-1', 'scp-2', 'svc-1', 'svc-2', 'svc-3', 'svc-4', 'db-2']
        blades = dummy_get_blades_to_move()
        blades[0].hostname = None
        m_get_blades.return_value = blades

        sed_handler = ExpansionSedHandler(target_sed)
        ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
        serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)

        self.assertRaises(ExpansionException, get_blade_info, self.oa,
                          ilo_dict, serial_dict)

    @patch('h_expansion.expansion_utils.get_blades_from_litp')
    @patch('h_expansion.expansion_utils.get_bays_from_server_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_get_blade_info_missing_serial(self, m_server_names, m_server_out, m_get_blades):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        target_sed = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_sed')

        peer_nodes = ['scp-1', 'scp-2', 'svc-1', 'svc-2', 'svc-3', 'svc-4', 'db-2']
        m_get_blades.return_value = dummy_get_blades_to_move()

        sed_handler = ExpansionSedHandler(target_sed)
        ilo_dict = sed_handler.get_peer_node_ilo_ip_addresses(peer_nodes)
        serial_dict = sed_handler.get_peer_serials_for_nodes(peer_nodes)
        del serial_dict['svc-2']

        self.assertRaises(KeyError, get_blade_info, self.oa,
                          ilo_dict, serial_dict)

    def test_is_valid_ip_address(self):
        valid_ip = '127.0.0.1'
        self.assertTrue(is_valid_ip_address(valid_ip))

        invalid_ip = '192.168.1.2555'
        self.assertFalse(is_valid_ip_address(invalid_ip))

    @patch('h_expansion.expansion_utils.sleep')
    def test_sleep_and_write_char(self, m_sleep):
        with patch('sys.stdout') as m_sysout:
            sleep_and_write_char()

        self.assertTrue(m_sysout.flush.called)
        self.assertTrue(m_sysout.write.called)
        self.assertTrue(m_sleep.called)
        m_sleep.assert_called_with(3)
        m_sysout.write.assert_called_with('.')

    @patch('h_expansion.expansion_utils.sleep_and_write_char')
    def test_progress_bar(self, m_sleep):
        progress_bar(30)

        self.assertTrue(m_sleep.called)
        self.assertEqual(m_sleep.call_count, 11)
        self.assertEqual(m_sleep.call_args_list[10], call(delay=0, symbol='\n'))

    def test_display_time(self):
        time_string = display_time(5000)

        self.assertEqual(time_string, '1 hour, 23 minutes')

    @patch('__builtin__.open')
    @patch('os.path.exists')
    def test_report_file_ok(self, m_exists, m_open):
        m_exists.return_value = True
        m_open.side_effect = [mock_open(read_data=report_file).return_value]

        self.assertTrue(report_file_ok())

    @patch('__builtin__.open')
    @patch('os.path.exists')
    def test_report_file_not_ok(self, m_exists, m_open):
        m_exists.side_effect = [False, True]

        # Report file doesn't exist
        self.assertFalse(report_file_ok())
        # Report file exists, but doesn't have the correct contents
        self.assertFalse(report_file_ok())

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_get_litp_handler_init_fail(self, m_litp):
        m_litp.return_value.get_cluster_nodes.side_effect = [LitpException]
        self.assertRaises(LitpException, LitpHandler)

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_get_enm_system_names(self, m_litp):
        m_litp.return_value.get_cluster_nodes.return_value = cluster_nodes

        litp_handler = LitpHandler()

        expected_hosts = ['db-1', 'db-2', 'scp-1', 'scp-2', 'svc-1', 'svc-2',
                          'svc-3', 'svc-4']

        self.assertEqual(litp_handler.enm_system_names, expected_hosts)

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_get_ilo_properties(self, m_litp):
        m_litp.return_value.get_cluster_nodes.return_value = cluster_nodes

        litp_handler = LitpHandler()

        get_return = {'state': 'Applied',
                      'properties': {'username': 'root',
                                     'ipaddress': '10.141.5.41',
                                     'password_key': 'key-for-svc_node1_ilo'}}
        m_litp.return_value.get.side_effect = [get_return, LitpException]

        ilo_properties = litp_handler.get_ilo_properties('svc-1')

        self.assertEqual(ilo_properties['state'], 'Applied')
        self.assertEqual(ilo_properties['username'], 'root')
        self.assertEqual(ilo_properties['ipaddress'], '10.141.5.41')
        self.assertEqual(ilo_properties['password_key'], 'key-for-svc_node1_ilo')
        m_litp.return_value.get.assert_called_with(
            '/infrastructure/systems/svc-1_system/bmc', False)

        self.assertRaises(LitpException, litp_handler.get_ilo_properties, 'svc-1')

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_delete_ilo_entry(self, m_litp):
        m_litp.return_value.get_cluster_nodes.return_value = cluster_nodes

        litp_handler = LitpHandler()

        m_litp.return_value.delete_path.side_effect = [None, LitpException]

        litp_handler.delete_ilo_entry('svc-2')

        m_litp.return_value.delete_path.assert_called_with(
            '/infrastructure/systems/svc-2_system/bmc')
        self.assertRaises(LitpException, litp_handler.delete_ilo_entry, 'svc-2')

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_create_ilo_entry(self, m_litp):
        m_litp.return_value.get_cluster_nodes.return_value = cluster_nodes

        litp_handler = LitpHandler()

        m_litp.return_value.https_request.side_effect = [None, LitpException]

        bmc = {'ipaddress': '10.141.5.41',
               'username': 'root',
               'password_key': 'key-for-svc_node1_ilo'}

        litp_handler.create_ilo_entry('svc-1', bmc)

        m_litp.return_value.https_request.assert_called_with(
            'POST', '/infrastructure/systems/svc-1_system/',
            data={'id': 'bmc', 'type': 'bmc', 'properties': bmc})
        self.assertRaises(LitpException, litp_handler.create_ilo_entry,
                          'svc-1', bmc)

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_get_hostname(self, m_litp):
        m_scp1 = MagicMock()
        m_scp1.path = '/deployments/enm/clusters/scp_cluster/nodes/scp-1'
        m_scp1.properties = {'hostname': 'ieatrcxb5496'}

        m_scp2 = MagicMock()
        m_scp2.path = '/deployments/enm/clusters/scp_cluster/nodes/scp-2'
        m_scp2.properties = {'hostname': 'ieatrcxb4959'}

        m_litp.return_value.get_cluster_nodes.return_value = {'scp_cluster': {'scp-1': m_scp1, 'scp-2': m_scp2}}

        litp_handler = LitpHandler()

        sys_name = litp_handler.get_hostname('scp-1')

        self.assertEqual(sys_name, 'ieatrcxb5496')

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def test_get_hostname_fail(self, m_litp):
        m_scp1 = MagicMock()
        m_scp1.path = '/deployments/enm/clusters/scp_cluster/nodes/scp-1'
        m_scp1.properties = {'hostname': 'ieatrcxb5496'}

        m_litp.return_value.get_cluster_nodes.return_value = {'scp_cluster': {'scp-1': m_scp1}}
        litp_handler = LitpHandler()
        self.assertRaises(ExpansionException, litp_handler.get_hostname, 'scp-2')

    @patch('h_expansion.expansion_utils._pexpect_execute_remote_command')
    def test_oa_cmd(self, m_pexpect):
        self.oa.oa_cmd('SHOW SERVER NAMES', ip_addr='10.10.10.10')

        exp_ssh_command = 'ssh oa_user@10.10.10.10 SHOW SERVER NAMES'

        self.assertTrue(m_pexpect.called)
        m_pexpect.assert_called_with(exp_ssh_command, 'passwd')

    @patch('h_expansion.expansion_utils._pexpect_execute_remote_command')
    def test_oa_cmd_exception(self, m_pexpect):
        m_pexpect.side_effect = OSError()

        self.assertRaises(OSError, self.oa.oa_cmd, 'SHOW SERVER NAMES')
        self.assertTrue(m_pexpect.called)
        self.assertEqual(m_pexpect.call_count, 3)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    def test_set_active_ip(self, m_oa_cmd):
        m_oa_cmd.return_value = active_output

        ret = self.oa.set_active_ip()

        self.assertEqual(ret, self.oa.ip_1)
        m_oa_cmd.assert_called_with('SHOW OA STATUS', '10.10.10.10')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    def test_set_active_ip_fail(self, m_oa_cmd):
        m_oa_cmd.return_value = ''
        self.assertRaises(EnvironmentError, self.oa.set_active_ip)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    def test_set_active_ip_already_set(self, m_oa_cmd):
        m_oa_cmd.return_value = ''
        self.oa.active_ip = '10.10.10.2'
        ret = self.oa.set_active_ip()
        self.assertEqual(ret, None)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_show_server_names(self, m_set, m_cmd):
        self.oa.show_server_names()

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('SHOW SERVER NAMES')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_show_server_list(self, m_set, m_cmd):
        self.oa.show_server_list()

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('SHOW SERVER LIST')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_power_on_system(self, m_set, m_cmd):
        self.oa.power_on_system('10')

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('POWERON SERVER 10')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_show_ebipa_server(self, m_set, m_cmd):
        self.oa.show_ebipa_server()

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('SHOW EBIPA SERVER')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_set_ebipa_server(self, m_set, m_cmd):
        self.oa.set_ebipa_server('10', ip_addr='127.0.0.1',
                                 netmask='255.255.252.0',
                                 gateway='10.141.4.1',
                                 domain='athtem.eei.ericsson.se')

        oa_calls = [call('SET EBIPA SERVER 127.0.0.1 255.255.252.0 10'),
                    call('SET EBIPA SERVER GATEWAY 10.141.4.1 10'),
                    call('SET EBIPA SERVER DOMAIN athtem.eei.ericsson.se 10'),
                    call('ENABLE EBIPA SERVER 10')]

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        self.assertEqual(m_cmd.call_count, 4)
        self.assertEqual(m_cmd.call_args_list, oa_calls)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_disable_ebipa_server(self, m_set, m_cmd):
        self.oa.disable_ebipa_server('10')

        oa_calls = [call('DISABLE EBIPA SERVER 10'),
                    call('SET EBIPA SERVER NONE NONE 10'),
                    call('SET EBIPA SERVER GATEWAY NONE 10')]

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        self.assertEqual(m_cmd.call_count, 3)
        self.assertEqual(m_cmd.call_args_list, oa_calls)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    def test_save_ebipa(self, m_cmd):
        self.oa.save_ebipa()

        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('SAVE EBIPA')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_show_oa_network(self, m_set, m_cmd):
        self.oa.show_oa_network()

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('SHOW OA NETWORK')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.oa_cmd')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_active_ip')
    def test_efuse_reset(self, m_set, m_cmd):
        self.oa.efuse_reset('10')

        self.assertTrue(m_set.called)
        self.assertTrue(m_cmd.called)
        m_cmd.assert_called_with('RESET SERVER 10')
