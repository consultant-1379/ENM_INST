import unittest
import logging
import re
import os
import filecmp
import tempfile
import glob
from re import search
from time import strftime
from shutil import copy2
from shutil import rmtree
from mock import MagicMock, Mock, patch
from workarounds.expansion_sed import ExpansionSed
from workarounds.expansion_logger import setup_logger
from workarounds.expansion_sed import main
from testfunclib import myassert_raises_regexp, create_sed, create_profile


TEST_TXT_DIRECTORY = os.path.dirname(__file__)

SERVICE_GROUP_SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/amos_sed_test.txt')
SERVICE_GROUP_V4SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/amos_sed_v4test.txt')
TEST_TEMP_DIRECTORY = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/expansion_temp')
TEST_LOAD_SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/sed_test_load_sed.txt')
MISSING_PARAMS_SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/amos_crippled_sed_test.txt')
MISSING_VALUES_SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/missing_value_sed_test.txt')
SWAPPED_PARAMS_SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/amos_sed_swapped_test.txt')
SWAPPED_PARAMS_V4SED = os.path.join(TEST_TXT_DIRECTORY,
                                 '../Resources/amos_sed_swapped_v4test.txt')

class TestExpansionSed(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(TEST_TEMP_DIRECTORY):
            os.mkdir(TEST_TEMP_DIRECTORY)

    def test_validate_sed_swap_param_raise_value_error(self):
        """
        Test to assert that the function swap_parameter_values calls a
        ValueError if there is a missing value in the SED
        """
        mock_logger= Mock()
        expansion_writer = ExpansionSed(MISSING_PARAMS_SED, mock_logger)
        expansion_writer._get_sed_data()
        # Check to see if the function throws an Error when one of the required
        # parameters is missing its value
        self.assertRaises(ValueError, expansion_writer.swap_parameter_values)

    def test_validate_sed_swap_param_internal_ip(self):
        """
        Test to assert that the function swap_parameter_values swaps the values
        for nternal_ip parameters
        """
        mock_logger = Mock()
        expansion_writer = ExpansionSed(SERVICE_GROUP_SED, mock_logger)
        expansion_writer._get_sed_data()
        expansion_writer.swap_parameter_values()
        output_sed = expansion_writer._sed_data
        # Check if internal arameters have been swapped successfully
        self.assertEqual(output_sed["amos_1_ip_internal"], "192.168.2.97")
        self.assertEqual(output_sed["amos_2_ip_internal"], "192.168.2.96")

    def test_validate_sed_swap_param_jgroups_ip(self):
        """
        Test to assert that the function swap_parameter_values swaps the values
        for jgroups_ip parameters
        """
        mock_logger = Mock()
        expansion_writer = ExpansionSed(SERVICE_GROUP_SED, mock_logger)
        expansion_writer._get_sed_data()
        expansion_writer.swap_parameter_values()
        output_sed = expansion_writer._sed_data
        # Check if jgroups arameters have been added to the SED successfully
        self.assertEqual(output_sed["amos_1_ip_jgroups"], "192.168.1.92")
        self.assertEqual(output_sed["amos_2_ip_jgroups"], "192.168.1.91")

    def test_validate_sed_swap_param_storage_ip(self):
        """
        Test to assert that the function swap_parameter_values swaps the values
        for storage_ip parameters
        """
        mock_logger = Mock()
        expansion_writer = ExpansionSed(SERVICE_GROUP_SED, mock_logger)
        expansion_writer._get_sed_data()
        expansion_writer.swap_parameter_values()
        output_sed = expansion_writer._sed_data
        # Check if storage parameters have been added to the SED successfully
        self.assertEqual(output_sed["amos_1_ip_storage"], "10.140.32.151")
        self.assertEqual(output_sed["amos_2_ip_storage"], "10.140.32.150")

    def test_validate_sed_backup_intact(self):
        """
        Test to check if the SED backup matches the SED text file passed in.
        """
        mock_logger = Mock()
        expansion_writer = ExpansionSed(SERVICE_GROUP_SED, mock_logger)
        expansion_writer.create_backup_sed()
        backup_file = expansion_writer.sed_backup_file
        self.assertTrue(filecmp.cmp(SERVICE_GROUP_SED,backup_file))

    def test_check_empty_value_error(self):
        """
        Test to check if the swapped values are written out to the SED
        text file.
        """
        mock_logger = Mock()
        expansion_writer = ExpansionSed(MISSING_VALUES_SED, mock_logger)
        expansion_writer._get_sed_data()
        expansion_writer._update_params_if_ipv6()
        expansion_writer.log.error = Mock()
        myassert_raises_regexp(self,
                               ValueError,
                               "Missing values in SED",
                               expansion_writer._confirm_sed_data)
        expansion_writer.log.error.assert_any_call(
            'amos_1_ip_jgroups contains an empty value. Please correct this'
            + ' parameter and try again.')


    def test_validate_swapped_params_write_to_sed(self):
        """
        Test to check if the swapped values are written out to the SED
        text file.
        """
        mock_logger = Mock()
        service_group_sed_copy = os.path.join(TEST_TEMP_DIRECTORY + \
                                              '/amos_sed_copy' +
                                              strftime("%Y%m%d_%H%M%S") +
                                              '.txt')
        copy2(SERVICE_GROUP_SED,service_group_sed_copy)
        expansion_writer = ExpansionSed(service_group_sed_copy, mock_logger)
        expansion_writer.swap_parameter_values()
        expansion_writer.sed_backup_file = SERVICE_GROUP_SED
        expansion_writer.update_sed()
        self.assertTrue(filecmp.cmp(SWAPPED_PARAMS_SED,service_group_sed_copy))

    def test_validate_swapped_params_write_to_v4sed(self):
        """
        Test to check if the swapped values are written out to the SED
        text file.
        """
        mock_logger = Mock()
        service_group_sed_copy = os.path.join(TEST_TEMP_DIRECTORY + \
                                              '/amos_v4sed_copy' +
                                              strftime("%Y%m%d_%H%M%S") +
                                              '.txt')
        copy2(SERVICE_GROUP_V4SED, service_group_sed_copy)
        expansion_writer = ExpansionSed(service_group_sed_copy, mock_logger)
        expansion_writer.swap_parameter_values()
        expansion_writer.sed_backup_file = SERVICE_GROUP_V4SED
        expansion_writer.update_sed()
        self.assertTrue(filecmp.cmp(SWAPPED_PARAMS_V4SED,service_group_sed_copy))

    def test_validate_sed_swap_param_raise_key_error(self):
        """
        Test to assert that the function swap_parameter_values calls a
        ValueError if there is a missing parameter in the SED
        """
        mock_logger = Mock()
        expansion_writer = ExpansionSed(MISSING_PARAMS_SED, mock_logger)
        expansion_writer._get_sed_data()
        expansion_writer._update_params_if_ipv6()
        # Check if the message we get from the exception generated matches
        # the expected string below for missing parameters in the SED.
        myassert_raises_regexp(self,
                               ValueError,
                               "Missing parameters in SED",
                               expansion_writer._confirm_sed_data)

    def test_load_sed_entries(self):
        '''
        Test to check if the function _get_sed_data captures all required
        data from a service group
        '''
        print(self.shortDescription())
        mock_logger = Mock()
        expansion_writer = ExpansionSed(TEST_LOAD_SED, mock_logger)
        expansion_writer._get_sed_data()
        data = expansion_writer._sed_data
        # Check if all entries in sample SED are loaded into dictionary
        self.assertEqual(len(data), 14)
        matches = [k for k, v in data.items() if k.startswith('amos')]
        # Check number of amos specific values in the sample SED
        self.assertEqual(len(matches), 10)


    @patch('sys.argv', ["test"])
    # @patch('workarounds.expansion_logger.setup_logger')
    @patch('workarounds.expansion_sed.setup_logger')
    def test_check_missing_file_parameter(self,mock_get_logger):
        '''
        Test to check if the script exits when the filename for the SED
        is missing
        '''
        mock_logger = Mock()
        # pdb.set_trace()
        mock_get_logger.return_value = mock_logger
        self.assertRaises(SystemExit, main)
        mock_logger.error.assert_any_call("Missing filename for SED file, exiting.")

    @patch('sys.argv', ["val1", "val2"])
    @patch('workarounds.expansion_sed.ExpansionSed')
    @patch('workarounds.expansion_sed.setup_logger')
    def test_check_value_error_catch(self, mock_get_logger, MockExpansionSed):
        '''
        Test to check if the script exits gracefully when a value or parameter
        is missing from the SED.
        '''
        mock_expansion_sed_instance = Mock()
        # Have the mock function throw an ValueError
        mock_expansion_sed_instance.swap_parameter_values.side_effect = \
                ValueError
        MockExpansionSed.return_value = mock_expansion_sed_instance
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        self.assertRaises(SystemExit, main)
        mock_logger.error.assert_any_call("Cannot continue with the script. " + \
                                   "Please check the errors above " + \
                                   "and try again.")

    @patch('sys.argv', ["val1", "val2"])
    @patch('workarounds.expansion_sed.ExpansionSed')
    @patch('workarounds.expansion_sed.setup_logger')
    def test_check_index_error_catch(self, mock_get_logger, MockExpansionSed):
        '''
        Test to check if the script exits gracefully when a value or parameter
        is missing from the SED.
        '''
        mock_expansion_sed_instance = Mock()
        # Have the mock function throw an IndexError
        mock_expansion_sed_instance.swap_parameter_values.side_effect = \
                IndexError
        MockExpansionSed.return_value = mock_expansion_sed_instance
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        self.assertRaises(SystemExit, main)
        mock_logger.error.assert_any_call("Issues occurred while processing" +
                                          " SED parameters.")

    def tearDown(self):
        BACKUP_PATTERN="../Resources/expansion_sed_backup*.txt"
        if os.path.exists(TEST_TEMP_DIRECTORY):
            rmtree(TEST_TEMP_DIRECTORY)

        for f in glob.glob(TEST_TXT_DIRECTORY + "/" + BACKUP_PATTERN):
            os.remove(f)

if __name__ == "__main__":
    unittest.main()
