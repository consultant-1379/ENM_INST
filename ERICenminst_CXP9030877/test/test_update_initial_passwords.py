import unittest2

from update_initial_passwords import set_credentials, get_peer_nodes
from mock import patch


class TestSetInitialCredentials(unittest2.TestCase):

    @patch('logging.Logger.info')
    @patch('update_initial_passwords.EnminstAgent.update_initial_credentials')
    def test_set_credentials_nodes_updated(self, m_update_cred, m_info):
        update_success = {
            'cloud-svc-2': (u'Changing password for user root.\npasswd: all '
                            ' authentication tokens updated successfully.'),
            'cloud-svc-3': (u'Changing password for user root.\npasswd: all '
                            'authentication tokens updated successfully.')
        }

        m_update_cred.return_value = update_success
        nodes = ['cloud-svc-2', 'cloud-svc-3']
        set_credentials(nodes, 'foo', 'bar')

        m_info.assert_called_with(
            'Credentials set successfully for user "foo" on peer nodes')

    @patch('logging.Logger.info')
    @patch('update_initial_passwords.EnminstAgent.update_initial_credentials')
    def test_set_credentials_nodes_not_updated(self, m_update_cred, m_info):

        update_failed = {'cloud-svc-2': u'', 'cloud-svc-3': u''}

        m_update_cred.return_value = update_failed
        nodes = ['cloud-svc-2', 'cloud-svc-3']
        set_credentials(nodes, 'foo', 'bar')

        m_info.assert_called_with(('Unable to set new credentials for '
                                   'user "foo" on node "cloud-svc-3", '
                                   'please update manually.'))

    @patch('update_initial_passwords.set_credentials')
    @patch('update_initial_passwords.get_peer_nodes')
    def test_main_no_peer_nodes(self, m_peer_nodes, m_update_cred):
        m_peer_nodes.side_effect = [[]]
        m_update_cred.assert_has_no_calls([])

    @patch('logging.Logger.info')
    @patch('update_initial_passwords.discover_peer_nodes')
    def test_get_peer_nodes(self, m_peer_nodes, m_info):
        m_peer_nodes.side_effect = [['node1', 'node2', 'node3']]
        m_peer_nodes.assert_called()

        self.assertEquals(get_peer_nodes(),
                          ['node1', 'node2', 'node3'])
        m_info.assert_called_with(
            'Peer nodes found: "node1", "node2", "node3"')

        m_peer_nodes.side_effect = [[]]
        m_peer_nodes.assert_called()

        self.assertEquals(get_peer_nodes(), None)
        m_info.assert_called_with('No Peer nodes found.')


if __name__ == '__main__':
    unittest2.main()
