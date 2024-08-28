from mock import patch, Mock, MagicMock
from unittest2.case import TestCase

from h_hc.hc_san import SanHealthChecks
from h_litp.litp_utils import LitpObject
from h_util.h_utils import read_enminst_config
from litpd import LitpIntegration
from sanapi import SanApiIntegration
from sanapiexception import SanApiOperationFailedException

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.nasexceptions'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

class TestSanHealthChecks(TestCase):
    # noinspection PyPep8Naming
    def __init__(self, methodName='runTest'):
        super(TestSanHealthChecks, self).__init__(methodName)
        self.read_value = 0
        self.test_site_id = 'somerandomthing'
        self.test_pool_name = 'ENM123'
        self.test_san_name = 'san1'
        self.p_san = '/infrastructure/storage/storage_providers/' + \
                     self.test_san_name
        self.p_sg = self.p_san + '/storage_containers/' + self.test_pool_name
        self.litpd = LitpIntegration()

    def setUp(self):
        super(TestSanHealthChecks, self).setUp()
        self.litpd.setup_empty_model()
        self.litpd.setup_storagepool(self.test_san_name, self.test_site_id,
                                     self.test_pool_name)
        self.litpd.setup_db_cluster(node_count=2,
                                    storage_pool=self.test_pool_name)
        self.litpd.setup_svc_cluster(self.test_pool_name)
        self.litpd.setup_shared_lun(self.test_pool_name, ['db-1', 'db-2'])

    @patch('h_hc.hc_san.LitpRestClient')
    def test_get_modeled_providers(self, p_litp):
        p_litp.return_value = self.litpd

        hc = SanHealthChecks(verbose=True)
        containers = hc._get_modeled_providers()
        self.assertEqual(1, len(containers))
        provider = containers.keys()[0]
        self.assertEqual(self.test_site_id, provider.get_property(
                SanHealthChecks.K_STORAGE_SITE_ID))

        pools = containers.get(provider)
        self.assertEqual(1, len(pools))
        self.assertEqual(self.test_pool_name,
                         pools[0].get_property(SanHealthChecks.K_NAME))

    @patch('h_hc.hc_san.BasePluginApi.get_password')
    @patch('h_hc.hc_san.LitpRestClient')
    def test_get_api(self, p_litp, p_get_password):
        p_get_password.return_value = 'password'
        p_litp.return_value = self.litpd

        hc = SanHealthChecks()
        san = LitpObject(None, self.litpd.get(self.p_san),
                         self.litpd.path_parser)
        a_api = hc._get_api(san)
        self.assertIsNotNone(a_api)
        self.assertTrue(a_api.initialised)

    @patch('h_hc.hc_san.LitpRestClient')
    def test_get_total_pool_required(self, p_litp):
        p_litp.return_value = self.litpd

        hc = SanHealthChecks()
        pools, snaps = hc._get_total_pool_required()
        self.assertIn(self.test_pool_name, pools)
        # 3x1G LUNs and one shared LUN 100M (shared to both db nodes)
        self.assertEqual(30820, pools[self.test_pool_name])
        self.assertEqual(4623, snaps[self.test_pool_name])

    @patch('h_hc.hc_san.LitpRestClient')
    def test_check_storagepool(self, p_litp):
        p_litp.return_value = self.litpd
        pool_gb = 4
        snap_gb = 1
        SanApiIntegration.setup_storage_pool(self.test_pool_name,
                                             pool_gb * 1024,
                                             snap_gb * 1024)
        hc = SanHealthChecks()
        sanapi = SanApiIntegration.api_builder('vnx2')
        san_type = 'vnx2'
        containers = hc._get_modeled_providers()
        modeled_pool = containers.values()[0][0]

        for max_usage, should_fail in [(25, True), (50, True), (75, False)]:
            exceeded = hc.check_storagepool(sanapi, modeled_pool, max_usage,
                                            pool_gb, snap_gb, False, san_type)
            self.assertEqual(exceeded, should_fail)

    @patch('h_hc.hc_san.BasePluginApi.get_password')
    @patch('h_hc.hc_san.LitpRestClient')
    def test_healthcheck_san_nosnaps(self, p_litp, p_get_password):
        p_get_password.return_value = 'password'
        p_litp.return_value = self.litpd
        hc = SanHealthChecks()

        config = read_enminst_config()
        san_watermark = int(config.get(SanHealthChecks.C_SAN_POOL_USE_NS))
        usage_mark = float(san_watermark) / 100

        total_pool_size = 51200  # 50Gb
        available_space = 1024  # 1Gb

        SanApiIntegration.setup_storage_pool(self.test_pool_name,
                                             total_pool_size,
                                             available_space)
        self.assertRaises(SystemExit, hc.healthcheck_san)

        # Reduce the usage below 71% of 95% of the total pool
        available_space = total_pool_size - (total_pool_size * (
            usage_mark - 0.6))
        SanApiIntegration.setup_storage_pool(self.test_pool_name,
                                             total_pool_size,
                                             available_space)
        SanApiIntegration.snapshot('some_site_id')
        try:
            hc.healthcheck_san()
        except SystemExit:
            self.fail('No usage error should have been raised!')

    @patch('h_hc.hc_san.BasePluginApi.get_password')
    @patch('h_hc.hc_san.LitpRestClient')
    def test_healthcheck_san_withsnaps(self, p_litp, p_get_password):
        p_get_password.return_value = 'password'
        p_litp.return_value = self.litpd
        hc = SanHealthChecks()

        config = read_enminst_config()
        san_watermark = int(config.get(SanHealthChecks.C_SAN_POOL_USE_WS))
        usage_mark = float(san_watermark) / 100

        total_pool_size = 51200  # 50Gb

        available_space = total_pool_size - (total_pool_size * (
            usage_mark + 0.05))
        SanApiIntegration.setup_storage_pool(self.test_pool_name,
                                             total_pool_size,
                                             available_space)

        SanApiIntegration.snapshot(self.test_site_id)
        self.assertRaises(SystemExit, hc.healthcheck_san)

        # Reduce the usage below 71% of 95% of the total pool
        available_space = total_pool_size - (total_pool_size * (
            usage_mark - 0.6))
        SanApiIntegration.setup_storage_pool(self.test_pool_name,
                                             total_pool_size,
                                             available_space)

        # Updated for TORF-281182
        # With snaps created, ensure the correct value is being used for
        # the check i.e. C_SAN_POOL_USE_WS
        config = read_enminst_config()
        expected_mark = int(config.get(SanHealthChecks.C_SAN_POOL_USE_WS))
        real_get_watermark = hc.get_watermark
        with patch('h_hc.hc_san.SanHealthChecks.get_watermark') as _stub:

            self.read_value = -1

            def stub_get_watermark1(snapshots_included):
                self.read_value = real_get_watermark(snapshots_included)
                return self.read_value

            _stub.side_effect = stub_get_watermark1
            try:
                hc.healthcheck_san()
            except SystemExit:
                self.fail('No usage error should have been raised!')

            self.assertEqual(expected_mark, self.read_value,
                             'SAN check using the wrong watermark value!')

        SanApiIntegration.clear_snapshots()
        # Clear the snaps and check C_SAN_POOL_USE_NS is being used
        expected_mark = int(config.get(SanHealthChecks.C_SAN_POOL_USE_NS))
        with patch('h_hc.hc_san.SanHealthChecks.get_watermark') as _stub:

            self.read_value = -1

            def stub_get_watermark2(snapshots_included):
                self.read_value = real_get_watermark(snapshots_included)
                return self.read_value

            _stub.side_effect = stub_get_watermark2
            try:
                hc.healthcheck_san()
            except SystemExit:
                self.fail('No usage error should have been raised!')

            self.assertEqual(expected_mark, self.read_value,
                             'SAN check using the wrong watermark value!')

    @patch('h_hc.hc_san.BasePluginApi.get_password')
    @patch('h_hc.hc_san.LitpRestClient')
    def test_healthcheck_san_sizeok(self, p_litp, p_get_password):
        p_get_password.return_value = 'password'
        p_litp.return_value = self.litpd
        hc = SanHealthChecks()

        total_pool_size = 10240  # 10G, not enough to hold the modeled sizes
        SanApiIntegration.setup_storage_pool(self.test_pool_name,
                                             total_pool_size,
                                             4096)

        self.assertRaises(SystemExit, hc.healthcheck_san)

    @patch('sanapi.SanApi.get_hw_san_alerts')
    @patch('sanapi.SanApi.get_filtered_san_alerts')
    def test_get_san_critical_alerts(self, m_get_filtered_san_alerts, m_hw):
        m_get_filtered_san_alerts.return_value = [Mock(message="Alert Message 1", description="Alert Description 1", severity=2, state=1),
                                                  Mock(message="Alert Message 2", description="Alert Description 2", severity=4, state=1),
                                                  Mock(message="Alert Message 3", description="Alert Description 3", severity=2, state=2)]

        sanapi = SanApiIntegration.api_builder('unity')
        m_hw.return_value = ["spa_mm_0: u'this component is degraded.'"]
        hc = SanHealthChecks()
        san_alerts, san_hw_alerts = hc.get_san_critical_alerts(sanapi, 'unity')

        self.assertEquals(len(san_alerts), 1)
        self.assertEqual(san_alerts[0].message, "Alert Message 1")
        self.assertEqual(san_alerts[0].description, "Alert Description 1")
        self.assertEqual(san_hw_alerts[0], "spa_mm_0: u'this component is degraded.'")

    @patch('h_hc.hc_san.LitpRestClient')
    @patch('h_hc.hc_san.SanHealthChecks.get_san_critical_alerts')
    @patch('h_hc.hc_san.BasePluginApi.get_password')
    def test_san_critical_alert_healthcheck_vnx(self, m_get_password,
                                                m_get_san_alerts,
                                                m_litp):
        m_get_password.return_value = 'password'
        m_litp.return_value = self.litpd
        hc = SanHealthChecks()

        m_get_san_alerts.return_value = None, None
        hc.san_critical_alert_healthcheck()

        self.assertTrue(m_get_san_alerts.called)

    @patch('h_hc.hc_san.LitpRestClient')
    @patch('h_hc.hc_san.SanHealthChecks.get_san_critical_alerts')
    @patch('h_hc.hc_san.BasePluginApi.get_password')
    def test_san_critical_alert_healthcheck_vnx_1(self, m_get_password,
                                                   m_get_san_alerts,
                                                   m_litp):
        m_get_password.return_value = 'password'
        m_litp.return_value = self.litpd
        hc = SanHealthChecks()

        hw_error = "HwErrMon: ECC Errors in 24 hours -DIMM DIMM_ECC Rank1 Error Overflow."
        m_get_san_alerts.return_value = None, hw_error
        self.assertRaises(SystemExit, hc.san_critical_alert_healthcheck)

    @patch('h_hc.hc_san.LitpRestClient')
    @patch('sanapi.SanApi.get_hw_san_alerts')
    @patch('sanapi.SanApi.get_filtered_san_alerts')
    @patch('h_hc.hc_san.BasePluginApi.get_password')
    def test_san_critical_alert_healthcheck_unity(self, m_get_password,
                                                  m_filtered_san_alerts,
                                                  m_hw_alerts,
                                                  m_litp):
        m_get_password.return_value = 'password'
        litp_int = LitpIntegration()
        litp_int.setup_empty_model()
        litp_int.setup_storagepool(self.test_san_name, self.test_site_id, self.test_pool_name, vnx_type='unity')

        m_filtered_san_alerts.return_value = [Mock(message="Alert Message 1", description="Alert Description 1", severity=2, state=1),
                                              Mock(message="Alert Message 2", description="Alert Description 2", severity=4, state=1),
                                              Mock(message="Alert Message 3", description="Alert Description 3", severity=2, state=2)]
        m_hw_alerts.return_value = [Mock(["0spa_mm_0: u'unknown error on this dimm.'",\
                                          "7spa_mm_1: u'minor error on this dimm.'"\
                                          "spb_mm_0: u'this component is  degraded.'"])]
        m_litp.return_value = litp_int
        hc = SanHealthChecks()
        for alert in m_hw_alerts:
            if alert[0] != "7" or "0":
                self.assertRaises(SystemExit, hc.san_critical_alert_healthcheck)

        self.assertRaises(SystemExit, hc.san_critical_alert_healthcheck)
        self.assertTrue(m_filtered_san_alerts.called)

    @patch('h_hc.hc_san.LitpRestClient')
    @patch('sanapi.SanApi.get_hw_san_alerts')
    @patch('sanapi.SanApi.get_filtered_san_alerts')
    @patch('h_hc.hc_san.BasePluginApi.get_password')
    def test_san_critical_alert_healthcheck_unity_no_alerts(self, m_get_password,
                                                            m_filtered_san_alerts,
                                                            m_hw_alerts,
                                                            m_litp):
        m_get_password.return_value = 'password'
        litp_int = LitpIntegration()
        litp_int.setup_empty_model()
        litp_int.setup_storagepool(self.test_san_name, self.test_site_id, self.test_pool_name, vnx_type='unity')

        m_filtered_san_alerts.return_value = []
        m_hw_alerts.return_value = []

        m_litp.return_value = litp_int
        hc = SanHealthChecks()

        hc.san_critical_alert_healthcheck()
        self.assertTrue(m_filtered_san_alerts.called)

    @patch('h_hc.hc_san.SanHealthChecks.san_minor_major_alerts')
    def test_san_minor_major_alerts(self, m_hw):
        m_hw.return_value = ["0spa_mm_0: u'unknown error on this dimm.'",\
                           "7spa_mm_1: u'minor error on this dimm.'"\
                           "spb_mm_0: u'this component is degraded.'"]
        hc = SanHealthChecks()
        for alert in m_hw:
            if alert == m_hw[2]:
                self.assertRaises(SystemExit, hc.san_minor_major_alerts(alert))
            elif alert == m_hw[0]:
                self.assertEqual(hc.san_minor_major_alerts(alert),"spa_mm_0: u'unknown error on this dimm.")
            else:
                self.assertEqual(hc.san_minor_major_alerts(alert),"spa_mm_1: u'minor error on this dimm.")
    @patch('sanapi.SanApi.get_filtered_san_alerts')
    def test_failed_to_get_filtered_san_critical_alerts(self, m_get_filtered_san_alerts):

        m_get_filtered_san_alerts.side_effect = SanApiOperationFailedException("Alerts query failed", 1)
        sanapi = SanApiIntegration.api_builder('unity')
        hc = SanHealthChecks()

        with self.assertRaises(SystemExit) as sysexit:
            hc.get_san_critical_alerts(sanapi, 'unity')

        the_exception = sysexit.exception

        self.assertEqual(the_exception.code, 1)
