"""
The purpose of this script is to query the SAN
storage to determine if there are any faults.
If a fault is found an fmalarm should be created.
"""
# pylint: disable=E1101,R0902
##############################################################################
# COPYRIGHT Ericsson AB 2023
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################
import os
import json
import requests
# pylint: disable=import-error,no-name-in-module,unused-import
from naslib.connection import NasConnection
from naslib.nasexceptions import NasConnectionException
from clean_san_luns import SanCleanup
from h_litp.litp_utils import main_exceptions
from h_litp.litp_maintenance import LitpMaintenance
from h_logging.enminst_logger import init_enminst_logging
from h_litp.litp_rest_client import LitpRestClient, LitpException
from h_util.h_utils import get_nas_type
from sanapi import api_builder
from sanapiexception import SanApiException
from clean_san_luns import IP_A, LOGIN_SCOPE, SAN_TYPE, \
    USERNAME, SAN_PASSW

ALARM_TEMPLATE = {"specificProblem": "Dell EMC SAN Storage Critical Alert",
                  "probableCause": "None",
                  "eventType": "SAN Issue",
                  "managedObjectInstance": "ENM",
                  "perceivedSeverity": "CRITICAL",
                  "recordType": "ALARM"}

NAS_SERVER_MESS = "NAS Servers on the SAN are not balanced correctly. " \
                  "Ignore if routine maintenance is being done on the SAN."

ALARM_REQUEST_HEADER = {"Content-Type": "application/json"}
ALARM_REQUEST_PATH = "/internal-alarm-service/internalalarm/" \
                     "internalalarmservice/translate"

SAN_ALERT_THRESHOLD = 2
SAN_ALERT_INACTIVE = 2
SAN_ALERT_FILTER_FILE = '/opt/ericsson/enminst/etc/dell_unity_alert_filters'
ALARMS_FILE_PATH = "/var/log/current_san_alarms.txt"


class SanFaultCheck(object):
    """
    Class to create and clear SAN FMalarms
    """

    def __init__(self):
        self.logger = init_enminst_logging()
        self.litp_rest = LitpRestClient()
        self.san_alerts = []
        self.alerts_to_create = []
        self.alerts_to_clear = []
        self.litp_nas_servers = []
        self.haproxy_int_ip = None
        self.nas_server_fault = False

    def is_unityxt(self):
        """
        Checks if SAN is UnityXT
        :return: Bool
        """
        try:
            if get_nas_type(self.litp_rest) == "unityxt":
                return True
        except LitpException as error:
            if error.args[0] == 404 and \
               error.args[1]["reason"] == "Not Found":
                return False
            else:
                self.logger.error("Cannot get SAN type from LITP: {0}".
                                  format(error))
                return False
        except Exception as error:
            self.logger.error("Cannot get SAN type from LITP: {0}".
                              format(error))
            return False

    def get_litp_nas_servers(self):
        """
        Check that there are 2 NAS servers in LITP
        Get the NAS servers names and SPs
        :return: list
        """
        storage_path = "/infrastructure/storage/storage_providers"
        try:
            unityxt_path = self.litp_rest.get_all_items_by_type(
                storage_path,
                'sfs-service', [])[0]['path']
            vs_path = "{0}/{1}".format(unityxt_path, "virtual_servers")
            items = self.litp_rest.get(vs_path, log=False)
        except Exception as error:  # pylint: disable=W0703
            self.logger.error("Cannot get NAS servers from LITP: {0}".
                              format(error))
            return []

        try:
            num_ns = len(items["_embedded"]["item"])
            if num_ns != 2:
                self.logger.error("2 NAS servers expected, "
                                  "{0} found. Check the LITP model.".
                                  format(num_ns))
                self.logger.info("Items found: {0}".format(items))
                return []
        except:  # pylint: disable=W0702
            self.logger.error("NAS servers not found: {0}. "
                              "Check the LITP model.".
                              format(items))
            return []

        try:
            nas_servers = [
                {"name": items["_embedded"]["item"][0]["properties"]["name"],
                 "sp": items["_embedded"]["item"][0]["properties"]["sp"]},
                {"name": items["_embedded"]["item"][1]["properties"]["name"],
                 "sp": items["_embedded"]["item"][1]["properties"]["sp"]}]
        except Exception as error:  # pylint: disable=W0703
            self.logger.error("Missing NAS server information: {0}. "
                              "Check the LITP model.".
                              format(error))
            self.logger.info("Items found: {0}".format(items))
            return []

        return nas_servers

    def check_nas_servers(self, san_info, san):
        """
        Check that the SP for each NAS server matches
        both the homeSP and currentSP on the UnityXT
        :return: None
        """
        for nas_server in self.get_litp_nas_servers():
            try:
                nasconn = NasConnection(san_info[san][IP_A],
                                        san_info[san][USERNAME],
                                        san_info[san][SAN_PASSW],
                                        nas_type='unityxt')
                with nasconn as nas:
                    details = nas.nasserver.get_nasserver_details(
                        nas_server["name"])
            except NasConnectionException:
                self.logger.error("Cannot connect to the SAN. "
                                  "Check the LITP model.")
                return
            except Exception as error:
                self.logger.error("Cannot get NAS server details: {0}".
                                  format(error))
                return

            try:
                home_sp = details['homeSP']['id']
            except:  # pylint: disable=W0702
                self.logger.error("NAS server '{0}' home SP "
                                  "not found: {1}".
                                  format(nas_server["name"],
                                         details))
                return

            try:
                curr_sp = details['currentSP']['id']
            except:  # pylint: disable=W0702
                self.logger.error("NAS server '{0}' current SP "
                                  "not found: {1}".
                                  format(nas_server["name"],
                                         details))
                return

            if nas_server["sp"] != home_sp or \
               nas_server["sp"] != curr_sp:
                self.logger.error("The SP '{0}' for NAS server '{1}' "
                                  "in LITP does not match the SAN - "
                                  "home SP = '{2}' current SP = '{3}'".
                                  format(nas_server["sp"],
                                         nas_server["name"],
                                         home_sp,
                                         curr_sp))
                self.nas_server_fault = True
        return

    def set_haproxy_internal_ip(self):
        """
        Retrieves the haproxy internal IP address from the LITP model
        and stores it in a class variable.
        :return: None
        """
        path = "/deployments/enm/clusters/svc_cluster/services/" \
               "haproxy-int/ipaddresses/haproxy-int_internal_vip"

        try:
            items = self.litp_rest.get(path, log=False)
        except LitpException as err:
            self.logger.error(err)
            raise

        self.haproxy_int_ip = items["properties"]["ipaddress"]

    @staticmethod
    def build_alarm_message(alert):
        """
        Build the post request message for creating an FMalarm.
        The Alarm dictionary is updated with the alerts info and
        converted to a JSON string.
        :param alert from the SAN.
        :return: json string to create an FMalarm.
        """
        ALARM_TEMPLATE["probableCause"] = alert.message

        return json.dumps(ALARM_TEMPLATE)

    def build_alarm_url(self):
        """
        Builds the url that is required to create/clear an FMalarm using the
        haproxy internal IP address and the request path.
        :return: url to create/clear an FMalarm.
        """
        self.set_haproxy_internal_ip()
        url = "http://{ip}:8081{path}".format(ip=self.haproxy_int_ip,
                                              path=ALARM_REQUEST_PATH)

        return url

    def clear_fmalarm(self):
        """
        Attempts to clear an FMalarm by making a post request to the
        FMalarm endpoint.
        The post request JSON used to create the alarm is transformed
        to clear the alarm.
        Will log if the action succeeds or not.
        :return: None
        """
        for alert in self.alerts_to_clear:
            temp_dict = json.loads(alert)
            temp_dict['perceivedSeverity'] = "CLEARED"
            message = json.dumps(temp_dict)
            alarm_url = self.build_alarm_url()

            response = requests.post(url=alarm_url,
                                     headers=ALARM_REQUEST_HEADER,
                                     data=message)

            if response.status_code == 200:
                self.logger.info("HTTP 200 - FMalarm cleared - {0}"
                    .format(alert))
            else:
                self.logger.error("HTTP {0} - Failed to clear FMalarm - {1}"
                    .format(response.status_code, alert))

    def create_fmalarm(self):
        """
        Attempts to create an FMalarm by making a post request to the
        FMalarm endpoint.
        Will log if the action succeeds or not.
        :return: None
        """
        for alert in self.alerts_to_create:
            alarm_url = self.build_alarm_url()

            response = requests.post(url=alarm_url,
                                     headers=ALARM_REQUEST_HEADER,
                                     data=alert)

            if response.status_code == 200:
                self.logger.info("HTTP 200 - " \
                    "FMalarm created for SAN alert - {0}".format(alert))
            else:
                self.logger.error("HTTP {0} - " \
                    "Failed to create FMalarm for SAN alert - {1}"
                    .format(response.status_code, alert))

    @staticmethod
    def get_current_alarms():
        """
        Gets the a list of current alarms from a file.
        The alarms are split and returned as a list.
        :return: list of active alarms.
        """
        current_alarms = []

        if not os.path.exists(ALARMS_FILE_PATH):
            os.mknod(ALARMS_FILE_PATH)

        if os.stat(ALARMS_FILE_PATH).st_size > 0:
            with open(ALARMS_FILE_PATH, 'r') as alarm_file:
                first_line = alarm_file.readline().strip()

            if first_line:
                current_alarms = filter(None, first_line.split("!"))

        return current_alarms

    @staticmethod
    def make_alert_filter():
        """
        Build and return an alert query filter string that filters for
        - All active 'CRITICAL' alerts.
        - Active alerts with alert message IDs in file SAN_ALERT_FILTER_FILE
          if the file exists.
        """
        # Mandatory alert filter for active critical alerts
        alert_filter = 'state ne {0} and severity eq {1}' \
                .format(SAN_ALERT_INACTIVE, SAN_ALERT_THRESHOLD)

        # Check for additional alerts to search for by message ID
        if (not os.path.exists(SAN_ALERT_FILTER_FILE) or
            os.stat(SAN_ALERT_FILTER_FILE).st_size == 0):
            return alert_filter

        # Read alert message ID(s) from file.
        # Skip blank lines and commented lines.
        lines = []
        with open(SAN_ALERT_FILTER_FILE, 'r') as alert_filter_file:
            lines = [line.strip() for line in alert_filter_file if line.strip()
                and not line.strip().startswith('#')]

        # Mandatory alerts plus alerts matching message ID(s) from file.
        if lines:
            alert_filter = 'state ne {0} and (severity eq {1} or (' \
                .format(SAN_ALERT_INACTIVE, SAN_ALERT_THRESHOLD)

            for index, alert_message_id in enumerate(lines):
                alert_filter += 'messageId eq "{0}"'.format(alert_message_id)
                if index != len(lines) - 1:
                    alert_filter += ' or '
            alert_filter += '))'

        return alert_filter

    def write_alarms_to_file(self):
        """
        Writes the alarms to a file.
        The file is overwritten to remove old alarms.
        :return: None
        """
        with open(ALARMS_FILE_PATH, 'w') as alarm_file:
            for alert in self.alerts_to_create:
                alarm_file.write(alert)
                alarm_file.write("!")
            alarm_file.close()

    def get_alarms_to_create_and_clear(self):
        """
        Gets the list of alarms to create and clear.
        Subsequently updates a text file to hold
        the active alarms.
        :return: None
        """

        current_alarms = self.get_current_alarms()

        for alert in self.san_alerts:
            self.alerts_to_create.append(
                SanFaultCheck.build_alarm_message(alert))
        if self.nas_server_fault:
            ALARM_TEMPLATE["probableCause"] = NAS_SERVER_MESS
            self.alerts_to_create.append(
                json.dumps(ALARM_TEMPLATE))

        self.alerts_to_clear = list(set(current_alarms) -
                                    set(self.alerts_to_create))

        self.write_alarms_to_file()

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
                self.logger.warning("LITP is in maintenance mode - "
                                    "Unable to run SAN fault check.")
                return True
            else:
                return False
        except ValueError as error:
            self.logger.error('Cannot check if LITP is in maintenance mode. '
                              '{0}'.format(str(error)))
            raise SystemExit(1)


def main():
    """
    Main function
    :return: None
    """
    san_fault_check = SanFaultCheck()

    if not san_fault_check.check_litp_maintenance():

        san_cleanup = SanCleanup()
        san_info = san_cleanup.get_san_info()

        for san in san_info:

            if san_fault_check.is_unityxt():
                try:
                    san_fault_check.check_nas_servers(san_info, san)
                except Exception as error:  # pylint: disable=W0703
                    san_fault_check.logger.error(
                        "Error checking NAS servers: {0}".format(error))

            if san_info[san][SAN_TYPE].lower() == "unity":
                san_api = api_builder(san_info[san][SAN_TYPE].lower(),
                                      san_fault_check.logger)
                try:
                    san_api.initialise((san_info[san][IP_A],),
                                       san_info[san][USERNAME],
                                       san_info[san][SAN_PASSW],
                                       san_info[san][LOGIN_SCOPE],
                                       esc_pwd=True)

                except SanApiException:
                    san_fault_check.logger.error("Cannot connect to the SAN. "
                                                 "Check the LITP model.")
                    return

                san_fault_check.san_alerts = san_api.get_filtered_san_alerts(
                    [san_fault_check.make_alert_filter()])

                san_fault_check.get_alarms_to_create_and_clear()

                san_fault_check.create_fmalarm()

                san_fault_check.clear_fmalarm()


if __name__ == '__main__':
    main_exceptions(main)
