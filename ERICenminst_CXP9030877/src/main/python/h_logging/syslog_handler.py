"""
Enminst log handler implementations
"""
##############################################################################
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import socket
from logging.handlers import SysLogHandler, RotatingFileHandler
import re

from h_util.h_utils import Formatter


def remove_colour_codes(string):
    """
    Remove base colour codes from a string
    :param string: The string to check
    :returns: String
    """
    if Formatter.ENDC in string:
        string = re.sub(r'\033.*?m', '', string)
    return string


class ColourlessHandler(RotatingFileHandler, object):
    """
    Handler to remove bash colour codes from log statements
    """

    def format(self, record):
        """
        Remove any BASH colour codes from the message

        :param record: The record to check
        """
        msg = super(ColourlessHandler, self).format(record)
        return remove_colour_codes(msg)


class WSyslogHandler(SysLogHandler):
    """
    SysLogHandler is extended since it has problems dealing with Rsyslog.
    """

    def __init__(self, *args, **kwargs):
        try:
            SysLogHandler.__init__(self, *args, **kwargs)
        except:  # pylint: disable=W0702
            self.filters = []
            self.lock = False
            self.facility = SysLogHandler.LOG_USER

    def emit(self, record):
        """
        Emit a record.

        The record is formatted, and then sent to the syslog server. If
        exception information is present, it is NOT sent to the server.
        :param record: The record to format
        """
        msg = self.format(record) + '\000'
        msg = remove_colour_codes(msg)

        prio = '<%d>' % self.encodePriority(self.facility,
                                            self.mapPriority(record.levelname))

        msg = prio + msg
        try:

            if hasattr(self, 'socktype'):
                _socktype = getattr(self, 'socktype')
            else:
                _socktype = -1
            if self.unixsocket:
                try:
                    self.socket.send(msg)
                except socket.error:
                    self._connect_unixsocket(self.address)
                    self.socket.send(msg)
            elif _socktype == socket.SOCK_DGRAM:
                self.socket.sendto(msg, self.address)
            else:
                self.socket.sendall(msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

    def close(self):
        try:
            SysLogHandler.close(self)
        # pylint: disable=bare-except
        except:
            pass
