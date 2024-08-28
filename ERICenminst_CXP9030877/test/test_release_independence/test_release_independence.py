import os
import shutil
import tempfile
import unittest2
from h_litp.litp_utils import LitpException

from nose.tools import nottest
from unittest2 import TestCase
from mock import patch
import test_utils


class TestReleaseWrapper(TestCase):
    def setUp(self):
        self.test_dir = os.path.join(tempfile.mkdtemp(), 'test_dir')
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
        fcaps_healthcheck_modules = test_utils.mock_fcaps_healthcheck_module()
        self.fcaps_healthcheck_module_patcher = patch.dict('sys.modules', fcaps_healthcheck_modules)
        self.fcaps_healthcheck_module_patcher.start()
        import release_independence
        self.release_independence = release_independence

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    @patch('release_independence.os.system')
    @patch('release_independence.os.path.exists')
    def test_exec_repo_update_error(self, exist, mos):
        instance = self.release_independence.ReleaseWrapper()
        action = 'model_update'
        exist.return_value = [True, True]
        mos.side_effect = OSError
        self.assertRaises(OSError, instance.exec_repo_update, action)

    @patch('release_independence.ReleaseWrapper.pre_check')
    @patch('release_independence.ReleaseWrapper.litp_backup')
    @patch('release_independence.ReleaseWrapper.repo_backup')
    @patch('release_independence.ReleaseWrapper.exec_create_run_plan')
    @patch('release_independence.ReleaseWrapper.exec_repo_update')
    @patch('release_independence.ReleaseWrapper.exec_mdt_check')
    @patch('release_independence.ReleaseWrapper.exec_healthcheck')
    @patch('release_independence.init_enminst_logging')
    @patch('release_independence.os.path.exists')
    def test_main_model_update(self, repocheck, _, hc, mdt, repo, plan, backup, litp, pre):
        action = ['--action', 'model_update']
        self.release_independence.main(action)
        repocheck.return_value = [True, True]
        self.assertTrue(pre.called)
        self.assertTrue(backup.called)
        self.assertTrue(hc.called)
        self.assertTrue(mdt.called)
        self.assertTrue(repo.called)
        self.assertTrue(litp.called)
        self.assertTrue(plan.called)

    @patch('release_independence.os')
    def test_pre_check_error_file_error(self, mos):
        instance = self.release_independence.ReleaseWrapper()
        mos.path.isfile.return_value = False
        self.assertRaises(OSError, instance.pre_check)

    @patch('release_independence.os.path.exists')
    def test_pre_check_error_dir_error(self, repo):
        repo.return_value = [True, True, True, False]
        instance = self.release_independence.ReleaseWrapper()
        self.assertRaises(OSError, instance.pre_check)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.os.path')
    @patch('release_independence.ReleaseWrapper.create_status_file')
    @patch('release_independence.ReleaseWrapper.cleanup')
    @patch('release_independence.os.mkdir')
    def test_pre_check_test(self, m_dir, clean, status, path, mos):
        path.isfile.side_effect = [True, True, False, False]
        mos.side_effect = [True, True, True, True, True, True, True]
        instance = self.release_independence.ReleaseWrapper()
        instance.pre_check()
        status.assert_called_with(2)
        self.assertTrue(clean.called)
        m_dir.assert_called_with(self.release_independence.BACKUPDIR)
        self.assertTrue(status.called)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.os.path.isfile')
    @patch('release_independence.ReleaseWrapper.create_status_file')
    def test_pre_check_cleanup(self, status, filer, mos):
        filer.side_effect = [True, True, False]
        mos.side_effect = [True, True, True, True, True, True]
        instance = self.release_independence.ReleaseWrapper()
        status.side_effect = OSError
        self.assertRaises(OSError, instance.pre_check)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.os.path.isfile')
    @patch('release_independence.os.mkdir')
    def test_pre_check_cleanup_errs(self, m_dir, filer, mos):
        mos.side_effect = [True, True, True, True, True, False]
        filer.side_effect = [True, True, False]
        instance = self.release_independence.ReleaseWrapper()
        m_dir.side_effect = OSError
        self.assertRaises(OSError, instance.pre_check)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.os.path.isfile')
    @patch('release_independence.os.mkdir')
    def test_pre_check_cleanup_errors(self, m_dir, filer, mos):
        mos.side_effect = [True, True, True, True, True]
        filer.side_effect = [False, True, False]

        instance = self.release_independence.ReleaseWrapper()
        m_dir.side_effect = OSError
        self.assertRaises(OSError, instance.pre_check)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.HealthCheck')
    def test_exec_healthcheck(self, hc, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        instance.exec_healthcheck()
        self.assertTrue(hc.return_value.pre_checks.called)
        self.assertTrue(hc.return_value.enminst_healthcheck.called)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.HealthCheck')
    def test_exec_healthcheck_err(self, hc, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        instance.exec_healthcheck()
        hc.return_value.pre_checks.side_effect = SystemExit
        self.assertRaises(SystemExit, instance.exec_healthcheck)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.exec_process')
    def test_exec_mdt_check_2nd_error(self, exec_p, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        exec_p.side_effect = IOError
        self.assertRaises(IOError, instance.exec_mdt_check)

    @nottest
    @patch('release_independence.Deployer')
    def test_exec_create_run_plan(self, deploy):
        instance = self.release_independence.ReleaseWrapper()
        action = 'model_update'
        instance.exec_create_run_plan(action)
        self.assertTrue(deploy.return_value.create_plan.called)
        self.assertTrue(deploy.return_value.run_plan.called)
        self.assertTrue(deploy.return_value.wait_plan_complete.called)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.Deployer')
    def test_exec_create_run_plan_err(self, deploy, repo):
        instance = self.release_independence.ReleaseWrapper()
        action = 'model_update'
        repo.return_value = [True, True]
        deploy.side_effect = LitpException
        self.assertRaises(LitpException, instance.exec_create_run_plan, action)

    @patch('release_independence.os.path.exists')
    @patch('release_independence.Deployer')
    def test_exec_create_run_plan2(self, deploy, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        action = 'model_update'
        instance.exec_create_run_plan(action)
        self.assertTrue(deploy.return_value.create_plan.called)
        self.assertTrue(deploy.return_value.run_plan.called)
        self.assertTrue(deploy.return_value.wait_plan_complete.called)

    @patch('release_independence.shutil.rmtree')
    @patch('release_independence.os.path.exists')
    def test_cleanup(self, mos, remove):
        instance = self.release_independence.ReleaseWrapper()
        mos.return_value = [True]
        remove.return_value = True
        instance.cleanup()
        self.assertTrue(mos.called)
        self.assertTrue(remove.called)

    @patch('release_independence.os.path.exists')
    def test_create_status_file(self, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        instance.statusfile = self.test_dir + 'releaseindependence.status'
        instance.create_status_file(0)
        with open(instance.statusfile) as f:
            content = f.readlines()
        self.assertTrue('status:success\n' in content)
        self.assertTrue('0\n' in content)

    @patch('release_independence.os.path.exists')
    def test_create_status_file_with_warning(self, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        instance.statusfile = self.test_dir + 'releaseindependence.status'
        instance.create_status_file(1)
        with open(instance.statusfile) as f:
            content = f.readlines()
        self.assertTrue('status:failure\n' in content)
        self.assertTrue('1\n' in content)

    @patch('release_independence.os.path.exists')
    def test_create_status_file_with_except(self, repo):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        instance.model_deploy_path = self.test_dir
        self.assertRaises(IOError, instance.create_status_file('1'))

    @nottest
    @patch('release_independence.os.path.exists')
    def test_repo_check(self, mos):
        instance = self.release_independence.ReleaseWrapper()
        mos.return_value = True
        mylist = instance.repo_check()
        expected_list = ['/var/www/html/ENM_services_rhel7',
                         '/var/www/html/ENM_events_rhel7',
                         '/var/www/html/ENM_asrstream_rhel7',
                         '/var/www/html/ENM_ebsstream_rhel7',
                         '/var/www/html/ENM_automation_rhel7']
        self.assertEqual(mylist, expected_list)

    @patch('release_independence.os.path.exists')
    def test_repo_check2(self, mos):
        instance = self.release_independence.ReleaseWrapper()
        mos.return_value = False
        self.assertRaises(OSError, instance.repo_check)

    @patch('tarfile.open')
    @patch('release_independence.ReleaseWrapper.repo_check')
    def test_repo_backup(self, repo, tar):
        instance = self.release_independence.ReleaseWrapper()
        stdout = ['/bla/bla/bla', '/blah/blah/blah']
        repo.return_value = stdout
        instance.repo_backup()
        self.assertTrue(repo.called)
        self.assertTrue(tar.called)

    @patch('tarfile.open')
    @patch('release_independence.ReleaseWrapper.repo_check')
    def test_repo_backup_error(self, repo, tar):
        instance = self.release_independence.ReleaseWrapper()
        stdout = ['/bla/bla/bla', '/blah/blah/blah']
        repo.return_value = stdout
        tar.side_effect = SystemExit
        self.assertTrue(repo.called)
        self.assertRaises(SystemExit, instance.repo_backup)

    @patch('release_independence.exec_process')
    @patch('release_independence.ReleaseWrapper.repo_check')
    def test_litp_backup(self, repo, exec_p):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        instance.litp_backup()
        self.assertTrue(exec_p.called)

    @patch('release_independence.exec_process')
    @patch('release_independence.ReleaseWrapper.repo_check')
    def test_litp_backup_error(self, repo, exec_p):
        instance = self.release_independence.ReleaseWrapper()
        repo.return_value = [True, True]
        exec_p.side_effect = SystemExit
        self.assertRaises(SystemExit, instance.litp_backup)

    @patch('release_independence.os.path')
    @patch('release_independence.os.remove')
    def test_remove_lockfile(self, remove, filer):
        instance = self.release_independence.ReleaseWrapper()
        filer.isfile.side_effect = [True]
        remove.return_value = [True]
        instance.remove_lockfile()

    @patch('release_independence.os.path')
    @patch('release_independence.os.remove')
    def test_remove_lockfile_error(self, remove, filer):
        instance = self.release_independence.ReleaseWrapper()
        filer.isfile.side_effect = [True]
        remove.side_effect = OSError
        self.assertRaises(OSError, instance.remove_lockfile)

    @patch('release_independence.ReleaseWrapper.litp_backup')
    @patch('release_independence.ReleaseWrapper.repo_check')
    @patch('release_independence.ReleaseWrapper.exec_create_run_plan')
    @patch('release_independence.ReleaseWrapper.exec_repo_update')
    @patch('release_independence.ReleaseWrapper.repo_backup')
    @patch('release_independence.ReleaseWrapper.pre_check')
    def test_manage_release_actions_error_recovery(self, pre_check, repo_backup,
                                                   exec_repo_update, exec_create_run_plan,
                                                   repo_check, litp_backup):
        repo_check.return_value = ['repo_1', 'repo_2']
        action = ['--action', 'error_recovery']
        self.release_independence.main(action)
        self.assertTrue(pre_check.called)
        self.assertTrue(repo_backup.called)
        self.assertTrue(litp_backup.called)
        exec_repo_update.assert_called_with('error_recovery')
        exec_create_run_plan.assert_called_with('error_recovery')

    @patch('release_independence.ReleaseWrapper.litp_backup')
    @patch('release_independence.ReleaseWrapper.repo_check')
    @patch('release_independence.ReleaseWrapper.exec_create_run_plan')
    @patch('release_independence.ReleaseWrapper.exec_repo_update')
    @patch('release_independence.ReleaseWrapper.repo_backup')
    @patch('release_independence.ReleaseWrapper.pre_check')
    @patch('release_independence.ReleaseWrapper.exec_healthcheck')
    @patch('release_independence.ReleaseWrapper.exec_mdt_check')
    def test_manage_release_actions_model_update(self, mdt, hc, pre_check, repo_backup,
                                                 exec_repo_update, exec_create_run_plan,
                                                 repo_check, litp_backup):
        repo_check.return_value = ['repo_1', 'repo_2']
        action = ['--action', 'model_update']
        self.release_independence.main(action)
        self.assertTrue(pre_check.called)
        self.assertTrue(repo_backup.called)
        self.assertTrue(litp_backup.called)
        self.assertTrue(hc.called)
        self.assertTrue(mdt.called)
        exec_repo_update.assert_called_with('model_update')
        exec_create_run_plan.assert_called_with('model_update')

    @patch('release_independence.ReleaseWrapper.repo_check')
    @patch('release_independence.ReleaseWrapper.exec_create_run_plan')
    def test_manage_release_actions_rerunplan(self, exec_create_run_plan,
                                              repo_check):
        repo_check.return_value = ['repo_1', 'repo_2']
        action = ['--action', 'rerun_plan']
        self.release_independence.main(action)
        exec_create_run_plan.assert_called_with('rerun_plan')

    def test_main_help(self):
        self.assertRaises(SystemExit, self.release_independence.main, ['--action', 'bla'])

if __name__ == '__main__':
    unittest2.main()
