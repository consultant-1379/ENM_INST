#!/usr/bin/python
"""
Update LITP with SED changes that are valid according to a set of
in-code filter rules.  These rules allow for MAC and WWPN changes.
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2017 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : upgrade_enm_internal_model_only.py
# Purpose : Update LITP with SED changes for WWPN and MAC address
# Date    : 29-11_2017
# ********************************************************************

import logging
import socket
import sys

from re import match

from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpException
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import Sed

LOGGER = 'enminst'

# Regexes to get LITP path info from SED keys
C_LIST = ('asr', 'aut', 'db', 'ebs', 'esn', 'evt', 'scp', 'str', 'svc')
R_CLUSTERS = '(' + '|'.join(C_LIST) + ')'
R_NODE = r'_node(\d{1,3})'

# WWPN Rule
WWPN_FILTER = R_CLUSTERS + R_NODE + '_WWPN(1|2)'
WWPN_PATH = '/infrastructure/systems/{0}-{1}_system/controllers/hba{2}'

# MAC Rule
MAC_FILTER = R_CLUSTERS + R_NODE + r'_eth(\d{1,3})_macaddress'
MAC_PATH = '/deployments/enm/clusters/{0}_cluster/nodes/' \
           '{0}-{1}/network_interfaces/eth{2}'


class SedLitpMappingRule(object):  # pylint: disable=R0903
    ''' Defines a SED regex filter and a corresponding path_map
        entry to convert a SED entry into a LITP path.  It also
        stores the associated LITP property name. '''

    def __init__(self, r_filter, path_map, prop_name, ignore_case=False):
        self.log = logging.getLogger(LOGGER)
        self.sed_filter = r_filter
        self.path_map = path_map
        self.prop_name = prop_name
        self.no_case = ignore_case
        self.log.debug('Created mapping rule: %s', self)

    def __str__(self):
        return 'SED:{0}, path:{1}, property:{2}, ic:{3}'.format(
            self.sed_filter,
            self.path_map,
            self.prop_name,
            self.no_case)

    def get_litp_path(self, key):
        '''
        Function Description:
        Determine LITP path from SED parameter
        :param  key: The SED parameter name
        :type - string
        :return: The LITP path as a string
        '''

        match_obj = match(self.sed_filter, key)
        if not match_obj:
            self.log.error('Unable to determine path from %s', key)
            raise ValueError()

        matches = match_obj.groups()
        path = self.path_map.format(*matches)   # pylint:  disable=W0142
        self.log.debug('SED key %s, LITP path: %s Property: %s',
                       key, path, self.prop_name)
        return path


class LitpPropertyItem(object):  # pylint: disable=R0903

    ''' This holds a SED property name, and the corresponding LITP path
        and property.  In addition it has a state attribute to indicate
        if LITP has been updated with its information, and a rollback
        value which stores the original LITP property value.
        '''
    STATE_UNKNOWN = 'UNKNOWN'
    STATE_IDENTICAL = 'IDENTICAL'
    STATE_FOR_UPDATE = 'FOR_UPDATE'
    STATE_UPDATED = 'UPDATED'

    def __init__(self, sed_key, path, prop_name,  # pylint: disable=R0913
                 value, ignore_case=False):
        self.sed_key = sed_key
        self.path = path
        self.prop_name = prop_name
        self.value = value
        self.rollback = None
        self.status = LitpPropertyItem.STATE_UNKNOWN
        self.no_case = ignore_case

    def __str__(self):
        return '{0}:{1}@{2}={3} State={4}'.format(
            self.sed_key,
            self.prop_name,
            self.path,
            self.value,
            self.status)

    def equals(self, value):
        '''
        Function Description:
        Compares the value attribute with the passed value
        parameter.  Case may be ignoreded depending on the
        value of the no_case attribute.
        :param  value: The value to compare
        :type - string
        :return: Boolean
        '''

        if self.no_case:
            return self.value.lower() == value.lower()
        return self.value == value


class LitpUpdater(object):
    ''' Class to manage loading of SED, checking values against LITP
        and updating LITP for valid SED items whose values have changed
    '''
    def __init__(self, sed_path, filter_rules):
        self.log = logging.getLogger(LOGGER)
        self.litp = LitpRestClient()

        try:
            sed = Sed(sed_path)
        except IOError as ioe:
            self.log.exception('Failed to read SED: %s', sed_path)
            raise SystemExit(ioe)

        self.log.debug('SED %s read successfully', sed_path)
        sed_dict = sed.sed
        self.items = self._sed_to_litp_items(sed_dict, filter_rules)
        self.rollback = []

    def _sed_to_litp_items(self, sed_dict, filter_rules):
        '''
        Method Description:
        Converts SED dictionary into list of LitpPropertyItem, using
        a list of SedLitpMappingRule to determine valid SED items and
        use the mappings to convert the SED information into a LITP
        path and property information.
        :param sed_dict: Dictionary of SED key/values.
        :type - Dictionary
        :param filter_rules: Rules to convert SED entries to LITP items
        :type - List of SedLitpMappingRule
        :return: List of LitpPropertyItem
        '''
        litp_items = []
        for rule in filter_rules:
            self.log.debug('Parsing SED with rule: %s', rule.sed_filter)
            for key in sed_dict:
                if match(rule.sed_filter, key):
                    path = rule.get_litp_path(key)
                    name = rule.prop_name
                    val = sed_dict[key]
                    item = LitpPropertyItem(key, path, name, val, rule.no_case)
                    litp_items.append(item)
                    self.log.debug('LITP item from SED: %s', item)
        self.log.debug('SED Parsed successfully')
        return litp_items

    def get_items_by_states(self, states):
        '''
        Method Description:
        Returns a list of items built from the SED whose state
        corresponds to the state list passed as an argument.
        :param states: list of states.
        :type - List of strings.
        :return: List of LitpPropertyItem
        '''

        return [i for i in self.items if i.status in states]

    def list_rollback_cmds(self):
        '''
        Method Description:
        Logs a list of LITP commands to roll back any LITP updates
        made by this class.
        :param  None
        :type - N/A
        :return: Nothing
        '''
        if self.rollback:
            self.log.info('LITP Updates can be rolled back with:')
            for item in self.rollback:
                self.log.info(item)

    def check_litp_for_updates(self):
        '''
        Method Description:
        Retrieves information from LITP to determine which items from
        the SED should be used to update the LITP model.
        :param  None
        :type - N/A
        :return: Nothing
        '''
        for item in self.items:
            try:
                self.log.debug('Checking for property %s at %s',
                               item.prop_name, item.path)
                res = self.litp.get(item.path)
                litp_value = res['properties'][item.prop_name]

                if item.equals(litp_value):
                    item.status = LitpPropertyItem.STATE_IDENTICAL
                    self.log.debug('No change for item %s', item)
                else:
                    item.status = LitpPropertyItem.STATE_FOR_UPDATE
                    self.log.info('Update from %s required for %s',
                                  litp_value, item)
                item.rollback = litp_value
            except (socket.error, LitpException, KeyError) as exc:
                self.log.exception('Error checking LITP item: %s : %s',
                                   item, exc)
                raise

    def update_litp_items(self, items=None):
        '''
        Method Description:
        Updates the LITP model using the list of updated items.
        :param  None
        :type - N/A
        :return: Nothing
        '''
        if not items:
            items = self.get_items_by_states(LitpPropertyItem.STATE_FOR_UPDATE)

        for item in items:
            try:
                self.log.info('Updating LITP with: %s', item)
                update = {item.prop_name: item.value}
                self.litp.update(item.path, update)

                self.rollback.append('litp update -p {0} -o {1}={2}'.format(
                    item.path, item.prop_name, item.rollback))

                item.status = LitpPropertyItem.STATE_UPDATED
            except (socket.error, LitpException) as exc:
                self.log.exception('Failed to update item: %s : %s', item, exc)
                self.list_rollback_cmds()
                raise


def update_litp(args):
    '''
    Function Description:
    Uses this script's classes to read the SED whose path is
    passed as an arg, retrieve valid SED changes, and update
    LITP with them.
    :param  args: Argument list script is called with
    :type - list of strings
    :return: Nothing
    '''
    try:
        script_name = args[0]
        sed_path = args[1]
    except IndexError:
        print 'Usage:  {0} <path to SED>'.format(script_name)
        raise SystemExit(1)

    log = init_enminst_logging()
    log.info('Script started: %s', ' '.join(args))

    # SED Filters
    wwpn_rule = SedLitpMappingRule(
        WWPN_FILTER, WWPN_PATH, 'hba_porta_wwn', ignore_case=True)

    mac_rule = SedLitpMappingRule(
        MAC_FILTER, MAC_PATH, 'macaddress', ignore_case=True)

    # Instantiate LitpUpdater to Filter SED based on SED/LITP mapping rules
    rules = (wwpn_rule, mac_rule)

    try:
        updater = LitpUpdater(sed_path, rules)
    except ValueError:
        log.error('Failed to parse SED.  Exiting')
        raise SystemExit(1)

    # Check LITP to see what items need updating
    log.info('Checking LITP model for required updates')
    updater.check_litp_for_updates()

    items = updater.get_items_by_states(LitpPropertyItem.STATE_FOR_UPDATE)
    if not items:
        log.info('No items require updating.  Exiting')
        raise SystemExit(0)

    # Update relevant items in LITP
    log.info('Updating LITP')
    updater.update_litp_items(items=items)
    log.info('LITP updated successfully')
    updater.list_rollback_cmds()
    log.info("Script %s completed successfully", script_name)
    raise SystemExit(0)

if __name__ == '__main__':
    main_exceptions(update_litp, sys.argv)
