import re
from collections import namedtuple

import unittest2
from mock import patch, Mock, MagicMock, call, mock_open

from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpException
from h_snapshots.lvm_snapshot import LVMManager, LVMManagerException, \
    LVMSnapshots
from litpd import LitpIntegration

TC_MODULE = 'h_snapshots.lvm_snapshot'
lv_out = "lv_home,,owi-aos---,/dev/vg_root/lv_home,vg_root,,unknown,"
lv_out_snap = "Snapshot_lv_home,enm_upgarde_snapshot,swi-a-s---,/dev/vg_root" \
              "/Snapshot_lv_home,vg_root,lv_home,,0.00," \
              "2016-12-19 23:26:40 +0000"
create_snap_output = 'File descriptor 3 (socket:[12823905]) leaked on ' \
                     'lvcreate ' \
                     'invocation. Parent PID 28341: /usr/bin/python\nFile ' \
                     'descriptor 4 (/var/log/enminst.log) leaked on lvcreate ' \
                     '' \
                     'invocation. Parent PID 28341: /usr/bin/python\nFile ' \
                     'descriptor 5 (socket:[12824005]) leaked on lvcreate ' \
                     'invocation. Parent PID 28341: /usr/bin/python\nFile ' \
                     'descriptor 9 (/dev/urandom) leaked on lvcreate ' \
                     'invocation. Parent PID 28341: /usr/bin/python\n' \
                     'Logical volume "Snapshot_lv_home" created'

lv_opts = 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,' \
          'lv_snapshot_invalid,snap_percent,lv_time'
lv_args = '--noheadings --separator , --unquoted'
LogicalVolume = namedtuple('LogicalVolume', lv_opts)
cmd_output = "File descriptor 3 (socket:[12542492]) leaked on lvs " \
             "invocation. Parent PID 51902: /usr/bin/python \n " \
             "  /dev/vg_root/Snapshot_vg1_fs_software: read failed after 0 of " \
             "4096 at 21474770944: Input/output error\n" \
             "Snapshot_lv_home,enm_upgarde_snapshot,swi-a-s---," \
             "/dev/vg_root/Snapshot_lv_home,vg_root,lv_home,,0.00,2017-01-13 16:36:06 +0000\n " \
             "lv_home,,owi-aos---,/dev/vg_root/lv_home,vg_root,,unknown,,2017-01-13 16:36:06 +0000\n" \
             "lv_var,,owi-aos---,/dev/vg_root/lv_var,vg_root,,unknown,,2017-01-13 16:36:06 +0000\n" \
             "lv_var_log,,-wi-ao----,/dev/vg_root/lv_var_log,vg_root,," \
             "unknown,,2017-01-30 12:32:55 +0000\n" \
             "vg1_fs_software,,-wi-ao----,/dev/vg_root/vg1_fs_software,vg_root" \
             ",,unknown,,2017-01-30 12:32:55 +0000"
df_output = \
    "Filesystem                        1Kblks Used Available Capacity Mountedon\n" \
    "/dev/mapper/vg_root-lv_root       15350768 2455860  12108476      17% /\n" \
    "tmpfs                             5144       0    510144       0% /dev/shm\n" \
    "/dev/sda1                         487652   28114    433938       7% /boot\n" \
    "/dev/mapper/vg_root-lv_home       6061632   12296   5734764       1% /home\n" \
    "/dev/mapper/vg--root-lv_software  192   44992  1657224       1% /var/other\n" \
    "/dev/mapper/vg_root-lv_software   192   44992  1657224       1% /software\n" \
    "/dev/mapper/vg_root-lv_var        15350768  225328  14339008       2% /var\n" \
    "/dev/mapper/vg_root-lv--var_log   1792   79056  16513160       1% /var/log\n" \
    "/dev/mapper/vg_root-lv_var_www    4892 4598768  41675420      10% /var/www\n" \
    "/dev/mapper/other--vg-my--_lv     1972    3072   1890744       1% /var/pepe\n"
ks_fss = [{'fs_snap_size': 100,
           'fs_item_id': 'home',
           'lv_path': '/dev/vg_root/lv_home',
           'lv_name': 'lv_home'
           },
          {'fs_snap_size': 100,
           'fs_item_id': 'root',
           'lv_path': '/dev/vg_root/lv_root',
           'lv_name': 'lv_root'
           },
          {'fs_snap_size': 100,
           'fs_item_id': 'var',
           'lv_path': '/dev/vg_root/lv_var',
           'lv_name': 'lv_var'
           },
          {'fs_snap_size': 100,
           'fs_item_id': 'var_www',
           'lv_path': '/dev/vg_root/lv_var_www',
           'lv_name': 'lv_var_www'
           }]


class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id


def get_ms_ks_vg_fs():
    ms_ks_fss = []
    for item_id, mount_point, ss in \
            [('home', '/home', '100'), ('root', '/', '100'),
             ('swap', 'swap', '0'), ('var', '/var', '100'),
             ('var_log', '/var/log', '0'), ('var_www', '/var/www', '100'),
             ('software', '/software', '0')]:
        ms_ks_fss.append(
                (item_id,
                 MockLitpObject(
                         "/ms/storage_profile/volume_groups/vg_ms/"
                         "file_systems/{0}".format(item_id),
                         'Applied',
                         {'snap_size': ss, 'mount_point': mount_point,
                          'type': 'ext4'},
                         item_id)
                 )
        )
    ms_vg = MockLitpObject('/ms/storage_profile/volume_groups/vg_ms',
                           'Applied',
                           {'volume_group_name': 'vg_root'},
                           'vg_ms')
    return ms_vg, ms_ks_fss


class TestLVMManager(unittest2.TestCase):
    def test_process_out(self):
        lvm = LVMManager()
        self.assertTrue(any("File descriptor 5 (/tmp/tmpf2Kqw6a (deleted)) "
                            "leaked on lvcreate invocation. Parent PID 9633:"
                            " /bin/bash " not in line for line in
                            lvm.process_out(cmd_output)))
        self.assertTrue(any('  /dev/vg_root/Snapshot_vg1_fs_software: '
                            'read failed after 0 of 4096 at 21474770944: '
                            'Input/output error' not in line for line in
                            lvm.process_out(cmd_output)))

    def test_process_lvm_output(self):
        lvm = LVMManager()
        processed = lvm.process_lvm_output(cmd_output)
        self.assertTrue(any("Snapshot_lv_home" in line for line in processed))

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_list_volumes(self, ep):
        ep.return_value = cmd_output
        lvm = LVMManager()
        self.assertTrue('lv_home' and 'Snapshot_lv_home' in vol.lv_name for vol
                        in lvm.list_volumes())

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_list_volumes_exclude_lvs(self, ep):
        ep.return_value = cmd_output
        lvm = LVMManager()
        vols = lvm.list_volumes(exclude_lv=False)
        self.assertEqual(len(vols), 5)
        vols = lvm.list_volumes()
        self.assertEqual(len(vols), 3)
        for vol in lvm.list_volumes():
            self.assertTrue('swap' not in vol.lv_name)
            self.assertTrue('var_log' not in vol.lv_name)
            self.assertTrue('software' not in vol.lv_name)

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_list_origin_volumes(self, ep):
        ep.return_value = cmd_output
        lvm = LVMManager()
        self.assertTrue('lv_home' and 'lv_var' in vol.lv_name for vol in
                        lvm.list_origin_volumes())

    @patch('h_snapshots.lvm_snapshot.LVMManager.list_snapshots')
    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_create_snapshots(self, ep, m_list_snapshots):
        volume = ks_fss
        m_list_snapshots.return_value = None
        ep.return_value = create_snap_output
        lvm = LVMManager()
        for std_out in lvm.create_snapshots(volume, pc=40,
                                            tag='test_tag'):
            self.assertTrue(re.match('^Logical volume .* created$', std_out))

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_calculate_lvm_snap_size(self, ep):
        lvs_output = "File descriptor 3 (socket:[12542492]) leaked on lvs " \
                     "invocation. Parent PID 51902: /usr/bin/python \n" \
                     "   6144.00m \n" \
                     "   51200.00m \n" \
                     "   2048.00m \n" \
                     "51200.00m \n" \
                     "20480.00m \n" \
                     "20480.00m\n"
        vgs_output = "File descriptor 3 (socket:[12542492]) leaked on lvs " \
                     "invocation. Parent PID 51902: /usr/bin/python \n " \
                     "420230.00m"
        ep.side_effect = [vgs_output, lvs_output]
        lvm = LVMManager()
        self.assertEquals(100, lvm.calculate_lvm_snap_size())
        lvs_output = """
                6144.00m
                46688.00m
                2048.00m
                51200.00m
                20480.00m
                20480.00m
            """
        ep.side_effect = ['147040.00m', lvs_output]
        self.assertEquals(90, lvm.calculate_lvm_snap_size())

    @patch('h_snapshots.lvm_snapshot.LVMManager.list_snapshots')
    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_create_snapshots_exception(self, ep, m_list_snapshots):
        m_list_snapshots.return_value = None
        volume = ks_fss
        ep.side_effect = IOError
        lvm = LVMManager()
        self.assertRaises(LVMManagerException, lvm.create_snapshots,
                          volume, pc=40)
        m_list_snapshots.reset_mock()
        m_list_snapshots.return_value = [{}]
        with self.assertRaises(LVMManagerException) as err:
            lvm.create_snapshots(volume, pc=40)
        self.assertTrue('LVM snapshots already exist' in str(err.exception))

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_remove_snpshots(self, ep):
        lvm = LVMManager()
        remove_vols = [MagicMock(lv_path='vol_a'), MagicMock(lv_path='vol_b')]
        lvm.remove_snapshots(LVMSnapshots.DEFAULT_SNAPSHOT_LABEL, remove_vols)
        self.assertTrue(ep.called)
        ep.assert_called_with(['lvremove', '-f',
                               '@' + LVMSnapshots.DEFAULT_SNAPSHOT_LABEL,
                               '@enm_upgarde_snapshot', 'vol_a', 'vol_b'])

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_restore_snapshots(self, ep):
        lvm = LVMManager()
        resore_vols = [MagicMock(lv_path='vol_a'), MagicMock(lv_path='vol_b')]
        lvm.restore_snapshots(LVMSnapshots.DEFAULT_SNAPSHOT_LABEL, resore_vols)
        self.assertTrue(ep.called)
        ep.assert_called_with(['lvconvert', '--merge',
                               '@' + LVMSnapshots.DEFAULT_SNAPSHOT_LABEL,
                               '@enm_upgarde_snapshot', 'vol_a', 'vol_b'])


class TestLVMSnapshots(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestLVMSnapshots, self).__init__(method_name)
        self.litpd = None

    def setUp(self):
        self.litpd = LitpIntegration()
        self.rh6_grub = '/boot/grub/grub.conf'
        self.rh7_grub = '/boot/grub2/grub.cfg'
        self.rh7_uefi_grub = '/boot/efi/EFI/redhat/grub.cfg'

    def tearDown(self):
        self.litpd = None


    @patch('os.path.isfile')
    def test_get_grub_files(self, p_is_file):
        p_is_file.side_effect = [False, True, True]
        self.assertEqual(('/boot/grub/grub.conf', '/boot/grub/grub.conf.org'),
                         LVMSnapshots('Snapshot')._get_grub_files())
        p_is_file.reset_mock()
        p_is_file.side_effect = [False, True, False]
        self.assertEqual(('/boot/grub/grub.conf', '/boot/grub/grub.conf.org'),
                         LVMSnapshots('Snapshot')._get_grub_files(check_grub_file=False))
        p_is_file.reset_mock()
        p_is_file.side_effect = [False, False, True]
        self.assertEqual(('/boot/grub2/grub.cfg', '/boot/grub2/grub.cfg.org'),
                         LVMSnapshots('Snapshot')._get_grub_files())
        p_is_file.reset_mock()
        p_is_file.side_effect = [False, False, True]
        self.assertEqual(('/boot/grub2/grub.cfg', '/boot/grub2/grub.cfg.org'),
                         LVMSnapshots('Snapshot')._get_grub_files(check_grub_file=False))
        p_is_file.reset_mock()
        p_is_file.side_effect = [True, False, False]

        self.assertEqual(('/boot/efi/EFI/redhat/grub.cfg', '/boot/efi/EFI/redhat/grub.cfg.org'),
                         LVMSnapshots('Snapshot')._get_grub_files())
        p_is_file.reset_mock()
        p_is_file.side_effect = [True, False, False]
        self.assertEqual(('/boot/efi/EFI/redhat/grub.cfg', '/boot/efi/EFI/redhat/grub.cfg.org'),
                         LVMSnapshots('Snapshot')._get_grub_files(
                             check_grub_file=False))


    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_list_snapshots(self, m_run_rpc_command, m_exec_process,
                            m_lvm_litp):
        mco_call_host = 'hostname-str-1'
        node_vg_name = 'vg_local'
        node_lv_name = 'lv_local_snap'
        node_snapname = 'Snapshot_{0}_{1}'.format(node_vg_name, node_lv_name)

        self.litpd.setup_svc_cluster()
        self.litpd.setup_str_cluster(mco_call_host)

        snap_lv_output = [node_snapname, 'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/{0}/{1}'.format(node_vg_name, node_snapname),
                          node_vg_name, '{0}_{1}'.format(node_vg_name,
                                                         node_lv_name),
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['{0}_{1}'.format(node_vg_name, node_lv_name), '',
                     'owi-aos---', '/dev/{0}/{0}_{1}'.format(node_vg_name,
                                                             node_lv_name),
                     node_vg_name, '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        rpc_results = {mco_call_host: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        m_run_rpc_command.return_value = rpc_results

        lms_vg_name = 'vg_root'
        lms_lv_name = 'lv_var_www'
        lms_snapname = 'Snapshot_{0}'.format(lms_lv_name)

        m_exec_process.return_value = '\n'.join([
            '{0},enm_upgrade_snapshot,swi-a-s---,/dev/{1}/{0},{1},{2},,'
            '0.00,2017-01-30 12:32:51 +0000'.format(lms_snapname,
                                                    lms_vg_name, lms_lv_name),
            '{0},,owi-aos---,/dev/{1}/{0},{1},,unknown,,'
            '2016-12-19 23:26:40 +0000'.format(lms_lv_name, lms_vg_name)])

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        lms_vols, node_vols = lvm.list_snapshots(True)
        self.assertEqual(1, len(lms_vols))
        self.assertEqual(lms_snapname, lms_vols[0].lv_name)
        self.assertEqual(lms_lv_name, lms_vols[0].origin)

        self.assertEqual(1, len(node_vols))
        self.assertIn(mco_call_host, node_vols)
        self.assertEqual(1, len(node_vols[mco_call_host]))

        self.assertEqual(node_snapname, node_vols[mco_call_host][0].lv_name)
        self.assertEqual('{0}_{1}'.format(node_vg_name, node_lv_name),
                         node_vols[mco_call_host][0].origin)

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_list_no_snapshots(self, m_run_rpc_command, m_exec_process,
                               m_lvm_litp):
        lms_vg_name = 'vg_root'
        lms_lv_name = 'lv_var_www'
        mco_call_host = 'str-1'

        m_exec_process.return_value = '\n'.join([
            '{0},,owi-aos---,/dev/{1}/{0},{1},,unknown,,'
            '2016-12-19 23:26:40 +0000'.format(lms_lv_name, lms_vg_name)])

        rpc_results = {mco_call_host: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': ''
        }}}
        m_run_rpc_command.return_value = rpc_results

        self.litpd.setup_svc_cluster()
        self.litpd.setup_str_cluster(mco_call_host)

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        lms_vols, node_vols = lvm.list_snapshots(True)
        self.assertEqual(0, len(lms_vols))
        self.assertEqual(0, len(node_vols))

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_list_snapshots_after_failed_expansion(self, m_run_rpc_command,
                                                   m_exec_process,
                                                   m_lvm_litp):
        mco_call_host = 'hostname-str-1'
        new_node = 'str-2'
        node_vg_name = 'vg_local'
        node_lv_name = 'lv_local_snap'
        node_snapname = 'Snapshot_{0}_{1}'.format(node_vg_name, node_lv_name)

        self.litpd.setup_svc_cluster()
        cluster_path = self.litpd.setup_str_cluster(mco_call_host)

        snap_lv_output = [node_snapname, 'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/{0}/{1}'.format(node_vg_name, node_snapname),
                          node_vg_name, '{0}_{1}'.format(node_vg_name,
                                                         node_lv_name),
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['{0}_{1}'.format(node_vg_name, node_lv_name), '',
                     'owi-aos---', '/dev/{0}/{0}_{1}'.format(node_vg_name,
                                                             node_lv_name),
                     node_vg_name, '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        rpc_results = {mco_call_host: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        m_run_rpc_command.return_value = rpc_results

        lms_vg_name = 'vg_root'
        lms_lv_name = 'lv_var_www'
        lms_snapname = 'Snapshot_{0}'.format(lms_lv_name)

        m_exec_process.return_value = '\n'.join([
            '{0},enm_upgrade_snapshot,swi-a-s---,/dev/{1}/{0},{1},{2},,'
            '0.00,2017-01-30 12:32:51 +0000'.format(lms_snapname,
                                                    lms_vg_name, lms_lv_name),
            '{0},,owi-aos---,/dev/{1}/{0},{1},,unknown,,'
            '2016-12-19 23:26:40 +0000'.format(lms_lv_name, lms_vg_name)])

        initial = LitpRestClient.ITEM_STATE_INITIAL
        nodepath = self.litpd.create_litp_clusternode(cluster_path, new_node,
                                                      state=initial)

        syspath = self.litpd.create_litp_system(new_node, state=initial)
        self.litpd.create_item('{0}/disks/local_disk'.format(syspath),
                               item_type='disk', properties={
                'name': 'sda'}, state=initial)
        self.litpd.inherit_object(syspath, '{0}/system'.format(nodepath))
        sprofile = '/infrastructure/storage/storage_profiles/profile'
        self.litpd.inherit_object(sprofile,
                                  '{0}/storage_profile'.format(nodepath))

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        _, node_vols = lvm.list_snapshots(True)

        self.assertIn(mco_call_host, node_vols)
        self.assertNotIn(new_node, node_vols)

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch(TC_MODULE + '.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_list_snapshots_luns_only(self, m_run_rpc_command, m_exec_process,
                                      m_lvm_litp):
        lms_vg_name = 'vg_root'
        lms_lv_name = 'lv_var_www'
        mco_call_host = 'hostname-str-1'

        m_exec_process.return_value = '\n'.join([
            '{0},,owi-aos---,/dev/{1}/{0},{1},,unknown,,'
            '2016-12-19 23:26:40 +0000'.format(lms_lv_name, lms_vg_name)])

        rpc_results = {mco_call_host: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': ''
        }}}
        m_run_rpc_command.return_value = rpc_results

        self.litpd.setup_svc_cluster()

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        lms_vols, node_vols = lvm.list_snapshots(True)
        self.assertEqual(0, len(lms_vols))
        self.assertEqual(0, len(node_vols))

    @patch(TC_MODULE + '.LVMSnapshots._get_node_snappable_localvols')
    @patch(TC_MODULE + '.LVMSnapshots._get_lms_snappable_vols')
    @patch(TC_MODULE + '.LVMManager')
    @patch(TC_MODULE + '.LVMSnapshots.copy_file')
    def test_create_snapshots(self, cf, lm,
                              m_get_lms_snappable_vols,
                              m_get_node_snappable_localvols):
        log_msg = 'Logical volume "Snapshot_lv_home" created'
        lvm = LVMSnapshots('Snapshot')
        lm.return_value.create_snapshots.return_value = [log_msg]
        m_get_lms_snappable_vols.return_value = ks_fss

        m_get_node_snappable_localvols.return_value = {
            'node-1': ks_fss
        }

        log_messages = list()

        def se(st):
            log_messages.append(st)

        lvm.logger = MagicMock()
        lvm.logger.info = se
        lvm.create_snapshots()
        self.assertTrue(cf.called)
        self.assertTrue(any(log_msg in line for line in log_messages))
        self.assertTrue(
                any('LVM SNAP: 1 node(s) with local Logical Volumes to snap.'
                    in line for line in log_messages))

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch(TC_MODULE + '.FilemanagerAgent')
    @patch(TC_MODULE + '.EnminstAgent')
    def test_create_snapshots_localstorage(self, m_enminstagent,
                                           m_filemgragent,
                                           m_lvm_litp):
        expected_mco_call_host = 'hostname-str-1'
        modeled_vg_name = 'vg_root'
        modeled_lv_name = 'lv_root'
        expected_lv_name = '{0}_{1}'.format(modeled_vg_name, modeled_lv_name)
        expected_snap_name = 'Snapshot_{0}'.format(expected_lv_name)
        expected_lv_path = '/dev/{0}/{1}'.format(modeled_vg_name,
                                                 expected_lv_name)

        self.litpd.setup_svc_cluster()
        self.litpd.setup_str_cluster(expected_mco_call_host)
        m_lvm_litp.return_value = self.litpd
        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_snap_lms_volumes = MagicMock()
        m_snap_lms_volumes.return_value = ['vol_a', 'vol_b']
        lvm.snap_lms_volumes = m_snap_lms_volumes

        m_enminstagent.return_value.create_lv_snapshots.return_value = {
            expected_mco_call_host: 'did a snap!\nand another one?'
        }

        m_filemgragent.return_value.copy_file.return_value = {
            expected_mco_call_host: 'made a copy!'
        }

        lvm.create_snapshots()
        m_enminstagent.assert_has_call(
                call().create_lv_snapshots({
                    expected_mco_call_host: [{
                        'fs_snap_size': 10,
                        'snap_name': expected_snap_name,
                        'lv_path': expected_lv_path,
                        'lv_name': expected_lv_name
                    }], 'snap_tag': 'enm_upgrade_snapshot'},
                        [expected_mco_call_host]))
        m_filemgragent.assert_has_call(
                call().copy_file('/boot/grub/grub.conf',
                                 '/boot/grub/grub.conf.org',
                                 [expected_mco_call_host])
        )

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch(TC_MODULE + '.EnminstAgent')
    def test_create_snapshots_no_localstorage(self, m_mcoagent, m_lvm_litp):

        self.litpd.setup_svc_cluster()
        m_lvm_litp.return_value = self.litpd
        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd

        m_snap_lms_volumes = MagicMock()
        m_snap_lms_volumes.return_value = ['vol_a']
        lvm.snap_lms_volumes = m_snap_lms_volumes

        lvm.create_snapshots()
        self.assertEqual(0, m_mcoagent.call_count,
                         msg='No local storage being used yet MCO '
                             'call was made!')

    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.LitpObject.children')
    def test_get_ms_ks_positive_case(self, litp_object, rest, ep):
        ep.return_value = df_output
        rest.ITEM_STATE_APPLIED = 'Applied'
        ms_vg, ms_ks_fss = get_ms_ks_vg_fs()
        litp_object.itervalues.return_value = [ms_vg]
        litp_object.iteritems.return_value = ms_ks_fss
        lvm = LVMSnapshots('Snapshot')
        self.assertEqual(ks_fss, lvm._get_lms_snappable_vols())

    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.LitpObject.children')
    def test_get_ms_ks_unmounted_fs(self, litp_object, rest, ep):
        ms_vg, extended_ms_ks_fss = get_ms_ks_vg_fs()
        extended_ms_ks_fss.append(('data', MockLitpObject(
                "/ms/storage_profile/volume_groups/vg_ms/file_systems/data",
                'Applied',
                {'snap_size': 100, 'type': 'ext4'},
                'data'
        ))
                                  )
        ep.return_value = df_output
        rest.ITEM_STATE_APPLIED = 'Applied'
        litp_object.itervalues.return_value = [ms_vg]
        litp_object.iteritems.return_value = extended_ms_ks_fss
        expected = ks_fss
        expected.append({'fs_item_id': 'data',
                         'fs_snap_size': 100,
                         'lv_name': 'vg_ms_data',
                         'lv_path': '/dev/vg_root/vg_ms_data'})
        lvm = LVMSnapshots('Snapshot')
        self.assertEqual(expected, lvm._get_lms_snappable_vols())

    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.LitpRestClient')
    @patch(TC_MODULE + '.LitpObject.children')
    def test_get_ms_ks_non_applied_items(self, litp_object, rest, ep):
        lvm_snapper = LVMSnapshots('Snapshot')
        ep.return_value = df_output
        ms_vg, ms_ks_fss = get_ms_ks_vg_fs()
        ms_ks_fss[0][1].state = 'Initial'
        rest.ITEM_STATE_APPLIED = 'Applied'
        rest.ITEM_STATE_INITIAL = 'Initial'
        litp_object.itervalues.return_value = [ms_vg]
        litp_object.iteritems.return_value = ms_ks_fss
        # won't raise exception because items in Initial get discarded

        lvm_snapper._get_lms_snappable_vols()
        ms_ks_fss[0][1].state = 'Updated'
        # but this should fail
        self.assertRaises(LVMManagerException,
                          lvm_snapper._get_lms_snappable_vols)
        ms_ks_fss[0][1].state = 'ForRemoval'
        # this too
        self.assertRaises(LVMManagerException,
                          lvm_snapper._get_lms_snappable_vols)

        rest.return_value.get.side_effect = LitpException()
        self.assertRaises(LVMManagerException,
                          lvm_snapper._get_lms_snappable_vols)

        rest.reset_mock()
        rest.return_value.get.side_effect = [
            MagicMock(), LitpException()
        ]
        self.assertRaises(LVMManagerException,
                          lvm_snapper._get_lms_snappable_vols)

    def test_parse_df_path(self):
        s = '/dev/mapper/my--volume----group-----my--volume'
        lvm = LVMSnapshots('Snapshot')
        self.assertEqual(['my-volume--group--', 'my-volume'],
                         lvm._parse_df_path(s))
        s = '/dev/mapper/myvolumegroup-mylogicalvolume'
        self.assertEqual(['myvolumegroup', 'mylogicalvolume'],
                         lvm._parse_df_path(s))
        s = '/dev/mapper/my--_volumegroup-my_volume'
        self.assertEqual(['my-_volumegroup', 'my_volume'],
                         lvm._parse_df_path(s))
        s = '/dev/mapper/myvolumegroup-my--volume'
        self.assertEqual(['myvolumegroup', 'my-volume'],
                         lvm._parse_df_path(s))
        s = '/dev/mapper/vg---a--------------volume'
        self.assertEqual(['vg-', 'a-------volume'],
                         lvm._parse_df_path(s))
        s = '/dev/sda1'
        self.assertEqual([None, None], lvm._parse_df_path(s))
        s = 'tmpfs'
        self.assertEqual([None, None], lvm._parse_df_path(s))

    @patch(TC_MODULE + '.exec_process')
    def test_get_ms_rootvg_fss(self, ep):
        ep.return_value = df_output
        lvm = LVMSnapshots('Snapshot')
        self.assertEqual([['lv_root', '/'],
                          ['lv_home', '/home'],
                          ['lv_software', '/software'],
                          ['lv_var', '/var'],
                          ['lv-var_log', '/var/log'],
                          ['lv_var_www', '/var/www']],
                         lvm._get_ms_rootvg_fss())

    @patch(TC_MODULE + '.LVMSnapshots._get_lms_snappable_vols')
    @patch(TC_MODULE + '.LVMManager')
    def test_create_snapshots_exception(self, lm, fs):
        lvm = LVMSnapshots('Snapshot')
        lm.return_value.create_snapshots.side_effect = [LVMManagerException]
        fs.return_value = ks_fss
        self.assertRaises(LVMManagerException, lvm.create_snapshots)

    @patch('os.path.isfile')
    @patch(TC_MODULE + '.exec_process')
    def test_validate_lms(self, m_exec_process, m_isfile):
        self.litpd.setup_svc_cluster()
        lv_snap = 'Snapshot_lv_var,enm_upgrade_snapshot,swi-a-s---,' \
                  '/dev/vg_root/Snapshot_lv_var,vg_root,lv_var,{0},' \
                  '1.36,2017-02-09 12:31:49 +0000'
        list_volumes = [
            lv_snap.format(''),
            'lv_var,,owi-aos---,/dev/vg_root/lv_var,vg_root,,unknown,,'
            '2016-12-19 23:26:37 +0000',
            'lv_var_log,,-wi-ao----,/dev/vg_root/lv_var_log,vg_root,,unknown'
            ',,2016-12-19 23:26:38 +0000'
        ]
        m_exec_process.return_value = '\n'.join(list_volumes)
        m_isfile.return_value = True

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_validate_node_local = MagicMock()
        m_validate_node_local.return_value = False
        lvm.validate_nodelocal_snapshots = m_validate_node_local
        lvm.validate(lms_vol_names=['lv_var'])
        self.assertEqual(1, m_isfile.call_count)

        self.assertRaises(LVMManagerException, lvm.validate,
                          lms_vol_names=['lv_var_log'])

        list_volumes[0] = lv_snap.format('lv_snapshot_invalid')
        m_exec_process.return_value = '\n'.join(list_volumes)

        _tmp = lvm.logger
        m_logger = MagicMock()
        lvm.logger = m_logger

        try:
            self.assertRaises(LVMManagerException, lvm.validate,
                              lms_vol_names=['lv_var'])
            m_logger.error.assert_has_calls([
                call.error(
                        'LVM SNAP: LMS : Snapshot Snapshot_lv_var '
                        ': lv_snapshot_invalid')
            ])
        finally:
            lvm.logger = _tmp

        m_isfile.return_value = False
        self.assertRaises(LVMManagerException, lvm.validate,
                          lms_vol_names=['lv_var'])

        m_exec_process.reset_mock()
        m_exec_process.side_effect = [
            '\n'.join(list_volumes), '\n'.join(list_volumes)]
        self.assertRaises(LVMManagerException, lvm.validate)
        self.assertEqual(2, m_exec_process.call_count)

        list_volumes = [
            'lv_var,,owi-aos---,/dev/vg_root/lv_var,vg_root,,unknown,,'
            '2016-12-19 23:26:37 +0000',
            'lv_var_log,,-wi-ao----,/dev/vg_root/lv_var_log,vg_root,,unknown'
            ',,2016-12-19 23:26:38 +0000'
        ]
        m_exec_process.reset_mock()
        m_exec_process.side_effect = ['\n'.join(list_volumes)]
        with self.assertRaises(LVMManagerException) as error:
            lvm.validate(lms_vol_names=['lv_var'])
        self.assertEqual('No LMS snapshots found on the system.',
                         str(error.exception))


    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_get_grub_save_file(self, m_run_rpc_command, m_is_env_on_rack):
        mco_call_host = 'str-1'
        grub6_rpc_results = {mco_call_host: {'errors': '',
                                             'data': {'retcode': 0,
                                                      'err': '',
                                                      'out': False}}}
        grub7_rpc_results = {mco_call_host: {'errors': '',
                                             'data': {'retcode': 0,
                                                      'err': '',
                                                      'out': True}}}
        grub7_uefi_rpc_results = {mco_call_host: {'errors': '',
                                                  'data': {'retcode': 0,
                                                           'err': '',
                                                           'out': True}}}
        m_is_env_on_rack.return_value = False
        node_local_vols = {mco_call_host: ks_fss}
        m_run_rpc_command.side_effect = [grub6_rpc_results, grub7_rpc_results]

        LVMSnapshots('Snapshot')._get_grub_save_file(node_local_vols)
        m_run_rpc_command.assert_has_calls(
            [call([mco_call_host], 'filemanager', 'exist',
                       {'file': '/boot/grub/grub.conf.org'}, retries=0,
                       timeout=None),
             call([mco_call_host], 'filemanager', 'exist',
                       {'file': '/boot/grub2/grub.cfg.org'}, retries=0,
                       timeout=None)])

        m_run_rpc_command.reset_mock()
        m_is_env_on_rack.return_value = True
        m_run_rpc_command.side_effect = [grub6_rpc_results, grub7_uefi_rpc_results]

        LVMSnapshots('Snapshot')._get_grub_save_file(node_local_vols)
        m_run_rpc_command.assert_has_calls(
            [call([mco_call_host], 'filemanager', 'exist',
                       {'file': '/boot/grub/grub.conf.org'}, retries=0,
                       timeout=None),
             call([mco_call_host], 'filemanager', 'exist',
                       {'file': '/boot/efi/EFI/redhat/grub.cfg.org'}, retries=0,
                       timeout=None)])

    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    @patch(TC_MODULE + '.LVMSnapshots.create_rhel7_node_list_file')
    def test_validate_nodelocal_is_migration_lost_node_unreachable(self,
                                             m_create_rhel7_node_list_file,
                                             m_is_migration, m_run_rpc_command,
                                             m_lvm_litp, m_is_env_on_rack):

        m_is_env_on_rack.return_value = False
        m_create_rhel7_node_list_file.return_value = True
        str_lost_node_1 = 'str-1'
        str_node_2 = 'str-2'
        node_list = [str_lost_node_1, str_node_2]
        self.litpd.setup_str_cluster_multiple_nodes(node_list)
        m_lvm_litp.return_value = self.litpd

        # ----
        # McoAgent  grub True for Rhel6
        grub6_rpc_results = {str_node_2: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': True}}}
        grub7_rpc_results = {str_node_2: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': False}}}

        snap_lv_output = ['Snap_vg_local_lv_local_snap',
                          'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/vg_local/Snap_vg_local_lv_local_snap',
                          'vg_local', 'vg_local_lv_local_snap',
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['vg_local_lv_local_snap', '',
                     'owi-aos---', '/dev/vg_local/vg_local_lv_local_snap',
                     'vg_local', '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        lv_rpc_results_2 = {str_node_2: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        lv_rpc_results_1 = {str_lost_node_1: {
            'errors':'No answer from node str-1', 'data': {}}}

        m_run_rpc_command.side_effect = [lv_rpc_results_2, lv_rpc_results_1,
                                         grub6_rpc_results, grub7_rpc_results]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        m_is_migration.return_value = True
        lvm.validate_lms_snapshots = m_validate_lms_snapshots
        lvm.validate(node_vol_names={str_lost_node_1: ['vg_local_lv_local_snap'],
                                     str_node_2:['vg_local_lv_local_snap']
                                     },
                     detailed=True)
        m_create_rhel7_node_list_file.assert_has_calls([call([u'str-1'])])

    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    @patch(TC_MODULE + '.LVMSnapshots.create_rhel7_node_list_file')
    def test_validate_nodelocal_is_migration_lost_node_reachable(self,
                                             m_create_rhel7_node_list_file,
                                             m_is_migration, m_run_rpc_command,
                                             m_lvm_litp, m_is_env_on_rack):

        m_is_env_on_rack = False
        m_create_rhel7_node_list_file.return_value = True
        str_lost_node_1 = 'str-1'
        str_node_2 = 'str-2'
        node_list = [str_lost_node_1, str_node_2]
        self.litpd.setup_str_cluster_multiple_nodes(node_list)
        m_lvm_litp.return_value = self.litpd

        # ----
        # McoAgent  grub  Rhel6 for str-2:
        #                 Rhel7 for str-1

        grub6_rpc_results = {
                             str_lost_node_1: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': False}
                                         },
                             str_node_2: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': True}
                                         }
                            }
        grub7_rpc_results = {
                             str_lost_node_1: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': False}
                                         },
                             str_node_2: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': False}
                                         }
                            }

        snap_lv_output = ['Snap_vg_local_lv_local_snap',
                          'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/vg_local/Snap_vg_local_lv_local_snap',
                          'vg_local', 'vg_local_lv_local_snap',
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['vg_local_lv_local_snap', '',
                     'owi-aos---', '/dev/vg_local/vg_local_lv_local_snap',
                     'vg_local', '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        lv_rpc_results_2 = {str_node_2: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        lv_rpc_results_1 = {str_lost_node_1: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}'.format(','.join(lv_output))
        }}}

        m_run_rpc_command.side_effect = [lv_rpc_results_1, lv_rpc_results_2,
                                         grub6_rpc_results, grub7_rpc_results]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        m_is_migration.return_value = True
        lvm.validate_lms_snapshots = m_validate_lms_snapshots

        lvm.validate(node_vol_names={str_lost_node_1: ['vg_local_lv_local_snap'],
                                     str_node_2:['vg_local_lv_local_snap']
                                     },
                     detailed=True)
        m_create_rhel7_node_list_file.assert_has_calls([call([u'str-1'])])

    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    @patch(TC_MODULE + '.LVMSnapshots.create_rhel7_node_list_file')
    def test_validate_nodelocal_is_migration_all_lost_unreachable(self,
                                             m_create_rhel7_node_list_file,
                                             m_is_migration, m_run_rpc_command,
                                             m_lvm_litp, m_is_env_on_rack):

        m_is_env_on_rack.return_value = False
        m_create_rhel7_node_list_file.return_value = True
        str_lost_node_1 = 'str-1'
        self.litpd.setup_str_cluster(str_lost_node_1)
        m_lvm_litp.return_value = self.litpd

        lv_rpc_results_1 = {str_lost_node_1: {
            'errors':'No answer from node str-1', 'data': {}}}

        m_run_rpc_command.side_effect = [lv_rpc_results_1]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        m_is_migration.return_value = True
        lvm.validate_lms_snapshots = m_validate_lms_snapshots
        lvm.validate(node_vol_names={str_lost_node_1: ['vg_local_lv_local_snap']
                                     },
                     detailed=True)
        m_create_rhel7_node_list_file.assert_has_calls([call([u'str-1'])])

    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    @patch(TC_MODULE + '.LVMSnapshots.create_rhel7_node_list_file')
    def test_validate_nodelocal_is_migration(self,
                                             m_create_rhel7_node_list_file,
                                             m_is_migration, m_run_rpc_command,
                                             m_lvm_litp, m_is_env_on_rack):

        m_is_env_on_rack = False
        m_create_rhel7_node_list_file.return_value = True
        test_node = 'str-1'
        self.litpd.setup_str_cluster(test_node)
        # ----
        # McoAgent False for both calls
        grub6_rpc_results = {test_node: {'errors': '',
                                         'data': {
                                             'retcode': 1,
                                             'err': '',
                                             'out': False}}}
        grub7_rpc_results = {test_node: {'errors': 'Not Found',
                                         'data': {
                                             'retcode': 1,
                                             'err': 'Not Found',
                                             'out': False}}}

        snap_lv_output = ['Snap_vg_local_lv_local_snap',
                          'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/vg_local/Snap_vg_local_lv_local_snap',
                          'vg_local', 'vg_local_lv_local_snap',
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['vg_local_lv_local_snap', '',
                     'owi-aos---', '/dev/vg_local/vg_local_lv_local_snap',
                     'vg_local', '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        lv_rpc_results = {test_node: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results,
                                         grub7_rpc_results]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        lvm.validate_lms_snapshots = m_validate_lms_snapshots
        m_is_migration.return_value = True
        m_logger = MagicMock()
        lvm.logger = m_logger

        self.assertRaises(LVMManagerException, lvm.validate,
                        node_vol_names={test_node: ['vg_local_lv_local_snap']})

        m_create_rhel7_node_list_file.assert_not_called()
        m_logger.error.assert_called_once_with(
            'LVM SNAP : {0} : Got no grub data from node!'.format(test_node))

        # ----
        # Snapshot not found, one McoAgentException
        grub6_rpc_results = {test_node: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': True}}}
        grub7_rpc_results = {test_node: {'errors': 'Not found',
                                         'data': {
                                             'retcode': 1,
                                             'err': 'Not found',
                                             'out': False}}}
        m_logger.reset_mock()
        lvm.logger = m_logger
        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results,
                                         grub7_rpc_results]
        self.assertRaises(LVMManagerException, lvm.validate,
                          node_vol_names={test_node: ['booooo']})
        m_logger.error.assert_called_once_with(
                'LVM SNAP : {0} : Snapshot for volume booooo '
                'not found!'.format(test_node))

        # ----
        # no grub no LV data
        test_node = 'str-2'

        m_logger.reset_mock()
        grub6_rpc_results = {test_node: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': False}}}
        grub7_rpc_results = {test_node: {'errors': 'Not Found',
                                         'data': {
                                             'retcode': 1,
                                             'err': 'Not Found',
                                             'out': True}}}

        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results, grub7_rpc_results]

        self.assertRaises(LVMManagerException, lvm.validate,
                          node_vol_names={test_node: ['vg_root_lv_local_snap']})
        m_logger.error.assert_has_calls([
            call('LVM SNAP : str-2 : Got no grub data from node!'),
            call('LVM SNAP : str-2 : Got no LV data from node!')
        ])

        # ----

        test_node = 'str-3'

        grub6_rpc_results = {'lms': {'errors': '',
                                     'data': {
                                         'retcode': 0,
                                         'err': '',
                                         'out': True}}}

        grub7_rpc_results = {'lms': {'errors': 'Not Found',
                                     'data': {
                                         'retcode': 1,
                                         'err': 'Not Found',
                                         'out': True}}}

        lv_rpc_results = {'lms': {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}
        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results, grub7_rpc_results]
        m_logger.reset_mock()
        self.assertRaises(LVMManagerException, lvm.validate,
                          node_vol_names={test_node: ['vg_root_lv_local_snap']})
        m_logger.error.assert_has_calls([
            call('LVM SNAP : str-3 : Got no grub data from node!'),
            call('LVM SNAP : str-3 : Got no LV data from node!')
        ], any_order=True)



    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_validate_nodelocal(self, m_run_rpc_command, m_lvm_litp,
                                m_is_env_on_rack):
        m_is_env_on_rack = False
        test_node = 'str-1'
        self.litpd.setup_str_cluster(test_node)
        grub6_rpc_results = {test_node: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': True}}}
        grub7_rpc_results = {test_node: {'errors': 'Not found',
                                         'data': {
                                             'retcode': 1,
                                             'err': 'Not found',
                                             'out': False}}}

        snap_lv_output = ['Snap_vg_local_lv_local_snap',
                          'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/vg_local/Snap_vg_local_lv_local_snap',
                          'vg_local', 'vg_local_lv_local_snap',
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['vg_local_lv_local_snap', '',
                     'owi-aos---', '/dev/vg_local/vg_local_lv_local_snap',
                     'vg_local', '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        lv_rpc_results = {test_node: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results,
                                         grub7_rpc_results]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        lvm.validate_lms_snapshots = m_validate_lms_snapshots
        lvm.validate(node_vol_names={test_node: ['vg_local_lv_local_snap']},
                     detailed=True)
        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results,
                                         grub7_rpc_results]
        m_logger = MagicMock()

        lvm.logger = m_logger
        self.assertRaises(LVMManagerException, lvm.validate,
                          node_vol_names={test_node: ['booooo']})
        m_logger.error.assert_called_once_with(
                'LVM SNAP : {0} : Snapshot for volume booooo '
                'not found!'.format(test_node))

        # ----

        test_node = 'str-2'

        m_logger.reset_mock()
        grub6_rpc_results = {test_node: {'errors': '',
                                         'data': {
                                             'retcode': 0,
                                             'err': '',
                                             'out': False}}}
        grub7_rpc_results = {test_node: {'errors': 'Not Found',
                                         'data': {
                                             'retcode': 1,
                                             'err': 'Not Found',
                                             'out': True}}}

        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results,
                                         grub7_rpc_results]

        self.assertRaises(LVMManagerException, lvm.validate,
                          node_vol_names={test_node: ['vg_root_lv_local_snap']})
        m_logger.error.assert_has_calls([
            call('LVM SNAP : str-2 : Got no grub data from node!'),
            call('LVM SNAP : str-2 : Got no LV data from node!')
        ])

        # ----

        test_node = 'str-3'

        grub6_rpc_results = {'lms': {'errors': '',
                                     'data': {
                                         'retcode': 0,
                                         'err': '',
                                         'out': True}}}

        grub7_rpc_results = {'lms': {'errors': 'Not Found',
                                     'data': {
                                         'retcode': 1,
                                         'err': 'Not Found',
                                         'out': True}}}

        lv_rpc_results = {'lms': {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}
        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results, grub7_rpc_results]
        m_logger.reset_mock()
        self.assertRaises(LVMManagerException, lvm.validate,
                          node_vol_names={test_node: ['vg_root_lv_local_snap']})
        m_logger.error.assert_has_calls([
            call('LVM SNAP : str-3 : Got no grub data from node!'),
            call('LVM SNAP : str-3 : Got no LV data from node!')
        ], any_order=True)

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_validate_nodelocal_after_failed_expansion_new_cluster(
            self, m_run_rpc_command, m_lvm_litp):
        """
        Scenario where a new cluster is brought in via expansion
         local volumes
        :param m_run_rpc_command:
        :return:
        """

        # Given and expanded system addition of a new cluster
        str_new_node_1 = 'str-1'
        str_new_node_2 = 'str-2'
        node_list = [str_new_node_1, str_new_node_2]
        self.litpd.setup_str_cluster_multiple_nodes(node_list)
        m_lvm_litp.return_value = self.litpd

        grub_rpc_results = {str_new_node_1: {'errors': '', 'data': {
            'retcode': 0, 'err': '', 'out': True}}}

        snap_lv_output = ['Snap_vg_local_lv_local_snap',
                          'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/vg_local/Snap_vg_local_lv_local_snap',
                          'vg_local', 'vg_local_lv_local_snap',
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['vg_local_lv_local_snap', '',
                     'owi-aos---', '/dev/vg_local/vg_local_lv_local_snap',
                     'vg_local', '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        lv_rpc_results = {str_new_node_1: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        m_run_rpc_command.side_effect = [lv_rpc_results, grub_rpc_results]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd

        m_logger = MagicMock()

        lvm.logger = m_logger

        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        lvm.validate_lms_snapshots = m_validate_lms_snapshots

        # When we validate lvm snapshots
        validation_errors = lvm.validate(node_vol_names={})

        # Then no validation will be done with new nodes picked out
        # from the model.
        m_logger.debug.assert_called_once_with("LVM SNAP: Expanded nodes [u'str-2',"
                                               " u'str-1'] not part of snapshot")
        self.assertFalse(validation_errors, "Expanded nodes should not be part "
                                            "of validation checks.")

    @patch(TC_MODULE + '.is_env_on_rack')
    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_validate_nodelocal_after_failed_expansion_new_node_in_cluster(
            self, m_run_rpc_command, m_lvm_litp, m_is_env_on_rack):

        m_is_env_on_rack.return_value = False
        # Given and expanded system with one new node in an existing cluster
        str_node = 'str-1'
        new_node = 'str-2'
        node_list = [str_node, new_node]
        self.litpd.setup_str_cluster_multiple_nodes(node_list)

        grub6_rpc_results = {str_node: {'errors': '',
                                        'data': {'retcode': 0,
                                                 'err': '',
                                                 'out': True}}}

        err_txt = 'Failed to copy /boot/grub2/grub.cfg.org to /boot/grub2/grub.cfg: No such file or directory - /boot/grub2/grub/cfg.org'
        grub7_rpc_results = {str_node: {'errors': 'File not found',
                                        'data': {'retcode': 1,
                                                 'err': err_txt,
                                                 'out': None}}}
        snap_lv_output = ['Snap_vg_local_lv_local_snap',
                          'enm_upgrade_snapshot',
                          'swi-a-s---',
                          '/dev/vg_local/Snap_vg_local_lv_local_snap',
                          'vg_local', 'vg_local_lv_local_snap',
                          '', '4.18,2017-01-30 12:32:53 +0000']
        lv_output = ['vg_local_lv_local_snap', '',
                     'owi-aos---', '/dev/vg_local/vg_local_lv_local_snap',
                     'vg_local', '', 'unknown', '',
                     '2017-01-27 15:44:34 +0000']

        lv_rpc_results = {str_node: {'errors': '', 'data': {
            'retcode': 0, 'err': '',
            'out': 'lv_name,lv_tags,lv_attr,lv_path,vg_name,origin,'
                   'lv_snapshot_invalid,snap_percent,lv_time\n  '
                   '{0}\n{1}'.format(','.join(snap_lv_output),
                                     ','.join(lv_output))
        }}}

        m_run_rpc_command.side_effect = [lv_rpc_results,
                                         grub6_rpc_results,
                                         grub7_rpc_results]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_validate_lms_snapshots = MagicMock()
        m_validate_lms_snapshots.return_value = False
        lvm.validate_lms_snapshots = m_validate_lms_snapshots

        # When validate lvm snapshots is called
        lvm.validate(node_vol_names={str_node: ['vg_local_lv_local_snap']},
                     detailed=True)

        # Then check no calls were made/attempted to str-2
        for _call in m_run_rpc_command.mock_calls:
            self.assertNotEqual(new_node, _call[1][0])

    @patch('os.path.isfile')
    @patch(TC_MODULE + '.LVMSnapshots.copy_file')
    @patch(TC_MODULE + '.LVMManager.restore_snapshots')
    def test_restore_lms_snapshots(self, m_restore_snapshots, m_copy_file, m_isfile):
        lvm = LVMSnapshots('Snapshot')
        m_restore_snapshots.return_value = []
        lvm.restore_lms_snapshots()
        self.assertTrue(m_restore_snapshots.called)
        self.assertTrue(m_copy_file.called)
        m_isfile.return_value = True

        m_restore_snapshots.return_value = ['restored one']
        lvm.restore_lms_snapshots()

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('os.remove')
    @patch('os.path.isfile')
    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_remove_snapshots(self, m_run_rpc_command, m_is_migration,
                              m_exec_process,
                              m_isfile, m_remove, m_lvm_litp):
        mco_call_host = 'hostname-str-1'

        self.litpd.setup_svc_cluster()
        self.litpd.setup_str_cluster(mco_call_host)

        m_isfile.return_value = True
        m_is_migration.return_value = False
        m_exec_process.side_effect = ['deleted a filesystem']
        m_run_rpc_command.side_effect = [
            {mco_call_host: {
                'errors': '',
                'data': {
                    'retcode': 0, 'err': '', 'out': 'deleted a filesystem'}}},
            {mco_call_host: {
                'errors': '',
                'data': {
                    'retcode': 0, 'err': '', 'out': 'deleted grub'}}}
        ]

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        lvm.remove_snapshots()

        grub_org = '/boot/efi/EFI/redhat/grub.cfg.org'
        snap_tag = 'enm_upgrade_snapshot'

        expected_isfile_calls = [call(grub_org)]
        self.assertEquals(expected_isfile_calls, m_isfile.call_args_list)

        m_remove.assert_called_with(grub_org)
        m_exec_process.assert_called_with(['lvremove', '-f',
                                           '@{0}'.format(snap_tag),
                                           '@enm_upgarde_snapshot'])
        m_run_rpc_command.assert_has_calls([
            call([mco_call_host], 'enminst', 'delete_lv_snapshots',
                 {'tag_name': snap_tag}, retries=0, timeout=None),
            call([mco_call_host], 'filemanager', 'delete',
                 {'file': grub_org}, retries=0, timeout=None)
        ], any_order=True)

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('os.remove')
    @patch('os.path.isfile')
    @patch(TC_MODULE + '.exec_process')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    def test_remove_snapshots_lost_nodes(self,
                                         m_is_migration,
                                         m_exec_process,
                                         m_isfile,
                                         m_remove,
                                         m_lvm_litp):
        mco_call_host = 'hostname-str-1'

        self.litpd.setup_svc_cluster()
        self.litpd.setup_str_cluster(mco_call_host)
        m_isfile.side_effect = [True, True]
        m_is_migration.return_value = True
        m_exec_process.side_effect = ['deleted a filesystem']

        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        read_data = "[\"hostname-str-1\"]"
        mock_openn = mock_open(read_data=read_data)
        with patch("__builtin__.open", mock_openn):
            lvm.remove_snapshots()

        grub_org = '/boot/efi/EFI/redhat/grub.cfg.org'
        snap_tag = 'enm_upgrade_snapshot'

        expected_isfile_calls = [call(grub_org),
                                 call('/ericsson/custom/rhel7_node_list_file.txt')]
        self.assertEquals(expected_isfile_calls, m_isfile.call_args_list)

        m_remove.assert_called_with(grub_org)
        m_exec_process.assert_called_with(['lvremove', '-f',
                                           '@{0}'.format(snap_tag),
                                           '@enm_upgarde_snapshot'])

    @patch(TC_MODULE + '.exec_process')
    @patch('os.remove')
    @patch('os.path.isfile')
    def test_remove_snapshots_grubfailure(self, m_isfile, m_remove,
                                          m_exec_process):
        m_isfile.return_value = True
        m_remove.side_effect = IOError
        lvm = LVMSnapshots('Snapshot')
        self.assertRaises(SystemExit, lvm.remove_snapshots)
        snap_tag = 'enm_upgrade_snapshot'
        m_exec_process.assert_called_with(['lvremove', '-f',
                                           '@{0}'.format(snap_tag),
                                           '@enm_upgarde_snapshot'])

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('os.remove')
    @patch('os.path.isfile')
    @patch(TC_MODULE + '.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    def test_remove_snapshots_nonecreated(self, m_is_migration,
                                          m_run_rpc_command,
                                          m_exec_process,
                                          m_isfile, m_remove,
                                          m_lvm_litp):
        mco_call_host = 'hostname-str-1'
        self.litpd.setup_svc_cluster()
        self.litpd.setup_str_cluster(mco_call_host)
        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        m_isfile.return_value = False
        m_is_migration.return_value = False

        m_run_rpc_command.side_effect = [
            {mco_call_host: {
                'errors': '',
                'data': {
                    'retcode': 0, 'err': '', 'out': ''}}},
            {mco_call_host: {
                'errors': '',
                'data': {
                    'retcode': 0, 'err': '', 'out': ''}}}
        ]

        lvm.remove_snapshots()

        grub6_org = '/boot/grub/grub.conf.org'
        grub7_org = '/boot/grub2/grub.cfg.org'
        grub7_uefi = '/boot/efi/EFI/redhat/grub.cfg.org'
        snap_tag = 'enm_upgrade_snapshot'

        expected_isfile_calls = [call(grub7_uefi),
                                 call(grub6_org),
                                 call(grub7_org)]
        self.assertEquals(expected_isfile_calls, m_isfile.call_args_list)

        m_isfile.assert_has_calls([call(grub7_uefi),
                                   call(grub6_org),
                                   call(grub7_org)])

        self.assertEqual(0, m_remove.call_count)
        m_exec_process.assert_called_with(['lvremove', '-f',
                                           '@{0}'.format(snap_tag),
                                           '@enm_upgarde_snapshot'])
        m_run_rpc_command.assert_has_calls([
            call([mco_call_host], 'enminst', 'delete_lv_snapshots',
                 {'tag_name': snap_tag}, retries=0, timeout=None),
            call([mco_call_host], 'filemanager', 'delete',
                 {'file': grub7_uefi}, retries=0, timeout=None)
        ], any_order=True)

    @patch('h_snapshots.lvm_snapshot.LitpRestClient')
    @patch('os.remove')
    @patch('os.path.isfile')
    @patch(TC_MODULE + '.exec_process')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch(TC_MODULE + '.LVMSnapshots.is_migration')
    def test_remove_snapshots_no_nodelocal(self, m_is_migration,
                                           m_run_rpc_command, m_exec_process,
                                           m_isfile, m_remove, m_lvm_litp):
        self.litpd.setup_svc_cluster()

        m_isfile.side_effect = [True, True]
        m_exec_process.side_effect = ['deleted a filesystem']
        m_is_migration.return_value = False
        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd
        m_lvm_litp.return_value = self.litpd
        lvm.remove_snapshots()

        grub_org = '/boot/efi/EFI/redhat/grub.cfg.org'
        snap_tag = 'enm_upgrade_snapshot'

        expected_isfile_calls = [call(grub_org)]
        self.assertEquals(expected_isfile_calls, m_isfile.call_args_list)

        m_remove.assert_called_with(grub_org)
        m_exec_process.assert_called_with(['lvremove', '-f',
                                           '@{0}'.format(snap_tag),
                                           '@enm_upgarde_snapshot'])
        self.assertEqual(0, m_run_rpc_command.call_count)

    @patch(TC_MODULE + '.shutil.copy2')
    def test_copy_file(self, cp):
        lvm = LVMSnapshots('Snapshot')
        lvm.copy_file('t1', 't2')
        cp.side_effect = IOError
        self.assertRaises(SystemExit, lvm.copy_file, 't1', 't2')

    @patch('h_snapshots.lvm_snapshot.exec_process')
    def test_reboot(self, ep):
        lvm = LVMSnapshots('Snapshot')
        lvm.reboot()
        self.assertTrue(ep.called)
        ep.assert_called_with(['shutdown', '-r', '1', '"System',
                               'is', 'going', 'down', 'for', 'reboot',
                               'in', '1', 'minute"'])

    @patch('h_puppet.mco_agents.run_rpc_command')
    def test_restore_nodelocal_snapshots(self, m_run_rpc_command):
        self.litpd.setup_svc_cluster()
        lvm = LVMSnapshots('Snapshot')
        lvm._litp = self.litpd

        lvm.restore_nodelocal_snapshots([])
        self.assertEqual(0, m_run_rpc_command.call_count)

        str_node = 'str-1'
        self.litpd.setup_str_cluster(str_node)
        grub_rpc_results = {str_node: {'errors': '', 'data': {
            'retcode': 0, 'err': '', 'out': 'Copied file.'}}}

        lv_rpc_results = {str_node: {'errors': '', 'data': {
            'retcode': 0, 'err': '', 'out': 'line1\nline2'
        }}}

        sync_rpc_results = {str_node: {'errors': '', 'data': {
            'retcode': 0, 'err': '', 'out': ''
        }}}

        m_run_rpc_command.side_effect = [
            grub_rpc_results, lv_rpc_results, sync_rpc_results
        ]

        lvm.restore_nodelocal_snapshots([str_node])

    @patch('os.path.isfile')
    @patch('os.remove')
    def test_create_rhel7_node_list_file(self, p_os_remove, p_is_file):
        p_is_file.side_effect = [False, True]
        lvm = LVMSnapshots('Snapshot')
        read_data = ['ieatebs1', 'ieatebs2']
        mock_openn = mock_open(read_data=read_data)
        with patch("__builtin__.open", mock_openn):
            lvm.create_rhel7_node_list_file(read_data)
        mock_openn.assert_called_with('/ericsson/custom/rhel7_node_list_file.txt', 'w+')
        self.assertEqual(0, p_os_remove.call_count)

        with patch("__builtin__.open", mock_openn):
            lvm.create_rhel7_node_list_file(['ieatebs1', 'ieatebs2'])
        self.assertEqual(1, p_os_remove.call_count)

    @patch('os.path.isfile')
    def test_is_migration(self, p_is_file):
        p_is_file.side_effect = [False, True]
        self.assertEqual(False, LVMSnapshots('Snapshot').is_migration())
        self.assertEqual(True, LVMSnapshots('Snapshot').is_migration())


    @patch(TC_MODULE + '.FilemanagerAgent')
    @patch(TC_MODULE + '.EnminstAgent')
    @patch(TC_MODULE + '.os.path.isfile')
    def test_torf_539295_create(self, m_isfile, m_enminstagent, m_filemgragent):

        m_enminstagent.create_lv_snapshots = Mock(return_value={})

        m_isfile.side_effect = [False, True, False, True]

        snapper = LVMSnapshots('TORF-539295-create')

        vol_data_orig = {'node-1': ks_fss,
                         'node-2': ks_fss,
                         'node-3': ks_fss,
                         'node-4': ks_fss}
        vol_hosts = vol_data_orig.keys()
        snapper._get_lms_snappable_vols = Mock(return_value=ks_fss)
        snapper.copy_file = Mock(return_value=True)
        snapper._get_node_snappable_localvols = Mock(return_value=dict(vol_data_orig))
        snapper.lvm.create_snapshots = Mock(return_value=['Created'])

        cpy_response = dict(zip(vol_hosts, ['Ok'] * len(vol_hosts)))
        m_cpy_file = Mock(return_value=cpy_response)
        m_filemgragent.return_value = Mock(copy_file=m_cpy_file)
        snapper.create_snapshots()

        rh7_uefi_call = call(self.rh7_uefi_grub, self.rh7_uefi_grub + '.org', vol_hosts)
        expected = [rh7_uefi_call]
        m_cpy_file.assert_has_calls(expected)

        # ----
        m_cpy_file.reset_mock()
        snapper._get_node_snappable_localvols = Mock(return_value=dict(vol_data_orig))
        m_isfile.return_value = False
        snapper.create_snapshots()
        m_cpy_file.assert_has_calls(expected)

    @patch(TC_MODULE + '.FilemanagerAgent')
    @patch(TC_MODULE + '.EnminstAgent')
    def test_torf_539295_restore(self, m_enminstagent, m_filemgragent):
        m_enminstagent.restore_lv_snapshots = Mock(return_value={})
        m_enminstagent.execute_sync_command = Mock(return_value={})

        restore_hosts = ['node-1', 'node-2', 'node-3', 'node-4']

        snapper = LVMSnapshots('TORF-539295-restore')

        cpy_response = dict(zip(restore_hosts, ['Ok'] * len(restore_hosts)))
        m_cpy_file = Mock(return_value=cpy_response)
        m_filemgragent.return_value = Mock(copy_file=m_cpy_file)


        rh7_uefi_call = call(self.rh7_uefi_grub + '.org', self.rh7_uefi_grub,
                             restore_hosts)
        expected = [rh7_uefi_call]

        for grub_file in (self.rh6_grub, self.rh7_grub, self.rh7_uefi_grub):

            m_cpy_file.reset_mock()

            save_file = grub_file + '.org'
            snapper.grub = grub_file
            snapper.grub_save = save_file

            snapper.restore_nodelocal_snapshots(restore_hosts)

            m_cpy_file.assert_has_calls(expected)

if __name__ == '__main__':
    unittest2.main()
