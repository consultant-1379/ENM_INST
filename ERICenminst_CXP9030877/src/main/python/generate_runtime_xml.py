"""
This script take a SED file and Deployment Description template and generates
a runtime xml using the substituteParams.sh script.
This script takes encrypted idenmgt passwords from the LITP model to pass into
substituteParams.sh.
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2024 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : generate_runtime_xml.py
# Purpose : The purpose of this wrapper script is to generate a
# runtime xml using a provided Site Engineering Data file and
# Deployment Description template.
# ********************************************************************

from argparse import ArgumentParser
from h_litp.litp_utils import main_exceptions
from encrypt_passwords import EncryptPassword, \
                              PROPERTY_TO_TEMPFILE_NAME_DICTIONARY
from h_util.h_utils import exec_process_via_pipes
from h_logging.enminst_logger import init_enminst_logging
from shutil import copy

import sys
import os

TEMP_SED_PATH = "/software/sed_backup.cfg"
PROPERTY_FILE_PATH = "/opt/ericsson/enminst/runtime/enminst_working.cfg"
ENMINST_LOG = init_enminst_logging()


class GenerateXml(object):
    """
    A program that takes a SED file and deployment description template and
    generates a runtime xml by calling the substituteParams.sh script. This
    script will take values from a property file and read a known list of
    encrypted passwords from the LITP Model and append them to the sed file.
    """
    def __init__(self, xml_template, sed, verbose):
        """Initialize instance
        :param xml_template: Deployment Description template filepath
        :type xml_template: String
        :param sed: SED filepath
        :type sed: String
        :param verbose: if verbose logging mode is required
        :type verbose: Boolean
        """

        self.verbose = verbose
        if os.path.isfile(sed):
            self.sed_path = sed
        else:
            raise IOError('File {0} not found.' \
                           .format(sed))
        if os.path.isfile(xml_template):
            self.xml_template_path = xml_template
        else:
            raise IOError('File {0} not found.' \
                           .format(xml_template))
        if not os.path.isfile(PROPERTY_FILE_PATH):
            raise IOError('File {0} not found.' \
                           .format(PROPERTY_FILE_PATH))
        self.encrypt_password = EncryptPassword(self.sed_path,
                                                None, None, None)

    def create_temp_sed_file(self):
        """
        Create a temporary SED file to pass into substituteParams.sh
        """
        self.encrypt_password.read_values()
        ENMINST_LOG.info(
            "Creating temprary SED file {0}".format(TEMP_SED_PATH))
        copy(self.sed_path, TEMP_SED_PATH)
        with open(TEMP_SED_PATH, 'a') as temp_sed:
            for key in self.encrypt_password.password_value_dict:
                property_name = PROPERTY_TO_TEMPFILE_NAME_DICTIONARY[key]
                encrypted_password = \
                    self.encrypt_password.password_value_dict[key]
                line = property_name + "=" + encrypted_password + "\n"
                temp_sed.write(line)

    def execute_substitute_params(self):
        """
        Execute the substituteParams.sh script with temporary SED.
        """
        cmd = "/opt/ericsson/enminst/bin/substituteParams.sh " \
                "--xml_template {0} " \
                "--sed {1} " \
                "--propertyfile {2}".format(self.xml_template_path,
                                            TEMP_SED_PATH,
                                            PROPERTY_FILE_PATH)
        if self.verbose:
            cmd += " -v"
        ENMINST_LOG.info("Executing {0}".format(cmd))
        output = exec_process_via_pipes(cmd.split())
        ENMINST_LOG.info(output)


def remove_temp_sed_file():
    """
    Remove the temporary SED generated for substituteParams.sh
    """
    if os.path.isfile(TEMP_SED_PATH):
        os.remove(TEMP_SED_PATH)
        ENMINST_LOG.info("The file {0} has been deleted." \
                        .format(TEMP_SED_PATH))
    else:
        ENMINST_LOG.info("The file {0} does not exist." \
                        .format(TEMP_SED_PATH))


def generate_xml_sub_params(parsed_args):
    """
    Generate a temporary SED populated with encrypted passwords read from the
    LITP model and run substituteParams.sh to generate a Deployment
    Description xml.
    :param parsed_args: configuration of inputs
    :type parsed_args: ArgumentParser
    """
    try:
        substitute_params = GenerateXml(parsed_args.xml_template,
                                        parsed_args.sed_file,
                                        parsed_args.verbose)
        substitute_params.create_temp_sed_file()
        substitute_params.execute_substitute_params()
    except IOError as ex:
        ENMINST_LOG.error(ex)
        exit(1)
    finally:
        remove_temp_sed_file()


def create_parser():
    """Create and configure command line parser instance
    :return: parser instance
    :rtype: ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        default=False, help="Enable all debugging output")
    parser.add_argument('--xml_template',
                        required=True,
                        help='Path to Deployment Model XML file')
    parser.add_argument('--sed', dest="sed_file",
                        required=True, help='Path to Site Engineering file')
    return parser


def main(args):
    """
    Main function parsing command arguments and running substitution
    :param args:command line arguments
    :type args: List
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args[1:])
    generate_xml_sub_params(parsed_args)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
