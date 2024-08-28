"""
Module containing classes to represent blades, interact with LITP
and interact with the OA.  Also functions to retrieve blade lists,
set up logging and run remote commands.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################
import os
import sys
import logging
from time import sleep

from netaddr import IPAddress, AddrFormatError

from expansion_settings import REPORT_FILE
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpException
from h_util.h_utils import _pexpect_execute_remote_command


LOGGER = logging.getLogger("enminst")


class ExpansionException(Exception):
    """
    Simple Expansion Exception
    """
    pass


class ValidationException(Exception):
    """
    General Validation exception
    """
    pass


class Blade(object):  # pylint: disable=R0903,R0902
    """
    Class to represent a blade for chassis migration
    """
    def __init__(self):
        """
        Init method
        """
        self.hostname = None
        self.sys_name = None
        self.serial_no = None
        self.src_ilo = None
        self.dest_ilo = None
        self.src_bay = None
        self.dest_bay = None
        self.ilo_user = None
        self.ilo_pass_key = None

    def __str__(self):
        """
        Allow for object to be represented as a string
        :return: string representing the object
        """
        out = 'Blade Details:\n'
        out += 'Hostname: {0}\n'.format(self.hostname)
        out += 'Sys Name: {0}\n'.format(self.sys_name)
        out += 'Serial #: {0}\n'.format(self.serial_no)
        out += 'Src iLO : {0}\n'.format(self.src_ilo)
        out += 'Dest iLO: {0}\n'.format(self.dest_ilo)
        out += 'Src Bay : {0}\n'.format(self.src_bay)
        out += 'Dest Bay: {0}\n'.format(self.dest_bay)
        return out


class LitpHandler(object):
    """
    Class to handle interactions with LITP
    """
    BMC = '/infrastructure/systems/{0}_system/bmc'

    def __init__(self):
        """
        Init method
        """
        LOGGER.debug('Instantiating LitpHandler object')
        try:
            self.rest = LitpRestClient()
            self.enm_nodes = self.rest.get_cluster_nodes()
            self.enm_clusters = self.enm_nodes.keys()
            self.enm_clusters.sort()
            self.enm_system_names = self._get_enm_system_names()
        except LitpException as err:
            LOGGER.error('Failed to get system information from LITP: %s', err)
            raise

    def _get_enm_system_names(self):
        """
        Get a list of the system names defined in LITP
        :return: the list of system names
        """
        LOGGER.debug('Entered _get_enm_system_names')
        system_names = []
        for cluster in self.enm_clusters:
            LOGGER.info('Getting system names in %s cluster', cluster)
            for sys_name in self.enm_nodes.get(cluster):
                system_names.append(sys_name)
        return system_names

    def get_ilo_properties(self, enm_system_name):
        """
        Use the system name to retrieve the corresponding
        BMC properties as a dict
        :param enm_system_name: system name of server (e.g. svc-1)
        :return: dict of BMC properties
        """
        LOGGER.debug('Entered get_ilo_properties with %s', enm_system_name)
        bmc_path = self.BMC.format(enm_system_name)
        try:
            bmc_item = self.rest.get(bmc_path, False)
            LOGGER.debug('BMC item: %s', bmc_item)
            bmc_properties = bmc_item['properties']
            bmc_properties['state'] = bmc_item['state']
        except LitpException as err:
            LOGGER.error('Failed to BMC item from LITP %s', err)
            raise
        return bmc_properties

    def delete_ilo_entry(self, enm_system_name):
        """
        Delete from LITP the BMC item corresponding to the system name
        :param enm_system_name: system name of server (e.g. svc-1)
        :return: True/False
        """
        LOGGER.debug('Entered delete_ilo_entry')
        bmc_path = self.BMC.format(enm_system_name)
        try:
            res = self.rest.delete_path(bmc_path)
        except LitpException as err:
            LOGGER.error('Failed to delete BMC item from LITP %s', err)
            raise
        return res

    def create_ilo_entry(self, enm_system_name, bmc_properties):
        """
        Create a LITP BMC item for the node using the property dict
        :param enm_system_name: system name of server (e.g. svc-1)
        :param bmc_properties: dict containing BMC properties
        :return: results from LITP rquest
        """
        LOGGER.debug('Entered create_ilo_entry')
        parent = '/infrastructure/systems/{0}_system/'.format(enm_system_name)
        data = {'id': 'bmc', 'type': 'bmc', 'properties': bmc_properties}
        try:
            res = self.rest.https_request('POST', parent, data=data)
        except LitpException as err:
            LOGGER.error('Failed create BMC item in LITP %s', err)
            raise
        return res

    def get_hostname(self, enm_system_name):
        """
        Use the system name to retrieve the corresponding
        hostname from LITP
        :param enm_system_name: system name of server (e.g. svc-1)
        :return:
        """
        LOGGER.debug('Entered get_hostname')
        for cluster in self.enm_clusters:
            for node in self.enm_nodes.get(cluster).values():
                if node.path.endswith(enm_system_name):
                    return node.properties['hostname']
        err = 'Failed to get hostname {0} from LITP'.format(enm_system_name)
        raise ExpansionException(err)


class OnboardAdministratorHandler(object):
    """
    Class to handle interactions with the OA
    """
    def __init__(self, ip_1, ip_2, user, passwd):
        """
        init method
        """
        self.ip_1 = ip_1
        self.ip_2 = ip_2
        self.user = user
        self.passwd = passwd
        self.active_ip = None

    def oa_cmd(self, cmd, ip_addr=None, retries=3):
        """
        Run a command on the OA, using active_ip if ip_addr is not set
        :param cmd: the command to be ran
        :param ip_addr: IP address to
        :param retries:
        :return: output from command
        """
        if not ip_addr:
            ip_addr = self.active_ip

        ssh_cmd = 'ssh {0}@{1} {2}'.format(self.user, ip_addr, cmd)
        LOGGER.info('Running: %s', ssh_cmd)
        for attempt in xrange(1, retries + 1):
            try:
                stdout = _pexpect_execute_remote_command(ssh_cmd, self.passwd)
                LOGGER.info('Finished running: %s', ssh_cmd)
                return stdout
            except (OSError, IOError) as err:
                if attempt == retries:
                    LOGGER.error('Failed to run %s: %s', ssh_cmd, err)
                    raise
                else:
                    LOGGER.warn('Command failed, retrying')

    def set_active_ip(self, force=False):
        """
        Determine the active ip for the OA
        and set object attribute to it
        :return:
        """
        LOGGER.debug('Entered set_active_ip')
        cmd = "SHOW OA STATUS"
        if self.active_ip and not force:
            return

        self.active_ip = None

        for ip_addr in [self.ip_1, self.ip_2]:
            stdout = self.oa_cmd(cmd, ip_addr)
            stdout = stdout.replace(' ', '')

            if 'Role:Active' in stdout:
                LOGGER.debug('Active OA IP is: %s', ip_addr)
                self.active_ip = ip_addr
                return ip_addr

        LOGGER.error("Failed to find active OA")
        raise EnvironmentError("Failed to find active OA")

    def show_server_names(self):
        """
        Run OA command SHOW SERVER NAMES and return the output
        :return: output from command
        """
        LOGGER.debug('Entered show_server_names')
        cmd = "SHOW SERVER NAMES"
        self.set_active_ip()
        return self.oa_cmd(cmd)

    def show_server_list(self):
        """
        Run OA command SHOW SERVER LIST and return the output
        :return: output from command
        """
        LOGGER.debug('Entered show_server_names')
        cmd = "SHOW SERVER LIST"
        self.set_active_ip()
        return self.oa_cmd(cmd)

    def power_on_system(self, bay):
        """
        Run OA command POWERON SERVER <BAY> and return the output
        param bay: the bay number to power on
        :return: output from command
        """
        LOGGER.debug('Entered power_on_system')
        cmd = "POWERON SERVER {0}".format(bay)
        self.set_active_ip()
        return self.oa_cmd(cmd)

    def show_ebipa_server(self):
        """
        Run OA command SHOW EBIPA SERVER
        :return: output from command
        """
        LOGGER.debug('Entered show_ebipa_server')
        self.set_active_ip()
        cmd = 'SHOW EBIPA SERVER'
        return self.oa_cmd(cmd)

    # pylint: disable=R0913
    def set_ebipa_server(self, bay, ip_addr=None, netmask='', gateway=None,
                         domain=None):
        """
        Run OA commands SET EBIPA SERVER, ENABLE and SAVE
        :param bay: bay number to set
        :param ip_addr: iLO IP address
        :param netmask: the netmask
        :param gateway: the gateway IP
        :param domain: the domain to be set
        :return: None
        """
        LOGGER.debug('Entered set_ebipa_server')
        self.set_active_ip()

        # DO I NEED TO DISABLE FIRST?
        if ip_addr:
            cmd = 'SET EBIPA SERVER {0} {1} {2}'.format(ip_addr, netmask, bay)
            LOGGER.info('Running %s', cmd)
            output = self.oa_cmd(cmd)
            LOGGER.info('Output:\n%s', output)

        if gateway:
            cmd = 'SET EBIPA SERVER GATEWAY {0} {1}'.format(gateway, bay)
            LOGGER.info('Running %s', cmd)
            output = self.oa_cmd(cmd)
            LOGGER.info('Output:\n%s', output)

        if domain:
            cmd = 'SET EBIPA SERVER DOMAIN {0} {1}'.format(domain, bay)
            LOGGER.info('Running %s', cmd)
            output = self.oa_cmd(cmd)
            LOGGER.info('Output:\n%s', output)

        cmd = 'ENABLE EBIPA SERVER {0}'.format(bay)
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)

    def disable_ebipa_server(self, bay):
        """
        Run OA commands DISABLE EBIPA SERVER
        :param bay: bay number to set
        :return: None
        """
        LOGGER.debug('Entered disable_ebipa_server')
        self.set_active_ip()

        cmd = 'DISABLE EBIPA SERVER {0}'.format(bay)
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)

        cmd = 'SET EBIPA SERVER NONE NONE {0}'.format(bay)
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)

        cmd = 'SET EBIPA SERVER GATEWAY NONE {0}'.format(bay)
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)

    def save_ebipa(self):
        """
        Run OA command SAVE EBIPA
        :return: None
        """
        cmd = 'SAVE EBIPA'
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)

    def show_oa_network(self):
        """
        Run OA command SHOW OA NETWORK and return the output
        :return: output from command
        """
        self.set_active_ip()
        cmd = 'SHOW OA NETWORK'
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)
        return output

    def efuse_reset(self, bay):
        """
        Run OA command SHOW RESET SERVER and return the output
        :return: output from command
        """
        self.set_active_ip()
        cmd = 'RESET SERVER {0}'.format(bay)
        LOGGER.info('Running %s', cmd)
        output = self.oa_cmd(cmd)
        LOGGER.info('Output:\n%s', output)
        return output


def get_info_from_network_output(network_output):
    """
    Parse SHOW OA NETWORK
    :param network_output: output from OA command
    :return: gateway and netmask
    """
    LOGGER.debug('Entered get_gateway_netmask_from_network_output')
    gateway = None
    netmask = None

    for line in network_output.split('\n'):
        words = line.split()
        if words and words[0] == 'Netmask:':
            netmask = words[1]
        if words and words[0] == 'Gateway' and words[1] == 'Address:':
            gateway = words[2]

    if not gateway:
        LOGGER.error('Failed get gateway from network output')
        raise ExpansionException('Could not get gateway information')

    if not netmask:
        LOGGER.error('Failed to get netmask from network output')
        raise ExpansionException('Could not get netmask information')
    return gateway, netmask


def get_bays_from_server_output(server_output):
    """
    Parse OA SHOW SERVER NAMES
    :param server_output: output from OA command
    :return: dict of bay number: serial no
    """
    LOGGER.debug('Entered get_bays_from_server_output')
    bays_serial = {}
    for line in server_output.split('\n'):
        if '[Absent]' in line:
            continue

        words = line.split()
        if words and words[0].isdigit():
            try:
                bays_serial[words[0]] = words[-4]
                LOGGER.debug('%s  = %s:%s', line, words[0], words[-4])
            except IndexError as err:
                LOGGER.error("Failed to parse %s: %s", line, err)
                raise
    LOGGER.debug('Returning %s', bays_serial)
    return bays_serial


def get_ilo_bays_from_ebipa_output(ebipa_output):
    """
    Parse OA SHOW EBIPA SERVER OUTPUT
    :param ebipa_output: output from OA command
    :return: dict of ilo ip: bay number
    """
    LOGGER.debug('Entered get_bays_from_ebipa_output')
    # returns dict of ilo ip key, with bay value
    ilo_bays = {}
    try:
        for line in ebipa_output.split('\n'):
            words = line.split()
            if words and words[0].isdigit():
                try:
                    ilo_bays[words[2]] = words[0]
                except IndexError:
                    continue
        return ilo_bays
    except IndexError:
        LOGGER.error('Failed to parse OA ebipa output')
        raise


def get_blades_from_litp(rollback):
    """
    Return a lit of blade objects made from what is modelled in LITP
    Only even numbered blades are returned e.g. svc-2, svc-4.  The
    blade objects are populated with the hostname, system name, and
    source ilo IP address.
    :param:
    :return: list of Blade Objects
    """
    LOGGER.debug('Entered get_blades_from_litp')

    # Create initial list of blade objects, setting some of the attributes
    # from what is available in LITP
    blades = []
    litp = LitpHandler()
    for sys_name in litp.enm_system_names:
        blade_number = int((sys_name.split('-')[1]))
        # We are only interested in blades with an even number, e.g. db-2,
        # or svc-4
        if blade_number % 2 == 1:
            LOGGER.debug("Odd numbered blade: %s - this will not be moved",
                         sys_name)
            continue
        LOGGER.debug('Getting details from LITP for: %s', sys_name)
        blade = Blade()
        blade.hostname = litp.get_hostname(sys_name)
        blade.sys_name = sys_name
        bmc_properties = litp.get_ilo_properties(sys_name)

        if rollback:
            LOGGER.info('Rollback so setting src_ilo to unknown')
            blade.src_ilo = 'Unknown'
        else:
            LOGGER.info('Getting src_ilo from LITP')
            blade.src_ilo = bmc_properties['ipaddress']
            blade.ilo_user = bmc_properties['username']
            blade.ilo_pass_key = bmc_properties['password_key']

        LOGGER.info('%s has LITP ilo of %s', blade.sys_name,
                    bmc_properties['ipaddress'])

        blades.append(blade)
    return blades


def get_blade_info(enclosure_oa, sed_ilos, sed_serial_dict, rollback=False):
    """
    Use the OnboardAdministratorHandler and LitpHandler methods to create
    a list of Blade objects with all their attributes set
    :param enclosure_oa:
    :param sed_ilos:
    :param sed_serial_dict:  [node] = serial_no
    :param rollback:
    :return:
    """
    LOGGER.debug('Entered get_blade_info')
    LOGGER.info('sed_ilos: %s', sed_ilos)
    LOGGER.info('sed_serial_dict: %s', sed_serial_dict)

    # Get a list of Blade Objects from what is defined in LITP.  LITP only
    # holds some of the information we require so only some attributes have
    # their values set, the rest we need to get from the OA of each enclosure
    LOGGER.debug('Getting blade information from LITP')
    blades = get_blades_from_litp(rollback)

    LOGGER.info('Getting additional information from the OA')
    # Get hostnames & serial numbers from src OA and construct dicts
    # of the form {hostname: serial number}
    show_server_out = enclosure_oa.show_server_names()
    src_bays_serial_no = get_bays_from_server_output(show_server_out)

    # Iterate through the list of Blade Objects and use the OA dicts
    # to set their attribute's values
    # LOGGER.debug('src_server_serial: %s', src_server_serial)
    LOGGER.debug('src_bays_serial_no: %s', src_bays_serial_no)

    LOGGER.info('Serial dict is %s', sed_serial_dict)
    for blade in blades:
        LOGGER.info('Setting info for blade %s', blade.sys_name)
        try:
            blade.serial_no = sed_serial_dict[blade.sys_name]
        except KeyError:
            LOGGER.error('Failed to set blade serial number')
            raise

        LOGGER.info('blade serial number is %s', blade.serial_no)
        if rollback:
            try:
                blade.dest_bay = [k for k, v in src_bays_serial_no.iteritems()
                                  if v == blade.serial_no][0]
                blade.src_bay = 'Unknown'
            except IndexError:
                LOGGER.info('Cannot determine dest bay for %s', blade.sys_name)
                blade.dest_bay = 'Unknown'
        else:
            try:
                blade.dest_bay = 'Unknown'
                blade.src_bay = [k for k, v in src_bays_serial_no.iteritems()
                                 if v == blade.serial_no][0]
                LOGGER.info('blade src bay is %s', blade.src_bay)
            except IndexError:
                LOGGER.info('Cannot determine src bay for %s', blade.sys_name)
                blade.src_bay = 'Unknown'

        blade.dest_ilo = sed_ilos[blade.sys_name]
        # If any attribute is not set then something has gone wrong
        # we need to exit
        if not all([blade.hostname, blade.sys_name, blade.serial_no,
                    blade.src_ilo, blade.dest_ilo, blade.src_bay,
                    blade.dest_bay]):
            LOGGER.error("Some blade attributes are missing: %s", blade)
            raise ExpansionException("Retrieving blade details failed")
    LOGGER.debug('Retrieved blade information from LITP and the OA')
    return blades


def is_valid_ip_address(ip_address):
    """
    Function that validates if an IP address is valid.
    :param ip_address: The IP address to validate.
    :return: True if valid, False if not valid.
    """
    try:
        _ = IPAddress(ip_address)
    except (AddrFormatError, ValueError):
        return False

    return True


def sleep_and_write_char(delay=3, symbol='.'):
    """
    Write character to stdout then wait delay
    :param delay: time to wait before leaving function
    :param symbol: character to write
    """
    sleep(delay)
    sys.stdout.write(symbol)
    sys.stdout.flush()


def progress_bar(duration, delay=3):
    """
    Function that prints a progress bar for long running tasks
    :param duration: How long the progress bar should run for.
    :param delay: time to wait before progress character is written
    :return: None
    """
    duration = duration / 3
    for i in xrange(duration):  # pylint: disable=unused-variable
        sleep_and_write_char(delay)
    sleep_and_write_char(delay=0, symbol='\n')


def display_time(seconds, granularity=2):
    """
    Function that converts seconds to hours/minutes/seconds
    :param seconds: The number of seconds to convert.
    :param granularity: The number of time units to display,
    e.g. granularity 2 will convert seconds in X hours Y minutes
    :return: The converted time as a Str
    """
    intervals = (('hours', 3600),
                 ('minutes', 60),
                 ('seconds', 1))
    result = []
    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{0} {1}".format(value, name))
    return ', '.join(result[:granularity])


def report_file_ok():
    """
    Function that validates the Enclosure report file exists and is valid.
    :return: Boolean indicating if the file is valid.
    """
    if not os.path.exists(REPORT_FILE):
        LOGGER.error('Report file %s does not exist', REPORT_FILE)
        return False

    with open(REPORT_FILE, 'r') as rep:
        report_contents = rep.read()

    if 'DETAILS OF DESTINATION ENCLOSURE' in report_contents and \
            '[Absent]' in report_contents:
        LOGGER.debug('Report file is ok')
        return True

    LOGGER.error('Report file is missing required information')
    return False
