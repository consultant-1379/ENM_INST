#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
This module is the main module for the SED expansion script.
"""

import sys
import os
import time
import re
import expansion_sed_constants
from expansion_logger import setup_logger
from shutil import copy

####################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
####################################################################


class ExpansionSed(object):
    """
    Class to swap parameters for certain service groups in a SED text file
    before performing an expansion.
    """

    def __init__(self, sed_file, logger):
        """
        params:
            sed_file: Path to the SED file to swap parameters
            logger: Logger object to log info
        """
        self.sed_file = sed_file
        self._sed_data = {}
        self.log = logger
        self.sed_backup_file = ""
        self.workaround_service_list = expansion_sed_constants. \
            WORKAROUND_SERVICE_LIST_IPV4.copy()

    def _get_sed_data(self):
        """
        Get name/value pairs from SED file

        Returns:
               none
        Throws:
               IOError
        """
        self.log.debug("Entering function {0}:_get_sed_data"
                       .format(self.__class__.__name__))

        if not self._sed_data:
            with open(self.sed_file, 'r') as sed_fh:
                for line in sed_fh:
                    line = line.rstrip()
                    match = re.search(r'^\s*(\w+)\s*=(.*)', line)
                    # pudb.set_trace()
                    if match:
                        self._sed_data[match.group(1)] = \
                            (match.group(2)).strip("' \"")

        self.log.debug("Exiting function {0}:_get_sed_data"
                       .format(self.__class__.__name__))

    def _update_params_if_ipv6(self):
        """
        Update params to check if IP v6

        :return: None
        """

        if self._sed_data.get("ENMservices_IPv6subnet"):
            self.workaround_service_list.update(
                (k, self.workaround_service_list[k] + v) for k, v in \
                expansion_sed_constants.WORKAROUND_SERVICE_EXTRAS_IPV6.items())

    def _confirm_sed_data(self):
        """
        Checks if the service groups and parameters listed in their respective
        lists are included within the SED.
        Throws exceptions is values are missing.

        :param: None
        :return: None
        :throw: ValueError
        """
        halt_flag_parameter = False
        halt_flag_value = False

        self.log.debug("Entering function {0}:_confirm_sed_data"
                       .format(self.__class__.__name__))

        self.log.info("Validating required SED data.")

        sed_data_keys = self._sed_data.keys()

        for service in self.workaround_service_list.iterkeys():
            for parameter_name in self.workaround_service_list[service]:
                for i in xrange(1, 3):
                    param_name = "{0}_{1}_{2}".format(service,
                                                      i,
                                                      parameter_name)

                    self.log.debug("Checking parameter {0}".format(param_name))

                    if param_name not in sed_data_keys:
                        self.log.error("Parameter " + param_name + " is not "
                                       + "found in the SED file. Please "
                                       + "correct this issue and try again")
                        halt_flag_parameter = True

                    elif self._sed_data[param_name] == "":
                        self.log.error(param_name + " contains an empty"
                                       + " value. "
                                       + "Please correct "
                                       + "this parameter "
                                       + "and try again.")
                        halt_flag_value = True

        if halt_flag_parameter is True and halt_flag_value is True:
            raise ValueError("Missing parameters and values in SED")
        elif halt_flag_parameter is True:
            raise ValueError("Missing parameters in SED")
        elif halt_flag_value is True:
            raise ValueError("Missing values in SED")

        self.log.debug("Exiting function {0}:_confirm_sed_data"
                       .format(self.__class__.__name__))

    def swap_parameter_values(self):
        """
        Swaps the parameter values between the first and second instances of
        the services outlined in WORKAROUND_SERVICE_LIST

        :param: None
        :return: None
        :throw: ValueError
        """

        self.log.debug("Entering function {0}:swap_parameter_values"
                       .format(self.__class__.__name__))

        self._get_sed_data()
        self._update_params_if_ipv6()
        self._confirm_sed_data()

        self.log.info("Configuring SED parameters.")

        for service in self.workaround_service_list:
            for parameter_name in self.workaround_service_list[service]:
                instance_one = "{0}_1_{1}".format(service, parameter_name)
                instance_two = "{0}_2_{1}".format(service, parameter_name)

                self.log.debug("Altering parameter " + instance_one +\
                               " from {0} to {1}"\
                               .format(self._sed_data[instance_one],\
                                       self._sed_data[instance_two]))

                self.log.debug("Altering parameter " + instance_two +\
                               " from {0} to {1}"\
                               .format(self._sed_data[instance_two],\
                                       self._sed_data[instance_one]))

                temp_value = self._sed_data[instance_one]
                self._sed_data[instance_one] = self._sed_data[instance_two]
                self._sed_data[instance_two] = temp_value

        self.log.debug("Exiting function {0}:swap_parameter_values"
                       .format(self.__class__.__name__))

    def update_sed(self):
        """
        Update SED values corresponding to passed param/value dictionary

        :param: param_data - dictionary containing parameters to update
        :return: None
        :throw: None
        """
        self.log.debug("Entering function {0}:update_sed"
                       .format(self.__class__.__name__))

        # Create a backup of the SED text file.
        self.log.info("The existing SED text file '{0}' will be updated:\n"
                      .format(self.sed_file))
        param_data = self._sed_data

        # Copy each line in the backup SED file into the SED text file.
        # If the parameter in a line matches a parameter in param_data
        # Update the value of the parameter in that line and save the line to
        # the SED text file. Copy all other lines unchanged
        with open(self.sed_backup_file, 'r') as backup_fh:
            with open(self.sed_file, 'w') as upd_sed_fh:
                for line in backup_fh:
                    match = re.search(r'^\s*(\w+)\s*=(.*)', line.rstrip())
                    if match:
                        curr_param_name = match.group(1)
                        curr_param_value = (match.group(2)).strip("' \"")
                        if curr_param_name in param_data and \
                                    curr_param_value != param_data[
                                    curr_param_name]:
                            new_value = param_data[curr_param_name]
                            self.log.info("Updating SED Parameter {0} from "
                                          "\"{1}\" to \"{2}\""
                                          .format(curr_param_name,
                                                  curr_param_value,
                                                  new_value))
                            upd_sed_fh.write("{0}={1}\n"
                                             .format(curr_param_name,
                                                     new_value))
                        else:
                            if curr_param_name in param_data:
                                self.log.debug("SED Parameter {0} is left "
                                               "unchanged."
                                               .format(curr_param_name))
                            upd_sed_fh.write(line)
                    else:
                        # Also write unmatched lines
                        upd_sed_fh.write(line)

        self.log.debug("Exiting function {0}:update_sed"
                       .format(self.__class__.__name__))

    def create_backup_sed(self):
        """
        Creates a backup of the SED passed to this script.

        :param: param_data - dictionary containing parameters to update
        :return: None
        :throw: None
        """
        self.log.debug("Entering function {0}:create_backup_sed"
                       .format(self.__class__.__name__))

        config_file_dir = os.path.abspath(os.path.dirname(self.sed_file))

        self.sed_backup_file = config_file_dir + \
                               '/expansion_sed_backup_' + \
                               time.strftime("%Y%m%d_%H%M%S") + '.txt'
        copy(self.sed_file, self.sed_backup_file)

        self.log.info("Created backup SED text file {0}"
                      .format(self.sed_backup_file))

        self.log.debug("Exiting function {0}:create_backup_sed"
                       .format(self.__class__.__name__))


def main():
    """
    Main function for the SED Expansion script.
    """

    log = setup_logger()

    if len(sys.argv) < 2:
        log.error("Missing filename for SED file, exiting.")
        exit(3)
    try:
        expansion_writer = ExpansionSed(sys.argv[1], log)
        expansion_writer.create_backup_sed()
        expansion_writer.swap_parameter_values()
        expansion_writer.update_sed()
    except ValueError:
        log.error("Cannot continue with the script. " + \
                                   "Please check the errors above " + \
                                   "and try again.")
        exit(2)
    except IndexError:
        log.error("Issues occurred while processing SED parameters.")
        exit(1)

if __name__ == '__main__':
    main()
