import os
import json
from mock import call, patch
from unittest2 import TestCase

from h_expansion.expansion_cleanup import cleanup_arp_cache, \
    cleanup_runtime_files, cleanup_source_oa


EXPECTED_ARP_CALLS = [call(['arp', '-d', '10.141.5.48']),
                      call(['arp', '-d', '10.141.5.49']),
                      call(['arp', '-d', '10.141.5.50']),
                      call(['arp', '-d', '10.141.5.51']),
                      call(['arp', '-d', '10.141.5.52'])]


class TestExpansionCleanup(TestCase):

    def setUp(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.sed_path = os.path.join(dir_path,
                                     '../Resources/chassis_expansion_sed')
        model_path = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_model.json')

        with open(model_path, 'r') as model_file:
            self.exp_model = json.load(model_file)

    @patch('h_expansion.expansion_cleanup.exec_process')
    @patch('h_expansion.expansion_model_handler.ExpansionModelHandler.read_expansion_model')
    def test_cleanup_arp_cache(self, m_read, m_exec):
        m_read.return_value = self.exp_model
        cleanup_arp_cache()
        self.assertTrue(m_exec.called)
        self.assertEqual(m_exec.call_args_list, EXPECTED_ARP_CALLS)

    @patch('h_expansion.expansion_cleanup.exec_process')
    @patch('h_expansion.expansion_model_handler.ExpansionModelHandler.read_expansion_model')
    def test_cleanup_arp_cache_handle_exception(self, m_read, m_exec):
        m_read.return_value = self.exp_model
        m_exec.side_effect = IOError()
        cleanup_arp_cache()
        self.assertTrue(m_exec.called)
        self.assertEqual(m_exec.call_args_list, EXPECTED_ARP_CALLS)

    @patch('os.remove')
    @patch('os.path.exists')
    @patch('h_expansion.expansion_cleanup.exec_process')
    def test_cleanup_runtime_files(self, m_exec, m_exists, m_remove):
        m_exists.return_value = True
        cleanup_runtime_files()
        self.assertTrue(m_exec.called)
        self.assertTrue(m_remove.called)
        self.assertEqual(m_remove.call_args_list,
                         [call('/opt/ericsson/enminst/runtime/enclosure_report.txt'),
                          call('/opt/ericsson/enminst/runtime/expansion_model.json')])

    @patch('os.remove')
    @patch('os.path.exists')
    @patch('h_expansion.expansion_cleanup.exec_process')
    def test_cleanup_runtime_files_exception(self, m_exec, m_exists, m_remove):
        m_exists.return_value = True
        m_remove.side_effect = OSError()
        self.assertRaises(OSError, cleanup_runtime_files)

        m_exec.side_effect = IOError()
        self.assertRaises(IOError, cleanup_runtime_files)

    @patch('os.remove')
    @patch('os.path.exists')
    @patch('h_expansion.expansion_cleanup.exec_process')
    def test_cleanup_runtime_files_model_exception(self, m_exec, m_exists, m_remove):
        m_exists.side_effect = [False, True]
        m_remove.side_effect = OSError()
        self.assertRaises(OSError, cleanup_runtime_files)

    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.save_ebipa')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.disable_ebipa_server')
    @patch('h_expansion.expansion_model_handler.ExpansionModelHandler.read_expansion_model')
    def test_cleanup_source_oa(self, m_read, m_disable, m_save):
        m_read.return_value = self.exp_model

        cleanup_source_oa(self.sed_path)

        #self.assertTrue(m_disable.called)
        #self.assertEqual(m_disable.call_count, 5)
        self.assertEqual(m_disable.call_args_list,
                         [call(u'9'), call(u'10'), call(u'11'), call(u'12'), call(u'13')])
        self.assertTrue(m_save.called)
