import difflib
import pprint

from collections import OrderedDict
from mock import patch, call
from unittest2 import TestCase

from h_puppet.mco_agents import BaseAgent, McoAgentException, EnminstAgent, \
    VcsCmdApiAgent, FilemanagerAgent, PostgresAgent, Neo4jClusterMcoAgent, \
    PostgresMcoAgent, Neo4jFilesystemMcoAgent

node1 = '''
[{"statusmsg":"OK","action":"service_list","data":
{"out":"atd","retcode":0,"err":""},
"statuscode":0,"sender":"node-1","agent":"enminst"}]
'''


def get_mco_rdata(agent, action, sender, rc, stdout, stderr):
    return {
        "statusmsg": "OK",
        "action": action,
        "data": {
            "out": stdout,
            "retcode": rc,
            "err": stderr
        },
        "statuscode": 0,
        "sender": sender,
        "agent": agent
    }


def get_rpc_data(rc, stdout, stderr):
    return {
        'retcode': rc,
        'out': stdout,
        'err': stderr}


def assert_sequence_equal(pyunit, seq1, seq2, msg=None):  # pylint: disable=R0915
    seq_type_name = "sequence"

    differing = None
    len1 = len2 = 0
    try:
        len1 = len(seq1)
    except (TypeError, NotImplementedError):
        differing = 'First {0} has no length. Non-sequence?'.format(
                seq_type_name)

    if differing is None:
        try:
            len2 = len(seq2)
        except (TypeError, NotImplementedError):
            differing = 'Second {0} has no length. Non-sequence?'.format(
                    seq_type_name)

    if differing is None:
        if seq1 == seq2:
            return

        seq1_repr = repr(seq1)
        seq2_repr = repr(seq2)
        if len(seq1_repr) > 30:
            seq1_repr = seq1_repr[:30] + '...'
        if len(seq2_repr) > 30:
            seq2_repr = seq2_repr[:30] + '...'
        elements = (seq_type_name.capitalize(), seq1_repr, seq2_repr)
        differing = '%ss differ: %s != %s\n' % elements

        for i in xrange(min(len1, len2)):
            try:
                item1 = seq1[i]
            except (TypeError, IndexError, NotImplementedError):
                differing += (
                    '\nUnable to index element %d of first %s\n' %
                    (i, seq_type_name))
                break

            try:
                item2 = seq2[i]
            except (TypeError, IndexError, NotImplementedError):
                differing += ('\nUnable to index '
                              'element %d of second %s\n' % (
                                  i, seq_type_name))
                break

            if item1 != item2:
                differing += ('\nFirst differing element %d:\n%s\n%s\n' %
                              (i, item1, item2))
                break
        else:
            if len1 == len2 and type(seq1) != type(seq2):
                # The sequences are the same, but have differing types.
                return

        if len1 > len2:
            differing += ('\nFirst %s contains %d additional '
                          'elements.\n' % (seq_type_name, len1 - len2))
            try:
                differing += ('First extra element %d:\n%s\n' %
                              (len2, seq1[len2]))
            except (TypeError, IndexError, NotImplementedError):
                differing += ('Unable to index element %d '
                              'of first %s\n' % (len2, seq_type_name))
        elif len1 < len2:
            differing += ('\nSecond %s contains %d additional '
                          'elements.\n' % (seq_type_name, len2 - len1))
            try:
                differing += ('First extra element %d:\n%s\n' %
                              (len1, seq2[len1]))
            except (TypeError, IndexError, NotImplementedError):
                differing += ('Unable to index element %d '
                              'of second %s\n' % (len1, seq_type_name))
    standardmsg = ''
    if msg:
        standardmsg = msg + '\n'
    standardmsg += differing
    diffmsg = '\n' + '\n'.join(
            difflib.ndiff(pprint.pformat(seq1).splitlines(),
                          pprint.pformat(seq2).splitlines()))

    standardmsg += diffmsg
    pyunit.fail(standardmsg)


def assert_list_equal(pyunit, list1, list2, msg=None):
    """A list-specific equality assertion.

    Args:
        list1: The first list to compare.
        list2: The second list to compare.
        msg: Optional message to use on failure instead of a list of
                differences.

    """
    list1.sort()
    list2.sort()
    assert_sequence_equal(pyunit, list1, list2, msg=msg)


class TestBaseAgent(TestCase):
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_mco_exec(self, m_run_rpc_command):
        ba = BaseAgent('')
        expected = 'some_output'

        m_run_rpc_command.side_effect = [
            {'sender': {
                'errors': '', 'data': get_rpc_data(0, expected, 'err')}}
        ]
        data = ba.mco_exec('agent', ['groups=action'], 'sender')
        self.assertEqual(expected, data)

        m_run_rpc_command.side_effect = [
            {'sender1': {'errors': '',
                         'data': get_rpc_data(0, 's1', 'err')},
             'sender2': {'errors': '',
                         'data': get_rpc_data(0, 's2', 'err')}}
        ]
        data = ba.mco_exec('agent', ['groups=action'], ['sender1', 'sender2'])
        self.assertIn('sender1', data)
        self.assertEqual('s1', data['sender1'])
        self.assertIn('sender2', data)
        self.assertEqual('s2', data['sender2'])

        m_run_rpc_command.side_effect = [
            {'sender': {
                'errors': 'no!', 'data': get_rpc_data(0, expected, 'err')}}
        ]
        self.assertRaises(McoAgentException, ba.mco_exec,
                          'agent', ['groups=action'], 'sender')

        m_run_rpc_command.side_effect = [
            {'failed_node': {
                'errors': 'oops', 'data': get_rpc_data(0, expected, 'err')}}
        ]
        try:
            data = ba.mco_exec('agent', ['groups=action'], 'sender')
        except McoAgentException as exc:
            self.assertEqual(str(exc),
                "{'failed_node': {'errors': 'oops', 'data': {'retcode': 0,"
                " 'err': 'err', 'out': 'some_output'}}}")

    def test_get_exec_system(self):
        ba = BaseAgent('')
        self.assertEqual('b', ba.get_exec_system(None, 'b'))
        self.assertEqual('b', ba.get_exec_system('a', 'b'))
        self.assertEqual('a', ba.get_exec_system('a', None))

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_mco_exec_connection_exception(self, m_run_rpc_command):
        ba = BaseAgent('')
        m_run_rpc_command.side_effect = [IOError(4, '')]
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = '4'
            self.assertRaises(IOError, ba.mco_exec, 'blah', ['blah=blah'],
                              'blah')

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_mco_exec_exception(self, m_run_rpc_command):
        ba = BaseAgent('')
        m_run_rpc_command.side_effect = [IOError(3, '')]
        with patch('h_util.h_utils.Popen') as mock:
            process = mock.return_value
            process.returncode = '3'
            self.assertRaises(IOError, ba.mco_exec, 'blah', ['blah=blah'],
                              'blah')


class TestEnminstAgent(TestCase):
    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_get_grub_conf_lvs(self, m_mco):
        agent = EnminstAgent()
        m_mco.return_value = '\n'.join(['lv_a', 'lv_b', 'lv_c'])
        node = 'node1'
        lvs = agent.get_grub_conf_lvs(node)
        self.assertTrue(m_mco.called)
        self.assertEqual('lv_a\nlv_b\nlv_c', lvs)

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_haclus_list(self, m_run_rpc_command):
        agent = EnminstAgent()
        expected = 'a_cluster'
        m_run_rpc_command.side_effect = [
            {'sender': {'errors': '',
                        'data': get_rpc_data(0, expected, 'err')}}]
        cluster = agent.haclus_list('sender')
        self.assertEqual(expected, cluster)

        m_run_rpc_command.reset()
        m_run_rpc_command.side_effect = [
            {'sender': {'errors': '',
                        'data': get_rpc_data(1, expected, 'err')}}]
        self.assertRaises(McoAgentException, agent.haclus_list, ['sender'])

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_hagrp_list(self, m_run_rpc_command):
        agent = EnminstAgent()
        rdata = '\n'.join([
            'gp1   \t\tn1',
            '   ',
            'gp2   \t\tn1'
        ])
        m_run_rpc_command.side_effect = [
            {'sender': {'errors': '',
                        'data': get_rpc_data(0, rdata, 'err')}}]
        groups = agent.hagrp_list('sender')
        self.assertEqual(2, len(groups))
        self.assertIn('gp1', groups)
        self.assertIn('gp2', groups)

        m_run_rpc_command.reset()
        m_run_rpc_command.side_effect = [
            {'sender': {'errors': '',
                        'data': get_rpc_data(1, rdata, 'err')}}]
        self.assertRaises(McoAgentException, agent.hagrp_list, 'sender')

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_hagrp_display(self, m_run_rpc_command):
        agent = EnminstAgent()
        rdata = ['\n'.join([
            '#Group  Attribute System Value',
            'gp AdministratorGroups   global     ',
            'gp Parallel              global     1',
            'gp State                 node |ONLINE|',
            'gp VCSi3Info             node'
        ])]
        m_run_rpc_command.side_effect = [
            {'node1': {'errors': '',
                       'data': get_rpc_data(0, rdata, 'err')}}]
        info = agent.hagrp_display('gp', 'node1')
        self.assertIn('gp', info)
        self.assertIn('global', info['gp'])
        self.assertIn('node', info['gp'])

        self.assertIn('AdministratorGroups', info['gp']['global'])
        self.assertEqual('', info['gp']['global']['AdministratorGroups'])
        self.assertIn('Parallel', info['gp']['global'])
        self.assertEqual('1', info['gp']['global']['Parallel'])

        self.assertIn('VCSi3Info', info['gp']['node'])
        self.assertEqual('', info['gp']['node']['VCSi3Info'])
        self.assertIn('State', info['gp']['node'])
        self.assertEqual('|ONLINE|', info['gp']['node']['State'])

        m_run_rpc_command.reset()
        m_run_rpc_command.side_effect = [
            {'node1': {'errors': '',
                       'data': get_rpc_data(1, rdata, 'err')}}]
        self.assertRaises(McoAgentException, agent.hagrp_display, 'gp',
                          'node1')

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_hagrp_history(self, m_run_rpc_command):
        agent = EnminstAgent()
        rdata = {
            "gp": [
                {
                    "id": "V-16-1-10447",
                    "date": "Thu Apr 16 19:26:50 2015",
                    "info": "Group gp is online on system n1"
                },
            ],
        }
        m_run_rpc_command.side_effect = [
            {'node1': {'errors': '', 'data': get_rpc_data(0, rdata, 'err')}}]
        history = agent.hagrp_history('gp', 'node1')
        self.assertIn('gp', history)
        self.assertEqual(1, len(history['gp']))
        self.assertIn('id', history['gp'][0])
        self.assertIn('date', history['gp'][0])
        self.assertIn('info', history['gp'][0])
        self.assertEqual('V-16-1-10447', history['gp'][0]['id'])

        m_run_rpc_command.reset()
        m_run_rpc_command.side_effect = [
            {'node1': {'errors': '', 'data': get_rpc_data(1, rdata, 'err')}}]
        self.assertRaises(McoAgentException, agent.hagrp_history, 'gp',
                          'node1')

    def test_get_states(self):
        self.assertEqual([], EnminstAgent.get_states(''))
        self.assertEqual(['a'], EnminstAgent.get_states('a   '))
        self.assertEqual(['a'], EnminstAgent.get_states('|a'))
        self.assertEqual(['a'], EnminstAgent.get_states('a|'))
        self.assertEqual(['a'], EnminstAgent.get_states('|a|'))
        self.assertEqual(['a', 'b'], EnminstAgent.get_states('a|b'))

    def mock_get_state(self, mock_mco, headers, systems):
        out = ' '.join(headers) + '\n'
        for s in systems:
            line = ''
            for h in headers:
                line += ' ' + s[h]
            out += '\n' + line
        mock_mco.return_value = [
            {'data': {'err': '', 'retcode': 0, 'out': out},
             "statuscode": 0,
             "sender": 'some_host',
             "action": "df"}]

    @patch('h_puppet.mco_agents.discover_peer_nodes')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test__vcs_state_2(self, m_run_rpc_command, m_discover_peer_nodes):
        agent = EnminstAgent()
        rdata = '\n'.join([
            'gp1   \t\tn1',
            '   ',
            'gp2   \t\tn1'
        ])
        m_run_rpc_command.return_value = {
            'node1': {'errors': '', 'data': get_rpc_data(0, rdata, 'err')}}
        groups = agent._vcs_state('command', 'node1')
        self.assertEqual(2, len(groups))
        self.assertTrue(any('gp1' in group for group in groups))

        m_discover_peer_nodes.return_value = ['node1', 'node2']
        groups = agent._vcs_state('command', None)
        self.assertEqual(2, len(groups))
        self.assertTrue(any('gp1' in group for group in groups))

    def test_hasys_state(self):
        with patch('h_puppet.mco_agents.BaseAgent.mco_exec') as m_mco:
            m_mco.return_value = """#Group  Attribute  System Value
            Grp_CS_service  State                 db-1  |ONLINE|
            Grp_CS_service   State        db-1  |ONLINE|
            """
            agent = EnminstAgent()
            headers, states = agent.hasys_state('host')
            self.assertTrue(any('Name' in header for header in headers))
            self.assertTrue(any('State' in header for header in headers))
            self.assertTrue(any('db-1' in state['Name'] for state in states))

    def test_hagrp_state(self):
        with patch('h_puppet.mco_agents.BaseAgent.mco_exec') as m_mco:
            m_mco.return_value = """#Group  Attribute  System Value
            Grp_CS_service  State                 db-1  |ONLINE|
            Grp_CS_service   State        db-1  |ONLINE|
            """
            agent = EnminstAgent()
            headers, states = agent.hagrp_state('host')
            self.assertTrue(any('Name' in header for header in headers))
            self.assertTrue(any('System' in header for header in headers))
            self.assertTrue(any('State' in header for header in headers))

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hagrp_online(self, mco):
        agent = EnminstAgent()
        agent.hagrp_online('group', 'system')

        mco.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hagrp_online, 'group',
                          'system')

        mco.reset_mock()
        mco.side_effect = None
        agent.hagrp_online('group', 'system', propagate=True)
        mco.assert_has_calls([
            call('hagrp_online', ['group_name=group', 'system=system',
                                  'propagate=true'], 'system')
        ], any_order=True)

        mco.side_effect = ['aww V-16-1-40229 boo!']
        self.assertRaises(McoAgentException, agent.hagrp_online,
                          'group', 'system')

        mco.side_effect = IOError('ee')
        self.assertRaises(IOError, agent.hagrp_online,
                          'group', 'system')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hagrp_clear(self, mco):
        agent = EnminstAgent()
        mco.return_value = [
            {"data": {"retcode": 0, "err": "", "out": ""}, "statuscode": 0,
             "sender": "eps-1", "agent": "enminst", "statusmsg": "OK",
             "action": "hagrp_clear"}]
        agent.hagrp_clear('group', 'system')
        mco.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hagrp_online, 'group',
                          'system')

        mco.side_effect = IOError('error')
        self.assertRaises(IOError, agent.hagrp_clear, 'group', 'system')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hagrp_offline(self, mco):
        agent = EnminstAgent()
        agent.hagrp_offline('group', 'system')
        mco.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hagrp_offline,
                          'group',
                          'system')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hagrp_switch(self, mco):
        agent = EnminstAgent()

        mco.return_value = [
            {"data": {"retcode": 0, "err": "", "out": ""}, "statuscode": 0,
             "sender": "eps1", "agent": "enminst", "statusmsg": "OK",
             "action": "hagrp_switch"}]
        agent.hagrp_switch('group', 'system', 'system')
        mco.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hagrp_switch, 'group',
                          'system', 'system')

        mco.side_effect = IOError({'err': 'err_msg'})
        self.assertRaises(McoAgentException, agent.hagrp_switch, 'group',
                          'system', 'system')

        mco.side_effect = IOError(1)
        self.assertRaises(IOError, agent.hagrp_switch, 'group',
                          'system', 'system')

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_hagrp_wait(self, m_run_rpc_command):
        vcsapiagent = VcsCmdApiAgent()
        m_run_rpc_command.return_value = {
            'system':
                {'errors': None,
                 'data': {'retcode': 0, 'out': 'results'}}
        }
        vcsapiagent.hagrp_wait('group', 'system', 'blah')

        m_run_rpc_command.assert_has_calls([
            call(['system'], 'vcs_cmd_api', 'hagrp_wait',
                 {'state': 'blah', 'node_name': 'system', 'timeout': '60',
                  'group_name': 'group'}, retries=0, timeout=65)],
                any_order=True)

        m_run_rpc_command.reset_mock()
        vcsapiagent.hagrp_wait('group', 'system', 'blah',
                               timeout=30)
        m_run_rpc_command.assert_has_calls([
            call(['system'], 'vcs_cmd_api', 'hagrp_wait',
                 {'state': 'blah', 'node_name': 'system', 'timeout': '30',
                  'group_name': 'group'}, retries=0, timeout=35)],
                any_order=True)

        m_run_rpc_command.reset_mock()
        m_run_rpc_command.return_value = {
            'system':
                {'errors': None,
                 'data': {'retcode': 1, 'out': 'results'}}
        }
        self.assertRaises(McoAgentException, vcsapiagent.hagrp_wait,
                          'group', 'system', 'blah')

    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makerw')
    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makero')
    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hagrp_freeze(self, m_mco_exec, ro, rw):
        agent = EnminstAgent()
        agent.hagrp_freeze('', '')
        self.assertFalse(rw.called)
        self.assertFalse(ro.called)
        self.assertTrue(m_mco_exec.called)

        agent.hagrp_freeze('', '', persistent=True)
        self.assertTrue(rw.called)
        self.assertTrue(ro.called)
        self.assertTrue(m_mco_exec.called)

        m_mco_exec.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hagrp_freeze, '', '')

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.hagrp_freeze, '', '')

    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makerw')
    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makero')
    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hagrp_unfreeze(self, m_mco_exec, ro, rw):
        agent = EnminstAgent()
        agent.hagrp_unfreeze('', '')
        self.assertFalse(rw.called)
        self.assertFalse(ro.called)
        self.assertTrue(m_mco_exec.called)

        agent.hagrp_unfreeze('', '', persistent=True)
        self.assertTrue(rw.called)
        self.assertTrue(ro.called)
        self.assertTrue(m_mco_exec.called)

        m_mco_exec.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hagrp_unfreeze, '', '')

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.hagrp_unfreeze, '', '')

    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makerw')
    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makero')
    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hasys_freeze(self, m_mco_exec, ro, rw):
        agent = EnminstAgent()
        agent.hasys_freeze('')
        self.assertFalse(rw.called)
        self.assertFalse(ro.called)
        self.assertTrue(m_mco_exec.called)

        agent.hasys_freeze('', persistent=True)
        self.assertTrue(rw.called)
        self.assertTrue(ro.called)
        self.assertTrue(m_mco_exec.called)

        m_mco_exec.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hasys_freeze, '')

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.hasys_freeze, '')

    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makerw')
    @patch('h_puppet.mco_agents.VcsCmdApiAgent.haconf_makero')
    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hasys_unfreeze(self, m_mco_exec, ro, rw):
        agent = EnminstAgent()
        agent.hasys_unfreeze('')
        self.assertFalse(rw.called)
        self.assertFalse(ro.called)
        self.assertTrue(m_mco_exec.called)

        agent.hasys_unfreeze('', persistent=True)
        self.assertTrue(rw.called)
        self.assertTrue(ro.called)
        self.assertTrue(m_mco_exec.called)

        m_mco_exec.side_effect = McoAgentException
        self.assertRaises(McoAgentException, agent.hasys_unfreeze, '')

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.hasys_unfreeze, '')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_hasys_display(self, m_mco_exec):
        m_mco_exec.side_effect = [
            {'s1': '\n'.join([
                '#System    Attribute             Value',
                's1 a       v',
                's1 b     CPU    3.40'
            ])}
        ]
        agent = EnminstAgent()
        data = agent.hasys_display([''])
        self.assertIn('s1', data)
        self.assertEqual('v', data['s1']['a'])
        self.assertEqual('CPU    3.40', data['s1']['b'])

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_haconf_makerw(self, m_mco_exec):
        agent = VcsCmdApiAgent()
        agent.haconf_makerw('')
        self.assertTrue(m_mco_exec.called)

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.haconf_makerw, '')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_haconf_makero(self, m_mco_exec):
        agent = VcsCmdApiAgent()
        agent.haconf_makero('')
        self.assertTrue(m_mco_exec.called)

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.haconf_makero, '')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_lock(self, m_mco_exec):
        agent = VcsCmdApiAgent()
        agent.lock('sys1', -1)
        m_mco_exec.assert_has_calls([
            call('lock', ['sys=sys1', 'switch_timeout=-1'], 'sys1')
        ])

        m_mco_exec.side_effect = IOError('this is expected')
        self.assertRaises(IOError, agent.lock, 'sys1', 300)

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_unlock(self, m_mco_exec):
        agent = VcsCmdApiAgent()
        agent.unlock('sys1')
        m_mco_exec.assert_has_calls([
            call('unlock', ['sys=sys1', 'nic_wait_timeout=300'], 'sys1')
        ])

        m_mco_exec.reset_mock()
        agent.unlock('sys1', 42)
        m_mco_exec.assert_has_calls([
            call('unlock', ['sys=sys1', 'nic_wait_timeout=42'], 'sys1')
        ])

        m_mco_exec.side_effect = IOError('this is expected')
        self.assertRaises(IOError, agent.unlock, 'sys1')

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_lvs_list(self, m_mco_exec):
        agent = EnminstAgent()
        agent.lvs_list(['h1'], 'opt1,opt2')
        m_mco_exec.assert_has_calls([
            call('lvs_list', ['lv_opts=opt1,opt2'], mco_exec_host=['h1'])
        ])

        m_mco_exec.side_effect = IOError
        self.assertRaises(IOError, agent.lvs_list, [], '')

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_runlevel(self, m_run_rpc_command):
        rlevels = {
            'out': '3',
            'retcode': 0,
            'err': None
        }
        m_run_rpc_command.return_value = {
            'node1': {'errors': '', 'data': get_rpc_data(0, rlevels, 'err')}}

        agent = EnminstAgent()
        data = agent.runlevel()
        self.assertIn('node1', data)
        self.assertEqual('3', data['node1']['out'])

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_scan_device_tree(self, m_run_rpc_command):
        rlevels = {
            'out': '3',
            'retcode': 0,
            'err': None
        }
        m_run_rpc_command.return_value = {
            'node1': {'errors': '', 'data': get_rpc_data(0, rlevels, 'err')}}

        agent = EnminstAgent()
        data = agent.scan_device_tree()
        self.assertIn('node1', data)
        self.assertEqual('3', data['node1']['out'])

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_service_list(self, m_run_rpc_command):
        rlevels = {
            'out': 's1\ns2',
            'retcode': 0,
            'err': None
        }
        m_run_rpc_command.return_value = {
            'node1': {'errors': '', 'data': get_rpc_data(0, rlevels, 'err')}}

        agent = EnminstAgent()
        data = agent.service_list('3')
        self.assertIn('node1', data)
        self.assertEqual('s1\ns2', data['node1']['out'])

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_check_service(self, m_run_rpc_command):
        rlevels = {
            'out': {'s1': 0},
            'retcode': 0,
            'err': None
        }
        m_run_rpc_command.return_value = {
            'node1': {'errors': '', 'data': get_rpc_data(0, rlevels, 'err')}}

        agent = EnminstAgent()
        data = agent.check_service('s1')
        self.assertIn('node1', data)
        self.assertIn('s1', data['node1']['out'])
        self.assertEqual(0, data['node1']['out']['s1'])

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_shutdown_host(self, m_mco):
        agent = EnminstAgent()
        m_mco.return_value = ['a', 'b', 'c']
        host = 'host1'
        ret = agent.shutdown_host(host)
        self.assertTrue(m_mco.called)
        self.assertEqual(str(['a', 'b', 'c']), ret)

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_get_active_and_prime_bond_mbr(self, m_mco):
        agent = EnminstAgent()

        m_mco.return_value = '\n'.join([
            'Primary Slave: eth0 (primary_reselect always)',
            'Currently Active Slave: eth0'
            ])

        expected_result = OrderedDict([
            ('Primary Member', 'eth0'),
            ('Active Member', 'eth0')
        ])
        actual_result = agent.get_active_and_prime_bond_mbr('host')

        self.assertTrue(m_mco.called)
        self.assertEqual(actual_result, expected_result)

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_get_bond_interface_info(self, m_mco):
        agent = EnminstAgent()
        m_mco.return_value = '\n'.join([
            'Slave Interface: eth0',
            'MII Status: up',
            'Speed: 25000 Mbps',
            '--',
            'Slave Interface: eth2',
            'MII Status: up',
            'Speed: 25000 Mbps',
            ])

        expected_result = [
            OrderedDict([
                ('Member Interface', 'eth0'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps'),
            ]),
            OrderedDict([
                ('Member Interface', 'eth2'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps'),
            ])
        ]
        actual_result = agent.get_bond_interface_info('host')

        self.assertTrue(m_mco.called)
        self.assertEqual(actual_result, expected_result)


class TestFilemanagerAgent(TestCase):
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_exists(self, m_run_rpc_command):
        rpc_results = {'h1': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                     'out': True}},
                       'h2': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                     'out': False}}}
        m_run_rpc_command.return_value = rpc_results

        agent = FilemanagerAgent()
        results = agent.exists('somefile', ['h1', 'h2'])
        self.assertIn('h1', results)
        self.assertTrue(results['h1'])
        self.assertIn('h2', results)
        self.assertFalse(results['h2'])

    @patch('h_puppet.mco_agents.BaseAgent.mco_exec')
    def test_move(self, m_mco_exec):
        agent = FilemanagerAgent()
        agent.move('/a', '/b', 'sys1', command_timeout=1)
        m_mco_exec.assert_has_calls([call('move', ['src=/a', 'dest=/b'],
                                          'sys1', rpc_command_timeout=1)])


class TestPostgresAgent(TestCase):
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_call_postgres_service_reload(self, m_run_rpc_command):
        rpc_results = {'node1': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                     'out': ''}}}
        m_run_rpc_command.return_value = rpc_results

        agent = PostgresAgent()
        results = agent.call_postgres_service_reload('node1')
        self.assertTrue(m_run_rpc_command.called)


class TestNeo4jClusterMcoAgent(TestCase):
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_get_cluster_overview(self, m_run_rpc_command):
        rpc_results = {'node1': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                        'out': ''}}}
        m_run_rpc_command.return_value = rpc_results

        agent = Neo4jClusterMcoAgent('node1')
        results = agent.get_cluster_overview()

        self.assertTrue(m_run_rpc_command.called)


class TestPostgresMcoAgent(TestCase):
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_get_postgres_mnt_perc_used(self, m_run_rpc_command):
        rpc_results = {'node1': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                     'out': ''}}}
        m_run_rpc_command.return_value = rpc_results

        agent = PostgresMcoAgent('node1')
        results = agent.get_postgres_mnt_perc_used()
        self.assertTrue(m_run_rpc_command.called)


class TestNeo4jFilesystemMcoAgent(TestCase):
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_get_filesystem_status(self, m_run_rpc_command):
        rpc_results = {'node1': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                        'out': {}}}}
        m_run_rpc_command.return_value = rpc_results
        agent = Neo4jFilesystemMcoAgent()
        result = agent.get_filesystem_status("node1", ["arg1=arg1", "arg1=arg1"])
        self.assertTrue(m_run_rpc_command.called)
