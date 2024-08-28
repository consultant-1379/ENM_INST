from os import remove, path
import sys
import tempfile

from mock import MagicMock, call, patch
sys.modules['sanapiexception'] = MagicMock()

from netaddr import IPNetwork, IPAddress

from unittest2 import TestCase

from workarounds.storage_default_route.storage_default_route import ipv4, \
    _check_updates_needed, _add_default_route, check_and_update, \
    main, is_pxe_on_services
from workarounds.storage_default_route.w_lookups import DefaultRouteException

XML_SNIPPET = """
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
            <litp:node id="scp-1">
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
  <litp:infrastructure id="infrastructure">
    <litp:infrastructure-items-collection id="items" />
    <litp:networking id="networking">
      <litp:networking-routes-collection id="routes">
        <litp:route id="services_gateway_route">
          <gateway>%%ENMservices_gateway%%</gateway>
          <subnet>0.0.0.0/0</subnet>
        </litp:route>
      </litp:networking-routes-collection>
    </litp:networking>
  </litp:infrastructure>
</litp:root>
"""
class TestStorageDefaultRoute(TestCase):
    MODNAME = 'workarounds.storage_default_route.storage_default_route.'

    def mock_sed(self, m_sed):
        m_sed.return_value.has_site_key.return_value = False

    def test_ipv4(self):
        self.assertFalse(ipv4('asd'))
        self.assertTrue(ipv4('127.0.0.1'))

    @patch(MODNAME + 'get_storage_providers')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test__check_updates_needed(self, m_sed, m_get_network_subnet,
                                   m_get_storage_providers):
        self.mock_sed(m_sed)

        m_get_network_subnet.return_value = IPNetwork('192.168.0.1/24')
        m_get_storage_providers.return_value = [{'ip_a': '192.168.0.22',
                                                 'ip_b': '192.168.0.23'}]
        self.assertFalse(_check_updates_needed('storage', ''))
        m_get_storage_providers.return_value = [{'ip_a': '192.168.0.22',
                                                 'ip_b': '127.0.0.1'}]
        self.assertFalse(_check_updates_needed('storage', ''))
        m_get_storage_providers.return_value = [{'ip_a': '192.168.200.22',
                                                 'ip_b': '192.168.200.23'}]
        self.assertTrue(_check_updates_needed('storage', ''))
        m_get_storage_providers.return_value = [{'ip_a': '192.168.200.22',
                                                 'ip_b': '127.0.0.1'}]
        self.assertTrue(_check_updates_needed('storage', ''))

    @patch(MODNAME + 'get_storage_providers')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test__check_updates_needed_pxeservices(self, m_sed,
                                               m_get_network_subnet,
                                               m_get_storage_providers):
        m_sed.return_value.has_site_key.return_value = False
        _check_updates_needed('', '')
        self.assertTrue(m_get_network_subnet.called)

        m_get_network_subnet.reset_mock()
        m_sed.return_value.has_site_key.return_value = True
        m_sed.return_value.get_value.return_value = 'services'
        _check_updates_needed('', '')
        self.assertFalse(m_get_network_subnet.called)

        m_get_network_subnet.reset_mock()
        m_sed.return_value.has_site_key.return_value = True
        m_sed.return_value.get_value.return_value = 'internal'
        _check_updates_needed('', '')
        self.assertTrue(m_get_network_subnet.called)

    @patch(MODNAME + 'Sed')
    def test_is_pxe_on_services(self, m_sed):
        m_sed.return_value.has_site_key.return_value = False
        self.assertFalse(is_pxe_on_services(''))

        m_sed.return_value.has_site_key.return_value = True
        m_sed.return_value.get_value.return_value = 'internal'
        self.assertFalse(is_pxe_on_services(''))

        m_sed.return_value.has_site_key.return_value = True
        m_sed.return_value.get_value.return_value = 'services'
        self.assertTrue(is_pxe_on_services(''))

    @patch(MODNAME + 'litp')
    def test__add_default_route_litp(self, get_litp):
        gateway_ip = IPAddress('192.168.0.1')
        get_litp.return_value.get_items_by_type.return_value = \
            [{'path': '/deployments/enm/clusters/db_cluster/nodes/db-1', 'data': {u'id': u'db-1'}},
             {'path': '/deployments/enm/clusters/db_cluster/nodes/db-2', 'data': {u'id': u'db-2'}}]
        _add_default_route('new_route', gateway_ip)
        calls = [
            call().create('/infrastructure/networking/routes', 'new_route',
                          'route', properties={'subnet': '0.0.0.0/0',
                                               'gateway': str(gateway_ip)}),
            call().get_items_by_type('/deployments/enm/clusters/db_cluster/nodes', 'node', []),
            call().inherit(
                '/deployments/enm/clusters/db_cluster/nodes/db-1/routes'
                '/new_route',
                '/infrastructure/networking/routes/new_route'),
            call().inherit(
                '/deployments/enm/clusters/db_cluster/nodes/db-2/routes/'
                'new_route',
                '/infrastructure/networking/routes/new_route')
        ]
        get_litp.assert_has_calls(calls, any_order=True)

    @patch(MODNAME + 'inherit_infra_route')
    @patch(MODNAME + 'add_infra_route')
    def test__add_default_route_xml(self,
                                    m_add_infra_route,
                                    m_inherit_infra_route):

        dd = tempfile.mktemp()
        with open(dd, 'w') as _writer:
            _writer.write(XML_SNIPPET)

        gateway_ip = IPAddress('192.168.0.1')
        _add_default_route('new_route', gateway_ip, dd)

        woo = False
        for ca in m_add_infra_route.call_args:
            if len(ca) == 3 and ca[1] == 'new_route' and ca[2] == str(
                    gateway_ip):
                woo = True
                break
        self.assertTrue(woo,
                        'Expected call to \'add_infra_route()\' not found!')

        woo = False
        source_path = '/infrastructure/networking/routes/new_route'
        for ca in m_inherit_infra_route.call_args:
            if len(ca) == 3 and ca[1] == source_path and ca[2] in ['db-1',
                                                                   'db-2']:
                woo = True
                break
        self.assertTrue(woo,
                        'Expected call to \'inherit_infra_route()\' '
                        'not found!')
        if path.exists(dd):
            remove(dd)

    @patch(MODNAME + '_check_updates_needed')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test_check_and_update_not_needed(self, m_sed,
                                         m_get_network_subnet,
                                         m_check_updates_needed):
        self.mock_sed(m_sed)
        m_check_updates_needed.return_value = False

        check_and_update('storage', '', None, auto_detect_gateway=True,
                         storage_gateway_ip=None,
                         new_route_name='new_route',
                         check_only=False)
        self.assertEqual(0, m_get_network_subnet.call_count)

    @patch(MODNAME + '_add_default_route')
    @patch(MODNAME + 'get_modeled_route')
    @patch(MODNAME + 'get_nas_storage_default_route')
    @patch(MODNAME + '_check_updates_needed')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test_check_and_update_needed_not_modeled(self, m_sed,
                                                 m_get_network_subnet,
                                                 m_check_updates_needed,
                                                 m_nas_storage_default_route,
                                                 m_get_modeled_route,
                                                 m_add_default_route):
        self.mock_sed(m_sed)
        m_check_updates_needed.return_value = True
        m_nas_storage_default_route.return_value = IPAddress('192.168.0.1')
        m_get_network_subnet.return_value = IPNetwork('192.168.0.1/24')
        m_get_modeled_route.return_value = (None, None)

        check_and_update('storage', '', None, auto_detect_gateway=True,
                         storage_gateway_ip=None,
                         new_route_name='new_route',
                         check_only=False)

        calls = [
            call('new_route', IPAddress('192.168.0.1'), None)
        ]
        m_add_default_route.assert_has_calls(calls, any_order=True)

    @patch(MODNAME + '_add_default_route')
    @patch(MODNAME + 'get_modeled_route')
    @patch(MODNAME + 'get_nas_storage_default_route')
    @patch(MODNAME + '_check_updates_needed')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test_check_and_update_needed_check_only(self, m_sed,
                                                m_get_network_subnet,
                                                m_check_updates_needed,
                                                m_nas_storage_default_route,
                                                m_get_modeled_route,
                                                m_add_default_route):
        self.mock_sed(m_sed)
        m_check_updates_needed.return_value = True
        m_nas_storage_default_route.return_value = IPAddress('192.168.0.1')
        m_get_network_subnet.return_value = IPNetwork('192.168.0.1/24')
        m_get_modeled_route.return_value = (None, None)

        check_and_update('storage', '', None, auto_detect_gateway=True,
                         storage_gateway_ip=None,
                         new_route_name='new_route',
                         check_only=True)

        self.assertEqual(0, m_add_default_route.call_count)

    @patch(MODNAME + '_add_default_route')
    @patch(MODNAME + 'get_modeled_route')
    @patch(MODNAME + 'get_nas_storage_default_route')
    @patch(MODNAME + '_check_updates_needed')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test_check_and_update_explicit_not_modeled(self, m_sed,
                                                   m_get_network_subnet,
                                                   m_check_updates_needed,
                                                   m_nas_storage_default_route,
                                                   m_get_modeled_route,
                                                   m_add_default_route):
        self.mock_sed(m_sed)
        user_gateway_ip = IPAddress('192.168.0.1')
        m_check_updates_needed.return_value = True
        m_get_network_subnet.return_value = IPNetwork('192.168.0.1/24')
        m_get_modeled_route.return_value = (None, None)

        check_and_update('storage', '', None, auto_detect_gateway=False,
                         storage_gateway_ip=user_gateway_ip,
                         new_route_name='new_route',
                         check_only=False)

        self.assertEqual(0, m_nas_storage_default_route.call_count)

        calls = [
            call('new_route', user_gateway_ip, None)
        ]
        m_add_default_route.assert_has_calls(calls, any_order=True)

    @patch(MODNAME + '_add_default_route')
    @patch(MODNAME + 'get_modeled_route')
    @patch(MODNAME + 'get_nas_storage_default_route')
    @patch(MODNAME + '_check_updates_needed')
    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + 'Sed')
    def test_check_and_update_needed_modeled(self, m_sed,
                                             m_get_network_subnet,
                                             m_check_updates_needed,
                                             m_nas_storage_default_route,
                                             m_get_modeled_route,
                                             m_add_default_route):
        self.mock_sed(m_sed)
        m_check_updates_needed.return_value = True
        m_nas_storage_default_route.return_value = IPAddress('192.168.0.1')

        m_get_modeled_route.return_value = ('route', {'some': 'ting'})

        check_and_update('storage', '', None, auto_detect_gateway=True,
                         storage_gateway_ip=None,
                         new_route_name='new_route',
                         check_only=False)

        self.assertEqual(0, m_add_default_route.call_count)

    @patch(MODNAME + 'get_network_subnet')
    @patch(MODNAME + '_check_updates_needed')
    def test_check_and_update_invalid_ip(self, m_check_updates_needed,
                                         m_get_network_subnet):
        m_check_updates_needed.return_value = True
        m_get_network_subnet.return_value = IPNetwork('192.168.0.1/24')

        self.assertRaises(DefaultRouteException, check_and_update, 'storage',
                          None,
                          auto_detect_gateway=False,
                          storage_gateway_ip='sdfsdf',
                          new_route_name='new_route',
                          check_only=False)

        self.assertRaises(DefaultRouteException, check_and_update, 'storage',
                          None,
                          auto_detect_gateway=False,
                          storage_gateway_ip='10.1.1.1',
                          new_route_name='new_route',
                          check_only=False)

    @patch(MODNAME + 'check_and_update')
    def test_main(self, m_check_and_update):
        args = []
        self.assertRaises(SystemExit, main, args)

        main(['--sed', '', '--auto', '--update'])
        self.assertEqual(1, m_check_and_update.call_count)

        m_check_and_update.reset_mock()
        afile = tempfile.mktemp()
        self.assertRaises(SystemExit, main, ['--sed', '',
                                             '--auto', '--update', afile])

        m_check_and_update.reset_mock()
        with open(afile, 'w') as _f:
            _f.write('')
        try:
            main(['--sed', '',
                  '--auto', '--update', afile])
            self.assertEqual(1, m_check_and_update.call_count)
        finally:
            remove(afile)
