import unittest2
from unittest2 import TestCase
from mock import patch
from io import StringIO
from datetime import datetime, timedelta

from verify_postgres_password_expiry import VerifyPostgresPasswordExpiry, \
    PostgresQueryFailed, DateParserFailed, PostgresDBDoesNotExist, \
    PostgresObjectDoesNotExist, PostgresExpiryNotRetrieved, \
    PostgresPasswordHasExpired

GLOBAL_PROPERTIES = u"""
kpiserv=10.247.246.142
solrautoID=10.247.246.220
bnsiserv_service_IPv6_IPs=2001:1b70:82a1:103::133
connectivity=10.247.246.229
postgresql01_admin_password=encryted_pass
default_security_admin_password=encryted_pass_2
netex=10.247.246.182
haproxysb_ipv6=2001:1b70:82a1:103::181
"""
GLOBAL_PROPERTIES_NA = u"""
Not Available
"""

INFINITEA = 'infinity'
CURRENT_DAY = datetime.now()
INVALID_DATE = (CURRENT_DAY + timedelta(days=2)).date()
VALID_DATE = (CURRENT_DAY + timedelta(days=3)).date()
STR_VALID_DATE = str(VALID_DATE)
STR_INVALID_DATE = str(INVALID_DATE)

MULTILINE_INFINITY = """
mesg: /dev/pts/19: Operation not permitted
mesg: /dev/pts/19: Operation not permitted
%s
""" % INFINITEA

MULTILINE_DATE = """
mesg: /dev/pts/19: Operation not permitted
mesg: /dev/pts/19: Operation not permitted
%s
""" % str(VALID_DATE)

MULTILINE_NO_DATE = """
mesg: /dev/pts/19: Operation not permitted
mesg: /dev/pts/19: Operation not permitted
NO_DATE
"""

EMPTY_RESPONE = ''

DATABASE_DOES_NOT_EXIST = """
FATAL: database "admindb" does not exist
"""

DATABASE_OBJECT_DOES_NOT_EXIST = """
ERROR:  relation "expiry_user" does not exist
"""


class TestVerifyPostgresExpiry(TestCase):
    global_props = '/ericsson/tor/data/global.properties'
    postgres_key = '/ericsson/tor/data/idenmgmt/postgresql01_passkey'
    openssl = '/usr/bin/openssl'
    psql = '/usr/bin/psql'
    pguser = "postgres"
    pghost = 'postgresql01'

    def setUp(self):
        self.verifier = VerifyPostgresPasswordExpiry()

    def tearDown(self):
        pass

    @patch("__builtin__.open")
    def test_get_encoded_password(self, _open):
        _open.return_value = StringIO(GLOBAL_PROPERTIES)
        self.assertEquals(self.verifier.encoded_password, '')
        self.verifier._get_encoded_password()
        self.assertEquals(self.verifier.encoded_password, 'encryted_pass')

    @patch("__builtin__.open")
    def test_get_encoded_password_not_available(self, _open):
        _open.return_value = StringIO(GLOBAL_PROPERTIES_NA)
        self.assertEquals(self.verifier.encoded_password, '')
        self.verifier._get_encoded_password()
        self.assertNotEquals(self.verifier.encoded_password, 'encryted_pass')

    @patch('verify_postgres_password_expiry.exec_process')
    def test_decode_password(self, execed_process):
        self.assertEquals(self.verifier.decoded_password, '')
        execed_process.return_value = 'PG_PASS'
        self.verifier._decode_password()
        self.assertEquals(self.verifier.decoded_password, 'PG_PASS')

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_multiline_infinity(self, execed_process):
        self.assertEquals(self.verifier.password_expiry, '')
        execed_process.return_value = MULTILINE_INFINITY
        self.verifier._set_expiry()
        self.assertEquals(self.verifier.password_expiry, INFINITEA)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_multiline_date(self, execed_process):
        self.assertEquals(self.verifier.password_expiry, '')
        execed_process.return_value = MULTILINE_DATE
        self.verifier._set_expiry()
        self.assertEquals(self.verifier.password_expiry, VALID_DATE)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_multiline_no_date_exception(self, execed_process):
        self.assertEquals(self.verifier.password_expiry, '')
        execed_process.return_value = MULTILINE_NO_DATE
        self.assertRaises(DateParserFailed, self.verifier._set_expiry)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_empty_response_exception(self, execed_process):
        self.assertEquals(self.verifier.password_expiry, '')
        execed_process.return_value = EMPTY_RESPONE
        self.assertRaises(PostgresExpiryNotRetrieved,
                          self.verifier._set_expiry)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_postgres_exception(self, execed_process):
        execed_process.side_effect = IOError
        self.assertRaises(PostgresQueryFailed, self.verifier._set_expiry)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_postgres_no_db_exception(self, execed_process):
        execed_process.side_effect = IOError(DATABASE_DOES_NOT_EXIST)
        self.assertRaises(PostgresDBDoesNotExist, self.verifier._set_expiry)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_set_expiry_postgres_no_objects_exception(self, execed_process):
        execed_process.side_effect = IOError(DATABASE_OBJECT_DOES_NOT_EXIST)
        self.assertRaises(PostgresObjectDoesNotExist,
                          self.verifier._set_expiry)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_check_connectivity_fail_exception(self, execed_process):
        execed_process.side_effect = IOError
        self.assertRaises(PostgresQueryFailed,
                          self.verifier._check_connectivity)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_calculate_expiry_invalid_date_exception(self, execed_process):
        execed_process.return_value = STR_INVALID_DATE
        self.verifier._set_expiry()
        self.assertRaises(PostgresPasswordHasExpired,
                          self.verifier._validate_expiry)

    @patch('verify_postgres_password_expiry.exec_process')
    def test_calculate_expiry_valid_date_true(self, execed_process):
        execed_process.return_value = STR_VALID_DATE
        self.verifier._set_expiry()
        self.assertIsNone(self.verifier._validate_expiry())

    @patch('verify_postgres_password_expiry.exec_process')
    def test_calculate_expiry_infinity_true(self, execed_process):
        execed_process.return_value = INFINITEA
        self.verifier._set_expiry()
        self.assertIsNone(self.verifier._validate_expiry())

    @patch('verify_postgres_password_expiry.VerifyPostgresPasswordExpiry._get_encoded_password')
    @patch('verify_postgres_password_expiry.VerifyPostgresPasswordExpiry._decode_password')
    @patch('verify_postgres_password_expiry.VerifyPostgresPasswordExpiry._check_connectivity')
    @patch('verify_postgres_password_expiry.VerifyPostgresPasswordExpiry._set_expiry')
    @patch('verify_postgres_password_expiry.VerifyPostgresPasswordExpiry._validate_expiry')
    def test_check_expiry_is_none(self, vxp, sxp, chc, dep, sep):
        self.assertIsNone(self.verifier.check_expiry())

    @patch("__builtin__.open")
    @patch('verify_postgres_password_expiry.exec_process')
    def test_check_expiry_positive(self, execed_process, _open):
        _open.return_value = StringIO(GLOBAL_PROPERTIES)
        execed_process.side_effect = ['encryted_pass', 'PG_PASS',
                                      STR_VALID_DATE]
        self.assertIsNone(self.verifier.check_expiry())

    @patch("__builtin__.open")
    @patch('verify_postgres_password_expiry.exec_process')
    def test_check_expiry_negative(self, execed_process, _open):
        _open.return_value = StringIO(GLOBAL_PROPERTIES)
        execed_process.side_effect = ['encryted_pass', 'PG_PASS',
                                      STR_INVALID_DATE]
        self.assertRaises(PostgresPasswordHasExpired,
                          self.verifier.check_expiry)


if __name__ == '__main__':
    unittest2.main()
