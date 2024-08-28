import unittest2
from mock import patch, MagicMock, call
from h_hc import hc_mp_paths
from h_hc.hc_mp_paths import MPpathsHealthCheck
from h_logging.enminst_logger import init_enminst_logging

LOGGER = init_enminst_logging()


dmp_subpaths_2ctlr = '''NAME         STATE[A]   PATH-TYPE[M] DMPNODENAME  ENCLR-NAME   CTLR   ATTRS
================================================================================
sdl          ENABLED(A) PRIMARY      emc_clariion0_137 emc_clariion0 c0        -
sdx          ENABLED    SECONDARY    emc_clariion0_137 emc_clariion0 c2        -
sdj          ENABLED(A) PRIMARY      emc_clariion0_138 emc_clariion0 c0        -
sdv          ENABLED    SECONDARY    emc_clariion0_138 emc_clariion0 c2        -
sdk          ENABLED    SECONDARY    emc_clariion0_139 emc_clariion0 c0        -
sdw          ENABLED(A) PRIMARY      emc_clariion0_139 emc_clariion0 c2        -
sdc          ENABLED(A) PRIMARY      emc_clariion0_69 emc_clariion0 c0        -
sdo          ENABLED    SECONDARY    emc_clariion0_69 emc_clariion0 c2        -
sdd          ENABLED    SECONDARY    emc_clariion0_70 emc_clariion0 c0        -
sdp          ENABLED(A) PRIMARY      emc_clariion0_70 emc_clariion0 c2        -
sde          ENABLED(A) PRIMARY      emc_clariion0_71 emc_clariion0 c0        -
sdq          ENABLED    SECONDARY    emc_clariion0_71 emc_clariion0 c2        -
sdg          ENABLED(A) PRIMARY      emc_clariion0_73 emc_clariion0 c0        -
sds          ENABLED    SECONDARY    emc_clariion0_73 emc_clariion0 c2        -
sdh          ENABLED    SECONDARY    emc_clariion0_74 emc_clariion0 c0        -
sdt          ENABLED(A) PRIMARY      emc_clariion0_74 emc_clariion0 c2        -
sdi          ENABLED(A) PRIMARY      emc_clariion0_75 emc_clariion0 c0        -
sdu          ENABLED    SECONDARY    emc_clariion0_75 emc_clariion0 c2        -
sdb          ENABLED    SECONDARY    emc_clariion0_79 emc_clariion0 c0        -
sdn          ENABLED(A) PRIMARY      emc_clariion0_79 emc_clariion0 c2        -
sda          ENABLED(A) PRIMARY      emc_clariion0_80 emc_clariion0 c0        -
sdm          ENABLED    SECONDARY    emc_clariion0_80 emc_clariion0 c2        -
sdf          ENABLED(A) PRIMARY      emc_clariion0_81 emc_clariion0 c0        -
sdr          ENABLED    SECONDARY    emc_clariion0_81 emc_clariion0 c2        -
'''

dmp_subpaths_1_ctlr_1disabled = '''NAME         STATE[A]   PATH-TYPE[M] DMPNODENAME  ENCLR-NAME   CTLR   ATTRS
================================================================================
sdaa         ENABLED    SECONDARY    emc_clariion0_11 emc_clariion0 c0        -
sdam         ENABLED    SECONDARY    emc_clariion0_11 emc_clariion0 c0        -
sdc          ENABLED(A) PRIMARY      emc_clariion0_11 emc_clariion0 c0        -
sdo          ENABLED(A) PRIMARY      emc_clariion0_11 emc_clariion0 c0        -
sdab         ENABLED(A) PRIMARY      emc_clariion0_12 emc_clariion0 c0        -
sdan         ENABLED(A) PRIMARY      emc_clariion0_12 emc_clariion0 c0        -
sdd          ENABLED    SECONDARY    emc_clariion0_12 emc_clariion0 c0        -
sdp          ENABLED    SECONDARY    emc_clariion0_12 emc_clariion0 c0        -
sdaj         ENABLED(A) SECONDARY    emc_clariion0_123 emc_clariion0 c0        -
sdav         ENABLED(A) SECONDARY    emc_clariion0_123 emc_clariion0 c0        -
sdl          ENABLED    PRIMARY      emc_clariion0_123 emc_clariion0 c0        -
sdx          ENABLED    PRIMARY      emc_clariion0_123 emc_clariion0 c0        -
sdac         ENABLED    SECONDARY    emc_clariion0_13 emc_clariion0 c0        -
sdao         ENABLED    SECONDARY    emc_clariion0_13 emc_clariion0 c0        -
sde          ENABLED(A) PRIMARY      emc_clariion0_13 emc_clariion0 c0        -
sdq          ENABLED(A) PRIMARY      emc_clariion0_13 emc_clariion0 c0        -
sdad         ENABLED(A) PRIMARY      emc_clariion0_14 emc_clariion0 c0        -
sdap         ENABLED(A) PRIMARY      emc_clariion0_14 emc_clariion0 c0        -
sdf          ENABLED    SECONDARY    emc_clariion0_14 emc_clariion0 c0        -
sdr          ENABLED    SECONDARY    emc_clariion0_14 emc_clariion0 c0        -
sdae         ENABLED    SECONDARY    emc_clariion0_15 emc_clariion0 c0        -
sdaq         ENABLED    SECONDARY    emc_clariion0_15 emc_clariion0 c0        -
sdg          ENABLED(A) PRIMARY      emc_clariion0_15 emc_clariion0 c0        -
sds          ENABLED(A) PRIMARY      emc_clariion0_15 emc_clariion0 c0        -
sdaf         ENABLED(A) PRIMARY      emc_clariion0_16 emc_clariion0 c0        -
sdar         ENABLED(A) PRIMARY      emc_clariion0_16 emc_clariion0 c0        -
sdh          ENABLED    SECONDARY    emc_clariion0_16 emc_clariion0 c0        -
sdt          ENABLED    SECONDARY    emc_clariion0_16 emc_clariion0 c0        -
sdag         ENABLED    SECONDARY    emc_clariion0_17 emc_clariion0 c0        -
sdas         ENABLED    SECONDARY    emc_clariion0_17 emc_clariion0 c0        -
sdi          ENABLED(A) PRIMARY      emc_clariion0_17 emc_clariion0 c0        -
sdu          ENABLED(A) PRIMARY      emc_clariion0_17 emc_clariion0 c0        -
sdal         ENABLED(A) PRIMARY      emc_clariion0_2 emc_clariion0 c0        -
sdb          ENABLED    SECONDARY    emc_clariion0_2 emc_clariion0 c0        -
sdn          ENABLED    SECONDARY    emc_clariion0_2 emc_clariion0 c0        -
sdz          ENABLED(A) PRIMARY      emc_clariion0_2 emc_clariion0 c0        -
sda          ENABLED(A) PRIMARY      emc_clariion0_6 emc_clariion0 c0        -
sdak         ENABLED    SECONDARY    emc_clariion0_6 emc_clariion0 c0        -
sdm          ENABLED(A) PRIMARY      emc_clariion0_6 emc_clariion0 c0        -
sdy          ENABLED    SECONDARY    emc_clariion0_6 emc_clariion0 c0        -
sdai         ENABLED(A) PRIMARY      emc_clariion0_93 emc_clariion0 c0        -
sdau         ENABLED(A) PRIMARY      emc_clariion0_93 emc_clariion0 c0        -
sdk          ENABLED    SECONDARY    emc_clariion0_93 emc_clariion0 c0        -
sdw          DISABLED(M) SECONDARY    emc_clariion0_93 emc_clariion0 c0        -
sdah         ENABLED(A) SECONDARY    emc_clariion0_95 emc_clariion0 c0        -
sdat         ENABLED(A) SECONDARY    emc_clariion0_95 emc_clariion0 c0        -
sdj          ENABLED    PRIMARY      emc_clariion0_95 emc_clariion0 c0        -
sdv          ENABLED    PRIMARY      emc_clariion0_95 emc_clariion0 c0        -
'''

dmp_subpaths_infoscale = '''NAME         STATE[A]   PATH-TYPE[M] DMPNODENAME  ENCLR-NAME   CTLR           ATTRS      PRIORITY
=================================================================================================
sdag         ENABLED(A) Active/Optimized(P) emc_clariion0_25 emc_clariion0 c2              -         -
sdah         ENABLED(A) Active/Optimized(P) emc_clariion0_25 emc_clariion0 c0              -         -
sdbd         ENABLED(A) Active/Optimized(P) emc_clariion0_25 emc_clariion0 c0              -         -
sdbg         ENABLED(A) Active/Optimized(P) emc_clariion0_25 emc_clariion0 c2              -         -
sdc          ENABLED    Active/Non-Optimized emc_clariion0_25 emc_clariion0 c2              -         -
sdca         ENABLED    Active/Non-Optimized emc_clariion0_25 emc_clariion0 c0              -         -
'''

multipath_ll_htype1 = """mpathc (36006016007b038001502f409ed11e911) dm-0 DGC,VRAID
size=50G features='2 queue_if_no_path' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:1 sdh 8:112 active ready running
| `- 0:0:3:1 sdk 8:160 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:0:1 sdb 8:16  active ready running
  `- 0:0:1:1 sde 8:64  active ready running
"""

multipath_ll_htype2 = """reload: mpathq (360050768029180b06000000000000007) dm-8 IBM,2145
size=2.5G features='1 queue_if_no_path' hwhandler='0' wp=rw
| `- 5:0:0:7 sdr 65:16 failed ready running
`- 6:0:0:7 sdi 8:128 failed ready running
mpathp (360050768029180b06000000000000005) dm-3 IBM,2145
size=2.5G features='1 queue_if_no_path' hwhandler='0' wp=rw
| `- 5:0:0:5 sdp 8:240 failed ready running
`- 6:0:0:5 sdg 8:96  failed ready running"""

multipath_ll_htype3 = """3600d0230000000000e13955cc3757800 dm-1 WINSYS,SF2372
size=269G features='0' hwhandler='0' wp=rw
|-+- policy='round-robin 0' prio=1 status=active
| `- 6:0:0:0 sdb 8:16  active ready  running
`-+- policy='round-robin 0' prio=1 status=enabled
`- 7:0:0:0 sdf 8:80  active ready  running"""

multipath_ll_2ctrl = """mpathc (36006016027a04000e3dd9ce823b5e811) dm-0 DGC,VRAID
size=250G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:2 sdi 8:128  active ready running
| |- 2:0:3:2 sdx 65:112 active ready running
| |- 0:0:3:2 sdl 8:176  active ready running
| `- 2:0:2:2 sdu 65:64  active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:0:2 sdc 8:32   active ready running
  |- 2:0:0:2 sdo 8:224  active ready running
  |- 0:0:1:2 sdf 8:80   active ready running
  `- 2:0:1:2 sdr 65:16  active ready running
mpathb (36006016027a0400016b98cad23b5e811) dm-1 DGC,VRAID
size=50G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:1 sdh 8:112  failed ready running
| |- 2:0:3:1 sdw 65:96  active ready running
| |- 0:0:3:1 sdk 8:160  active ready running
| `- 2:0:2:1 sdt 65:48  failed ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:0:1 sdb 8:16   active ready running
  |- 2:0:0:1 sdn 8:208  active ready running
  |- 0:0:1:1 sde 8:64   active ready running
  `- 2:0:1:1 sdq 65:0   active ready running
mpatha (36006016027a0400039f909cc23b5e811) dm-2 DGC,VRAID
size=50G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:0:0 sda 8:0    active ready running
| |- 2:0:0:0 sdm 8:192  active ready running
| |- 0:0:1:0 sdd 8:48   active ready running
| `- 2:0:1:0 sdp 8:240  active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:2:0 sdg 8:96   active ready running
  |- 2:0:2:0 sds 65:32  active ready running
  |- 0:0:3:0 sdj 8:144  active ready running
  `- 2:0:3:0 sdv 65:80  active ready running"""

multipath_ll_1ctrl = """mpathc (36006016057703d00be0b1de70525e911) dm-2 DGC,VRAID
size=50G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:0:0 sda 8:0   active ready running
| `- 0:0:1:0 sdg 8:96  active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:2:0 sdk 8:160 active ready running
  `- 0:0:3:0 sdn 8:208 active ready running
mpathb (36006016057703d00ae485dfd0525e911) dm-1 DGC,VRAID
size=250G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:2 sdm 8:192 active ready running
| `- 0:0:3:2 sdp 8:240 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:0:2 sdf 8:80  active ready running
  `- 0:0:1:2 sdj 8:144 active ready running
mpatha (36006016057703d00ef71cdcf0525e911) dm-0 DGC,VRAID
size=50G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:1 sdl 8:176 active ready running
| `- 0:0:3:1 sdo 8:224 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:1:1 sdi 8:128 active ready running
  `- 0:0:0:1 sdd 8:48  active ready running"""


multipath_ll_1ctrl_double_space = """mpathc (36006016057703d00be0b1de70525e911) dm-2 DGC,VRAID
size=50G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:0:0 sda 8:0   active ready running
| `- 0:0:1:0 sdg 8:96  active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:2:0 sdk 8:160 active ready running
  `- 0:0:3:0 sdn 8:208 active ready running
mpathb (36006016057703d00ae485dfd0525e911) dm-1 DGC,VRAID
size=250G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:2 sdm  8:192 active ready running
| `- 0:0:3:2 sdp 8:240 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:0:2 sdf 8:80  active ready running
  `- 0:0:1:2 sdj 8:144 active ready running
mpatha (36006016057703d00ef71cdcf0525e911) dm-0 DGC,VRAID
size=50G features='2 queue_if_no_path retain_attached_hw_handler' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:1 sdl 8:176 active ready running
| `- 0:0:3:1 sdo 8:224 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 0:0:1:1 sdi 8:128 active ready running
  `- 0:0:0:1 sdd 8:48  active ready running"""

mp_conf_one_mpath = """mpatha"""

mp_conf_three_mpath = """mpatha
mpathb
mpathc"""

mco_fct_dsk_no_mpath = """  disk_6000c29a61a7b980e2b6cb3fea1c0668_dev: /dev/sda
  disk_6000c29a61a7b980e2b6cb3fea1c0668_part1_dev: /dev/sda1
  disk_6000c29a61a7b980e2b6cb3fea1c0668_part2_dev: /dev/sda2
  disk_sda: /dev/sda
  disk_sda1: /dev/sda1
  disk_sda2: /dev/sda2
  disk_wmp_6000c29a61a7b980e2b6cb3fea1c0668_dev: /dev/sda
  disk_wmp_6000c29a61a7b980e2b6cb3fea1c0668_part1_dev: /dev/sda1
  disk_wmp_6000c29a61a7b980e2b6cb3fea1c0668_part2_dev: /dev/sda2
dev_mapper_list:
total 0
crw-rw----. 1 root root 10, 58 Nov  1 07:02 control
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_etc -> ../dm-5
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_opt -> ../dm-6
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_root -> ../dm-0
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_swap -> ../dm-1
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_var -> ../dm-2
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_var_ericsson -> ../dm-4
lrwxrwxrwx. 1 root root      7 Nov  1 07:02 vg_root-vg1_lv_vms -> ../dm-3
"""

mco_fct_dsk_good_mpath = """  disk_600601601d703c0030d312e9e338ec11_dev: /dev/mapper/mpathb
  disk_600601601d703c00a22c6218e438ec11_dev: /dev/mapper/mpathc
  disk_600601601d703c00b2edf4ffe338ec11_dev: /dev/mapper/mpatha
  disk_600601601d703c00b2edf4ffe338ec11_part1_dev: /dev/mapper/mpathap1
  disk_600601601d703c00b2edf4ffe338ec11_part2_dev: /dev/mapper/mpathap2
  disk_sdv: /dev/mapper/mpatha
  disk_sdw: /dev/mapper/mpathb
  disk_sdx: /dev/mapper/mpathc
  disk_wmp_600601601d703c0030d312e9e338ec11_dev: /dev/sdw
  disk_wmp_600601601d703c00a22c6218e438ec11_dev: /dev/sdx
  disk_wmp_600601601d703c00b2edf4ffe338ec11_dev: /dev/sdv
dev_mapper_list:
total 0
crw-rw----. 1 root root 10, 58 Oct 29 23:27 control
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpatha -> ../dm-0
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathap1 -> ../dm-1
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathap2 -> ../dm-2
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathb -> ../dm-3
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathc -> ../dm-4
lrwxrwxrwx. 1 root root      8 Oct 29 23:27 vg_app-vg2_lv_etc -> ../dm-10
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_app-vg2_lv_opt -> ../dm-9
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_app-vg2_lv_var_ericsson -> ../dm-8
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_root-vg1_lv_root -> ../dm-5
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_root-vg1_lv_swap -> ../dm-6
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_root-vg1_lv_var -> ../dm-7
lrwxrwxrwx. 1 root root      8 Oct 29 23:27 vg_vmvg-vg3_lv_vms -> ../dm-11
"""

mco_fct_dsk_bad_mpath = """  disk_600601601d703c0030d312e9e338ec11_dev: /dev/mapper/sdx
  disk_600601601d703c00a22c6218e438ec11_dev: /dev/mapper/mpathc
  disk_600601601d703c00b2edf4ffe338ec11_dev: /dev/mapper/mpatha
  disk_600601601d703c00b2edf4ffe338ec11_part1_dev: /dev/mapper/mpathap1
  disk_600601601d703c00b2edf4ffe338ec11_part2_dev: /dev/mapper/mpathap2
  disk_sdv: /dev/mapper/mpatha
  disk_sdw: /dev/mapper/mpathb
  disk_sdx: /dev/mapper/mpathc
  disk_wmp_600601601d703c0030d312e9e338ec11_dev: /dev/sdw
  disk_wmp_600601601d703c00a22c6218e438ec11_dev: /dev/sdx
  disk_wmp_600601601d703c00b2edf4ffe338ec11_dev: /dev/sdv
dev_mapper_list:
total 0
crw-rw----. 1 root root 10, 58 Oct 29 23:27 control
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpatha -> ../dm-0
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathap1 -> ../dm-1
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathap2 -> ../dm-2
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathb -> ../dm-3
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 mpathc -> ../dm-4
lrwxrwxrwx. 1 root root      8 Oct 29 23:27 vg_app-vg2_lv_etc -> ../dm-10
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_app-vg2_lv_opt -> ../dm-9
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_app-vg2_lv_var_ericsson -> ../dm-8
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_root-vg1_lv_root -> ../dm-5
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_root-vg1_lv_swap -> ../dm-6
lrwxrwxrwx. 1 root root      7 Oct 29 23:27 vg_root-vg1_lv_var -> ../dm-7
lrwxrwxrwx. 1 root root      8 Oct 29 23:27 vg_vmvg-vg3_lv_vms -> ../dm-11
"""


class TestMPpathsHealthCheck(unittest2.TestCase):

    def __init__(self, methodName='runTest'):
        super(TestMPpathsHealthCheck, self).__init__(methodName)
        self.mp = MPpathsHealthCheck(verbose=True)

    def setUp(self):
        super(TestMPpathsHealthCheck, self).setUp()
        # Reset MP_REQUIREMENTS as Test test_process_node_mp_metadata sets the
        # unity paths_per_hba to '1' with flag fc_switches='false'.
        hc_mp_paths.MP_REQUIREMENTS = {
            'vnx': {'paths_per_hba': 4,
                    'number_of_hbas': 2
                    },
            'unity': {'paths_per_hba': 3,
                      'number_of_hbas': 2
                      },
        }

    def tearDown(self):
        super(TestMPpathsHealthCheck, self).tearDown()

    def test_create_dbnode_dmp_metadata(self):
        d = {'emc_clariion0_137': {'c0': {'enabled': ['sdl']}, 'c2': {'enabled': ['sdx']}},
 'emc_clariion0_138': {'c0': {'enabled': ['sdj']}, 'c2': {'enabled': ['sdv']}},
 'emc_clariion0_139': {'c0': {'enabled': ['sdk']}, 'c2': {'enabled': ['sdw']}},
 'emc_clariion0_69': {'c0': {'enabled': ['sdc']}, 'c2': {'enabled': ['sdo']}},
 'emc_clariion0_70': {'c0': {'enabled': ['sdd']}, 'c2': {'enabled': ['sdp']}},
 'emc_clariion0_71': {'c0': {'enabled': ['sde']}, 'c2': {'enabled': ['sdq']}},
 'emc_clariion0_73': {'c0': {'enabled': ['sdg']}, 'c2': {'enabled': ['sds']}},
 'emc_clariion0_74': {'c0': {'enabled': ['sdh']}, 'c2': {'enabled': ['sdt']}},
 'emc_clariion0_75': {'c0': {'enabled': ['sdi']}, 'c2': {'enabled': ['sdu']}},
 'emc_clariion0_79': {'c0': {'enabled': ['sdb']}, 'c2': {'enabled': ['sdn']}},
 'emc_clariion0_80': {'c0': {'enabled': ['sda']}, 'c2': {'enabled': ['sdm']}},
 'emc_clariion0_81': {'c0': {'enabled': ['sdf']}, 'c2': {'enabled': ['sdr']}}}
        self.assertEqual(d, self.mp._create_dbnode_dmp_metadata("db-node", dmp_subpaths_2ctlr))

        d = {'emc_clariion0_11': {'c0': {'enabled': ['sdaa', 'sdam', 'sdc', 'sdo']}},
 'emc_clariion0_12': {'c0': {'enabled': ['sdab', 'sdan', 'sdd', 'sdp']}},
 'emc_clariion0_123': {'c0': {'enabled': ['sdaj', 'sdav', 'sdl', 'sdx']}},
 'emc_clariion0_13': {'c0': {'enabled': ['sdac', 'sdao', 'sde', 'sdq']}},
 'emc_clariion0_14': {'c0': {'enabled': ['sdad', 'sdap', 'sdf', 'sdr']}},
 'emc_clariion0_15': {'c0': {'enabled': ['sdae', 'sdaq', 'sdg', 'sds']}},
 'emc_clariion0_16': {'c0': {'enabled': ['sdaf', 'sdar', 'sdh', 'sdt']}},
 'emc_clariion0_17': {'c0': {'enabled': ['sdag', 'sdas', 'sdi', 'sdu']}},
 'emc_clariion0_2': {'c0': {'enabled': ['sdal', 'sdb', 'sdn', 'sdz']}},
 'emc_clariion0_6': {'c0': {'enabled': ['sda', 'sdak', 'sdm', 'sdy']}},
 'emc_clariion0_93': {'c0': {'disabled': ['sdw'],
                             'enabled': ['sdai', 'sdau', 'sdk']}},
 'emc_clariion0_95': {'c0': {'enabled': ['sdah', 'sdat', 'sdj', 'sdv']}}}
        self.assertEqual(d, self.mp._create_dbnode_dmp_metadata("db-node", dmp_subpaths_1_ctlr_1disabled))

    def test_create_dbnode_dmp_metadata_infoscale(self):
        d = {'emc_clariion0_25' : {'c2': {'enabled': ['sdag', 'sdbg', 'sdc']},
                                   'c0': {'enabled': ['sdah', 'sdbd', 'sdca']}}}
        self.assertEqual(d, self.mp._create_dbnode_dmp_metadata("db-node", dmp_subpaths_infoscale))

    def test_create_non_dbnode_mp_metadata(self):
        d = {'36006016007b038001502f409ed11e911': {'0': {'enabled': ['sdh', 'sdk', 'sdb', 'sde']}}}
        self.assertEqual(d, self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_htype1))

        d = {'360050768029180b06000000000000005': {'5': {'disabled': ['sdp']}, '6': {'disabled': ['sdg']}},
             '360050768029180b06000000000000007': {'5': {'disabled': ['sdr']}, '6': {'disabled': ['sdi']}}}
        self.assertEqual(d, self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_htype2))

        d = {'3600d0230000000000e13955cc3757800': {'7': {'enabled': ['sdf']}, '6': {'enabled': ['sdb']}}}
        self.assertEqual(d, self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_htype3))

        d = {'36006016027a0400016b98cad23b5e811': {'0': {'disabled': ['sdh'],
                                                         'enabled': ['sdk', 'sdb', 'sde']},
                                                   '2': {'disabled': ['sdt'],
                                                         'enabled': ['sdw', 'sdn', 'sdq']}},
             '36006016027a0400039f909cc23b5e811': {'0': {'enabled': ['sda', 'sdd', 'sdg', 'sdj']},
                                                   '2': {'enabled': ['sdm', 'sdp', 'sds', 'sdv']}},
             '36006016027a04000e3dd9ce823b5e811': {'0': {'enabled': ['sdi', 'sdl', 'sdc', 'sdf']},
                                                   '2': {'enabled': ['sdx', 'sdu', 'sdo', 'sdr']}}}
        self.assertEqual(d, self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_2ctrl))

    def test_process_node_mp_metadata(self):
        db_ok = {'emc_clariion0_11': {'c0': {'enabled': ['sdaa', 'sdam', 'sdc', 'sdo']},
                                      'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}},
                 'emc_clariion0_12': {'c0': {'enabled': ['sdab', 'sdan', 'sdd', 'sdp']},
                                      'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}}}
        db_ok_unity = {'emc_clariion0_11': {'c0': {'enabled': ['sdam', 'sdc', 'sdo']},
                                      'c2': {'enabled': ['sdbm', 'sdj', 'sdk']}},
                       'emc_clariion0_12': {'c0': {'enabled': ['sdan', 'sdd', 'sdp']},
                                      'c2': {'enabled': ['sdbm', 'sdj', 'sdk']}}}
        db_ok_xt_direct = {'emc_clariion0_7': {'c0': {'enabled': ['sdam']},
                                      'c2': {'enabled': ['sdbm']}},
                       'emc_clariion0_8': {'c0': {'enabled': ['sdan']},
                                      'c2': {'enabled': ['sdbm']}}}
        db_nok1 = {'emc_clariion0_11': {'c0': {'enabled': ['sdaa', 'sdc', 'sdo']},
                                        'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}},
                   'emc_clariion0_12': {'c0': {'enabled': ['sdab', 'sdan', 'sdd', 'sdp']},
                                        'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}}}
        db_nok2 = {'emc_clariion0_6': {'c0': {'enabled': ['sda', 'sdak', 'sdm', 'sdy']},
                                       'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}},
                   'emc_clariion0_93': {'c0': {'disabled': ['sdw'],
                                               'enabled': ['sdai', 'sdau', 'sdk']},
                                        'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}}}
        self.assertFalse(self.mp._process_node_mp_metadata('node1', 'DB', db_ok))
        self.assertTrue(self.mp._process_node_mp_metadata('node1', 'DB', db_nok1))
        self.assertTrue(self.mp._process_node_mp_metadata('node1', 'DB', db_nok2))
        # in the unity case, succeed only if the deployment is of unity type
        self.assertTrue(self.mp._process_node_mp_metadata('node1', 'DB', db_ok_unity))
        self.assertFalse(MPpathsHealthCheck(verbose=True, deployment_type='unity', fc_switches='true').\
                         _process_node_mp_metadata('node2', 'DB', db_ok_unity))
        #Direct connection for UnityXT
        self.assertFalse(MPpathsHealthCheck(verbose=True, deployment_type='unity', fc_switches='false').\
                         _process_node_mp_metadata('node3', 'DB', db_ok_xt_direct))

    @patch('logging.Logger.error')
    @patch('logging.Logger.info')
    def test_process_node_mp_metadata_logging(self, m_info, m_error):
        print("-------------------------------------------")
        print("test_process_node_mp_metadata_logging")
        db_ok = {'emc_clariion0_11': {'c0': {'enabled': ['sdaa', 'sdam', 'sdc', 'sdo']},
                                      'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}},
                 'emc_clariion0_12': {'c0': {'enabled': ['sdab', 'sdan', 'sdd', 'sdp']},
                                      'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}}}
        db_nok1 = {'emc_clariion0_11': {'c0': {'enabled': ['sdaa', 'sdc', 'sdo']},
                                        'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}},
                   'emc_clariion0_12': {'c0': {'enabled': ['sdab', 'sdan', 'sdd', 'sdp']},
                                        'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}}}
        db_nok2 = {'emc_clariion0_6': {'c0': {'enabled': ['sda', 'sdak', 'sdm', 'sdy']},
                                       'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}},
                   'emc_clariion0_93': {'c0': {'disabled': ['sdw'],
                                               'enabled': ['sdai', 'sdau', 'sdk']},
                                        'c2': {'enabled': ['sdba', 'sdbm', 'sdj', 'sdk']}}}
        db_nok_unity = {'emc_clariion0_11': {'c0': {'disabled': ['sdw', 'sdam'],
                                                    'enabled': ['sdc', 'sdo']},
                                             'c2': {'enabled': ['sdbm', 'sdj', 'sdk']}},
                       'emc_clariion0_12': {'c0': {'enabled': ['sdan', 'sdd', 'sdp']}}}

        self.assertFalse(self.mp._process_node_mp_metadata('node1', 'DB', db_ok))
        self.assertTrue(self.mp._process_node_mp_metadata('node1', 'DB', db_nok1))
        self.assertTrue(self.mp._process_node_mp_metadata('node1', 'DB', db_nok2))

        m_info.assert_any_call(
            "ERROR: DB node node1 has 1 disabled paths [sdw] on disk "
            "emc_clariion0_93 and controller c0")
        m_error.assert_any_call(
            "ERROR: DB node node1 has 3 enabled paths (4 expected), "
            "[sdai, sdau, sdk], on disk emc_clariion0_93 and controller c0")

        #Direct connection for UnityXT
        unity_mp = MPpathsHealthCheck(verbose=True, deployment_type='unity')
        self.assertTrue(unity_mp._process_node_mp_metadata('node3', 'DB', db_nok_unity))

        m_info.assert_any_call(
            "ERROR: DB node node3 has 2 disabled paths [sdw,sdam] on disk "
            "emc_clariion0_11 and controller c0. This can be OK for Unity "
            "deployments if a minimum of 3 paths are enabled")
        m_error.assert_any_call(
            "ERROR: DB node node3 has 2 enabled paths (minimum of 3 expected),"
            " [sdc, sdo], on disk emc_clariion0_11 and controller c0")

    def test_process_dmp_paths_node_output(self):
        with patch.object(self.mp, '_create_dbnode_dmp_metadata') as cddm:
            self.mp._process_node_mp_metadata = MagicMock(return_value=False)
            self.assertFalse(self.mp.process_dmp_paths_node_output(
                'node1', dmp_subpaths_2ctlr, mp_conf_three_mpath, mco_fct_dsk_good_mpath))
            cddm.assert_has_calls([call("node1", dmp_subpaths_2ctlr)])
        with patch.object(self.mp, '_create_dbnode_dmp_metadata') as cddm:
            self.mp._process_node_mp_metadata = MagicMock(return_value=True)
            self.assertTrue(self.mp.process_dmp_paths_node_output(
                'node1', dmp_subpaths_1_ctlr_1disabled, mp_conf_three_mpath, mco_fct_dsk_good_mpath))
            cddm.assert_has_calls([call("node1", dmp_subpaths_1_ctlr_1disabled)])
        with patch.object(self.mp, '_create_non_dbnode_mp_metadata') as cddm:
            self.mp._process_node_mp_metadata = MagicMock(return_value=True)
            self.assertTrue(self.mp.process_dmp_paths_node_output(
                'node1', multipath_ll_2ctrl, mp_conf_three_mpath, mco_fct_dsk_good_mpath))
            cddm.assert_has_calls([call("node1", multipath_ll_2ctrl)])
        with patch.object(self.mp, '_create_non_dbnode_mp_metadata') as cddm:
            self.mp._process_node_mp_metadata = MagicMock(return_value=False)
            self.assertFalse(self.mp.process_dmp_paths_node_output(
                'node1', multipath_ll_htype1, mp_conf_three_mpath, mco_fct_dsk_good_mpath))
            cddm.assert_has_calls([call("node1", multipath_ll_htype1)])

    def test_check_all_controllers_used(self):
        processed = self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_1ctrl)
        self.assertTrue(
            self.mp._check_all_controllers_used('n1', 'DB', processed))
        processed = self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_1ctrl_double_space)
        self.assertTrue(
            self.mp._check_all_controllers_used('n1', 'DB', processed))
        processed = self.mp._create_non_dbnode_mp_metadata("node1", multipath_ll_2ctrl)
        self.assertFalse(
            self.mp._check_all_controllers_used('n1', 'DB', processed))

    def test_check_mco_facts_mpath_disks(self):
        self.assertTrue(
            self.mp._check_mco_facts_mpath_disks("node1", mp_conf_one_mpath, mco_fct_dsk_no_mpath))
        self.assertFalse(
            self.mp._check_mco_facts_mpath_disks("node1", mp_conf_one_mpath, mco_fct_dsk_good_mpath))
        self.assertTrue(
            self.mp._check_mco_facts_mpath_disks("node1", mp_conf_three_mpath, mco_fct_dsk_no_mpath))
        self.assertFalse(
            self.mp._check_mco_facts_mpath_disks("node1", mp_conf_three_mpath, mco_fct_dsk_good_mpath))
        self.assertTrue(
            self.mp._check_mco_facts_mpath_disks("node1", mp_conf_three_mpath, mco_fct_dsk_bad_mpath))
