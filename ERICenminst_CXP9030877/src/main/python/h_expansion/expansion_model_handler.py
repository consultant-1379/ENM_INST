"""
Module that handles interacting with the expansion model file
"""
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import os
import json
import logging

from expansion_utils import Blade
from expansion_settings import EXPANSION_MODEL_FILE

LOGGER = logging.getLogger("enminst")


class ExpansionModelHandler(object):
    """
    Class to manage the expansion model
    """
    def __init__(self):
        self.exp_model = self.read_expansion_model()

    @staticmethod
    def read_expansion_model():
        """
        Function that reads in the expansion model JSON file into a dictionary.
        :return: Dictionary containing expansion model.
        """
        if not os.path.exists(EXPANSION_MODEL_FILE):
            raise Exception('Expansion model {0} does not exist'
                            .format(EXPANSION_MODEL_FILE))

        with open(EXPANSION_MODEL_FILE, 'r') as model_file:
            try:
                model = json.load(model_file)
            except ValueError:
                raise Exception('Failed to read in the expansion model')

        return model

    def get_blades_in_model(self):
        """
        Function that gets all the blades in the expansion model file.
        :return: List of Blade objects.
        """
        blades = []

        # List comprehension is to only get peer nodes.
        for peer_node in [node for node in self.exp_model.keys()]:
            peer_node_info = self.exp_model.get(peer_node)

            blade = Blade()
            blade.sys_name = peer_node
            blade.hostname = peer_node_info.get('hostname')
            blade.serial_no = peer_node_info.get('serial')
            blade.src_ilo = peer_node_info.get('src_ilo')
            blade.dest_ilo = peer_node_info.get('dest_ilo')
            blade.src_bay = peer_node_info.get('src_bay')
            blade.dest_bay = peer_node_info.get('dest_bay')
            blade.ilo_user = peer_node_info.get('ilo_user')
            blade.ilo_pass_key = peer_node_info.get('key')
            blades.append(blade)

        if not blades:
            LOGGER.error('Failed to find any blades in expansion model')
            raise Exception('No blades found in expansion model')

        return blades

    def write_model_file(self):
        """
        Function that writes the expansion model to file.
        :return: None
        """
        try:
            with open(EXPANSION_MODEL_FILE, 'w') as json_file:
                json_file.write(json.dumps(self.exp_model, indent=4))
        except IOError:
            raise Exception('Failed to write expansion model to file')
