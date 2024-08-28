from datetime import datetime, timedelta
from mock import MagicMock, Mock, patch
from unittest2.case import TestCase

from h_hc.hc_ombs import OmbsHealthCheck
from h_hc.hc_ombs import CUTOFF_DAYS, BPCONF_FILE, ENM_VERSION_FILE


class TestOmbsHealthCheck(TestCase):
    # noinspection PyPep8Naming
    def __init__(self, methodName='runTest'):
        super(TestOmbsHealthCheck, self).__init__(methodName)

    def setUp(self):
        super(TestOmbsHealthCheck, self).setUp()

    def test_get_localhost(self):
        # bp.conf file with CLIENT_NAME entry
        hosts_file_lines = ["#CN = 123\n", "CLIENT_NAME = xyz1234-bkp\n"]
        hc = OmbsHealthCheck(verbose=True)
        with patch('__builtin__.open') as mock_open:
            m = MagicMock(spec=file)
            m.__enter__.return_value.__iter__.return_value = iter(
                                                             hosts_file_lines)
            mock_open.return_value = m
            localhost = hc._get_localhost()
        self.assertEqual('xyz1234-bkp', localhost)
        mock_open.assert_called_once_with(BPCONF_FILE, 'r')

        #bp.conf file without CLIENT_NAME entry
        hosts_file_lines = ["#CN = 123\n", "NAME = xyz1234\n"]
        hc = OmbsHealthCheck(verbose=True)
        with patch('__builtin__.open') as mock_open:
            m = MagicMock(spec=file)
            m.__enter__.return_value.__iter__.return_value = iter(
                hosts_file_lines)
            mock_open.return_value = m
            localhost = hc._get_localhost()
        self.assertRaises(Exception)
        mock_open.assert_called_once_with(BPCONF_FILE, 'r')

    def test_get_enm_version(self):
        # Normal enm version file
        enm_ver_file_lines = ["#123\n", "ENM 18.12\n"]
        hc = OmbsHealthCheck(verbose=True)
        with patch('__builtin__.open') as mock_open:
            m = MagicMock(spec=file)
            m.__enter__.return_value.__iter__.return_value = iter(
                                                            enm_ver_file_lines)
            mock_open.return_value = m
            enm_ver = hc._get_enm_version()
        self.assertEqual('ENM 18.12', enm_ver)
        mock_open.assert_called_once_with(ENM_VERSION_FILE, 'r')

        # Corrupted enm version file
        enm_ver_file_lines = ["#123\n", " 18.12\n"]
        hc = OmbsHealthCheck(verbose=True)
        with patch('__builtin__.open') as mock_open:
            m = MagicMock(spec=file)
            m.__enter__.return_value.__iter__.return_value = iter(
                enm_ver_file_lines)
            mock_open.return_value = m
            enm_ver = hc._get_enm_version()
            self.assertRaises(Exception)
        mock_open.assert_called_once_with(ENM_VERSION_FILE, 'r')

    def test_get_backup_date_and_ver(self):
        ombs_output = ["""
                       2018-09-14 14:01:02
                       ENM 18.12
                       """,
                       " ",
                       """
                       2018-09-14 14:01:02
                       ENM 18.12
                       2018-10-10 10:10:10
                       ENM 18.13
                       """
                      ]
        hc = OmbsHealthCheck(verbose=True)
        backupdate, backupver = hc._get_backup_date_and_ver(ombs_output[0])
        self.assertEqual(datetime(2018, 9, 14, 14, 1, 2), backupdate)
        self.assertEqual('ENM 18.12', backupver)
        backupdate, backupver = hc._get_backup_date_and_ver(ombs_output[1])
        self.assertEqual(None, backupdate)
        self.assertEqual('', backupver)
        backupdate, backupver = hc._get_backup_date_and_ver(ombs_output[2])
        self.assertEqual(datetime(2018, 9, 14, 14, 1, 2), backupdate)
        self.assertEqual('ENM 18.12', backupver)

    @patch('h_hc.hc_ombs.OmbsHealthCheck._ombs_login')
    @patch('h_hc.hc_ombs.OmbsHealthCheck._get_enm_version')
    def test_ombs_backup_healthcheck(self, mock_get_enm_ver, mock_ombs_login):
        cutoff_days_ago = datetime.now() - timedelta(days=CUTOFF_DAYS)
        mock_ombs_login.return_value = cutoff_days_ago.strftime(
            '%Y-%m-%d %H:%M:%S') + ' ENM 18.12'
        mock_get_enm_ver.return_value = 'ENM 18.12'

        hc = OmbsHealthCheck(verbose=True)
        mock_log_info = Mock()
        hc.logger = Mock(info=mock_log_info)
        hc.ombs_backup_healthcheck()

        self.assertEqual(mock_log_info.call_count, 2)
        mock_log_info.assert_any_call('Last successful OMBS backup was'
                         ' taken on {0}'.format(
                         cutoff_days_ago.strftime('%Y-%m-%d')))

        # Repeat test with last backup CUTOFF_DAYS + 1
        cutoff_plus_one_days_ago = datetime.now() - timedelta(
                                                         days=CUTOFF_DAYS + 1)
        mock_ombs_login.return_value = cutoff_plus_one_days_ago.strftime(
            '%Y-%m-%d %H:%M:%S') + ' ENM 18.12'

        hc = OmbsHealthCheck(verbose=True)
        mock_log_warn = Mock()
        hc.logger = Mock(warning=mock_log_warn)
        hc.ombs_backup_healthcheck()

        mock_log_warn.assert_called_once_with('Last successful OMBS backup was'
                         ' taken on {0} and its more than {1} days old.'
                         '\nPlease run a new OMBS backup.'.format(
                         cutoff_plus_one_days_ago.strftime('%Y-%m-%d'),
                         CUTOFF_DAYS))

        # Repeat test with enm version mismatch
        mock_get_enm_ver.return_value = 'ENM 18.13'
        mock_ombs_login.return_value = cutoff_days_ago.strftime(
            '%Y-%m-%d %H:%M:%S') + ' ENM 18.12'

        hc = OmbsHealthCheck(verbose=True)
        mock_log_warn = Mock()
        hc.logger = Mock(warning=mock_log_warn)
        hc.ombs_backup_healthcheck()

        mock_log_warn.assert_called_once_with('Current release is ENM 18.13, '
                                     'but the OMBS backup is on ENM 18.12.'
                                     '\nPlease run a new OMBS backup.')

    @patch('__builtin__.raw_input')
    @patch('getpass.getpass')
    @patch('h_hc.hc_ombs.OmbsHealthCheck._get_localhost')
    @patch('h_hc.hc_ombs.create_ssh_client')
    def test_ombs_login(self, mock_create_ssh_client, mock_get_localhost,
                        mock_getpass, mock_raw_input):
        # Successful login
        mock_raw_input.return_value = 'ombs_ip'
        mock_getpass.return_value = 'ombs_pw'
        mock_get_localhost.return_value = 'lms_hostname'
        cutoff_days_ago = datetime.now() - timedelta(days=CUTOFF_DAYS)
        stdout = Mock(read=lambda: cutoff_days_ago.strftime(
                                      '%Y-%m-%d %H:%M:%S') + ' ENM 18.12',
                      channel=Mock(recv_exit_status=lambda: 0))
        mock_exec_command = Mock()
        mock_exec_command.return_value = ('stdin', stdout, 'stderr')
        ssh_client = Mock(exec_command=mock_exec_command)
        mock_create_ssh_client.return_value = ssh_client
        hc = OmbsHealthCheck(verbose=True)
        hc._ombs_login()

        mock_exec_command.assert_called_once_with('/ericsson/ombss_enm/bin/'
                                                  'manage_backup_images.bsh'
                                                  ' -M lms_hostname -s')

        # Failed login
        stdout = Mock(read=lambda: "Error",
                      channel=Mock(recv_exit_status=lambda: 1))
        mock_exec_command = Mock()
        mock_exec_command.return_value = ('stdin', stdout, 'stderr')
        ssh_client = Mock(exec_command=mock_exec_command)
        mock_create_ssh_client.return_value = ssh_client
        hc = OmbsHealthCheck(verbose=True)

        mock_log_error = Mock()
        hc.logger = Mock(error=mock_log_error)
        hc._ombs_login()

        mock_log_error.assert_called_once_with('OMBS server connection error'
                                               ' : stderr')
