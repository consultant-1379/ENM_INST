from mock import patch, call
from unittest2 import TestCase

from h_litp.sed_password_encrypter import main, set_key_nodes, set_key_sfs, \
    set_key_san, set_key_ndmp, litpcrypt_set
from h_util.h_utils import Sed


class TestPasswordEncrypter(TestCase):
    def mock_sed(self, seddata):
        with patch('h_litp.sed_password_encrypter.Sed._load'):
            sed = Sed('mock')
        sed.sed = seddata
        return sed

    def _mock_node_data(self, data, node_type, node_index):
        data['{0}_node{1}_hostname'.format(node_type, node_index)] = \
            '{0}n{1}'.format(node_type, node_index)
        data['{0}_node{1}_iloUsername'.format(node_type, node_index)] = 'u'
        data['{0}_node{1}_iloPassword'.format(node_type, node_index)] = 'p'
        return call(['/usr/bin/litpcrypt', 'set',
                     'key-for-{0}_node{1}_ilo'.format(node_type, node_index),
                     'u', 'p'])

    def setup_mocks(self, db_nodes, svc_nodes, scp_nodes):
        sed_data = {}
        ecalls = []
        for dbindex in range(1, db_nodes + 1):
            ecalls.append(self._mock_node_data(sed_data, 'db', dbindex))

        for svcindex in range(1, svc_nodes + 1):
            ecalls.append(self._mock_node_data(sed_data, 'svc', svcindex))

        for scpindex in range(1, scp_nodes + 1):
            ecalls.append(self._mock_node_data(sed_data, 'scp', scpindex))

        sed = self.mock_sed(sed_data)
        return sed, ecalls

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes_2db_2svc(self, ep):
        sed, expected_calls = self.setup_mocks(2, 2, 0)
        set_key_nodes(sed)
        self.assertEqual(4, ep.call_count)
        ep.assert_has_calls(expected_calls, any_order=True)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes_2db_4svc(self, ep):
        sed, expected_calls = self.setup_mocks(2, 4, 0)
        set_key_nodes(sed)
        self.assertEqual(6, ep.call_count)
        ep.assert_has_calls(expected_calls, any_order=True)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes_2db_empty_scp(self, ep):
        sed, expected_calls = self.setup_mocks(2, 2, 0)
        sed.sed['scp_node1_hostname'] = ''
        set_key_nodes(sed)
        self.assertEqual(4, ep.call_count)
        ep.assert_has_calls(expected_calls, any_order=True)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes_2db_2svc_2scp(self, ep):
        sed, expected_calls = self.setup_mocks(2, 2, 2)
        set_key_nodes(sed)
        self.assertEqual(6, ep.call_count)
        ep.assert_has_calls(expected_calls, any_order=True)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes_2db_4svc_4scp(self, ep):
        sed, expected_calls = self.setup_mocks(2, 4, 4)
        set_key_nodes(sed)
        self.assertEqual(10, ep.call_count)
        ep.assert_has_calls(expected_calls, any_order=True)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes_4db_10svc_4scp(self, ep):
        sed, expected_calls = self.setup_mocks(4, 10, 4)
        set_key_nodes(sed)
        self.assertEqual(18, ep.call_count)
        ep.assert_has_calls(expected_calls, any_order=True)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_nodes(self, m_exec_process):
        with self.assertRaises(ValueError) as error:
            set_key_nodes(
                self.mock_sed({
                    'db_node1_iloUsername': 'u',
                    'db_node1_iloPassword': None,
                    'db_node1_hostname': 'dbn1',
                    'db_node2_iloUsername': None,
                    'db_node2_iloPassword': 'p',
                    'db_node2_hostname': 'dbn1'})
            )
        self.assertTrue('db_node1_iloPassword' in error.exception.args[0])
        self.assertTrue('db_node2_iloUsername' in error.exception.args[0])

        self.assertRaises(ValueError, set_key_nodes,
                          self.mock_sed({
                              'db_node1_iloUsername': None,
                              'db_node1_iloPassword': 'p',
                              'db_node1_hostname': 'dbn1'}))

        self.assertRaises(ValueError, set_key_nodes,
                          self.mock_sed({
                              'db_node1_iloUsername': 'u',
                              'db_node1_iloPassword': None,
                              'db_node1_hostname': 'dbn1'}))

        # If the hostname isnt set then the litpcrypt call is not made.
        set_key_nodes(self.mock_sed({
            'db_node1_iloUsername': 'u',
            'db_node1_iloPassword': 'p',
            'db_node1_hostname': None}))
        self.assertFalse(m_exec_process.call_count)

        m_exec_process.reset_mock()
        set_key_nodes(self.mock_sed({
            'db_node1_iloUsername': 'u',
            'db_node1_iloPassword': 'p',
            'db_node1_hostname': 'dbn2'}))
        m_exec_process.assert_has_call(call(
            ['/usr/bin/litpcrypt', 'set', 'key-for-db_node1_ilo', 'u', 'p']))

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_sfs(self, ep):
        sed = self.mock_sed({
            'sfssetup_username': 'u',
            'sfssetup_password': 'p'
        })
        set_key_sfs(sed)
        self.assertEqual(1, ep.call_count)
        ep.assert_has_call(
            call(['/usr/bin/litpcrypt', 'set', 'key-for-sfs', 'u', 'p'])
        )

        sed = self.mock_sed({
            'sfssetup_username': None,
            'sfssetup_password': 'p'
        })
        self.assertRaises(ValueError, set_key_sfs, sed)

        sed = self.mock_sed({
            'sfssetup_username': 'u',
            'sfssetup_password': None
        })
        self.assertRaises(ValueError, set_key_sfs, sed)

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_ndmp(self, ep):
        sed = self.mock_sed({
            'nas_type': 'unityxt',
            'nas_ndmp_password': 'p'
        })
        set_key_ndmp(sed)
        self.assertEqual(1, ep.call_count)
        ep.assert_has_call(
            call(['/usr/bin/litpcrypt', 'set', 'key-for-ndmp', 'ndmp', 'p'])
        )

        ep.reset_mock()
        sed = self.mock_sed({
            'nas_ndmp_password': 'p'
        })
        set_key_ndmp(sed)
        self.assertEqual(0, ep.call_count)

        sed = self.mock_sed({
            'nas_type': 'veritas',
            'nas_ndmp_password': 'p'
        })
        set_key_ndmp(sed)
        self.assertEqual(0, ep.call_count)

        sed = self.mock_sed({
            'nas_type': 'unityxt',
            'nas_ndmp_password': None
        })
        try:
            set_key_ndmp(sed)
        except ValueError as ve:
            self.assertTrue("No value for key 'nas_ndmp_password' found" in str(ve))

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_set_key_san(self, ep):
        sed = self.mock_sed({
            'san_user': 'u',
            'san_password': 'p',
            'san_systemName': 'atcx123'
        })
        set_key_san(sed)
        ep.assert_has_call(call(['/usr/bin/litpcrypt', 'set',
                                 'key-for-san-atcx123', 'u', 'p']))

        sed = self.mock_sed({
            'san_user': 'u',
            'san_password': 'p',
            'san_systemName': None
        })
        self.assertRaises(ValueError, set_key_san, sed)

        sed = self.mock_sed({
            'san_user': 'u',
            'san_password': None,
            'san_systemName': 'u'
        })
        self.assertRaises(ValueError, set_key_san, sed)

        sed = self.mock_sed({
            'san_user': None,
            'san_password': 'p',
            'san_systemName': 'u'
        })
        self.assertRaises(ValueError, set_key_san, sed)

    @patch('h_litp.sed_password_encrypter.set_key_sfs')
    @patch('h_litp.sed_password_encrypter.set_key_ndmp')
    @patch('h_litp.sed_password_encrypter.set_key_nodes')
    @patch('h_litp.sed_password_encrypter.set_key_san')
    @patch('h_litp.sed_password_encrypter.Sed')
    def test_main(self, m_sed, m_set_key_san, m_set_key_nodes, m_set_key_ndmp, m_set_key_sfs):
        self.assertRaises(SystemExit, main, [])

        main(['--sed', 'bbbb', '--type', 'blade'])
        self.assertTrue(m_set_key_nodes.called,
                        msg='No call to set_key_nodes made!')
        self.assertTrue(m_set_key_ndmp.called,
                        msg='No call to set_key_ndmp made!')
        self.assertTrue(m_set_key_sfs.called,
                        msg='No call to set_key_sfs made!')
        self.assertTrue(m_set_key_san.called,
                        msg='No call to set_key_san made!')

    @patch('h_litp.sed_password_encrypter.exec_process')
    def test_litpcrypt_set(self, ep):
        litpcrypt_set('key-for-sfs', 'root', 'password')
        ep.assert_called_with(['/usr/bin/litpcrypt', 'set', 'key-for-sfs', 'root', 'password'])
        litpcrypt_set('key-for-sfs', 'root', '$%pass&*()')
        ep.assert_called_with(['/usr/bin/litpcrypt', 'set', 'key-for-sfs', 'root', '$%pass&*()'])
