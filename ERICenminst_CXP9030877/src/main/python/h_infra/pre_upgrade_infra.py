"""
Take a deployment XML and extract any changes that need to be applied before
upgrade snapshots can be taken.
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************
#
# ********************************************************************
# Name    : pre_upgrade_infra.py
# Purpose : Take a deployment XML and extract any changes that need to
# be applied before upgrade snapshots can be taken.
# ********************************************************************
import httplib
import logging

from h_litp.litp_rest_client import LitpRestClient, LitpException
from h_xml.xml_utils import load_xml, xpath, get_xml_element_properties

ITEM_TYPE_FILE_SYSTEM = 'file-system'
ITEM_TYPE_SFS_FILESYSTEM = 'sfs-filesystem'
ITEM_TYPE_SFS_EXPORT = 'sfs-export'
ITEM_TYPE_LUN_DISK = 'lun-disk'

CHANGE_TYPES = [ITEM_TYPE_FILE_SYSTEM,
                ITEM_TYPE_SFS_FILESYSTEM,
                ITEM_TYPE_SFS_EXPORT,
                ITEM_TYPE_LUN_DISK]


CHANGE_TYPE_PROPERTIES = {
    ITEM_TYPE_FILE_SYSTEM: {'size': 'config', 'snap_size': 'non-config'},
    ITEM_TYPE_SFS_FILESYSTEM: {'size': 'config'},
    ITEM_TYPE_SFS_EXPORT: {},
    ITEM_TYPE_LUN_DISK: {'size': 'config'}}


class ParentIdIterator(object):  # pylint: disable=too-few-public-methods
    """
    Iterator to traverse an Element parent tree
    """

    def __init__(self, node):
        self._node = node

    def next(self):
        """
        Get the next element in a list and return it.
        :return:
        """
        if self._node is None:
            raise StopIteration()
        self._node = self._node.getparent()
        if self._node is None:
            raise StopIteration()
        return self._node


def _get_parent_path(xmlnode):
    """
    Get the model path for the current XML element

    :param xmlnode: The XML element to get the parent model path for
    :returns: The parent path in the deployment model
    :rtype: str
    """
    parent_iter = ParentIdIterator(xmlnode)
    ids = []
    while True:
        try:
            ids.append(parent_iter.next().get('id'))
        except StopIteration:
            break
    return '/{0}'.format('/'.join(ids[::-1][1:]))


def get_model_path(xmlnode):
    """
    Get the LITP model path for an XML element

    :param xmlnode: The XML node to get the model path for
    :type xmlnode: Element
    :returns: The LITP model path of the XML element
    :rtype: str
    """
    return '{0}/{1}'.format(_get_parent_path(xmlnode), xmlnode.get('id'))


def get_modprops(properties, split_props):
    """
    Split a dictionary

    :param properties: The dict to split
    :type properties: dict
    :param split_props: The keys to split out
    :type split_props: list
    :returns: ``properties`` subset with keys from ``split_props``
    :rtype: dict
    """
    return dict([(i, properties[i]) for i in split_props if i in properties])


def update_item(x_props, m_props, model_path, item_state, cfg_type):
    """
    The LITP command to update an item properties

    :param x_props: The XML item properties
    :type x_props: dict
    :param m_props: The model item properties
    :type m_props: dict
    :param model_path: The LITP model path of the XML element
    :type model_path: str
    :param item_state: Item state in the model
    :type item_state: str
    :type cfg_type: dict
    :return: The litp command
    :rtype: str
    """
    change_list = []
    command = ''
    exec_plan = False
    for xname, xvalue in x_props.items():
        if xname in m_props:
            if m_props[xname] != xvalue or \
                            item_state != LitpRestClient.ITEM_STATE_APPLIED:
                if cfg_type[xname] == 'config':
                    exec_plan = True
                change_list.append('{0}={1}'.format(xname, xvalue))
        if change_list:
            command = 'litp update -p {0} -o {1}'.format(
                    model_path, ' '.join(change_list))
    return command, exec_plan


def create_item(xmlnode, change_type, model_path):
    """
    The LITP command to create a new item

    :param xmlnode: The XML node to get the model path for
    :type xmlnode: Element
    :param change_type: The item type
    :type change_type: str
    :param model_path: The LITP model path of the XML element
    :type model_path: str
    :return: The litp command
    :rtype: str
    """
    change_list = []
    command = ''
    exec_plan = False
    for xname, xvalue in get_xml_element_properties(xmlnode).items():
        change_list.append('{0}={1}'.format(xname, xvalue))
    if change_list:
        command = 'litp create -t {0} -p {1} -o {2}'.format(
                change_type, model_path, ' '.join(change_list))
        exec_plan = True
    return command, exec_plan


def pre_snap_changes(xml_dd):
    """
    Parse a deployment XML file for certain item-types and check
    if they've been updated i.e. the LITP model has a different value,
    or they're new in the LITP model.

    :param xml_dd: Path to the XML deployment description to parse
    :type xml_dd: str
    :return: The list of LITP commands
    :rtype: list
    """
    # pylint: disable=R0914
    logger = logging.getLogger('enminst')
    root = load_xml(xml_dd).getroot()
    litp = LitpRestClient()
    comm_list = []
    logger.info('Parse the runtime xml file')
    plan_required = False
    for change_type in CHANGE_TYPES:
        for node in xpath(root, change_type):
            command = ''
            x_props = get_modprops(get_xml_element_properties(node),
                                   CHANGE_TYPE_PROPERTIES[change_type])
            model_path = get_model_path(node)
            try:
                model_object = litp.get(model_path, log=False)
                m_props = get_modprops(model_object['properties'],
                                       CHANGE_TYPE_PROPERTIES[change_type])
                command, exec_plan = update_item(
                    x_props, m_props, model_path,
                    model_object.get('state'),
                    CHANGE_TYPE_PROPERTIES[change_type])
                plan_required |= exec_plan
            except LitpException as error:
                if error.args[0] == httplib.NOT_FOUND:
                    parent_path = _get_parent_path(node)
                    # exclude new service group but not sfs-export
                    is_export = change_type == ITEM_TYPE_SFS_EXPORT
                    if litp.exists(parent_path) or is_export:
                        command, exec_plan = create_item(node,
                            change_type, model_path)
                        plan_required |= exec_plan
                else:
                    raise
            if command:
                comm_list.append(command)
    logger.info('Runtime xml file parsed successfully')
    return comm_list, plan_required
