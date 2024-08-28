from unittest2 import TestCase

from mock import patch, PropertyMock
from paramiko import SSHClient

from h_util.h_ssh.client import SshClient, CommandTimeout, SuIncorrectPassword
from h_util.h_timing import TimeWindow


class TestSshClient(TestCase):
    def setUp(self):
        self.ssh = SshClient("host", "user", "password")

    def tearDown(self):
        self.ssh = None

    def test_ssh_client_base(self):
        self.assertEquals(str(self.ssh), "<SshClient host 22>")
        self.assertEquals(repr(self.ssh), "<SshClient host 22>")

    @patch.object(SSHClient, "get_transport")
    @patch.object(SSHClient, "connect")
    def test_connection(self, connect, get_transport):
        self.assertFalse(self.ssh.is_connected())
        self.ssh.connect()
        self.assertTrue(self.ssh.is_connected())
        self.ssh.close()
        self.assertFalse(self.ssh.is_connected())

    @patch.object(SSHClient, "get_transport")
    @patch.object(SSHClient, "connect")
    def test_run_command(self, connect, get_transport):
        self.ssh.connect()
        get_transport.return_value.open_session.return_value.recv.side_effect = ["output", None]
        get_transport.return_value.open_session.return_value.exit_status_ready.side_effect = [False, True, True]
        get_transport.return_value.open_session.return_value.recv_stderr.return_value = None
        get_transport.return_value.open_session.return_value.recv_exit_status.return_value = 0
        status, out = self.ssh.run("cmd")
        self.assertEquals(status, 0)
        self.assertEquals(out.strip(), "output")
        self.ssh.close()

    @patch.object(SSHClient, "get_transport")
    @patch.object(SSHClient, "connect")
    def test_run_su_command(self, connect, get_transport):
        get_transport.return_value.open_session.return_value.recv.side_effect = ["Password:", "output", None]
        get_transport.return_value.open_session.return_value.exit_status_ready.side_effect = [False, True, True]
        get_transport.return_value.open_session.return_value.recv_stderr.return_value = None
        get_transport.return_value.open_session.return_value.recv_exit_status.return_value = 0
        status, out = self.ssh.run("cmd", su_password="test")
        self.assertEquals(status, 0)
        self.assertEquals(out.strip(), "output")
        self.ssh.close()

    @patch.object(TimeWindow, "elapsed", new_callable=PropertyMock)
    @patch.object(SSHClient, "get_transport")
    @patch.object(SSHClient, "connect")
    def test_run_su_command_auth_timed_out(self, connect, get_transport, elapsed):
        elapsed.side_effect = [10, 11]
        get_transport.return_value.open_session.return_value.recv.return_value = None
        with self.assertRaises(CommandTimeout):
            self.ssh.run("cmd", su_password="test")

    @patch.object(SSHClient, "get_transport")
    @patch.object(SSHClient, "connect")
    def test_run_invalid_su_password_command(self, connect, get_transport):
        get_transport.return_value.open_session.return_value.recv.side_effect = ["Password:", "su: incorrect password", None]
        get_transport.return_value.open_session.return_value.exit_status_ready.side_effect = [True, True, True]
        get_transport.return_value.open_session.return_value.recv_stderr.return_value = None
        get_transport.return_value.open_session.return_value.recv_exit_status.return_value = 1
        with self.assertRaises(SuIncorrectPassword):
            self.ssh.run("cmd", su_password="test")

    @patch.object(SSHClient, "get_transport")
    @patch.object(SSHClient, "connect")
    def test_run_command_with_error(self, connect, get_transport):
        get_transport.return_value.open_session.return_value.recv.return_value = None
        get_transport.return_value.open_session.return_value.exit_status_ready.side_effect = [True, True, True]
        get_transport.return_value.open_session.return_value.recv_stderr.side_effect = ["Error", None]
        get_transport.return_value.open_session.return_value.recv_exit_status.return_value = 1
        status, out = self.ssh.run("cmd")
        self.assertEquals(status, 1)
        self.assertEquals(out.strip(), "Error")
