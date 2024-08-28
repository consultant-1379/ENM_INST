from genericpath import exists
from os import remove
import os
from tempfile import gettempdir
from os.path import join
from lxml import etree
from lxml.etree import Element
from unittest2 import TestCase
from h_xml.xml_utils import xpath, _NAMESPACES, is_ns_tag, _LITPNS, \
    load_xml, write_xml, get_xml_element_properties, get_parent, \
    inherit_infra_route, add_infra_route



NS_XML = """
<litp:root xmlns:litp="http://www.ericsson.com/litp">
    <litp:alias id="alias_1">
      <address>1.1.1.1</address>
    </litp:alias>
    <litp:alias id="alias_2">
      <address>2.2.2.2</address>
    </litp:alias>
</litp:root>
"""

XML_PROP = """
<litp:root xmlns:litp="http://www.ericsson.com/litp">
  <litp:vm-nfs-mount id="nfsm-batch">
    <device_path>v_device_path</device_path>
    <mount_options>v_mount_options</mount_options>
    <mount_point>v_mount_point</mount_point>
  </litp:vm-nfs-mount>
</litp:root>
"""

XML_INHERIT = """
<litp:root xmlns:litp="http://www.ericsson.com/litp">
 <litp:vcs-clustered-service id="nodecli">
   <active>2</active>
   <dependency_list>lvsrouter</dependency_list>
   <name>nodecli</name>
   <node_list>svc-1,svc-2</node_list>
   <standby>0</standby>
   <litp:clustered-service-applications-collection id="applications">
     <litp:vm-service-inherit source_path="/software/services/nodecli" id="vm-service_nodecli" />
   </litp:clustered-service-applications-collection>
   <litp:clustered-service-ha_configs-collection id="ha_configs">
     <litp:ha-service-config id="haservice_nodecli">
       <status_interval>30</status_interval>
       <status_timeout>15</status_timeout>
       <clean_timeout>310</clean_timeout>
       <fault_on_monitor_timeouts>3</fault_on_monitor_timeouts>
       <restart_limit>3</restart_limit>
       <startup_retry_limit>3</startup_retry_limit>
       <tolerance_limit>3</tolerance_limit>
     </litp:ha-service-config>
   </litp:clustered-service-ha_configs-collection>
   <litp:clustered-service-runtimes-collection id="runtimes" />
   <offline_timeout>300</offline_timeout>
   <online_timeout>600</online_timeout>
 </litp:vcs-clustered-service>
</litp:root>
"""

XML_NODES = """
<litp:root xmlns:litp="http://www.ericsson.com/litp" id="root">
  <litp:root-deployments-collection id="deployments">
    <litp:deployment id="enm">
      <litp:deployment-clusters-collection id="clusters">
        <litp:vcs-cluster id="db_cluster">
          <litp:cluster-nodes-collection id="nodes">
            <litp:node id="db-1">
              <litp:node-routes-collection id="routes">
                <litp:route-inherit id="multicast_route_db_node1"
                source_path="/r1"/>
              </litp:node-routes-collection>
            </litp:node>
            <litp:node id="db-2">
              <litp:node-routes-collection id="routes">
                <litp:route-inherit id="multicast_route_db_node1"
                source_path="/r1"/>
              </litp:node-routes-collection>
            </litp:node>
          </litp:cluster-nodes-collection>
        </litp:vcs-cluster>
      </litp:deployment-clusters-collection>
    </litp:deployment>
  </litp:root-deployments-collection>
</litp:root>
"""


class TestXmlUtils(TestCase):

    def test_get_parent(self):
        xfile = join(gettempdir(), 'test_get_parent.xml')
        with open(xfile, 'w') as ofile:
            ofile.write(XML_INHERIT)
        xml = load_xml(xfile)
        try:
            inherrited_vm = xpath(xml, 'vm-service-inherit',
                                  {'source_path':
                                       '/software/services/nodecli'})[0]
            parent_type = 'vcs-clustered-service'
            parent = get_parent(inherrited_vm, parent_type)
            self.assertEqual(parent[0].tag, 'active')
            self.assertEqual(parent[0].text, '2')
            self.assertEqual(parent[1].tag, 'dependency_list')
            self.assertEqual(parent[1].text, 'lvsrouter')
            self.assertEqual(parent[2].tag, 'name')
            self.assertEqual(parent[2].text, 'nodecli')
            self.assertEqual(parent[3].tag, 'node_list')
            self.assertEqual(parent[3].text, 'svc-1,svc-2')
            self.assertEqual(parent[4].tag, 'standby')
            self.assertEqual(parent[4].text, '0')

            not_inheritted_vm = None
            parent_type = 'ms'
            parent = get_parent(not_inheritted_vm, parent_type)
            self.assertEqual(parent, None)

        finally:
            os.remove(xfile)

    def test_get_xml_element_properties(self):
        root = etree.fromstring(XML_PROP)
        props = get_xml_element_properties(root.getchildren()[0])
        for kvp in [('device_path', 'v_device_path'),
                    ('mount_options', 'v_mount_options'),
                    ('mount_point', 'v_mount_point')]:
            self.assertIn(kvp[0], props)
            self.assertEqual(kvp[1], props[kvp[0]])

    def test_xpath(self):
        root = etree.fromstring(NS_XML)
        self.assertEqual(2, len(xpath(root, 'alias')))
        self.assertEqual(1, len(xpath(root, 'alias', attributes=
        {'id':'alias_1'})))
        self.assertEqual(2, len(xpath(root, 'address', namespace=False)))

    def test_load_xml(self):
        xfile = join(gettempdir(), 'test.xml')

        self.assertRaises(IOError, load_xml, xfile)

        with open(xfile, 'w') as ofile:
            ofile.write('<abc>def</abc>')
        try:
            xml = load_xml(xfile)
            self.assertEqual('abc', xml.getroot().tag)
            self.assertEqual('def', xml.getroot().text)
        finally:
            if exists(xfile):
                remove(xfile)

    def test_write_xml(self):
        xmldata = '<root>data</root>'
        root = etree.fromstring(xmldata)
        xfile = join(gettempdir(), 'test.xml')
        if exists(xfile):
            remove(xfile)
        try:
            write_xml(root, xfile)
            with open(xfile, 'r') as ifile:
                xml = '\n'.join(ifile.readlines())
            self.assertTrue(xmldata in xml)
        finally:
            if exists(xfile):
                remove(xfile)

    def test_inherit_infra_route(self):
        root = etree.fromstring(XML_NODES)
        route_name = 'new_route'
        source_path = '/route/source/{0}'.format(route_name)
        inherit_infra_route(root, source_path, 'db-1')
        inherit_infra_route(root, source_path, 'db-2')

        xpath_string = './/litp:route-inherit'
        routes = root.xpath(xpath_string, namespaces=_NAMESPACES)
        self.assertEqual(4, len(routes), 'Expected to find 4 routes '
                                         '(2 per node)')
        new_routes = 0
        for route in routes:
            if route.get('id') == route_name:
                new_routes += 1
                self.assertEqual(source_path, route.get('source_path'))
        self.assertEqual(2, new_routes, 'Expected to find 2 new reoutes!')

        self.assertRaises(KeyError, inherit_infra_route, root, source_path,
                          'db-3')

    def test_add_infra_route(self):
        parent = Element('parent')
        add_infra_route(parent, 'route_name', '1.2.3.4')
        self.assertEqual(1, len(parent.getchildren()))
        route = parent.getchildren()[0]
        self.assertEqual('{http://www.ericsson.com/litp}route', route.tag)
        self.assertEqual('route_name', route.get('id'))

        self.assertEqual(2, len(route.getchildren()))
        self.assertEqual('gateway', route.getchildren()[0].tag)
        self.assertEqual('1.2.3.4', route.getchildren()[0].text)
        self.assertEqual('subnet', route.getchildren()[1].tag)
        self.assertEqual('0.0.0.0/0', route.getchildren()[1].text)

    def test_is_ns_tag(self):
        self.assertTrue(is_ns_tag('{0}def'.format(_LITPNS)))
        self.assertFalse(is_ns_tag('def'))
        self.assertFalse(is_ns_tag('<!--def-->'))
