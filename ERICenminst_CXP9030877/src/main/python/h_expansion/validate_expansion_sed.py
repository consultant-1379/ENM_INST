"""
Module that validates the contents of the Expansion target SED.
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2020 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : validate_expansion_sed.py
# Purpose : Script that validates the expansion SED against the
# current deployment SED.
# ********************************************************************
import os
import json
import logging

from h_util.h_utils import ping, query_strong_yes_no
from expansion_settings import EXPANSION_MODEL_FILE
from expansion_utils import LitpHandler, ValidationException

LOGGER = logging.getLogger("enminst")


class ExpansionSedValidation(object):
    """
    Class to read and validate the SED
    """
    def __init__(self, target_sed):
        # target_sed is an instance of ExpansionSedHandler
        self.target_sed = target_sed

        self.litp_handler = LitpHandler()
        self.deployment_info = {}

    def validate_sed(self, blades_to_move):
        """
        Function that validates the SED information of the blades to move.
        :param blades_to_move: List of blades to move to second enclosure
        :return: None
        """
        # Check if model file exists
        if os.path.exists(EXPANSION_MODEL_FILE):
            LOGGER.warning('Expansion model file {0} already exists'
                           .format(EXPANSION_MODEL_FILE))
            if query_strong_yes_no("Do you want to delete the model file?"):
                try:
                    os.remove(EXPANSION_MODEL_FILE)
                except OSError:
                    LOGGER.error('Failed to remove expansion model file')
                    raise
            else:
                raise Exception('Cannot continue while expansion model '
                                'file exists.')

        LOGGER.info('Validating target SED information')

        LOGGER.info('Verifying blades to move information in the target SED '
                    'is correct')
        for blade in blades_to_move:
            if blade.src_ilo == blade.dest_ilo:
                continue

            LOGGER.info('Detected a change of ILO for {0}'
                        .format(blade.sys_name))

            # Get serial number from SED & Compare to serial number in obj
            sed_serial = \
                self.target_sed.get_peer_node_serial_number(blade.sys_name)

            if sed_serial != blade.serial_no:
                LOGGER.error('Serial number {0} for blade {1} does not match '
                             'the SED serial number {2}'
                             .format(blade.serial_no,
                                     blade.sys_name,
                                     sed_serial))
                raise ValidationException('Serial numbers do not match for '
                                          'node {0}'.format(blade.sys_name))

            LOGGER.info('Node {0} with serial {1} will move to the other '
                        'chassis'.format(blade.sys_name, blade.serial_no))

            # Ping test the new iLO IP (Shouldn't be reachable)
            if ping(blade.dest_ilo):
                LOGGER.error('New iLO IP {0} is already in use'
                             .format(blade.dest_ilo))
                raise ValidationException('IP already in use')

            # Check the IP isn't in SED already
            if self.target_sed.sed.values().count(blade.dest_ilo) > 1:
                LOGGER.error('Duplicate IP entry for IP {0}'
                             .format(blade.dest_ilo))
                raise ValidationException('Duplicate IP in SED')

            self.deployment_info[blade.sys_name] = {'hostname': blade.hostname,
                                                    'serial': blade.serial_no,
                                                    'src_ilo': blade.src_ilo,
                                                    'dest_ilo': blade.dest_ilo,
                                                    'src_bay': blade.src_bay,
                                                    'dest_bay': blade.dest_bay,
                                                    'ilo_user': blade.ilo_user,
                                                    'key': blade.ilo_pass_key}

    def write_model_file(self):
        """
        Function that writes the expansion JSON model to file.
        :return: None
        """
        LOGGER.info('Writing expansion model to file {0}'
                    .format(EXPANSION_MODEL_FILE))
        try:
            with open(EXPANSION_MODEL_FILE, 'w') as json_file:
                json_file.write(json.dumps(self.deployment_info, indent=4))
        except IOError:
            LOGGER.error('Failed to write expansion model to file',
                         exc_info=True)
            raise
