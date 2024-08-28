import logging
from socket import gethostname

from mock import patch, MagicMock, call
from unittest2 import TestCase

from h_puppet.h_puppet import discover_all_nodes, discover_peer_nodes, \
    puppet_status, puppet_enable_disable, puppet_runall, main, _init_logging, \
    sync_agents_interrupt, InterceptHandler, puppet_trigger_wait
from h_puppet.mco_agents import McoAgentException
from h_util.h_utils import ExitCodes


class TestInterceptHandler(TestCase):
    def test_emit(self):
        class MockedInterceptHandler(InterceptHandler):
            def format(self, record):
                print record

        h = MockedInterceptHandler()
        m_record = logging.LogRecord('name', 0, '', 123,
                                     'n1 completed a Puppet run: '
                                     '1441026989 < 1441027100',
                                     None, None)

        h.emit(m_record)
        self.assertTrue('1441026989' in m_record.getMessage())
        self.assertTrue('1441027100' in m_record.getMessage())


class TestMcoAgentException(TestCase):

    def test_mco_agent_exception_simple(self):

        def simple_exc_raise():
            raise McoAgentException("ERROR")

        exc = None
        try:
            simple_exc_raise()
        except Exception as exc:
            pass
        self.assertTrue(exc is not None, exc)
        self.assertTrue(isinstance(exc, McoAgentException), exc)
        self.assertTrue(hasattr(exc, 'err'), exc)
        self.assertEquals(exc.err, str(exc), exc)

    def test_mco_agent_exception_data(self):

        def data_exc_raise():
            raise McoAgentException({'retcode': 1, 'out': '',
                                     'err': 'ERROR WITHIN DICT'})
        exc = None
        try:
            data_exc_raise()
        except Exception as exc:
            pass
        self.assertTrue(exc is not None, exc)
        self.assertTrue(isinstance(exc, McoAgentException), exc)
        self.assertTrue(hasattr(exc, 'err'), exc)
        self.assertTrue(hasattr(exc, 'data'), exc)
        self.assertTrue(isinstance(exc.data, dict), exc)
        self.assertTrue('retcode' in exc.data, exc)
        self.assertTrue('out' in exc.data, exc)
        self.assertTrue('err' in exc.data, exc)
        self.assertEquals(exc.data['retcode'], 1, exc)
        self.assertEquals(exc.data['out'], '', exc)
        self.assertEquals(exc.data['err'], 'ERROR WITHIN DICT', exc)
        self.assertNotEquals(exc.err, str(exc), exc)
        self.assertEquals(exc.err, 'ERROR WITHIN DICT', exc)

    def test_mco_agent_exception_data_2(self):

        def data_exc_raise():
            raise McoAgentException({'node':
                                     {'errors': 'ERROR WITHIN WITHIN DICT'}})
        exc = None
        try:
            data_exc_raise()
        except Exception as exc:
            pass
        self.assertTrue(exc is not None, exc)
        self.assertTrue(isinstance(exc, McoAgentException), exc)
        self.assertTrue(hasattr(exc, 'err'), exc)
        self.assertTrue(hasattr(exc, 'data'), exc)
        self.assertTrue(isinstance(exc.data, dict), exc)
        self.assertTrue(len(exc.data.values()) == 1, exc)
        self.assertTrue(all([isinstance(v, dict) for v in exc.data.values()]), exc)
        self.assertTrue(isinstance(exc.data.values()[0], dict), exc)
        self.assertTrue('errors' in exc.data.values()[0], exc)
        self.assertEquals(exc.data.values()[0]['errors'],
                          'ERROR WITHIN WITHIN DICT', exc)
        self.assertNotEquals(exc.err, str(exc), exc)
        self.assertEquals(exc.err, 'ERROR WITHIN WITHIN DICT', exc)


class TestPuppet(TestCase):
    @patch('h_puppet.h_puppet.fileConfig')
    @patch('h_puppet.h_puppet.LitpLogger')
    def test__init_logging(self, m_litplogger, m_fileconfig):
        logger = _init_logging('')
        self.assertTrue(logger.trace.addHandler.called)

    @patch('h_puppet.h_puppet.exec_process')
    def test_discover_all_nodes(self, ep):
        ep.side_effect = ['a\nb\nlms']
        nodes = discover_all_nodes(include_lms=True, lms_hostname='lms')
        self.assertEqual(3, len(nodes))
        self.assertIn('a', nodes)
        self.assertIn('b', nodes)
        self.assertIn('lms', nodes)

        ep.rest()
        ep.side_effect = ['a\nb\n{0}'.format(gethostname())]
        nodes = discover_all_nodes(include_lms=False)
        self.assertEqual(2, len(nodes))
        self.assertNotIn(gethostname(), nodes)
        self.assertIn('a', nodes)
        self.assertIn('b', nodes)

        ep.rest()
        ep.side_effect = ['a\nb\nlmsss']
        nodes = discover_all_nodes(include_lms=False, lms_hostname='lmsss')
        self.assertEqual(2, len(nodes))
        self.assertNotIn('lmsss', nodes)
        self.assertIn('a', nodes)
        self.assertIn('b', nodes)

    @patch('h_puppet.h_puppet.exec_process')
    def test_discover_peer_nodes(self, ep):
        ep.side_effect = ['n1\nn2\n{0}'.format(gethostname())]
        nodes = discover_peer_nodes()
        self.assertEqual(2, len(nodes))
        self.assertNotIn(gethostname(), nodes)
        self.assertIn('n1', nodes)
        self.assertIn('n2', nodes)

        ep.reset()
        ep.side_effect = ['']
        nodes = discover_peer_nodes()
        self.assertEqual(0, len(nodes))

        ep.reset()
        ep.side_effect = ['n1\nn2\n{0}'.format(gethostname())]
        nodes = discover_peer_nodes(peer_filter='.*2')
        self.assertEqual(1, len(nodes))
        self.assertNotIn(gethostname(), nodes)
        self.assertIn('n2', nodes)

    @patch('h_puppet.h_puppet.exec_process')
    def test_puppet_status(self, m_exec_process):
        puppet_status(['n1', 'n2'])
        m_exec_process.assert_has_calls([call(['mco', 'puppet', 'status',
                                               '--json', '-I', 'n1',
                                               '-I', 'n2'])],
                                        any_order=True)

        m_exec_process.reset_mock()
        m_exec_process.return_value = '\n'.join([
            'n1: Currently applying a catalog; last completed run 2 minutes '
            '46 seconds ago',
            'n21: Currently idling; last completed run 12 seconds ago'
        ])
        puppet_status()
        m_exec_process.assert_has_calls([call(['mco', 'puppet', 'status',
                                               '--json'])], any_order=True)

    @patch('h_puppet.h_puppet.exec_process')
    def test_puppet_enable_disable(self, m_exec_process):
        puppet_enable_disable(['n1', 'n2'], state='enable')
        m_exec_process.assert_has_calls([call(['mco', 'puppet', 'enable',
                                               '--json', '-I', 'n1',
                                               '-I', 'n2'])])
        m_exec_process.reset_mock()

        puppet_enable_disable(state='enable')
        m_exec_process.assert_has_calls([call(['mco', 'puppet', 'enable',
                                               '--json'])])
        m_exec_process.reset_mock()

        puppet_enable_disable(state='disable')
        m_exec_process.assert_has_calls([call(['mco', 'puppet', 'disable',
                                               '--json'])])

    @patch('h_puppet.h_puppet.exec_process')
    def test_puppet_runall(self, m_exec_process):
        puppet_runall()
        m_exec_process.assert_has_calls([call(['mco', 'puppet', 'runall',
                                               '10', '--json'])])

    @patch('h_puppet.h_puppet.discover_all_nodes')
    def test_puppet_trigger_wait(self, m_discover_all_nodes):
        with patch('h_puppet.h_puppet.PuppetExecutionProcessor') as pep:
            with patch('h_puppet.h_puppet.PuppetCatalogRunProcessor') as pepc:
                instance = pep.return_value
                instancec = pepc.return_value
                instancec.trigger_and_wait.return_value = MagicMock()
                instance.wait.return_value = MagicMock()

                puppet_trigger_wait(True, MagicMock(), ['n1'])
                self.assertTrue(instancec.trigger_and_wait.called)
                self.assertFalse(instance.wait.called)

                instance.trigger_and_wait.reset_mock()
                instance.wait.reset_mock()
                puppet_trigger_wait(False, MagicMock(), ['n1'])
                self.assertFalse(instance.trigger_and_wait.called)
                self.assertTrue(instance.wait.called)

        with patch('h_puppet.h_puppet.PuppetCatalogRunProcessor') as pep:
            instance = pep.return_value
            instance.nodes = {
                'n3': {'lastrun': 1441023897, 'state': 'completed'}
            }
            instance.trigger_and_wait.return_value = MagicMock()
            m_discover_all_nodes.return_value = ['n1', 'n2']
            puppet_trigger_wait(True, MagicMock())
            self.assertTrue(m_discover_all_nodes.called)
            self.assertTrue(instance.update_config_version.called)
            self.assertTrue(instance.trigger_and_wait.called)

        m_discover_all_nodes.reset_mock()
        with patch('h_puppet.h_puppet.PuppetCatalogRunProcessor') as pep:
            instance = pep.return_value
            instance.nodes = {
                'n3': {'lastrun': 1441023897, 'state': 'completed'}
            }
            instance.trigger_and_wait.return_value = MagicMock()
            puppet_trigger_wait(True, MagicMock(), ['n3'])
            self.assertFalse(m_discover_all_nodes.called)
            self.assertTrue(instance.trigger_and_wait.called)

    @patch('h_puppet.h_puppet._init_logging')
    @patch('h_puppet.h_puppet.puppet_status')
    def test_main_status(self, m_puppet_status, m_init_logging):
        with self.assertRaises(SystemExit) as sysexit:
            main([])
        self.assertEqual(sysexit.exception.args[0], ExitCodes.INVALID_USAGE)

        with self.assertRaises(SystemExit) as sysexit:
            main([''])
        self.assertEqual(sysexit.exception.args[0], ExitCodes.INVALID_USAGE)

        main(['', '--status'])
        self.assertTrue(m_puppet_status.called)

        m_trace = MagicMock()
        m_init_logging.return_value = m_trace
        main(['', '--status', '-V'])
        self.assertTrue(m_puppet_status.called)
        m_trace.assert_has_calls([call.trace.setLevel(logging.DEBUG)],
                                 any_order=True)

    @patch('h_puppet.h_puppet._init_logging')
    @patch('h_puppet.h_puppet.puppet_trigger_wait')
    def test_main_puppet_trigger_wait(self, m_puppet_trigger_wait,
                                      m_init_logging):
        with self.assertRaises(SystemExit) as sysexit:
            main([])
        self.assertEqual(sysexit.exception.args[0], ExitCodes.INVALID_USAGE)
        with self.assertRaises(SystemExit) as sysexit:
            main(['h_puppet.py'])
        self.assertEqual(sysexit.exception.args[0], ExitCodes.INVALID_USAGE)

        main(['', '--sync'])
        self.assertTrue(m_puppet_trigger_wait.called)

    @patch('h_puppet.h_puppet._get_litp_logger')
    def test_puppet_trigger_wait_interrupt(self, m_get_litp_logger):
        m_logger = MagicMock()
        m_get_litp_logger.side_effect = [m_logger]
        sync_agents_interrupt()
        self.assertTrue(m_logger.trace.info.called)
