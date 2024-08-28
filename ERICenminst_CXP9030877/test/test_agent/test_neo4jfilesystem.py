import sys

from mock import patch, MagicMock
from unittest2 import TestCase

from agent.neo4jfilesystem import Neo4jFilesystemStatus

MOUNT_DATA = 'Filesystem 1B-blocks Used Available Use% Mounted on' \
             '\n/dev/mapper/vg_root-vg1_lv_root\n ' \
             '1000 600 400  60% /ericsson/neo4j_data'

LUN_DATA = "'LOGICAL UNIT NUMBER 14\nName:  LITP2_ENM665_neo4j_2\n" \
           "User Capacity (Blocks):  3 \nUser Capacity (GBs):  xxxx'"

SAN_ARGS = {"lun_size": "1500"}


class TestNeo4jFilesystemStatus(TestCase):

    def setUp(self):
        self.neo4j_fs = Neo4jFilesystemStatus()

    def tearDown(self):
        self.neo4j_fs = None

    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('agent.base_agent.Popen')
    def test_pre_uplift_space_check_report(self, popen, getsize, exists):
        # side effects of popen in order:
        # neostore size, transactions size, logs size, schema size,
        # retained transactions size, transactions size, mount size
        # mount data, grep db-3 /etc/hosts, hagrp -list | grep neo4jbur
        popen.return_value.communicate.side_effect = [("500", ""), ("50", ""), ("20", ""),
                                                      ("50", ""), ("100", ""),
                                                      ("50", ""), ("20", ""),
                                                      ("30", ""),
                                                      (MOUNT_DATA, ""),
                                                      ("1.1.1.1     db-3", ""),
                                                      ("Grp_CS_db_cluster_sg_neo4jbur_clustered_service", "")]
        # labelscanstore (as excluded), relationshipgroupstore, labels,
        # nodestore, relationshipstore, labelscanstore (as removable)
        getsize.side_effect = [20, 10, 10, 30, 20, 20]

        popen.return_value.returncode = 0
        fs_rep = self.neo4j_fs.pre_uplift_space_check(SAN_ARGS)
        self.assertTrue(fs_rep["out"]["enough_space"])
        self.assertEqual(fs_rep["out"]["avail_space"], 400)
        self.assertEqual(fs_rep["out"]["reserved"], 50)
        self.assertEqual(fs_rep["out"]["extension"], 425)
        self.assertEqual(fs_rep["out"]["required"], 380)
        self.assertEqual(fs_rep["out"]["can_free"]["total"], 230)
        self.assertEqual(fs_rep["out"]["can_free"]["labels_scan"], 20)
        self.assertEqual(fs_rep["out"]["can_free"]["schema"], 100)
        self.assertEqual(fs_rep["out"]["can_free"]["logs"], 50)
        self.assertEqual(fs_rep["out"]["can_free"]["transactions"], 30)
        self.assertEqual(fs_rep["out"]["expansion_error"], "")

    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('agent.base_agent.Popen')
    def test_pre_uplift_space_check_report_40k(self, popen, getsize, exists):
        # side effects of popen in order:
        # neostore size, transactions size, logs size, schema size,
        # retained transactions size, transactions size, mount size
        # mount data, grep db-3 /etc/hosts, hagrp -list | grep neo4jbur
        returns = [
            (0, "500", ""), (0, "50", ""), (0, "20", ""), (0, "50", ""),
            (0, "100", ""), (0, "50", ""), (0, "20", ""), (0, "30", ""),
            (0, MOUNT_DATA, ""), (1, "", ""),
            (0, "Grp_CS_db_cluster_sg_neo4jbur_clustered_service", "")
        ]

        def mock_communicate():
            status, out, err = returns.pop(0)
            mock_process.returncode = status
            return out, err

        mock_process = popen.return_value
        mock_process.communicate.side_effect = mock_communicate

        # labelscanstore (as excluded), relationshipgroupstore, labels,
        # nodestore, relationshipstore, labelscanstore (as removable)
        getsize.side_effect = [20, 10, 10, 30, 20, 20]

        popen.return_value.returncode = 0
        fs_rep = self.neo4j_fs.pre_uplift_space_check(SAN_ARGS)
        self.assertTrue(fs_rep["out"]["enough_space"])
        self.assertEqual(fs_rep["out"]["avail_space"], 400)
        self.assertEqual(fs_rep["out"]["reserved"], 50)
        self.assertEqual(fs_rep["out"]["extension"], 425)
        self.assertEqual(fs_rep["out"]["required"], 380)
        self.assertEqual(fs_rep["out"]["can_free"]["total"], 230)
        self.assertEqual(fs_rep["out"]["can_free"]["labels_scan"], 20)
        self.assertEqual(fs_rep["out"]["can_free"]["schema"], 100)
        self.assertEqual(fs_rep["out"]["can_free"]["logs"], 50)
        self.assertEqual(fs_rep["out"]["can_free"]["transactions"], 30)
        self.assertEqual(fs_rep["out"]["expansion_error"], "")

    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('agent.base_agent.Popen')
    def test_pre_uplift_space_check_report_40k_expansion_error(self, popen, getsize, exists):
        # side effects of popen in order:
        # neostore size, transactions size, logs size, schema size,
        # retained transactions size, transactions size, mount size
        # mount data, grep db-3 /etc/hosts, hagrp -list | grep neo4jbur
        returns = [
            (0, "500", ""), (0, "50", ""), (0, "20", ""), (0, "50", ""),
            (0, "100", ""), (0, "50", ""), (0, "20", ""), (0, "30", ""),
            (0, MOUNT_DATA, ""), (1, "", ""), (1, "", "")
        ]

        def mock_communicate():
            status, out, err = returns.pop(0)
            mock_process.returncode = status
            return out, err

        mock_process = popen.return_value
        mock_process.communicate.side_effect = mock_communicate

        # labelscanstore (as excluded), relationshipgroupstore, labels,
        # nodestore, relationshipstore, labelscanstore (as removable)
        getsize.side_effect = [20, 10, 10, 30, 20, 20]
        #
        popen.return_value.returncode = 0
        fs_rep = self.neo4j_fs.pre_uplift_space_check(SAN_ARGS)
        self.assertTrue(fs_rep["out"], repr(fs_rep))
        self.assertTrue(fs_rep["out"]["enough_space"])
        self.assertEqual(fs_rep["out"]["avail_space"], 400)
        self.assertEqual(fs_rep["out"]["reserved"], 50)
        self.assertEqual(fs_rep["out"]["extension"], 0)
        self.assertEqual(fs_rep["out"]["expansion_error"],
                         "A filesystem expansion is only supported "
                         "on 15k/40k systems when neo4jbur volume "
                         "is available")
        self.assertEqual(fs_rep["out"]["required"], 380)
        self.assertEqual(fs_rep["out"]["can_free"]["total"], 230)
        self.assertEqual(fs_rep["out"]["can_free"]["labels_scan"], 20)
        self.assertEqual(fs_rep["out"]["can_free"]["schema"], 100)
        self.assertEqual(fs_rep["out"]["can_free"]["logs"], 50)
        self.assertEqual(fs_rep["out"]["can_free"]["transactions"], 30)

    @patch('os.path.getsize')
    @patch('agent.base_agent.Popen')
    def test_pre_uplift_space_check_report_failed(self, popen, getsize):
        # side effects of popen: neostore size, transactions size, logs size,
        #                        schema size, mount size
        popen.return_value.communicate.side_effect = [("xxx", "err msg"), ("50", ""),
                                                      ("50", ""), ("100", ""),
                                                      (MOUNT_DATA, "")]
        # labelscanstore
        getsize.return_value = 20

        popen.return_value.returncode = 0
        fs_rep = self.neo4j_fs.pre_uplift_space_check(SAN_ARGS)
        self.assertEqual(fs_rep["retcode"], 1)
        self.assertTrue("err msg" in fs_rep["err"])

    @patch('agent.base_agent.Popen')
    def test_pre_uplift_space_check_handles_error(self, popen):
        popen.return_value.communicate.side_effect = OSError("some error")
        popen.return_value.returncode = 1
        fs_rep = self.neo4j_fs.pre_uplift_space_check(SAN_ARGS)
        self.assertEqual(fs_rep["retcode"], 1)
        self.assertTrue("some error" in fs_rep["err"])

    @patch('agent.base_agent.Popen')
    def test_mount_data(self, popen):
        popen.return_value.communicate.return_value = (MOUNT_DATA, "")
        popen.return_value.returncode = 0
        data = self.neo4j_fs._mount_data
        self.assertIsInstance(data, dict)
        self.assertEqual(data["fs_path"], "/dev/mapper/vg_root-vg1_lv_root")
        self.assertEqual(data["mount_path"], "/ericsson/neo4j_data")
        self.assertEqual(data["size"], "1000")
        self.assertEqual(data["used"], "600")
        self.assertEqual(data["available"], "400")
        self.assertEqual(data["used_perc"], "60%")

    @patch('agent.base_agent.Popen')
    def test_mount_data_raise_ioerror(self, popen):
        popen.return_value.communicate.return_value = ("", "")
        popen.return_value.returncode = 1
        with self.assertRaises(IOError):
            data = self.neo4j_fs._mount_data

    @patch('agent.base_agent.Popen')
    def test_retained_transactions_size_ioerror(self, popen):
        popen.return_value.communicate.return_value = ("", "error")
        popen.return_value.returncode = 0
        with self.assertRaises(IOError):
            data = self.neo4j_fs._retained_transactions_size

    @patch('os.path.exists')
    def test_labelscanstore_dont_exist(self, exists):
        exists.return_value = False
        labelscanstore = self.neo4j_fs._labelscanstore_size
        self.assertEqual(labelscanstore, 0)

    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('agent.base_agent.Popen')
    def test_excluded_files_from_required_dont_exist(self, popen, getsize, exists):
        # neostore*, transactions
        popen.return_value.communicate.side_effect = [("500", ""), ("50", ""), ("20", ""), ("50", "")]

        # neostore*, labelscanstore, relationshipgroupstore, labels,
        # nodestore, relationshipstore, transactions
        exists.side_effect = [True, True, False, True, False]

        # labelscanstore, labels, relationshipstore
        getsize.side_effect = [10, 20, 30]

        required_space = self.neo4j_fs._required_uplift_space
        self.assertEqual(required_space, 410)

    @patch('os.path.exists')
    def test_has_file(self, exists):
        exists.side_effect = [True, False]
        ret = self.neo4j_fs.has_file({'file_path': '/path/to/file'})
        self.assertTrue(isinstance(ret, dict), ret)
        self.assertTrue('retcode' in ret)
        self.assertTrue('out' in ret)
        self.assertTrue('err' in ret)
        self.assertEquals(ret['retcode'], 0, ret)
        self.assertEquals(ret['err'], '', ret)
        self.assertEquals(ret['out'], 'true', ret)
        ret = self.neo4j_fs.has_file({'file_path': '/path/to/file'})
        self.assertTrue(isinstance(ret, dict), ret)
        self.assertTrue('retcode' in ret)
        self.assertTrue('out' in ret)
        self.assertTrue('err' in ret)
        self.assertEquals(ret['retcode'], 0, ret)
        self.assertEquals(ret['err'], '', ret)
        self.assertEquals(ret['out'], 'false', ret)

    def test_check_ssh_connectivity(self):
        sys.modules['pyu'] = MagicMock()
        sys.modules['pyu.os'] = MagicMock()
        sys.modules['pyu.os.shell'] = MagicMock()
        sys.modules['pyu.os.shell.session'] = MagicMock()
        args = {'host': 'host', 'user': 'user',
                'key_filename': '/path/to/key.pem', 'sudo': True}
        ret = self.neo4j_fs.check_ssh_connectivity(args)
        self.assertTrue(isinstance(ret, dict), ret)
        self.assertTrue('retcode' in ret)
        self.assertTrue('out' in ret)
        self.assertTrue('err' in ret)
        self.assertEquals(ret['retcode'], 0, ret)
        self.assertEquals(ret['err'], '', ret)
        self.assertEquals(ret['out'], 'ok', ret)

    def test_check_ssh_connectivity_failed(self):

        class MockedSshConnectionFailed(Exception):
            pass

        session = MagicMock()
        fail = MockedSshConnectionFailed('Connection Failed')
        session.ShellSession.return_value.check_connectivity.side_effect = fail
        session.SshConnectionFailed = MockedSshConnectionFailed

        sys.modules['pyu'] = MagicMock()
        sys.modules['pyu.os'] = MagicMock()
        sys.modules['pyu.os.shell'] = MagicMock()
        sys.modules['pyu.os.shell.session'] = session
        args = {'host': 'host', 'user': 'user',
                'key_filename': '/path/to/key.pem', 'sudo': True}
        ret = self.neo4j_fs.check_ssh_connectivity(args)
        self.assertTrue(isinstance(ret, dict), ret)
        self.assertTrue('retcode' in ret)
        self.assertTrue('out' in ret)
        self.assertTrue('err' in ret)
        self.assertEquals(ret['retcode'], 1, ret)
        self.assertEquals(ret['err'], 'Connection Failed', ret)
        self.assertEquals(ret['out'], '', ret)
