"""
From a deployment XML extract any changes that need to be applied before
the RHEL7 upgrade rollover nodes plan.
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2021
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
#
# ********************************************************************
# Name    : rh7_pre_upgrade.py
# Purpose : Take a deployment XML and extract any changes that need to be
# applied before RHEL7 rollover node plan is to be run.
# ********************************************************************
import logging
import httplib

from h_litp.litp_rest_client import LitpRestClient, LitpException
from h_xml.xml_utils import load_xml, xpath, get_xml_element_properties
from h_infra.pre_upgrade_infra import get_model_path, get_modprops, \
                                  _get_parent_path, update_item, create_item

ITEM_TYPE_HA_SERVICE_CONFIG = 'ha-service-config'
ITEM_TYPE_VCS_CLUSTER = 'vcs-cluster'
ITEM_TYPE_VCS_CLUSTERED_SERVICE = 'vcs-clustered-service'
ITEM_TYPE_VIP = 'vip'

PRE_ROLLOVER_TYPE_PROPERTIES = {
            ITEM_TYPE_VCS_CLUSTER: ['app_agent_num_threads'],
            ITEM_TYPE_VCS_CLUSTERED_SERVICE: ['offline_timeout',
                                              'online_timeout',
                                              'node_list',
                                              'active',
                                              'standby',
                                              'dependency_list'],
            ITEM_TYPE_HA_SERVICE_CONFIG: ['status_interval',
                                          'status_timeout',
                                          'restart_limit',
                                          'startup_retry_limit',
                                          'fault_on_monitor_timeouts',
                                          'tolerance_limit',
                                          'clean_timeout'],
            ITEM_TYPE_VIP: ['ipaddress',
                            'network_name']
                               }
PRE_ROLLOVER_CREATE_TYPES = [ITEM_TYPE_HA_SERVICE_CONFIG,
                             ITEM_TYPE_VIP]


def _remove_unchanged_node_list(x_props, m_props):
    """
    Detect order of node_list changes
    :param x_props: deployment description xml property
    :type x_props: dict
    :param m_props: litp model property
    :type m_props: dict
    """

    if 'node_list' in x_props and 'node_list' in m_props:
        if set(x_props['node_list'].split(',')) == set(
            m_props['node_list'].split(',')):
            del x_props['node_list']
            del m_props['node_list']


def pre_rollover_changes(xml_dd):
    """
    From a deployment XML extract any changes that need to be applied before
    the RHEL7 upgrade rollover nodes plan.
    This is similar to and re-uses a number of methods from
    h_infra/pre_upgrade_infra.py
    :param xml_dd: deployment description xml doc
    :type xml_dd: string
    :return: litp commands to make the required changes
    :rtype: list
    """
    # pylint: disable=R0914

    logger = logging.getLogger('enminst')
    root = load_xml(xml_dd).getroot()
    litp = LitpRestClient()
    comm_list = []
    logger.debug('Parsing the runtime xml file')
    for change_type in PRE_ROLLOVER_TYPE_PROPERTIES:
        for node in xpath(root, change_type):
            command = ''
            x_props = get_modprops(get_xml_element_properties(node),
                                   PRE_ROLLOVER_TYPE_PROPERTIES[change_type])
            model_path = get_model_path(node)
            try:
                model_object = litp.get(model_path, log=False)
                m_props = get_modprops(
                              model_object['properties'],
                              PRE_ROLLOVER_TYPE_PROPERTIES[change_type])
                _remove_unchanged_node_list(x_props, m_props)
                cfg_type = dict((c, 'config') for c in
                                PRE_ROLLOVER_TYPE_PROPERTIES[change_type])
                command, _ = update_item(x_props, m_props, model_path,
                                         model_object.get('state'), cfg_type)
            except LitpException as error:
                if error.args[0] == httplib.NOT_FOUND:
                    parent_path = _get_parent_path(node)
                    if (litp.exists(parent_path) and
                            change_type in PRE_ROLLOVER_CREATE_TYPES):
                        command, _ = create_item(node, change_type, model_path)
                else:
                    raise
            if command:
                comm_list.append(command)
    logger.debug('Runtime xml file successfully parsed')
    return comm_list
