import os
import shutil
from tempfile import gettempdir
from os.path import join, exists, isdir
from unittest2 import TestCase
from mock import patch

from litpd import LitpIntegration
from pre_upgrade_rpms import PreUpgradeRpm, \
    validate_iso_from_args, RpmsUpgradedInfo, main
from h_util.h_utils import touch


class TestPreUpgradeRpm(TestCase):

    def mktmpfile(self, filename):
        filepath = join(self.tmpdir, filename)
        touch(filepath)
        return filepath

    def setUp(self):
        self.tmpdir = join(gettempdir(), 'TestPreUpgrade')
        if exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        os.makedirs(self.tmpdir)

        iso_filename = self.mktmpfile('ERICenm_CXP9027091-1.73.31.iso')
        m_args = ['pre_upgrade_rpms.py', str(iso_filename)]
        self.enm_iso = validate_iso_from_args(m_args)

        self.litpd = LitpIntegration()
        self.litpd.setup_empty_model()
        self.litpd.setup_db_cluster(node_count=2)

        self.pre_upgrade_rpms = PreUpgradeRpm(self.enm_iso, "1.72.50")
        self.pre_upgrade_rpms.litp_rest = self.litpd
        self.pre_upgrade_rpms.get_model_info()

    def tearDown(self):
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def test_validate_iso_from_args(self):
        iso_filename = self.mktmpfile('ERICenm_CXP9027091-1.73.31.iso')
        m_args = ['pre_upgrade_rpms.py', str(iso_filename)]

        iso = validate_iso_from_args(m_args)
        self.assertIsInstance(iso, str)
        self.assertTrue("ERICenm_CXP9027091-1.73.31.iso" in iso)

    def test_validate_iso_from_args_not_valid(self):
        m_args = ['pre_upgrade_rpms.py', 'ERICenm_CXP9027091-wrong-format']

        self.assertRaises(SystemExit, validate_iso_from_args, m_args)

    @patch('pre_upgrade_rpms.get_rpm_info')
    @patch('h_puppet.mco_agents.EnmPreCheckAgent.upgrade_packages')
    def test_upgrade_rpm_on_lms(self,
                                m_mco_agent,
                                m_get_rpm_info):
        self.pre_upgrade_rpms.litp_rest = self.litpd
        self.pre_upgrade_rpms.upgrade_rpm_on_lms("TestRPM", "/test/rpm/path/ERICdstutilities_CXP9032738-1.51.1.rpm")
        self.assertTrue(m_mco_agent.called)

    @patch('pre_upgrade_rpms.PreUpgradeRpm.check_for_install_space')
    @patch('pre_upgrade_rpms.get_rpm_info')
    @patch('pre_upgrade_rpms.install_rpm')
    @patch('pre_upgrade_rpms.check_package_installed')
    def test_install_rpm_on_lms_install(self,
                                        m_check_pkg,
                                        m_pkg_install,
                                        m_get_rpm_info,
                                        m_install_space):
        self.pre_upgrade_rpms.litp_rest = self.litpd
        m_check_pkg.return_value = False
        self.pre_upgrade_rpms.install_rpm_on_lms("/test/rpm/path/ERICdstutilities_CXP9032738-1.51.1.rpm")

        self.assertTrue(m_pkg_install.called)

    @patch('pre_upgrade_rpms.PreUpgradeRpm.check_for_install_space')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.upgrade_rpm_on_lms')
    @patch('pre_upgrade_rpms.check_package_installed')
    def test_install_rpm_on_lms_upgrade(self,
                                        m_check_pkg,
                                        m_upg_rpm,
                                        m_install_space):
        self.pre_upgrade_rpms.litp_rest = self.litpd
        m_check_pkg.return_value = True
        self.pre_upgrade_rpms.install_rpm_on_lms("/test/rpm/path/ERICdstutilities_CXP9032738-1.51.1.rpm")

        self.assertTrue(m_upg_rpm.called)

    @patch('pre_upgrade_rpms.get_rpm_info')
    @patch('pre_upgrade_rpms.install_rpm')
    @patch('pre_upgrade_rpms.check_package_installed')
    def test_install_rpm_on_lms_install_snapshot_rpm(self,
                                                     m_check_pkg,
                                                     m_pkg_install,
                                                     m_get_rpm_info):
        self.pre_upgrade_rpms.litp_rest = self.litpd
        m_check_pkg.return_value = False
        self.pre_upgrade_rpms.install_rpm_on_lms("/test/rpm/path/ERICdstutilities_CXP9032738-1.51.13-"
                                                 "SNAPSHOT20190606090202.noarch.rpm")

        self.assertTrue(m_pkg_install.called)

    @patch('glob.glob')
    @patch('import_iso.mount')
    @patch('import_iso.create_mnt_dir')
    @patch('import_iso.configure_logging')
    def test_get_rpms_to_upgrade(self,
                                 m_create_dir,
                                 m_config_log,
                                 m_iso_mount,
                                 m_glob):

        self.assertEquals(self.pre_upgrade_rpms.enm_iso, self.enm_iso)
        self.pre_upgrade_rpms.get_rpms_to_upgrade()

        self.assertTrue(m_create_dir.called)
        self.assertTrue(m_config_log.called)
        self.assertTrue(m_iso_mount.called)
        self.assertTrue(m_glob.called)
        self.assertTrue(self.pre_upgrade_rpms.rpms_to_install)

    @patch('__builtin__.open')
    @patch('import_iso.umount')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.update_san_psl')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.install_rpm_on_lms')
    def test_install_rpms(self,
                          m_install_rpm_lms,
                          m_psl_upg,
                          m_iso_umount,
                          m_open):

        self.pre_upgrade_rpms.rpms_to_install = ["/litp/plugins/ENM/ERIClitpsanemc_CXP9030788-1.18.1.rpm",
                                                 "/repos/ENM/ms/ERICdstutilities_CXP9032738-1.51.1.rpm",
                                                 "/repos/ENM/ms/ERICenmdeploymenttemplates_CXP9031758-1.72.15.rpm"]

        self.pre_upgrade_rpms.install_rpms()
        self.assertTrue(m_psl_upg.called)
        self.assertTrue(m_install_rpm_lms.called)
        self.assertTrue(m_iso_umount.called)
        self.assertTrue(m_open.called)

    @patch('__builtin__.open')
    @patch('import_iso.umount')
    @patch('pre_upgrade_rpms.install_rpm')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.update_san_psl')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.install_rpm_on_lms')
    @patch('h_util.h_utils.check_package_installed')
    def test_install_rpms_failure(self,
                                  m_pkg_installed,
                                  m_install_rpm_lms,
                                  m_psl_upg,
                                  m_install_rpm,
                                  m_iso_umount,
                                  m_open):

        self.pre_upgrade_rpms.rpms_to_install = ["/litp/plugins/ENM/ERIClitpsanemc_CXP9030788-1.18.1.rpm",
                                                 "/repos/ENM/ms/ERICdstutilities_CXP9032738-1.51.1.rpm",
                                                 "/repos/ENM/ms/ERICenmdeploymenttemplates_CXP9031758-1.72.15.rpm"]

        self.pre_upgrade_rpms.UPGRADE_FAILURE = True
        self.assertRaises(SystemExit, self.pre_upgrade_rpms.install_rpms)

    @patch('pre_upgrade_rpms.copy_file')
    @patch('pre_upgrade_rpms.delete_file')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.update_rpm_info')
    @patch('h_puppet.h_puppet.puppet_runall')
    @patch('h_puppet.mco_agents.EnmPreCheckAgent.upgrade_packages')
    @patch('h_puppet.h_puppet.puppet_enable_disable')
    @patch('h_puppet.h_puppet.discover_all_nodes')
    def test_update_san_psl(self,
                            m_discover_all_nodes,
                            m_puppet_enable_disable,
                            m_mco_agent_upg_pkg,
                            m_puppet_runall,
                            m_update_rpm_info,
                            m_del_file,
                            m_copy_file,
                            ):
        self.pre_upgrade_rpms.litp_rest = self.litpd
        san_psl_rpm = "/litp/plugins/ENM/ERIClitpsanemc_CXP9030788-1.18.1.rpm"
        self.pre_upgrade_rpms.update_san_psl(san_psl_rpm)

        self.assertTrue(m_copy_file.called)
        self.assertEqual(m_puppet_enable_disable.call_count, 2)
        self.assertEqual(m_puppet_runall.call_count, 1)
        self.assertEqual(m_mco_agent_upg_pkg.call_count, 3)
        self.assertEqual(m_update_rpm_info.call_count, 3)
        self.assertTrue(m_del_file.called)

    @patch('pre_upgrade_rpms.copy_file')
    @patch('pre_upgrade_rpms.delete_file')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.update_rpm_info')
    @patch('h_puppet.h_puppet.puppet_runall')
    @patch('h_puppet.mco_agents.EnmPreCheckAgent.upgrade_packages')
    @patch('h_puppet.h_puppet.puppet_enable_disable')
    @patch('h_puppet.h_puppet.discover_all_nodes')
    def test_update_san_plugin(self,
                            m_discover_all_nodes,
                            m_puppet_enable_disable,
                            m_mco_agent_upg_pkg,
                            m_puppet_runall,
                            m_update_rpm_info,
                            m_del_file,
                            m_copy_file,
                            ):
        self.pre_upgrade_rpms.litp_rest = self.litpd
        san_plugin_rpm = "/litp/plugins/ENM/ERIClitpsan_CXP9030786-1.35.3.rpm"
        self.pre_upgrade_rpms.update_san_psl(san_plugin_rpm)

        self.assertTrue(m_copy_file.called)
        self.assertEqual(m_puppet_enable_disable.call_count, 2)
        self.assertEqual(m_puppet_runall.call_count, 1)
        self.assertEqual(m_mco_agent_upg_pkg.call_count, 3)
        self.assertEqual(m_update_rpm_info.call_count, 3)
        self.assertTrue(m_del_file.called)

    @patch('pre_upgrade_rpms.get_rpm_info')
    @patch('pre_upgrade_rpms.check_package_installed')
    @patch('h_puppet.mco_agents.EnmPreCheckAgent.get_package_info')
    def test_get_installed_rpms_versions(self,
                                         m_mco,
                                         m_pkg_installed,
                                         m_get_pkg_info):
        # self.pre_upgrade_rpms.litp_rest = self.litpd
        m_mco.return_value = "name=ERIClitpsanemc_CXP9030788,version=2.18.5,release=1"
        m_get_pkg_info.return_value = {"name": "ERICdstutilities_CXP9032738", "version": "1.51.1", "release": "1"}
        m_pkg_installed.return_value = True

        self.pre_upgrade_rpms.rpms_to_install = ["/litp/plugins/ENM/ERIClitpsanemc_CXP9030788-1.20.2.rpm",
                                                 "/repos/ENM/ms/ERICdstutilities_CXP9032738-1.51.1.rpm",
                                                 "repos/ENM/ms/ERICenmdeploymenttemplates_CXP9031758-1.75.7.rpm"]
        self.pre_upgrade_rpms.get_installed_rpms_versions()

        self.assertEqual(len(self.pre_upgrade_rpms.rpm_info), 5)

    @patch('h_util.h_utils.get_rpm_install_size')
    @patch('h_util.h_utils.get_lms_free_space')
    def test_check_space_to_install(self,
                                    m_lms_free_space,
                                    m_rpm_install_size):
        m_lms_free_space.return_value = '500'
        m_rpm_install_size.side_effect = ['4000', '4700']
        check = self.pre_upgrade_rpms.check_for_install_space()
        self.assertRaises(SystemExit, check)

    @patch('pre_upgrade_rpms.get_rpm_info')
    def test_update_rpm_info(self,
                             m_get_rpm_info):
        m_get_rpm_info.return_value = {"name": "ERIClitpsanemc_CXP9030788",
                                       "version": "1.3.1",
                                       "release": "1"}

        rpm_info = {"name": "ERIClitpsanemc_CXP9030788",
                    "version": "1.2.3",
                    "release": "1"}
        rpm_upg_info = RpmsUpgradedInfo("ms-1", rpm_info)
        self.pre_upgrade_rpms.rpm_info.append(rpm_upg_info)

        rpm_info_output = "ERIClitpsanemc_CXP9030788-1.2.3,None,ERIClitpsanemc_CXP9030788-None,ms-1"
        self.assertEqual(str(self.pre_upgrade_rpms.rpm_info[0]), rpm_info_output)

        self.pre_upgrade_rpms.update_rpm_info("ms-1", "ERIClitpsanemc_CXP9030788-1.3.1", "upgrade")
        updated_rpm_info_output = "ERIClitpsanemc_CXP9030788-1.2.3,upgrade,ERIClitpsanemc_CXP9030788-1.3.1,ms-1"
        self.assertEqual(str(self.pre_upgrade_rpms.rpm_info[0]), updated_rpm_info_output)

    def test_format_rpm_version_snapshot(self):
        rpm_info = {"name": "ERIClitpsanemc_CXP9030788",
                    "version": "1.2.3",
                    "release": "SNAPSHOT"}
        rpm_upg_info = RpmsUpgradedInfo("ms-1", rpm_info)

        self.assertTrue(rpm_upg_info.format_rpm_version(rpm_info), "1.2.3-SNAPSHOT")

    def test_format_rpm_version_not_snapshot(self):
        rpm_info = {"name": "ERIClitpsanemc_CXP9030788",
                    "version": "1.2.3",
                    "release": "1"}
        rpm_upg_info = RpmsUpgradedInfo("ms-1", rpm_info)

        self.assertTrue(rpm_upg_info.format_rpm_version(rpm_info), "1.2.3")

    def test_rpms_upgraded_info_to_string(self):
        rpm_info = {"name": "ERIClitpsanemc_CXP9030788",
                    "version": "1.2.3",
                    "release": "1"}
        rpm_upg_info = RpmsUpgradedInfo("ms-1", rpm_info)
        rpm_upg_info.post_rpm_version = "1.3.1"
        rpm_upg_info.rpm_operation = "upgrade"

        expected_output = "ERIClitpsanemc_CXP9030788-1.2.3,upgrade,ERIClitpsanemc_CXP9030788-1.3.1,ms-1"
        self.assertEqual(str(rpm_upg_info), expected_output)

    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    def test_get_model_info(self, get_cluster_nodes, get_lms):
        self.pre_upgrade_rpms.get_model_info()
        self.assertTrue(get_cluster_nodes.called)
        self.assertTrue(get_lms.called)

    def test_main_no_args(self):
        self.assertRaises(SystemExit, main, [])

    def test_main_one_args(self):
        self.assertRaises(SystemExit, main, ['pre_upgrade_rpms.py'])

    def test_main_non_iso_file(self):
        non_iso_filename = self.mktmpfile('ERICenm_CXP9027091-1.73.31.jpg')
        self.assertRaises(SystemExit, main, ['pre_upgrade_rpms.py', non_iso_filename])

    @patch('pre_upgrade_rpms.validate_iso_from_args')
    @patch('pre_upgrade_rpms.copy_over_xml_dd_file')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.get_model_info')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.get_rpms_to_upgrade')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.check_for_install_space')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.get_installed_rpms_versions')
    @patch('pre_upgrade_rpms.PreUpgradeRpm.install_rpms')
    def test_main_two_args(self, m_install_rpms, m_get_installed_rpms_versions, m_check_for_install_space,
                           m_get_rpms_to_upgrade, m_get_model_info, m_copy_over_xml_dd_file, m_validate_iso_from_args):
        m_args = ['pre_upgrade_rpms.py', self.enm_iso]
        m_validate_iso_from_args.return_value = self.enm_iso
        main(m_args)
        self.assertTrue(m_validate_iso_from_args.called)
        self.assertTrue(m_copy_over_xml_dd_file.called)
        self.assertTrue(m_get_model_info.called)
        self.assertTrue(m_get_rpms_to_upgrade.called)
        self.assertTrue(m_check_for_install_space.called)
        self.assertTrue(m_get_installed_rpms_versions.called)
        self.assertTrue(m_install_rpms.called)
