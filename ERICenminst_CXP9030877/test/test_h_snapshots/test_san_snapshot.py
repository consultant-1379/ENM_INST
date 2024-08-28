import unittest2
from mock import call, patch, Mock, MagicMock

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.nasexceptions'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

from h_litp.litp_rest_client import LitpObject
from h_snapshots.san_snapshot import VNXSnap, filter_luns
from h_snapshots.snapshots_utils import NavisecCLI, SanApiException
from h_vcs.vcs_cli import Vcs
from test_h_vcs.test_vcs_cli import CDATA_GP_AS_OK, CDATA_GP_PAR_OK
from test_utils import assert_exception_raised
#from sanapiexception import SanApiException
from sanapiinfo import SnapshotInfo, LunInfo
from sanapiinfo import StorageGroupInfo, HluAluPairInfo
from test_h_snapshots.test_litp_snapshots import litp_object


litp_header_value = { 'Authorization': 'Basic  litp-admin:password' }
litp_get_value = {'properties': {'key': 'enm_deployment_type',
                                    'value': 'Extra_Large_ENM_X_Servers'}}


class TestVNXSnap(unittest2.TestCase):
    @patch('h_snapshots.snapshots_utils.api_builder')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def setUp(self, litp, litp_header, mock_api_builder):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        self.poolname = 'Fargo9'
        self.san_cred = {'san_login_scope': 'global',
                         'san_user': 'admin',
                         'san_spb_ip': '10.32.236.189',
                         'san_spa_ip': '10.32.236.188',
                         'san_psw': 'passw0rd',
                         'san_pool': self.poolname,
                         'san_type': 'vnx2'}
        self.snap_prefix = 'Snapshot'
        self.lun_disks_dummy = {'LUN_{0}_mysql'.format(self.poolname):
                                    "/deployments/d/clusters/c/nodes/n1/system/"
                                    "disks/d1 [item-type:lun-disk state:Applied] "
                                    "properties{'lun_name': "
                                    "'LITP2_ENM223_snappable', "
                                    "'storage_container': 'ENM223', "
                                    "'snap_size': '100'"}
        mock_api_builder.return_value = Mock()

    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_lunids_for_snap(self, litp, litp_header, list_luns, litp_san):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        mysql_lun_name = 'LUN_{0}_mysql'.format(self.poolname)
        versant_lun_name = 'LUN_{0}_versant'.format(self.poolname)
        sfs_lun_name = '{0}_SFS'.format(self.poolname)
        elasticsearch_lun_name = 'LUN_{0}_elasticsearchdb'.format(self.poolname)

        mysql_lun = LunInfo(lun_id='73',
                           name=mysql_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        versant_lun = LunInfo(lun_id='4444',
                           name=versant_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        sfs_lun = LunInfo(lun_id='22',
                           name=sfs_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        elasticsearch_lun = LunInfo(lun_id='33',
                           name=elasticsearch_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        san_luns = [mysql_lun, versant_lun, sfs_lun, elasticsearch_lun]
        list_luns.return_value = san_luns

        lun_disks = {'LUN_{0}_versant'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_mysql'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)

        luns = san.get_snappable_luns()
        self.assertEqual(2, len(luns))
        self.assertIn('73', luns)
        self.assertIn('4444', luns)
        self.assertNotIn('22', luns)
        self.assertNotIn('33', luns)
        luns = san.get_snappable_luns(['4444'])
        self.assertEqual(1, len(luns))
        self.assertIn('4444', luns)
        self.assertNotIn('73', luns)

    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_exclude_luns(self, litp, litp_header, list_luns, litp_san):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        fen1_lun_name = 'LUN_{0}_fen1'.format(self.poolname)
        fen2_lun_name = 'LUN_{0}_fen2'.format(self.poolname)
        sfs_lun_name = '{0}_SFS'.format(self.poolname)
        elasticsearch_lun_name = 'LUN_{0}_elasticsearchdb'.format(self.poolname)
        app_db_lun_name = 'LUN_{0}_appdb1'.format(self.poolname)

        fen1_lun = LunInfo(lun_id='65',
                          name=fen1_lun_name,
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')

        fen2_lun = LunInfo(lun_id='63',
                          name=fen2_lun_name,
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')

        sfs_lun = LunInfo(lun_id='22',
                          name=sfs_lun_name,
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')

        elasticsearch_lun = LunInfo(lun_id='33',
                                    name=elasticsearch_lun_name,
                                    uid='sadasd',
                                    container=self.poolname,
                                    size='100Gb',
                                    container_type='StoragePool',
                                    raid='5')

        app_db_lun = LunInfo(lun_id='45',
                           name=app_db_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        san_luns = [fen1_lun, fen2_lun, sfs_lun, elasticsearch_lun, app_db_lun]
        list_luns.return_value = san_luns

        lun_disks = {'LUN_{0}_fen1'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_appdb1'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)
        luns = san.get_snappable_luns()
        self.assertEqual(2, len(luns))

        for _, lun in luns.iteritems():
            self.assertTrue('elasticsearch' not in lun.name)
            self.assertTrue('SFS' not in lun.name)

    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_lun_ids_for_dbs(self, litp, litp_header, list_luns, litp_san):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        mysql_lun_name = 'LUN_{0}_mysql'.format(self.poolname)
        versantdb_lun_name = 'LUN_{0}_versantdb'.format(self.poolname)
        versant_bur_lun_name = 'LUN_{0}_versant_bur'.format(self.poolname)
        versant_ap_lun_name = 'LUN_AP_versant'

        mysql_lun = LunInfo(lun_id='73',
                           name=mysql_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        versantdb_lun = LunInfo(lun_id='4444',
                           name=versantdb_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        versant_bur_lun = LunInfo(lun_id='444',
                           name=versant_bur_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        versant_ap_lun = LunInfo(lun_id='22',
                           name=versant_ap_lun_name,
                           uid='sadasd',
                           container='AP',
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        san_luns = [mysql_lun, versantdb_lun, versant_bur_lun, versant_ap_lun]
        list_luns.return_value = san_luns

        lun_disks = {'LUN_{0}_versantdb'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_mysql'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)
        luns = san.get_snappable_luns()
        dbluns = san._get_lun_ids_for_dbs(luns)
        self.assertIn('mysql', dbluns)
        self.assertIn('versantdb', dbluns)
        self.assertEqual('73', dbluns['mysql'])
        self.assertIn('versantdb', dbluns)
        self.assertEqual('4444', dbluns['versantdb'])

    @patch('h_snapshots.san_snapshot.VNXSnap._is_sg_exist')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_list_snapshots(self, litp, litp_header, list_snaps, list_luns, litp_san,
                            is_sg_exist):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        versant_lun_name = 'LUN_{0}_versant'.format(self.poolname)
        neo4j_lun_name = 'LUN_{0}_neo4j'.format(self.poolname)
        mysql_lun_name = 'LUN_{0}_mysql'.format(self.poolname)
        sfs_lun_name = '{0}_SFS'.format(self.poolname)

        mysql_lun = LunInfo(lun_id='74',
                           name=mysql_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        neo4j_lun = LunInfo(lun_id='73',
                            name=neo4j_lun_name,
                            uid='sadasd',
                            container=self.poolname,
                            size='100Gb',
                            container_type='StoragePool',
                            raid='5')

        versant_lun = LunInfo(lun_id='74',
                           name=versant_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        sfs_lun = LunInfo(lun_id='22',
                          name=sfs_lun_name,
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')

        san_luns = [mysql_lun, neo4j_lun, versant_lun, sfs_lun]
        list_luns.return_value = san_luns

        snap_info = SnapshotInfo(resource_lun_id='73',
                                 snapshot_name='Snapshot_73',
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name=neo4j_lun_name,
                                 description=None)

        list_snaps.return_value = [snap_info]

        lun_disks = {'LUN_{0}_versant'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_mysql'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_neo4j'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"
                     }

        litp_san.return_value.get_node_lundisks.return_value = lun_disks

        san = VNXSnap(self.san_cred, self.snap_prefix)
        is_sg_exist.return_value = True

        info_messages = []

        def info(message):
            print message
            info_messages.append(message)

        orig_log = san.logger.info
        san.logger.info = info

        sae = assert_exception_raised(SanApiException, san.list_snapshots,
                                      False, validating=True)
        self.assertTrue('Invalid LUN snapshots' in str(sae))
        info_lines = r'\cccn'.join(info_messages)
        self.assertIn('{0} has snapshot'.format(neo4j_lun_name), info_lines)
        san.logger.info = orig_log

    @patch('h_snapshots.san_snapshot.VNXSnap._is_sg_exist')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_list_restore_snapshots(self, litp, litp_header, list_snaps, list_luns, litp_san,
                                    is_sg_exist):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        versant_lun_name = 'LUN_{0}_versant'.format(self.poolname)
        mysql_lun_name = 'LUN_{0}_mysql'.format(self.poolname)
        neo4j_lun_name = 'LUN_{0}_neo4j'.format(self.poolname)
        sfs_lun_name = '{0}_SFS'.format(self.poolname)

        mysql_lun = LunInfo(lun_id='75',
                           name=mysql_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        neo4j_lun = LunInfo(lun_id='73',
                           name=neo4j_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        versant_lun = LunInfo(lun_id='74',
                           name=versant_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        sfs_lun = LunInfo(lun_id='22',
                          name=sfs_lun_name,
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')

        san_luns = [mysql_lun, neo4j_lun, versant_lun, sfs_lun]
        list_luns.return_value = san_luns

        mysql_snap = SnapshotInfo(resource_lun_id='75',
                                 snapshot_name='Snapshot_75',
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name=mysql_lun_name,
                                 description=None)

        neo4j_snap = SnapshotInfo(resource_lun_id='73',
                                  snapshot_name='Snapshot_73',
                                  created_time='just a moment ago',
                                  snap_state='Available',
                                  resource_lun_name=neo4j_lun_name,
                                  description=None)

        versant_snap = SnapshotInfo(resource_lun_id='74',
                                 snapshot_name='Snapshot_74',
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name=versant_lun_name,
                                 description=None)

        is_sg_exist.return_value = True
        list_snaps.return_value = [mysql_snap, neo4j_snap, versant_snap]

        san = VNXSnap(self.san_cred, self.snap_prefix)

        info_messages = []

        def info(message):
            print message
            info_messages.append(message)

        orig_log = san.logger.info
        san.logger.info = info

        snapshots = san.list_snapshots(False, ['73'])
        self.assertTrue(snapshots)
        infomessages = '\n'.join(info_messages)
        self.assertIn('{0} has snapshot'.format(neo4j_lun_name), infomessages)
        self.assertNotIn('{0} has snapshot'.format(mysql_lun_name), infomessages)
        self.assertNotIn('{0} has snapshot'.format(versant_lun_name), infomessages)
        san.logger.info = orig_log

    @patch('h_snapshots.san_snapshot.VNXSnap._is_sg_exist')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_list_unknown_snapshots(self, litp, litp_header, list_snaps, list_luns, litp_san,
                                    is_sg_exist):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        neo4j_lun_name = 'LUN_{0}_neo4j'.format(self.poolname)
        versant_lun_name = 'LUN_{0}_versant'.format(self.poolname)
        mysql_lun_name = 'LUN_{0}_mysql'.format(self.poolname)
        sfs_lun_name = '{0}_SFS'.format(self.poolname)

        neo4j_lun = LunInfo(lun_id='73',
                            name=neo4j_lun_name,
                            uid='sadasd',
                            container=self.poolname,
                            size='100Gb',
                            container_type='StoragePool',
                            raid='5')

        mysql_lun = LunInfo(lun_id='73',
                           name=mysql_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        versant_lun = LunInfo(lun_id='74',
                           name=versant_lun_name,
                           uid='sadasd',
                           container=self.poolname,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        sfs_lun = LunInfo(lun_id='22',
                          name=sfs_lun_name,
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')

        san_luns = [neo4j_lun, mysql_lun, versant_lun, sfs_lun]
        list_luns.return_value = san_luns

        neo4j_snap = SnapshotInfo(resource_lun_id='73',
                                  snapshot_name='somesnap_73',
                                  created_time='just a moment ago',
                                  snap_state='Available',
                                  resource_lun_name=neo4j_lun_name,
                                  description=None)

        mysql_snap = SnapshotInfo(resource_lun_id='73',
                                 snapshot_name='somesnap_73',
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name=mysql_lun_name,
                                 description=None)

        versant_snap = SnapshotInfo(resource_lun_id='74',
                                 snapshot_name='somesnap_74',
                                 created_time='just a moment ago',
                                 snap_state='Available',
                                 resource_lun_name=versant_lun_name,
                                 description=None)

        list_snaps.return_value = [neo4j_snap, mysql_snap, versant_snap]

        lun_disks = {'LUN_{0}_versant'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_neo4j'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_mysql'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        is_sg_exist.return_value = True
        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)

        info_messages = []

        def info(message):
            print message
            info_messages.append(message)

        orig_log = san.logger.info
        san.logger.info = info

        with self.assertRaises(SanApiException) as sae:
            san.list_snapshots(False, validating=True)
        self.assertTrue('Invalid LUN snapshots' in str(sae.exception))
        info_lines = '\n'.join(info_messages)
        self.assertIn('No LUN snapshots found on the system', info_lines)
        san.logger.info = orig_log


    @patch('h_snapshots.snap_agent.SnapAgents.backup_opendj')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_opendj_nodes')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_opendj_backup(self, litp, litp_header, litp_san, get_opendj_nodes, backup_opendj):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        node_list = ['node_1', 'node_2']
        get_opendj_nodes.return_value = node_list
        san = VNXSnap(self.san_cred, self.snap_prefix)
        san._opendj_backup()
        backup_opendj.assert_called_with(node_list,
                                         san.opendj_backup_cmd,
                                         san.opendj_backup_dir,
                                         san.opendj_log_dir)

    @patch('h_vcs.vcs_cli.Vcs.is_sg_persistently_frozen')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_opendj_luns')
    @patch('h_snapshots.san_snapshot.sleep')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    @patch('h_snapshots.san_snapshot.Vcs.node_name_to_vcs_system')
    @patch('h_snapshots.san_snapshot.SnapAgents.backup_opendj')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_opendj_nodes')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_neo4j_nodes')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_active_versant_node')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_active_mysql_node')
    @patch('h_snapshots.snap_agent.SnapAgents.create_mysql_snapshot')
    @patch('h_snapshots.snap_agent.SnapAgents.create_versant_snapshot')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.snap_create')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.is_dps_using_neo4j')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_create_snapshots(self, litp, litp_header, is_dps_using_neo4j, litp_san, snap_create, list_luns,
                              m_create_versant_snapshot,
                              m_create_mysql_snapshot,
                              m_get_active_mysql_node,
                              m_get_active_versant_node,
                              m_get_neo4j_nodes,
                              m_get_opendj_nodes,
                              m_backup_opendj,
                              m_node_name_to_vcs_system,
                              m_hagrp_online,
                              m_hagrp_offline,
                              m_sleep,
                              m_get_opendj_luns,
                              m_vcs_is_sg_frozen):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        is_dps_using_neo4j.return_value = False
        m_vcs_is_sg_frozen.return_value = True
        m_node_name_to_vcs_system.return_value = 'system'
        m_get_opendj_luns.return_value = {'LUN_{0}_bootdb2'.format(self.poolname):"db-2"}

        versant_lunid = '73'
        neo4j_1_lunid = '13'
        neo4j_2_lunid = '19'
        neo4j_3_lunid = '22'
        neo4j_4_lunid = '25'
        mysql_lunid = '74'
        postgres_lunid = '14'
        node_lunid = '33'
        bootdb2_lunid = '85'
        sfs_lun_id = '23'

        lun_ids_names = {
            versant_lunid: 'LUN_{0}_versantdb',
            neo4j_1_lunid: 'LUN_{0}_neo4j_1',
            neo4j_2_lunid: 'LUN_{0}_neo4j_2',
            neo4j_3_lunid: 'LUN_{0}_neo4j_3',
            neo4j_4_lunid: 'LUN_{0}_neo4j_4',
            mysql_lunid: 'LUN_{0}_mysql',
            postgres_lunid: 'LUN_{0}_postgresdb',
            bootdb2_lunid: 'LUN_{0}_bootdb2',
            sfs_lun_id: '{0}_SFS',
            node_lunid: 'Applun_{0}_app1'
        }

        san_luns = []
        for lun_id, lun_name in lun_ids_names.items():
            lun = LunInfo(lun_id=lun_id,
                          name=lun_name.format(self.poolname),
                          uid='sadasd',
                          container=self.poolname,
                          size='100Gb',
                          container_type='StoragePool',
                          raid='5')
            san_luns.append(lun)

        list_luns.return_value = san_luns

        snap_ids_names = {
            versant_lunid: 'Snapshot_%s' % versant_lunid,
            neo4j_1_lunid: 'Snapshot_%s' % neo4j_1_lunid,
            neo4j_2_lunid: 'Snapshot_%s' % neo4j_2_lunid,
            neo4j_3_lunid: 'Snapshot_%s' % neo4j_3_lunid,
            neo4j_4_lunid: 'Snapshot_%s' % neo4j_4_lunid,
            mysql_lunid: 'Snapshot_%s' % mysql_lunid,
            postgres_lunid: 'Snapshot_%s' % postgres_lunid,
            bootdb2_lunid: 'Snapshot_%s' % bootdb2_lunid,
            node_lunid: 'Snapshot_%s' % node_lunid,
        }

        lun_disks = {'LUN_{0}_versantdb'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_neo4j_1'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_neo4j_2'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_neo4j_3'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_neo4j_4'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_mysql'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_postgresdb'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_bootdb2'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_app1'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        m_get_active_mysql_node.return_value = 'mysql_node'
        m_get_active_versant_node.return_value = 'versant_node'

        litp_san.return_value.get_node_lundisks.return_value = lun_disks

        m_get_opendj_nodes.return_value = ['db-1', 'db-2']
        m_get_neo4j_nodes.return_value = ([], [], False)

        san = VNXSnap(self.san_cred, self.snap_prefix)
        san.create_snapshots()

        (call(self.poolname))
        list_luns.assert_has_calls([call(self.poolname)], any_order=True)

        expected_snap_calls = []
        for lun_id, snap_name in snap_ids_names.items():
            if lun_id not in [mysql_lunid, versant_lunid]:
                expected_snap_calls.append(call(lun_id, snap_name))

        snap_create.assert_has_calls(expected_snap_calls, any_order=True)

        m_create_versant_snapshot.assert_called_with('versant',
                                                     versant_lunid,
                                                     'vnx2',
                                                     '10.32.236.188',
                                                     '10.32.236.189',
                                                     'versant_node',
                                                     'admin',
                                                     'passw0rd',
                                                     'global',
                                                     'Snapshot',
                                                     'ENM_Upgrade_Snapshot')

        m_create_mysql_snapshot.assert_called_with('mysql',
                                                   mysql_lunid,
                                                   'vnx2',
                                                   '10.32.236.188',
                                                   '10.32.236.189',
                                                   'mysql_node',
                                                   'admin', 'passw0rd',
                                                   'global',
                                                   'Snapshot',
                                                   'ENM_Upgrade_Snapshot',
                                                   'root')
        m_backup_opendj.assert_called_with(
            m_get_opendj_nodes.return_value,
            san.opendj_backup_cmd,
            san.opendj_backup_dir,
            san.opendj_log_dir
        )

        m_hagrp_online.assert_called_with(".*opendj_clustered_service",
                                  "system",
                                  Vcs.ENM_DB_CLUSTER_NAME,
                                  -1
        )

        m_hagrp_offline.assert_called_with(".*opendj_clustered_service",
                                  "system",
                                  Vcs.ENM_DB_CLUSTER_NAME,
                                  -1
        )

    def setup_get_cluster_group_status(self,
                                       cluster_name,
                                       vcs_group_name,
                                       vcs_group_data,
                                       m_get_modeled_groups,
                                       m_get_hostname_vcs_aliases,
                                       m_get_modeled_group_types,
                                       m_get_vcs_group_info,
                                       m_discover_peer_nodes):
        vcs_name = cluster_name + '_' + vcs_group_name

        mock_object = LitpObject(None, {}, None)
        mock_object._id = vcs_group_name
        mock_object._properties = {'node_list': 'svc-1,svc-2'}

        m_get_modeled_groups.return_value = (
            {},
            {cluster_name: {vcs_name: mock_object}}
        )
        m_get_hostname_vcs_aliases.return_value = (
            {'atrcxb1': 'svc-1', 'atrcbx2': 'svc-2'},
            {'svc-1': 'atrcxb1', 'svc-2': 'atrcxb2'}
        )
        m_discover_peer_nodes.return_value = ['atrcxb1', 'atrcxb2']
        m_get_modeled_group_types.return_value = {
            vcs_group_name: {'type': 'vm', 'node_list': ['svc-1', 'svc-2']}}

        m_get_vcs_group_info.return_value = {vcs_name: vcs_group_data}


    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_active_versant_node(self, litp, litp_header, litp_san,
                                     m_get_modeled_groups,
                                     m_get_hostname_vcs_aliases,
                                     m_get_modeled_group_types,
                                     m_get_vcs_group_info,
                                     m_discover_peer_nodes):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        gp_name = 'Grp_CS_db_cluster_versant_clustered_service'
        self.setup_get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                            gp_name,
                                            CDATA_GP_AS_OK,
                                            m_get_modeled_groups,
                                            m_get_hostname_vcs_aliases,
                                            m_get_modeled_group_types,
                                            m_get_vcs_group_info,
                                            m_discover_peer_nodes)
        san = VNXSnap(self.san_cred, self.snap_prefix)
        active_node = san._get_active_versant_node()
        self.assertEqual('svc-1', active_node)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_active_versant_node_cm(self, litp, litp_header, litp_san,
                                        m_get_modeled_groups,
                                        m_get_hostname_vcs_aliases,
                                        m_get_modeled_group_types,
                                        m_get_vcs_group_info,
                                        discover_peer_nodes):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        gp_name = 'Grp_CS_db_cluster_versant_clustered_service_CM'
        self.setup_get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                            gp_name,
                                            CDATA_GP_AS_OK,
                                            m_get_modeled_groups,
                                            m_get_hostname_vcs_aliases,
                                            m_get_modeled_group_types,
                                            m_get_vcs_group_info,
                                            discover_peer_nodes)
        san = VNXSnap(self.san_cred, self.snap_prefix)
        active_node = san._get_active_versant_node()
        self.assertEqual('svc-1', active_node)

    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    def test_sg_not_exist(self, cluster_group_status):
        cluster_group_status.return_value = None, None
        self.assertEqual(VNXSnap._is_sg_exist('sg_name'), False)

    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    def test_sg_exist(self, cluster_group_status):
        cluster_group_status.return_value = "Text Output", None
        self.assertEqual(VNXSnap._is_sg_exist('sg_name'), True)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_active_mysql_node(self, litp, litp_header, litp_san,
                                   m_get_modeled_groups,
                                   m_get_hostname_vcs_aliases,
                                   m_get_modeled_group_types,
                                   m_get_vcs_group_info,
                                   m_discover_peer_nodes):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        gp_name = 'Grp_CS_db_cluster_mysql_clustered_service'
        self.setup_get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                            gp_name,
                                            CDATA_GP_AS_OK,
                                            m_get_modeled_groups,
                                            m_get_hostname_vcs_aliases,
                                            m_get_modeled_group_types,
                                            m_get_vcs_group_info,
                                            m_discover_peer_nodes)

        san = VNXSnap(self.san_cred, self.snap_prefix)
        active_node = san._get_active_mysql_node()
        self.assertEqual('svc-1', active_node)

    @patch('h_vcs.vcs_cli.discover_peer_nodes')
    @patch('h_vcs.vcs_cli.get_vcs_group_info')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_group_types')
    @patch('h_vcs.vcs_cli.Vcs._get_hostname_vcs_aliases')
    @patch('h_vcs.vcs_cli.Vcs._get_modeled_groups')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_opendj_nodes(self, litp, litp_header, litp_san,
                              m_get_modeled_groups,
                              m_get_hostname_vcs_aliases,
                              m_get_modeled_group_types,
                              m_get_vcs_group_info,
                              m_discover_peer_nodes):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        gp_name = 'Grp_CS_db_cluster_opendj_clustered_service'
        self.setup_get_cluster_group_status(Vcs.ENM_DB_CLUSTER_NAME,
                                            gp_name,
                                            CDATA_GP_PAR_OK,
                                            m_get_modeled_groups,
                                            m_get_hostname_vcs_aliases,
                                            m_get_modeled_group_types,
                                            m_get_vcs_group_info,
                                            m_discover_peer_nodes)
        san = VNXSnap(self.san_cred, self.snap_prefix)
        node_list = san._get_opendj_nodes()
        expected_node_list = ['svc-1', 'svc-2']
        self.assertEqual(node_list, expected_node_list)


    @patch('h_snapshots.san_snapshot.NavisecCLI.snap_destroy')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.san_snapshot.LitpRestClient.get_children')
    @patch('h_snapshots.san_snapshot.LitpRestClient.get_items_by_type')
    @patch('h_snapshots.snapshots_utils.NavisecCLI.delete_lun_with_snap')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_remove_snapshots(self, litp, litp_header, navi_delete_lun, litp_items_type, litp_get_children,
                              litp_san, list_snaps, list_luns, snap_destroy):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        infrastructure = [{'path':'/infrastructure/systems'}]
        disks = [{'path':'/infrastructure/systems/db-1_system/disks/versant_lun_disk0'}]
        litp_get_children.side_effect = [infrastructure, disks]
        litp_items_type.return_value = [{
            "path": "/infrastructure/systems/db-2_system/disks/mysql_lun_disk0",
            "data": {
                "id": u"mysql_lun_disk0",
                "item-type-name": u"lun-disk",
                "applied_properties_determinable": True,
                "state": u"Applied",
                "_links": {
                "self": {
                    "href": u"http://127.0.0.1/litp/rest/v1/infrastructure/systems/db-2_system/disks/mysql_lun_disk0"
                },
                "item-type": {
                    "href": u"http://127.0.0.1/litp/rest/v1/item-types/lun-disk"
                },
            },
            "properties": {
                "lun_name": u"LITP2_ENM326_mysqldb",
                "name": u"sde",
                "balancing_group": u"high",
                "external_snap": u"true",
                "bootable": u"false",
                "disk_part": u"false",
                "storage_container": u"ENM326",
                "shared": u"true",
                "snap_size": u"100",
                "size": u"20G",
                "uuid": u"600601601D703C000F2DEC0858AEEB11",
                },
            },
        }]

        lun1 = LunInfo(lun_id='11',
                       name='LUN_{0}_versant'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')
        san_luns = [lun1]
        list_luns.return_value = san_luns

        snap1 = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='Snapshot_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='LUN_{0}_versant'.format(self.poolname),
                             description=None)
        snap_info = [snap1]
        list_snaps.return_value = snap_info

        lun_disks = {'LUN_{0}_versant'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}
        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)
        san.remove_snapshots()

        snap_destroy.assert_has_calls([call("Snapshot_11")], any_order=True)
        navi_delete_lun.assert_not_called()

    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_validate_exception(self, litp, litp_header, litp_san, list_snaps, list_luns):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun1 = LunInfo(lun_id='11',
                       name='LUN_{0}_11'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        lun1 = LunInfo(lun_id='22',
                       name='LUN_{0}_22'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        san_luns = [lun1]
        list_luns.return_value = san_luns

        snap1 = SnapshotInfo(resource_lun_id='11',
                            snapshot_name='Snapshot_11',
                            created_time='just a moment ago',
                            snap_state='Available',
                            resource_lun_name='Lun_{0}_11'.format(self.poolname),
                            description=None)

        snap_info = [snap1]
        list_snaps.return_value = snap_info

        lun_disks = {'LUN_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        litp_san.return_value.get_node_lundisks.return_value = lun_disks

        san = VNXSnap(self.san_cred, self.snap_prefix)
        self.assertRaises(SanApiException, san.validate)

    @patch('h_snapshots.san_snapshot.VNXSnap._is_sg_exist')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_validate(self, litp, litp_header, litp_san, list_snaps, list_luns, is_sg_exist):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun1 = LunInfo(lun_id='11',
                       name='Lun_{0}_11'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        san_luns = [lun1]
        list_luns.return_value = san_luns

        snap11 = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='Snapshot_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Lun_{0}_11'.format(self.poolname),
                             description=None)
        snap_info = [snap11]
        list_snaps.return_value = snap_info

        lun_disks = {'LUN_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'LUN_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}
        is_sg_exist.return_value = True
        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)
        logged = []

        def m_log(st):
            logged.append(st)

        orig_log = san.logger.info
        san.logger.info = m_log

        try:
            san.validate()
            luns = san.get_snappable_luns().values()
            for lun in luns:
                self.assertRegexpMatches(''.join(logged),
                                         'LUN {0}.* has '
                                         'snapshot'.format(lun.lunid))
        except SanApiException:
            self.fail('san.validate() raised SanApiException unexpectedly!')
        finally:
            san.logger.info = orig_log

    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_restore_snapshots_multiple(self, litp, litp_header, litp_san, list_snaps, list_luns):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun1 = LunInfo(lun_id='11',
                       name='Applun_{0}_11'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        lun2 = LunInfo(lun_id='22',
                       name='Applun_{0}_22'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        san_luns = [lun1, lun2]
        list_luns.return_value = san_luns

        snap11 = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='Snapshot_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_11'.format(self.poolname),
                             description=None)


        snap11_again = SnapshotInfo(resource_lun_id='11',
                                    snapshot_name='Snapshot_11_again',
                                    created_time='just a moment ago',
                                    snap_state='Available',
                                    resource_lun_name='Applun_{0}_11'.format(self.poolname),
                                    description=None)

        snap11b = SnapshotInfo(resource_lun_id='11',
                               snapshot_name='L_11_',
                               created_time='just a moment ago',
                               snap_state='Available',
                               resource_lun_name='Applun_{0}_11'.format(self.poolname),
                               description=None)

        snap22 = SnapshotInfo(resource_lun_id='22',
                              snapshot_name='Snapshot_22',
                              created_time='just a moment ago',
                              snap_state='Available',
                              resource_lun_name='Applun_{0}_22'.format(self.poolname),
                              description=None)

        snap11bkp = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='enm_upgrade_bkup_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_11'.format(self.poolname),
                             description=None)

        snap22bkp = SnapshotInfo(resource_lun_id='22',
                             snapshot_name='enm_upgrade_bkup_22',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_22'.format(self.poolname),
                             description=None)

        snap_info = [snap11, snap11_again, snap11b, snap22, snap11bkp, snap22bkp]
        list_snaps.return_value = snap_info

        lun_disks = {'Applun_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}
        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)
        self.assertRaises(SanApiException, san.restore_snapshots)

    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_restore_snapshots_none(self, litp, litp_header, litp_san, list_snaps, list_luns):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun11 = LunInfo(lun_id='11',
                        name='Applun_{0}_11'.format(self.poolname),
                        uid='sadasd',
                        container=self.poolname,
                        size='100Gb',
                        container_type='StoragePool',
                        raid='5')

        lun22 = LunInfo(lun_id='22',
                        name='Applun_{0}_22'.format(self.poolname),
                        uid='sadasd',
                        container=self.poolname,
                        size='100Gb',
                        container_type='StoragePool',
                        raid='5')

        san_luns = [lun11, lun22]
        list_luns.return_value = san_luns

        snap11 = SnapshotInfo(resource_lun_id='11',
                              snapshot_name='L_11_',
                              created_time='just a moment ago',
                              snap_state='Available',
                              resource_lun_name='Applun_{0}_11'.format(self.poolname),
                              description=None)

        snap22 = SnapshotInfo(resource_lun_id='22',
                              snapshot_name='Snapshot_22',
                              created_time='just a moment ago',
                              snap_state='Available',
                              resource_lun_name='Applun_{0}_22'.format(self.poolname),
                              description=None)

        snap11b = SnapshotInfo(resource_lun_id='11',
                               snapshot_name='enm_upgrade_bkup_11',
                               created_time='just a moment ago',
                               snap_state='Available',
                               resource_lun_name='Applun_{0}_11'.format(self.poolname),
                               description=None)

        snap22b = SnapshotInfo(resource_lun_id='22',
                               snapshot_name='enm_upgrade_bkup_22',
                               created_time='just a moment ago',
                               snap_state='Available',
                               resource_lun_name='Applun_{0}_22'.format(self.poolname),
                               description=None)

        snap_info = [snap11, snap22, snap11b, snap22b]
        list_snaps.return_value = snap_info

        lun_disks = {'Applun_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}
        litp_san.return_value.get_node_lundisks.return_value = lun_disks

        san = VNXSnap(self.san_cred, self.snap_prefix)
        self.assertRaises(SanApiException, san.restore_snapshots)

    @patch('h_snapshots.san_snapshot.NavisecCLI.snap_restore')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_restore_snapshots_exception(self, litp, litp_header, litp_san, list_snaps, list_luns,
                                         snap_restore):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun1 = LunInfo(lun_id='11',
                       name='Applun_{0}_11'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        lun2 = LunInfo(lun_id='22',
                       name='Applun_{0}_22'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        san_luns = [lun1, lun2]
        list_luns.return_value = san_luns

        snap1 = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='Snapshot_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_11'.format(self.poolname),
                             description=None)

        snap2 = SnapshotInfo(resource_lun_id='22',
                             snapshot_name='Snapshot_22',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_22'.format(self.poolname),
                             description=None)

        snap_info = [snap1, snap2]
        list_snaps.return_value = snap_info

        lun_disks = {'Applun_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}
        litp_san.return_value.get_node_lundisks.return_value = lun_disks
        san = VNXSnap(self.san_cred, self.snap_prefix)
        snap_restore.side_effect = [Exception]

        self.assertRaises(SanApiException, san.restore_snapshots)

    @patch('h_snapshots.san_snapshot.VNXSnap.restore_san_lun')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_restore_snapshots_threads_exception(self, litp, litp_header, litp_san, list_snaps,
                                                 list_luns, snap_restore):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun1 = LunInfo(lun_id='11',
                       name='Applun_{0}_11'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        lun2 = LunInfo(lun_id='22',
                       name='Applun_{0}_22'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        san_luns = [lun1, lun2]
        list_luns.return_value = san_luns

        snap1 = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='Snapshot_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_11'.format(self.poolname),
                             description=None)

        snap2 = SnapshotInfo(resource_lun_id='22',
                             snapshot_name='Snapshot_22',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_22'.format(self.poolname),
                             description=None)

        snap_info = [snap1, snap2]
        list_snaps.return_value = snap_info

        lun_disks = {'Applun_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}
        litp_san.return_value.get_node_lundisks.return_value = lun_disks

        return_value_1 = san_luns[0]
        san = VNXSnap(self.san_cred, self.snap_prefix)
        snap_restore.side_effect = [(True, return_value_1)]

        return_value_2 = san_luns[1]
        self.assertRaises(SanApiException, san.restore_snapshots)
        snap_restore.side_effect = [(True, return_value_1), (False,
                                                             return_value_2)]
        self.assertRaises(SanApiException, san.restore_snapshots)


    @patch('h_snapshots.san_snapshot.NavisecCLI.snap_destroy')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_snaps')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_remove_snaps_by_prefix(self, litp, litp_header, litp_san, list_snaps, list_luns, snap_destroy):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        lun1 = LunInfo(lun_id='11',
                       name='Applun_{0}_11'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        lun2 = LunInfo(lun_id='22',
                       name='Applun_{0}_22'.format(self.poolname),
                       uid='sadasd',
                       container=self.poolname,
                       size='100Gb',
                       container_type='StoragePool',
                       raid='5')

        san_luns = [lun1, lun2]
        list_luns.return_value = san_luns

        snap1 = SnapshotInfo(resource_lun_id='11',
                             snapshot_name='enm_upgrade_bkup_11',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_11'.format(self.poolname),
                             description=None)

        snap2 = SnapshotInfo(resource_lun_id='22',
                             snapshot_name='enm_upgrade_bkup_22',
                             created_time='just a moment ago',
                             snap_state='Available',
                             resource_lun_name='Applun_{0}_22'.format(self.poolname),
                             description=None)

        snap_info = [snap1, snap2]
        list_snaps.return_value = snap_info

        lun_disks = {'Applun_{0}_11'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'",
                     'Applun_{0}_22'.format(self.poolname):
                         "/deployments/d/clusters/c/nodes/n1/system/"
                         "disks/d1 [item-type:lun-disk state:Applied] "
                         "properties{'lun_name': "
                         "'LITP2_ENM223_snappable', "
                         "'storage_container': 'ENM223', "
                         "'snap_size': '100'"}

        litp_san.return_value.get_node_lundisks.return_value = lun_disks

        san = VNXSnap(self.san_cred, self.snap_prefix)
        san.remove_snaps_by_prefix(['11', '22'])

        bkdestroy_calls = []
        for bk in snap_info:
            bkdestroy_calls.append(
                call(bk.snap_name)
            )
        snap_destroy.assert_has_calls(bkdestroy_calls, any_order=True)

        snap_destroy.side_effect = [Exception]
        self.assertRaises(SanApiException, san.remove_snaps_by_prefix)

    @patch('h_snapshots.san_snapshot.NavisecCLI.list_all_luns')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_luns_by_pool(self, litp, litp_header, litp_san, list_luns):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        san_luns = []
        for idx in range(1, 6):
            lun_id = str(idx)
            pool_name = 'pool1' if idx < 3 else 'pool2'

            lun = LunInfo(lun_id=lun_id,
                           name='lun-{0}'.format(lun_id),
                           uid='sadasd',
                           container=pool_name,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')
            if lun.container == 'pool1':
                san_luns.append(lun)

        list_luns.return_value = san_luns

        san = VNXSnap(self.san_cred, self.snap_prefix)
        luns = san._get_luns_by_pool('pool1')

        self.assertEqual(2, len(luns))
        self.assertIn('1', luns)
        self.assertIn('2', luns)
        self.assertEqual('lun-1', luns['1'].name)
        self.assertEqual('lun-2', luns['2'].name)

    @patch('h_snapshots.san_snapshot.NavisecCLI')
    def test_filter_luns(self, navisec):
        all_luns = {
            '1': '1',
            '2': '2',
            '3': '3'
        }
        filter_luns(all_luns, ['1', '3'])
        self.assertEqual(2, len(all_luns))
        self.assertIn('1', all_luns)
        self.assertEqual('1', all_luns['1'])
        self.assertIn('3', all_luns)
        self.assertEqual('3', all_luns['3'])

    @patch('h_snapshots.san_snapshot.VNXSnap._get_lun_name')
    @patch('h_snapshots.san_snapshot.LitpRestClient.get')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_opendj_node_paths')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_get_opendj_luns(self, litp, litp_header,
                             m_get_opendj_node_paths,
                             m_litp_get,
                             m_get_lun_name):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        m_get_opendj_node_paths.return_value = '/deployments/enm/clusters/db_cluster/nodes/db-2/'
        m_litp_get.return_value = {'id':'db-2'}
        m_get_lun_name.return_value = 'LUN_dummy_bootdb2'

        opendj_luns = VNXSnap._get_opendj_luns()

        self.assertEqual({'LUN_dummy_bootdb2':'db-2'}, opendj_luns)

    @patch('h_snapshots.san_snapshot.LitpRestClient.exists')
    @patch('h_snapshots.san_snapshot.LitpRestClient.get_children')
    def test_get_opendj_node_paths(self,
                             m_litp_get_children,
                             m_litp_exists):

        deployment = [{'path':'/deployments/enm'}]
        cluster = [{'path':'/deployments/enm/clusters/db_cluster'}]
        service = [{'path':'/deployments/enm/clusters/db_cluster/services/opendj_clustered_service',
                   'data': {'properties': {'node_list':'db-2'}}}]
        application = [{'path':'/deployments/enm/clusters/db_cluster/services/opendj_clustered_service/applications/opendj',
                       'data': {'item-type-name': 'reference-to-opendj-service'}}]

        m_litp_get_children.side_effect = [deployment,
                                           cluster,
                                           service,
                                           application]
        m_litp_exists.return_value = True
        opendj_node_paths = VNXSnap._get_opendj_node_paths()

        self.assertEqual(['/deployments/enm/clusters/db_cluster/nodes/db-2'], opendj_node_paths)

    @patch('h_snapshots.san_snapshot.LitpRestClient.get')
    @patch('h_snapshots.san_snapshot.LitpRestClient.get_children')
    def test_get_device(self,
                         m_litp_get_children,
                         m_litp_get):

        volume_group = [{'path':'/deployments/enm/clusters/db_cluster/nodes/db-2/storage_profile/volume_groups/vg1'}]
        file_system = [{'path':'/deployments/enm/clusters/db_cluster/nodes/db-2/storage_profile/volume_groups/vg1/file_systems/fs1',
                        'data': {'properties': {'mount_point':'/'}}}]
        m_litp_get_children.side_effect = [volume_group,
                                           file_system]
        m_litp_get.return_value = {'properties': {'device_name':'sda'}}

        device = VNXSnap._get_device('/deployments/enm/clusters/db_cluster/nodes/db-2', '/')

        self.assertEqual("sda", device)

    @patch('h_snapshots.san_snapshot.LitpRestClient.get_items_by_type')
    def test_get_lun_name(self,
                          m_get_items_by_type):
        m_get_items_by_type.return_value = [{'data': {'properties': {'name':'sda', 'lun_name':'LUN_dummy_bootdb2'}}}]
        lun_name = VNXSnap._get_lun_name('/deployments/enm/clusters/db_cluster/nodes/db-2', 'sda')

        self.assertEqual('LUN_dummy_bootdb2', lun_name)


class TestNavisecCLI(unittest2.TestCase):
    @patch('h_snapshots.snapshots_utils.api_builder')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def setUp(self, litp, litp_header, mock_api_builder):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        self.san_cred = {'san_login_scope': 'global', 'san_user': 'admin',
                         'san_spb_ip': '10.32.236.189',
                         'san_spa_ip': '10.32.236.188', 'san_psw':
                             'passw0rd',
                         'san_pool': 'Fargo9',
                         'san_type': 'Vnx2'}
        self.snap_prefix = 'Snapshot'
        self.cli = NavisecCLI(self.san_cred)
        self.lun_disks = {'LITP2_ENM223_snappable':
                              "/deployments/d/clusters/c/nodes/n1/system/"
                              "disks/d1 [item-type:lun-disk state:Applied] "
                              "properties{'lun_name': "
                              "'LITP2_ENM223_snappable', "
                              "'storage_container': 'ENM223', "
                              "'snap_size': '100'"}
        mock_api_builder.return_value = Mock()

    def test_snap_create(self):
        lun_id = 35
        snap_name = 'SnapName'
        description = 'CI VnxSnap'
        self.cli.snap_create(lun_id, snap_name)
        self.cli.san_api.create_snapshot_with_id.assert_called_with(lun_id,
                                                            snap_name,
                                                            description=description)

    def test_snap_destroy(self):
        snap_id = '53'
        self.cli.snap_destroy(snap_id)
        self.cli.san_api.delete_snapshot.assert_called_with(snap_id)

    def test_snap_restore(self):
        lun_id = 35
        snap_name = 'SnapName'
        bkup_name = 'enm_upgrade_bkup_%s' % lun_id

        self.cli.snap_restore(lun_id, snap_name)
        self.cli.san_api.restore_snapshot_by_id.assert_called_with(lun_id, snap_name,
                                                              delete_backupsnap=False,
                                                              backup_name=bkup_name)

    @patch('h_snapshots.snap_agent.SnapAgents.cleanup_opendj')
    @patch('h_snapshots.san_snapshot.VNXSnap._get_opendj_nodes')
    @patch('h_snapshots.san_snapshot.LitpSanSnapshots')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get_auth_header')
    @patch('h_snapshots.snapshots_utils.LitpRestClient.get')
    def test_opendj_backup_cleanup(self, litp, litp_header, litp_san, active_nodes, cleanup_opendj):
        litp_header.return_value = litp_header_value
        litp.return_value = litp_get_value
        node_list = ['opendj_1', 'opendj_2']
        active_nodes.return_value = node_list
        san = VNXSnap(self.san_cred, self.snap_prefix)
        san.opendj_backup_cleanup()
        cleanup_opendj.assert_called_with(node_list, san.opendj_backup_dir,
                                          san.opendj_log_dir)


if __name__ == '__main__':
    unittest2.main()
