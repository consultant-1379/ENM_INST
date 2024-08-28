import mock
import os

from collections import namedtuple
from h_hc.hc_mdt import MdtHealthCheck
from mock import patch
from unittest2.case import TestCase

class TestMdtHealthCheck(TestCase):

    def __init__(self, methodName='runTest'):
        super(TestMdtHealthCheck, self).__init__(methodName)

    def setUp(self):
        super(TestMdtHealthCheck, self).setUp()

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_va_success(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(22528, 17542, 17680, 1048576)
        hc = MdtHealthCheck(True)
        hc.mdt_nfs_volume_healthcheck(True)

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_unityxt_success(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(22528, 17542, 17680, 1048576)
        hc = MdtHealthCheck(False)
        hc.mdt_nfs_volume_healthcheck(False)

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_sfs_verify_count_models_success(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(22528, 17542, 17680, 1048576)
        hc = MdtHealthCheck(True)
        hc.mdt_nfs_volume_healthcheck(False)

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_sfs_size_not_above_minimum(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(10240, 9622, 9697, 1048576)
        hc = MdtHealthCheck(True)
        self.assertFalse(hc.sfs_above_min_expected_size())

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_sfs_size_above_minimum(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(22528, 17542, 17680, 1048576)
        hc = MdtHealthCheck(True)
        self.assertTrue(hc.sfs_above_min_expected_size())

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_unityxt_failure(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(22528, 6000, 3680, 1048576)
        hc = MdtHealthCheck(False)
        self.assertRaises(SystemExit, hc.mdt_nfs_volume_healthcheck, False)

    @patch('os.statvfs', mock.Mock())
    def test_mdt_nfs_healthcheck_va_failure(self):
        os.statvfs.return_value = namedtuple(
            'statvfs',
            'f_blocks, f_bavail, f_bfree, f_frsize')(22528, 6000, 3680, 1048576)
        hc = MdtHealthCheck(False)
        self.assertRaises(SystemExit, hc.mdt_nfs_volume_healthcheck, True)

