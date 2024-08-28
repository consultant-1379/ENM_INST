import sys
import mock

if sys.platform.lower().startswith('win'):
    from mock import MagicMock

    sys.modules['syslog'] = MagicMock()

import os
from os.path import join, exists
from tempfile import gettempdir
from mock import patch
from unittest2 import TestCase
from agent.dbsnapshots import RPCAgent, Dbsnapshots, DbsnapshotsException
from simplejson import dumps, loads
from subprocess import PIPE, STDOUT


class MockRPCAgent(RPCAgent):
    def __init__(self):
        super(MockRPCAgent, self).__init__()
        self.exit_enabled = True

    def enable_exits(self, enabled):
        self.exit_enabled = enabled

    def mock_action(self, request):
        return {'a': 'b'}

    def exit(self, exit_value):
        if self.exit_enabled:
            super(MockRPCAgent, self).exit(exit_value)


class TestRPCAgent(TestCase):
    def setUp(self):
        self.MCOLLECTIVE_REQUEST_FILE = join(gettempdir(),
                                             'MCOLLECTIVE_REQUEST_FILE')
        self.MCOLLECTIVE_REPLY_FILE = join(gettempdir(),
                                           'MCOLLECTIVE_REPLY_FILE')
        os.environ['MCOLLECTIVE_REQUEST_FILE'] = self.MCOLLECTIVE_REQUEST_FILE
        os.environ['MCOLLECTIVE_REPLY_FILE'] = self.MCOLLECTIVE_REPLY_FILE
        if exists(self.MCOLLECTIVE_REPLY_FILE):
            os.remove(self.MCOLLECTIVE_REPLY_FILE)

    def tearDown(self):
        if exists(self.MCOLLECTIVE_REQUEST_FILE):
            os.remove(self.MCOLLECTIVE_REQUEST_FILE)
        if exists(self.MCOLLECTIVE_REPLY_FILE):
            os.remove(self.MCOLLECTIVE_REPLY_FILE)

    def setupRequest(self, request):
        with open(self.MCOLLECTIVE_REQUEST_FILE, 'w') as _f:
            _f.write(request)

    def test_action(self):
        self.setupRequest(dumps({
            'action': 'mock_action',
            'data': {}
        }))
        agent = MockRPCAgent()
        agent.enable_exits(False)
        self.assertFalse(exists(self.MCOLLECTIVE_REPLY_FILE))
        with self.assertRaises(SystemExit) as sysexit:
            agent.action()
        self.assertEqual(sysexit.exception.message, 0)
        self.assertTrue(exists(self.MCOLLECTIVE_REPLY_FILE))
        with open(self.MCOLLECTIVE_REPLY_FILE) as _rf:
            rdata = loads('\n'.join(_rf.readlines()))
            self.assertDictEqual(rdata, agent.mock_action({}))

        self.setupRequest(dumps({
            'action': 'vvvvvvvvvvvvvvvvvvvvv',
            'data': {}
        }))
        agent.enable_exits(True)
        with self.assertRaises(SystemExit) as sysexit:
            agent.action()
        self.assertNotEqual(sysexit.exception, 0)


class TestDbsnapshots(TestCase):
    @patch('agent.dbsnapshots.Popen')
    def test_exec_command(self, popen):
        popen.return_value.communicate.return_value = '_stdout_', '_stderr_'
        popen.return_value.returncode = 0
        snap = Dbsnapshots()
        stdout = snap.exec_command('cmd')
        self.assertEqual('_stdout_', stdout)

    @patch('agent.dbsnapshots.Popen')
    def test_exec_command_exeption(self, popen):
        popen.return_value.returncode = 1
        snap = Dbsnapshots()
        self.assertRaises(IOError, snap.exec_command, 'cmd')

    def test_get_sancli_snap_command(self):
        ip_a = '192.168.1.11'
        ip_b = '192.168.1.12'
        username = 'master'
        password = 'password'
        scope = 'global'
        lunid = '111'
        name = 'snap_name'
        array = 'vnx2'
        descr = 'description'

        enc_pass = 'cGFzc3dvcmQ='

        comparison = ('/opt/ericsson/nms/litp/lib/sanapi/sancli.py create_snap'
                      ' --ip_spa={0} --ip_spb={1} --user={2} '
                      '--password={3} --scope={4} --lun_id={5} --snap_name={6} '
                      '--array={7} --description="{8}" --enc=b64:_'.format(ip_a, ip_b,
                                                               username, enc_pass,
                                                               scope, lunid, name,
                                                               array, descr))

        output = Dbsnapshots.get_sancli_snap_command(ip_a, ip_b, username,
                                                      password, scope, lunid,
                                                      name, descr, array)

        self.assertEqual(output, comparison)

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_create_neo4j_db_snapshot_single(self, ec):
        ec.return_value = 'output string'
        sys.modules['neo4jlib'] = mock.MagicMock()
        sys.modules['neo4jlib.constants'] = mock.MagicMock()
        sys.modules['neo4jlib.neo4j'] = mock.MagicMock()
        sys.modules['neo4jlib.neo4j.session'] = mock.MagicMock()
        sys.modules['neo4jlib.eos'] = mock.MagicMock()
        sys.modules['neo4jlib.eos.host'] = mock.MagicMock()
        sys.modules['neo4jlib.error'] = mock.MagicMock()
        args = {
            'dbtype': 'neo4j',
            'navi_cmd': 'navi_cmd',
            'array_type': 'vnx2',
            'spa_ip': 'spa_ip',
            'spb_ip': 'spb_ip',
            'spa_username': 'san_user',
            'Password': 'san_pw',
            'Scope': 'san_login_scope',
            'dblun_id': '{"neo4jlun": 1}',
            'snap_name': 'snap_prefix' + 'dblun_id',
            'descr': 'descr'

        }
        snap = Dbsnapshots()
        os.environ['VERSANT_HOST_NAME'] = 'db1-service'
        res = snap.create_neo4j_db_snapshot(args)
        self.assertTrue(ec.called)
        self.assertEquals(len(ec.call_args[0]), 1)

        self.assertTrue("--snap_name=snap_prefixdblun_id_1" in ec.call_args[0][0])
        self.assertTrue(isinstance(res, dict), "Expected dict, got %s instead: "
                                               "%s" % (type(res), res))
        self.assertTrue('retcode' in res)
        self.assertTrue('err' in res)
        self.assertTrue('out' in res)
        self.assertEquals(res['retcode'], 0, "Expected retcode 0, got %s "
                                             "instead: %s" % (res['retcode'],
                                                              res['err']))
        self.assertEquals(res['err'], "", "Expected empty err, got %s instead" %
                                          res['err'])
        self.assertEquals(res['out'], "output string")

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_create_neo4j_db_snapshot_causal_cluster(self, ec):
        ec.return_value = 'output string'
        shell = mock.Mock()
        shell.cluster.is_single.return_value = False
        session = mock.MagicMock()
        session.Neo4jSession.return_value.__enter__.return_value = shell
        host = mock.MagicMock()
        host_obj = mock.MagicMock()
        host_obj.aliases = ["db-3"]
        host.Host.return_value = host_obj
        sys.modules['neo4jlib'] = mock.MagicMock()
        sys.modules['neo4jlib.constants'] = mock.MagicMock()
        sys.modules['neo4jlib.neo4j'] = mock.MagicMock()
        sys.modules['neo4jlib.neo4j.session'] = session
        sys.modules['neo4jlib.eos'] = mock.MagicMock()
        sys.modules['neo4jlib.eos.host'] = host
        sys.modules['neo4jlib.error'] = mock.MagicMock()
        sys.modules['neo4jlib.log'] = mock.MagicMock()
        args = {
            'dbtype': 'neo4j',
            'navi_cmd': 'navi_cmd',
            'array_type': 'vnx2',
            'spa_ip': 'spa_ip',
            'spb_ip': 'spb_ip',
            'spa_username': 'san_user',
            'Password': 'san_pw',
            'timeout': 'navi_timeout',
            'Scope': 'san_login_scope',
            'dblun_id': '{"neo4j_2": 2, "neo4j_3": 3, "neo4j_4": 4}',
            'snap_name': 'snap_prefix' + 'dblun_id',
            'descr': 'descr'
        }
        snap = Dbsnapshots()
        os.environ['VERSANT_HOST_NAME'] = 'db1-service'
        res = snap.create_neo4j_db_snapshot(args)
        self.assertTrue(ec.called)
        self.assertEquals(len(ec.call_args[0]), 1)
        #self.assertTrue("-name snap_prefixdblun_id_3" in ec.call_args[0][0])
        self.assertTrue("--snap_name=snap_prefixdblun_id_3" in ec.call_args[0][0])

        self.assertTrue(isinstance(res, dict), "Expected dict, got %s instead: "
                                               "%s" % (type(res), res))
        self.assertTrue('retcode' in res)
        self.assertTrue('err' in res)
        self.assertTrue('out' in res)
        self.assertEquals(res['retcode'], 0, "Expected retcode 0, got %s "
                                             "instead: %s" % (res['retcode'],
                                                              res['err']))
        self.assertEquals(res['err'], "", "Expected empty err, got %s instead" %
                                          res['err'])
        self.assertEquals(res['out'], "output string")

    @patch('agent.dbsnapshots.Dbsnapshots._set_neo4j_iops_limit')
    def test_force_neo4j_checkpoint(self, _set_neo4j_iops_limit):
        shell = mock.Mock()
        shell.cluster.is_single.return_value = False
        session = mock.MagicMock()
        session.Neo4jSession.return_value.__enter__.return_value = shell
        sys.modules['neo4jlib'] = mock.MagicMock()
        sys.modules['neo4jlib.client'] = mock.MagicMock()
        sys.modules['neo4jlib.client.drivers'] = mock.MagicMock()
        sys.modules['neo4jlib.client.drivers.base'] = mock.MagicMock()
        sys.modules['neo4jlib.client.session'] = session
        sys.modules['pyu'] = mock.MagicMock()
        sys.modules['pyu.error'] = mock.MagicMock()
        sys.modules['pyu.log'] = mock.MagicMock()
        snap = Dbsnapshots()
        os.environ['VERSANT_HOST_NAME'] = 'db1-service'
        res = snap.force_neo4j_checkpoint(None)
        self.assertTrue(_set_neo4j_iops_limit.called)
        self.assertEquals(_set_neo4j_iops_limit.call_count, 1)
        self.assertEquals(len(_set_neo4j_iops_limit.call_args[0]), 2)
        self.assertEquals(_set_neo4j_iops_limit.call_args[0][1], 5000)
        self.assertTrue(shell.instance.force_checkpoint.called)
        self.assertEquals(len(shell.instance.force_checkpoint.call_args[0]), 0)
        self.assertTrue(isinstance(res, dict), "Expected dict, got %s instead: "
                                               "%s" % (type(res), res))
        self.assertTrue('retcode' in res)
        self.assertTrue('err' in res)
        self.assertTrue('out' in res)
        self.assertEquals(res['retcode'], 0, "Expected retcode 0, got %s "
                                             "instead: %s" % (res['retcode'],
                                                              res['err']))
        self.assertEquals(res['err'], "", "Expected empty err, got %s instead" %
                                          res['err'])
        self.assertEquals(res['out'], "")

    @patch('agent.dbsnapshots.Dbsnapshots._set_neo4j_iops_limit')
    def test_force_neo4j_checkpoint_negative(self, _set_neo4j_iops_limit):
        shell = mock.Mock()
        shell.cluster.is_single.return_value = False
        shell.instance.force_checkpoint.side_effect = KeyError
        session = mock.MagicMock()
        session.Neo4jSession.return_value.__enter__.return_value = shell
        sys.modules['neo4jlib'] = mock.MagicMock()
        sys.modules['neo4jlib.client'] = mock.MagicMock()
        sys.modules['neo4jlib.client.drivers'] = mock.MagicMock()
        sys.modules['neo4jlib.client.drivers.base'] = mock.MagicMock()
        sys.modules['neo4jlib.client.session'] = session
        sys.modules['pyu'] = mock.MagicMock()
        sys.modules['pyu.error'] = mock.MagicMock()
        sys.modules['pyu.log'] = mock.MagicMock()
        snap = Dbsnapshots()
        os.environ['VERSANT_HOST_NAME'] = 'db1-service'
        res = snap.force_neo4j_checkpoint(None)
        self.assertTrue(_set_neo4j_iops_limit.called)
        self.assertEquals(_set_neo4j_iops_limit.call_count, 2)
        self.assertEquals(len(_set_neo4j_iops_limit.call_args[0]), 2)
        # self.assertEquals(_set_neo4j_iops_limit.mock_calls[0][1], 5000)
        # self.assertEquals(_set_neo4j_iops_limit.mock_calls[1][1], 3000)
        self.assertTrue(shell.instance.force_checkpoint.called)
        self.assertEquals(len(shell.instance.force_checkpoint.call_args[0]), 0)
        self.assertTrue(isinstance(res, dict), "Expected dict, got %s instead: "
                                               "%s" % (type(res), res))
        self.assertTrue('retcode' in res)
        self.assertTrue('err' in res)
        self.assertTrue('out' in res)
        self.assertEquals(res['retcode'], 1, "Expected retcode 1, got %s "
                                             "instead: %s" % (res['retcode'],
                                                              res['err']))
        self.assertEquals(res['out'], "", "Expected empty out, got %s instead" %
                                           res['out'])
        self.assertTrue(bool(res['err']))


    def test_set_neo4j_iops_limit(self):
        shell = mock.Mock()
        snap = Dbsnapshots()
        res = snap._set_neo4j_iops_limit(shell, 9999)
        self.assertTrue(shell.instance.set_iops_limit.called)
        self.assertEquals(len(shell.instance.set_iops_limit.call_args[0]), 1)
        self.assertEquals(shell.instance.set_iops_limit.call_args[0][0], 9999)
        self.assertTrue(res is None)

    def test_set_neo4j_iops_limit_backward_compatibility(self):
        shell = mock.Mock()
        shell.instance.set_iops_limit.side_effect = AttributeError
        shell.instance.transaction_timeout = 100
        snap = Dbsnapshots()
        res = snap._set_neo4j_iops_limit(shell, 9999)
        self.assertTrue(shell.instance.set_iops_limit.called)
        self.assertEquals(len(shell.instance.set_iops_limit.call_args[0]), 1)
        self.assertEquals(shell.instance.set_iops_limit.call_args[0][0], 9999)
        self.assertTrue(res is None)

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_create_versant_db_snapshot(self, ec):
        args = {
            'dbtype': 'versant',
            'navi_cmd': 'navi_cmd',
            'array_type': 'vnx2',
            'spa_ip': 'spa_ip',
            'spb_ip': 'spb_ip',
            'spa_username': 'san_user',
            'Password': 'san_pw',
            'timeout': 'navi_timeout',
            'Scope': 'san_login_scope',
            'dblun_id': 'dblun_id',
            'snap_name': 'snap_prefix' + 'dblun_id',
            'descr': 'descr'
        }
        snap = Dbsnapshots()
        ec.return_value = 'output string'
        os.environ['VERSANT_HOST_NAME'] = 'db1-service'

        output = snap.create_versant_db_snapshot(args)
        self.assertTrue(ec.called)
        self.assertEqual(output['err'], '')

    @patch('agent.dbsnapshots.Popen')
    def test_create_versant_db_snapshot_exception(self, popen):
        args = {
            'dbtype': 'versant',
            'navi_cmd': 'navi_cmd',
            'array_type': 'vnx2',
            'spa_ip': 'spa_ip',
            'spb_ip': 'spb_ip',
            'spa_username': 'san_user',
            'Password': 'san_pw',
            'timeout': 'navi_timeout',
            'Scope': 'san_login_scope',
            'dblun_id': 'dblun_id',
            'snap_name': 'snap_prefix' + 'dblun_id',
            'descr': 'descr'
        }
        popen.return_value.communicate.return_value = '_stdout_', '_stderr_'
        popen.return_value.returncode = 1
        snap = Dbsnapshots()
        output = snap.create_versant_db_snapshot(args)
        self.assertEqual(output['out'], '')
        self.assertIsNotNone(output['err'])

    @patch('agent.dbsnapshots.tempfile.mktemp')
    @patch('agent.dbsnapshots.Popen')
    def test_get_db_password_success(self, popen, mktemp):
        gp_file_content = 'key1=value1\npassword_key=SomeasdfWERFkey=\nkey2=12'
        gp_file = join(gettempdir(), 'global.properties')
        with open(gp_file, 'w') as gpf:
            gpf.write(gp_file_content)

        popen.return_value.communicate.return_value = '_stdout_', '_stderr_'
        popen.return_value.returncode = 0
        mktemp.return_value = 'temp_file'
        expected_cmd = 'openssl enc -a -d -aes-128-cbc -salt ' \
                       '-kfile kfile -in temp_file'
        snap = Dbsnapshots()
        snap.get_mysql_db_psw('password_key', 'kfile', gp_file)
        popen.assert_called_with(expected_cmd, shell=True, stdout=PIPE,
                                 stderr=STDOUT, env=None, preexec_fn=None)

    def test_get_db_password_no_key(self):
        gp_file_content = 'key1=value1\nkey2=12'

        gp_file = join(gettempdir(), 'global.properties')
        with open(gp_file, 'w') as gpf:
            gpf.write(gp_file_content)

        snap = Dbsnapshots()
        self.assertRaises(DbsnapshotsException, snap.get_mysql_db_psw,
                          'password_key', 'kfile', gp_file)

    @patch('agent.dbsnapshots.tempfile.mktemp')
    @patch('agent.dbsnapshots.Popen')
    def test_get_db_password_failed_decrypt(self, popen, mktemp):
        gp_file_content = 'key1=value1\npassword_key=SomeasdfWERFkey=\nkey2=12'
        gp_file = join(gettempdir(), 'global.properties')
        with open(gp_file, 'w') as gpf:
            gpf.write(gp_file_content)

        popen.return_value.communicate.return_value = '_stdout_', '_stderr_'
        popen.return_value.returncode = 7
        mktemp.return_value = 'temp_file'
        snap = Dbsnapshots()
        self.assertRaises(DbsnapshotsException, snap.get_mysql_db_psw,
                          'password_key', 'kfile', gp_file)

    @patch('agent.dbsnapshots.Dbsnapshots.get_mysql_db_psw')
    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_create_mysql_snapshot(self, exec_command, get_mysql_db_psw):
        args = {
            'dbtype': 'mysql',
            'navi_cmd': 'cmd',
            'array_type': 'vnx2',
            'spa_ip': '192.168.1.11',
            'spb_ip': '192.168.1.12',
            'spa_username': 'san_user',
            'Password': 'san_pw',
            'timeout': '50',
            'Scope': 'global',
            'dblun_id': '8',
            'snap_name': 'Snapshot_8',
            'descr': 'descr',
            'mysql_user': 'mysql_user'
        }
        get_mysql_db_psw.return_value = 'Password'
        snap = Dbsnapshots()
        snap.create_mysql_snapshot(args)

        exec_command.assert_called_with('/opt/mysql/bin/mysql --delimiter="\'" '
                                        "--user=mysql_user --password=Password "
                                        '--execute="FLUSH TABLES WITH READ'
                                        " LOCK'system "
                                        "/opt/ericsson/nms/litp/lib/sanapi/sancli.py "
                                        "create_snap "
                                        "--ip_spa=192.168.1.11 "
                                        "--ip_spb=192.168.1.12 "
                                        "--user=san_user "
                                        "--password=c2FuX3B3 "
                                        "--scope=global "
                                        "--lun_id=8 "
                                        "--snap_name=Snapshot_8 "
                                        "--array=vnx2 "
                                        '--description="descr" '
                                        "--enc=b64:_"
                                        " || echo "
                                        "FAILED_SNAP_COMMAND\n'"
                                        'UNLOCK TABLES"',
                                        use_shell=True)

    @patch('agent.dbsnapshots.Dbsnapshots.get_mysql_db_psw')
    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_create_mysql_snapshot_IOError(self, exec_command, get_mysql_db_psw):
        args = {
            'dbtype': 'mysql',
            'navi_cmd': 'cmd',
            'array_type': 'vnx2',
            'spa_ip': '192.168.1.11',
            'spb_ip': '192.168.1.12',
            'spa_username': 'san_user',
            'Password': 'san_pw',
            'timeout': '50',
            'Scope': 'global',
            'dblun_id': '8',
            'snap_name': 'Snapshot_8',
            'descr': 'descr',
            'mysql_user': 'mysql_user'
        }
        snap = Dbsnapshots()
        get_mysql_db_psw.return_value = 'Password'
        exec_command.side_effect = [IOError, 'stdout']
        out = snap.create_mysql_snapshot(args)
        self.assertEqual(out['retcode'], 1)
        self.assertTrue(out['out'] is '')

        exec_command.reset_mock()
        exec_command.side_effect = IOError
        out = snap.create_mysql_snapshot(args)
        self.assertEqual(out['retcode'], 1)
        self.assertTrue(out['out'] is '')

    @patch('agent.dbsnapshots.Dbsnapshots.create_mysql_snapshot')
    @patch('agent.dbsnapshots.Dbsnapshots.create_versant_db_snapshot')
    def test_create_snapshot(self, create_versant_db_snapshot,
                             create_mysql_snapshot):
        args = {
            'dbtype': 'mysql'
        }
        snap = Dbsnapshots()
        snap.create_snapshot(args)
        self.assertTrue(create_mysql_snapshot.called)
        args = {
            'dbtype': 'versant'
        }
        snap.create_snapshot(args)
        self.assertTrue(create_versant_db_snapshot.called)
        args = {
            'dbtype': 'mongodb'
        }
        out = snap.create_snapshot(args)
        self.assertEqual(1, out['retcode'])

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_opendj_backup(self, exec_command):
        args = {
            'opendj_backup_cmd': 'opendj_backup.sh',
            'opendj_backup_dir': '/var/tmp/opendj_backup',
            'opendj_log_dir': '/var/tmp/opendj_backup_log'
        }
        expected_cmd = '{0} {1} {2}'.format(args['opendj_backup_cmd'],
                                            args['opendj_backup_dir'],
                                            args['opendj_log_dir'])
        snap = Dbsnapshots()
        snap.opendj_backup(args)
        exec_command.assert_called_with(expected_cmd, use_shell=True,
                                        sudo='opendj')

    @patch('agent.dbsnapshots.os')
    @patch('agent.dbsnapshots.shutil.rmtree')
    def test_opendj_cleanup(self, m_rmtree, m_os):
        m_os.path.exists.return_value = True
        snap = Dbsnapshots()
        args = {
            'opendj_backup_dir': '/var/tmp/opendj_backup',
            'opendj_log_dir': '/var/tmp/opendj_backup_log'
        }
        snap.opendj_cleanup(args)
        m_rmtree.assert_has_calls([
            mock.call('/var/tmp/opendj_backup'),
            mock.call('/var/tmp/opendj_backup_log')
        ], any_order=True)

        m_rmtree.reset_mock()
        m_os.path.exists.return_value = False
        snap.opendj_cleanup(args)
        self.assertEqual(0, m_rmtree.call_count)

    @patch('agent.dbsnapshots.os')
    @patch('agent.dbsnapshots.shutil.rmtree')
    def test_opendj_OSError(self, m_rmtree, m_os):
        args = {
            'opendj_backup_dir': '/var/tmp/opendj_backup',
            'opendj_log_dir': '/var/tmp/opendj_backup_log'
        }
        snap = Dbsnapshots()
        m_os.path.exists.return_value = True
        m_rmtree.side_effect = OSError
        out = snap.opendj_cleanup(args)
        self.assertEqual(out['retcode'], 1)

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_opendj_backup_IOError(self, exec_command):
        args = {
            'opendj_backup_cmd': 'opendj_backup.sh',
            'opendj_backup_dir': '/var/tmp/opendj_backup',
            'opendj_log_dir': '/var/tmp/opendj_backup_log'
        }
        snap = Dbsnapshots()
        exec_command.side_effect = IOError
        out = snap.opendj_backup(args)
        self.assertEqual(out['retcode'], 1)
        self.assertTrue(out['out'] is '')

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_ensure_package_already_installed(self, m_exec_command):
        pkg_name = 'test_package'

        m_exec_command.side_effect = 'installed'
        ragent = Dbsnapshots()
        results = ragent.ensure_installed({'package': pkg_name})
        self.assertEqual(1, m_exec_command.call_count)
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Package {0} already installed.'.format(pkg_name),
                         results['out'])
        self.assertIsNone(results['err'])

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_ensure_package_not_currently_installed(self, m_exec_command):
        pkg_name = 'test_package'

        m_exec_command.side_effect = [
            IOError(), ''
        ]
        ragent = Dbsnapshots()
        ragent.yum_retry_wait = 1
        results = ragent.ensure_installed({'package': 'test_package'})
        self.assertEqual(2, m_exec_command.call_count)
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Installed {0}'.format(pkg_name),
                         results['out'])
        self.assertIsNone(results['err'])

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_ensure_package_yumlocks(self, m_exec_command):
        pkg_name = 'test_package'

        m_exec_command.side_effect = [
            IOError(),
            IOError('Another app is currently holding the yum lock'), ''
        ]
        ragent = Dbsnapshots()
        ragent.yum_retry_wait = 1
        results = ragent.ensure_installed({'package': pkg_name})
        self.assertEqual(3, m_exec_command.call_count)
        self.assertEqual(0, results['retcode'])
        self.assertEqual('Installed {0}'.format(pkg_name),
                         results['out'])
        self.assertIsNone(results['err'])

        m_exec_command.reset_mock()
        m_exec_command.side_effect = [
            IOError(),
            IOError('Another app is currently holding the yum lock'),
            IOError('Another app is currently holding the yum lock'),
            IOError('Another app is currently holding the yum lock'),
            IOError('Another app is currently holding the yum lock')
        ]
        results = ragent.ensure_installed({'package': pkg_name})
        self.assertEqual(1, results['retcode'])
        self.assertTrue(
            'YUM is locked, retried {0}'.format(ragent.yum_retry_count) in
            results['err'])

    @patch('agent.dbsnapshots.Dbsnapshots.exec_command')
    def test_ensure_package_install_fails(self, m_exec_command):
        m_exec_command.side_effect = [
            IOError(),
            IOError('some error')
        ]
        ragent = Dbsnapshots()
        results = ragent.ensure_installed({'package': 'test_package'})
        self.assertEqual(2, m_exec_command.call_count)
        self.assertEqual(1, results['retcode'])
        self.assertTrue('some error' in results['err'])
