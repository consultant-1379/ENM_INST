from ConfigParser import NoSectionError
from os.path import basename

from mock import patch, call, MagicMock
from unittest2 import TestCase

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.nasexceptions'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

from h_litp.litp_rest_client import LitpObject, LitpRestClient
from h_snapshots.litp_snapshots import LitpSanSnapshots, LitpNasSnapshots, \
    LitpVolMgrSnapshots, LitpSnapError, LitpSnapshots, LitpBaseSnapshots, \
    get_volume_snapshot_name
from h_util.h_utils import ExitCodes
from sanapiinfo import SnapshotInfo, LunInfo, StoragePoolInfo

item_path_parser = LitpRestClient().path_parser


def litp_json(model_path, item_type, properties=None):
    return {
        '_links': {
            'self': {
                'href': 'https://localhost:9999/litp/rest/v1'
                        '{0}'.format(model_path)
            }
        },
        'id': basename(model_path),
        'item-type-name': item_type,
        'state': 'Applied',
        'description': '',
        'properties': properties
    }


def litp_object(model_path, item_type, properties=None):
    if not properties:
        properties = {}
    return LitpObject(None, litp_json(model_path, item_type, properties),
                      item_path_parser)


class MockedLitpSanSnapshots(LitpSanSnapshots):
    def __init__(self, verbose=False):
        super(MockedLitpSanSnapshots, self).__init__(verbose)
        self.child_model = {}

    def get_children(self, model_path):
        if model_path in self.child_model:
            return self.child_model[model_path]
        else:
            raise KeyError('No setup for {0} found!'.format(model_path))


class MockedLitpNasSnapshots(LitpNasSnapshots):
    def __init__(self, verbose=False):
        super(MockedLitpNasSnapshots, self).__init__(verbose)
        self.child_model = {}

    def get_children(self, model_path):
        if model_path in self.child_model:
            return self.child_model[model_path]
        else:
            raise KeyError('No setup for {0} found!'.format(model_path))


class MockedLitpVolMgrSnapshots(LitpVolMgrSnapshots):
    def __init__(self, verbose=False):
        super(MockedLitpVolMgrSnapshots, self).__init__(verbose)
        self.child_model = {}
        self.get_model = {}

    def get_children(self, model_path):
        if model_path in self.child_model:
            return self.child_model[model_path]
        else:
            raise KeyError('No child setup for {0} found!'.format(model_path))

    def get(self, model_path):
        if model_path in self.get_model:
            return self.get_model[model_path]
        else:
            raise KeyError('No get setup for {0} found!'.format(model_path))


@patch('h_snapshots.litp_snapshots.get_nas_type', return_value='veritas')
class TestLitpSanSnapshots(TestCase):

    @patch('h_snapshots.snapshots_utils.api_builder')
    def setUp(self, mock_api_builder):
        mock_api_builder.return_value = MagicMock()
        self.logged = []

    def setup_model(self, pool_name, pool_id, snap_cdate,
                    snappable_lun_name, snappable_lunid,
                    nonsnap_lun_name, nonsnap_lunid,
                    m_navisec, pool_usage='80',
                    snaps_created=True):
        snap_name = 'L_{0}_'.format(snappable_lun_name)

        snappable_lun = litp_object(
                '/deployments/d/clusters/c/nodes/n1/system/disks/d1',
                'lun-disk', {'lun_name': snappable_lun_name,
                             'snap_size': '100',
                             'storage_container': pool_name})

        nonsnap_lun = litp_object(
                '/deployments/d/clusters/c/nodes/n1/system/disks/d2',
                'lun-disk', {'lun_name': nonsnap_lun_name,
                             'snap_size': '0',
                             'storage_container': pool_name})

        child_model = {
            '/deployments': [litp_object('/deployments/d', 'deployment')],
            '/deployments/d/clusters': [
                litp_object('/deployments/d/clusters/c', 'cluster')],
            '/deployments/d/clusters/c/nodes': [
                litp_object('/deployments/d/clusters/c/nodes/n1', 'node')],
            '/deployments/d/clusters/c/nodes/n1/system/disks': [
                snappable_lun, nonsnap_lun
            ],
            '/infrastructure/storage/storage_providers': [
                litp_object('/infrastructure/storage/storage_providers/san',
                            'san-emc',
                            {
                                "username": "admin",
                                "name": "atvnx-77",
                                "storage_network": "storage",
                                "storage_site_id": pool_name,
                                "login_scope": "global",
                                "ip_a": "10.32.231.48",
                                "ip_b": "10.32.231.49",
                                "san_type": "vnx2",
                                "password_key": "key-for-san-atvnx-77"
                            })
            ],
            '/infrastructure/storage/storage_providers/'
            'san/storage_containers': [
                litp_object(
                        '/infrastructure/storage/storage_providers/'
                        'san/storage_containers/pool1',
                        'storage-container',
                        {
                            "type": "POOL",
                            "name": pool_name
                        }
                )
            ]
        }

        other_snap_name = 'some_other_snapshot'
        other_snap = SnapshotInfo(resource_lun_id='991',
                                  snapshot_name=other_snap_name,
                                  created_time=snap_cdate,
                                  snap_state='Ready',
                                  resource_lun_name=nonsnap_lun_name,
                                  description=None)

        created_snap = SnapshotInfo(resource_lun_id=snappable_lunid,
                                  snapshot_name=snap_name,
                                  created_time=snap_cdate,
                                  snap_state='Ready',
                                  resource_lun_name=snappable_lun_name,
                                  description=None)

        snap_list_results = [other_snap]
        if snaps_created:
            snap_list_results.append(created_snap)

        m_navisec.return_value.list_all_snaps.return_value = snap_list_results

        snap_lun = LunInfo(lun_id=snappable_lunid,
                           name=snappable_lun_name,
                           uid='sadasd',
                           container=pool_name,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        non_snap_lun = LunInfo(lun_id=nonsnap_lunid,
                           name=nonsnap_lun_name,
                           uid='d33333',
                           container=pool_name,
                           size='100Gb',
                           container_type='StoragePool',
                           raid='5')

        m_navisec.return_value.list_all_luns.return_value = [snap_lun,
                                                             non_snap_lun]

        storage_pool = StoragePoolInfo(name=pool_name,
                                       ident=pool_id,
                                       raid='5',
                                       size='20Tb',
                                       available='Ready',
                                       perc_full=pool_usage,
                                       perc_sub=pool_usage)

        m_navisec.return_value.get_storagepool_info.return_value = storage_pool
        return child_model

    @patch('h_snapshots.litp_snapshots.NavisecCLI')
    @patch('h_snapshots.litp_snapshots.Decryptor')
    def test_get_snapshots_no_litpcrypt(self, m_decryptor, m_navisec, m_nas_type):
        test_class = MockedLitpSanSnapshots(verbose=True)
        test_class.child_model = self.setup_model(
                'p', '1', '', '', '', '', '', m_navisec
        )
        m_decryptor.return_value.get_password.side_effect = NoSectionError('')

        self.assertRaises(LitpSnapError, test_class.get_snapshots)

    @patch('h_snapshots.litp_snapshots.NavisecCLI')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_list_snapshots(self, m_get_password, m_navisec, m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        san_pool = 'ENM223'
        san_pool_id = '223'

        snappable_lun_name = 'LITP2_{0}_snappable'.format(san_pool)
        snappable_lunid = '99'

        nonsnap_lun_name = 'LITP2_{0}_nonsnap'.format(san_pool)
        nonsnap_lunid = '101'

        snap_cdate = '01/22/16 15:59:22'

        test_class = MockedLitpSanSnapshots(verbose=True)
        test_class.child_model = self.setup_model(
                san_pool, san_pool_id, snap_cdate,
                snappable_lun_name, snappable_lunid,
                nonsnap_lun_name, nonsnap_lunid,
                m_navisec
        )

        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder

        test_class.list_snapshots('snapshot', detailed=True)
        check_str = '\n'.join(self.logged)

        self.assertTrue(
                'SAN - Pool:{0}/{1}'.format(san_pool,
                                            san_pool_id) in check_str)
        self.assertTrue(
                'SAN - LUN:{0}/{1}/{2}'.format(san_pool,
                                               snappable_lun_name,
                                               snappable_lunid) in check_str)

        self.assertTrue('Creation: "{0}"'.format(snap_cdate) in check_str)
        self.assertTrue('State: "Ready"' in check_str)

    @patch('h_snapshots.litp_snapshots.NavisecCLI')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_list_snapshot_NO_SNAP(self, m_get_password, m_navisec, m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        san_pool = 'ENM223'
        san_pool_id = '223'

        snappable_lun_name = 'LITP2_{0}_snappable'.format(san_pool)
        snappable_lunid = '99'

        nonsnap_lun_name = 'LITP2_{0}_nonsnap'.format(san_pool)
        nonsnap_lunid = '101'

        snap_cdate = '01/22/16 15:59:22'

        test_class = MockedLitpSanSnapshots(verbose=True)
        test_class.child_model = self.setup_model(
                san_pool, san_pool_id, snap_cdate,
                snappable_lun_name, snappable_lunid,
                nonsnap_lun_name, nonsnap_lunid,
                m_navisec, snaps_created=False
        )
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder

        test_class.list_snapshots('snapshot', detailed=True)

        self.assertTrue(
                'SAN - LUN:{0}/{1}/{2}     - N/A'.format(san_pool,
                                                         snappable_lun_name,
                                                         snappable_lunid) in
                '\n'.join(self.logged))

    @patch('h_snapshots.litp_snapshots.NavisecCLI')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_validate_snapshot_POOL_FULL(self, m_get_password, m_navisec, m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        san_pool = 'ENM223'
        san_pool_id = '223'

        snappable_lun_name = 'LITP2_{0}_snappable'.format(san_pool)
        snappable_lunid = '99'

        nonsnap_lun_name = 'LITP2_{0}_nonsnap'.format(san_pool)
        nonsnap_lunid = '101'

        snap_cdate = '01/22/16 15:59:22'

        usage = '100'

        test_class = MockedLitpSanSnapshots(verbose=True)
        test_class.child_model = self.setup_model(
                san_pool, san_pool_id, snap_cdate,
                snappable_lun_name, snappable_lunid,
                nonsnap_lun_name, nonsnap_lunid,
                m_navisec, pool_usage=usage
        )
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder

        snaps_ok = test_class.validate_snapshots('snapshot')
        self.assertFalse(snaps_ok)

        check_str = '\n'.join(self.logged)

        self.assertTrue(
                'SAN - Pool "{0}" total subscription '
                'is {1}%'.format(san_pool, usage) in check_str)

    @patch('h_snapshots.litp_snapshots.NavisecCLI')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_validate_snapshot_NO_SNAP(self, m_get_password, m_navisec, m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        san_pool = 'ENM223'
        san_pool_id = '223'

        snappable_lun_name = 'LITP2_{0}_snappable'.format(san_pool)
        snappable_lunid = '99'

        nonsnap_lun_name = 'LITP2_{0}_nonsnap'.format(san_pool)
        nonsnap_lunid = '101'

        snap_cdate = '01/22/16 15:59:22'

        test_class = MockedLitpSanSnapshots(verbose=True)
        test_class.child_model = self.setup_model(
                san_pool, san_pool_id, snap_cdate,
                snappable_lun_name, snappable_lunid,
                nonsnap_lun_name, nonsnap_lunid,
                m_navisec, snaps_created=False
        )
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder

        snaps_ok = test_class.validate_snapshots('snapshot')
        self.assertFalse(snaps_ok)
        self.assertEqual(
                'SAN - Could not find snapshot named "L_{1}_" for {0}/{1}/{2}'
                ''.format(san_pool, snappable_lun_name, snappable_lunid),
                self.logged[0]
        )

@patch('h_snapshots.litp_snapshots.get_nas_type', return_value='veritas')
class TestLitpNasSnapshots(TestCase):

    def setUp(self):
        self.logged = []

    def setup_model(self, pool_name, cache_name, snap_cdate,
                    snappable_fs_name, snappable_fs_snap_name,
                    nonsnap_fs_name, m_nasconsole,
                    create_snap=True, create_cache=True,
                    cache_usage='20'):
        p_sp = '/infrastructure/storage/storage_providers'
        model = {
            p_sp: [
                litp_object(p_sp + '/sfs',
                            'sfs-service',
                            {
                                "management_ipv4": "10.140.1.29",
                                "user_name": "support",
                                "name": "atsfsx148mgt",
                                "password_key": "key-for-sfs"
                            })
            ],
            p_sp + '/sfs/pools': [
                litp_object(p_sp + '/sfs/pools/{0}'.format(pool_name),
                            'sfs-pool', {"name": pool_name}
                            )
            ],
            p_sp + '/sfs/pools/{0}/cache_objects'.format(pool_name): [
                litp_object('/infrastructure/storage/storage_providers/sfs/'
                            'pools/{0}/cache_objects/cache'.format(pool_name),
                            'sfs-cache', {"name": cache_name})
            ],
            p_sp + '/sfs/pools/{0}/file_systems'.format(pool_name): [
                litp_object(
                        p_sp + '/sfs/pools/{0}/file_systems/snappable'.format(
                                pool_name), 'sfs-filesystem', {
                            "path": "/vx/{0}".format(snappable_fs_name),
                            "size": "5G",
                            "cache_name": cache_name,
                            "snap_size": "40"
                        }),
                litp_object(
                        p_sp + '/sfs/pools/{0}/file_systems/'
                               'non_snappable'.format(pool_name),
                        'sfs-filesystem', {
                            "path": "/vx/{0}".format(nonsnap_fs_name),
                            "size": "5G",
                            "cache_name": cache_name,
                            "snap_size": "0"})
            ]
        }

        caches = {
            'other-cache': {'size_mb': '20480', 'used_perc': '0'}
        }
        if create_cache:
            caches[cache_name] = {'size_mb': '20480',
                                  'used_perc': cache_usage}

        m_nasconsole.return_value.storage_rollback_cache_list.return_value = \
            caches

        snaps = []
        snaps_data = {}
        if create_snap:
            snaps.append('L_{0}_'.format(snappable_fs_name))
            snaps_data[snappable_fs_snap_name] = {
                'SNAPDATE': snap_cdate,
                'TYPE': 'spaceopt',
                'NAME': snappable_fs_snap_name,
                'SYNCED_DATA': '111K(0.0%)',
                'CHANGED_DATA': '222K(0.0%)',
                'CREATIONTIME': '222K(0.0%)'
            }

        m_nasconsole.return_value.storage_rollback_list.return_value = {
            snappable_fs_name: snaps
        }

        m_nasconsole.return_value.storage_rollback_info.return_value = \
            snaps_data

        return model

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor')
    def test_get_snapshots_no_litpcrypt(self, m_decryptor, m_nasconsole,
                                        m_nas_type):
        test_class = MockedLitpNasSnapshots(verbose=True)
        test_class.child_model = self.setup_model(
                '', '', '', '', '', '', m_nasconsole)
        m_decryptor.return_value.get_password.side_effect = NoSectionError('')

        self.assertRaises(LitpSnapError, test_class.get_snapshots, False)

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_list_snapshots_OK(self, m_get_password, m_nasconsole,
                               m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole)
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder

        test_class.list_snapshots('snapshot', detailed=True)
        self.assertEqual(2, len(self.logged))

        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'NAS - Cache:{0}/{1}\s+-.*'.format(
                        pool_name, cache_name
                ))

        self.assertRegexpMatches(
                ''.join(self.logged),
               r'NAS - FS:{0}/{1}\s+- {2}.*'.format(
                        pool_name, snappable_name,
                        snappable_snap_name
                ))

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_list_snapshots_NO_SNAP(self, m_get_password, m_nasconsole,
                                    m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole,
                                                  create_snap=False)
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder

        test_class.list_snapshots('snapshot', detailed=True)

        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'NAS - Cache:{0}/{1}\s+-.*'.format(
                        pool_name, cache_name
                ))

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_list_snapshots_NO_CACHE(self, m_get_password, m_nasconsole,
                                     m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'
        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole,
                                                  create_cache=False)
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder

        test_class.list_snapshots('snapshot', detailed=True)

        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'NAS - Cache:{0}/{1}\s+-.*'.format(
                        pool_name, cache_name
                ))

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_validate_snapshots_OK(self, m_get_password, m_nasconsole,
                                   m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole)
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder

        ok = test_class.validate_snapshots('snapshot')
        self.assertTrue(ok)

        self.assertRegexpMatches(
                ' '.join(self.logged),
                'NAS - Pool {0} has expected cache "{1}"'.format(
                        pool_name, cache_name
                ))

        self.assertRegexpMatches(
                ' '.join(self.logged),
                'NAS - {0}/{1} has expected snapshot "{2}"'.format(
                        pool_name, snappable_name,
                        snappable_snap_name
                ))

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_validate_snapshots_NO_CACHE(self, m_get_password, m_nasconsole,
                                         m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'
        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole,
                                                  create_cache=False)
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder

        ok = test_class.validate_snapshots('snapshot')

        self.assertFalse(ok)
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'NAS - Could not find rollback cache named "{0}" '
                'for pool {1}'.format(
                        cache_name, pool_name
                ))
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'NAS - {0}/{1} has expected snapshot "{2}"'.format(
                        pool_name, snappable_name,
                        snappable_snap_name
                ))

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_validate_snapshots_NO_SNAP(self, m_get_password, m_nasconsole,
                                        m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole,
                                                  create_snap=False)
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder

        ok = test_class.validate_snapshots('snapshot')
        self.assertFalse(ok)
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'NAS - Pool {0} has expected cache "{1}"'.format(
                        pool_name, cache_name
                ))
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'Could not find snapshot named "{0}" for '
                'testpool/testpool-snappable'.format(
                        snappable_snap_name, pool_name, snappable_name,

                ))

    @patch('h_snapshots.litp_snapshots.NasConsole')
    @patch('h_snapshots.litp_snapshots.Decryptor.get_password')
    def test_validate_snapshots_CACHE_USAGE(self, m_get_password,
                                            m_nasconsole, m_nas_type):
        m_get_password.return_value = 'ljasdlkdj'

        pool_name = 'testpool'
        cache_name = "{0}_cache".format(pool_name)
        snappable_name = '{0}-snappable'.format(pool_name)
        snappable_snap_name = 'L_{0}_'.format(snappable_name)
        nonsnappable_name = '{0}-nonsnap'.format(pool_name)
        create_date = '2016/01/28 08:50'
        test_class = MockedLitpNasSnapshots()
        test_class.child_model = self.setup_model(pool_name, cache_name,
                                                  create_date,
                                                  snappable_name,
                                                  snappable_snap_name,
                                                  nonsnappable_name,
                                                  m_nasconsole,
                                                  cache_usage='100')
        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder
        ok = test_class.validate_snapshots('snapshot')

        self.assertFalse(ok)
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'NAS - Rollback cache {0} for pool {1} is at 100.0% '
                'usage!'.format(
                        cache_name, pool_name
                ))


@patch('h_snapshots.litp_snapshots.get_nas_type', return_value='veritas')
class TestLitpVolMgrSnapshots(TestCase):
    def setup_child_model(self, vg_name, vg_id, lms_hostname,
                          snappable_fs, snappable_fs_snap,
                          ks_fs, ks_fs_snap,
                          m_lvs_list, m_exec_process,
                          create_snap=True,
                          invalid_snap=False):
        child_model = {
            '/ms/system/disks': [
                litp_object('/ms/system/disks/disk0', 'disk', {
                    'name': 'ms_hd0'
                })
            ],
            '/ms/storage_profile/volume_groups': [
                litp_object('/ms/storage_profile/volume_groups/'
                            '{0}'.format(vg_id),
                            'volume-group', {
                                'volume_group_name': vg_name
                            })
            ],
            '/ms/storage_profile/volume_groups/{0}/'
            'physical_devices'.format(vg_id): [
                litp_object('/ms/storage_profile/volume_groups/{0}/'
                            'physical_devices/pd1'.format(vg_id),
                            'physical-device',
                            {'device_name': 'ms_hd0'})
            ],
            '/ms/storage_profile/volume_groups/{0}/file_systems'.format(
                    vg_id): [
                litp_object('/ms/storage_profile/volume_groups/{0}/'
                            'file_systems/fs_data'.format(vg_id),
                            'file-system', {
                                'snap_size': '20'
                            })
            ],
            '/deployments': [litp_object('/deployments/d', 'deployment')],
            '/deployments/d/clusters': [
                litp_object('/deployments/d/clusters/c', 'cluster')],
            '/deployments/d/clusters/c/nodes': [
                litp_object('/deployments/d/clusters/c/nodes/n1', 'node')],
            '/deployments/d/clusters/c/nodes/n1/system/disks': [
                litp_object(
                        '/deployments/d/clusters/c/nodes/n1/system/disks/d1',
                        'lun-disk', {'lun_name': 'LITP2_ENM223_appsvc1',
                                     'snap_size': '100',
                                     'storage_container': 'ENM223'})
            ],
            '/deployments/d/clusters/c/nodes/n1/storage_profile/'
            'volume_groups': [
                litp_object('/deployments/d/clusters/c/nodes/n1/'
                            'storage_profile/volume_groups/vg1',
                            'volume-group')
            ],
            '/deployments/d/clusters/c/nodes/n1/storage_profile/'
            'volume_groups/vg1/physical_devices': [
                litp_object('/deployments/d/clusters/c/nodes/n1/'
                            'storage_profile/volume_groups/vg1/'
                            'physical_devices/internal', 'physical-device')
            ]
        }

        lvm_data = [
            'File descriptor 5 (socket:[25860534]) leaked on lvs '
            'invocation. Parent PID 20973: /usr/bin/python',
            'Input/output error',
            '{0},,swi-a-s---,/dev/{1}/{0},{1},{2},,0.00,'
            '2016-01-28 11:13:14 +0000'.format(ks_fs_snap, vg_name, ks_fs),
            '{0},,owi-aos---,/dev/{1}/{0},{1},,unknown,,'
            '2016-01-15 09:54:48 +0000'.format(ks_fs, vg_name),
            'lv_swap,,-wi-ao----,/dev/{0}/lv_swap,{0},,unknown,,'
            '2016-01-15 09:54:47 +0000'.format(vg_name),
            '{1},,owi-aos---,/dev/{0}/{1},{0}'
            ',,unknown,,'
            '2016-01-15 10:57:37 +0000'.format(vg_name, snappable_fs)
        ]
        if create_snap:
            _invalid_snap = ''
            if invalid_snap:
                _invalid_snap = 'lv_snapshot_invalid'
            lvm_data.append('{0},,swi-a-s---,/dev/{1}/'
                            '{0},{1},{2},{3},0.00,'
                            '2016-01-28 11:13:13 '
                            '+0000'.format(snappable_fs_snap,
                                           vg_name,
                                           snappable_fs,
                                           _invalid_snap))

        mcodata = list(lvm_data)
        mcodata.insert(0, LitpVolMgrSnapshots.LV_OPTS)

        m_lvs_list.return_value = {lms_hostname: '\n'.join(mcodata)}

        # Only host with LVM's at the time of writing was the LMS but vApps
        # probably have them too now

        def p_exec_process(args):
            if 'lvs' in args[0]:
                return '\n'.join(lvm_data)
            elif 'blkid' in args[0]:
                if 'swap' in args[-1]:
                    return 'TYPE=swap'
                else:
                    return 'TYPE=ext4'
            else:
                raise KeyError('No exec_process setup for {0'.format(args))

        m_exec_process.side_effect = p_exec_process

        return child_model

    def setup_get_model(self, lms_hostname):
        return {
            '/ms': litp_object('/ms', 'ms', {'hostname': lms_hostname}),
            '/ms/system': litp_object('/ms/system', 'system'),
            '/deployments/d/clusters/c/nodes/n1/system':
                litp_object('/deployments/d/clusters/c/nodes/n1/system',
                            'blade')
        }

    @patch('h_snapshots.litp_snapshots.exec_process')
    @patch('h_snapshots.litp_snapshots.EnminstAgent.lvs_list')
    def test_list_snapshots_OK(self, m_lvs_list, m_exec_process,
                               m_nas_type):
        test_class = MockedLitpVolMgrSnapshots()
        vg_name = 'testvg'
        vg_id = 'tvg'
        lms_hostname = 'lmshostname'
        snappable_fs = '{0}_fs_data'.format(vg_id)
        snappable_fs_snap = 'L_{0}_'.format(snappable_fs)

        ks_fs = 'lv_home'
        ks_fs_snap = 'L_lv_home_'

        test_class.child_model = self.setup_child_model(vg_name, vg_id,
                                                        lms_hostname,
                                                        snappable_fs,
                                                        snappable_fs_snap,
                                                        ks_fs,
                                                        ks_fs_snap,
                                                        m_lvs_list,
                                                        m_exec_process)
        test_class.get_model = self.setup_get_model(lms_hostname)

        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.list_snapshots('snapshot', detailed=True)
        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'VOL - {0}/{1}/{2}\s+- {3}.*'.format(lms_hostname, vg_name,
                                                     snappable_fs,
                                                     snappable_fs_snap)
        )
        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'VOL - {0}/{1}/{2}\s+- {3}.*'.format(lms_hostname, vg_name,
                                                     ks_fs,
                                                     ks_fs_snap)
        )

    @patch('h_snapshots.litp_snapshots.exec_process')
    @patch('h_snapshots.litp_snapshots.EnminstAgent.lvs_list')
    def test_list_snapshots_NO_SNAP(self, m_lvs_list, m_exec_process,
                                    m_nas_type):
        test_class = MockedLitpVolMgrSnapshots()
        vg_name = 'testvg'
        vg_id = 'tvg'
        lms_hostname = 'lmshostname'
        snappable_fs = '{0}_fs_data'.format(vg_id)
        snappable_fs_snap = 'L_{0}_'.format(snappable_fs)

        ks_fs = 'lv_home'
        ks_fs_snap = 'L_{0}_'.format(ks_fs)

        test_class.child_model = self.setup_child_model(vg_name, vg_id,
                                                        lms_hostname,
                                                        snappable_fs,
                                                        snappable_fs_snap,
                                                        ks_fs,
                                                        ks_fs_snap,
                                                        m_lvs_list,
                                                        m_exec_process,
                                                        create_snap=False)
        test_class.get_model = self.setup_get_model(lms_hostname)

        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.list_snapshots('snapshot', detailed=True)

        print '\n'.join(self.logged)
        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'VOL - {0}/{1}/{2}\s+- N/A.*'.format(lms_hostname,
                                                     vg_name,
                                                     snappable_fs)
        )
        self.assertRegexpMatches(
                ' '.join(self.logged),
               r'VOL - {0}/{1}/{2}\s+ - {3}'.format(lms_hostname,
                                                    vg_name,
                                                    ks_fs,
                                                    ks_fs_snap)
        )

    @patch('h_snapshots.litp_snapshots.exec_process')
    @patch('h_snapshots.litp_snapshots.EnminstAgent.lvs_list')
    def test_validate_snapshots_OK(self, m_lvs_list, m_exec_process,
                                   m_nas_type):
        test_class = MockedLitpVolMgrSnapshots()
        vg_name = 'testvg'
        vg_id = 'tvg'
        lms_hostname = 'lmshostname'
        snappable_fs = '{0}_fs_data'.format(vg_id)
        snappable_fs_snap = 'L_{0}_'.format(snappable_fs)

        ks_fs = 'lv_home'
        ks_fs_snap = 'L_lv_home_'

        test_class.child_model = self.setup_child_model(vg_name, vg_id,
                                                        lms_hostname,
                                                        snappable_fs,
                                                        snappable_fs_snap,
                                                        ks_fs,
                                                        ks_fs_snap,
                                                        m_lvs_list,
                                                        m_exec_process)
        test_class.get_model = self.setup_get_model(lms_hostname)

        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        ok = test_class.validate_snapshots('snapshot')
        self.assertTrue(ok)
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'VOL - {0}/{1}/{2} has expected snapshot "{3}"'.format(
                        lms_hostname, vg_name,
                        snappable_fs,
                        snappable_fs_snap)
        )

    @patch('h_snapshots.litp_snapshots.exec_process')
    @patch('h_snapshots.litp_snapshots.EnminstAgent.lvs_list')
    def test_validate_snapshots_NO_SNAP(self, m_lvs_list, m_exec_process,
                                        m_nas_type):
        test_class = MockedLitpVolMgrSnapshots()
        vg_name = 'testvg'
        vg_id = 'tvg'
        lms_hostname = 'lmshostname'
        snappable_fs = '{0}_fs_data'.format(vg_id)
        snappable_fs_snap = 'L_{0}_'.format(snappable_fs)

        ks_fs = 'lv_home'
        ks_fs_snap = 'L_{0}_'.format(ks_fs)

        test_class.child_model = self.setup_child_model(vg_name, vg_id,
                                                        lms_hostname,
                                                        snappable_fs,
                                                        snappable_fs_snap,
                                                        ks_fs,
                                                        ks_fs_snap,
                                                        m_lvs_list,
                                                        m_exec_process,
                                                        create_snap=False)
        test_class.get_model = self.setup_get_model(lms_hostname)

        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder
        ok = test_class.validate_snapshots('snapshot')
        self.assertFalse(ok)
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'VOL - Could not find snapshot named '
                '"{0}" for {1}/{2}'.format(snappable_fs_snap,
                                           vg_name,
                                           snappable_fs)
        )

    @patch('h_snapshots.litp_snapshots.exec_process')
    @patch('h_snapshots.litp_snapshots.EnminstAgent.lvs_list')
    def test_validate_snapshots_INVALID_SNAP(self, m_lvs_list, m_exec_process,
                                             m_nas_type):
        test_class = MockedLitpVolMgrSnapshots()
        vg_name = 'testvg'
        vg_id = 'tvg'
        lms_hostname = 'lmshostname'
        snappable_fs = '{0}_fs_data'.format(vg_id)
        snappable_fs_snap = 'L_{0}_'.format(snappable_fs)

        ks_fs = 'lv_home'
        ks_fs_snap = 'L_{0}_'.format(ks_fs)

        test_class.child_model = self.setup_child_model(vg_name, vg_id,
                                                        lms_hostname,
                                                        snappable_fs,
                                                        snappable_fs_snap,
                                                        ks_fs,
                                                        ks_fs_snap,
                                                        m_lvs_list,
                                                        m_exec_process,
                                                        invalid_snap=True)
        test_class.get_model = self.setup_get_model(lms_hostname)

        self.logged = []

        def recorder(msg):
            self.logged.append(msg)

        test_class.info = recorder
        test_class.error = recorder
        ok = test_class.validate_snapshots('snapshot')
        self.assertFalse(ok)
        self.assertRegexpMatches(
                ' '.join(self.logged),
                'VOL - {0}/{1}/{2} has INVALID snapshot "{3}"'.format(
                        lms_hostname, vg_name, snappable_fs,
                        snappable_fs_snap)
        )


@patch('h_snapshots.litp_snapshots.get_nas_type', return_value='veritas')
class TestLitpSnapshots(TestCase):
    @patch('h_snapshots.litp_snapshots.init_enminst_logging')
    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    def test_list_snapshot_names(self, m_litp, m_init_enminst_logging, m_nas_type):
        m_log = MagicMock()
        m_info = MagicMock()
        m_log.info = m_info

        m_init_enminst_logging.return_value = m_log
        m_litp.return_value.list_snapshots.return_value = []

        test_class = LitpSnapshots()
        test_class.list_snapshot_names()
        m_info.assert_has_calls([
            call.info('No modeled snapshots found.')
        ], any_order=True)

        m_info.reset_mock()
        m_litp.return_value.list_snapshots.return_value = ['snapshot']
        test_class.list_snapshot_names()
        m_info.assert_has_calls([
            call.info('Modeled named snapshot: snapshot')
        ], any_order=True)

        m_info.reset_mock()
        m_litp.return_value.list_snapshots.return_value = ['snapshot', 'ombs']
        test_class.list_snapshot_names()
        m_info.assert_has_calls([
            call.info('Modeled named snapshot: snapshot'),
            call.info('Modeled named snapshot: ombs')
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    def test_list_snapshots_NO_MODELSNAP_NO_FORCE(self, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = []
        with self.assertRaises(SystemExit) as error:
            test_class.list_snapshots('snapshot', detailed=True,
                                      force=False, verbose=True)
        self.assertEqual(ExitCodes.LITP_NO_NAMED_SNAPS_EXIST,
                         error.exception.code)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_list_snapshots_NO_MODELSNAP_FORCE(self, m_volmgr, m_nas,
                                               m_san, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = []
        test_class.list_snapshots('snapshot', detailed=True,
                                  force=True, verbose=True)

        m_volmgr.assert_has_calls([
            call().list_snapshots('snapshot', True)
        ], any_order=True)
        m_nas.assert_has_calls([
            call().list_snapshots('snapshot', True)
        ], any_order=True)
        m_san.assert_has_calls([
            call().list_snapshots('snapshot', True)
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_list_snapshots_OK(self, m_volmgr, m_nas, m_san, m_litp,
                               m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = [
            'snapshot'
        ]
        test_class.list_snapshots('snapshot', detailed=False,
                                  force=False, verbose=True)

        m_volmgr.assert_has_calls([
            call().list_snapshots('snapshot', False)
        ], any_order=True)
        m_nas.assert_has_calls([
            call().list_snapshots('snapshot', False)
        ], any_order=True)
        m_san.assert_has_calls([
            call().list_snapshots('snapshot', False)
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_validate_snapshots_OK(self, m_volmgr, m_nas, m_san, m_litp,
                                   m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = [
            'snapshot'
        ]
        m_volmgr.return_value.validate_snapshots.side_effect = [True]
        m_nas.return_value.validate_snapshots.side_effect = [True]
        m_san.return_value.validate_snapshots.side_effect = [True]

        test_class.validate_snapshots('snapshot', verbose=False,
                                      force=False)

        m_volmgr.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_nas.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_san.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    def test_validate_snapshots_NO_MODELSNAP_NO_FORCE(self, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = []

        with self.assertRaises(SystemExit) as error:
            test_class.validate_snapshots('snapshot',
                                          force=False,
                                          verbose=True)
        self.assertEqual(ExitCodes.LITP_NO_NAMED_SNAPS_EXIST,
                         error.exception.code)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_validate_snapshots_NO_MODELSNAP_FORCE(self, m_volmgr, m_nas,
                                                   m_san, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = []

        m_volmgr.return_value.validate_snapshots.side_effect = [True]
        m_nas.return_value.validate_snapshots.side_effect = [True]
        m_san.return_value.validate_snapshots.side_effect = [True]

        test_class.validate_snapshots('snapshot', force=True, verbose=True)

        m_volmgr.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_nas.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_san.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_validate_snapshots_VOLMGR_ERROR(self, m_volmgr, m_nas,
                                             m_san, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = [
            'snapshot'
        ]

        m_volmgr.return_value.validate_snapshots.side_effect = [False]
        m_nas.return_value.validate_snapshots.side_effect = [True]
        m_san.return_value.validate_snapshots.side_effect = [True]

        with self.assertRaises(SystemExit) as error:
            test_class.validate_snapshots('snapshot',
                                          force=False,
                                          verbose=True)
        self.assertEqual(ExitCodes.LITP_SNAP_ERROR,
                         error.exception.code)

        m_volmgr.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_nas.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_san.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_validate_snapshots_NAS_ERROR(self, m_volmgr, m_nas,
                                          m_san, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = [
            'snapshot'
        ]

        m_volmgr.return_value.validate_snapshots.side_effect = [True]
        m_nas.return_value.validate_snapshots.side_effect = [False]
        m_san.return_value.validate_snapshots.side_effect = [True]

        with self.assertRaises(SystemExit) as error:
            test_class.validate_snapshots('snapshot',
                                          force=False,
                                          verbose=True)
        self.assertEqual(ExitCodes.LITP_SNAP_ERROR,
                         error.exception.code)

        m_volmgr.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_nas.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_san.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    @patch('h_snapshots.litp_snapshots.LitpSanSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpNasSnapshots')
    @patch('h_snapshots.litp_snapshots.LitpVolMgrSnapshots')
    def test_validate_snapshots_SAN_ERROR(self, m_volmgr, m_nas,
                                          m_san, m_litp, m_nas_type):
        test_class = LitpSnapshots()
        m_litp.return_value.list_snapshots.return_value = [
            'snapshot'
        ]

        m_volmgr.return_value.validate_snapshots.side_effect = [True]
        m_nas.return_value.validate_snapshots.side_effect = [True]
        m_san.return_value.validate_snapshots.side_effect = [False]

        with self.assertRaises(SystemExit) as error:
            test_class.validate_snapshots('snapshot',
                                          force=False,
                                          verbose=True)
        self.assertEqual(ExitCodes.LITP_SNAP_ERROR,
                         error.exception.code)

        m_volmgr.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_nas.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)
        m_san.assert_has_calls([
            call().validate_snapshots('snapshot')
        ], any_order=True)

    def test_get_snapshot_name(self, m_nas_type):
        self.assertEqual('L_fs_', get_volume_snapshot_name('fs', 'snapshot'))
        self.assertEqual('fs_ombs', get_volume_snapshot_name('fs', 'ombs'))
        self.assertEqual('fs_rolling1', get_volume_snapshot_name('fs',
                                                                 'rolling1'))

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    def test_get(self, m_litp, m_nas_type):
        _json = litp_json('/path', 'item-type', {'p': 'v'})
        m_litp.return_value.get.side_effect = [_json]
        m_litp.return_value.path_parser.side_effect = ['/path']

        test_class = LitpBaseSnapshots(verbose=False)
        _litp_object = test_class.get('/path')
        self.assertEqual('/path', _litp_object.path)
        self.assertEqual('item-type', _litp_object.item_type)
        self.assertEqual('v', _litp_object.get_property('p'))

    @patch('h_snapshots.litp_snapshots.LitpRestClient')
    def test_get_children(self, m_litp, m_nas_type):
        _json_c1 = litp_json('/path/c1', 'item-type', {'p': 'v'})
        _json_c2 = litp_json('/path/c2', 'item-type', {'p': 'v'})
        m_litp.return_value.get_children.side_effect = [
            [{'data': _json_c1}, {'data': _json_c2}]
        ]
        test_class = LitpBaseSnapshots(verbose=False)
        children = test_class.get_children('/path')
        self.assertEqual(2, len(children))
        self.assertEqual('c1', children[0].item_id)
        self.assertEqual('c2', children[1].item_id)

    @patch('h_snapshots.litp_snapshots.init_enminst_logging')
    def test_log(self, m_init_enminst_logging, m_nas_type):
        m_log = MagicMock()
        m_info = MagicMock()
        m_error = MagicMock()
        m_debug = MagicMock()
        m_log.info = m_info
        m_log.error = m_error
        m_log.debug = m_debug
        m_init_enminst_logging.return_value = m_log

        test_class = LitpBaseSnapshots(verbose=False)

        test_class.info('info_message')
        m_info.assert_has_calls([call.info('info_message')])

        test_class.error('error_message')
        m_error.assert_has_calls([call.info('error_message')])

        test_class.debug('debug_message')
        m_debug.assert_has_calls([call.info('debug_message')])
