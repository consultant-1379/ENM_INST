"""
This script does the following:
- At install:
    It generates a temporary file that stores a timestamp that is used as
    an input as well as other unique values to generate a key used in
    encryption.
    It encrypts the open text passwords read from SED file
    using the newly generated passkeys and stores the passwords and their
    encrypted values in a temporary properties file.
- At upgrade:
    It generates a temporary file that stores a timestamp that is used as
    an input as well as other unique values to generate a key used in
    encryption.
    It decrypts the password values read from the LITP Model using the
    existing passkeys.
    It encrypts the decrypted passwords using the newly generated passkeys
    and stores the passwords and their encrypted values in a temporary
    properties file

These passwords are used during the deployment of the model.
"""
from argparse import ArgumentParser
from h_litp.litp_utils import main_exceptions
from h_util.h_utils import Sed, exec_process_via_pipes
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_litp.litp_rest_client import LitpRestClient

import platform
import socket
import hashlib
import commands
import sys
import os
import time

IDENMGMT_PATH = "/ericsson/tor/data/idenmgmt/"
ENM_GLOBAL_PROPERTIES_PATH = \
    "/software/items/config_manager/global_properties/"
TEMPFILE_PATH = '/root/'

VARIABLE_TO_PASSKEY_NAME_DICTIONARY = \
    {'openidm_admin_password': 'openidm_passkey',
     'com_inf_ldap_admin_access_password': 'ssoldap_passkey',
     'ldap_admin_password': 'opendj_passkey',
     'postgresql01_admin_password': 'postgresql01_passkey',
     'default_security_admin_password': 'secadmin_passkey',
     'neo4j_admin_user_password': 'neo4j_passkey',
     'neo4j_dps_user_password': 'neo4j_passkey',
     'neo4j_reader_user_password': 'neo4j_passkey',
     'neo4j_ddc_user_password': 'neo4j_passkey'
     }

PROPERTY_TO_PASSKEY_NAME_DICTIONARY = \
    {'property_openidm_admin_password': 'openidm_passkey',
     'property_com_inf_ldap_amin_access': 'ssoldap_passkey',
     'property_ldap_amin_password': 'opendj_passkey',
     'property_postgresql01_admin_password': 'postgresql01_passkey',
     'property_default_security_admin_password': 'secadmin_passkey',
     'property_neo4j_admin_user_password': 'neo4j_passkey',
     'property_neo4j_dps_user_password': 'neo4j_passkey',
     'property_neo4j_reader_user_password': 'neo4j_passkey',
     'property_neo4j_ddc_user_password': 'neo4j_passkey'
     }

PROPERTY_TO_TEMPFILE_NAME_DICTIONARY = \
    {'property_openidm_admin_password':
         'openidm_admin_password_encrypted',
     'property_com_inf_ldap_amin_access':
         'com_inf_ldap_admin_access_password_encrypted',
     'property_ldap_amin_password':
         'ldap_admin_password_encrypted',
     'property_postgresql01_admin_password':
         'postgresql01_admin_password_encrypted',
     'property_default_security_admin_password':
         'default_security_admin_password_encrypted',
     'property_neo4j_admin_user_password':
         'neo4j_admin_user_password_encrypted',
     'property_neo4j_dps_user_password':
         'neo4j_dps_user_password_encrypted',
     'property_neo4j_reader_user_password':
         'neo4j_reader_user_password_encrypted',
     'property_neo4j_ddc_user_password':
         'neo4j_ddc_user_password_encrypted'
     }


class EncryptPassword(object):
    """
    Class to handle encrypting passwords using openssl
    """
    def __init__(self, sed_filename, password_store_filename,
                 upgrade, verbose):
        """Initialize instance
        :param sed_filename: SED filename
        :param password_store_filename: filename to store password properties
        :param upgrade: indicates upgrade if present
        :param verbose: if verbose logging mode is required
        """

        self.log = init_enminst_logging()
        self.litp = LitpRestClient()
        if verbose:
            set_logging_level(self.log, 'DEBUG')
        self.upgrade = upgrade
        self.sed = Sed(sed_filename)
        self.password_store_filename = password_store_filename
        self.password_value_dict = {}

    @staticmethod
    def get_host_ipaddress(ms_hostname):
        """
        Get the IP address of the MS hostname
        :param ms_hostname: MS hostname to resolve to an IP address
        :type ms_hostname: string
        :return: IP address of the MS host
        :rtype: string
        """
        return socket.gethostbyname(ms_hostname + '.')

    @staticmethod
    def get_mac_address(ms_hostname):
        """
        Get the hardware address of the MS hostname
        :param ms_hostname: MS hostname to get MAC for
        :type ms_hostname: string
        :return: MAC address
        :rtype: string
        """
        cmd = ("ip addr show | " +
               ("grep -B 1 -w $(grep -w %s /etc/hosts | " % ms_hostname) +
               "grep -m1 -v '127.0.0.1' | " +
               "awk '{print $1}') | " +
               "grep -m1 'link/ether' | awk '{print $2}'")

        return commands.getoutput(cmd)

    @staticmethod
    def get_hostname():
        """
        Get the MS hostname
        :return: MS hostname
        :rtype: string
        """
        return platform.node().lower()

    @staticmethod
    def get_md5digest(txt):
        """
        Generate an MD5 hex digest of a string
        :param txt: Text to use for digest
        :type txt: string
        :return: MD5 hex digest
        :rtype: string
        """
        return hashlib.md5(txt.encode()).hexdigest()

    def gen_timestamp_filename(self, hostname, mac, ip_addr):
        """
        Generate absolute filepath for timestamp marker file
        :param hostname: hostname
        :type hostname: string
        :param mac: MAC address
        :type mac: string
        :param ip_addr: IP address
        :type ip_addr: string
        :return: filepath
        :rtype: string
        """
        return os.path.join(os.sep, TEMPFILE_PATH,
                            self.get_md5digest("%s_%s_%s"
                                               % (hostname, mac, ip_addr)))

    @staticmethod
    def gen_passkey_prefix(hostname, mac, ip_addr, timestamp):
        """
        Returns the passkey prefix which will used as one
        of the inputs to generate the passkey
        :param hostname: hostname
        :type hostname: string
        :param mac: MAC address
        :type mac: string
        :param ip_addr: IP address
        :type ip_addr: string
        :param timestamp: Time stamp
        :type timestamp: string
        :return: filepath
        :rtype: string
        """
        return "%s_%s_%s_%s_" % (hostname, mac, ip_addr, timestamp)

    def write_timestamp_file(self):
        """
        Generate a temporary file to store a timestamp
        that will be read by the Config Manager Plugin
        :return: time stamp
        :rtype: string
        """

        hostname = self.get_hostname()
        mac = self.get_mac_address(hostname)
        ip_addr = self.get_host_ipaddress(hostname)

        datestamp = str(time.time())

        try:
            filename = self.gen_timestamp_filename(
                hostname, mac, ip_addr)

            if os.path.exists(os.path.join(TEMPFILE_PATH, filename)):
                os.remove(os.path.join(TEMPFILE_PATH, filename))

            with open(os.path.join(TEMPFILE_PATH, filename), 'a') as f_name:
                f_name.write(datestamp)
                os.chmod(os.path.join(TEMPFILE_PATH, filename), 0o440)
            f_name.close()

            self.log.debug('Created temporary file {0} '.format(
                    filename))

        except OSError as err:
            raise OSError('Error: Unable to create temporary file containing '
                          'timestamp', err)

        return datestamp

    def encrypt_algorithm(self, passkey, datestamp):
        """
        Generate unique passkey and use it to encrypt password using openssl.
        Each passkey contains a compound of 5 values: hostname, mac, ip,
        timestamp, passkey-name making them unique per site.
        Config-Manager Plugin uses same encrypt algorithm.
        :param passkey: passkey password type
        :type passkey: string
        :param datestamp: Generated timestamp
        :type datestamp: string
        :return: passkey hash
        :rtype: string
        """
        hostname = self.get_hostname()
        mac = self.get_mac_address(hostname)
        ip_addr = self.get_host_ipaddress(hostname)

        passkey_prefix = self.gen_passkey_prefix(
            hostname, mac, ip_addr, datestamp)

        passkey_txt = passkey_prefix + passkey
        passkey_digest = self.get_md5digest(
            passkey_txt)

        return passkey_digest

    def encrypt_sed_passwords(self):
        """
        At install, iterate over all known variables for configmanager,
        retrieve clear text password from SED file.
        Encrypt clear text password using uniquely generated passkey
        and finally append them to property file
        """

        with open(self.password_store_filename, 'a') as property_file:
            property_file.write('#Generated properties for configmanager\n')

            datestamp = self.write_timestamp_file()

            for variable_name in VARIABLE_TO_PASSKEY_NAME_DICTIONARY:
                passkey_name = \
                    VARIABLE_TO_PASSKEY_NAME_DICTIONARY[variable_name]

                clear_text_passwd = self.sed.get_value(variable_name)
                if clear_text_passwd is None:
                    raise Exception(
                        'Password %s in SED must not be empty '
                        'string at Install' % variable_name)
                else:
                    passkey_digest = \
                        self.encrypt_algorithm(passkey_name, datestamp)
                    encrypt_variable = self.encrypt_clear_text_password(
                        variable_name, clear_text_passwd, passkey_digest)
                    variable_name_encrypted = "%s_encrypted" % variable_name
                    property_entry = "%s=%s\n" % (variable_name_encrypted,
                                                  encrypt_variable)

                property_file.write(property_entry)

            property_file.close()

        self.log.info("Function sed properties completed")

    def read_values(self):
        """
        Reads the values of a known list of passwords from the LITP Model
        and stores their values in a dictionary
        """
        self.log.info('Reading the values of the required '
                      'passwords from the LITP Model')

        for prop in PROPERTY_TO_PASSKEY_NAME_DICTIONARY:
            if self.litp.exists(os.path.join(
                        ENM_GLOBAL_PROPERTIES_PATH, prop)):
                enm_passwords_prop_info = self.litp.get(
                        os.path.join(ENM_GLOBAL_PROPERTIES_PATH, prop))
                self.password_value_dict[prop] = \
                    enm_passwords_prop_info.get(
                        'properties').get('value')
            else:
                raise Exception(
                    'Could not read %s from LITP model' % prop)

    def decrypt_passwords(self):
        """
        Decrypt the password values read from the LITP model
        using openssl tool and passkeys in /ericsson/tor/data/idenmgmt/
        """
        self.log.debug('Decrypting')

        for prop in self.password_value_dict:
            passkey_name = PROPERTY_TO_PASSKEY_NAME_DICTIONARY[prop]
            with open(os.path.join(
                    IDENMGMT_PATH, passkey_name), 'r') as keyfile:
                passkey_password = keyfile.readline()

            keyfile.close()

            echo_command = "echo %s " % self.password_value_dict[prop]

            echo_command_parts = echo_command.split()

            openssl_command = \
                "/usr/bin/openssl enc -a -d -aes-128-cbc -salt -k %s" \
                % passkey_password
            openssl_command_parts = openssl_command.split()

            try:
                output = \
                    exec_process_via_pipes(echo_command_parts,
                                           openssl_command_parts)

                decrypted_password = output.strip()
                self.password_value_dict[prop] = decrypted_password
            except Exception as ex:
                self.log.error('Password decryption failed for property %s'
                               % prop)
                raise SystemExit(ex)

    def encrypt_configmanager_passwords(self):
        """
        Iterate over all known variables for configmanager,
        retrieve encrypted password from the LITP Model.
        Decrypt the password using the corresponding passkey file in
        /ericsson/tor/data/idenmgmt/.
        Encrypt the password using the newly generated unique passkey value
        and finally append them to a temporary property file
        """
        self.read_values()

        self.decrypt_passwords()

        with open(self.password_store_filename, 'a') as property_file:
            property_file.write('#Generated properties for configmanager\n')

            datestamp = self.write_timestamp_file()

            for prop in self.password_value_dict:
                passkey_name = \
                    PROPERTY_TO_PASSKEY_NAME_DICTIONARY[prop]
                clear_text_passwd = self.password_value_dict[prop]
                passkey_digest = \
                    self.encrypt_algorithm(passkey_name, datestamp)
                encrypt_variable = \
                    self.encrypt_clear_text_password(prop, clear_text_passwd,
                                                     passkey_digest)
                variable_name_encrypted = \
                    PROPERTY_TO_TEMPFILE_NAME_DICTIONARY[prop]
                property_entry = "%s=%s\n" % (variable_name_encrypted,
                                              encrypt_variable)

                property_file.write(property_entry)

            property_file.close()

        self.log.info("Function configmanager properties completed")

    def encrypt_clear_text_password(self, variable_name,
                                    clear_text_password, passkey_password):
        """
        Encrypt clear text password using openssl tool and a unique passkey
        password
        :param variable_name: name of variable to encrypt
        :type variable_name: string
        :param clear_text_password: clear text password
        :type clear_text_password: string
        :param passkey_password: passkey phrase used to encrypt password
        :type passkey_password: string
        :return: encrypted password
        :rtype: string
        """
        echo_command = "echo %s " % clear_text_password
        echo_command_parts = echo_command.split()

        openssl_command = \
            "/usr/bin/openssl enc -e -aes-128-cbc -a -salt -k %s" \
            % passkey_password
        openssl_command_parts = openssl_command.split()

        try:
            output = \
                exec_process_via_pipes(echo_command_parts,
                                       openssl_command_parts)
            encrypted_password = output.splitlines()
            encrypted_password = "".join(encrypted_password)
            encrypted_password = encrypted_password.strip()
            if not encrypted_password:
                self.log.error('Password encryption failed - generated empty '
                               'password - for password variable %s'
                               % variable_name)
                raise \
                    SystemExit('Password encryption failed for %s'
                               % variable_name)
            self.log.debug('Password encrypted for variable %s '
                           % variable_name)
            return encrypted_password
        except Exception as ex:
            self.log.error('Password encryption failed for variable %s'
                           % variable_name)
            raise SystemExit(ex)

    def encrypt_passwords(self):
        """
        Encrypt all passwords used in the system
        Generate a temporary file to store the timestamp
        of install or upgrade
        At install, password values read from SED
        At upgrade, password values read from LITP Model
        """

        if self.upgrade:
            self.encrypt_configmanager_passwords()
        else:
            self.encrypt_sed_passwords()


def encrypt(parsed_args):
    """Encrypt passwords used in system
    :param parsed_args configuration of encryption
    :rtype Namespace
    """
    instance = EncryptPassword(parsed_args.sed_file,
                               parsed_args.passwords_store,
                               parsed_args.upgrade,
                               parsed_args.verbose)

    instance.encrypt_passwords()


def create_parser():
    """Create and configure command line parser instance
    :return: parser instance
    :rtype: ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        default=False, help="Enable all debugging output")
    parser.add_argument('--sed', dest="sed_file",
                        required=True, help='Site Engineering file')
    parser.add_argument('--passwords_store',
                        required=True, help='Passwords store properties file')
    parser.add_argument('--upgrade', action='store_true',
                        default=False,
                        help='Indicates upgrade if present')
    return parser


# =============================================================================
# Main
# =============================================================================
def main(args):
    """
    Main function parsing command arguments and running encryption
    :param args:command line arguments
    :type args: List
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args[1:])
    encrypt(parsed_args)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
