"""
The purpose of this script is to query the NAS Audit
error to determine if there are any errors.
If any errors are found then fmalarm should be created.
"""

# pylint: disable=E1101
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################

from restapi import RESTapi
from h_litp.litp_rest_client import LitpRestClient, LitpException
from h_litp.litp_maintenance import LitpMaintenance
from h_util.h_nas_console import NasConsole
from h_logging.enminst_logger import init_enminst_logging
from enm_healthcheck import HealthCheck

ALARM_REQUEST_HEADER = {"Content-Type": "application/json"}
ALARM_REQUEST_PATH = "/internal-alarm-service/internalalarm/" \
                     "internalalarmservice/translate"
ALARMS_FILE_PATH = "/var/log/current_nasaudit_alarms.txt"


class NasAuditCheck(object):
    """
    class to create and clear nas FMalarms
    """
    NAS_CMD_USAGE = 'df -hPTl -x tmpfs -x devtmpfs'
    NAS_AUDIT = '/opt/ericsson/NASconfig/bin/nasAudit.sh'
    NAS_AUDIT_CHECK = '/opt/ericsson/NASconfig/bin/nasauditcheck.sh'
    NAS_VA_CHECK = 'ls /opt/SYMCsnas'
    NAS_VA74_CHECK = 'ls /opt/VRTSnas'

    NAS_AUDIT_SUCCESS = 0
    NAS_AUDIT_WARNING = 3
    NAS_AUDIT_ERROR = 1
    NAS_AUDIT_UNKNOWN = 2

    def __init__(self):
        self.logger = init_enminst_logging()
        self.litp_rest = LitpRestClient()

    def build_alarm_url(self):
        """
        Retrieves the haproxy internal IP address from the LITP model
        and stores it in a class variable.
        Also Builds the url that is required to create
        clear an FMalarm using the
        haproxy internal IP address and the request path.
        """
        clear_list = self.litp_rest.get_items_by_type("/deployments", \
                                                         'vcs-cluster', [])
        for ip_path in clear_list:
            if "svc_cluster" == ip_path['data']['id']:
                output = self.litp_rest.get_items_by_type(ip_path['path'], \
                                                           'vip', [])
                full_path = eval(str(output[0]))['path']
                try:
                    items = self.litp_rest.get(full_path, log=False)
                except LitpException as err:
                    self.logger.error(err)
                    raise LitpException(err)
                haproxy_int_ip = items["properties"]["ipaddress"]
                return "http://{0}:8081{1}".format(haproxy_int_ip,\
                                                      ALARM_REQUEST_PATH)

    # pylint: disable=too-many-arguments
    # pylint : disable=missing doc string
    def build_alarm(self, specific_problem='NAS Health Check Issue',
                    probable_cause='INDETERMINATE',
                    event_type='OTHER',
                    managed_object_instance='NAS',
                    perceived_severity='CLEARED',
                    record_type='ERROR_MESSAGE'):
        """
        build alarm function
        """
        rest_json = {'specificProblem': specific_problem,
                     'probableCause': probable_cause,
                     'eventType': event_type,
                     'managedObjectInstance': managed_object_instance,
                     'perceivedSeverity': perceived_severity,
                     'recordType': record_type}
        restapi = RESTapi(self.build_alarm_url())
        return restapi.post(rest_json)

    # pylint: disable=W0212

    def check_litp_maintenance(self):
        """
        Queries LITP to determine is LITP is in maintenance.
        If LITP is in maintenance a SystemExit exception will be
        raised.
        :return: None
        :raises: SystemExit
        """

        litp_maintenance = LitpMaintenance(client=self.litp_rest)
        try:
            if litp_maintenance.is_maintenance_mode():
                self.logger.warning("LITP is in maintenance mode")
                return True
            else:
                return False
        except ValueError as val_error:
            self.logger.error('Cannot check if LITP is in maintenance mode. '
                              '{0}'.format(str(val_error)))
            raise SystemExit(1)

    def nasaudit_main(self):
        """
        Main function
        """
        nas_check = HealthCheck()
        if not self.check_litp_maintenance():
            nas_info = nas_check._get_nas_info()
            for nas in nas_info:
                nas_pwd = nas_check._get_psw(nas_info[nas][2],
                                             nas_info[nas][1],
                                             sanitise=False)
                nas_console = NasConsole(nas_info[nas][0], nas_info[nas][1],
                                         nas_pwd)
                ls_va_res = nas_console.exec_basic_nas_command(
                    nas_check.NAS_VA_CHECK, as_master=False)
                ls_va74_res = nas_console.exec_basic_nas_command(
                    nas_check.NAS_VA74_CHECK, as_master=False)
                if ls_va_res[0] == 0 or ls_va74_res[0] == 0:
                    retcode = nas_console.exec_basic_nas_command(
                        nas_check.NAS_AUDIT, as_master=False)
                    self.logger.info("HealthCheck status: PASSED, "
                                     "Checking Alarm Status..")
                    if retcode[0] == 3:
                        self.build_alarm()
                        self.build_alarm(perceived_severity='WARNING')
                        self.logger.info("Warning Alarm was Raised!")
                    elif retcode[0] in [1, 2]:
                        self.build_alarm()
                        self.build_alarm(perceived_severity='WARNING')
                        self.logger.info("Error Alarm was Raised!")
                    elif retcode[0] == 0:
                        self.build_alarm()
                        self.logger.info("Alarm was Cleared!")
                else:
                    self.logger.error('HealthCheck status: FAILED.')
                    raise SystemExit(1)
        else:
            self.logger.warning("Unable to run NAS Audit Error check")


if __name__ == '__main__':
    NAS_AUDITCHECK = NasAuditCheck()
    NAS_AUDITCHECK.nasaudit_main()
