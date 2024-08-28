import time

from mock import patch
from unittest2 import TestCase

from h_vcs.vcs_utils import sort_tab_data, report_tab_data, filter_tab_data, \
    match_filter, get_avail_type, VCS_AVAIL_STANDALONE, VCS_AVAIL_PARALLEL, \
    VCS_AVAIL_ACTIVE_STANDBY, discover_vcs_clusters, \
    _filter_property, filter_groups_by_state, filter_groups_by_systems, \
    filter_groups_by_name, filter_systems_by_state, get_group_info, \
    get_system_info, check_systems_exist, VcsCodes, get_group_avail_type, \
    get_vcs_group_info

m_group_list = ['gp_sa', 'gp_par', 'gp_ap']
m_group_data = {'gp_sa': {
    'node1': {'State': '|ONLINE|', 'VCSi3Info': ''},
    'global': {'AdministratorGroups': '', 'Parallel': '1'}
}, 'gp_par': {
    'node1': {'State': '|ONLINE|', 'VCSi3Info': ''},
    'node2': {'State': '|ONLINE|', 'VCSi3Info': ''},
    'global': {'AdministratorGroups': '', 'Parallel': '1'}
}, 'gp_ap': {
    'node1': {'State': '|ONLINE|', 'VCSi3Info': ''},
    'node2': {'State': '|OFFLINE|', 'VCSi3Info': ''},
    'global': {'AdministratorGroups': '', 'Parallel': '0'}}
}
m_group_hist = {'gp_sa': [
    {'date': 'Thu Apr 16 19:26:50 2015',
     'info': 'Group gp_sa is online on system node1',
     'id': 'V-16-1-10447',
     'ts': time.localtime()}
]}


class TestVcsUtils(TestCase):
    def test_sort_tab_data(self):
        headers = ['h1', 'h2']
        data = [
            {'h1': 'z', 'h2': 'a'},
            {'h1': 'a', 'h2': 'a'}
        ]

        result = sort_tab_data(data, None, headers)
        self.assertListEqual(data, result)

        result = sort_tab_data(data, 'nooo', headers)
        self.assertListEqual(data, result)

        result = sort_tab_data(data, 'h1', headers)
        self.assertEqual('a', result[0]['h1'])
        self.assertEqual('z', result[1]['h1'])

    @patch('h_vcs.vcs_utils.screen')
    def test_report_tab_data(self, _screen):
        headers = ['h1', 'h2']
        data = [
            {'h1': 'z', 'h2': 'a'},
            {'h1': 'a', 'h2': 'a'}
        ]

        recorded = []

        def _record(msg, verbose=True):
            recorded.append(msg)

        _screen.side_effect = _record

        report_tab_data('test report', headers, data)
        self.assertIn('test report', recorded)
        self.assertIn('  h1  h2', recorded)
        self.assertIn('   z   a', recorded)
        self.assertIn('   a   a', recorded)

    def test_filter_tab_data(self):
        data = [
            {'h1': 'z', 'h2': 'a'},
            {'h1': 'a', 'h2': 'a'}
        ]
        filtered = filter_tab_data(data, None, '')
        self.assertListEqual(data, filtered)

        filtered = filter_tab_data(data, 'z', 'h1')
        self.assertEqual(1, len(filtered))
        self.assertEqual('z', filtered[0]['h1'])

        filtered = filter_tab_data(data, 'z', 'h999')
        self.assertEqual(0, len(filtered))

        data = [
            {'h1': 'z', 'h2': ['index_a', 'index_b']},
            {'h1': 'a', 'h2': ['index_c', 'index_d']}
        ]

        filtered = filter_tab_data(data, 'index_d', 'h2')
        self.assertEqual(1, len(filtered))
        self.assertEqual(['index_c', 'index_d'], filtered[0]['h2'])

    def test_match_filter(self):
        self.assertTrue(match_filter(None, 'string'))
        self.assertFalse(match_filter('abc', 'string'))
        self.assertTrue(match_filter('.*ri.*', 'string'))
        self.assertFalse(match_filter('.*ri.*', None))
        self.assertTrue(match_filter(None, None))
        self.assertTrue(match_filter('abc', ['abc', '123']))
        self.assertFalse(match_filter('xyz', ['abc', '123']))

    def test_get_avail_type(self):
        self.assertEqual(VCS_AVAIL_STANDALONE, get_avail_type(1, 1))
        self.assertEqual(VCS_AVAIL_PARALLEL, get_avail_type(1, 2))
        self.assertEqual(VCS_AVAIL_PARALLEL, get_avail_type(1, 42))
        self.assertEqual(VCS_AVAIL_ACTIVE_STANDBY, get_avail_type(0, 2))

    @patch('h_vcs.vcs_utils.discover_peer_nodes')
    @patch('h_vcs.vcs_utils.EnminstAgent')
    def test_discover_vcs_clusters(self, m_agent, m_discover_peer_nodes):
        m_discover_peer_nodes.side_effect = [['node1', 'node2', 'node3']]
        m_agent.return_value.haclus_list.side_effect = ['c1', 'c1', 'c3']
        clusters = discover_vcs_clusters(None)
        self.assertIn('c1', clusters)
        self.assertEqual(2, len(clusters['c1']))
        self.assertIn('node1', clusters['c1'])
        self.assertIn('node2', clusters['c1'])

        self.assertEqual(1, len(clusters['c3']))
        self.assertIn('c3', clusters)
        self.assertIn('node3', clusters['c3'])

        m_discover_peer_nodes.reset()
        m_agent.reset()
        m_discover_peer_nodes.side_effect = [['node1', 'node2', 'node3']]
        m_agent.return_value.haclus_list.side_effect = ['c1', 'c1', 'c3']
        clusters = discover_vcs_clusters('c3')
        self.assertNotIn('c1', clusters)

        self.assertEqual(1, len(clusters['c3']))
        self.assertIn('c3', clusters)
        self.assertIn('node3', clusters['c3'])

    def test_get_group_avail_type(self):
        self.assertEqual(VCS_AVAIL_ACTIVE_STANDBY,
                         get_group_avail_type(1, 1, 2))
        self.assertEqual(VCS_AVAIL_PARALLEL,
                         get_group_avail_type(3, 0, 3))
        self.assertEqual(VCS_AVAIL_STANDALONE,
                         get_group_avail_type(1, 0, 1))
        self.assertRaises(ValueError, get_group_avail_type, 4, 2, 6)

    @patch('h_vcs.vcs_utils.EnminstAgent.hagrp_history')
    @patch('h_vcs.vcs_utils.EnminstAgent.hagrp_display')
    def test_get_vcs_group_info(self, m_hagrp_display, m_hagrp_history):
        m_hagrp_display.return_value = {'gp_sa': m_group_data['gp_sa']}
        m_hagrp_history.return_value = m_group_hist

        group_info = get_vcs_group_info('svc-1', ['gp_sa'],
                                        include_uptimes=True)
        self.assertIn('gp_sa', group_info)
        self.assertIn('global', group_info['gp_sa'])
        self.assertIn('systems', group_info['gp_sa'])
        self.assertIn('type', group_info['gp_sa'])
        self.assertIn('uptime', group_info['gp_sa']['systems']['node1'])

    @patch('h_vcs.vcs_utils.EnminstAgent.hagrp_display')
    @patch('h_vcs.vcs_utils.EnminstAgent.hagrp_list')
    def test_get_vcs_group_info_nogroup(self, m_hagrp_list, m_hagrp_display):
        m_hagrp_list.return_value = ['gp_sa']
        m_hagrp_display.return_value = {'gp_sa': m_group_data['gp_sa']}
        group_info = get_vcs_group_info('svc-1', include_uptimes=False)
        self.assertIn('gp_sa', group_info)
        self.assertIn('global', group_info['gp_sa'])
        self.assertIn('systems', group_info['gp_sa'])
        self.assertIn('type', group_info['gp_sa'])
        self.assertIn('uptime', group_info['gp_sa']['systems']['node1'])

    def test__filter_property(self):
        data = [
            {'a': 'a1', 'b': 'b1'},
            {'a': ['a1'], 'b': 'b11'},
            {'a': 'a2', 'b': 'b2'},
        ]

        filtered = _filter_property(data, None, 'a')
        self.assertListEqual(data, filtered)

        filtered = _filter_property(data, 'a1', 'a')
        self.assertEqual(2, len(filtered))
        self.assertDictEqual({'a': 'a1', 'b': 'b1'}, filtered[0])
        self.assertDictEqual({'a': ['a1'], 'b': 'b11'}, filtered[1])

    def test_filter_groups_by_state(self):
        data = [
            {'name': 'n1', 'State': 's1'},
            {'name': 'n2', 'State': 's2'},
        ]
        filtered = filter_groups_by_state(data, None)
        self.assertListEqual(data, filtered)

        filtered = filter_groups_by_state(data, 's1')
        self.assertEqual(1, len(filtered))
        self.assertDictEqual({'name': 'n1', 'State': 's1'}, filtered[0])

    def test_filter_groups_by_systems(self):
        data = [
            {'name': 'n1', 'System': 's1'},
            {'name': 'n2', 'System': 's2'},
        ]
        filtered = filter_groups_by_systems(data, None)
        self.assertListEqual(data, filtered)

        filtered = filter_groups_by_systems(data, 's1')
        self.assertEqual(1, len(filtered))
        self.assertDictEqual({'name': 'n1', 'System': 's1'}, filtered[0])

    def test_filter_groups_by_name(self):
        data = [
            {'Name': 'n1', 'System': 's1'},
            {'Name': 'n2', 'System': 's2'},
        ]
        filtered = filter_groups_by_name(data, None)
        self.assertListEqual(data, filtered)

        filtered = filter_groups_by_name(data, 'n2')
        self.assertEqual(1, len(filtered))
        self.assertDictEqual({'Name': 'n2', 'System': 's2'}, filtered[0])

    def test_filter_systems_by_state(self):
        data = [
            {'Name': 'n1', 'State': 's1'},
            {'Name': 'n2', 'State': 's2'},
        ]
        filtered = filter_systems_by_state(data, None)
        self.assertListEqual(data, filtered)

        filtered = filter_systems_by_state(data, 's1')
        self.assertEqual(1, len(filtered))
        self.assertDictEqual({'Name': 'n1', 'State': 's1'}, filtered[0])

    @patch('h_vcs.vcs_utils.EnminstAgent')
    def test_get_group_info(self, m_agent):
        edata = [{'State': ['ONLINE'], 'Name': 'c1_g1', 'System': 's1'},
                 {'State': ['OFFLINE'], 'Name': 'c1_g2', 'System': 's2'}]
        m_agent.return_value.hagrp_state.side_effect = [([], edata)]
        _, data = get_group_info()
        self.assertEqual(2, len(data))
        self.assertListEqual(edata, data)

        m_agent.reset_mock()
        m_agent.return_value.hagrp_state.side_effect = [([], edata)]
        _, data = get_group_info(states='ONLINE')
        self.assertEqual(1, len(data))
        self.assertEqual('c1_g1', data[0]['Name'])

        m_agent.reset_mock()
        m_agent.return_value.hagrp_state.side_effect = [([], edata)]
        _, data = get_group_info(system='s1')
        self.assertEqual(1, len(data))
        self.assertEqual('c1_g1', data[0]['Name'])

        m_agent.reset_mock()
        m_agent.return_value.hagrp_state.side_effect = [([], edata)]
        _, data = get_group_info(group='c1_g2')
        self.assertEqual(1, len(data))
        self.assertEqual('c1_g2', data[0]['Name'])

    @patch('h_vcs.vcs_utils.EnminstAgent')
    def test_get_system_info(self, m_agent):
        edata = [{'State': ['RUNNING'], 'Name': 's1'},
                 {'State': ['LEAVING'], 'Name': 's2'}]

        m_agent.return_value.hasys_state.side_effect = [([], edata)]
        _, data = get_system_info()
        self.assertEqual(2, len(data))
        self.assertListEqual(edata, data)

        m_agent.reset_mock()
        m_agent.return_value.hasys_state.side_effect = [([], edata)]
        _, data = get_system_info(states='RUNNING')
        self.assertEqual(1, len(data))
        self.assertEqual('s1', data[0]['Name'])

    @patch('h_vcs.vcs_utils.EnminstAgent')
    def test_check_systems_exist(self, m_agent):
        self.assertIsNone(check_systems_exist(None))

        edata = [{'State': ['RUNNING'], 'Name': 's1'},
                 {'State': ['LEAVING'], 'Name': 's2'}]
        m_agent.return_value.hasys_state.side_effect = [([], edata)]
        try:
            check_systems_exist('s1')
        except Exception:
            self.fail('No error should have been raised!')

        m_agent.reset_mock()
        m_agent.return_value.hasys_state.side_effect = [([], edata)]
        self.assertRaises(SystemExit, check_systems_exist, 's3')

    def test_to_string(self):
        self.assertIn(VcsCodes.V_16_1_10600[VcsCodes.KEY_VCS_CODE],
                      VcsCodes.to_string(VcsCodes.V_16_1_10600))
        self.assertIn(VcsCodes.V_16_1_10600[VcsCodes.KEY_DESCRIPTION],
                      VcsCodes.to_string(VcsCodes.V_16_1_10600))

    def test_is_error(self):
        self.assertFalse(VcsCodes.is_error(VcsCodes.V_16_1_10600, ''))
        self.assertTrue(VcsCodes.is_error(VcsCodes.V_16_1_10600,
                                          VcsCodes.to_string(
                                              VcsCodes.V_16_1_10600)))
