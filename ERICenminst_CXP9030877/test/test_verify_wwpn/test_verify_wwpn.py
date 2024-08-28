import os
from unittest2 import TestCase
from mock import patch

from verify_wwpn import ENMverifyWWPN


class TestVerifyWwpn(TestCase):

    def setUp(self):
        self.verifier = ENMverifyWWPN()
        self.verifier.create_arg_parser()
        self.verifier.processed_args = self.create_args()

        self.verifier.set_verbosity_level()

    def tearDown(self):
        pass

    def create_args(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))

        class Args(object):
            verbose = True
            vnx_ip_address = '10.20.30.40'
            sed_file = os.path.join(dir_path, '../Resources/sed1017')

        return Args

    def test_is_valid_ip(self):

        self.verifier.get_sed_arg = lambda: 'sed.txt'

        # +ive tests
        valid_addrs_lists = (['1.2.3.4', '10.20.30.40'],
                            ['255.255.255.255', 'fe80::8edc:d4ff:feaf:f3b9'])
        for addrs in valid_addrs_lists:
            self.verifier.sed_sp_ips = addrs
            self.assertTrue(self.verifier.is_valid_sed_sp_ips())

        # -ive tests
        invalid_addrs_lists = (['1.2.3.'],
                               ['10.20.30.40.50'],
                               ['256.256.256.256', '1.2.3.4/24'],
                               ['fe80::8edc:d4ff:feaf:f3b9/64'])
        for addrs in invalid_addrs_lists:
            self.verifier.sed_sp_ips = addrs
            self.assertRaises(SystemExit, self.verifier.is_valid_sed_sp_ips)

    def test_read_sed_file(self):
        self.assertNotEquals([], self.verifier.read_sed_file())

    def test_process_sed_wwpns(self):
        expected_list = ['50:01:43:80:12:0b:38:64',
                         '50:01:43:80:12:0b:38:66',
                         '50:01:43:80:18:70:94:8a',
                         '50:01:43:80:18:70:94:88']

        sed_dict = self.verifier.read_sed_file()
        self.verifier.process_sed_wwpns(sed_dict)
        self.assertEqual(expected_list, self.verifier.sed_wwpns)

    def test_process_datalines(self):
        expected_list = ['50:01:43:80:26:e9:e1:f1:50:01:43:80:26:e9:e1:f0',
                         '50:01:43:80:26:e9:e1:f3:50:01:43:80:26:e9:e1:f2',
                         '50:01:43:80:24:d6:49:79:50:01:43:80:24:d6:49:78',
                         '50:01:43:80:24:d6:49:7b:50:01:43:80:24:d6:49:7a']
        results_list = []

        wwpn_long_pattern = ENMverifyWWPN.WWPN_PATTERN_TEMPLATE % '15'
        pattern = r'^HBA UID:\s+(?P<wwpn>%s)\s*$' % wwpn_long_pattern

        self.verifier.process_datalines(
            self.gen_sample_vnx_output().splitlines(),
            pattern, results_list, "wwpn")

        self.assertEqual(expected_list, results_list)

    def test_compare_wwpns(self):
        self.verifier.sed_wwpns = ['50:01:43:80:26:e9:e1:f1',
                                   '50:01:43:80:26:e9:e1:f3',
                                   '50:01:43:80:24:d6:49:79',
                                   '50:01:43:80:18:70:94:8a']

        self.verifier.san_wwpns = \
            ['50:01:43:80:26:e9:e1:f0:50:01:43:80:26:e9:e1:f1',
             '50:01:43:80:26:e9:e1:f2:50:01:43:80:26:e9:e1:f3',
             '50:01:43:80:24:d6:49:78:50:01:43:80:24:d6:49:79',
             '50:01:43:80:24:d6:49:7a:50:01:43:80:24:d6:49:7b']

        call_list = [(('50:01:43:80:26:e9:e1:f1', ENMverifyWWPN.COLOR_GREEN),),
                     (('50:01:43:80:26:e9:e1:f3', ENMverifyWWPN.COLOR_GREEN),),
                     (('50:01:43:80:24:d6:49:79', ENMverifyWWPN.COLOR_GREEN),),
                     (('50:01:43:80:18:70:94:8a', ENMverifyWWPN.COLOR_RED,
                       'not '),)]

        with patch.object(ENMverifyWWPN, 'print_colored_report') as mock_method:
            self.verifier.compare_wwpns()
            self.assertEqual(mock_method.call_args_list, call_list)

    def gen_sample_vnx_output(self):
        vnx_port_list = '''
Information about each HBA:

HBA UID:                 50:01:43:80:26:E9:E1:F1:50:01:43:80:26:E9:E1:F0
Server Name:             atrcxb3344-1
Server IP Address:       10.144.6.151
HBA Model Description:
HBA Vendor Description:
HBA Device Driver Name:
Information about each port of this HBA:

SP Name:               SP A
SP Port ID:            1
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None

SP Name:               SP B
SP Port ID:            1
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None

Information about each HBA:

HBA UID:                 50:01:43:80:26:E9:E1:F3:50:01:43:80:26:E9:E1:F2
Server Name:             atrcxb3344-1
Server IP Address:       10.144.6.151
HBA Model Description:
HBA Vendor Description:
HBA Device Driver Name:
Information about each port of this HBA:

SP Name:               SP A
SP Port ID:            5
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None

SP Name:               SP B
SP Port ID:            5
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None

Information about each HBA:

HBA UID:                 50:01:43:80:24:D6:49:79:50:01:43:80:24:D6:49:78
Server Name:             ieatrcxb3034-1
Server IP Address:       10.144.4.151
HBA Model Description:
HBA Vendor Description:
HBA Device Driver Name:
Information about each port of this HBA:

SP Name:               SP A
SP Port ID:            1
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None

SP Name:               SP B
SP Port ID:            1
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None
Information about each HBA:

HBA UID:                 50:01:43:80:24:D6:49:7B:50:01:43:80:24:D6:49:7A
Server Name:             ieatrcxb3034-1
Server IP Address:       10.144.4.151
HBA Model Description:
HBA Vendor Description:
HBA Device Driver Name:
Information about each port of this HBA:

SP Name:               SP A
SP Port ID:            5
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None

SP Name:               SP B
SP Port ID:            5
HBA Devicename:
Trusted:               NO
Logged In:             NO
Defined:               YES
Initiator Type:           3
StorageGroup Name:     None
        '''
        return vnx_port_list
