import sys

from os import remove
from tempfile import gettempdir
from os.path import exists, join

from mock import MagicMock, patch
from netaddr import IPAddress, IPNetwork
from unittest2 import TestCase

sys.modules['sanapiexception'] = MagicMock()

from workarounds.storage_default_route.w_lookups import \
    get_storage_providers, \
    DefaultRouteException, get_network_subnet, get_modeled_route, \
    get_nas_storage_default_route, check_in_network, \
    _get_storage_providers_litp, _get_network_subnet_litp, \
    _get_modeled_route_litp, litp, PROVIDER_TYPE_SAN, \
    _get_storage_providers_xml, _get_network_subnet_xml, \
    _get_modeled_route_xml

XML_SP = """
<litp:root xmlns:litp="http://www.ericsson.com/litp" id="root">
    <litp:san-emc id="san1">
      <ip_a>10.32.231.48</ip_a>
      <ip_b>10.32.231.49</ip_b>
      <name>atvnx-77</name>
      <password_key>key-for-san-atvnx-77</password_key>
      <username>admin</username>
      <login_scope>global</login_scope>
      <san_type>vnx2</san_type>
    </litp:san-emc>
</litp:root>
"""

XML_NETWORKS = """
<litp:root xmlns:litp="http://www.ericsson.com/litp" id="root">
  <litp:infrastructure id="infrastructure">
    <litp:networking id="networking">
      <litp:networking-networks-collection id="networks">
        <litp:network id="services_network">
          <litp_management>false</litp_management>
          <name>services</name>
          <subnet>141.137.208.0/23</subnet>
        </litp:network>
      </litp:networking-networks-collection>
    </litp:networking>
  </litp:infrastructure>
</litp:root>
"""

XML_ROUTES = """
<litp:root xmlns:litp="http://www.ericsson.com/litp" id="root">
  <litp:infrastructure id="infrastructure">
    <litp:networking id="networking">
      <litp:networking-routes-collection id="routes">
        <litp:route id="services_gateway_route">
          <gateway>141.137.208.1</gateway>
          <subnet>0.0.0.0/0</subnet>
        </litp:route>
      </litp:networking-routes-collection>
    </litp:networking>
  </litp:infrastructure>
</litp:root>
"""


class TestWLookups(TestCase):
    MODNAME = 'workarounds.storage_default_route.w_lookups.'

    @patch(MODNAME + 'LitpRestClient')
    def test_litp_getclass(self, mlitp):
        obj = litp()

        obj2 = litp()
        self.assertEqual(obj, obj2)

    @patch(MODNAME + '_get_storage_providers_litp')
    @patch(MODNAME + '_get_storage_providers_xml')
    def test_get_storage_providers_source(self, _xml, _litp):
        _litp.side_effect = [{'': ''}]
        get_storage_providers('', source=None)
        self.assertTrue(_litp.called)
        self.assertFalse(_xml.called)

        _xml.reset_mock()
        _litp.reset_mock()
        _litp.side_effect = [None]
        self.assertRaises(DefaultRouteException, get_storage_providers, '',
                          None)

        _xml.reset_mock()
        _litp.reset_mock()
        _xml.side_effect = [{'': ''}]
        get_storage_providers('', source='afile')
        self.assertFalse(_litp.called)
        self.assertTrue(_xml.called)

        _xml.reset_mock()
        _litp.reset_mock()
        _xml.side_effect = [None]
        self.assertRaises(DefaultRouteException, get_storage_providers, '',
                          'somefile')

    @patch(MODNAME + '_get_network_subnet_litp')
    @patch(MODNAME + '_get_network_subnet_xml')
    def test_get_network_subnet_source(self, _xml, _litp):
        _litp.side_effect = [{'': ''}]
        get_network_subnet('', source=None)
        self.assertTrue(_litp.called)
        self.assertFalse(_xml.called)

        _xml.reset_mock()
        _litp.reset_mock()
        _litp.side_effect = [None]
        self.assertRaises(DefaultRouteException, get_network_subnet, '',
                          None)

        _xml.reset_mock()
        _litp.reset_mock()
        _xml.side_effect = [{'': ''}]
        get_network_subnet('', source='afile')
        self.assertFalse(_litp.called)
        self.assertTrue(_xml.called)

        _xml.reset_mock()
        _litp.reset_mock()
        _xml.side_effect = [None]
        self.assertRaises(DefaultRouteException, get_network_subnet, '',
                          'somefile')

    @patch(MODNAME + '_get_modeled_route_litp')
    @patch(MODNAME + '_get_modeled_route_xml')
    def test_get_modeled_route_source(self, _xml, _litp):
        ip = IPAddress('127.0.0.1')

        _litp.side_effect = [{'': ''}]
        get_modeled_route(ip, source=None)
        self.assertTrue(_litp.called)
        self.assertFalse(_xml.called)

        _xml.reset_mock()
        _litp.reset_mock()
        _xml.side_effect = [{'': ''}]
        get_modeled_route(ip, source='afile')
        self.assertFalse(_litp.called)
        self.assertTrue(_xml.called)

    def test_check_in_network(self):
        subnet = IPNetwork('10.140.1.0/24')
        self.assertTrue(check_in_network(IPAddress('10.140.1.29'), subnet))
        self.assertTrue(check_in_network(IPAddress('10.140.1.1'), subnet))
        self.assertFalse(check_in_network(IPAddress('10.140.2.29'), subnet))

    @patch(MODNAME + 'NasConsole')
    @patch(MODNAME + 'Decryptor')
    @patch(MODNAME + 'get_storage_providers')
    def test_get_nas_storage_default_route(self, m_get_storage_providers,
                                           m_decryptor, m_nasconsole):
        subnet = IPNetwork('10.140.1.0/24')

        m_get_storage_providers.return_value = {}
        self.assertRaises(DefaultRouteException,
                          get_nas_storage_default_route, subnet)

        m_get_storage_providers.return_value = [
            {'user_name': 'uname', 'password_key': ' password_key',
             'management_ipv4': '10.140.1.29'}
        ]
        m_nasconsole.return_value.ip_route_show.return_value = [
            '127.0.0.0/8 dev lo  scope link',
            'default via 10.140.1.1 dev pubeth0'
        ]
        dr = get_nas_storage_default_route(subnet)
        self.assertEqual(IPAddress('10.140.1.1'), dr)

    @patch(MODNAME + 'litp')
    @patch(MODNAME + 'LitpRestClient')
    def test__get_storage_providers_litp(self, mlitp, get_litp):
        get_litp.side_effect = mlitp
        mlitp.return_value.get_children.return_value = [
            {'path': '/p1', 'data': {
                'item-type-name': 'boo',
                'properties': {'p': 'p1'}
            }},
            {'path': '/p2', 'data': {
                'item-type-name': PROVIDER_TYPE_SAN,
                'properties': {'p': 'p2'}
            }}
        ]
        found = _get_storage_providers_litp(PROVIDER_TYPE_SAN)
        self.assertEqual(1, len(found))
        self.assertEqual('p2', found[0]['p'])

    @patch(MODNAME + 'litp')
    @patch(MODNAME + 'LitpRestClient')
    def test__get_network_subnet_litp(self, mlitp, get_litp):
        get_litp.side_effect = mlitp
        subnet = IPNetwork('192.168.0.1/24')
        mlitp.return_value.get_children.return_value = [
            {'path': '/p1', 'data': {
                'item-type-name': 'boo',
                'properties': {'name': 'netname', 'subnet': str(subnet)}
            }},
            {'path': '/p1', 'data': {
                'item-type-name': 'boo',
                'properties': {'name': 'netname2', 'subnet': '192.168.20.0/22'}
            }}
        ]
        found = _get_network_subnet_litp('netname')
        self.assertEqual(subnet, found)

    @patch(MODNAME + 'litp')
    @patch(MODNAME + 'LitpRestClient')
    def test__get_modeled_route_litp(self, mlitp, get_litp):
        get_litp.side_effect = mlitp
        ip = IPAddress('192.168.0.1')
        mlitp.return_value.get_children.return_value = [
            {'path': '/p1', 'data': {
                'item-type-name': 'boo',
                'id': 'p1',
                'properties': {'gateway': str(ip)}
            }}
        ]
        rid, props = _get_modeled_route_litp(ip)
        self.assertEqual('p1', rid)
        self.assertDictEqual({'gateway': str(ip)}, props)

    def test__get_storage_providers_xml(self):
        xfile = join(gettempdir(), 'test.xml')
        with open(xfile, 'w') as ofile:
            ofile.write(XML_SP)
        try:
            found = _get_storage_providers_xml(PROVIDER_TYPE_SAN, xfile)
            self.assertEqual(1, len(found))
            self.assertEqual('atvnx-77', found[0]['name'])
        finally:
            if exists(xfile):
                remove(xfile)

    def test__get_network_subnet_xml(self):
        xfile = join(gettempdir(), 'test.xml')
        with open(xfile, 'w') as ofile:
            ofile.write(XML_NETWORKS)
        try:
            found = _get_network_subnet_xml('services', xfile)
            self.assertEqual(IPNetwork('141.137.208.0/23'), found)
        finally:
            if exists(xfile):
                remove(xfile)

    def test__get_modeled_route_xml(self):
        xfile = join(gettempdir(), 'test.xml')
        with open(xfile, 'w') as ofile:
            ofile.write(XML_ROUTES)
        try:
            name, props = _get_modeled_route_xml(IPAddress('141.137.208.1'),
                                                 xfile)
            self.assertEqual('services_gateway_route', name)
        finally:
            if exists(xfile):
                remove(xfile)

    # def test__get_modeled_defaultroute_xml(self):
    #     xfile = join(gettempdir(), 'test.xml')
    #     with open(xfile, 'w') as ofile:
    #         ofile.write(XML_ROUTES)
    #     try:
    #         name, ip = _get_modeled_defaultroute_xml(IPNetwork('0.0.0.0/0'),
    #                                                  xfile)
    #         self.assertEqual('services_gateway_route', name)
    #         self.assertEqual(IPAddress('141.137.208.1'), ip)
    #
    #         name, ip = _get_modeled_defaultroute_xml('1.1.1.1/0',
    #                                                  xfile)
    #         self.assertIsNone(name)
    #         self.assertIsNone(ip)
    #
    #     finally:
    #         if exists(xfile):
    #             remove(xfile)

    # @patch(MODNAME + 'litp')
    # @patch(MODNAME + 'LitpRestClient')
    # def test__get_modeled_defaultroute_litp(self, mlitp, get_litp):
    #     get_litp.side_effect = mlitp
    #     ip = IPAddress('192.168.0.1')
    #     subnet = IPNetwork('0.0.0.0/0')
    #     mlitp.return_value.get_children.return_value = [
    #         {'path': '/p1', 'data': {
    #             'item-type-name': 'boo',
    #             'id': 'services_gateway_route',
    #             'properties': {'gateway': str(ip), 'subnet': str(subnet)}
    #         }}
    #     ]
    #     name, aip = _get_modeled_defaultroute_litp(subnet)
    #     self.assertEqual('services_gateway_route', name)
    #     self.assertEqual(ip, aip)
    #
    #     name, aip = _get_modeled_defaultroute_litp('vvvv')
    #     self.assertIsNone(name)
    #     self.assertIsNone(aip)

    # @patch(MODNAME + '_get_modeled_defaultroute_litp')
    # @patch(MODNAME + '_get_modeled_defaultroute_xml')
    # def test_get_modeled_defaultroute_source(self, _xml, _litp):
    #     ip = IPAddress('127.0.0.1')
    #
    #     _litp.side_effect = [{'': ''}]
    #     get_modeled_defaultroute(ip, source=None)
    #     self.assertTrue(_litp.called)
    #     self.assertFalse(_xml.called)
    #
    #     _xml.reset_mock()
    #     _litp.reset_mock()
    #     _xml.side_effect = [{'': ''}]
    #     get_modeled_defaultroute(ip, source='afile')
    #     self.assertFalse(_litp.called)
    #     self.assertTrue(_xml.called)
