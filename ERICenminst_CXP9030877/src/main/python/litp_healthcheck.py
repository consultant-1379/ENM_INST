"""
This class is used as a healthcheck of LITP after it has been installed.
If all services are running okay a zero exit code is returned.
If some services are stopped a non-zero exit code will be returned.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

from os.path import exists, join
from h_logging.enminst_logger import init_enminst_logging
import os
from h_util.h_utils import exec_process
import logging


class LitpCheck(object):
    """
    LITP health check funcions
    """
    def __init__(self):
        self.log = logging.getLogger('enminst')
        self.litp_health_conf = join(os.environ['ENMINST_CONF'],
                                     'litp_healthcheck.conf')

    def check_services_status(self):
        """
        Executes services in the litp_healthcheck.conf file.
        Any service that is 'stopped' is caught, and a counter is increased.
        Any service that is 'running' continues and the counter stays the same.
        healthcheck_status is called with count, and decides the LITP status.
        :raises: SystemExit if no litp_healthcheck.conf file exists
        """
        if exists(self.litp_health_conf):
            self.log.info('\n' + '-' * 26 + ' LITP Healthcheck ' +
                          '-' * 47 + '\n')
            with open(self.litp_health_conf, 'r') as configuration_file:
                count_errors = 0
                for service in configuration_file.readlines():
                    service = service.strip()
                    if service.startswith('#') or len(service) == 0:
                        continue
                    self.log.info(' Checking {0} ... '.format(service))
                    service_cmd = service.split()
                    try:
                        exec_process(service_cmd)
                    except IOError:
                        self.log.error(' service status:'
                                       '\t\t\t\t\t[ stopped ]\n')
                        count_errors += 1
                    else:
                        self.log.info(' service status:'
                                      '\t\t\t\t\t[ running ]\n')
                self.healthcheck_status(count_errors)
        else:
            self.log.error('-' * 65 + '\n'
                           '\t\t\t   LITP Healthcheck \t\t\t\t\t'
                           '{ FAILED! }\n' + '-' * 91)
            raise SystemExit(self.litp_health_conf +
                             '\t\t{ FILE DOES NOT EXIST }\n' + '-' * 91)

    def healthcheck_status(self, count_errors):
        """
        Looks at the count_errors value passed in, and decides whether the LITP
        healthcheck status is FAILED or a SUCCESS
        :param count_errors: Counter that increments for every service stopped
        :type: Integer
        :raises: SystemExit if there are any services stopped, after checking
        all services
        """
        if count_errors > 0:
            self.log.error('-' * 65 + '\n\t\t\t   ' + str(count_errors) +
                           ' LITP service(s) not running\t\t\t{ FAILED! }\n' +
                           '-' * 91)
            raise SystemExit('\n-->\tNot all LITP services running ...'
                             '\n-->\tSome service(s) returned non-zero exit'
                             ' code'
                             '\n-->\tCheck LITP Healthcheck'
                             ' (and/or)'
                             ' litp_healthcheck.conf\n' + '-' * 91)
        else:
            self.log.info('-' * 65 + '\n\t\t\t   All LITP services running'
                          '\t\t\t\t{ SUCCESS }\n' + '-' * 91)


def main():
    """
    Main function
    :return:
    """
    init_enminst_logging()
    litp_healthcheck = LitpCheck()
    litp_healthcheck.check_services_status()


if __name__ == '__main__':
    main()
