import os
from mock import MagicMock, patch, call
from os.path import join, exists
from simplejson import dumps, loads
from tempfile import gettempdir
from unittest2 import TestCase

# from agent.enminst import RPCAgent, Enminst, VCSCommandException
from agent.base_agent import RPCAgent
from agent.enminst import Enminst, VCSCommandException


class MockRPCAgent(RPCAgent):
    def __init__(self):
        super(MockRPCAgent, self).__init__()
        self.exit_enabled = True

    def enable_exits(self, enabled):
        self.exit_enabled = enabled

    def mock_action(self, request):
        return {'a': 'b'}

    def exit(self, exit_value):
        if self.exit_enabled:
            super(MockRPCAgent, self).exit(exit_value)


class TestRPCAgent(TestCase):
    def setUp(self):
        self.MCOLLECTIVE_REQUEST_FILE = join(gettempdir(),
                                             'MCOLLECTIVE_REQUEST_FILE')
        self.MCOLLECTIVE_REPLY_FILE = join(gettempdir(),
                                           'MCOLLECTIVE_REPLY_FILE')
        os.environ['MCOLLECTIVE_REQUEST_FILE'] = self.MCOLLECTIVE_REQUEST_FILE
        os.environ['MCOLLECTIVE_REPLY_FILE'] = self.MCOLLECTIVE_REPLY_FILE
        if exists(self.MCOLLECTIVE_REPLY_FILE):
            os.remove(self.MCOLLECTIVE_REPLY_FILE)

    def tearDown(self):
        if exists(self.MCOLLECTIVE_REQUEST_FILE):
            os.remove(self.MCOLLECTIVE_REQUEST_FILE)
        if exists(self.MCOLLECTIVE_REPLY_FILE):
            os.remove(self.MCOLLECTIVE_REPLY_FILE)

    def setupRequest(self, request):
        with open(self.MCOLLECTIVE_REQUEST_FILE, 'w') as _f:
            _f.write(request)

    def test_action(self):
        self.setupRequest(dumps({
            'action': 'mock_action',
            'data': {}
        }))
        agent = MockRPCAgent()
        agent.enable_exits(False)
        self.assertFalse(exists(self.MCOLLECTIVE_REPLY_FILE))
        with self.assertRaises(SystemExit) as sysexit:
            agent.action()
        self.assertEqual(sysexit.exception.message, 0)
        self.assertTrue(exists(self.MCOLLECTIVE_REPLY_FILE))
        with open(self.MCOLLECTIVE_REPLY_FILE) as _rf:
            rdata = loads('\n'.join(_rf.readlines()))
            self.assertDictEqual(rdata, agent.mock_action({}))

        self.setupRequest(dumps({
            'action': 'vvvvvvvvvvvvvvvvvvvvv',
            'data': {}
        }))
        agent.enable_exits(True)
        with self.assertRaises(SystemExit) as sysexit:
            agent.action()
        self.assertNotEqual(sysexit.exception, 0)


class TestEnminst(TestCase):
    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hagrp_display_torf135033(self, m_run_vcs_command):
        inst = Enminst()
        m_run_vcs_command.side_effect = [
            (1, 'stdout-1', 'stderr-1'),
            (0, 'stdout-0', 'stderr-0')
        ]
        group_data = inst.hagrp_display({'groups': 'group1,group2'})
        self.assertEqual(0, group_data['retcode'])
        self.assertEqual(2, len(group_data['out']))
        self.assertEqual('group1 stdout-1 stderr-1', group_data['out'][0])
        self.assertEqual('stdout-0', group_data['out'][1])

    @patch('agent.base_agent.Popen')
    def test_run_vcs_command_ok(self, popen):
        inst = Enminst()
        popen.return_value.communicate.return_value = '_stdout_', '_stderr'
        popen.return_value.returncode = 0
        returncode, stdout, stderr = inst.run_vcs_command('cmd')
        self.assertEqual(0, returncode)
        self.assertEqual('_stdout_', stdout)
        self.assertEqual('_stderr', stderr)

    @patch('agent.base_agent.Popen')
    def test_run_vcs_command_errors(self, m_open):
        inst = Enminst()

        m_open.return_value.communicate.return_value = '_stdout_', '_stderr'
        m_open.return_value.returncode = 1

        self.assertRaises(VCSCommandException, inst.run_vcs_command, 'cmd')

        _rc, _stdout, _stderr = inst.run_vcs_command('cmd', ignore_errors=True)
        self.assertEqual(1, _rc)
        self.assertEqual('_stdout_', _stdout)
        self.assertEqual('_stderr', _stderr)

    @patch('agent.base_agent.Popen')
    def test_run_vcs_command_exception(self, popen):
        inst = Enminst()
        popen.return_value.communicate.return_value = '_stdout_', '_stderr'
        popen.return_value.returncode = 1
        self.assertRaises(VCSCommandException, inst.run_vcs_command, 'cccc')

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hagrp_display(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, 'hagrp_list', '')]
        result = inst.hagrp_display({'groups': 'g1'})
        self.assertEqual(0, result['retcode'])
        self.assertEqual('', result['err'])
        self.assertEqual(['hagrp_list'], result['out'])
        run_vcs_command.side_effect = [(1, 'hagrp_list', '')]
        result = inst.hagrp_display({'groups': 'g1'})
        self.assertEqual(0, result['retcode'])

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hagrp_add_triggers_enabled(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, '', ''),
                                       (0, '', ''),
                                       (0, '', ''),
                                       (0, '', '')]
        result = inst.hagrp_add_triggers_enabled({'group_name': 'g1',
                                     'attribute_val':'PREONLINE'})
        self.assertEqual(0, result['retcode'])
        self.assertEqual('', result['err'])
        self.assertEqual('', result['out'])
        self.assertEqual(run_vcs_command.call_count, 4)
        self.assertEqual(run_vcs_command.call_args_list[0], call(['haconf', '-makerw']))
        self.assertEqual(run_vcs_command.call_args_list[1],
        call(['hagrp', '-modify', 'g1', 'TriggersEnabled', '-add', 'PREONLINE'],
            expected_errors=['V-16-1-10563'], rewrite_retcode=True))
        self.assertEqual(run_vcs_command.call_args_list[2], call(['haconf', '-dump', '-makero']))
        self.assertEqual(run_vcs_command.call_args_list[3],
            call(['haclus', '-wait', 'DumpingMembership', '0', '-time', '60']))

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hagrp_del_triggers_enabled(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, '', ''),
                                       (0, '', ''),
                                       (0, '', ''),
                                       (0, '', '')]
        result = inst.hagrp_delete_triggers_enabled({'group_name': 'g1',
                                     'attribute_val':'PREONLINE'})
        self.assertEqual(0, result['retcode'])
        self.assertEqual('', result['err'])
        self.assertEqual('', result['out'])
        self.assertEqual(run_vcs_command.call_count, 4)
        self.assertEqual(run_vcs_command.call_args_list[0], call(['haconf', '-makerw']))
        self.assertEqual(run_vcs_command.call_args_list[1],
        call(['hagrp', '-modify', 'g1', 'TriggersEnabled', '-delete', 'PREONLINE'],
            expected_errors=['VCS WARNING V-16-1-12130', 'V-16-1-10566'], rewrite_retcode=True))
        self.assertEqual(run_vcs_command.call_args_list[2], call(['haconf', '-dump', '-makero']))
        self.assertEqual(run_vcs_command.call_args_list[3],
        call(['haclus', '-wait', 'DumpingMembership', '0', '-time', '60']))

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hagrp_modify(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, '', ''),
                                       (0, '', ''),
                                       (0, '', ''),
                                       (0, '', ''),
                                       (0, '', '')]

        result = inst.hagrp_modify({'group_name': 'g1',
                                   'attribute': 'PreonlineTimeout',
                                    'attribute_val':'1500'})
        self.assertEqual(0, result['retcode'])
        self.assertEqual('', result['err'])
        self.assertEqual('', result['out'])
        self.assertEqual(run_vcs_command.call_count, 5)
        self.assertEqual(run_vcs_command.call_args_list[0],
            call(['hagrp', '-value', 'g1', 'PreonlineTimeout']))
        self.assertEqual(run_vcs_command.call_args_list[1],
            call(['haconf', '-makerw']))
        self.assertEqual(run_vcs_command.call_args_list[2],
            call(['hagrp', '-modify', 'g1', 'PreonlineTimeout', '1500']))
        self.assertEqual(run_vcs_command.call_args_list[3], call(['haconf', '-dump', '-makero']))
        self.assertEqual(run_vcs_command.call_args_list[4],
            call(['haclus', '-wait', 'DumpingMembership', '0', '-time', '60']))

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_cluster_app_agent_num_threads(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, '', ''),
                                       (0, '', ''),
                                       (0, '', ''),
                                       (0, '', '')]
        result = inst.cluster_app_agent_num_threads({'app_agent_num_threads': '50'})
        self.assertEqual(0, result['retcode'])
        self.assertEqual('', result['err'])
        self.assertEqual('', result['out'])
        self.assertEqual(run_vcs_command.call_count, 4)
        self.assertEqual(run_vcs_command.call_args_list[0], call(['haconf', '-makerw']))
        self.assertEqual(run_vcs_command.call_args_list[1],
        call(['hatype', '-modify', 'Application', 'NumThreads', '50']))
        self.assertEqual(run_vcs_command.call_args_list[2], call(['haconf', '-dump', '-makero']))
        self.assertEqual(run_vcs_command.call_args_list[3],
        call(['haclus', '-wait', 'DumpingMembership', '0', '-time', '60']))

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_haconf_False(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, '', '')]
        rc, err, out = inst._haconf(False)
        self.assertEqual(0, rc)
        self.assertEqual('', err)
        self.assertEqual('', out)
        self.assertEqual(run_vcs_command.call_count, 1)
        self.assertEqual(run_vcs_command.call_args_list[0], call(['haconf', '-makerw']))

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_haconf_True(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0, '', ''),
                                       (0, '', '')]
        rc, err, out = inst._haconf(True)
        self.assertEqual(0, rc)
        self.assertEqual('', err)
        self.assertEqual('', out)
        self.assertEqual(run_vcs_command.call_count, 2)
        self.assertEqual(run_vcs_command.call_args_list[0], call(['haconf', '-dump', '-makero']))
        self.assertEqual(run_vcs_command.call_args_list[1],
        call(['haclus', '-wait', 'DumpingMembership', '0', '-time', '60']))

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_get_engine_logs(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(0,
                                        'engine_A\nsome_log\nDiskGroup_A'
                                        '\n\nengine_B',
                                        '')]
        rc, logs = inst.get_engine_logs()
        self.assertEqual(0, rc)
        self.assertIn('engine_A', logs)
        self.assertNotIn('DiskGroup_A', logs)
        self.assertIn('engine_B', logs)
        run_vcs_command.side_effect = [(1, '', '')]
        rc, logs = inst.get_engine_logs()
        self.assertEqual(1, logs['retcode'])

    def test_hagrp_history(self):
        inst = Enminst()
        m_run_vcs_command = MagicMock()
        inst.run_vcs_command = m_run_vcs_command

        hamsg = [
            'Tue 12 May 2015 07:19:29 PM IST VCS NOTICE V-16-1-10447 Group '
            'Grp_CS_gp1 is online on system s-1'
        ]

        m_run_vcs_command.side_effect = [
            (0, 'engine_A', ''),
            (0, '\n'.join(hamsg), '')
        ]

        history = inst.hagrp_history({})
        self.assertEqual(0, history['retcode'])
        self.assertIn('Grp_CS_gp1', history['out'])
        self.assertEqual('V-16-1-10447', history['out']['Grp_CS_gp1'][0]['id'])

        m_run_vcs_command.reset_mock()
        m_run_vcs_command.side_effect = [
            (0, 'engine_A', ''),
            (1, '\n'.join(hamsg), '')
        ]
        history = inst.hagrp_history({'group': 'gp1'})
        self.assertEqual(1, history['retcode'])

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hagrp_switch(self, run_vcs_command):
        inst = Enminst()
        run_vcs_command.side_effect = [(1, 'stdout', 'stderr')]
        result = inst.hagrp_switch({'groups': 'g1'})
        self.assertEqual(1, result['retcode'])
        self.assertEqual('stdout', result['out'])
        self.assertEqual('stderr', result['err'])

        run_vcs_command.side_effect = [(0, 'stdout', 'stderr')]
        result = inst.hagrp_switch({'groups': 'g1'})
        self.assertEqual(['stdout'], result['out'])
        self.assertEqual('', result['err'])

    @patch('agent.enminst.Enminst.run_vcs_command')
    def test_hasys_display(self, m_run_vcs_command):
        agent = Enminst()
        m_run_vcs_command.side_effect = [
            (0, 'stdout', 'stderr')
        ]
        json = agent.hasys_display({'systems': 's1'})
        self.assertEqual(0, json['retcode'])
        self.assertEqual('', json['err'])
        self.assertEqual('stdout', json['out']['s1'])

        m_run_vcs_command.reset_mock()
        m_run_vcs_command.side_effect = [
            (1, 'stdout', 'stderr')
        ]
        json = agent.hasys_display({'systems': 's1'})
        self.assertEqual(1, json['retcode'])
        self.assertEqual('stderr', json['err'])

        m_run_vcs_command.reset_mock()
        m_run_vcs_command.side_effect = [
            (0, 'stdout', 'stderr')
        ]
        json = agent.hasys_display({})
        self.assertEqual(0, json['retcode'])
        self.assertEqual('stderr', json['err'])
        self.assertEqual('stdout', json['out'])

    @patch('agent.enminst.Enminst.execute')
    def test_check_service(self, m_execute):
        inst = Enminst()

        m_execute.side_effect = [
            (0, None, None),
            (1, None, None)
        ]

        rc = inst.check_service({'service': 'sa, sb'})
        self.assertEqual(0, rc['out']['sa'])
        self.assertEqual(1, rc['out']['sb'])
