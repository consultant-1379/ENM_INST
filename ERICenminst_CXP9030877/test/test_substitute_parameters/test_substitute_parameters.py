import os
from os import remove, environ
from os.path import join, dirname
from tempfile import gettempdir
from mock import patch
import unittest2
from h_litp.litp_utils import main_exceptions
from h_util.h_utils import ExitCodes
from substitute_parameters import Substituter, main

sed = '''#SED Template Version: 1.0.27
COM_INF_LDAP_ROOT_SUFFIX=dc=ieatlms4352,dc=com
Variable_Name=Variable_Value

ENMservices_subnet=10.59.142.0/23
ENMservices_gateway=10.59.142.1
ENMservices_IPv6gateway=2001:1b70:82a1:16:0:3018:0:1
ENMIPv6_subnet=2001:1b70:82a1:0017/64
storage_subnet=10.42.2.0/23
backup_subnet=10.0.24.0/21
jgroups_subnet=192.168.5.0/24
internal_subnet=192.168.55.0/24
VLAN_ID_storage=3019
VLAN_ID_backup=256
VLAN_ID_jgroups=2192
VLAN_ID_internal=2199
VLAN_ID_services=3018
svc_node2_IP=10.59.143.92
key_without_value=
line_with_no_equal_sign
=
'''

xml_template = '''<?xml version='1.0' encoding='utf-8'?>
<litp:root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp--schema/litp.xsd" id="root">
<!--                                                                                       -->
<!-- Purpose of ENM6Node tags                                                              -->
<!--   Within this XML Template there are several instances of the ENM6Node tag.           -->
<!--   This tag is used by ENMInst to identify XML that is for a 6 node deployment only.   -->
<!--                                                                                       -->
<!-- If the number of nodes in the SED is set to 4:                                        -->
<!--    then the XML between these tags, and the tags themselves, are removed.             -->
<!--                                                                                       -->
<!-- If the number of nodes in the SED is set to 6:                                        -->
<!--    then just the tags are removed, so 'activating' the XML.                           -->
<!--                                                                                       -->
<!-- The tags can be used to wrap around lines of XML or text within a single line of XML. -->
<!--                                                                                       -->
  <litp:root-deployments-collection id="deployments">
    <litp:deployment id="enm">
      <litp:deployment-clusters-collection id="clusters">
        <litp:vcs-cluster id="db_cluster">
          <litp:cluster-configs-collection id="configs">
            <litp:alias-cluster-config id="alias_configuration">
              <litp:alias-cluster-config-aliases-collection id="aliases">
                <litp:alias id="ENMservices_alias">
                  <address>%%db_node1_IP%%</address>
                  <alias_names>%%db_node1_hostname%%-ENMservices</alias_names>
                </litp:alias>
                <litp:alias id="postgresql_alias">
                  <address>%%db_vip_postgres%%</address>
                  <alias_names>postgresql01</alias_names>
                </litp:alias>
                <litp:alias id="versant_alias">
                  <address>%%db_vip_versant%%</address>
                  <alias_names>db1-service</alias_names>
                </litp:alias>
                <litp:alias id="ms-1_alias">
                  <address>%%LMS_IP%%</address>
                  <alias_names>ms-1</alias_names>
                </litp:alias>
                <litp:alias id="db-1_alias">
                  <address>%%db_node1_IP%%</address>
                  <alias_names>db-1</alias_names>
                </litp:alias>
                <litp:alias id="db-2_alias">
                  <address>%%db_node2_IP%%</address>
                  <alias_names>db-2</alias_names>
                </litp:alias>
                <litp:alias id="svc-1_alias">
                  <address>%%svc_node1_IP%%</address>
                  <alias_names>svc-1</alias_names>
                </litp:alias>
                <litp:alias id="svc-2_alias">
                  <address>%%svc_node2_IP%%</address>
                  <alias_names>svc-2</alias_names>
                </litp:alias>
                <litp:alias id="logstash_alias">
                  <address>%%logstash_storage%%</address>
                  <alias_names>logstashhost</alias_names>
                </litp:alias>
                <litp:alias id="ldap_alias">
                  <address>%%db_vip_opendj%%</address>
                  <alias_names>ldap-remote,ldap-local</alias_names>
                </litp:alias>
                <!--ENM6Node>
                <litp:alias id="svc-3_alias">
                  <address>%%svc_node3_IP%%</address>
                  <alias_names>svc-3</alias_names>
                </litp:alias>
                <litp:alias id="svc-4_alias">
                  <address>%%svc_node4_IP%%</address>
                  <alias_names>svc-4</alias_names>
                </litp:alias>
                <ENM6Node-->
              </litp:alias-cluster-config-aliases-collection>
            </litp:alias-cluster-config>
          </litp:cluster-configs-collection>
        </litp:vcs-cluster>
       </litp:deployment-clusters-collection>
      </litp:deployment>
    </litp:root-deployments-collection>
  </litp:root>'''

working = '''base_image=ERICrhel79lsbimage_CXP9041915-1.9.1.qcow2
jboss_image=ERICrhel79jbossimage_CXP9041916-1.9.1.qcow2
uuid_bootvg_DB1=6006016028503200F431BE8B4181E411
uuid_bootvg_DB2=6006016028503200F831BE8B4181E411
vm_ssh_key=vm_private_key.pub
uuid_appvg_DB1=6006016028503200F631BE8B4181E411
uuid_appvg_DB2=6006016028503200EE87EF774281E411'''

param = {'svc_node2_IP': '10.59.143.92'}

xml = '''<litp:alias id="svc-2_alias">
<address>%%svc_node2_IP%%</address>
<alias_names>svc-2</alias_names>
</litp:alias>'''

vm_public_key = 'ssh-rsa AAAA'

property_file_content = '''#Encrypted passwords
com_inf_ldap_admin_access_password_encrypted=U2FsdGVkX18nyWsgIBtQG66/7+39FPn0U0nOYBdf81I=
'''


class TestSubstitution(unittest2.TestCase):
    def setUp(self):
        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        self.xml = xml
        self.param = param
        self.xml_template = xml_template
        self.sed = sed
        new_working = working
        value = ''
        self.public_key = join(gettempdir(), 'vm_private_key.pub')
        for item in working.split():
            if item and item != '=' and not item.startswith("#") \
                    and '=' in item:
                key, value = item.split('=', 1)
            if value == 'vm_private_key.pub':
                new_working = working.replace(value, self.public_key)
        self.sed_file = join(gettempdir(), 'sed_file')
        self.property_file = join(gettempdir(), 'property_file')
        self.working_cfg = join(gettempdir(), 'enminst_working.cfg')
        self.xml_file = join(gettempdir(), 'xml_template')
        self.write_file(self.sed_file, sed)
        self.write_file(self.property_file, property_file_content)
        self.write_file(self.working_cfg, new_working)
        self.write_file(self.xml_file, self.xml_template)
        self.write_file(self.public_key, vm_public_key)
        environ['ENMINST_RUNTIME'] = gettempdir()
        os.environ['ENMINST_CONF'] = join(basepath, 'src/main/resources/conf')

    def tearDown(self):
        del os.environ['ENMINST_RUNTIME']
        try:
            remove(self.sed_file)
            remove(self.working_cfg)
            remove(self.xml_file)
            remove(self.public_key)
        except OSError as why:
            print why

    def test_build_full_file(self):
        subber = Substituter()
        subber.enminst_working = self.working_cfg
        subber.build_full_file(self.sed_file)
        subber.build_full_file(self.sed_file, self.property_file)
        self.assertIn('ENMservices_subnet', subber.full_parameter_list)
        self.assertIn('vm_ssh_key', subber.full_parameter_list)
        self.assertIn('uuid_bootvg_DB1', subber.full_parameter_list)
        self.assertIn('com_inf_ldap_admin_access_password_encrypted', subber.full_parameter_list)
        self.assertNotIn('#', subber.full_parameter_list)

    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    def test_write_xml(self):
        subber = Substituter()
        try:
            subber.write_file('asdasd')
            with open(subber.output_xml, 'r') as _f:
                self.assertEqual('asdasd', _f.readline())
        finally:
            remove(subber.output_xml)

    def test_replace_values(self):
        subber = Substituter()
        subber.full_parameter_list = self.param
        xml_populated = subber.replace_values(self.xml)
        self.assertNotIn('%%', xml_populated)

    def test_build_param_file_throws_exception(self):
        subber = Substituter()
        self.assertRaises(IOError, subber.build_param_file, 'non-existent')

    def test_build_param_file(self):
        subber = Substituter()
        subber.build_param_file(self.sed_file)
        self.assertNotIn('#', self.sed_file)
        self.assertEqual(len(subber.full_parameter_list), 16)
        back_to_string = ''
        for key, value in subber.full_parameter_list.iteritems():
            back_to_string += '{0}={1} \n'.format(key, value)
        for line in self.sed.split('\n'):
            if not line.startswith('#') and not len(line) == 0 \
                    and not line.endswith('=') and '=' in line:
                self.assertTrue(line in back_to_string, 'Not the same {0}'.
                                format(line))

    def test_read_xml_file_throws_exception(self):
        subber = Substituter()
        self.assertRaises(IOError, subber.read_file, 'non-existent')

    def test_read_xml_file(self):
        subber = Substituter()
        tfile = join(gettempdir(), 'bla')
        try:
            self.write_file(tfile, 'blaaa')
            stuff = subber.read_file(tfile)
            self.assertTrue('blaaa' in stuff)
        finally:
            remove(tfile)

    def test_verify_xml(self):
        subber = Substituter()
        subber.full_parameter_list = self.param
        _xml = subber.replace_values(self.xml)
        outstanding = subber.verify_xml(_xml)
        self.assertEqual(len(outstanding), 0)
        missing_xml = '''
                <litp:alias id="svc-3_alias">
                <address>%%svc_node3_IP%%</address>
                <address>%%svc_node3_IP%%</address>
                <alias_names>svc-3</alias_names>
                <value>%%sparkWorker5_1_ip_internal%%,%%svc_node3_IP%%,%%sparkWorker5_3_ip_internal%%,%%sparkWorker5_4_ip_internal%%,%%sparkWorker5_5_ip_internal%%,%%sparkWorker5_6_ip_internal%%</value>
                </litp:alias>'''
        xml_incomplete = subber.replace_values(missing_xml)
        self.assertRaises(SystemExit, subber.verify_xml, xml_incomplete)

    def test_main_no_args(self):
        self.assertRaises(SystemExit, main, [])

    def test_main_one_args(self):
        self.assertRaises(SystemExit, main, ['--xml_template= some_file'])

    @patch('substitute_parameters.Substituter')
    def test_main(self, sub):
        main(['substitute_parameters.py', '--xml_template',
              self.xml_file, '--sed', self.sed_file])
        self.assertTrue(sub.return_value.build_full_file.called,
                        'Expected a call to enable LITP debug!')
        self.assertTrue(sub.return_value.replace_values.called,
                        'Expected a call to enable LITP debug!')
        self.assertTrue(sub.return_value.verify_xml.called,
                        'Expected a call to enable LITP debug!')
        self.assertTrue(sub.return_value.write_file.called,
                        'Expected a call to enable LITP debug!')

    @patch('substitute_parameters.ArgumentParser')
    @patch('substitute_parameters.substitute')
    def test_KeyboardInterrupt_handling(self, sub, ap):
        sub.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main_exceptions(main, [])
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        sub.reset_mock()
        sub.side_effect = IOError()
        self.assertRaises(IOError, main_exceptions, main, [])

    def test_build_param_file_filecontents(self):
        test_cfg = join(gettempdir(), 'test.cfg')
        content_file = join(gettempdir(), 'test.txt')
        try:
            with open(content_file, 'w') as _writer:
                _writer.write('contents')

            with open(test_cfg, 'w') as _writer:
                _writer.write('somekey=file://{0}'.format(content_file))

            subber = Substituter()
            subber.build_param_file(test_cfg)
            self.assertEqual('contents', subber.full_parameter_list['somekey'])
        finally:
            os.remove(test_cfg)
            os.remove(content_file)


if __name__ == '__main__':
    unittest2.main()
