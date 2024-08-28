from mock import patch, Mock
import unittest2
from os.path import abspath, join
from os.path import dirname
from h_snapshots.snapshots_utils import NavisecCLI, SanApiException
from h_litp.litp_rest_client import  LitpException
import h_snapshots.snapshots_utils


def get_navi_template_xml(xml_file):
    lun_data_dir = join(dirname(abspath(__file__)), 'test_data')
    with open(join(lun_data_dir, xml_file)) as _f:
        return '\n'.join(_f.readlines())


def mock_list_luns_xml(luns):
    container = get_navi_template_xml('lun_container.xml')
    template_lun = get_navi_template_xml('lun.xml')
    insert_xml = ''
    for luninfo in luns:
        insert_xml += template_lun
        insert_xml = insert_xml.replace('@LUNID@', luninfo[0])
        insert_xml = insert_xml.replace('@NAME@', luninfo[1])
        insert_xml = insert_xml.replace('@POOL@', luninfo[2])

    return container.replace('@mocked_xml@', insert_xml)


class TestSnapshotsUtils(unittest2.TestCase):
    @patch('h_snapshots.snapshots_utils.api_builder')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def setUp(self, litp, litp_header, mock_api_builder):
        header = {
            'Authorization': 'Basic ' + "litp-admin:passwd"
        }
        litp_header.return_value = header
        litp.return_value = {'properties': {'key': 'enm_deployment_type',
                                                             'value': 'Extra_Large_ENM_O_Rack_Servers'}}
        self.san_cred = {'san_login_scope': 'global',
                         'san_user': 'admin',
                         'san_spb_ip': '10.32.236.189',
                         'san_spa_ip': '10.32.236.188',
                         'san_psw': 'passw0rd',
                         'san_pool': 'Fargo9',
                         'san_type': 'vnx2'}
        mock_api_builder.return_value = Mock()
        self.cli = NavisecCLI(self.san_cred)

    def test_no_creds(self):
        self.assertRaises(SanApiException, NavisecCLI, None, None)

    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_rack_get_default_config(self,  litp, litp_header):
        header = {
            'Authorization': 'Basic litp-admin:password'
        }
        litp_header.return_value = header
        litp.return_value = {'properties': {'key': 'enm_deployment_type',
                                            'value': 'Extra_Large_ENM_On_Rack_Servers'}}
        def_config = h_snapshots.snapshots_utils.get_default_config()
        self.assertIn("neo4j_1,neo4j_2,neo4j_3", def_config)

    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_default_config(self,  litp, litp_header):
        header = {
            'Authorization': 'Basic  litp-admin:password'
        }
        litp_header.return_value = header
        litp.return_value = {'properties': {'key': 'enm_deployment_type',
                                            'value': 'Extra_Large_ENM_X_Servers'}}
        def_config = h_snapshots.snapshots_utils.get_default_config()
        self.assertIn("neo4j_2,neo4j_3,neo4j_4", def_config)

    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_fault_get_default_config(self,  litp, litp_header):
        header = {
            'Authorization': 'Basic  litp-admin:password'
        }
        litp_header.return_value = header
        litp.side_effect = LitpException()
        def_config = h_snapshots.snapshots_utils.get_default_config()
        self.assertRaises(LitpException)
        self.assertIn("neo4j_2,neo4j_3,neo4j_4", def_config)

    def test_init(self):
        ips = (self.san_cred['san_spa_ip'], self.san_cred['san_spa_ip'])
        user = self.san_cred['san_user']
        passwd = self.san_cred['san_psw']
        scope = self.san_cred['san_login_scope']
        self.cli.san_api.initialise.called_with(ips, user, passwd, scope, True, False)

    def test_storage_pool_list(self):
        pool = 'TestPoolName'
        self.cli.storage_pool_list(pool)
        self.cli.san_api.get_luns.assert_called_with('StoragePool', pool)

    def test_get_storagepool_info(self):
        pool = 'pool1'
        self.cli.get_storagepool_info(pool)
        self.cli.san_api.get_storage_pool.assert_called_with(pool)

    def test_list_all_luns(self, storage_pool=None):
        pool = 'pool2'
        self.cli.list_all_luns(pool)
        self.cli.san_api.get_luns.assert_called_with('StoragePool', pool)

    def test_list_all_snaps(self):
        self.cli.list_all_snaps()
        self.cli.san_api.get_snapshots.assert_called_with()

    def test_snap_create(self):
        lun_id = '1'
        lun_name = 'lun1'
        description = 'CI VnxSnap'
        name = 'snap1'

        self.cli.snap_create(lun_id, name)
        self.cli.san_api.create_snapshot_with_id.assert_called_with(lun_id,
                                                                    name,
                                                                    description=description)

    def test_snap_destroy(self):
        snap_id = 'blah'
        self.cli.snap_destroy(snap_id)
        self.cli.san_api.delete_snapshot.assert_called_with(snap_id)

    def test_snap_restore(self):
        lun_id = '1'
        snap_name = 'snap1'
        bkup_name = 'enm_upgrade_bkup_%s' % lun_id

        self.cli.snap_restore(lun_id, snap_name)
        self.cli.san_api.restore_snapshot_by_id.assert_called_with(lun_id, snap_name,
                                                              delete_backupsnap=False,
                                                              backup_name=bkup_name)

    def test_delete_lun_with_snap(self):
        lun_id = '12'
        specific_options = "-destroySnapshots -forceDetach"
        self.cli.delete_lun_with_snap(None, lun_id)
        self.cli.san_api.delete_lun.assert_called_with(None, lun_id,
                                                       array_specific_options=specific_options)

    def test_get_storagegroup_info(self):
        sgroup_name = 'ENM336-enm-db_cluster-db-1'
        self.cli.get_storagegroup_info(sgroup_name)
        self.cli.san_api.get_storage_group.assert_called_with(sg_name=sgroup_name)

    def test_remove_luns_from_storage_group(self):
        sgroup_name = 'ENM336-enm-db_cluster-db-1'
        hlu = '4'
        self.cli.remove_luns_from_storage_group(sg_name=sgroup_name, hlus=hlu)
        self.cli.san_api.remove_luns_from_storage_group.assert_called_with(
            sg_name=sgroup_name, hlus=hlu)



if __name__ == '__main__':
    unittest2.main()
