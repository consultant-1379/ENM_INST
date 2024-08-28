from copy import deepcopy
import httplib
from json import dumps
from mock import patch, MagicMock, call
import unittest2

from h_snapshots.sfs_snapshot import SfsSnapshots, SfsSnapshotsException, \
    SFS_SNAP_SIZE_KEY
from h_snapshots import sfs_snapshot
from h_litp.litp_utils import LitpException
from h_util.h_nas_console import get_rollback_cache_name
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mocks

TC_MODULE = 'h_snapshots.sfs_snapshot'
nas_cred = {sfs_snapshot.SK_NASCONSOLE_IP: '1.1.1.1',
            sfs_snapshot.SK_NASCONSOLE_SUPUSER: 'support',
            sfs_snapshot.SK_NASCONSOLE_SUPPASSWD: 'symantec',
            sfs_snapshot.SK_SFS_POOL_NAME: 'enm'}
fs_to_snap = {
    'enm-smrs': {
        'status': 'online', 'shared': 'yes',
        'fs': 'enm-smrs', 'size': '10.00G'},
    'enm-brsadm_home': {
        'status': 'online', 'shared': 'yes',
        'fs': 'enm-brsadm_home', 'size': '100.00M'}
}
modelled_filesystems_mock = {'enm-smrs': {SFS_SNAP_SIZE_KEY: 40},
                        'enm-brsadm_home': {SFS_SNAP_SIZE_KEY: 40}}

storage_fs_list = {
    'enm-smrs': {
        'status': 'online', 'shared': 'yes',
        'fs': 'enm-smrs', 'size': '10.00G'},
    'enm-brsadm_home': {
        'status': 'online', 'shared': 'yes',
        'fs': 'enm-brsadm_home', 'size': '100.00M'},
    'enm-sdncontroller': {
        'status': 'online', 'shared': 'yes',
        'fs': 'enm-ddc_data', 'size': '5.00G'},
    'enm-ddc_data': {
        'status': 'online', 'shared': 'yes',
        'fs': 'enm-ddc_data', 'size': '5.00G'}
}
nfs_share_show = {
    'enm-brsadm_home': [{
        'client': '10.140.3.0/24', 'options': 'rw,sync,no_root_squash',
        'filesystem': 'enm-brsadm_home'}],
    'enm-smrs': [{
        'client': '10.140.3.0/24', 'options': 'rw,sync,no_root_squash',
        'filesystem': 'enm-smrs'}],
    'enm-sdncontroller': [{
        'client': '10.140.3.0/24', 'options': 'rw,sync,no_root_squash',
        'filesystem': 'enm-sdncontroller'}]}

litp_storage_pools = {
    "_embedded": {
        "item": [
            {
                "id": "enm-pool",
                "item-type-name": "sfs-pool",
                "applied_properties_determinable": True,
                "state": "Applied",
                "_links": {
                    "self": {
                        "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools/enm-pool"
                    },
                    "item-type": {
                        "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-pool"
                    }
                },
                "properties": {
                    "name": "enm"
                }
            }
        ]
    },
    "item-type-name": "collection-of-sfs-pool",
    "applied_properties_determinable": 'true',
    "state": "Applied",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools"
        },
        "collection-of": {
            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-pool"
        }
    },
    "id": "pools"
}


def get_modelled_filesystems():
    return {
        "_embedded": {
            "item": [
                {
                    "id": "fs_amos",
                    "item-type-name": "sfs-filesystem",
                    "applied_properties_determinable": True,
                    "state": "Applied",
                    "_links": {
                        "self": {
                            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools/enm-pool/file_systems/fs_amos"
                        },
                        "item-type": {
                            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-filesystem"
                        }
                    },
                    "properties": {
                        "path": "/vx/enm-amos",
                        "size": "100G",
                        "cache_name": "enm_cache",
                        "snap_size": "40"
                    }
                },
                {
                    "id": "fs_brsadm_home",
                    "item-type-name": "sfs-filesystem",
                    "applied_properties_determinable": True,
                    "state": "Applied",
                    "_links": {
                        "self": {
                            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools/enm-pool/file_systems/fs_brsadm_home"
                        },
                        "item-type": {
                            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-filesystem"
                        }
                    },
                    "properties": {
                        "path": "/vx/enm-brsadm_home",
                        "size": "100M",
                        "cache_name": "enm_cache",
                        "snap_size": "40"
                    }
                },
                {
                    "id": "fs_smrs",
                    "item-type-name": "sfs-filesystem",
                    "applied_properties_determinable": True,
                    "state": "Applied",
                    "_links": {
                        "self": {
                            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools/enm-pool/file_systems/fs_smrs"
                        },
                        "item-type": {
                            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-filesystem"
                        }
                    },
                    "properties": {
                        "path": "/vx/enm-smrs",
                        "size": "2600G",
                        "cache_name": "enm_cache",
                        "snap_size": "40"
                    }
                },
                {
                    "id": "fs_some_file_system",
                    "item-type-name": "sfs-filesystem",
                    "applied_properties_determinable": True,
                    "state": "Applied",
                    "_links": {
                        "self": {
                            "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools/enm-pool/file_systems/fs_some_file_system"
                        },
                        "item-type": {
                            "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-filesystem"
                        }
                    },
                    "properties": {
                        "path": "/vx/enm-some_file_system",
                        "size": "2600G",
                        "cache_name": "enm_cache",
                        "snap_size": "0"
                    }
                }
            ]
        },
        "item-type-name": "collection-of-sfs-filesystem",
        "applied_properties_determinable": 'true',
        "state": "Applied",
        "_links": {
            "self": {
                "href": "https://localhost:9999/litp/rest/v1/infrastructure/storage/storage_providers/sfs/pools/enm-pool/file_systems"
            },
            "collection-of": {
                "href": "https://localhost:9999/litp/rest/v1/item-types/sfs-filesystem"
            }
        },
        "id": "file_systems"
    }


def patch_ssh(ssh_patch, return_code, stdout, stderr):
    mstdout = MagicMock()
    mstdout.channel.recv_exit_status.return_value = return_code
    mstdout.readlines.return_value = stdout

    mstderr = MagicMock()
    mstderr.readlines.return_value = stderr

    ssh_patch.return_value.exec_command.return_value = [None, mstdout,
                                                        mstderr]


@patch('h_snapshots.sfs_snapshot.get_nas_type', return_value='veritas')
class TestSfsSnapshots(unittest2.TestCase):

    def setUp(self):
        self.deleted = None
        self.cache = None
        self.create = None

    def get_litp_model_mock(self, sfs):
        setup_litp_mocks(
            sfs.litp, [
                [
                    'GET',
                    dumps(litp_storage_pools),
                    httplib.OK
                ], [
                    'GET', dumps(get_modelled_filesystems()), httplib.OK

                ]
            ]
        )

    @patch(TC_MODULE + '.NasConsole')
    def test_remove_snapshots(self, nc, m_nas_type):
        nc.return_value.storage_rollback_list.return_value = {
            'enm-brsadm_home': ['Snapshot-enm-brsadm_home'],
            'enm-smrs': ['Snapshot-enm-smrs']
        }
        nc.return_value.storage_fs_list.return_value = fs_to_snap
        self.deleted = {}

        def se(fs, ex):
            self.deleted[fs] = ex

        nc.return_value.storage_rollback_destroy = se
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        sfs.remove_snapshots()
        self.assertIn('Snapshot-enm-brsadm_home', self.deleted)
        self.assertIn('Snapshot-enm-smrs', self.deleted)
        self.assertTrue('enm-brsadm_home',
                        self.deleted['Snapshot-enm-brsadm_home'])
        self.assertTrue('enm-smrs', self.deleted['Snapshot-enm-smrs'])
        nc.return_value.storage_rollback_list.return_value = {}
        self.deleted = {}
        sfs.remove_snapshots()
        self.assertEquals(self.deleted, {})

    @patch(TC_MODULE + '.NasConsole')
    def test_create_snapshots(self, nc, m_nas_type):
        dummy_fs = {'dummy': {'status': 'online', 'shared': 'yes',
                              'fs': 'dummy', 'size': '10.00G'}}
        nc.return_value.storage_fs_list.return_value = dummy_fs
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        self.assertRaises(SfsSnapshotsException, sfs.create_snapshots)
        nc.return_value.storage_fs_list.return_value = fs_to_snap
        nc.return_value.storage_rollback_cache_list.return_value = \
            'enm-cache'
        self.create = {}

        def se1(rl, fs, cache):
            self.create[fs] = [rl, cache]

        nc.return_value.storage_rollback_create = se1
        filesystems = sfs.create_snapshots()
        self.assertIn('enm-smrs', filesystems)
        self.assertIn('enm-brsadm_home', filesystems)
        self.assertIn('Snapshot-enm-brsadm_home',
                      self.create['enm-brsadm_home'])
        self.assertIn('Snapshot-enm-smrs', self.create['enm-smrs'])
        nc.return_value.storage_rollback_cache_list.return_value = ''
        self.cache = {}

        def se2(cache, cacheize, poolname):
            self.cache[poolname] = [cache, cacheize]

        nc.return_value.storage_rollback_cache_create = se2
        sfs.create_snapshots()
        self.assertIn(nas_cred[sfs_snapshot.SK_SFS_POOL_NAME], self.cache)
        self.assertIn(get_rollback_cache_name
                      (nas_cred[sfs_snapshot.SK_SFS_POOL_NAME]),
                      self.cache[nas_cred[sfs_snapshot.SK_SFS_POOL_NAME]])

    @patch(TC_MODULE + '.NasConsole')
    def test_calculate_cache_already_exit(self, nc, m_nas_type):
        nc.return_value.storage_rollback_cache_list.return_value = {
            'enm-cache': {'size_mb': '22528', 'used_perc': '2'}
        }
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        rollback_cache_name = 'enm-cache'
        self.assertIsNone(sfs.calculate_cache_size(fs_to_snap,
                                                   rollback_cache_name,
                                                   modelled_filesystems_mock))

    @patch(TC_MODULE + '.NasConsole')
    def test_calculate_cache_size_different_snap_size(self, nc, m_nas_type):
        nc.return_value.storage_rollback_cache_list.return_value = {}
        nc.return_value.storage_fs_list.return_value = storage_fs_list
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        rollback_cache_name = 'enm-cache'
        modelled_filesystems = {'enm-smrs': {SFS_SNAP_SIZE_KEY: 50},
                                'enm-brsadm_home': {SFS_SNAP_SIZE_KEY: 40}}
        cache_size = sfs.calculate_cache_size(fs_to_snap, rollback_cache_name,
                                              modelled_filesystems)
        self.assertEqual('5G', cache_size)

    @patch(TC_MODULE + '.NasConsole')
    def test_calculate_cache_size(self, nc, m_nas_type):
        nc.return_value.storage_rollback_cache_list.return_value = {}
        nc.return_value.storage_fs_list.return_value = storage_fs_list
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        rollback_cache_name = 'enm-cache'
        cache_size = sfs.calculate_cache_size(fs_to_snap, rollback_cache_name,
                                              modelled_filesystems_mock)
        self.assertEqual('4G', cache_size)
        tdata = deepcopy(fs_to_snap)
        tdata['enm-smrs']['size'] = '1M'
        tdata['enm-brsadm_home']['size'] = '1M'
        cache_size = sfs.calculate_cache_size(tdata, rollback_cache_name,
                                              modelled_filesystems_mock)
        self.assertEqual('256M', cache_size)

    @patch(TC_MODULE + '.NasConsole')
    def test_list_snapshots(self, nc, m_nas_type):

        fslist = {
            'enm-brsadm_home': {},
            'enm-smrs': {},
        }

        snapped = {}
        for fs in fslist.keys():
            snapped[fs] = 'Snapshot-'.format(fs)

        nc.return_value.storage_rollback_list.return_value = snapped
        sfs = SfsSnapshots(nas_cred, 'Snapshot')

        sfs.build_fs_to_snap = MagicMock()
        sfs.build_fs_to_snap.return_value = fslist

        logged = []

        def se(st):
            logged.append(st)

        sfs.logger = MagicMock()
        sfs.logger.info = se

        sfs.list_snapshots(False)
        for fs in fslist.keys():
            self.assertTrue(any(
                '{0} has associated'.format(fs) in line for line in logged))

        nc.return_value.storage_rollback_list.return_value = {}
        logged = []
        sfs.list_snapshots(False)
        self.assertIn('No NAS snapshots found on the system (tag=Snapshot).',
                      ''.join(logged))

    @patch(TC_MODULE + '.NasConsole')
    def test_build_fs_to_snap_error(self, m_nasconsole, m_nas_type):
        m_nasconsole.return_value.storage_fs_list.return_value = {}

        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        self.assertRaises(SfsSnapshotsException, sfs.build_fs_to_snap)

    @patch(TC_MODULE + '.NasConsole')
    def test_build_fs_to_snap_remove_scenario(self, m_nasconsole, m_nas_type):
        m_nasconsole.return_value.storage_fs_list.return_value = storage_fs_list

        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        the_backed_up_list = {"ENM425-data": {
            "status": "online",
            "shared": "yes",
            "fs": "ENM425-data",
            "size": "20.00G"}}
        backed_up = sfs.build_fs_to_snap(file_system_list=the_backed_up_list)
        self.assertEquals(backed_up, the_backed_up_list)

    @patch(TC_MODULE + '.NasConsole')
    def test_validate(self, nc, m_nas_type):
        nc.return_value.storage_fs_list.return_value = fs_to_snap
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        nc.return_value.storage_rollback_cache_list.return_value = ''
        nc.return_value.storage_rollback_list.return_value = {
            'enm-brsadm_home': 'Snapshot-enm-brsadm_home',
            'enm-smrs': 'Snapshot-enm-smrs'
        }
        self.assertRaises(SystemExit, sfs.validate)

        nc.return_value.storage_rollback_cache_list.return_value = \
            {'enm-cache': {'size_mb': '26624', 'used_perc': '100'}}
        self.assertRaises(SystemExit, sfs.validate)

        nc.return_value.storage_rollback_cache_list.return_value = \
            {'enm-cache': {'size_mb': '26624', 'used_perc': '90'}}
        try:
            sfs.validate()
        except Exception:
            self.fail('No error should have been raised!')

        nc.return_value.storage_rollback_cache_list.return_value = \
            {'enm-cache': {'size_mb': '26624', 'used_perc': '10'}}
        nc.return_value.storage_rollback_list.return_value = {
            'enm-brsadm_home': 'Snapshot-enm-brsadm_home'
        }
        self.assertRaises(SystemExit, sfs.validate)

        nc.return_value.storage_rollback_cache_list.return_value = \
            {'enm-cache': {'size_mb': '26624', 'used_perc': '10'}}
        nc.return_value.storage_rollback_list.return_value = {
            'enm-brsadm_home': 'Snapshot-enm-brsadm_home',
            'enm-smrs': 'Snapshot-enm-smrs'
        }
        self.assertEqual(None, sfs.validate(fs_to_snap))

    @patch(TC_MODULE + '.NasConsole.storage_rollback_list')
    @patch(TC_MODULE + '.NasConsole.storage_fs_list')
    @patch('h_util.h_nas_console.read_enminst_config')
    @patch('paramiko.SSHClient')
    @patch(TC_MODULE + '.NasConsole.storage_rollback_restore')
    @patch(TC_MODULE + '.NasConsole.storage_fs_online')
    @patch(TC_MODULE + '.NasConsole.nfs_share_show')
    def test_restore_snapshots(self, nss, sfo, srr,
                               ssh, cfg, fls, rl, m_nas_type):
        rl.return_value = {
            'enm-brsadm_home': ['Snapshot-enm-brsadm_home'],
            'enm-smrs': ['Snapshot-enm-smrs']
        }
        snap_fs_export = {'enm-smrs': [{'client': '10.140.3.0/24',
                                        'options': 'rw,sync,no_root_squash',
                                        'filesystem': 'enm-smrs'}],
                          'enm-brsadm_home': [{'client': '10.140.3.0/24',
                                               'options':
                                                   'rw,sync,no_root_squash',
                                               'filesystem':
                                                   'enm-brsadm_home'}]}
        fls.return_value = {'enm-smrs': {'status': 'offline'},
                            'enm-brsadm_home': {'status': 'offline'}}
        cfg.return_value = {'fs_status_check': '0,10'}
        nss.return_value = nfs_share_show
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        patch_ssh(ssh, 0, [], [])
        sfs.restore_snapshots(snap_fs_export)
        self.assertTrue(rl.called)
        self.assertTrue(cfg.called)
        self.assertTrue(fls.called)
        self.assertTrue(srr.called)
        self.assertTrue(sfo.called)
        self.assertTrue(nss.called)

        rl.return_value = {
            'enm-brsadm_home': ['Snapshot-enm-brsadm_home', 'another_snap'],
            'enm-smrs': ['Snapshot-enm-smrs']
        }
        self.assertRaises(SfsSnapshotsException, sfs.restore_snapshots,
                          snap_fs_export)

        rl.return_value = {
            'enm-brsadm_home': ['Snapshot-enm-brsadm_home'],
            'enm-smrs': ['Snapshot-enm-smrs']
        }

        fls.return_value = {'enm-smrs': {'status': 'offline'},
                            'enm-brsadm_home': {'status': 'online'}}
        self.assertRaises(SfsSnapshotsException, sfs.restore_snapshots,
                          snap_fs_export)

    @patch(TC_MODULE + '.sleep')
    @patch(TC_MODULE + '.NasConsole.nfs_share_show')
    @patch('paramiko.SSHClient')
    @patch(TC_MODULE + '.NasConsole.nfs_share_add')
    def test_restore_snapshots_nfs_share_issue(self, nsa, ssh, nss,
                                               m_sleep, m_nas_type):
        snap_fs_export = {'enm-smrs': [{'client': '10.140.3.0/24',
                                        'options': 'rw,sync,no_root_squash',
                                        'filesystem': 'enm-smrs'}],
                          'enm-brsadm_home': [{'client': '10.140.3.0/24',
                                               'options':
                                                   'rw,sync,no_root_squash',
                                               'filesystem':
                                                   'enm-brsadm_home'}]}
        nfs_share_incomplete = {'enm-smrs': [{'client': '10.140.3.0/24',
                                              'options':
                                                  'rw,sync,no_root_squash',
                                              'filesystem': 'enm-smrs'}]}
        nss.side_effect = [nfs_share_incomplete, nfs_share_show]
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        patch_ssh(ssh, 0, [], [])
        sfs.rollback_nas_fs('enm-brsadm_home', snap_fs_export,
                          ['Snapshot-enm-brsadm_home'])
        nss.side_effect = [nfs_share_incomplete, nfs_share_incomplete,
                           nfs_share_incomplete]
        self.assertEqual((False, 'enm-brsadm_home'), sfs.rollback_nas_fs('enm-brsadm_home',
                                                                       snap_fs_export,
                                                                       ['Snapshot-enm-brsadm_home']))

    @patch(TC_MODULE + '.NasConsole.storage_rollback_list')
    @patch(TC_MODULE + '.NasConsole.nfs_share_show')
    @patch('paramiko.SSHClient')
    @patch(TC_MODULE + '.NasConsole.nfs_share_delete')
    @patch(TC_MODULE + '.NasConsole.storage_fs_offline')
    @patch(TC_MODULE + '.NasConsole.storage_rollback_restore')
    @patch(TC_MODULE + '.NasConsole.storage_fs_online')
    @patch(TC_MODULE + '.NasConsole.nfs_share_add')
    @patch(TC_MODULE + '.SfsSnapshots.rollback_nas_fs')
    def test_restore_snapshots_threads_exception(self, rnf, nsa, sfo, srr,
                                                 sfof, nsd, ssh, nss, nc,
                                                 m_nas_type):
        nc.return_value = {
            'enm-brsadm_home': ['Snapshot-enm-brsadm_home'],
            'enm-smrs': ['Snapshot-enm-smrs']
        }
        snap_fs_export = {'enm-smrs': [{'client': '10.140.3.0/24',
                                        'options': 'rw,sync,no_root_squash',
                                        'filesystem': 'enm-smrs'}],
                          'enm-brsadm_home': [{'client': '10.140.3.0/24',
                                               'options':
                                                   'rw,sync,no_root_squash',
                                               'filesystem':
                                                   'enm-brsadm_home'}]}
        nss.return_value = nfs_share_show
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        patch_ssh(ssh, 0, [], [])
        rnf.side_effect = [(True, 'enm-brsadm_home')]
        self.assertRaises(SfsSnapshotsException, sfs.restore_snapshots,
                          snap_fs_export)
        rnf.side_effect = [(True, 'enm-brsadm_home'), (False, 'enm-smrs')]
        self.assertRaises(SfsSnapshotsException, sfs.restore_snapshots,
                          snap_fs_export)

    @patch(TC_MODULE + '.NasConsole')
    def test_build_exported_fs(self, m_nasconsole, m_nas_type):
        m_nfs_share_show = MagicMock()
        m_nasconsole.return_value.nfs_share_show = m_nfs_share_show
        m_nfs_share_show.return_value = {
            'fs1': 'fs-1',
            'fs2': 'fs-2',
            'enm-amos': 'enm-amos'}

        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        fslist = sfs.build_exported_fs()
        self.assertEqual(1, len(fslist))
        self.assertIn('enm-amos', fslist)

    @patch(TC_MODULE + '.NasConsole')
    def test_build_exported_fs_exception(self, m_nasconsole, m_nas_type):
        m_nfs_share_show = MagicMock()
        m_nfs_share_show.side_effect = [Exception()]
        m_nasconsole.return_value.nfs_share_show = m_nfs_share_show
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        self.assertRaises(SfsSnapshotsException, lambda: sfs.build_exported_fs())

    @patch(TC_MODULE + '.NasConsole')
    def test_build_exported_fs_retries(self, m_nasconsole, m_nas_type):
        m_nfs_share_show = MagicMock()
        m_nfs_share_show.side_effect = [
            Exception(),
            Exception(),
            Exception(),
            {'fs1': 'fs-1','fs2': 'fs-2','enm-amos': 'enm-amos'}]
        m_nasconsole.return_value.nfs_share_show = m_nfs_share_show
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        fslist = sfs.build_exported_fs()
        self.assertEqual(1, len(fslist))
        self.assertIn('enm-amos', fslist)

    @patch(TC_MODULE + '.NasConsole')
    def test_remove_rollback_cache(self, m_nasconsole, m_nas_type):
        m_nasconsole.return_value.storage_rollback_cache_list.return_value = [
            'enm-cache'
        ]

        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        sfs.remove_rollback_cache()
        self.assertTrue(
            m_nasconsole.return_value.storage_rollback_cache_destroy.called)

        m_nasconsole.return_value.storage_rollback_cache_destroy.reset_mock()
        m_nasconsole.return_value.storage_rollback_cache_list.return_value = [
            'c1-cache'
        ]
        sfs.remove_rollback_cache()
        self.assertFalse(
            m_nasconsole.return_value.storage_rollback_cache_destroy.called)

    @patch(TC_MODULE + '.NasConsole.storage_rollback_list')
    @patch(TC_MODULE + '.NasConsole.nfs_share_show')
    @patch('paramiko.SSHClient')
    @patch(TC_MODULE + '.NasConsole.nfs_share_delete')
    def test_remove_sfs_shares(self, nsd, ssh, nss, nc, m_nas_type):
        nc.return_value = {
            'enm-brsadm_home': ['Snapshot-enm-brsadm_home'],
            'enm-smrs': ['Snapshot-enm-smrs']
        }
        nss.return_value = nfs_share_show
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        patch_ssh(ssh, 0, [], [])
        sfs.remove_sfs_shares()
        self.assertTrue(nsd.called)
        self.assertTrue(nss.called)
        self.assertTrue(nc.called)

    @patch('paramiko.SSHClient')
    def test_get_modelled_filesystems(self, ssh, m_nas_type):
        patch_ssh(ssh, 0, [], [])
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        self.get_litp_model_mock(sfs)
        sfs.get_modelled_filesystems()
        self.assertEqual(3, len(sfs.fs_snap_list))
        self.assertIn('enm-amos', sfs.fs_snap_list)
        self.assertNotIn('enm-some_file_system', sfs.fs_snap_list)

    @patch(TC_MODULE + '.LitpRestClient.get_children')
    @patch('paramiko.SSHClient')
    def test_get_filesystems_for_removal(self, ssh, litp, m_nas_type):
        litp.side_effect = LitpException(404, {'path': '/software/services/sdncontroller',
                                               'reason': 'Not Found',
                                               'messages': [{'type': 'InvalidLocationError'}]})
        patch_ssh(ssh, 0, [], [])
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        fs_for_removal = sfs.get_filesystems_for_removal()
        self.assertEqual(3, len(fs_for_removal))
        self.assertIn('enm-sdncontroller', fs_for_removal)

        litp.side_effect = None
        litp.return_value = {}
        patch_ssh(ssh, 0, [], [])
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        fs_for_removal = sfs.get_filesystems_for_removal()
        self.assertEqual(0, len(fs_for_removal))
        self.assertNotIn('enm-sdncontroller', fs_for_removal)

    @patch(TC_MODULE + '.NasConsole.storage_fs_destroy')
    @patch(TC_MODULE + '.NasConsole.nfs_share_delete')
    @patch(TC_MODULE + '.NasConsole.nfs_share_show')
    @patch(TC_MODULE + '.NasConsole.storage_fs_list')
    @patch(TC_MODULE + '.SfsSnapshots.get_filesystems_for_removal')
    @patch('paramiko.SSHClient')
    def test_ensure_removal_fs_not_required(self, ssh, gfsr, sfl, nss, nsd, sfd, m_nas_type):
        patch_ssh(ssh, 0, [], [])
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        gfsr.return_value = ['enm-sdncontroller']
        sfl.return_value = storage_fs_list
        nss.return_value = nfs_share_show
        sfs.ensure_removal_fs_not_required()
        self.assertTrue(sfl.called)
        self.assertEqual(sfl.call_args, call('enm'))
        self.assertTrue(nss.called)
        self.assertEqual(nss.call_args, call('enm'))
        self.assertTrue(nsd.called)
        self.assertEqual(nsd.call_args, call('enm-sdncontroller',
                                             '10.140.3.0/24'))
        self.assertTrue(sfd.called)
        self.assertEqual(sfd.call_args, call('enm-sdncontroller'))

        sfd.reset_mock()
        nsd.reset_mock()
        patch_ssh(ssh, 0, [], [])
        sfs = SfsSnapshots(nas_cred, 'Snapshot')
        gfsr.return_value = ['enm-sdncontroller1']
        sfl.return_value = storage_fs_list
        nss.return_value = nfs_share_show
        sfs.ensure_removal_fs_not_required()
        self.assertTrue(sfl.called)
        self.assertEqual(sfl.call_args, call('enm'))
        self.assertTrue(nss.called)
        self.assertEqual(nss.call_args, call('enm'))
        self.assertFalse(nsd.called)
        self.assertEqual(nsd.call_args, None)
        self.assertFalse(sfd.called)
        self.assertEqual(sfd.call_args, None)


if __name__ == '__main__':
    unittest2.main()

