import os
from datetime import datetime, timedelta
from unittest import TestCase
from mock import patch, call, mock_open

from h_puppet.mco_agents import McoAgentException
from test_validate_expansion_sed import dummy_get_blades_to_move
from h_expansion.expansion_utils import OnboardAdministratorHandler, \
    ExpansionException
from h_expansion.expansion_boot_utils import get_system_names, boot_systems, \
    run_hwcomm, wait_for_ping, vcs_running, wait_for_vcs, unlock_system, \
    unlock_systems, freeze_system, freeze_systems, services_offline, \
    wait_for_offline_services, shutdown_systems, wait_for_shutdown, \
    freeze_and_shutdown_systems, get_new_blade_bays, set_correct_bays, \
    configure_ebipa, check_ilos_not_configured, remove_ebipa_entries, \
    configure_ilo, get_network_info, serial_numbers_ok, wait_for_serials, \
    boot_systems_and_unlock_vcs

show_server_output = """
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
      9 HP ProLiant BL460c Gen9                           [Unknown]       Other    On      Off 
     10 HP ProLiant BL460c Gen9                           [Unknown]       Other    On      Off 
     11 HP ProLiant BL460c Gen9                           [Unknown]       Other    On      Off 
     12 HP ProLiant BL460c Gen9                           [Unknown]       Other    On      Off 
     13 HP ProLiant BL460c Gen9                           [Unknown]       Other    On      Off 
     14 [Absent]                                          
     15 HP ProLiant BL460c Gen9                           [Unknown]       Other    Off     Off 
     16 HP ProLiant BL460c Gen9                           [Unknown]       Other    Off     Off 
    Totals: 7 server blades installed, 5 powered on.

    ieatc7000-196oa1 [SCRIPT MODE]> 

    SHOW SERVER NAMES
    """


class TestExpansionBootUtils(TestCase):
    def setUp(self):
        self.enclosure_oa = OnboardAdministratorHandler('10.10.10.10',
                                                        '10.10.10.11',
                                                        'oa_user',
                                                        'passwd')

        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.target_sed = os.path.join(dir_path,
                                       '../Resources/chassis_expansion_sed')
        self.report_file = os.path.join(dir_path,
                                        '../Resources/chassis_expansion_report.txt')

    def test_get_system_names(self):
        system_names = get_system_names(dummy_get_blades_to_move())
        expected_names = 'ieatrcxb3184 ieatrcxb3774 ieatrcxb1958 ieatrcxb3175'

        self.assertEqual(system_names, expected_names)

    def _get_report_file_contents(self):
        with open(self.report_file, 'r') as rep:
            report = rep.read()

        return report

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.power_on_system')
    def test_boot_systems(self, m_power_on):
        bays = [2, 4, 6]

        boot_systems(bays, self.enclosure_oa)

        self.assertTrue(m_power_on.called)
        self.assertEqual(m_power_on.call_count, 3)
        self.assertEqual(m_power_on.call_args_list, [call(2), call(4), call(6)])

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.power_on_system')
    def test_boot_systems_exception(self, m_power_on):
        bays = [2, 4, 6]
        m_power_on.side_effect = [OSError(), IOError()]

        self.assertRaises(OSError, boot_systems, bays, self.enclosure_oa)
        self.assertRaises(IOError, boot_systems, bays, self.enclosure_oa)

    @patch('h_expansion.expansion_boot_utils.exec_process')
    def test_run_hwcomm(self, m_exec):
        run_hwcomm(self.target_sed, 'configure_oa')

        self.assertTrue(m_exec.called)
        m_exec.assert_called_with(['/opt/ericsson/hw_comm/bin/hw_comm.sh',
                                  '-y', 'configure_oa', self.target_sed])

    @patch('h_expansion.expansion_boot_utils.exec_process')
    def test_run_hwcomm_exception(self, m_exec):
        m_exec.side_effect = [IOError(), OSError()]
        self.assertRaises(IOError, run_hwcomm, self.target_sed, 'configure_vc')
        self.assertRaises(OSError, run_hwcomm, self.target_sed, 'configure_oa')

    @patch('h_expansion.expansion_boot_utils.ping')
    @patch('h_expansion.expansion_boot_utils.sleep')
    def test_wait_for_ping(self, m_sleep, m_ping):
        m_ping.side_effect = [True, False, True, True, True]

        nodes = dummy_get_blades_to_move()
        called_hosts = [call('ieatrcxb3184'), call('ieatrcxb3774'),
                        call('ieatrcxb1958'), call('ieatrcxb3175'),
                        call('ieatrcxb3774')]

        wait_for_ping(nodes)

        self.assertTrue(m_sleep.called)
        self.assertEqual(m_sleep.call_count, 1)
        self.assertTrue(m_ping.called)
        self.assertEqual(m_ping.call_count, 5)
        self.assertEqual(m_ping.call_args_list, called_hosts)

    @patch('h_expansion.expansion_boot_utils.datetime')
    @patch('h_expansion.expansion_boot_utils.ping')
    @patch('h_expansion.expansion_boot_utils.sleep')
    def test_wait_for_ping_timeout(self, m_sleep, m_ping, m_date):
        date1 = datetime.now()
        minutes = timedelta(minutes=32)
        date2 = date1 + minutes
        m_date.now.side_effect = [date1, date2]
        m_ping.return_value = False
        nodes = dummy_get_blades_to_move()
        self.assertRaises(ExpansionException, wait_for_ping, nodes)

    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_vcs_running(self, m_agent):
        edata = [{'State': ['RUNNING'], 'Name': 'host1'},
                 {'State': ['LEAVING'], 'Name': 'host2'}]

        m_agent.return_value.hasys_state.side_effect = [([], edata),
                                                        ([], edata),
                                                        KeyError()]

        self.assertTrue(vcs_running('host1'))
        self.assertFalse(vcs_running('host2'))
        # Test False is returned when an exception is raised
        self.assertFalse(vcs_running('host2'))

    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.vcs_running')
    def test_wait_for_vcs(self, m_vcs, m_sleep):
        m_vcs.side_effect = [True, False, True, True, True]

        nodes = dummy_get_blades_to_move()
        called_hosts = [call('ieatrcxb3184'), call('ieatrcxb3774'),
                        call('ieatrcxb1958'), call('ieatrcxb3175'),
                        call('ieatrcxb3774')]

        wait_for_vcs(nodes)

        self.assertTrue(m_vcs.called)
        self.assertEqual(m_vcs.call_count, 5)
        self.assertEqual(m_vcs.call_args_list, called_hosts)
        self.assertTrue(m_sleep.called)

    @patch('h_expansion.expansion_boot_utils.datetime')
    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.vcs_running')
    def test_wait_for_vcs_timeout(self, m_vcs, m_sleep, m_date):
        m_vcs.return_value = False
        date1 = datetime.now()
        minutes = timedelta(minutes=12)
        date2 = date1 + minutes
        m_date.now.side_effect = [date1, date2]
        nodes = dummy_get_blades_to_move()
        self.assertRaises(ExpansionException, wait_for_vcs, nodes)

    @patch('h_puppet.mco_agents.VcsCmdApiAgent.unlock')
    def test_unlock_system(self, m_unlock):
        unlock_system('host1')

        self.assertTrue(m_unlock.called)
        m_unlock.assert_called_with('host1', 300)

    @patch('h_puppet.mco_agents.VcsCmdApiAgent.unlock')
    def test_unlock_system_exception(self, m_unlock):
        m_unlock.side_effect = [McoAgentException()]
        self.assertRaises(McoAgentException, unlock_system, 'host')


    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.unlock_system')
    def test_unlock_systems(self, m_unlock, m_progress):
        nodes = dummy_get_blades_to_move()
        called_hosts = [call(node.hostname) for node in nodes]

        unlock_systems(nodes)

        self.assertTrue(m_unlock.called)
        self.assertEqual(m_unlock.call_count, 4)
        self.assertEqual(m_unlock.call_args_list, called_hosts)
        self.assertTrue(m_progress.called)
        self.assertEqual(m_progress.call_count, 3)

    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_freeze_system(self, m_agent):
        host = 'host1'
        m_freeze = m_agent.return_value.hasys_freeze
        m_freeze.side_effect = [None]
        freeze_system(host)
        m_freeze.assert_called_with(host, persistent=True, evacuate=True)

    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_freeze_system_already_frozen(self, m_agent):
        m_agent.return_value.hasys_freeze.side_effect = \
            [McoAgentException('V-16-1-40206')]
        freeze_system('host1')
        self.assertTrue(m_agent.called)

    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_freeze_system_exception(self, m_agent):
        m_agent.return_value.hasys_freeze.side_effect = [IOError]
        self.assertRaises(IOError, freeze_system, 'host2')

    @patch('h_expansion.expansion_boot_utils.freeze_system')
    def test_freeze_systems(self, m_freeze):
        nodes = dummy_get_blades_to_move()

        called_hosts = [call(node.hostname) for node in nodes]

        freeze_systems(nodes)

        self.assertTrue(m_freeze.called)
        self.assertEqual(m_freeze.call_count, 4)
        self.assertEqual(m_freeze.call_args_list, called_hosts)


    @patch('h_expansion.expansion_boot_utils.Vcs')
    @patch('h_expansion.expansion_boot_utils.filter_tab_data')
    def test_services_offline(self, m_filter, m_vcs):
        vcs_info = [{'ServiceState': 'OFFLINE'},
                    {'ServiceState': 'OFFLINE'}]

        m_vcs.get_cluster_group_status.return_value = vcs_info
        m_vcs.neo4j_health_check.return_value = vcs_info
        m_filter.return_value = vcs_info
        self.assertTrue(services_offline('host1'))

    @patch('h_expansion.expansion_boot_utils.Vcs')
    @patch('h_expansion.expansion_boot_utils.filter_tab_data')
    def test_services_offline_fail(self, m_filter, m_vcs):
        vcs_info = [{'ServiceState': 'ONLINE'},
                    {'ServiceState': 'OFFLINE'}]

        m_vcs.get_cluster_group_status.return_value = vcs_info
        m_vcs.neo4j_health_check.return_value = vcs_info
        m_filter.return_value = vcs_info
        self.assertFalse(services_offline('host1'))

    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.services_offline')
    def test_wait_for_offline_services(self, m_offline, m_sleep):
        nodes = dummy_get_blades_to_move()

        m_offline.side_effect = [True, True, True, False, True]
        called_hosts = [call('ieatrcxb3184'), call('ieatrcxb3774'),
                        call('ieatrcxb1958'), call('ieatrcxb3175'),
                        call('ieatrcxb3175')]

        wait_for_offline_services(nodes)

        self.assertTrue(m_offline.called)
        self.assertEqual(m_offline.call_count, 5)
        self.assertEqual(m_offline.call_args_list, called_hosts)
        self.assertTrue(m_sleep.called)

    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.services_offline')
    def test_wait_for_offline_services_exception(self, m_offline, m_sleep):
        nodes = dummy_get_blades_to_move()

        m_offline.side_effect = [McoAgentException(), McoAgentException(),
                                 McoAgentException()]

        self.assertRaises(McoAgentException, wait_for_offline_services, nodes)
        self.assertEqual(m_offline.call_count, 3)

    @patch('h_expansion.expansion_boot_utils.datetime')
    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.services_offline')
    def test_wait_for_offline_services_timeout(self, m_offline, m_sleep, m_date):
        m_offline.return_value = False
        date1 = datetime.now()
        minutes = timedelta(minutes=12)
        date2 = date1 + minutes
        m_date.now.side_effect = [date1, date2]
        nodes = dummy_get_blades_to_move()
        self.assertRaises(ExpansionException, wait_for_offline_services, nodes)


    @patch('h_expansion.expansion_boot_utils.ping')
    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_shutdown_systems(self, m_agent, m_ping):
        m_shutdown = m_agent.return_value.shutdown_host
        m_shutdown.return_value = None
        m_ping.return_value = True

        nodes = dummy_get_blades_to_move()
        shutdown_systems(nodes)
        self.assertTrue(m_shutdown.called)
        self.assertTrue(m_ping.called)

    @patch('h_expansion.expansion_boot_utils.ping')
    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_shutdown_systems_no_ping(self, m_agent, m_ping):
        m_shutdown = m_agent.return_value.shutdown_host
        m_shutdown.return_value = None
        m_ping.return_value = False

        nodes = dummy_get_blades_to_move()
        shutdown_systems(nodes)
        self.assertFalse(m_shutdown.called)
        self.assertTrue(m_ping.called)

    @patch('h_expansion.expansion_boot_utils.ping')
    @patch('h_expansion.expansion_boot_utils.EnminstAgent')
    def test_shutdown_systems_exception(self, m_agent, m_ping):
        m_shutdown = m_agent.return_value.shutdown_host
        m_shutdown.side_effect = [McoAgentException]
        m_ping.return_value = True
        nodes = dummy_get_blades_to_move()
        self.assertRaises(McoAgentException, shutdown_systems, nodes)

    @patch('h_expansion.expansion_boot_utils.ping')
    @patch('h_expansion.expansion_boot_utils.sleep')
    def test_wait_for_shutdown(self, m_sleep, m_ping):
        nodes = dummy_get_blades_to_move()
        m_ping.side_effect = [True, False, True, True,
                              True, False, True, True,
                              True, False, True, False,
                              False, False, False, False]

        wait_for_shutdown(nodes)

        self.assertTrue(m_ping.called)
        self.assertEqual(m_ping.call_count, 12)
        self.assertTrue(m_sleep.called)

    @patch('h_expansion.expansion_boot_utils.datetime')
    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.ping')
    def test_wait_for_shutdown_timeout(self, m_ping, m_sleep, m_date):
        m_ping.return_value = True
        date1 = datetime.now()
        minutes = timedelta(minutes=12)
        date2 = date1 + minutes
        m_date.now.side_effect = [date1, date2]
        nodes = dummy_get_blades_to_move()
        self.assertRaises(ExpansionException, wait_for_shutdown, nodes)

    @patch('h_expansion.expansion_boot_utils.freeze_systems')
    @patch('h_expansion.expansion_boot_utils.wait_for_offline_services')
    @patch('h_expansion.expansion_boot_utils.shutdown_systems')
    @patch('h_expansion.expansion_boot_utils.wait_for_shutdown')
    def test_freeze_and_shutdown_systems(self, m_wait, m_shutdown, m_offline,
                                         m_freeze):
        nodes = dummy_get_blades_to_move()

        freeze_and_shutdown_systems(nodes)

        self.assertTrue(m_freeze.called)
        m_freeze.assert_called_with(nodes)
        self.assertTrue(m_offline.called)
        m_offline.assert_called_with(nodes)
        self.assertTrue(m_shutdown.called)
        m_shutdown.assert_called_with(nodes)
        self.assertTrue(m_wait.called)
        m_wait.assert_called_with(nodes)

    @patch('h_expansion.expansion_boot_utils.freeze_systems')
    @patch('h_expansion.expansion_boot_utils.wait_for_offline_services')
    @patch('h_expansion.expansion_boot_utils.shutdown_systems')
    @patch('h_expansion.expansion_boot_utils.wait_for_shutdown')
    def test_freeze_and_shutdown_systems_exception(self, m_wait, m_shutdown,
                                                   m_offline, m_freeze):
        m_shutdown.side_effect = [McoAgentException, IOError]
        nodes = dummy_get_blades_to_move()

        self.assertRaises(McoAgentException,
                          freeze_and_shutdown_systems, nodes)
        self.assertRaises(IOError, freeze_and_shutdown_systems, nodes)

    @patch('__builtin__.open')
    def test_get_new_blade_bays(self, m_open):
        m_open.side_effect = [mock_open(read_data=self._get_report_file_contents()).return_value]

        bays = get_new_blade_bays(show_server_output)

        self.assertEqual(bays, ['10', '11', '12', '13', '15', '16', '9'])

    @patch('h_expansion.expansion_boot_utils.get_bays_from_server_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_set_correct_bays(self, m_show_servers, m_bays):
        m_bays.return_value = {'11': 'CZ3328JJT6', '10': 'CZJ423002Q',
                               '13': 'CZ36071H37', '12': 'CZ3328JD3P'}

        nodes = dummy_get_blades_to_move()

        new_bays = set_correct_bays(nodes, self.enclosure_oa)
        new_dest_bays = [bay.dest_bay for bay in new_bays]
        new_dest_bays.sort()

        self.assertTrue(m_show_servers.called)
        self.assertTrue(m_bays.called)
        self.assertEqual(new_dest_bays, ['10', '11', '12', '13'])

    @patch('h_expansion.expansion_boot_utils.get_bays_from_server_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_set_correct_bays_already_ok(self, m_show_servers, m_bays):
        bays_serial = {'11': 'CZ3328JJT6', '10': 'CZJ423002Q',
                      '13': 'CZ36071H37', '12': 'CZ3328JD3P'}

        m_bays.return_value = bays_serial
        nodes = dummy_get_blades_to_move()

        for node in nodes:
            node.dest_bay = [k for k, v in bays_serial.iteritems()
                             if v == node.serial_no][0]

        new_bays = set_correct_bays(nodes, self.enclosure_oa)
        self.assertEqual([], new_bays)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.set_ebipa_server')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.save_ebipa')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.efuse_reset')
    def test_configure_ebipa(self, m_reset, m_save, m_set):
        nodes = dummy_get_blades_to_move()

        configure_ebipa(nodes, self.enclosure_oa, 'gateway', 'netmask', 'domain')

        self.assertTrue(m_set.called)
        self.assertEqual(m_set.call_count, 4)
        self.assertEqual(m_set.call_args_list,
                         [call(node.dest_bay, node.dest_ilo, 'netmask',
                               'gateway', 'domain') for node in nodes])
        self.assertTrue(m_save.called)
        self.assertTrue(m_reset.called)
        self.assertEqual(m_reset.call_count, 4)
        self.assertEqual(m_reset.call_args_list,
                         [call(node.dest_bay) for node in nodes])

    @patch('h_expansion.expansion_boot_utils.get_ilo_bays_from_ebipa_output')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_ebipa_server')
    def test_check_ilos_not_configured(self, m_show, m_get_bays):
        unused_ilos = {'10.1.2.3': '2', '10.1.2.4': '4',
                       '10.1.2.5': '5', '10.1.2.6': '8'}

        used_ilos = {'10.151.119.10': '2', '10.151.111.12': '4',
                     '10.151.111.13': '5', '10.151.111.14': '8'}
        m_get_bays.side_effect = [unused_ilos, used_ilos]

        nodes = dummy_get_blades_to_move()

        check_ilos_not_configured(nodes, self.enclosure_oa)

        self.assertTrue(m_show.called)
        self.assertTrue(m_get_bays.called)

        self.assertRaises(ExpansionException, check_ilos_not_configured,
                          nodes, self.enclosure_oa)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.save_ebipa')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.disable_ebipa_server')
    def test_remove_ebipa_entries(self, m_disable, m_save):
        bays = ['2', '3', '4', '5', '6', '7']

        remove_ebipa_entries(self.enclosure_oa, bays)

        self.assertTrue(m_disable.called)
        self.assertEqual(m_disable.call_count, 6)
        self.assertEqual(m_disable.call_args_list, [call(bay) for bay in bays])
        self.assertTrue(m_save.called)

    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.configure_ebipa')
    @patch('h_expansion.expansion_boot_utils.set_correct_bays')
    @patch('h_expansion.expansion_boot_utils.remove_ebipa_entries')
    @patch('h_expansion.expansion_boot_utils.check_ilos_not_configured')
    def test_configure_ilo(self, m_check, m_remove, m_set, m_configure, m_bar):
        nodes = dummy_get_blades_to_move()
        bays = ['9', '10', '11', '12']

        configure_ilo(nodes, bays, self.enclosure_oa, 'gateway', 'netmask', 'domain')

        self.assertTrue(m_remove.called)
        self.assertEqual(m_remove.call_count, 2)
        self.assertTrue(m_check.called)
        self.assertEqual(m_check.call_count, 2)
        self.assertTrue(m_configure.called)
        self.assertEqual(m_configure.call_count, 2)
        self.assertTrue(m_bar.called)
        self.assertTrue(m_set.called)
        m_set.called_with(nodes, self.enclosure_oa)

    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.configure_ebipa')
    @patch('h_expansion.expansion_boot_utils.set_correct_bays')
    @patch('h_expansion.expansion_boot_utils.remove_ebipa_entries')
    @patch('h_expansion.expansion_boot_utils.check_ilos_not_configured')
    def test_configure_ilo_already_set(self, m_check,
                                       m_remove, m_set, m_configure, m_bar):
        nodes = dummy_get_blades_to_move()
        bays = ['9', '10', '11', '12']
        m_set.return_value = []
        configure_ilo(nodes, bays, self.enclosure_oa, 'gateway', 'netmask', 'domain')

        self.assertTrue(m_remove.called)
        self.assertEqual(m_remove.call_count, 1)
        self.assertTrue(m_check.called)
        self.assertEqual(m_check.call_count, 1)
        self.assertTrue(m_configure.called)
        self.assertEqual(m_configure.call_count, 1)
        self.assertTrue(m_bar.called)
        self.assertTrue(m_set.called)
        m_set.called_with(nodes, self.enclosure_oa)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_oa_network')
    def test_get_network_info(self, m_show_oa):
        oa_info = """
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
        m_show_oa.return_value = oa_info

        gateway, netmask, domain = get_network_info(self.enclosure_oa,
                                                    self.target_sed)

        self.assertEqual(gateway, '10.141.4.1')
        self.assertEqual(netmask, '255.255.252.0')
        self.assertEqual(domain, 'athtem.eei.ericsson.se')

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_serial_numbers_ok(self, m_show_names):
        m_show_names.return_value = """
        Bay Server Name                                       Serial Number   Status   Power   UID Partner
        --- ------------------------------------------------- --------------- -------- ------- --- -------
          1 ieatrcxb5482                                      CZ3542KBR3      OK       On      Off
          2 ieatrcxb5483                                      CZ3542KBR7      OK       On      Off
          3 ieatrcxb5484                                      CZ3542KBRL      OK       On      Off
          4 ieatrcxb5485                                      CZ3542KBRR      OK       On      Off
          5 ieatrcxb5496                                      CZ3542KBN7      OK       On      Off
          6 ProLiant BL460c Gen9                              CZ3521Y84K      OK       On      Off
          7 ieatrcxb4959                                      CZ352208YR      OK       On      Off
          8 ieatrcxb5270                                      CZ35294PAN      OK       On      Off
          9 [Absent]
         10 [Absent]
         11 [Absent]
         12 [Absent]
         13 [Absent]
         14 ProLiant BL460c Gen9                              CZ3542KBS1      Other    On      Off
         15 ProLiant BL460c Gen9                              CZ3521Y85L      Other    On      Off
         16 ProLiant BL460c Gen9                              CZ3521Y84X      Other    On      Off
        Totals: 11 server blades installed, 11 powered on.
        """
        bays = {'1': 'CZ3542KBR3', '3': 'CZ3542KBRL', '4': 'CZ3542KBRR',
                '6': 'CZ3521Y84K'}

        serials_okay = serial_numbers_ok(bays, self.enclosure_oa)

        self.assertTrue(serials_okay)

    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.serial_numbers_ok')
    def test_wait_for_serials(self, m_serial_ok, m_sleep):
        bays = {'1': 'CZ3542KBR3', '3': 'CZ3542KBRL', '4': 'CZ3542KBRR',
                '6': 'CZ3521Y84K'}

        m_serial_ok.side_effect = [False, True]

        wait_for_serials(bays, self.enclosure_oa)

        self.assertTrue(m_serial_ok.called)
        self.assertTrue(m_serial_ok.call_count, 2)
        self.assertTrue(m_sleep.called)

    @patch('h_expansion.expansion_boot_utils.datetime')
    @patch('h_expansion.expansion_boot_utils.sleep')
    @patch('h_expansion.expansion_boot_utils.serial_numbers_ok')
    def test_wait_for_serials_timeout(self, m_serial_ok, m_sleep, m_date):
        date1 = datetime.now()
        minutes = timedelta(minutes=12)
        date2 = date1 + minutes
        m_date.now.side_effect = [date1, date2]

        bays = {'1': 'CZ3542KBR3', '3': 'CZ3542KBRL', '4': 'CZ3542KBRR',
                '6': 'CZ3521Y84K'}

        m_serial_ok.side_effect = [False, True]

        self.assertRaises(ExpansionException, wait_for_serials, bays, self.enclosure_oa)

    @patch('h_expansion.expansion_boot_utils.run_hwcomm')
    @patch('h_expansion.expansion_boot_utils.boot_systems')
    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.wait_for_vcs')
    @patch('h_expansion.expansion_boot_utils.configure_ilo')
    @patch('h_expansion.expansion_boot_utils.wait_for_ping')
    @patch('h_expansion.expansion_boot_utils.unlock_systems')
    @patch('h_expansion.expansion_boot_utils.get_network_info')
    @patch('h_expansion.expansion_boot_utils.wait_for_serials')
    @patch('h_expansion.expansion_boot_utils.get_new_blade_bays')
    @patch('h_expansion.expansion_boot_utils.switch_dbcluster_groups')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_boot_systems_and_unlock_vcs(self, m_show_names, m_switch_db,
                                         m_new_blades, m_wait_serial,
                                         m_get_network, m_unlock, m_wait_ping,
                                         m_config, m_wait_vcs, m_progress,
                                         m_boot, m_hwcomm):
        m_new_blades.return_value = ['2', '3', '6', '8']
        m_get_network.return_value = ('10.141.4.1', '255.255.252.0', 'athtem.eei.ericsson.se')

        nodes = dummy_get_blades_to_move()

        boot_systems_and_unlock_vcs(nodes, self.enclosure_oa,
                                    self.target_sed, False)

        self.assertTrue(m_show_names.called)
        self.assertTrue(m_switch_db.called)
        self.assertTrue(m_new_blades.called)
        self.assertTrue(m_wait_serial.called)
        self.assertTrue(m_get_network.called)
        self.assertTrue(m_unlock.called)
        self.assertTrue(m_wait_ping.called)
        self.assertTrue(m_config.called)
        self.assertTrue(m_wait_vcs.called)
        self.assertTrue(m_progress.called)
        self.assertTrue(m_boot.called)
        self.assertTrue(m_hwcomm.called)

    @patch('h_expansion.expansion_boot_utils.run_hwcomm')
    @patch('h_expansion.expansion_boot_utils.boot_systems')
    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.wait_for_vcs')
    @patch('h_expansion.expansion_boot_utils.configure_ilo')
    @patch('h_expansion.expansion_boot_utils.wait_for_ping')
    @patch('h_expansion.expansion_boot_utils.unlock_systems')
    @patch('h_expansion.expansion_boot_utils.get_network_info')
    @patch('h_expansion.expansion_boot_utils.wait_for_serials')
    @patch('h_expansion.expansion_boot_utils.get_new_blade_bays')
    @patch('h_expansion.expansion_boot_utils.switch_dbcluster_groups')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_boot_systems_and_unlock_vcs_rb(self, m_show_names, m_switch_db,
                                            m_new_blades, m_wait_serial,
                                            m_get_network, m_unlock, m_wait_ping,
                                            m_config, m_wait_vcs, m_progress,
                                            m_boot, m_hwcomm):
        m_new_blades.return_value = ['2', '3', '6', '8']
        m_get_network.return_value = ('10.141.4.1', '255.255.252.0', 'athtem.eei.ericsson.se')

        nodes = dummy_get_blades_to_move()

        boot_systems_and_unlock_vcs(nodes, self.enclosure_oa,
                                    self.target_sed, True)

        self.assertTrue(m_show_names.called)
        self.assertTrue(m_switch_db.called)
        self.assertFalse(m_new_blades.called)
        self.assertTrue(m_wait_serial.called)
        self.assertFalse(m_get_network.called)
        self.assertTrue(m_unlock.called)
        self.assertTrue(m_wait_ping.called)
        self.assertFalse(m_config.called)
        self.assertTrue(m_wait_vcs.called)
        self.assertTrue(m_progress.called)
        self.assertTrue(m_boot.called)
        self.assertFalse(m_hwcomm.called)

    @patch('h_expansion.expansion_boot_utils.run_hwcomm')
    @patch('h_expansion.expansion_boot_utils.boot_systems')
    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.wait_for_vcs')
    @patch('h_expansion.expansion_boot_utils.configure_ilo')
    @patch('h_expansion.expansion_boot_utils.wait_for_ping')
    @patch('h_expansion.expansion_boot_utils.unlock_systems')
    @patch('h_expansion.expansion_boot_utils.get_network_info')
    @patch('h_expansion.expansion_boot_utils.wait_for_serials')
    @patch('h_expansion.expansion_boot_utils.get_new_blade_bays')
    @patch('h_expansion.expansion_boot_utils.switch_dbcluster_groups')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_boot_systems_and_unlock_vcs_exception(self, m_show_names, m_switch_db,
                                                   m_new_blades, m_wait_serial,
                                                   m_get_network, m_unlock, m_wait_ping,
                                                   m_config, m_wait_vcs, m_progress,
                                                   m_boot, m_hwcomm):
        m_new_blades.return_value = ['2', '3', '6', '8']
        m_get_network.return_value = ('10.141.4.1', '255.255.252.0', 'athtem.eei.ericsson.se')
        nodes = dummy_get_blades_to_move()

        m_hwcomm.side_effect = ['WARNING: The SED Serial numbers', '']

        self.assertRaises(ExpansionException, boot_systems_and_unlock_vcs,
                          nodes, self.enclosure_oa, self.target_sed, False)

        m_hwcomm.side_effect = ['', 'WARNING: The SED Serial numbers']

        self.assertRaises(ExpansionException, boot_systems_and_unlock_vcs,
                          nodes, self.enclosure_oa, self.target_sed, False)

    @patch('h_expansion.expansion_boot_utils.run_hwcomm')
    @patch('h_expansion.expansion_boot_utils.boot_systems')
    @patch('h_expansion.expansion_boot_utils.progress_bar')
    @patch('h_expansion.expansion_boot_utils.wait_for_vcs')
    @patch('h_expansion.expansion_boot_utils.configure_ilo')
    @patch('h_expansion.expansion_boot_utils.wait_for_ping')
    @patch('h_expansion.expansion_boot_utils.unlock_systems')
    @patch('h_expansion.expansion_boot_utils.get_network_info')
    @patch('h_expansion.expansion_boot_utils.wait_for_serials')
    @patch('h_expansion.expansion_boot_utils.get_new_blade_bays')
    @patch('h_expansion.expansion_boot_utils.switch_dbcluster_groups')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_boot_systems_and_unlock_vcs_wrong_bays(self, m_show_names, m_switch_db,
                                                    m_new_blades, m_wait_serial,
                                                    m_get_network, m_unlock, m_wait_ping,
                                                    m_config, m_wait_vcs, m_progress,
                                                    m_boot, m_hwcomm):
        m_new_blades.return_value = ['2', '3', '6']
        m_get_network.return_value = ('10.141.4.1', '255.255.252.0', 'athtem.eei.ericsson.se')
        nodes = dummy_get_blades_to_move()

        self.assertRaises(ExpansionException, boot_systems_and_unlock_vcs,
                          nodes, self.enclosure_oa, self.target_sed, False)
