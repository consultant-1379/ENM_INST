from logging import LogRecord
import socket
from logging.handlers import SysLogHandler

import mock

from unittest2 import TestCase

from h_logging.syslog_handler import WSyslogHandler, ColourlessHandler
from h_util.h_utils import Formatter


class MColourlessHandler(ColourlessHandler):
    def __init__(self, filename):
        super(MColourlessHandler, self).__init__(filename)

    def _open(self):
        return mock.Mock()


class TestColourlessHandler(TestCase):
    def test_format(self):
        tstring = Formatter.BG_GRAY + 'sometext' + Formatter.ENDC
        ch = MColourlessHandler('')

        record = LogRecord('Woop', 'INFO', 'path', 1, tstring, [], None)

        self.assertEqual('sometext', ch.format(record))

        record.msg = 'abc'
        self.assertEqual('abc', ch.format(record))


class SyslogHandlerTest(TestCase):
    """
    WSyslogHandler is a reduced version of method 'emit' in SysLogHandler.
    Functionality belongs to the standard library logging so we test
    that the exceptions are in place
    """

    @mock.patch.object(SysLogHandler, '__init__')
    def test_syslog_handler_basics(self, mocked_init):
        SysLogHandler.__init__.side_effect = SystemExit
        hdlr = WSyslogHandler()
        self.assertTrue((hdlr.filters == [] and
                         not hdlr.lock and
                         hdlr.facility == SysLogHandler.LOG_USER))

    def test_syslog_handler_1(self):
        hdlr = WSyslogHandler()
        hdlr.unixsocket = True
        hdlr.socket = mock.MagicMock()
        m_send = mock.MagicMock()
        hdlr.socket.send = m_send
        hdlr.emit(mock.MagicMock())
        self.assertTrue(m_send.called)

    class MockExcept(object):
        '''
        As date Jan/2014 jenkin's mock version is 0.8.0 that does not like
        iters in side_effect arg. Thus this little class is needed
        '''

        def __init__(self):
            self.called = 0

        def __call__(self, msg):
            if self.called == 0:
                self.called += 1
                raise socket.error
            else:
                return 'OK'

    def test_syslog_handler_connect_unix(self):
        hdlr = WSyslogHandler()
        hdlr.unixsocket = True
        hdlr.socket = mock.MagicMock()
        hdlr._connect_unixsocket = mock.MagicMock()
        m_send = mock.MagicMock()
        hdlr.socket.send = m_send
        hdlr.socket.send.side_effect = self.MockExcept()

        hdlr.emit(mock.MagicMock())
        self.assertTrue(m_send.called)
        self.assertTrue(m_send.call_count == 2)

    def test_syslog_handler_socktype(self):
        hdlr = WSyslogHandler()
        hdlr.unixsocket = False
        hdlr.socktype = socket.SOCK_DGRAM
        hdlr.socket = mock.MagicMock()
        m_sento = mock.MagicMock()
        hdlr.socket.sendto = m_sento
        hdlr.emit(mock.MagicMock())
        self.assertTrue(m_sento.called)

    def test_syslog_handler_sendall(self):
        hdlr = WSyslogHandler()
        hdlr.unixsocket = False
        hdlr.socktype = False
        hdlr.socket = mock.MagicMock()
        m_sendall = mock.MagicMock()
        hdlr.socket.sendall = m_sendall
        hdlr.emit(mock.MagicMock())
        self.assertTrue(m_sendall.called)

    def test_syslog_handler_except1(self):
        hdlr = WSyslogHandler()
        hdlr.unixsocket = False
        hdlr.socktype = False
        hdlr.socket = mock.MagicMock()
        hdlr.socket.sendall = mock.MagicMock()

        hdlr.socket.sendall.side_effect = KeyboardInterrupt
        self.assertRaises(KeyboardInterrupt, hdlr.emit, mock.MagicMock())

        hdlr.socket.sendall.side_effect = SystemExit
        self.assertRaises(SystemExit, hdlr.emit, mock.MagicMock())

    def test_syslog_handlert_except_e(self):
        hdlr = WSyslogHandler()
        hdlr.unixsocket = True
        hdlr.socktype = False
        hdlr._connect_unixsocket = mock.MagicMock()
        hdlr.socket = mock.MagicMock()
        hdlr.socket.sendall = mock.MagicMock()
        hdlr.socket.sendall.side_effect = ValueError
        self.assertTrue(hdlr.emit(mock.MagicMock()) is None)

    def test_syslog_handler_close(self):
        hdlr = WSyslogHandler()
        self.assertTrue(hdlr.close() is None)
