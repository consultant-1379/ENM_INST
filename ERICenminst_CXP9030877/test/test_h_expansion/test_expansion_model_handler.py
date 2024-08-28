import os
import json
from mock import call, patch
from unittest2 import TestCase

from h_expansion.expansion_model_handler import ExpansionModelHandler
from h_expansion.expansion_settings import EXPANSION_MODEL_FILE


class TestExpansionModelHandler(TestCase):
    def setUp(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        model_path = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_model.json')

        with open(model_path, 'r') as model_file:
            self.exp_model = json.load(model_file)

    @patch('json.load')
    @patch('os.path.exists')
    @patch('__builtin__.open')
    def test_get_blades_in_empty_model(self, m_open, m_exists, m_load):
        m_exists.return_value = True
        model_handler = ExpansionModelHandler()
        self.assertRaises(Exception, model_handler.get_blades_in_model)

    @patch('json.load')
    @patch('os.path.exists')
    @patch('__builtin__.open')
    def test_read_expansion_model(self, m_open, m_exists, m_load):
        m_exists.return_value = True
        model_handler = ExpansionModelHandler()
        self.assertTrue(m_open.called)
        self.assertEqual(m_open.call_args_list, [call(EXPANSION_MODEL_FILE, 'r')])
        self.assertTrue(m_load.called)

    @patch('json.load')
    @patch('os.path.exists')
    @patch('__builtin__.open')
    def test_read_expansion_model_exception(self, m_open, m_exists, m_load):
        # Fail to read in json data
        m_exists.return_value = True
        m_load.side_effect = ValueError()
        self.assertRaises(Exception, ExpansionModelHandler)

        # Model file does not exist
        m_exists.return_value = False
        self.assertRaises(Exception, ExpansionModelHandler)

    @patch('__builtin__.open')
    @patch('h_expansion.expansion_model_handler.ExpansionModelHandler.read_expansion_model')
    def test_write_model_file(self, m_read_model, m_open):
        m_read_model.return_value = self.exp_model
        model_handler = ExpansionModelHandler()

        model_handler.write_model_file()

        self.assertTrue(m_open.called)

    @patch('__builtin__.open')
    @patch('h_expansion.expansion_model_handler.ExpansionModelHandler.read_expansion_model')
    def test_write_model_file_exception(self, m_read_model, m_open):
        m_read_model.return_value = self.exp_model
        model_handler = ExpansionModelHandler()

        m_open.side_effect = IOError()

        self.assertRaises(Exception, model_handler.write_model_file)
