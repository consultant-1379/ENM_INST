import copy
from io import StringIO

from unittest2 import TestCase
from mock import patch, PropertyMock

from h_util.h_postgres import PostgresCredentials, PostgresCredentialsException, \
    PostgresService, PostgresServiceException
from h_puppet.mco_agents import McoAgentException, PostgresMcoAgent
from h_util.h_decorators import clear_cache
from h_vcs.vcs_cli import Vcs

GLOBAL_PROPERTIES = u"""
kpiserv=10.247.246.142
solrautoID=10.247.246.220
bnsiserv_service_IPv6_IPs=2001:1b70:82a1:103::133
connectivity=10.247.246.229
postgresql01_admin_password=encrypted_pass
default_security_admin_password=encryted_pass_2
netex=10.247.246.182
haproxysb_ipv6=2001:1b70:82a1:103::181
"""

PG_PASSKEY_F = u"5EacabwlanIHjZ8XAkoPIA=="

VCS_PG_SG_GRP_OUT = [
    {
        'ServiceState': 'ONLINE',
        'Cluster': 'db_cluster',
        'ServiceType': 'lsb',
        'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
        'GroupState': 'OK',
        'HAType': 'active-standby',
        'Frozen': '-',
        'System': 'ieatrcxb5260'
    }
]

VCS_SG_KEYS = ['Cluster', 'Group', 'System', 'HAType', 'ServiceType',
               'ServiceState', 'GroupState', 'Frozen']

MCO_RESP_ERR = {'retcode': 1,
                'err': '',
                'out': 'remote host error'}


class TestPostgresCredentials(TestCase):
    def setUp(self):
        self.pg_cred = PostgresCredentials()

    def tearDown(self):
        self.pg_cred = None

    @patch("__builtin__.open")
    @patch("os.path.exists")
    def test_enc_pass_property(self, exists, _open):
        exists.return_value = True
        _open.return_value = StringIO(GLOBAL_PROPERTIES)
        self.assertEqual(self.pg_cred._enc_pass, "encrypted_pass")

    @patch("__builtin__.open")
    @patch("os.path.exists")
    def test_enc_pass_not_found_in_global_properties(self, exists, _open):
        with self.assertRaises(PostgresCredentialsException):
            exists.return_value = True
            _open.return_value = StringIO(u"No enc pass here")
            enc_pass = self.pg_cred._enc_pass

    @patch("os.path.exists")
    def test_global_prop_file_does_not_exist(self, exists):
        with self.assertRaises(PostgresCredentialsException):
            exists.return_value = False
            enc_pass = self.pg_cred._enc_pass

    @patch("__builtin__.open")
    @patch("os.path.exists")
    def test_pg_passkey_property(self, exists, _open):
        exists.return_value = True
        _open.return_value = StringIO(PG_PASSKEY_F)
        self.assertEqual(self.pg_cred._pg_passkey, "5EacabwlanIHjZ8XAkoPIA==")

    @patch("os.path.exists")
    def test_pg_passkey_property2(self, exists):
        with self.assertRaises(PostgresCredentialsException):
            exists.return_value = False
            pass_key = self.pg_cred._pg_passkey

    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch('h_util.h_postgres.exec_process')
    def test_decrypt_password(self, exec_process, exists, _open):
        exists.return_value = True
        _open.side_effect = [StringIO(GLOBAL_PROPERTIES),
                             StringIO(PG_PASSKEY_F)]
        exec_process.return_value = "pg_pass"
        self.assertEqual(self.pg_cred.password, "pg_pass")

    @patch("__builtin__.open")
    @patch("os.path.exists")
    @patch('h_util.h_postgres.exec_process')
    def test_decrypt_password_failed_to_decrypt(self, exec_process, exists, _open):
        exists.return_value = True
        _open.side_effect = [StringIO(GLOBAL_PROPERTIES),
                             StringIO(PG_PASSKEY_F)]
        exec_process.side_effect = IOError("[Errno 1] ERROR: relation 'fs_mount_info' does not exist")
        with self.assertRaises(PostgresCredentialsException):
            password = self.pg_cred.password


class TestPostgresService(TestCase):
    def setUp(self):
        self.pg_serv = PostgresService()

    def tearDown(self):
        self.pg_serv = None

    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_postgres_version_fetched(self, password, exec_process):
        password.return_value = 'pg_pass'
        exec_process.return_value = '13'
        self.assertIsInstance(self.pg_serv.version, float)
        self.assertEquals(self.pg_serv.version, 13)

        clear_cache(self.pg_serv, 'version')

        exec_process.return_value = '9.4.9'
        self.assertIsInstance(self.pg_serv.version, float)
        self.assertEquals(self.pg_serv.version, 9.4)

    @patch.object(Vcs, "get_cluster_group_status")
    def test_postgres_sgs_offline(self, get_cluster_group_status):
        pg_sg_grp = copy.deepcopy(VCS_PG_SG_GRP_OUT)
        for i in pg_sg_grp:
            i['ServiceState'] = 'OFFLINE'
        get_cluster_group_status.return_value = pg_sg_grp, VCS_SG_KEYS

    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_perc_space_used(self, get_cluster_group_status, get_postgres_mnt_perc_used):
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS
        get_postgres_mnt_perc_used.return_value = '20%'
        self.assertIsInstance(self.pg_serv.perc_space_used, float)
        self.assertEquals(self.pg_serv.perc_space_used, 20)

    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_pg_mount_not_found(self, get_cluster_group_status, get_postgres_mnt_perc_used):
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS
        mco_resp_err = copy.deepcopy(MCO_RESP_ERR)
        mco_resp_err['retcode'] = 77
        with self.assertRaises(PostgresServiceException):
            get_postgres_mnt_perc_used.side_effect = McoAgentException(mco_resp_err)
            perc_space_used = self.pg_serv.perc_space_used

    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_pg_mount_internal_err(self, get_cluster_group_status, get_postgres_mnt_perc_used):
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS
        with self.assertRaises(PostgresServiceException):
            get_postgres_mnt_perc_used.side_effect = McoAgentException(MCO_RESP_ERR)
            perc_space_used = self.pg_serv.perc_space_used

    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_pg_mount_unexpected_err(self, get_cluster_group_status, get_postgres_mnt_perc_used):
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS
        with self.assertRaises(PostgresServiceException):
            get_postgres_mnt_perc_used.side_effect = McoAgentException("Failed")
            perc_space_used = self.pg_serv.perc_space_used

    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_not_is_contactable(self, password, exec_process):
        password.return_value = 'pg_pass'
        exec_process.side_effect = IOError("Postgres offline")
        self.assertFalse(self.pg_serv.is_contactable())

    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_is_contactable(self, password, exec_process):
        password.return_value = 'pg_pass'
        exec_process.return_value = 't'
        self.assertTrue(self.pg_serv.is_contactable())

    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_need_uplift(self, password, exec_process):
        password.return_value = 'pg_pass'

        exec_process.return_value = '9.4.9'
        self.assertTrue(self.pg_serv.need_uplift())
        clear_cache(self.pg_serv, 'version')

        exec_process.return_value = '10'
        self.assertTrue(self.pg_serv.need_uplift())
        clear_cache(self.pg_serv, 'version')

        exec_process.return_value = '12.12.5'
        self.assertTrue(self.pg_serv.need_uplift())
        clear_cache(self.pg_serv, 'version')

        exec_process.return_value = '12.6'
        self.assertTrue(self.pg_serv.need_uplift())
        clear_cache(self.pg_serv, 'version')

        exec_process.return_value = '13.8'
        self.assertFalse(self.pg_serv.need_uplift())
        clear_cache(self.pg_serv, 'version')

        exec_process.return_value = '14.4'
        self.assertFalse(self.pg_serv.need_uplift())

    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    def test_can_uplift(self, get_cluster_group_status, get_postgres_mnt_perc_used):
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS

        get_postgres_mnt_perc_used.return_value = '0%'
        self.assertTrue(self.pg_serv.can_uplift())
        clear_cache(self.pg_serv, 'perc_space_used')

        get_postgres_mnt_perc_used.return_value = '1%'
        self.assertTrue(self.pg_serv.can_uplift())
        clear_cache(self.pg_serv, 'perc_space_used')

        get_postgres_mnt_perc_used.return_value = '49.999%'
        self.assertTrue(self.pg_serv.can_uplift())
        clear_cache(self.pg_serv, 'perc_space_used')

        get_postgres_mnt_perc_used.return_value = '50%'
        self.assertFalse(self.pg_serv.can_uplift())
        clear_cache(self.pg_serv, 'perc_space_used')

        get_postgres_mnt_perc_used.return_value = '51%'
        self.assertFalse(self.pg_serv.can_uplift())

    @patch.object(PostgresService, "is_contactable")
    def test_pg_pre_uplift_checks_not_is_contactable(self, is_contactable):
        is_contactable.return_value = False
        with patch.object(self.pg_serv.logger, 'info') as mock_logger:
            with self.assertRaises(SystemExit):
                self.pg_serv.pg_pre_uplift_checks()
            mock_logger.assert_called_with("Check Status: FAILED. Postgres service is "
                                           "not contactable.")

    @patch.object(PostgresService, "is_contactable")
    @patch.object(PostgresService, "need_uplift")
    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_pg_pre_uplift_checks_not_need_uplift(self,
                                                  password,
                                                  exec_process,
                                                  need_uplift,
                                                  is_contactable):

        password.return_value = 'pg_pass'
        exec_process.return_value = '13.8'

        is_contactable.return_value = True
        need_uplift.return_value = False
        with patch.object(self.pg_serv.logger, 'info') as mock_logger:
            self.pg_serv.pg_pre_uplift_checks()
            mock_logger.assert_called_with("PostgreSQL server version {0} and is up-to-date."
                                           .format(self.pg_serv.version))

    @patch.object(PostgresService, "is_contactable")
    @patch.object(PostgresService, "need_uplift")
    @patch.object(PostgresService, "can_uplift")
    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_pg_pre_uplift_checks_can_not_uplift(self,
                                                 password,
                                                 exec_process,
                                                 get_cluster_group_status,
                                                 get_postgres_mnt_perc_used,
                                                 can_uplift,
                                                 need_uplift,
                                                 is_contactable):

        password.return_value = 'pg_pass'
        exec_process.return_value = '13.8'
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS
        get_postgres_mnt_perc_used.return_value = '51%'

        is_contactable.return_value = True
        need_uplift.return_value = True
        can_uplift.return_value = False
        with patch.object(self.pg_serv.logger, 'error') as mock_logger:
            with self.assertRaises(SystemExit):
                self.pg_serv.pg_pre_uplift_checks()
            mock_logger.assert_called_with("Check Status: FAILED. Not enough space on "
                                           "mount {0} for uplift to newer version. "
                                           "Need at least 50% free, there is currently "
                                           "{1}% free."
                                           .format(self.pg_serv.pg_mount,
                                                   100 - self.pg_serv.perc_space_used))

    @patch.object(PostgresService, "is_contactable")
    @patch.object(PostgresService, "need_uplift")
    @patch.object(PostgresService, "can_uplift")
    @patch.object(PostgresMcoAgent, "get_postgres_mnt_perc_used")
    @patch.object(Vcs, "get_cluster_group_status")
    @patch('h_util.h_postgres.exec_process')
    @patch.object(PostgresCredentials, "password", new_callable=PropertyMock)
    def test_pg_pre_uplift_checks_can_uplift(self,
                                             password,
                                             exec_process,
                                             get_cluster_group_status,
                                             get_postgres_mnt_perc_used,
                                             can_uplift,
                                             need_uplift,
                                             is_contactable):

        password.return_value = 'pg_pass'
        exec_process.return_value = '13.8'
        get_cluster_group_status.return_value = VCS_PG_SG_GRP_OUT, VCS_SG_KEYS
        get_postgres_mnt_perc_used.return_value = '30%'

        is_contactable.return_value = True
        need_uplift.return_value = True
        can_uplift.return_value = True
        with patch.object(self.pg_serv.logger, 'info') as mock_logger:
            self.pg_serv.pg_pre_uplift_checks()
            mock_logger.assert_called_with("Mount %s has enough space to uplift Postgres "
                                           "to newer version." % self.pg_serv.pg_mount)
