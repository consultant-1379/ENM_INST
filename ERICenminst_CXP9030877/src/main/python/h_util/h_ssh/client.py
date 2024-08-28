""" Python module containing functionality to create ssh connections to
remote machines.
"""
import socket
import time

from paramiko import SSHException, SSHClient, AutoAddPolicy

from h_logging.enminst_logger import init_enminst_logging
from h_util.h_decorators import retry_if_fail
from h_util.h_ssh.cmd import Command
from h_util.h_timing import TimeWindow

CONNECT_TIMEOUT = 20   # seconds

RETRY_MSGS = [
    "SSH session not active",
    "Error reading SSH protocol banner"
]


class SuIncorrectPassword(Exception):
    """ Exception raised if provided su password is incorrect """


# pylint: disable=too-many-instance-attributes
class SshClient(object):
    """ This class implements basic features of paramiko library in order to
    run remote commands.
    """

    def __init__(self, host, user, password=None, port=22):
        """ This constructor requires the connection arguments.
        >>> SshClient("host", "user")
        <SshClient host 22>
        >>> p = "some_password"
        >>> ssh = SshClient("host2", "user2", p, port=24)
        >>> ssh
        <SshClient host2 24>
        >>> ssh.password == p
        True
        >>> ssh._ssh is None
        True
        """
        self.host = str(host)
        self.user = user
        self.password = password
        self.port = port
        self._ssh = None
        self._transport = None
        self._last_channel = None
        self.log = init_enminst_logging()

    def __str__(self):
        """ Retrieves the str informal representation of this object.
        >>> ssh = SshClient("host", "user")
        >>> str(ssh)
        '<SshClient host 22>'
        """
        return "<%s %s %s>" % (self.__class__.__name__, self.host, self.port)

    def __repr__(self):
        """ Retrieves the official representation of this object.
        >>> ssh = SshClient("host", "user")
        >>> repr(ssh)
        '<SshClient host 22>'
        """
        return str(self)

    @property
    def ssh(self):
        """ Gets the paramiko SshClient object connected.
        """
        if self._ssh is not None:
            if not self.is_connected():
                self.log.debug("SshClient: connection lost, re-attempting to "
                               "connect")
                self.close()
                self.connect()
            return self._ssh
        self.connect()
        return self._ssh

    def connect(self):
        """ Builds the paramiko.SshClient object, sets
        the system keys, the missing host key (for .ssh/know_host file) and try
        to establish the SSH connection.
        """
        if self._ssh is not None:
            return
        self._ssh = SSHClient()
        self._ssh.load_system_host_keys()
        self._ssh.set_missing_host_key_policy(AutoAddPolicy())
        try:
            self._ssh.connect(self.host, self.port, self.user,
                              self.password, timeout=CONNECT_TIMEOUT)
        except Exception as err:
            self.log.error("SshClient: Failed to connect to %s: %s: %s" %
                           (self.host, type(err).__name__, err))
            self.close()
            raise
        else:
            self._transport = self._ssh.get_transport()

    def is_connected(self):
        """ Checks the SSH connectivity.
        """
        is_active = False
        if self._transport:
            is_active = self._transport.is_active()
        return bool(self._transport and is_active)

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-branches
    def _run(self, cmd, su_user=None, su_password=None, sudo=False,
             env=None, sh_source_path=None):
        """ Executes a command using self._transport object to open a channel
        inside the host machine.
        """
        if self._transport is None:
            self.connect()

        channel = self._transport.open_session()

        channel.set_combine_stderr(True)
        self._last_channel = channel

        if su_password is not None and not su_user:
            su_user = "root"

        cmd = str(Command(cmd, su_user, sudo, env, sh_source_path))
        if not cmd.strip().endswith("&"):
            channel.get_pty()
        channel.exec_command(cmd)

        if su_password is not None and not sudo:
            buf = ''
            with TimeWindow("") as time_window:
                while True:
                    resp = channel.recv(1024)
                    if resp:
                        buf += resp
                    if "Password:" in buf:
                        break
                    if time_window.elapsed > 10:
                        raise CommandTimeout("Timeout reached while trying to "
                                             "send su password for %s user" %
                                             su_user)
                    time.sleep(0.1)
            channel.send('%s\n' % su_password)

        buf = ''
        while True:
            resp = channel.recv(1024)
            if resp:
                buf += resp
            exit_status_ready = channel.exit_status_ready()
            if not resp and exit_status_ready:
                break

        while True:
            resp_err = channel.recv_stderr(1024)
            if resp_err:
                buf += resp_err
            exit_status_ready = channel.exit_status_ready()
            if not resp_err and exit_status_ready:
                break

        def clean(output):
            """ Strip "Password: " prompt from the output
            """
            password_prompt = "Password: "
            if (su_password is not None or su_user is not None) and not sudo:
                if output.startswith(password_prompt):
                    return output[len(password_prompt):].lstrip()
            return output

        status = channel.recv_exit_status()
        if su_password is not None and not sudo:
            if 'su: incorrect password' in buf or \
                    'su: Authentication failure' in buf:
                raise SuIncorrectPassword(buf)

        return status, clean(buf)

    @property
    def last_status(self):
        """ Previous channel exit status
        :return: int
        """
        if self._last_channel:
            return self._last_channel.recv_exit_status()

    # pylint: disable=too-many-arguments
    @retry_if_fail(5, exception=SSHException, msgs=RETRY_MSGS)
    def run(self, cmd, su_user=None, su_password=None,
            sudo=False, env=None, sh_source_path=None):
        """ Uses paramiko SshClient object to execute commands remotely and
        retrieves the correspond standard output and standard error.
        """
        try:
            ret = self._run(cmd, su_user, su_password, sudo, env,
                            sh_source_path)
        except socket.timeout as err:  # pylint: disable=E0712
            raise CommandTimeout("A timeout occurred after trying to execute"
                                 "the following command remotely "
                                 "through SSH on %s: \"%s\". Error: %s" %
                                 (self.host, cmd, str(err)), cmd=cmd)
        return ret

    def close(self):
        """ Closes the ssh connection properly.
        """
        if self._ssh is not None:
            self._ssh.close()
        if self._transport is not None:
            # sleep a bit to avoid the transport thread to hang while closing
            # the connection "via host".
            time.sleep(0.01)
            self._transport.close()
        self._ssh = None
        self._transport = None


# pylint: disable=too-few-public-methods
class SshConnection(object):
    """ Context Manager for an SSH connection
    """

    def __init__(self, *args, **kwargs):
        """ Uses an SshScpClient instance to establish the SSH connection.
        :param args: connection arguments
        :param kwargs: connection keyword arguments
        """
        self.ssh = SshClient(*args, **kwargs)

    def __enter__(self):
        """ Connects the SSH client and returns it.
        :return: SshScpClient instance
        """
        self.ssh.connect()
        return self.ssh

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ Closes the SSH connection.
        :return: None
        """
        self.ssh.close()


class CommandFailed(Exception):
    """ This exception is raised every time a command execution return a status
    code different than zero.
    """

    def __init__(self, message, output=None, status_code=None, cmd=None):
        """ This constructor also requires the status code to be able to
        easily retrieve it back after this exception is raised.
        """
        super(CommandFailed, self).__init__(message, output, status_code, cmd)
        self.msg = message
        self.output = output
        self.status_code = status_code
        self.cmd = cmd

    def __str__(self):
        """ Command Failed string representation"""
        error_msg = self.msg
        if self.status_code is not None:
            error_msg = "%s. Status code: %s" % (error_msg.strip().rstrip('.'),
                                                 self.status_code)
        if self.msg != self.output:
            return "%s. Error: %s" % (error_msg, self.output)
        if self.status_code == 127 and self.cmd:
            error_msg = "%s. Command: %s" % (error_msg, self.cmd)
        return error_msg


class CommandTimeout(CommandFailed):
    """ Exception raised in case of command times out """
