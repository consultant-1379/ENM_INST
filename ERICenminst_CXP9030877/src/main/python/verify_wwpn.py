"""
Verify SED WWPNs are known to SAN
"""
# pylint: disable=E1101,W0106,R0912
##############################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################

import re
import sys
from netaddr import IPAddress, AddrFormatError
from argparse import ArgumentParser, RawDescriptionHelpFormatter

from h_litp.litp_utils import main_exceptions
from h_util.h_utils import is_valid_file, Sed
from h_logging.enminst_logger import init_enminst_logging, set_logging_level

try:
    SANAPI = True
    from sanapi import api_builder
    from sanapiexception import SanApiException
except ImportError:
    SANAPI = False


class ENMverifyWWPN(object):
    """
    Class to verify SED WWPNs are visible in the SAN
    """

    PARAM_SED_FILE = 'sed_file'
    PARAM_VERBOSE = 'verbose'

    COLOR_RED = '\033[91m'
    COLOR_GREEN = '\033[92m'
    COLOR_NORM = '\033[0m'
    WWPN_PATTERN_TEMPLATE = r'([0-9a-fA-F]{2}[-:]?){%s}[0-9a-fA-F]{2}'

    def __init__(self):
        """
        Initialize logging and instance variables
        :return: None
        """
        self.log = init_enminst_logging('verifywwpn')

        self.processed_args = None
        self.parser = None
        self.san_wwpns = []
        self.sed_wwpns = []
        self.sed_wwpns_dict = {}
        self.sed_sp_ips = []

    def set_verbosity_level(self):
        """
        Set the logging verbosity level
        :return: None
        """

        if getattr(self.processed_args, ENMverifyWWPN.PARAM_VERBOSE, False):
            set_logging_level(self.log, 'DEBUG')

    def create_arg_parser(self):
        """
        Create an argument parser
        :return: None
        """

        this_script = 'verify_wwpn.sh'
        usage_info = ('Verify WWPN visibility to SAN.\n' +
                      'Example: %s -v ' +
                      '-s /software/autoDeploy/MASTER_siteEngineering.txt') % \
                      this_script

        self.parser = ArgumentParser(prog=this_script,
                                   usage='%(prog)s [-h] [-v] -s SED',
                                   formatter_class=RawDescriptionHelpFormatter,
                                   epilog=usage_info, add_help=False)

        required_group = self.parser.add_argument_group('required arguments')

        required_group.add_argument('-s', '--sed',
                                 dest=ENMverifyWWPN.PARAM_SED_FILE,
                                 metavar='SED',
                                 type=lambda x: is_valid_file(self.parser,
                                                              'SED', x),
                                 help='Path to site engineering document')

        optional_group = self.parser.add_argument_group('optional arguments')

        optional_group.add_argument('-h', '--help',
                                action='help',
                                help='Show this help message and exit')

        optional_group.add_argument('-v', '--verbose',
                                 dest=ENMverifyWWPN.PARAM_VERBOSE,
                                 default=False, action='store_true',
                                 help='Verbose logging')

    def get_sed_arg(self):
        """
        Helper method to get the processed argument for the SED
        :return: SED string
        """

        return getattr(self.processed_args, ENMverifyWWPN.PARAM_SED_FILE)

    def read_sed_file(self):
        """
        Read all Site-Engineering-Document data lines
        :return: dict of sed data
        """
        sed_obj = Sed(self.get_sed_arg())

        return sed_obj.sed

    def process_sed_san_sp_ips(self, sed_lines):
        """
        Process/parse/extract the SAN Service Processor addresses
        from the SED data lines
        :param sed_lines: Input data lines list from SED
        :return: None
        """
        self.sed_sp_ips = [sed_lines.get(key)
                           for key in ["san_spaIP", "san_spbIP"]
                           if sed_lines.get(key) is not None]

    def is_valid_sed_sp_ips(self):
        """
        Validate that at least one SAN service processor IP address
        has been retrieved from the SED
        :return: None
        """

        if not len(self.sed_sp_ips) >= 1:
            msg = ('At least 1 SAN SP IP address '
                   '(san_spaIP or san_spbIP) expected in SED "%s". '
                   'Found the following: %s' %
                   (self.get_sed_arg(), self.sed_sp_ips))
            self.log.error(msg)
            sys.exit(1)

        errors = 0
        for sp_ip in self.sed_sp_ips:
            try:
                _ = IPAddress(sp_ip)
            except (AddrFormatError, ValueError):
                errors += 1
                self.log.error("Invalid SP IP address value '%s'" % sp_ip)

        if errors:
            sys.exit(1)

        return True

    def process_sed_wwpns(self, sed_lines):
        """
        Process/parse/extract the WWPN values from the SED data lines
        :param sed_lines: Input data lines list from SED
        :return: None
        """
        for key, value in sed_lines.iteritems():
            if 'WWPN' in key and value is not None:
                self.sed_wwpns_dict[sed_lines.get(key).lower()] = key
        self.sed_wwpns = list(self.sed_wwpns_dict.keys())

    def is_valid_sed_wwpns(self):
        """
        Validate the length and format of each SED WWPN
        :return: None
        """
        wwpn_short_pattern = ENMverifyWWPN.WWPN_PATTERN_TEMPLATE % '7'
        pattern = r'^(?P<wwpn>%s)$' % wwpn_short_pattern

        non_blank_sed_wwpns = [wwpn for wwpn in self.sed_wwpns
                               if not wwpn == '']
        if not len(non_blank_sed_wwpns) == len(self.sed_wwpns):
            self.sed_wwpns = non_blank_sed_wwpns
            self.log.warn('Blank SED WWPN(s) found but ignored')

        valid_wwpns = []
        ENMverifyWWPN.process_datalines(self.sed_wwpns, pattern, valid_wwpns)

        invalid_wwpns = list(set(self.sed_wwpns) - set(valid_wwpns))
        if invalid_wwpns:
            for wwpn in invalid_wwpns:
                self.log.error('Invalid SED WWPN "%s"' % wwpn)
            sys.exit(1)

        return True

    @staticmethod
    def process_datalines(datalines, pattern,
                          results_list, group_key='wwpn'):
        """
        Process a set of data lines
        :param datalines: Input data lines list
        :param pattern: Regular expression pattern string
        :param results_list: List to which extracted values should be appended
        :param group_key: Regular expression group keyname string
        :return: None
        """

        regexp = re.compile(pattern)

        for line in datalines:
            line = line.strip()
            match = regexp.search(line)
            if match:
                parts = match.groupdict()
                if parts:
                    if group_key in parts.keys():
                        group_value = parts[group_key]
                        if group_key in ['san_username', 'san_password']:
                            results_list.append(group_value)
                        else:
                            results_list.append(group_value.lower())

    def compare_wwpns(self):
        """
        Iterate through the extracted SED WWPNs
        and verify each of those SED WWPNs can be
        found in the WWPNs known to the SAN.
        Print a green SED WWPN when it is known to the SAN.
        Print a red SED WWPN when it is not known to the SAN.
        :return: Number of wwpns not visible to the SAN
        """
        count_non_visible = 0
        for sed_wwpn in self.sed_wwpns:
            found = False
            for san_wwpn in self.san_wwpns:
                if san_wwpn.endswith(sed_wwpn):
                    found = True
                    break
            if found:
                self.print_colored_report(sed_wwpn,
                                          ENMverifyWWPN.COLOR_GREEN)
            else:
                self.print_colored_report(sed_wwpn,
                                          ENMverifyWWPN.COLOR_RED,
                                          'not ')
                count_non_visible = count_non_visible + 1
        return count_non_visible

    def print_colored_report(self, wwpn, start_color, extra=''):
        """
        Print a line to standard output
        :param wwpn: The WWPN to include in the print line
        :param start_color: Color to use to print the WWPN
        :param extra: Optional extra token for line
        :return: None
        """
        self.log.info("%s%s%s %svisible on SAN" %
                      (start_color, "{0:<41}".format
                      (wwpn + " (" + self.sed_wwpns_dict[wwpn]
                       + ")"), ENMverifyWWPN.COLOR_NORM, extra))


def main(args):
    """
    Main function
    :return: None
    """

    verifier = ENMverifyWWPN()
    verifier.create_arg_parser()

    verifier.processed_args = verifier.parser.parse_args(args[1:])

    if not vars(verifier.processed_args)[ENMverifyWWPN.PARAM_SED_FILE]:
        verifier.parser.error('argument -s/--sed is required')

    if not SANAPI:
        verifier.log.warn(
            'The SANAPI is not installed on the LMS. Skip the SAN cleanup')
        return

    verifier.set_verbosity_level()

    sed_lines = verifier.read_sed_file()
    verifier.process_sed_san_sp_ips(sed_lines)

    if verifier.is_valid_sed_sp_ips():

        san_api = api_builder(sed_lines.get("san_type"), verifier.log)
        try:
            san_api.initialise(verifier.sed_sp_ips,
                               sed_lines.get("san_user"),
                               sed_lines.get("san_password"),
                               sed_lines.get("san_loginScope"),
                               esc_pwd=True)
        except SanApiException:
            verifier.log.error(
                "Cannot connect to the SAN. "
                "Check SAN SED parameters.")
            return

        verifier.process_sed_wwpns(sed_lines)

        if verifier.is_valid_sed_wwpns():
            verifier.log.debug("SED WWPNs: %s" % verifier.sed_wwpns)

            try:
                san_hba_list = san_api.get_hba_port_info()
            except SanApiException:
                verifier.log.error("Cannot retrieve HBAs from SAN")
                return

            for hba in san_hba_list:
                hbauid = hba.hbauid.lower()
                if hbauid not in verifier.san_wwpns:
                    verifier.san_wwpns.append(hbauid)
            verifier.log.info('Checking if WWPNs are visible on SAN')
            verifier.log.debug("SAN WWPNs: %s" % verifier.san_wwpns)

            non_visible_wwpns = verifier.compare_wwpns()
            if non_visible_wwpns > 0:
                verifier.log.error(str(non_visible_wwpns) +
                                   " WWPNs are not visible on the SAN")
            else:
                verifier.log.info('All WWPNs are visible on the SAN')


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
