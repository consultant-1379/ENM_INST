import os
from unittest2 import TestCase
from mock import patch, Mock
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import compare_versions
from rollback_upgrade_rpms import RollbackUpgradeRpm, find_if_file_in_path
from h_puppet.mco_agents import EnmPreCheckAgent, McoAgentException


class TestRollbackUpgradeRpm(TestCase):

    def test_get_rpm_data(self):
        rpm_file_path = os.path.join(os.path.dirname(__file__), '../Resources/rpm_upgrade_info.txt')
        rb_rpms = RollbackUpgradeRpm()
        rb_rpms.get_rpm_data(rpm_file_path)
        self.assertTrue(len(rb_rpms.rpm_data_list) == 4)

        with self.assertRaises(IOError):
            rb_rpms.get_rpm_data("/nowhere/nofile.txt")

    @patch('h_puppet.mco_agents.EnmPreCheckAgent.get_package_info')
    def test_get_installed_rpm_info(self, package_info):
        rb_rpms = RollbackUpgradeRpm()
        package_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.76.12,release=1"
        rpm_info = rb_rpms.get_installed_rpm_info('ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210', EnmPreCheckAgent())
        self.assertTrue(rpm_info is not None)

        package_info.side_effect = McoAgentException(Mock(status=404), "{'node': 'ieatlms5736', u'retcode': 1, u'err': u'', u'out': u'package ERICenmdeploymenttemplates_CXP9031758 is not installed'}")
        rpm_info = rb_rpms.get_installed_rpm_info(
            'ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210',
            EnmPreCheckAgent())
        self.assertTrue(rpm_info is None)

    @patch('h_puppet.mco_agents.EnmPreCheckAgent.remove_packages')
    def test_remove_rpm_from_host(self, remove_packages):
        rb_rpms = RollbackUpgradeRpm()
        remove_packages.return_value = "Removed:\n    ERICenmdeploymenttemplates_CXP9031758.noarch 0:1.76.15-1"
        result = rb_rpms.remove_rpm_from_host('ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210', EnmPreCheckAgent())
        self.assertTrue(result is not None)

        remove_packages.return_value = "Setting up Remove Process\nNo Packages marked for removal"
        result = rb_rpms.remove_rpm_from_host(
            'ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210',
            EnmPreCheckAgent())
        self.assertTrue(result is None)

        remove_packages.side_effect = McoAgentException(Mock(status=404))
        result = rb_rpms.remove_rpm_from_host(
            'ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210',
            EnmPreCheckAgent())
        self.assertTrue(result is None)

    @patch('h_puppet.mco_agents.EnmPreCheckAgent.upgrade_packages')
    def test_upgrade_rpm_on_host(self, upgrade_packages):
        rb_rpms = RollbackUpgradeRpm()
        upgrade_packages.return_value = "Updated:\n   ERICenmdeploymenttemplates_CXP9031758.noarch 0:1.76.15-1"
        result = rb_rpms.upgrade_rpm_on_host('ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210', EnmPreCheckAgent())
        self.assertTrue(result)

        upgrade_packages.return_value = "Setting up Upgrade Process\nNo Packages marked for Update"
        result = rb_rpms.upgrade_rpm_on_host('ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210', EnmPreCheckAgent())
        self.assertFalse(result)

        upgrade_packages.side_effect = McoAgentException(Mock(status=404))
        result = rb_rpms.upgrade_rpm_on_host('ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210', EnmPreCheckAgent())
        self.assertFalse(result)

    @patch('h_puppet.mco_agents.EnmPreCheckAgent.downgrade_packages')
    def test_downgrade_rpm_on_host(self, downgrade_packages):
        rb_rpms = RollbackUpgradeRpm()
        downgrade_packages.return_value = "Removed:\n  ERICenmdeploymenttemplates_CXP9031758.noarch 0:1.76.15-1\n\nInstalled:\nERICenmdeploymenttemplates_CXP9031758.noarch 0:1.75.7-1"
        result = rb_rpms.downgrade_rpm_on_host(
            'ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210',
            EnmPreCheckAgent())
        self.assertTrue(result)

        downgrade_packages.return_value = "Setting up Downgrade Process\nNothing to do"
        result = rb_rpms.downgrade_rpm_on_host(
            'ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210',
            EnmPreCheckAgent())
        self.assertFalse(result)

        downgrade_packages.side_effect = McoAgentException(Mock(status=404))
        result = rb_rpms.downgrade_rpm_on_host(
            'ERICenmdeploymenttemplates_CXP9031758', 'ieatlms3210',
            EnmPreCheckAgent())
        self.assertFalse(result)

    @patch('h_puppet.mco_agents.EnmPreCheckAgent.get_available_package_versions')
    def test_check_if_version_in_yum(self, package_versions):
        rb_rpms = RollbackUpgradeRpm()
        package_versions.return_value = "ERICenmdeploymenttemplates_CXP9031758.noarch      1.76.15-1          @/ERICenmdeploymenttemplates_CXP9031758-1.76.15"
        available_versions = rb_rpms.check_if_version_in_yum(EnmPreCheckAgent(), 'ieatlms3210', 'ERICenmdeploymenttemplates_CXP9031758')
        self.assertTrue(available_versions == ['1.76.15'])

        package_versions.return_value = ""
        available_versions = rb_rpms.check_if_version_in_yum(EnmPreCheckAgent(), 'ieatlms3210', 'ERICenmdeploymenttemplates_CXP9031758')
        self.assertTrue(available_versions == [])

        package_versions.side_effect = McoAgentException(Mock(status=404), "{'node': 'ieatlms5736', u'retcode': 1, u'err': u'', u'out': u''}")
        available_versions = rb_rpms.check_if_version_in_yum(EnmPreCheckAgent(), 'ieatlms3210', 'ERICenmdeploymenttemplates_CXP9031758')
        self.assertTrue(available_versions == [])

    @patch('rollback_upgrade_rpms.get_rpm_info')
    # pylint: disable=R0915
    def test_check_old_rpm_not_same_package(self, m_get_rpm_info):
        old_package_name = "/ericsson/enm/dumps/ERICenmdeploymenttemplates_CXP9031758-1.76.12.rpm"
        rpm_name = "ERICenmdeploymenttemplates_CXP9031758-1.76.13.rpm"
        rb_rpms = RollbackUpgradeRpm()
        rb_rpms.ms_name = "ms1"
        m_get_rpm_info.return_value = {'name':'ERICenmdeploymenttemplates_CXP9031758', 'version':'1.76.13'}
        self.assertFalse(rb_rpms.check_old_rpm_vs_rollback_rpm(rpm_name, old_package_name))

    @patch('rollback_upgrade_rpms.get_rpm_info')
    # pylint: disable=R0915
    def test_check_old_rpm_same_package(self, m_get_rpm_info):
        old_package_name = "/ericsson/enm/dumps/ERICenmdeploymenttemplates_CXP9031758-1.76.12.rpm"
        rpm_name = "ERICenmdeploymenttemplates_CXP9031758-1.76.12.rpm"
        rb_rpms = RollbackUpgradeRpm()
        rb_rpms.ms_name = "ms1"
        m_get_rpm_info.return_value = {'name': 'ERICenmdeploymenttemplates_CXP9031758', 'version': '1.76.12'}
        self.assertTrue(rb_rpms.check_old_rpm_vs_rollback_rpm(rpm_name, old_package_name))

    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.install_rpm_on_host')
    @patch('rollback_upgrade_rpms.delete_file')
    @patch('rollback_upgrade_rpms.copy_file')
    @patch('os.remove')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.check_if_version_in_yum')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.upgrade_rpm_on_host')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.downgrade_rpm_on_host')
    @patch('rollback_upgrade_rpms.find_if_file_in_path')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.remove_rpm_from_host')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.get_installed_rpm_info')
    @patch('rollback_upgrade_rpms.compare_versions')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.check_old_rpm_vs_rollback_rpm')
    # pylint: disable=R0915
    def test_rollback_upgraded_rpms_timeout(self, m_check_rpm, m_result, rpm_info, remove_rpm_from_host, file_path,
                                    downgrade_rpm, upgrade_rpm, yum_versions,
                                    remove, copy_file, delete_file, install_rpm):
        rb_rpms = RollbackUpgradeRpm()
        remove.return_value = None
        copy_file.return_value = None
        delete_file.return_value = None
        logger = init_enminst_logging()
        m_result = None

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12", 'last_operation': "upgrade",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.76.12,release=1"
        file_path.return_value = ['/var/www/html/ERICenmdeploymenttemplates_CXP9031758-1.76.12.rpm']
        downgrade_rpm.return_value = False
        install_rpm.return_value = None
        m_check_rpm.return_value = True
        with patch.object(logger, 'warning') as mock_warning:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_warning.assert_called_with(
                'rollback of ERICenmdeploymenttemplates_CXP9031758 on LMS has'
                " timed out but the RPM "
                "has downgraded"
                ' successfully.')

    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.install_rpm_on_host')
    @patch('rollback_upgrade_rpms.delete_file')
    @patch('rollback_upgrade_rpms.copy_file')
    @patch('os.remove')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.check_if_version_in_yum')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.upgrade_rpm_on_host')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.downgrade_rpm_on_host')
    @patch('rollback_upgrade_rpms.find_if_file_in_path')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.remove_rpm_from_host')
    @patch('rollback_upgrade_rpms.RollbackUpgradeRpm.get_installed_rpm_info')
    @patch('h_puppet.h_puppet.puppet_runall')
    @patch('h_puppet.mco_agents.EnmPreCheckAgent.upgrade_packages')
    @patch('h_puppet.h_puppet.puppet_enable_disable')
    @patch('h_puppet.h_puppet.check_for_puppet_catalog_run')
    # pylint: disable=R0915
    def test_rollback_upgraded_rpms(self, m_puppet_check_catalogue,
                                    m_puppet_enable_disable,
                                    m_mco_agent_upg_pkg, m_puppet_runall, rpm_info,
                                    remove_rpm_from_host, file_path,
                                    downgrade_rpm, upgrade_rpm, yum_versions,
                                    remove, copy_file, delete_file, install_rpm):
        rb_rpms = RollbackUpgradeRpm()
        remove.return_value = None
        copy_file.return_value = None
        delete_file.return_value = None
        logger = init_enminst_logging()

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-None", 'last_operation': "install",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.76.12,release=1"
        remove_rpm_from_host.return_value = "Removed:\n    ERICenmdeploymenttemplates_CXP9031758.noarch 0:1.76.12-1"
        with patch.object(logger, 'info') as mock_info:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_info.assert_called_with("ERICenmdeploymenttemplates_CXP9031758 removed from host ieatlms5736")

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.73.13", 'last_operation': "upgrade",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.76.12,release=1"
        file_path.return_value = ['/var/www/html/ERICenmdeploymenttemplates_CXP9031758-1.73.13.rpm']
        downgrade_rpm.return_value = True
        install_rpm.return_value = "Installed: ERICenmdeploymenttemplates_CXP9031758-1.73.13"
        with patch.object(logger, 'info') as mock_info:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_info.assert_called_with(
                "Package ERICenmdeploymenttemplates_CXP9031758 has been rolled back from"
                                     " version 1.76.12 to 1.73.13")

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.77.13", 'last_operation': "upgrade",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.76.12,release=1"
        file_path.return_value = []
        yum_versions.return_value = ['1.77.13']
        upgrade_rpm.return_value = False
        with patch.object(logger, 'warning') as mock_error:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_error.assert_called_with(
                "Rollback version 1.77.13 not available for package ERICenmdeploymenttemplates_CXP9031758, please rollback manually..")
        yum_versions.return_value = ['1.76.18']
        upgrade_rpm.return_value = False
        with patch.object(logger, 'warning') as mock_warning:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_warning.assert_called_with(
                "Rollback version 1.77.13 not available for package ERICenmdeploymenttemplates_CXP9031758, please rollback manually..")

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-None", 'last_operation': "install",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = None
        with patch.object(logger, 'info') as mock_info:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_info.assert_not_called()

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-None", 'last_operation': "install",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.76.12,release=1"
        remove_rpm_from_host.return_value = None
        with patch.object(logger, 'info') as mock_info:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_info.assert_called_with(
                "Package ERICenmdeploymenttemplates_CXP9031758 version 1.76.12 installed on ieatlms5736")
            with self.assertRaises(AssertionError):
                mock_info.assert_called_with(
                    "ERICenmdeploymenttemplates_CXP9031758 removed from host ieatlms5736")

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.73.3", 'last_operation': "upgrade",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERICenmdeploymenttemplates_CXP9031758,version=1.73.3,release=1"
        with patch.object(logger, 'info') as mock_info:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_info.assert_called_with("Rollback of package ERICenmdeploymenttemplates_CXP9031758 to version 1.73.3 has already been completed, skipping..")

        rpms = [{'before_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.73.13", 'last_operation': "nothing",
                 'after_rpm_name': "ERICenmdeploymenttemplates_CXP9031758-1.73.13",
                 'host': "ieatlms5736"}]
        with patch.object(logger, 'info') as mock_info:
            rb_rpms.rollback_upgraded_rpms(rpms)
            mock_info.assert_not_called()

        rpms = [{'before_rpm_name': "ERIClitpsanemc_CXP9030788-1.73.13", 'last_operation': "upgrade",
                 'after_rpm_name': "ERIClitpsanemc_CXP9030788-1.76.12",
                 'host': "ieatlms5736"}]
        rpm_info.return_value = "name=ERIClitpsanemc_CXP9030788,version=1.76.12,release=1"
        file_path.return_value = ['/var/www/html/ERIClitpsanemc_CXP9030788-1.73.13.rpm']
        downgrade_rpm.return_value = True

        install_rpm.return_value = "Installed: ERIClitpsanemc_CXP9030788-1.73.13"
        rb_rpms.ms_name = "ieatlms5736"
        rb_rpms.rollback_upgraded_rpms(rpms)

        self.assertEqual(m_puppet_enable_disable.call_count, 2)
        self.assertEqual(m_puppet_runall.call_count, 1)
        self.assertEqual(m_puppet_check_catalogue.call_count, 1)

    def test_find_if_file_in_path(self):
        folder_path = os.path.join(os.path.dirname(__file__), '../Resources/')
        results = find_if_file_in_path('nofile.txt', folder_path)
        self.assertTrue(results == [])
        results = find_if_file_in_path('rpm_upgrade_info.txt', folder_path)
        self.assertTrue(len(results) == 1)
