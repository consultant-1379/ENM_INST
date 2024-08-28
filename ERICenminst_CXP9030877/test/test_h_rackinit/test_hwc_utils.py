import shutil
from os import makedirs
from os.path import join, isdir, exists, dirname
from tempfile import gettempdir

from lxml import etree
from lxml.etree import _Element
from mock import patch, MagicMock, call
from unittest2 import TestCase

from h_rackinit.hwc_utils import PxeTimeoutError, ping, is_ns_tag, _LITPNS, \
    BaseObject, Ssh, Scp, ModelItem, XmlReader, Config, SiteDoc
from h_util.h_utils import touch
from h_xml.xml_utils import xpath, get_xml_element_properties


class TestPxeTimeoutError(TestCase):
    def test_error(self):
        error = PxeTimeoutError('node', 'address', 10)
        self.assertEqual('node', error.node)
        self.assertEqual('address', error.address)
        self.assertEqual(10, error.timeout)

        self.assertEqual(
                'Node node/address has not come up within 10 seconds',
                str(error))


class TestFunctions(TestCase):
    @patch('h_rackinit.hwc_utils.exec_process')
    def test_ping(self, p_exec_process):
        p_exec_process.side_effect = [None, IOError]
        self.assertTrue(ping('1.1.1.1'))
        self.assertFalse(ping('2.2.2.2'))

    def test_is_ns_tag(self):
        self.assertFalse(is_ns_tag(etree.Comment('text').tag))

        tag = etree.Element(_LITPNS + 'node')
        self.assertTrue(is_ns_tag(tag.tag))

        tag = etree.Element('{http://www.bla.com/notin}node')
        self.assertFalse(is_ns_tag(tag.tag))


class TestBaseObject(TestCase):
    def setUp(self):
        super(TestBaseObject, self).setUp()
        self.tmpdir = join(gettempdir(), 'TestBaseObject')
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        makedirs(self.tmpdir)

    def tearDown(self):
        super(TestBaseObject, self).tearDown()
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def test_get_temp_dir(self):
        self.assertTrue(BaseObject.get_temp_dir().endswith('/.hwchecker'))

    @patch('h_rackinit.hwc_utils.exec_process')
    def test_exec_process(self, p_exec_process):
        p_exec_process.return_value = ['abc\ndef']
        self.assertEqual(['abc\ndef'], BaseObject.exec_process(['blaaa']))

        p_exec_process.side_effect = [IOError(1, 'expected exception')]
        self.assertRaises(IOError, BaseObject.exec_process, '')

    def test_readfile(self):
        test_file = join(self.tmpdir, 'read.file')
        with open(test_file, 'w') as _writer:
            _writer.write('a\nb')

        obj = BaseObject(MagicMock())
        self.assertEqual(['a\n', 'b'], obj._readfile(test_file))
        self.assertRaises(IOError, obj._readfile, 'aaaaa')

    def test_writefile(self):
        test_file = join(self.tmpdir, 'dir/write.file')
        obj = BaseObject(MagicMock())
        obj._writefile(test_file, 'data')

        self.assertTrue(exists(test_file))
        with open(test_file, 'r') as _reader:
            self.assertEqual(['data'], _reader.readlines())


class TestSsh(TestCase):
    def setUp(self):
        super(TestSsh, self).setUp()
        self.tmpdir = join(gettempdir(), 'TestSsh')
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        makedirs(self.tmpdir)

    def tearDown(self):
        super(TestSsh, self).tearDown()
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    @patch('h_rackinit.hwc_utils.BaseObject.get_temp_dir')
    def test_exists(self, p_get_temp_dir):
        p_get_temp_dir.return_value = self.tmpdir

        self.assertRaises(IOError, Ssh.ssh_pub)
        self.assertRaises(IOError, Ssh.ssh_priv)

        touch(Ssh._priv())
        touch(Ssh._pub())
        self.assertTrue(Ssh.exists())
        self.assertEqual(Ssh._priv(), Ssh.ssh_priv())
        self.assertEqual(Ssh._pub(), Ssh.ssh_pub())

    @patch('h_rackinit.hwc_utils.remove')
    @patch('h_rackinit.hwc_utils.chmod')
    @patch('h_rackinit.hwc_utils.BaseObject.exec_process')
    @patch('h_rackinit.hwc_utils.exists')
    def test_keygen(self, p_exists, p_exec_process, p_chmod, p_remove):
        p_exists.return_value = False
        if isdir(dirname(Ssh._priv())):
            shutil.rmtree(dirname(Ssh._priv()))
        Ssh.keygen()
        p_exec_process.assert_has_calls(
                [call(['/usr/bin/ssh-keygen', '-N', '', '-f',
                       Ssh._priv()])])

        p_chmod.assert_has_calls([
            call(Ssh._priv(), 384),
            call(Ssh._pub(), 384)
        ], any_order=True)
        self.assertEqual(0, p_remove.call_count)

        p_exec_process.reset_mock()
        p_chmod.reset_mock()
        p_exists.return_value = True
        Ssh.keygen()
        p_exec_process.assert_has_calls(
                [call(['/usr/bin/ssh-keygen', '-N', '', '-f',
                       Ssh._priv()])])

        p_chmod.assert_has_calls([
            call(Ssh._priv(), 384),
            call(Ssh._pub(), 384)
        ], any_order=True)
        p_remove.assert_has_calls([
            call(Ssh._priv()),
            call(Ssh._pub())
        ], any_order=True)

    @patch('h_rackinit.hwc_utils.BaseObject.exec_process')
    @patch('h_rackinit.hwc_utils.Ssh.ssh_priv')
    def test_exec_remote(self, p_ssh_priv, p_exec_process):
        p_ssh_priv.return_value = 'private_key_file'
        p_exec_process.return_value = ['yip']
        Ssh.exec_remote(['command'], 'hostname')
        self.assertEqual(1, p_exec_process.call_count)
        _str = ' '.join(p_exec_process.call_args[0][0])

        # Just checking certain options are in the ssh command
        self.assertTrue('-i private_key_file' in _str)
        self.assertTrue('root@hostname' in _str)
        self.assertTrue('StrictHostKeyChecking=no' in _str)

    @patch('h_rackinit.hwc_utils.BaseObject.exec_process')
    @patch('h_rackinit.hwc_utils.Ssh.ssh_priv')
    def test_restart(self, p_ssh_priv, p_exec_process):
        p_ssh_priv.return_value = 'private_key_file'
        Ssh.restart('service_name', 'hostname')

        self.assertEqual(1, p_exec_process.call_count)
        _str = ' '.join(p_exec_process.call_args[0][0])
        # Just checking certain options are in the ssh command
        self.assertTrue('-i private_key_file' in _str)
        self.assertTrue('root@hostname' in _str)
        self.assertTrue('StrictHostKeyChecking=no' in _str)
        self.assertTrue('service_name restart' in _str)

    @patch('h_rackinit.hwc_utils.BaseObject.exec_process')
    @patch('h_rackinit.hwc_utils.Ssh.ssh_priv')
    def test_cat(self, p_ssh_priv, p_exec_process):
        p_ssh_priv.return_value = 'private_key_file'
        Ssh.cat('file_path', 'hostname')

        self.assertEqual(1, p_exec_process.call_count)
        _str = ' '.join(p_exec_process.call_args[0][0])
        # Just checking certain options are in the ssh command
        self.assertTrue('-i private_key_file' in _str)
        self.assertTrue('root@hostname' in _str)
        self.assertTrue('StrictHostKeyChecking=no' in _str)
        self.assertTrue('cat file_path' in _str)


class TestScp(TestCase):
    @patch('h_rackinit.hwc_utils.exists')
    def test_put(self, p_exists):
        p_exists.reset_mock()
        p_exists.return_value = True
        scp = Scp('host', 'user', 'priv_key', MagicMock())
        m_exec_process = MagicMock()
        scp.exec_process = m_exec_process
        scp.put('localf', 'remotef')

        self.assertEqual(1, m_exec_process.call_count)
        _str = ' '.join(m_exec_process.call_args[0][0])
        # Just checking certain options are in the ssh command
        self.assertTrue('-i priv_key' in _str)
        self.assertTrue('StrictHostKeyChecking=no' in _str)
        self.assertTrue('localf user@host:remotef' in _str)


class TestModelItem(TestCase):
    def test_model_item(self):
        node = etree.Element(_LITPNS + 'item_type', attrib={'id': 'eid'})
        node_prop = etree.Element('property')
        node_prop.text = 'value'
        node.append(node_prop)

        child = etree.Element(_LITPNS + 'child_type', attrib={'id': 'cid'})
        node.append(child)

        item = ModelItem(node)
        item.set_defaults({'always': 'default'})

        self.assertEqual(node, item.element())
        self.assertEqual('eid', item.item_id)
        self.assertEqual('item_type', item.item_type_id)

        self.assertEqual('value', item.property)
        self.assertEqual('default', item.always)

        children = item.children()
        self.assertEqual(child, children[0].element())
        self.assertEqual(1, len(children))
        self.assertEqual('cid', children[0].item_id)
        self.assertEqual('child_type', children[0].item_type_id)

        self.assertEqual(children[0], item.cid)
        self.assertIsNone(item.not_found)

        self.assertEqual('item_type:eid', str(item))


class TestXmlReader(TestCase):
    def mock_xml_element(self, item_type, item_id):
        m_xml = MagicMock(tag=_LITPNS + item_type)
        m_xml.get.return_value = item_id

        return m_xml

    def get_reader(self):
        reader = XmlReader()
        xml_file = join(dirname(__file__), 'hwc_test_model.xml')
        reader.load(xml_file)
        return reader

    def mock_model_item(self, item_type, item_id, **properties):
        item = ModelItem(self.mock_xml_element(item_type, item_id))
        item.set_defaults(properties)
        return item

    def test_load(self):
        reader = self.get_reader()
        self.assertIsNotNone(reader._doc)
        self.assertEqual(_LITPNS + 'root', reader._doc.getroot().tag)

    def test_get_nodes_by_id(self):
        reader = self.get_reader()
        nodes = reader.get_nodes_by_id(['str-1', 'abc'])
        self.assertEqual(1, len(nodes))
        self.assertTrue(type(nodes[0]) is _Element)
        self.assertEqual('str-1', nodes[0].attrib['id'])

    def test_get_book_disk(self):
        reader = self.get_reader()
        str1 = reader.get_nodes_by_id(['str-1'])[0]
        self.assertEqual('sda', reader.get_boot_disk(str1))

        blade = xpath(reader.infrastructure,
                      'blade', {'id': 'str-1_system'})[0]

        blade_parent = blade.getparent()

        blade_parent.remove(blade)
        self.assertRaises(KeyError, reader.get_boot_disk, str1)

        blade_parent.append(blade)
        for disk in xpath(blade, 'disk'):
            for child in disk.getchildren():
                if child.tag == 'bootable':
                    child.text = 'false'
                    break
        self.assertRaises(ValueError, reader.get_boot_disk, str1)

    def test_get_infrastructure(self):
        reader = self.get_reader()
        infra = reader.infrastructure
        self.assertTrue(type(infra) is _Element)
        self.assertIsNotNone(infra)
        self.assertEqual('infrastructure', infra.attrib['id'])

    def test_get_lms(self):
        reader = self.get_reader()
        lms = reader.lms
        self.assertIsNotNone(lms)
        self.assertTrue(type(lms) is ModelItem)
        self.assertEqual('ms', lms.item_id)

    def test_get_bridge_parent(self):
        nets = [
            self.mock_model_item('eth', 'eth0', bridge='br0'),
            self.mock_model_item('eth', 'eth1', bridge='br1')
        ]
        br1 = self.mock_model_item('bridge', 'br1', device_name='br1')
        brx = self.mock_model_item('bridge', 'brX', device_name='brX')
        parent = XmlReader.get_bridge_parent(br1, nets)
        self.assertIsNotNone(parent)
        self.assertEqual('eth1', parent.item_id)

        self.assertIsNone(XmlReader.get_bridge_parent(brx, nets))

    def test_get_vcs_llt_nets(self):
        reader = self.get_reader()
        self.assertEqual(set(['heartbeat2', 'heartbeat1']),
                         reader.get_vcs_llt_nets())

    def test_get_static_routes(self):
        reader = self.get_reader()
        str1 = reader.get_nodes_by_id(['str-1'])[0]
        routes_1 = reader.get_static_routes(str1)
        self.assertEqual(1, len(routes_1))
        self.assertEqual('services_gateway_route', routes_1[0].item_id)

        routes_2 = reader.get_static_routes(ModelItem(str1))
        self.assertEqual(1, len(routes_2))
        self.assertEqual('services_gateway_route', routes_2[0].item_id)

        self.assertEqual(routes_1[0].item_id, routes_2[0].item_id)

        for route in xpath(reader.infrastructure, 'route'):
            route.getparent().remove(route)
        self.assertRaises(ValueError, reader.get_static_routes, str1)

    def test_get_subnets(self):
        reader = XmlReader()
        xml_file = join(dirname(__file__), 'hwc_test_model.xml')
        reader.load(xml_file)

        test_sed = SiteDoc(join(dirname(__file__), 'hwc_test_sed.txt'))
        subnets = reader.get_subnets(test_sed)

        self.assertIn('services', subnets)
        self.assertEqual('131.75.2.0/28', str(subnets['services']))

        self.assertIn('backup', subnets)
        self.assertEqual('192.168.3.0/24', str(subnets['backup']))

        self.assertIn('internal', subnets)
        self.assertEqual('192.168.1.0/24', str(subnets['internal']))

        self.assertIn('storage', subnets)
        self.assertEqual('192.168.2.0/24', str(subnets['storage']))

        self.assertIn('jgroups', subnets)
        self.assertEqual('192.168.4.0/24', str(subnets['jgroups']))

    def test_get_management_network(self):
        reader = self.get_reader()

        self.assertEqual('internal', reader.get_managment_network())

        for _net in xpath(reader.infrastructure, 'network'):
            props = get_xml_element_properties(_net)
            if props['litp_management'] == 'true':
                for child in _net.getchildren():
                    if child.tag == 'litp_management':
                        child.text = 'false'
                        break
        self.assertIsNone(reader.get_managment_network())

    def test_get_bond_eth_slaves(self):
        node_networks = [
            self.mock_model_item('eth', 'eth0', master='bond1'),
            self.mock_model_item('eth', 'eth1', master='bond1'),
            self.mock_model_item('eth', 'eth2', master='bond0'),
            self.mock_model_item('eth', 'eth3', master='bond0')
        ]

        m_bond = self.mock_model_item('bond', 'bond0',
                                      device_name='bond0')
        slaves = XmlReader.get_bond_eth_slaves(node_networks, m_bond)
        self.assertEqual(2, len(slaves))
        self.assertIn(node_networks[2], slaves)
        self.assertIn(node_networks[3], slaves)

        self.assertRaises(ValueError, XmlReader.get_bond_eth_slaves,
                          node_networks, node_networks[0])

    def test_get_bridge_root_nic(self):
        reader = XmlReader()

        br0 = self.mock_model_item('bridge', 'br0', device_name='br0')
        br1 = self.mock_model_item('bridge', 'br1', device_name='br1')

        # Simple case of a bridge connected to an eth
        node_networks = [
            self.mock_model_item('eth', 'eth0', bridge='br0'),
            self.mock_model_item('eth', 'eth1', bridge='br1')
        ]
        base_nic = reader.get_bridge_root_nic(node_networks, br1)
        self.assertIsNotNone(base_nic)
        self.assertEqual('eth1', base_nic.item_id)

        # Real case of bridge conncted to bonded eth
        nets = [
            self.mock_model_item('eth', 'eth0', device_name='eth0',
                                 master='bond0'),
            self.mock_model_item('eth', 'eth1', device_name='eth1',
                                 master='bond0'),
            self.mock_model_item('bond', 'bond0', bridge='br0',
                                 device_name='bond0'),
            br0,

            self.mock_model_item('eth', 'eth2', master='bond1'),
            self.mock_model_item('eth', 'eth3', master='bond1'),
            self.mock_model_item('bond', 'bond1', bridge='br1',
                                 device_name='bond1'),
            br1
        ]
        base_nic = reader.get_bridge_root_nic(nets, br0)
        self.assertIsNotNone(base_nic)
        self.assertEqual('eth0', base_nic.item_id)

        base_nic = reader.get_bridge_root_nic(nets, br1)
        self.assertIsNotNone(base_nic)
        self.assertEqual('eth2', base_nic.item_id)

        # Expect None if the bridge isn't connected to anything....
        base_nic = reader.get_bridge_root_nic(
                [self.mock_model_item('eth', 'eth0', device_name='eth0')],
                br1)
        self.assertIsNone(base_nic)

        # Excect None if a bridge is connedted to some other unknown device
        nets = [
            self.mock_model_item('vlan', 'b.1', device_name='b.1',
                                 bridge='br1'), br1
        ]
        base_nic = reader.get_bridge_root_nic(nets, br1)
        self.assertIsNone(base_nic)

    def test_get_pxe_device(self):
        reader = XmlReader()
        xml_file = join(dirname(__file__), 'hwc_test_model.xml')
        reader.load(xml_file)

        # Streaming setup i.e. pxe_boot_only on eth4
        node = reader.get_nodes_by_id(['str-1'])[0]
        pxe_device = reader.get_pxe_device(node, 'internal')
        self.assertIsNotNone(pxe_device)
        self.assertEqual('eth4', pxe_device.item_id)

        # Generic blade setup; a bonds first slave defice
        node = reader.get_nodes_by_id(['str-2'])[0]
        pxe_device = reader.get_pxe_device(node, 'services')
        self.assertIsNotNone(pxe_device)
        self.assertEqual('eth0', pxe_device.item_id)

        self.assertRaises(ValueError, reader.get_pxe_device, node, 'unknown')

        node = reader.get_nodes_by_id(['str-3'])[0]
        self.assertRaises(Exception, reader.get_pxe_device, node, 'services')

        dev = reader.get_pxe_device(node, 'internal')
        self.assertEqual('eth1', dev.item_id)


class TestConfig(TestCase):
    def test_get_config(self):
        cfg = Config.get_config()
        self.assertTrue(cfg.has_section('LITP'))
        self.assertTrue(cfg.has_section('TEMP'))
        self.assertTrue(cfg.has_section('PARTITIONS'))


class TestSiteDoc(TestCase):
    def test_get_sed_value(self):
        sed = SiteDoc(None)
        sed.sed = {
            'key': 'value'
        }
        self.assertEqual('value', sed.get_sed_value('key'))
        self.assertEqual('value', sed.get_sed_value('%%key%%'))
        self.assertRaises(KeyError, sed.get_sed_value, 'key1')
        self.assertRaises(KeyError, sed.get_sed_value, '%%key1%%')
