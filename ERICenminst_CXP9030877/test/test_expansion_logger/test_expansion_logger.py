import unittest
import logging
import re
import os
import filecmp
import tempfile
from re import search
from time import strftime
from shutil import copy2
from mock import MagicMock, Mock, patch
from workarounds.expansion_logger import setup_logger

class TestExpansionSed(unittest.TestCase):

    @patch('logging.getLogger')
    @patch('os.access')
    @patch('logging.FileHandler')
    @patch('logging.StreamHandler')
    def test_defer_to_failsafe_location(self, MockStreamHandler, MockFileHandler, mock_os_access, mock_get_logger):
        '''
        Test to check that the logger will fall back to the defined
        fallback directory should write access be unavailable
        '''
        MockFileHandler.return_value = Mock()
        MockStreamHandler.return_value = Mock()
        mock_os_access.return_value = False
        logger = setup_logger()
        # Gather calls amde to the mock filehandler to see what args
        # were passed in.
        args, kargs = MockFileHandler.call_args
        self.assertTrue(len(args) > 0)
        self.assertTrue(type(args[0]) is str)
        self.assertTrue('/var/tmp' in args[0])



if __name__ == "__main__":
    unittest.main()
