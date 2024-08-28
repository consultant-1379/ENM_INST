
from unittest2 import TestCase
from mock import MagicMock, patch, mock_open
from agent.filemanager import FileManager

class TestFilemanager(TestCase):

    @patch('agent.filemanager.urlopen')
    @patch('agent.filemanager.json.load')
    @patch('agent.filemanager.standard_b64decode')
    def test_pull_file_500_error(self,
                       m_standard_b64decode,
                       m_load,
                       m_urlopen):

        response = MagicMock()
        response.getcode.return_value = 500

        m_urlopen.return_value = response
        args = {'consul_url':'http://ms-1:8500/v1/kv/enminst/preonline',
                'file_path':'/opt/VRTSvcs/bin/triggers/preonline'}
        fm = FileManager()
        result = fm.pull_file(args)

        self.assertEqual(result, {'retcode': 1, 'err': 'Request "http://ms-1:8500/v1/kv/enminst/preonline" failed with Error "500"', 'out': ''})

    @patch('agent.filemanager.urlopen')
    @patch('agent.filemanager.json.load')
    @patch('agent.filemanager.standard_b64decode')
    @patch('os.path.exists')
    def test_pull_file_unexpected_error(self,
                       m_exists,
                       m_standard_b64decode,
                       m_load,
                       m_urlopen):

        response = MagicMock()
        response.getcode.return_value = 200

        m_urlopen.return_value = response
        args = {'consul_url':'http://ms-1:8500/v1/kv/enminst/preonline',
                'file_path':'/opt/VRTSvcs/bin/triggers/preonline'}
        fm = FileManager()
        with patch('__builtin__.open', new_callable=mock_open()) as m:
            result = fm.pull_file(args)
        expected = '/opt/VRTSvcs/bin/triggers'
        m_exists.assert_called_once_with(expected)
        self.assertEqual(result, {'retcode': 1,
                                 'err': "Unexpected error: [Errno 2] No such file or directory: '/opt/VRTSvcs/bin/triggers/preonline'",
                                 'out': ''})

    @patch('agent.filemanager.urlopen')
    @patch('agent.filemanager.json.load')
    @patch('agent.filemanager.standard_b64decode')
    #@patch('__builtin__.open', new_callable=mock_open())
    @patch('os.chmod')
    @patch('os.makedirs')
    def test_pull_file(self,
                       m_makedirs,
                       m_chmod,
                       #m_open,
                       m_standard_b64decode,
                       m_load,
                       m_urlopen):

        response = MagicMock()
        response.getcode.return_value = 200

        m_urlopen.return_value = response
        args = {'consul_url':'http://ms-1:8500/v1/kv/enminst/preonline',
                'file_path':'/opt/VRTSvcs/bin/triggers/preonline'}
        fm = FileManager()
        with patch('__builtin__.open', new_callable=mock_open()) as m:
            result = fm.pull_file(args)
        expected = '/opt/VRTSvcs/bin/triggers'
        m_makedirs.assert_called_once_with(expected)
        m_chmod.assert_called_once_with('/opt/VRTSvcs/bin/triggers/preonline', 493)
        self.assertEqual(result, {'retcode': 0,
                                'err': '',
                                'out': 'Request "http://ms-1:8500/v1/kv/enminst/preonline" returned "200"\nFile "/opt/VRTSvcs/bin/triggers/preonline" written successfully'})

