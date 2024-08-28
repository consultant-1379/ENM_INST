"""
Class to get the LITP maintenance mode.
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
#
# ********************************************************************
# Name    : litp_maintenance.py
# Purpose : Class to get the LITP maintenance mode.
# ********************************************************************
import logging
import socket

from h_litp.litp_rest_client import LitpObject, LitpException

JOB_STATE_STARTING = 'Starting'
JOB_STATE_RUNNING = 'Running'
JOB_STATE_DONE = 'Done'
JOB_STATE_FAILED = 'Failed'
JOB_STATE_NONE = 'None'
PATH_LITP_MAINTENANCE = "/litp/maintenance"

STATES_RUNNING = [JOB_STATE_STARTING, JOB_STATE_RUNNING]
STATES_WITHOUT_MAINTENANCE = [JOB_STATE_NONE, JOB_STATE_DONE]


class LitpMaintenance(object):
    """
    Class to get the LITP maintenance mode.
    """
    def __init__(self, client, logger_name='enmversion'):
        """
        Initializes logging and configures litp REST client
        :param client: LitpRestClient client instance to use
        :type client: LitpRestClient
        :param logger_name: name of logger
        :type logger_name: str
        """
        self.litp = client
        self.log = logging.getLogger(logger_name)

    def is_maintenance_mode(self):
        """
        Checks if LITP is in maintenance mode
        :raises SystemExit if LITP is in maintenance mode
        :return True if LITP is in maintenance mode, otherwise False
        """
        enabled, _ = self._get_maintenance_attributes()
        return enabled

    def get_status(self):
        """
        Retrieves LITP maintenance status
        :return: LITP maintenance status
        :rtype str
        """
        _, status = self._get_maintenance_attributes()
        return status

    def _get_maintenance_attributes(self):
        """
        Retrieves LITP maintenance attributes tuple
        :return: tuple of enabled and status attributes
        """
        while True:
            try:
                response = self.litp.get(PATH_LITP_MAINTENANCE, log=False)
                nobj = LitpObject(None, response, self.litp.path_parser)
                enabled = nobj.get_bool_property("enabled")
                status = nobj.get_property("status")
                return enabled, status
            except (LitpException, socket.error) as ex:
                if type(ex) is LitpException:
                    message = ex.get_default_message()
                else:
                    message = str(ex)
                debug_message = 'Could not temporarily retrieve LITP ' \
                                'maintenance status due to: {0}' \
                    .format(message)
                self.log.debug(debug_message)
                raise ValueError(debug_message)

    @staticmethod
    def is_operation_running(status):
        """
        Checks if operation is running based on operation status
        :param status: status of operation
        :type status: str
        :return: True if operation is running, otherwise False
        :rtype: bool
        """
        if status in STATES_RUNNING:
            return True
        return False
