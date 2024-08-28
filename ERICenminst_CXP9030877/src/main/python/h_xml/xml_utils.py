"""
Functions for various XML actions
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from os.path import exists
from os.path import basename
from lxml import etree
from lxml.etree import SubElement

_NAMESPACES = {
    'litp': 'http://www.ericsson.com/litp'
}
_LITPNS = '{http://www.ericsson.com/litp}'


def xpath(xml_node, element_type, attributes=None, namespace=True):
    """
    xpath query function

    :param xml_node: The start node for the query
    :type xml_node: Element
    :param element_type: The element type to search for
    :type element_type: str
    :param attributes: Optional attributes to file on
    :type attributes: dict
    :param namespace: The XML search tag is a prefixed tag.
    :returns: List of found elements
    :rtype: list
    """
    if namespace:
        xpath_string = './/litp:{0}'.format(element_type)
    else:
        xpath_string = './/{0}'.format(element_type)
    if attributes:
        for att_name, att_value in attributes.items():
            xpath_string += '[@{0}="{1}"]'.format(att_name, att_value)
    return xml_node.xpath(xpath_string, namespaces=_NAMESPACES)


def load_xml(input_file):
    """
    Load an xml file.
    :param input_file: The file to load
    :type input_file: str
    :returns: Object loaded with source elements from ``input_file``
    :rtype: etree.ElementTree
    """
    if not exists(input_file):
        raise IOError('File {0} not found!'.format(input_file))
    parser = etree.XMLParser(remove_comments=False)
    return etree.parse(input_file, parser=parser)


def write_xml(xml_node, output_file):
    """
    Write XML to file
    :param xml_node: The root node to write
    :type xml_node: etree.ElementTree
    :param output_file: The file to write the XML to.
    :type output_file: str
    """
    with open(output_file, 'w') as _writer:
        _writer.write(etree.tostring(xml_node, pretty_print=True,
                                     xml_declaration=True, encoding="utf-8"))


def get_parent(xml_node, parent_type):
    """
    get_parent function

    :param xml_node: The inherited path for a service
    :type xml_node: Element
    :param parent_type: The parent type to search for
    :type parent_type: str
    :returns: List of found elements
    :rtype: Element
    """
    tmp = xml_node
    while True:
        if tmp is not None:
            if tmp.tag == '{0}{1}'.format(_LITPNS, parent_type):
                break
            else:
                tmp = tmp.getparent()
        else:
            break
    return tmp


def get_xml_element_properties(element):
    """
    Convert elements to properties

    :param element: The parent XML node
    :returns: Child elements converted to a ``dict()``
    :rtype: dict
    """
    properties = {}
    for child in element.getchildren():
        if not is_ns_tag(child.tag):
            properties[child.tag] = child.text.strip()
    return properties


def is_ns_tag(tag):
    """
    Check if an element is a namespace tagged element

    :param tag: The element tag to check
    :type tag: str
    :returns: ``True`` ifa namespace element, ``False`` otherwise
    :rtype: bool
    """
    if tag is not etree.Comment:
        return tag.startswith(_LITPNS)
    return False


def add_infra_route(routes, route_name, gateway):
    """
    Add a route element to the parent ``routes`` element

    :param routes: Parent 'routes' element
    :type routes: etree.Element
    :param route_name: The item 'id'
    :type route_name: str
    :param gateway: The gateway IPv4 address
    :type gateway: IPAddress

    """
    route = SubElement(routes, _LITPNS + 'route',
                       attrib={'id': route_name})
    e_gateway = SubElement(route, 'gateway')
    e_gateway.text = str(gateway)
    e_subnet = SubElement(route, 'subnet')
    e_subnet.text = '0.0.0.0/0'


def inherit_infra_route(xml, source_path, node_id):
    """
    Add a route inherit element to the nodes routes

    :param xml: The XML to query to get the node to link the route to
    :type xml: etree.Element
    :param source_path: The infrastructue path of the 'route'
    :type source_path: str
    :param node_id: The node_id to link the route to
    :type node_id: str

    """
    nodes = xpath(xml, 'node', attributes={'id': node_id})
    if not nodes:
        raise KeyError('Could not find a node with '
                       'id \'{id}\''.format(id=node_id))
    e_route = xpath(nodes[0], 'node-routes-collection',
                    attributes={'id': 'routes'})[0]
    SubElement(e_route, _LITPNS + 'route-inherit',
               attrib={'id': basename(source_path),
                       'source_path': source_path})


def unity_model_updates(enm_xml):  # pylint: disable=too-many-branches
    """
    Check if the SAN array type is unity.  If so, update
    the model to:
    1) Remove 2nd SAN IP address as Unity only has one
    2) Remove the Raid Group entry from the model as Unity
       does not use Raid Groups
    3) Update the Fencing LUNs to use the Storage Pool

    :param enm_xml: path to the deployment description xml
    :type routes: str
    :returns: False if no updates needed, True if updates OK
    :rtype: Boolean
    :raises: Various exceptions on failure
    """
    enm_etree = load_xml(enm_xml)

    # If SAN not defined in model then return as there is
    # nothing to do
    try:
        san = xpath(enm_etree, 'san-emc')[0]
        san_props = get_xml_element_properties(san)
    except IndexError:
        return False

    san = xpath(enm_etree, 'san-emc')[0]
    san_props = get_xml_element_properties(san)

    # If SAN type is not unity then we do not
    # need any model changes
    if san_props['san_type'].lower() != 'unity':
        return False

    # Unity only has a single IP address so remove ip_b
    for child in san.getchildren():
        if child.tag == 'ip_b':
            # TODO, future story to remove   # pylint: disable=fixme
            # IP B, but a lot of refactoring needed, so for now
            # set to a dummy address
            # child.getparent().remove(child)
            child.text = '127.0.0.1'

    # Get Raid Group & Storage Pool names and remove Raid Group from the model
    raid_group_name = None
    storage_pool_name = None
    for container in xpath(enm_etree, 'storage-container'):
        container_prop = get_xml_element_properties(container)
        if container_prop['type'] == 'RAID_GROUP':
            raid_group_name = container_prop['name']
            container.getparent().remove(container)
        elif container_prop['type'] == 'POOL':
            storage_pool_name = container_prop['name']

    if storage_pool_name is None:
        raise AttributeError("Could not find Storage Pool in the model")

    # Update the Fencing LUNs to use the Storage Pool and not the Raid Group
    for disk in xpath(enm_etree, 'lun-disk'):
        disk_props = get_xml_element_properties(disk)

        try:
            if disk_props['storage_container'] == raid_group_name:
                for child in disk.getchildren():
                    if child.tag == 'storage_container':
                        child.text = storage_pool_name
        except KeyError:
            pass

    write_xml(enm_etree, enm_xml)
    return True
