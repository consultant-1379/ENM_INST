import argparse
import httplib
import os
from json import dumps
from os.path import dirname
from os.path import join
from tempfile import gettempdir
from collections import OrderedDict

import mock
import unittest2
from mock import patch, MagicMock, call, PropertyMock

import sys

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

import test_utils
import test_hw_resources.test_hw_resources as test_hw
from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpObject
from h_logging import enminst_logger
from h_xml.xml_utils import load_xml
from hw_resources import HwResources
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mock
from h_puppet.mco_agents import McoAgentException
from h_util.h_nas_console import NasConsoleException
from h_hc.hc_neo4j_cluster import DbNodesSshCredentials, \
    Neo4jClusterOverview, Neo4jClusterOverviewException, \
    FORCE_SSH_KEY_ACCESS_FLAG_PATH

builtin_os_path_exists = os.path.exists

systems = '''
  --------------  -------  -----------  ------
          System    State      Cluster  Frozen
  --------------  -------  -----------  ------
  ieatrcxb2539-1  RUNNING  svc_cluster       -
  ieatrcxb2540-1  RUNNING  svc_cluster       -
  ieatrcxb2537-1  RUNNING   db_cluster       -
  ieatrcxb2538-1  RUNNING   db_cluster       -
  --------------  -------  -----------  ------
'''

all_nodes = '''
  --------------  ------
          System   State
  --------------  ------
  ieatrcxb2539-1  ONLINE
  ieatrcxb2537-1  ONLINE
  ieatrcxb2538-1  ONLINE
  ieatrcxb2540-1  ONLINE
   ieatlms4352-1  ONLINE
  --------------  ------
'''

services = '''
  -------------  --------  ------
         System   Service   State
  -------------  --------  ------
  ieatlms4352-1  cobblerd  ONLINE
  -------------  --------  ------
'''

df_nok_versant = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
versant_fs                           vxfs    50G  2.6G   45G   93% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  15% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   80% /test
'''

df_nok_elastic = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
elastic_fs                           vxfs    50G  2.6G   45G   93% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  15% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   80% /test
'''

df_ok_nas = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
/dev/mapper/vg_root-lv_root          ext4    50G  2.6G   45G   55% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  22% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   4% /test
'''

df_nok_nas = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
/dev/mapper/vg_root-lv_root          ext4    50G  2.6G   45G   55% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  22% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   91% /test
'''

df_nok = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
/dev/mapper/vg_root-lv_root          ext4    50G  2.6G   45G   92% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  15% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   81% /test
'''

df_ok = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
/dev/mapper/vg_root-lv_root          ext4    50G  2.6G   45G   80% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  15% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   1% /test
'''

df_faulty = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
/dev/mapper/vg_root-lv_root          ext4    50G  2.6G   45G   80% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/mapper/vg_root-vg1_fs_data      ext4    50G -1.1G   48G   - /var/lib/mysql
/dev/sda1                            ext4   477M   65M  387M  15% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   1% /test
'''

df_mounted_iso = '''
Filesystem                           Type   Size  Used Avail Use% Mounted on
/dev/mapper/vg_root-lv_root          ext4    50G  2.6G   45G   70% /
tmpfs                                tmpfs   63G     0   63G   0% /dev/shm
/dev/sda1                            ext4   477M   65M  387M  15% /boot
10.144.64.17:/vx/ENM266-mdt          nfs     10G  783M  8.7G   1% /test
/root/litp_iso                       iso9660  1G    1G     0   100% /media/litp
'''

ls_va_ok = '''
agentlet  clish-parser  extern   isagui  log       pysnas      tools
bin       conf          gui      lib     man       repository  upgrade
clish     core          install  lib64   nodeconf  scripts

'''
nas_audit_out = '''
        [INFO]     Running NAS Audit Script (Revision A) at 2017-08-03 11:44:32

        [INFO] Report generated to /home/support/audit_report/NAS_Audit_VA_20170803114432.html
'''

nas_audit_check_ok = '''

        --- NAS Audit ---
Last run: 2017-08-03_11:45:03
Errors: 0
Warnings: 0
Not Collected: 0
Report: /home/support/audit_report/NAS_Audit_VA_20170803114432.html

'''

nas_audit_check_err = '''

        --- NAS Audit ---
Last run: 2017-08-03_11:45:03
Errors: 1
Warnings: 0
Not Collected: 0
Report: /home/support/audit_report/NAS_Audit_VA_20170803114432.html

'''

nas_audit_check_warn = '''

        --- NAS Audit ---
Last run: 2017-08-03_11:45:03
Errors: 0
Warnings: 1
Not Collected: 0
Report: /home/support/audit_report/NAS_Audit_VA_20170803114432.html

'''

nas_audit_check_err_warn = '''

        --- NAS Audit ---
Last run: 2017-08-03_11:45:03
Errors: 1
Warnings: 2
Not Collected: 0
Report: /home/support/audit_report/NAS_Audit_VA_20170803114432.html

'''

nas_audit_fail = '''
        [INFO]     Running NAS Audit Script (Revision A) at 2017-08-03 15:08:41

        [ERROR]    Unable to determine Cluster name
        [ERROR]    Review log file /home/support/audit_report/audit_log_20170803150841 and temp directory /var/tmp/audit_tmp
        [ERROR]    Aborting script

'''

enm_dep_type_path = {'id': 'enm_deployment_type',
                    'item-type-name': 'config-manager-property',
                    'applied_properties_determinable': True,
                    'state': 'Applied',
                    '_links': {
                        'self': {
                            'href': 'http://localhost:9999/litp/rest/v1/'
                                    'software/items/config_manager/'
                                    'global_properties/enm_deployment_type'
                        },
                        'item-type': {
                            'href': 'http://localhost:9999/litp/rest/v1/'
                                    'item-types/config-manager-property'
                        }
                    },
                    'properties': {
                        'key': 'enm_deployment_type',
                        'value': 'Extra_Large_ENM'}
                    }

sp1_path = [
    {'path': '/infrastructure/storage/storage_providers/sp1',
     'data': {'item-type-name': 'sfs-service', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage'
                                          '_providers/sp1'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/sfs-service'
                                       }},
              'id': 'sp1',
              'properties': {'management_ipv4': '192.168.50.19',
                             'user_name': 'support', 'name': 'sfs1',
                             'password_key': 'key-for-sfs'}}}]

san1_path = [
    {'path': '/infrastructure/storage/storage_providers/san1',
     'data': {'item-type-name': 'san-emc', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage'
                                          '_providers/san1'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/san-emc'
                                       }},
              'id': 'san1',
              'properties': {'username': 'admin',
                             'name': 'ieatunity-34',
                             'ip_b': '127.0.0.1',
                             'san_type': 'unity',
                             'ip_a': '10.150.72.4',
                             'fc_switches': 'false',
                             'storage_network': 'storage',
                             'storage_site_id': 'ENM1073',
                             'password_key': 'key-for-san-ieatunity-34'}}}]

fs_path = [
    {'path': '/infrastructure/storage/storage_providers/sp1/pools/pl1/'
             'file_systems/fs1',
     'data': {'item-type-name': 'sfs-filesystem', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage_'
                                          'providers/sp1/pools/pl1/'
                                          'file_systems/fs1'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/'
                                               'sfs-filesystem'}},
              'id': 'fs1',
              'properties': {'path': '/vx/enm1-00pm', 'size': '10G'}}}]

pool_path = [
    {'path': '/infrastructure/storage/storage_providers/sp1/pools/enm-pool',
     'data': {'item-type-name': 'sfs-pool', 'state': 'Applied',
              '_links': {'self': {'href': 'https://localhost:9999/litp/rest/'
                                          'v1/infrastructure/storage/storage_'
                                          'providers/sp1/pools/enm-pool'},
                         'item-type': {'href': 'https://localhost:9999/litp/'
                                               'rest/v1/item-types/'
                                               'sfs-pool'}},
              'id': 'sp1',
              'properties': {'name': 'enm'}}}]

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

dmp_subpaths_2ctlr_all_ok = '''NAME         STATE[A]   PATH-TYPE[M] DMPNODENAME  ENCLR-NAME   CTLR   ATTRS
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
sdba         ENABLED    SECONDARY    emc_clariion0_11 emc_clariion0 c2        -
sdbm         ENABLED    SECONDARY    emc_clariion0_11 emc_clariion0 c2        -
sdac          ENABLED(A) PRIMARY      emc_clariion0_11 emc_clariion0 c2        -
sdao          ENABLED(A) PRIMARY      emc_clariion0_11 emc_clariion0 c2        -
sdbb         ENABLED(A) PRIMARY      emc_clariion0_12 emc_clariion0 c2        -
sddn         ENABLED(A) PRIMARY      emc_clariion0_12 emc_clariion0 c2        -
sdad          ENABLED    SECONDARY    emc_clariion0_12 emc_clariion0 c2        -
sdap          ENABLED    SECONDARY    emc_clariion0_12 emc_clariion0 c2        -
sdbj         ENABLED(A) SECONDARY    emc_clariion0_123 emc_clariion0 c2        -
sdcv         ENABLED(A) SECONDARY    emc_clariion0_123 emc_clariion0 c2        -
sdal          ENABLED    PRIMARY      emc_clariion0_123 emc_clariion0 c2        -
sdjx          ENABLED    PRIMARY      emc_clariion0_123 emc_clariion0 c2        -
'''

multipath_ll_htype1 = """mpathc (36006016007b038001502f409ed11e911) dm-0 DGC,VRAID
size=50G features='2 queue_if_no_path' hwhandler='1 emc' wp=rw
|-+- policy='round-robin 0' prio=50 status=active
| |- 0:0:2:1 sdh 8:112 active ready running
| |- 2:0:3:2 sdx 65:112 active ready running
| |- 2:0:0:2 sdo 8:224  active ready running
| `- 0:0:3:1 sdk 8:160 active ready running
`-+- policy='round-robin 0' prio=10 status=enabled
  |- 2:0:3:1 sdw 65:96  active ready running
  |- 0:0:0:1 sdb 8:16  active ready running
  |- 2:0:0:2 sdo 8:224  active ready running
  `- 0:0:1:1 sde 8:64  active ready running
"""

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

mp_conf_three_mpath = """mpatha
mpathb
mpathc"""

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


class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id

    def get_property(self, key):
        return self.properties[key]


class TestHealthCheck(unittest2.TestCase):
    @patch('enm_healthcheck.get_nas_type')
    def setUp(self, m_get_nas_type):
        m_get_nas_type.return_value = ''

        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        os.environ['ENMINST_BIN'] = join(basepath, 'src/main/bin')
        self.fcaps_healthcheck_modules = test_utils.mock_fcaps_healthcheck_module()
        self.fcaps_healthcheck_module_patcher = patch.dict('sys.modules', self.fcaps_healthcheck_modules)
        self.fcaps_healthcheck_module_patcher.start()
        import enm_healthcheck
        self.hc = enm_healthcheck
        self.c = enm_healthcheck.HealthCheck()

    @patch('enm_healthcheck.HealthCheck.grub_cfg_healthcheck')
    @patch('enm_healthcheck.HealthCheck.network_bond_healthcheck')
    @patch('enm_healthcheck.HealthCheck.lvm_conf_filter_healthcheck')
    @patch('enm_healthcheck.HealthCheck.san_alert_healthcheck')
    @patch('enm_healthcheck.HealthCheck.consul_healthcheck')
    @patch('h_hc.hc_mdt.MdtHealthCheck.mdt_nfs_volume_healthcheck')
    @patch('enm_healthcheck.HealthCheck.storagepool_healthcheck')
    @patch('enm_healthcheck.HealthCheck.nas_healthcheck')
    @patch('h_litp.litp_rest_client.LitpRestClient.export_model_to_xml')
    @patch('enm_healthcheck.HealthCheck.hw_resources_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_cluster_healthcheck')
    @patch('enm_healthcheck.HealthCheck.system_service_healthcheck')
    @patch('enm_healthcheck.HealthCheck.stale_mount_healthcheck')
    @patch('enm_healthcheck.HealthCheck.node_fs_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_llt_heartbeat_healthcheck')
    @patch('enm_healthcheck.HealthCheck.postgres_pre_uplift_check')
    @patch('enm_healthcheck.HealthCheck.postgres_expiry_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_availability_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_raft_index_lag_check')
    @patch('enm_healthcheck.HealthCheck.multipath_active_healthcheck')
    def test_full_enm_healthcheck(self,
                                  dmp,
                                  neo4j_lag,
                                  neo4j,
                                  pgs,
                                  pgs_uplift,
                                  llt,
                                  node_fs,
                                  stale_mount,
                                  service,
                                  cluster,
                                  sg,
                                  hw,
                                  export,
                                  nas,
                                  san,
                                  mdt,
                                  consul,
                                  san_alert,
                                  lvm_conf,
                                  grub_cfg,
                                  net_bond):
        model = join(gettempdir(), 'exported.xml')
        with open(model, 'w') as ofile:
            ofile.write(test_hw.MODEL)
        model_xml = load_xml(model)
        export.return_value = model_xml
        self.c.enminst_healthcheck(None)

        for mk in [neo4j, dmp, pgs, llt, stale_mount, node_fs, service,
                   cluster, sg, hw, nas, san, mdt, consul, san_alert,
                   lvm_conf, pgs_uplift, grub_cfg, net_bond]:
            self.assertTrue(mk.called, 'Mock {0} not called!'.format(mk))

    @patch('enm_healthcheck.HealthCheck.grub_cfg_healthcheck')
    @patch('enm_healthcheck.HealthCheck.network_bond_healthcheck')
    @patch('enm_healthcheck.HealthCheck.lvm_conf_filter_healthcheck')
    @patch('enm_healthcheck.HealthCheck.san_alert_healthcheck')
    @patch('enm_healthcheck.HealthCheck.storagepool_healthcheck')
    @patch('enm_healthcheck.HealthCheck.consul_healthcheck')
    @patch('enm_healthcheck.HealthCheck.mdt_healthcheck')
    @patch('enm_healthcheck.HealthCheck.nas_healthcheck')
    @patch('enm_healthcheck.HealthCheck.hw_resources_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_cluster_healthcheck')
    @patch('enm_healthcheck.HealthCheck.system_service_healthcheck')
    @patch('enm_healthcheck.HealthCheck.node_fs_healthcheck')
    @patch('enm_healthcheck.HealthCheck.stale_mount_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_llt_heartbeat_healthcheck')
    @patch('enm_healthcheck.HealthCheck.postgres_expiry_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_availability_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_raft_index_lag_check')
    @patch('enm_healthcheck.HealthCheck.multipath_active_healthcheck')
    # pylint: disable=R0915
    def test_full_enm_healthcheck_errors(self,
                                         m_multipath_active_healthcheck,
                                         m_neo4j_raft_index_lag,
                                         m_neo4j_availability_healthcheck,
                                         m_postgres_expiry_healthcheck,
                                         m_node_vcs_llt_heartbeat_healthcheck,
                                         m_stale_mount_healthcheck,
                                         m_node_fs_healthcheck,
                                         m_system_service_healthcheck,
                                         m_vcs_cluster_healthcheck,
                                         m_vcs_service_group_healthcheck,
                                         m_hw_resources_healthcheck,
                                         m_nas_healthcheck,
                                         m_mdt_healthcheck,
                                         m_consul_healthcheck,
                                         m_storagepool_healthcheck,
                                         m_san_alert_healthcheck,
                                         m_lvm_conf_healthcheck,
                                         m_grub_cfg_healthcheck,
                                         m_network_bond_healthcheck):

        m_neo4j_availability_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_neo4j_availability_healthcheck.reset_mock()

        m_multipath_active_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_multipath_active_healthcheck.reset_mock()

        m_multipath_active_healthcheck.side_effect = McoAgentException
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_stale_mount_healthcheck.reset_mock()

        m_postgres_expiry_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_postgres_expiry_healthcheck.reset_mock()

        m_node_vcs_llt_heartbeat_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_node_vcs_llt_heartbeat_healthcheck.reset_mock()

        m_stale_mount_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_stale_mount_healthcheck.reset_mock()

        m_stale_mount_healthcheck.side_effect = OSError
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_stale_mount_healthcheck.reset_mock()

        m_stale_mount_healthcheck.side_effect = McoAgentException
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_stale_mount_healthcheck.reset_mock()

        m_node_fs_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_node_fs_healthcheck.reset_mock()

        m_node_fs_healthcheck.side_effect = OSError
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_node_fs_healthcheck.reset_mock()

        m_node_fs_healthcheck.side_effect = NasConsoleException
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_node_fs_healthcheck.reset_mock()

        m_node_fs_healthcheck.side_effect = McoAgentException
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_node_fs_healthcheck.reset_mock()

        m_system_service_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_system_service_healthcheck.side_effect = IOError
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_system_service_healthcheck.reset_mock()

        m_vcs_cluster_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_vcs_cluster_healthcheck.reset_mock()

        m_vcs_service_group_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_vcs_service_group_healthcheck.reset_mock()

        m_hw_resources_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_hw_resources_healthcheck.reset_mock()

        m_mdt_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_mdt_healthcheck.reset_mock()

        m_mdt_healthcheck.side_effect = OSError
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_mdt_healthcheck.reset_mock()

        m_consul_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_consul_healthcheck.reset_mock()

        m_nas_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_nas_healthcheck.reset_mock()

        m_storagepool_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_storagepool_healthcheck.reset_mock()

        m_san_alert_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_san_alert_healthcheck.reset_mock()

        m_lvm_conf_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_lvm_conf_healthcheck.reset_mock()

        m_grub_cfg_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_grub_cfg_healthcheck.reset_mock()

        m_network_bond_healthcheck.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.enminst_healthcheck)
        m_network_bond_healthcheck.reset_mock()

    @patch('enm_healthcheck.get_nas_type')
    @patch('enm_healthcheck.init_enminst_logging')
    def test_main_no_args(self, _, m_get_nas_type):
        m_get_nas_type.return_value = ''
        self.assertRaises(SystemExit, self.hc.main, [])

    @patch('enm_healthcheck.init_enminst_logging')
    def test_main_one_args_action(self, _):
        self.assertRaises(SystemExit, self.hc.main, ['--action'])

    @patch('enm_healthcheck.init_enminst_logging')
    def test_main_one_args_exclude(self, _):
        self.assertRaises(SystemExit, self.hc.main, ['--exclude'])

    @patch('h_vcs.vcs_cli.Vcs.verify_cluster_system_status')
    def test_vcs_cluster_healthcheck(self, cluster_status):
        cluster_status.return_value = systems
        self.c.vcs_cluster_healthcheck(verbose=True)
        self.assertTrue(cluster_status.called)

    @patch('h_vcs.vcs_cli.Vcs.verify_cluster_system_status')
    def test_vcs_cluster_healthcheck_IOError(self, cluster_status):
        cluster_status.side_effect = SystemExit
        self.assertRaises(SystemExit,
                          self.c.vcs_cluster_healthcheck, verbose=True)

    @patch('enm_healthcheck.get_nas_type')
    @patch('enm_healthcheck.argparse')
    @patch('enm_healthcheck.HealthCheck.check_active_nodes')
    def test_main_with_two_args(self, nodes, parser, m_get_nas_type):
        testargs = argparse.Namespace(action=['vcs_service_group_healthcheck'],
                                      verbose=False)
        parser.return_value = MagicMock()
        parser.return_value.parse_args.side_effect = [testargs]
        m_get_nas_type.return_value = ''
        self.hc.main(['--action', 'blah', '--verbose'])
        self.assertTrue(nodes.called)

    @patch('logging.Logger.info')
    @patch('enm_healthcheck.Services.verify_node_status')
    def test_check_active_nodes(self, m_verify_node_status, m_info):
        m_verify_node_status.return_value = True
        self.c.check_active_nodes(verbose=True)
        m_info.assert_called_with('Node Status: PASSED')

        m_verify_node_status.return_value = False
        self.c.check_active_nodes(verbose=True)
        m_info.assert_called_with('Node Status: FAILED')

        m_verify_node_status.side_effect = IOError
        self.assertRaises(SystemExit, self.c.check_active_nodes)

    @patch('h_hc.hc_services.Services.verify_node_status')
    def test_check_active_nodes_IOError(self, node):
        node.side_effect = IOError
        self.assertRaises(SystemExit,
                          self.c.check_active_nodes, verbose=True)

    @patch('logging.Logger.info')
    @patch('h_hc.hc_services.Services.verify_service_status')
    def test_system_service_healthcheck(self, m_verify_node_status, m_info):
        self.c.system_service_healthcheck(verbose=True)
        m_info.assert_any_call('Service Status: PASSED')

        m_verify_node_status.side_effect = IOError
        self.assertRaises(SystemExit, self.c.system_service_healthcheck)

    @patch('h_vcs.vcs_cli.Vcs.verify_cluster_group_status')
    def test_vcs_service_group_healthcheck(self, group_status):
        group_status.return_value = systems
        self.c.vcs_service_group_healthcheck(verbose=True)
        self.assertTrue(group_status.called)

    @patch('h_vcs.vcs_cli.Vcs.verify_cluster_group_status')
    def test_vcs_service_group_healthcheck_IOError(self, group_status):
        group_status.side_effect = SystemExit
        self.assertRaises(SystemExit,
                          self.c.vcs_service_group_healthcheck, verbose=True)

    @patch('logging.Logger.info')
    def test_san_alert_healthcheck_excluded(self, log_info):
        hc_instance = self.c
        hc_instance.excluded = ['san_alert_healthcheck']
        self.c.san_alert_healthcheck(verbose=True)
        log_info.assert_called_with('Skipping SAN alert Healthcheck '
                                    'as excluded.')

    @patch('enm_healthcheck.SanHealthChecks')
    @patch('logging.Logger.debug')
    @patch('logging.Logger.info')
    def test_san_alert_healthcheck_not_unityxt(self, log_info, log_debug, san_hcs):
        hc_instance = self.c
        hc_instance.excluded = []
        san_hcs.return_value.san_critical_alert_healthcheck.return_value = None
        hc_instance.nas_type = 'vnx'
        self.c.san_alert_healthcheck(verbose=True)
        log_info.assert_any_call('Checking SAN Storage for alerts:')
        log_debug.assert_any_call('Skipping NAS server imbalance check. '
                                  'Only applicable to ENM on Rackmount Servers.')
        log_info.assert_called_with('Successfully Completed SAN alert Healthcheck')

    @patch('enm_healthcheck.SanHealthChecks')
    @patch('logging.Logger.error')
    @patch('logging.Logger.debug')
    @patch('logging.Logger.info')
    def test_san_alert_healthcheck_not_unityxt_alerts_found(self, log_info, log_debug, log_error, san_hcs):
        hc_instance = self.c
        hc_instance.excluded = []
        san_hcs.return_value.san_critical_alert_healthcheck.side_effect = SystemExit
        hc_instance.nas_type = 'vnx'
        self.assertRaises(SystemExit, self.c.san_alert_healthcheck, True)
        log_info.assert_any_call('Checking SAN Storage for alerts:')
        log_debug.assert_any_call('Skipping NAS server imbalance check. '
                                  'Only applicable to ENM on Rackmount Servers.')
        log_error.assert_any_call('Healthcheck status: FAILED.')
        log_error.assert_called_with('There are critical alerts on the SAN Storage.')

    @patch('enm_healthcheck.SanHealthChecks')
    @patch('enm_healthcheck.SanCleanup')
    @patch('enm_healthcheck.SanFaultCheck')
    @patch('logging.Logger.info')
    def test_san_alert_healthcheck_unityxt_pass(self, log_info, san_fault, san_cleanup, san_hcs):
        hc_instance = self.c
        hc_instance.excluded = []
        san_hcs.return_value.san_critical_alert_healthcheck.return_value = None
        hc_instance.nas_type = 'unityxt'
        san_cleanup.return_value.get_san_info.return_value = {'san' : ['spa_ip', 'spb_ip', 'san_site_id',
                                                                       'login_scope', 'san_type', 'username',
                                                                       'password']}
        san_fault.return_value.check_nas_servers.return_value = None
        san_fault.return_value.nas_server_fault = False
        self.c.san_alert_healthcheck(verbose=True)
        log_info.assert_any_call('Checking SAN Storage for alerts:')
        log_info.assert_called_with('Successfully Completed SAN alert Healthcheck')

    @patch('enm_healthcheck.SanHealthChecks')
    @patch('enm_healthcheck.SanCleanup')
    @patch('enm_healthcheck.SanFaultCheck')
    @patch('logging.Logger.info')
    def test_san_alert_healthcheck_unityxt_raises_exception(self, log_info, san_fault, san_cleanup, san_hcs):
        hc_instance = self.c
        hc_instance.excluded = []
        san_hcs.return_value.san_critical_alert_healthcheck.return_value = None
        hc_instance.nas_type = 'unityxt'
        san_cleanup.return_value.get_san_info.return_value = {'san' : ['spa_ip', 'spb_ip', 'san_site_id',
                                                                       'login_scope', 'san_type', 'username',
                                                                       'password']}
        san_fault.return_value.check_nas_servers.side_effect = Exception
        self.assertRaises(Exception, self.c.san_alert_healthcheck, True)
        log_info.assert_any_call('Checking SAN Storage for alerts:')

    @patch('enm_healthcheck.SanHealthChecks')
    @patch('enm_healthcheck.SanCleanup')
    @patch('enm_healthcheck.SanFaultCheck')
    @patch('logging.Logger.error')
    @patch('logging.Logger.info')
    def test_san_alert_healthcheck_unityxt_fail(self, log_info, log_error, san_fault, san_cleanup, san_hcs):
        hc_instance = self.c
        hc_instance.excluded = []
        san_hcs.return_value.san_critical_alert_healthcheck.return_value = None
        hc_instance.nas_type = 'unityxt'
        san_cleanup.return_value.get_san_info.return_value = {'san' : ['spa_ip', 'spb_ip', 'san_site_id',
                                                                       'login_scope', 'san_type', 'username',
                                                                       'password']}
        san_fault.return_value.check_nas_servers.side_effect = None
        san_fault.return_value.nas_server_fault = True
        try:
            self.c.san_alert_healthcheck(verbose=True)
        except SystemExit as err:
            self.assertEqual(1, err.code)
        log_info.assert_any_call('Checking SAN Storage for alerts:')
        log_error.assert_any_call('Healthcheck status: FAILED.')
        log_error.assert_called_with('NAS server imbalance detected.')

    @patch('enm_healthcheck.set_logging_level')
    def test_configure_logging_hc_verbose(self, logging):
        self.hc.configure_logging(verbose=True, logger_name='enmhealthcheck')
        logger = enminst_logger.init_enminst_logging('enmhealthcheck')
        logging.assert_called_with(logger, 'DEBUG')

    @patch('enm_healthcheck.set_logging_level')
    def test_configure_logging_hc_non_verbose(self, logging):
        os.environ['LOG_LEVEL'] = 'INFO'
        self.hc.configure_logging(logger_name='enmhealthcheck')
        logger = enminst_logger.init_enminst_logging('enmhealthcheck')
        logging.assert_called_with(logger, os.environ['LOG_LEVEL'])

    @patch('h_litp.litp_utils.get_xml_deployment_file')
    @patch('h_litp.litp_utils.get_dd_xml_file')
    @patch('h_litp.litp_utils.is_custom_service')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    @patch('hw_resources.HwResources.litp')
    @patch('hw_resources.HwResources.show_blade_vm_usage')
    def test_hw_resources_healthcheck(self, sbu, m_litp, m_enm_version,
                                      m_is_custom, m_dd, m_xml):
        hw = HwResources()
        model = join(gettempdir(), 'exported.xml')
        with open(model, 'w') as ofile:
            ofile.write(test_hw.MODEL)
        model_xml = load_xml(model)

        mocked_litp = LitpRestClient()
        getc_deploy = {'_embedded': {'item': [{'id': 'enm'}]}}
        getc_clstr = {'_embedded': {'item': [{'id': 'svc_cluster'}]}}
        getc_nodes = {'_embedded': {'item': [
            {'id': 'svc-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'hostname-svc-1'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}},
            {'id': 'svc-2',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'hostname-svc-2'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}}
        ]}}
        get_lms = {'id': 'ms',
                   'state': 'Applied',
                   'item-type-name': 'node',
                   'properties': {'hostname': 'hostname-ms-1'},
                   '_links': {'self': {'href': '/litp/rest/v1/'}}}

        setup_litp_mock(mocked_litp, [
            ['GET', dumps({}), httplib.OK],
            ['GET', test_hw.MODEL, httplib.OK],
            ['GET', dumps(getc_deploy), httplib.OK],
            ['GET', dumps(getc_clstr), httplib.OK],
            ['GET', dumps(getc_nodes), httplib.OK],
            ['GET', dumps(get_lms), httplib.OK],
        ])
        m_litp.return_value = mocked_litp

        try:
            hostidmappings = hw.get_modeled_hosts(model_xml)
            self.c.hw_resources_healthcheck()
            vm_resource_usage = {
                'svc_cluster': {'svc-1': {'ram': 4096, 'cpus': 4},
                                'svc-2': {'ram': 4096, 'cpus': 4}}}
            node_model_states = {
                'hostname-ms-1': LitpRestClient.ITEM_STATE_APPLIED,
                'hostname-svc-1': LitpRestClient.ITEM_STATE_APPLIED,
                'hostname-svc-2': LitpRestClient.ITEM_STATE_APPLIED}

            sbu.assert_called_with(vm_resource_usage, hostidmappings,
                                   node_model_states, verbose=False)
        finally:
            os.remove(model)

    @patch('enm_healthcheck.set_logging_level')
    def test_configure_logging_hc_error(self, logging):
        logging.side_effect = KeyError
        self.hc.configure_logging(logger_name='enmhealthcheck')

    @patch('enm_healthcheck.set_logging_level')
    def test_configure_logging_enminst_verbose(self, logging):
        self.hc.configure_logging(verbose=True, logger_name='enminst')
        logger = enminst_logger.init_enminst_logging('enminst')
        logging.assert_called_with(logger, 'DEBUG')

    @patch('enm_healthcheck.set_logging_level')
    def test_configure_logging_enminst_non_verbose(self, logging):
        os.environ['LOG_LEVEL'] = 'INFO'
        self.hc.configure_logging(logger_name='enminst')
        logger = enminst_logger.init_enminst_logging('enminst')
        logging.assert_called_with(logger, os.environ['LOG_LEVEL'])

    @patch('enm_healthcheck.set_logging_level')
    def test_configure_logging_enminst_error(self, logging):
        logging.side_effect = KeyError
        self.hc.configure_logging(logger_name='enminst')

    @patch('enm_healthcheck.HealthCheck.check_active_nodes')
    def test_pre_checks(self, nodes):
        self.c.pre_checks(verbose=False)
        self.assertTrue(nodes.called)

    @patch('h_puppet.mco_agents.EnminstAgent.mco_exec')
    @patch('h_util.h_nas_console.NasConsole.exec_nas_command')
    @patch('h_util.h_utils.Decryptor.get_password')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_children')
    @patch('paramiko.SSHClient')
    def test_node_fs_healthcheck(self,
                                 ssh,
                                 rest_mock,
                                 nas_pw,
                                 exec_nas_cmd,
                                 mco_exec):
        hc = self.c

        df_ok_nas_ret = df_ok_nas.split('\n')
        df_nok_nas_ret = df_nok_nas.split('\n')

        nas_pw.return_value = 'nas_pw'

        self.patch_ssh(ssh, 0, '', None)

        # All fs (nas, peer nodes) under thresholds
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_ok, 'node2': df_ok}]
        self.assertEquals(hc.node_fs_healthcheck(verbose=True), None)

        # exceeded fs nas
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_nok_nas_ret]
        mco_exec.side_effect = [{'node1': df_ok, 'node2': df_ok}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # exceeded fs one node
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_ok, 'node2': df_nok}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # exceeded fs on multiple nodes
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_nok, 'node2': df_nok}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # exceeded versant fs node
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_ok, 'node2': df_nok_versant}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # exceeded elastic fs node
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_ok, 'node2': df_nok_elastic}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # exceeded elastic and versant fs on each of the peer nodes
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_nok_elastic,
                                 'node2': df_nok_versant}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # exceeded all fs, nas and nodes
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_nok_nas_ret]
        mco_exec.side_effect = [{'node1': df_nok, 'node2': df_nok}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # The df command didn't return useable value
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'node1': df_faulty}]
        self.assertRaises(OSError, hc.node_fs_healthcheck, True)

        # mounted iso9660 fs (100% usage) ignored
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        exec_nas_cmd.side_effect = [df_ok_nas_ret]
        mco_exec.side_effect = [{'ms': df_mounted_iso}]
        self.assertEquals(hc.node_fs_healthcheck(verbose=True), None)

    @patch('enm_healthcheck.HealthCheck._get_node_fs_usage')
    @patch('enm_healthcheck.HealthCheck._get_nas_fs_usage')
    @patch('enm_healthcheck.get_nas_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_children')
    @patch('paramiko.SSHClient')
    @patch('h_util.h_nas_console.NasConsole.exec_nas_command')
    @patch('h_puppet.mco_agents.EnminstAgent.mco_exec')
    @patch('h_util.h_utils.Decryptor.get_password')
    def test_unity_fs_usage(self,
                            nas_pw,
                            mco_exec,
                            nas_exec,
                            ssh,
                            rest_mock,
                            nas_type,
                            nas_usage,
                            node_usage):

        self.patch_ssh(ssh, 0, '', None)
        hc = self.c
        hc.nas_type = 'unityxt'
        rest_mock.return_value = [sp1_path, pool_path, fs_path]
        node_usage.return_value = {}

        # fs on unity nas exceeds
        nas_usage.return_value = [{'Use%': '94%', 'FileSystem': 'ENM_test1'}]
        self.assertRaises(SystemExit, hc.node_fs_healthcheck, True)

        # fs on unity under threshold
        nas_usage.return_value = [{'Use%': '9%', 'FileSystem': 'ENM_test1'}]
        self.assertEquals(hc.node_fs_healthcheck(verbose=True), None)

        # no fs on unity
        nas_usage.return_value = [{'Use%': '', 'FileSystem': ''}]
        self.assertEquals(hc.node_fs_healthcheck(verbose=True), None)

    @patch('h_puppet.mco_agents.EnminstAgent.mco_exec')
    def test_stale_mount_healthcheck(self,
                                     mco_exec):
        hc = self.c

        stale_mounts = '/root/nfsc1\n/root/nfsc2'

        # All nodes under thresholds
        mco_exec.side_effect = [{'ms': '', 'node1': '', 'node2': ''}]
        self.assertEquals(hc.stale_mount_healthcheck(verbose=True), None)

        # stale mounts on one node
        mco_exec.side_effect = [{'node1': '', 'node2': stale_mounts}]
        self.assertRaises(SystemExit, hc.stale_mount_healthcheck, True)

        # stale mounts on multiple nodes
        mco_exec.side_effect = [{'node1': stale_mounts, 'node2': stale_mounts}]
        self.assertRaises(SystemExit, hc.stale_mount_healthcheck, True)

    @patch('enm_healthcheck.HealthCheck.report_lvm_conf_filter_settings')
    @patch('enm_healthcheck.is_env_on_rack')
    def test_incorrect_entry_lvm_conf_filter_healthcheck(self, m_is_rack, m_check_filters):
        m_is_rack.return_value = True
        m_check_filters.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.lvm_conf_filter_healthcheck, True)

    @patch('logging.Logger.info')
    @patch('enm_healthcheck.is_env_on_rack')
    def test_lvm_conf_filter_healthcheck_env_not_rack(self, m_is_rack, m_info):
        m_is_rack.return_value = False
        self.assertEquals(self.c.lvm_conf_filter_healthcheck(), None)
        m_info.assert_called_with('Skipping check. '
                                  'Only applicable to ENM on Rackmount Servers')

    @patch('enm_healthcheck.HealthCheck.report_lvm_conf_filter_settings')
    @patch('enm_healthcheck.is_env_on_rack')
    @patch('logging.Logger.info')
    def test_lvm_conf_filter_ok_value(self, m_info, m_is_rack, m_check_filters):
        m_is_rack.return_value = True
        node = 'node1'
        ok_value = '[ "a|/dev/mapper/mpath.*|", "r|.*|" ]'
        m_check_filters.return_value = {
                    'Node': node,
                    'filter Value': ok_value,
                    'filter State': 'OK'
                    }
        self.c.lvm_conf_filter_healthcheck()
        m_info.assert_any_call('lvm.conf filter healthcheck status: PASSED.')
        m_info.assert_called_with("Successfully Completed lvm.conf Healthcheck")

    @patch('enm_healthcheck.HealthCheck.report_lvm_conf_filter_settings')
    @patch('enm_healthcheck.is_env_on_rack')
    @patch('logging.Logger.info')
    def test_lvm_conf_vxvm_filter_ok_value(self, m_info, m_is_rack, m_check_filters):
        m_is_rack.return_value = True
        node = 'node1'
        ok_value = '[ "r|/dev/vx/dmp/|", "r|/dev/Vx.*|", "a|/dev/mapper/mpath.*|", "r|.*|" ]'
        m_check_filters.return_value = {
                    'Node': node,
                    'filter Value': ok_value,
                    'filter State': 'OK'
                    }
        self.c.lvm_conf_filter_healthcheck()
        m_info.assert_any_call('lvm.conf filter healthcheck status: PASSED.')
        m_info.assert_called_with("Successfully Completed lvm.conf Healthcheck")

    @patch('h_litp.litp_utils.LitpObject')
    @patch('enm_healthcheck.EnminstAgent')
    @patch('enm_healthcheck.HealthCheck.get_nodes_in_clusters')
    def test_report_lvm_conf_filter_settings_empty(self,
                                        m_get_nodes_in_clusters,
                                        m_agent,
                                        m_litp_obj):
        m_agent.get_lvm_conf_filter.side_effect = '[""]'
        m_agent.get_lvm_conf_global_filter.side_effect = '[""]'
        self.c.get_global_property = MagicMock(return_value='')
        m_litp_obj._properties = {'hostname': 'node1'}
        m_get_nodes_in_clusters.return_value = [m_litp_obj]
        self.assertRaises(SystemExit, self.c.report_lvm_conf_filter_settings, True)

    @patch('h_litp.litp_utils.LitpObject')
    @patch('enm_healthcheck.EnminstAgent')
    @patch('enm_healthcheck.HealthCheck.get_nodes_in_clusters')
    def test_report_lvm_conf_filter_settings_error(self,
                                        m_get_nodes_in_clusters,
                                        m_agent,
                                        m_litp_obj):
        m_agent.get_lvm_conf_filter.side_effect = '[ "a|/de" ]'
        m_agent.get_lvm_conf_global_filter.side_effect = '[ "a|/de" ]'
        self.c.get_global_property = MagicMock(return_value='')
        m_litp_obj._properties = {'hostname': 'node1'}
        m_get_nodes_in_clusters.return_value = [m_litp_obj]
        self.assertRaises(SystemExit, self.c.report_lvm_conf_filter_settings, True)

    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    def test_get_nodes_in_clusters(self, m_litp_rest):
        svc1_object = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                     'Applied',
                                     {'hostname': 'svc1'}, 'svc-1')
        db1_object = MockLitpObject('/deployments/enm/clusters/db_cluster/',
                                    'Applied',
                                    {'hostname': 'db1'}, 'db-1')
        evt1_object = MockLitpObject('/deployments/enm/clusters/evt_cluster/',
                                    'Applied',
                                    {'hostname': 'evt1'}, 'evt-1')

        mock_cluster_nodes = {'svc_cluster': {'svc-1': svc1_object},
                              'db_cluster': {'db-1': db1_object},
                              'evt_cluster': {'evt-1': evt1_object}}

        m_litp_rest.return_value = mock_cluster_nodes

        self.assertEquals(
            self.c.get_nodes_in_clusters('db_cluster', 'svc_cluster'),
            [svc1_object, db1_object]
        )

        self.assertEquals(
            self.c.get_nodes_in_clusters(),
            [evt1_object, svc1_object, db1_object]
        )

    def test_create_lvm_conf_entry_report_filter_entry(self):
        node = 'node1'
        entry = 'filter'
        ok_value = '[ "a|/dev/mapper/mpath.*|", "r|.*|" ]'
        vxvm_value = '[ "r|/dev/vx/dmp/|", "r|/dev/Vx.*|", "a|/dev/mapper/mpath.*|", "r|.*|" ]'
        error_value = '[ "a|/dev/mapper/mpath]'
        missing_value = 'DOES NOT EXIST'
        ok_report = {
            'Node': node,
            'filter Value': ok_value,
            'filter State': 'OK'
        }
        vxvm_report = {
            'Node': node,
            'filter Value': vxvm_value,
            'filter State': 'OK'
        }
        error_report = {
            'Node': node,
            'filter Value': error_value,
            'filter State': 'ERROR'
        }
        missing_report = {
            'Node': node,
            'filter Value': missing_value,
            'filter State': 'ERROR'
        }

        self.assertEquals(self.c.create_lvm_conf_entry_report(
            node, entry, missing_value
        ), missing_report)

        self.assertEquals(self.c.create_lvm_conf_entry_report(
            node, entry, ok_value
        ), ok_report)

        self.assertEquals(self.c.create_lvm_conf_entry_report(
            node, entry, vxvm_value
        ), vxvm_report)

        self.assertEquals(self.c.create_lvm_conf_entry_report(
            node, entry, error_value
        ), error_report)

        # ----

        openstack_value = '[ "a|/dev/sd.*|",  "a|/dev/mapper/mpath.*|", "r|.*|" ]'
        openstack_ok_report = {
            'Node': node,
            'filter Value': openstack_value,
            'filter State': 'OK'
        }
        self.assertEquals(self.c.create_lvm_conf_entry_report(
            node, entry, error_value, True
        ), error_report)

        self.assertEquals(self.c.create_lvm_conf_entry_report(
            node, entry, openstack_value, True
        ), openstack_ok_report)

    @patch('enm_healthcheck.is_env_on_rack')
    @patch('logging.Logger.info')
    def test_network_bond_healthcheck_not_rack(self, m_info, m_is_rack):
        m_is_rack.return_value = False
        self.assertEquals(self.c.network_bond_healthcheck(), None)
        m_info.assert_called_with('Skipping check. '
                                  'Only applicable to ENM on Rackmount Servers')

    @patch('enm_healthcheck.is_env_on_rack')
    @patch('logging.Logger.info')
    @patch('enm_healthcheck.HealthCheck.get_nodes_in_clusters')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('enm_healthcheck.HealthCheck.run_network_bond_healthcheck')
    def test_network_bond_healthcheck_ok(self,
                                         m_net_bond_hc,
                                         m_get_lms,
                                         m_get_nodes,
                                         m_info,
                                         m_is_rack):
        m_is_rack.return_value = True
        svc1_obj = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                  'Applied',
                                  {'hostname': 'svc1'}, 'svc-1')
        ms_obj = MockLitpObject('/ms',
                                'Applied',
                                {'hostname': 'ms'}, 'ms')

        m_get_nodes.return_value = [svc1_obj]
        m_get_lms.return_value = ms_obj

        self.c.network_bond_healthcheck()
        m_net_bond_hc.assert_called_once_with([svc1_obj, ms_obj], False)
        m_info.assert_any_call('Beginning of network bond check')
        m_info.assert_called_with('Successfully completed network bond check')

    @patch('enm_healthcheck.is_env_on_rack')
    @patch('logging.Logger.info')
    @patch('logging.Logger.error')
    @patch('enm_healthcheck.HealthCheck.get_nodes_in_clusters')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_lms')
    @patch('enm_healthcheck.HealthCheck.run_network_bond_healthcheck')
    def test_network_bond_healthcheck_fail(self,
                                           m_net_bond_hc,
                                           m_get_lms,
                                           m_get_nodes,
                                           m_error,
                                           m_info,
                                           m_is_rack):
        m_is_rack.return_value = True
        svc1_obj = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                  'Applied',
                                  {'hostname': 'svc1'}, 'svc-1')
        ms_obj = MockLitpObject('/ms',
                                'Applied',
                                {'hostname': 'ms'}, 'ms')

        m_get_nodes.return_value = [svc1_obj]
        m_get_lms.return_value = ms_obj
        m_net_bond_hc.side_effect = SystemExit

        self.assertRaises(SystemExit, self.c.network_bond_healthcheck)
        m_info.assert_any_call('Beginning of network bond check')
        m_error.assert_any_call('The network bond is not in a healthy state. '
                                'MII status of every member on all nodes '
                                'should be up.')
        m_error.assert_called_with('Network bond check: FAILED.')

    @patch('enm_healthcheck.EnminstAgent')
    @patch('enm_healthcheck.HealthCheck')
    @patch('enm_healthcheck.report_tab_data')
    def test_run_network_bond_healthcheck_all_ok(self,
                                                 m_report,
                                                 m_healthcheck,
                                                 m_agent):

        self.c.get_global_property = MagicMock(return_value='')

        svc1_obj = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                  'Applied',
                                  {'hostname': 'svc1'}, 'svc-1')

        m_agent.return_value.get_active_and_prime_bond_mbr.return_value = \
            OrderedDict(
                [('Active Member', 'eth0'), ('Primary Member', 'eth0')]
            )

        m_agent.return_value.get_bond_interface_info.return_value = [
            OrderedDict(
                [('Member Interface', 'eth0'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps')]
            ),
            OrderedDict(
                [('Member Interface', 'eth2'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps')]
            ),
        ]

        m_healthcheck.return_value.check_active_bond_member.return_value = 'OK'
        m_healthcheck.return_value.check_bond_interface_speed.return_value = 'OK'

        final_report = [OrderedDict([
            ('Node', 'svc1'),
            ('Active Member', 'eth0'),
            ('Primary Member', 'eth0'),
            ('Active Member State', 'OK'),
            ('eth0 MII Status', 'up'),
            ('eth0 Speed', '25000 Mbps'),
            ('eth0 Speed State', 'OK'),
            ('eth2 MII Status', 'up'),
            ('eth2 Speed', '25000 Mbps'),
            ('eth2 Speed State', 'OK')
        ])]

        self.c.run_network_bond_healthcheck([svc1_obj], True)
        m_report.assert_called_with(None, final_report[0].keys(), final_report)

        # ----
        m_report.reset_mock()

        self.c.get_global_property = MagicMock(return_value='vLITP_ENM_On_Rack_Servers')
        m_agent.return_value.get_bond_interface_info.return_value = [
            OrderedDict([('Member Interface', 'eth0'),
                         ('MII Status', 'up')]),
            OrderedDict([('Member Interface', 'eth2'),
                         ('MII Status', 'up')])]
        final_report = [OrderedDict([
                            ('Node', 'svc1'),
                            ('Active Member', 'eth0'),
                            ('Primary Member', 'eth0'),
                            ('Active Member State', 'OK'),
                            ('eth0 MII Status', 'up'),
                            ('eth2 MII Status', 'up')])]

        self.c.run_network_bond_healthcheck([svc1_obj], True)
        m_report.assert_called_with(None, final_report[0].keys(), final_report)


    @patch('enm_healthcheck.EnminstAgent')
    @patch('enm_healthcheck.HealthCheck')
    @patch('enm_healthcheck.report_tab_data')
    @patch('logging.Logger.warning')
    def test_run_network_bond_healthcheck_active_member_warning(self,
                                                                m_warning,
                                                                m_report,
                                                                m_healthcheck,
                                                                m_agent):

        self.c.get_global_property = MagicMock(return_value='')

        svc1_obj = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                  'Applied',
                                  {'hostname': 'svc1'}, 'svc-1')

        m_agent.return_value.get_active_and_prime_bond_mbr.return_value = OrderedDict(
            [
                ('Active Member', 'eth2'),
                ('Primary Member', 'eth0')
            ]
        )

        m_agent.return_value.get_bond_interface_info.return_value = [
            OrderedDict(
                [('Member Interface', 'eth0'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps')]
            ),
            OrderedDict(
                [('Member Interface', 'eth2'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps')]
            ),
        ]

        m_healthcheck.return_value.check_active_bond_member.return_value = 'WARNING'
        m_healthcheck.return_value.check_bond_interface_speed.return_value = 'OK'

        final_report = [OrderedDict([
            ('Node', 'svc1'),
            ('Active Member', 'eth2'),
            ('Primary Member', 'eth0'),
            ('Active Member State', 'WARNING'),
            ('eth0 MII Status', 'up'),
            ('eth0 Speed', '25000 Mbps'),
            ('eth0 Speed State', 'OK'),
            ('eth2 MII Status', 'up'),
            ('eth2 Speed', '25000 Mbps'),
            ('eth2 Speed State', 'OK')
        ])]

        self.c.run_network_bond_healthcheck([svc1_obj], True)
        m_report.assert_called_with(None, final_report[0].keys(), final_report)
        m_warning.assert_called_with('WARNING: The active member is not equal to the '
                                      'primary member on one or more nodes.')

    @patch('enm_healthcheck.EnminstAgent')
    @patch('enm_healthcheck.HealthCheck')
    @patch('enm_healthcheck.report_tab_data')
    @patch('logging.Logger.warning')
    def test_run_network_bond_healthcheck_speed_warning(self,
                                                        m_warning,
                                                        m_report,
                                                        m_healthcheck,
                                                        m_agent):

        self.c.get_global_property = MagicMock(return_value='')

        svc1_obj = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                  'Applied',
                                  {'hostname': 'svc1'}, 'svc-1')

        m_agent.return_value.get_active_and_prime_bond_mbr.return_value = OrderedDict(
            [
                ('Active Member', 'eth0'),
                ('Primary Member', 'eth0')
            ]
        )

        m_agent.return_value.get_bond_interface_info.return_value = [
            OrderedDict(
                [('Member Interface', 'eth0'),
                ('MII Status', 'up'),
                ('Speed', '24000 Mbps')]
            ),
            OrderedDict(
                [('Member Interface', 'eth2'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps')]
            ),
        ]

        m_healthcheck.return_value.check_active_bond_member.return_value = 'OK'
        m_healthcheck.return_value.check_bond_interface_speed.return_value = 'WARNING'

        final_report = [OrderedDict([
            ('Node', 'svc1'),
            ('Active Member', 'eth0'),
            ('Primary Member', 'eth0'),
            ('Active Member State', 'OK'),
            ('eth0 MII Status', 'up'),
            ('eth0 Speed', '24000 Mbps'),
            ('eth0 Speed State', 'WARNING'),
            ('eth2 MII Status', 'up'),
            ('eth2 Speed', '25000 Mbps'),
            ('eth2 Speed State', 'OK')
        ])]

        self.c.run_network_bond_healthcheck([svc1_obj], True)
        m_report.assert_called_with(None, final_report[0].keys(), final_report)
        m_warning.assert_called_with('WARNING: Not every member interface has a '
                                      'speed of 25000Mbps on one or more nodes.')

    @patch('enm_healthcheck.EnminstAgent')
    @patch('enm_healthcheck.HealthCheck')
    @patch('enm_healthcheck.report_tab_data')
    def test_run_network_bond_healthcheck_fail(self,
                                               m_report,
                                               m_healthcheck,
                                               m_agent):

        self.c.get_global_property = MagicMock(return_value='')

        svc1_obj = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                  'Applied',
                                  {'hostname': 'svc1'}, 'svc-1')

        m_agent.return_value.get_active_and_prime_bond_mbr.return_value = OrderedDict(
            [
                ('Active Member', 'eth0'),
                ('Primary Member', 'eth0')
            ]
        )

        m_agent.return_value.get_bond_interface_info.return_value = [
            OrderedDict(
                [('Member Interface', 'eth0'),
                ('MII Status', 'down'),
                ('Speed', 'Unknown')]
            ),
            OrderedDict(
                [('Member Interface', 'eth2'),
                ('MII Status', 'up'),
                ('Speed', '25000 Mbps')]
            ),
        ]

        m_healthcheck.return_value.check_active_bond_member.return_value = 'OK'
        m_healthcheck.return_value.check_bond_interface_speed.return_value = 'OK'

        final_report = [OrderedDict([
            ('Node', 'svc1'),
            ('Active Member', 'eth0'),
            ('Primary Member', 'eth0'),
            ('Active Member State', 'OK'),
            ('eth0 MII Status', 'down'),
            ('eth0 Speed', 'Unknown'),
            ('eth0 Speed State', 'ERROR'),
            ('eth2 MII Status', 'up'),
            ('eth2 Speed', '25000 Mbps'),
            ('eth2 Speed State', 'OK')
        ])]

        self.assertRaises(SystemExit, self.c.run_network_bond_healthcheck, [svc1_obj], True)
        m_report.assert_called_with(None, final_report[0].keys(), final_report)

    def test_check_active_bond_member_ok(self):
        member_info = {
            'Active Member': 'eth0',
            'Primary Member': 'eth0'
        }

        self.assertEquals(self.c.check_active_bond_member(member_info),
            'OK')

    def test_check_active_bond_member_warning(self):
        member_info = {
            'Active Member': 'eth0',
            'Primary Member': 'eth2'
        }

        self.assertEquals(self.c.check_active_bond_member(member_info),
            'WARNING')

    def test_check_bond_interface_speed_ok(self):
        member_info = {
            'Member Interface': 'eth0',
            'MII Status': 'up',
            'Speed': '25000 Mbps'
        }

        self.assertEquals(self.c.check_bond_interface_speed(member_info),
            'OK')

    def test_check_bond_interface_speed_warning(self):
        member_info = {
            'Member Interface': 'eth0',
            'MII Status': 'up',
            'Speed': '24000 Mbps'
        }

        self.assertEquals(self.c.check_bond_interface_speed(member_info),
            'WARNING')

    def patch_ssh(self, ssh_mock, return_code, stdout, stderr):
        mstdout = MagicMock()
        mstdout.channel.recv_exit_status.return_value = return_code
        mstdout.read.return_value = stdout

        mstderr = MagicMock()
        mstderr.stderr.read.return_value = stderr

        ssh_mock.exec_command.return_value = [None, mstdout, mstderr]

    @patch('logging.Logger.info')
    @patch('logging.Logger.error')
    @patch('enm_upgrade_prechecks.report_tab_data')
    @patch('enm_healthcheck.is_env_on_rack')
    @patch('enm_healthcheck.GrubConfCheck')
    def test_grub_cfg_healthcheck(self, grub_cfg, is_on_rack, tab_data, log_error, log_info):
        # NOT on Blade
        is_on_rack.return_value = True
        self.c.grub_cfg_healthcheck(verbose=True)
        log_info.assert_called_with('Skipping grub.conf healthcheck. '
            'NOT applicable to ENM on Rackmount Servers.')
        self.assertEquals(self.c.grub_cfg_healthcheck(), None)

        # On Blade + check is Successful
        is_on_rack.return_value = False
        grub_cfg.report_lvs.return_value = 'report for testing'
        grub_cfg.return_value.grub_lvs_check_failed = False
        tab_data.return_value = 'data in a table for testing'
        self.c.grub_cfg_healthcheck(verbose=True)
        log_info.assert_any_call('Beginning of checking LVs in the grub.conf')
        log_info.assert_any_call('grub.cfg healthcheck status: PASSED.')

        # On Blade + check is Failed
        grub_cfg.report_lvs.return_value = 'report for testing'
        grub_cfg.return_value.grub_lvs_check_failed = True
        self.assertRaises(SystemExit, self.c.grub_cfg_healthcheck)
        log_error.assert_any_call('There is one or more mismatch between '
            'LVs in the model and LVs in grub.cfg ')
        log_error.assert_any_call('LVs in the grub.conf healthcheck Status: FAILED.')

    @patch('enm_healthcheck.HealthCheck')
    @patch('inspect.getargspec')
    def test_function_call(self, m_inspect, m_healthcheck):
        m_inspect.return_value = (['--action', 'nas_healthcheck'], "", "", "")
        m_healthcheck.test_healthcheck = MagicMock()
        m_healthcheck.return_value.test_healthcheck = MagicMock()
        self.hc.main(['--action', 'nas_healthcheck'])
        self.assertTrue(m_healthcheck.return_value.test_healthcheck)

    @patch('enm_healthcheck.HealthCheck')
    @patch('inspect.getargspec')
    def test_action_emninst_healthcheck(self, m_inspect, m_healthcheck):
        m_inspect.return_value = (['--action', 'enminst_healthcheck'], "", "", "")
        m_healthcheck.test_healthcheck = MagicMock()
        m_healthcheck.return_value.test_healthcheck = MagicMock()
        self.hc.main(['--action', 'enminst_healthcheck'])
        self.assertTrue(m_healthcheck.return_value.test_healthcheck)

    @patch('enm_healthcheck.HealthCheck')
    @patch('inspect.getargspec')
    def test_action_ombs_healthcheck(self, m_inspect, m_healthcheck):
        m_inspect.return_value = (['--action', 'ombs_backup_healthcheck'], "", "", "")
        m_healthcheck.test_healthcheck = MagicMock()
        m_healthcheck.return_value.test_healthcheck = MagicMock()
        self.hc.main(['--action', 'ombs_backup_healthcheck'])
        self.assertTrue(m_healthcheck.return_value.test_healthcheck)

    @patch('enm_healthcheck.HealthCheck')
    @patch('inspect.getargspec')
    def test_action_fcaps_healthcheck(self, m_inspect, m_healthcheck):
        m_inspect.return_value = (['--action', 'fcaps_healthcheck'], "", "", "")
        m_healthcheck.test_healthcheck = MagicMock()
        m_healthcheck.return_value.test_healthcheck = MagicMock()
        self.hc.main(['--action', 'fcaps_healthcheck'])
        self.assertTrue(m_healthcheck.return_value.test_healthcheck)

    @patch('enm_healthcheck.HealthCheck')
    def test_action_non_existing_healthcheck(self, m_healthcheck):
        self.assertRaises(SystemExit, self.hc.main, ['--action something'])

    @patch('enm_healthcheck.HealthCheck')
    def test_exclude_non_existing_healthcheck(self, m_healthcheck):
        self.assertRaises(SystemExit, self.hc.main, ['--exclude something'])

    @patch('h_util.h_nas_console.NasConsole.exec_basic_nas_command')
    @patch('h_util.h_utils.Decryptor.get_password')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_children')
    @patch('paramiko.SSHClient')
    def test_nas_healthcheck(self,
                             ssh,
                             rest_mock,
                             nas_pw,
                             exec_nas_cmd):
        hc = self.c

        ok_nas_audit_check = nas_audit_check_ok.split('\n')
        out_nas_audit = nas_audit_out.split('\n')
        fail_nas_audit = nas_audit_fail.split('\n')
        err_nas_audit_check = nas_audit_check_err.split('\n')
        warn_nas_audit_check = nas_audit_check_warn.split('\n')
        err_warn_nas_audit_check = nas_audit_check_err_warn.split('\n')

        nas_pw.return_value = 'nas_pw'

        self.patch_ssh(ssh, 0, '', None)

        # Audit passes - need to mock 3 exec_nas_command
        # ls - to determine if VA
        # audit
        # audit check
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(0, out_nas_audit, [], ""),
                                    (0, ok_nas_audit_check, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertEquals(hc.nas_healthcheck(verbose=True), None)

        # Simulate nasAudit failing with retcode 1
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(1, out_nas_audit, [], ""),
                                    (0, err_nas_audit_check, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertRaises(SystemExit, hc.nas_healthcheck)

        # Simulate nasAudit failing with retcode 2
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(2, out_nas_audit, [], ""),
                                    (0, err_warn_nas_audit_check, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertRaises(SystemExit, hc.nas_healthcheck)

        # Simulate nasAudit failing with retcode 3
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(3, out_nas_audit, [], ""),
                                    (0, warn_nas_audit_check, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertEquals(hc.nas_healthcheck(), None)

        # Verify do not do audit check on success if not verbose
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(0, out_nas_audit, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertEquals(hc.nas_healthcheck(verbose=False), None)

        # Simulate nasAudit fails to generate report
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(1, fail_nas_audit, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertRaises(SystemExit, hc.nas_healthcheck)

        # Simulate nasAudit fails to generate report but no report location
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(1, [], [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertRaises(SystemExit, hc.nas_healthcheck)

        # Simulate NAS being UnityXT
        hc.nas_type = 'unityxt'
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertEquals(hc.nas_healthcheck(verbose=False), None)

        # Unexpected error code from nasAudit
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(5, out_nas_audit, out_nas_audit, "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertRaises(SystemExit, hc.nas_healthcheck)

        # Simulate nasAudit warning and nasAuditCheck errors
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(3, out_nas_audit, [], ""),
                                    (1, warn_nas_audit_check, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertEquals(hc.nas_healthcheck(), None)

        # Simulate nasAudit error and nasAuditCheck errors
        hc.nas_type = 'veritas'
        exec_nas_cmd.side_effect = [(2, out_nas_audit, [], ""),
                                    (1, err_nas_audit_check, [], "")]
        rest_mock.side_effect = [sp1_path, pool_path, fs_path]
        self.assertRaises(SystemExit, hc.nas_healthcheck)

    @patch('h_hc.hc_mdt.MdtHealthCheck.mdt_nfs_volume_healthcheck')
    def test_mdt_healthcheck(self, mdt):
        hc = self.c
        self.assertEquals(hc.mdt_healthcheck(verbose=True), None)
        mdt.return_value = SystemExit
        self.assertRaises(SystemExit, hc.mdt_healthcheck(verbose=True))

    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('logging.Logger.info')
    @patch('h_hc.hc_consul.ConsulHC.healthcheck_consul')
    def test_consul_healthcheck(self, m_consul, m_info, m_litp):
        m_litp.return_value = True
        m_consul.return_value = True
        self.c.consul_healthcheck(verbose=True)
        m_info.assert_called_with('Consul Health Check status: PASSED.')

        m_consul.side_effect = SystemExit
        self.assertRaises(SystemExit,
                          self.c.consul_healthcheck, verbose=True)

        m_litp.return_value = False
        self.c.consul_healthcheck(verbose=True)
        m_info.assert_called_with(
            'Consul not installed, Skipping Health Check.')

    @patch('enm_healthcheck.HealthCheck.grub_cfg_healthcheck')
    @patch('enm_healthcheck.HealthCheck.network_bond_healthcheck')
    @patch('enm_healthcheck.HealthCheck.puppet_enabled_healthcheck')
    @patch('enm_healthcheck.HealthCheck.lvm_conf_filter_healthcheck')
    @patch('enm_healthcheck.HealthCheck.consul_healthcheck')
    @patch('enm_healthcheck.HealthCheck.mdt_healthcheck')
    @patch('enm_healthcheck.HealthCheck.system_service_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_cluster_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_llt_heartbeat_healthcheck')
    @patch('enm_healthcheck.HealthCheck.postgres_pre_uplift_check')
    @patch('enm_healthcheck.HealthCheck.postgres_expiry_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_availability_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_raft_index_lag_check')
    @patch('enm_healthcheck.HealthCheck.multipath_active_healthcheck')
    @patch('enm_healthcheck.HealthCheck.san_alert_healthcheck')
    @patch('enm_healthcheck.HealthCheck.node_fs_healthcheck')
    @patch('enm_healthcheck.HealthCheck.stale_mount_healthcheck')
    @patch('enm_healthcheck.HealthCheck.storagepool_healthcheck')
    @patch('enm_healthcheck.HealthCheck.nas_healthcheck')
    @patch('enm_healthcheck.HealthCheck.hw_resources_healthcheck')
    @patch('logging.Logger.info')
    @patch('h_litp.litp_rest_client.LitpRestClient.export_model_to_xml')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    def test_full_enm_exclude_healthchecks(self, m_exists, m_get, export,
                                           log_info, hc_hw, nas_hc, storage_san_hc,
                                           stale_mount, node_fs, san_alert, dmp, neo4j_lag,
                                           neo4j, pgs, pgs_uplift, llt, cluster, sg,
                                           service_status, mdt, hc_consul, lvm_conf, puppet,
                                           net_bond, grub_cfg):
        model = join(gettempdir(), 'exported.xml')
        with open(model, 'w') as ofile:
            ofile.write(test_hw.MODEL)
        model_xml = load_xml(model)
        export.return_value = model_xml
        self.c.set_exclude(["hw_resources_healthcheck", "nas_healthcheck",
                            "storagepool_healthcheck", "stale_mount_healthcheck",
                            "node_fs_healthcheck", "system_service_healthcheck",
                            "vcs_cluster_healthcheck", "vcs_llt_heartbeat_healthcheck",
                            "vcs_service_group_healthcheck", "consul_healthcheck",
                            "multipath_active_healthcheck", "puppet_enabled_healthcheck",
                            "san_alert_healthcheck", "lvm_conf_filter_healthcheck",
                            "mdt_healthcheck", "postgres_expiry_check",
                            "postgres_pre_uplift_check", "neo4j_availability_check",
                            "neo4j_raft_index_lag_check", "grub_cfg_healthcheck",
                            "network_bond_healthcheck"])

        self.assertEquals(self.c.enminst_healthcheck(), None)

        self.assertTrue(hc_hw.called)
        self.assertTrue(self.c.is_healthcheck_excluded('hw_resources_healthcheck', 'Hardware Resources Healthcheck'))
        log_info.assert_any_call('Skipping Hardware Resources Healthcheck as excluded.')

        self.assertTrue(nas_hc.called)
        self.assertTrue(self.c.is_healthcheck_excluded('nas_healthcheck', 'NAS Healthcheck'))
        log_info.assert_called_with('Skipping NAS Healthcheck as excluded.')

        self.assertTrue(storage_san_hc.called)
        self.assertTrue(self.c.is_healthcheck_excluded('storagepool_healthcheck', 'SAN Storage Healthcheck'))
        log_info.assert_called_with('Skipping SAN Storage Healthcheck as excluded.')

        self.assertTrue(san_alert.called)
        self.assertTrue(self.c.is_healthcheck_excluded('san_alert_healthcheck', 'SAN alert Healthcheck'))
        log_info.assert_called_with('Skipping SAN alert Healthcheck as excluded.')

        self.assertTrue(service_status.called)
        self.assertTrue(self.c.is_healthcheck_excluded('system_service_healthcheck', 'System Service Healthcheck'))
        log_info.assert_called_with('Skipping System Service Healthcheck as excluded.')

        self.assertTrue(neo4j.called)
        self.assertTrue(self.c.is_healthcheck_excluded('neo4j_availability_check', 'Neo4j availability Healthcheck'))
        log_info.assert_called_with('Skipping Neo4j availability Healthcheck as excluded.')

        self.assertTrue(neo4j_lag.called)
        self.assertTrue(self.c.is_healthcheck_excluded('neo4j_raft_index_lag_check',
                                                       'Neo4j raft index lag Healthcheck'))
        log_info.assert_called_with('Skipping Neo4j raft index lag Healthcheck as excluded.')

        self.assertTrue(pgs.called)
        self.assertTrue(self.c.is_healthcheck_excluded('postgres_expiry_check', 'Postgres password expiry Healthcheck'))
        log_info.assert_called_with('Skipping Postgres password expiry Healthcheck as excluded.')

        self.assertTrue(pgs_uplift.called)
        self.assertTrue(self.c.is_healthcheck_excluded('postgres_pre_uplift_check',
                                                       'Postgres pre version uplift requirements Healthcheck'))
        log_info.assert_called_with('Skipping Postgres pre version uplift requirements Healthcheck as excluded.')

        self.assertTrue(llt.called)
        self.assertTrue(self.c.is_healthcheck_excluded('vcs_llt_heartbeat_healthcheck',
                                                       'VCS LLT Heartbeat Healthcheck'))
        log_info.assert_called_with('Skipping VCS LLT Heartbeat Healthcheck '
                                    'as excluded.')

        self.assertTrue(node_fs.called)
        self.assertTrue(self.c.is_healthcheck_excluded('node_fs_healthcheck', 'Node Filesystem Healthcheck'))
        log_info.assert_called_with('Skipping Node Filesystem Healthcheck as excluded.')

        self.assertTrue(stale_mount.called)
        self.assertTrue(self.c.is_healthcheck_excluded('stale_mount_healthcheck', 'Stale Mount Healthcheck'))
        log_info.assert_called_with('Skipping Stale Mount Healthcheck as excluded.')

        self.assertTrue(sg.called)
        self.assertTrue(self.c.is_healthcheck_excluded('vcs_service_group_healthcheck',
                                                       'VCS Service Group Healthcheck'))
        log_info.assert_called_with('Skipping VCS Service Group Healthcheck as excluded.')

        self.assertTrue(mdt.called)
        self.assertTrue(self.c.is_healthcheck_excluded('mdt_healthcheck', 'MDT Healthcheck'))
        log_info.assert_called_with('Skipping MDT Healthcheck as excluded.')

        self.assertTrue(dmp.called)
        self.assertTrue(self.c.is_healthcheck_excluded('multipath_active_healthcheck',
                                                       'multipath number of paths Healthcheck'))
        log_info.assert_called_with('Skipping multipath number of paths Healthcheck as excluded.')

        self.assertTrue(hc_consul.called)
        self.assertTrue(self.c.is_healthcheck_excluded('consul_healthcheck', 'Consul Healthcheck'))
        log_info.assert_called_with('Skipping Consul Healthcheck as excluded.')

        self.assertTrue(lvm_conf.called)
        self.assertTrue(self.c.is_healthcheck_excluded('lvm_conf_filter_healthcheck', 'lvm.conf filter Healthcheck'))
        log_info.assert_called_with('Skipping lvm.conf filter Healthcheck as excluded.')

        self.assertTrue(puppet.called)
        self.assertTrue(self.c.is_healthcheck_excluded('puppet_enabled_healthcheck', 'LITP Puppet enabled Healthcheck'))
        log_info.assert_called_with('Skipping LITP Puppet enabled Healthcheck as excluded.')

        self.assertTrue(net_bond.called)
        self.assertTrue(self.c.is_healthcheck_excluded('network_bond_healthcheck', 'Network Bond Healthcheck'))
        log_info.assert_called_with('Skipping Network Bond Healthcheck as excluded.')

        self.assertTrue(grub_cfg.called)
        self.assertTrue(self.c.is_healthcheck_excluded('grub_cfg_healthcheck', 'grub.cfg Healthcheck'))
        log_info.assert_called_with('Skipping grub.cfg Healthcheck as excluded.')

        self.assertTrue(cluster.called)
        self.assertTrue(self.c.is_healthcheck_excluded('vcs_cluster_healthcheck', 'VCS Cluster System Healthcheck'))
        log_info.assert_called_with('Skipping VCS Cluster System Healthcheck as excluded.')

    @patch('enm_healthcheck.HealthCheck.grub_cfg_healthcheck')
    @patch('enm_healthcheck.HealthCheck.network_bond_healthcheck')
    @patch('enm_healthcheck.HealthCheck.puppet_enabled_healthcheck')
    @patch('enm_healthcheck.HealthCheck.lvm_conf_filter_healthcheck')
    @patch('enm_healthcheck.HealthCheck.consul_healthcheck')
    @patch('enm_healthcheck.HealthCheck.mdt_healthcheck')
    @patch('enm_healthcheck.HealthCheck.system_service_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_cluster_healthcheck')
    @patch('enm_healthcheck.HealthCheck.vcs_llt_heartbeat_healthcheck')
    @patch('enm_healthcheck.HealthCheck.postgres_pre_uplift_check')
    @patch('enm_healthcheck.HealthCheck.postgres_expiry_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_availability_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_raft_index_lag_check')
    @patch('enm_healthcheck.HealthCheck.multipath_active_healthcheck')
    @patch('enm_healthcheck.HealthCheck.san_alert_healthcheck')
    @patch('enm_healthcheck.HealthCheck.node_fs_healthcheck')
    @patch('enm_healthcheck.HealthCheck.stale_mount_healthcheck')
    @patch('enm_healthcheck.HealthCheck.storagepool_healthcheck')
    @patch('enm_healthcheck.HealthCheck.nas_healthcheck')
    @patch('enm_healthcheck.HealthCheck.hw_resources_healthcheck')
    @patch('logging.Logger.info')
    @patch('h_litp.litp_rest_client.LitpRestClient.export_model_to_xml')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    def test_full_enm_exclude_healthchecks_verbose(self, m_exists, m_get, export,
                                           log_info, hc_hw, nas_hc, storage_san_hc,
                                           stale_mount, node_fs, san_alert, dmp, neo4j_lag,
                                           neo4j, pgs, pgs_uplift, llt, cluster, sg,
                                           service_status, mdt, hc_consul, lvm_conf, puppet,
                                           net_bond, grub_cfg):
        model = join(gettempdir(), 'exported.xml')
        with open(model, 'w') as ofile:
            ofile.write(test_hw.MODEL)
        model_xml = load_xml(model)
        export.return_value = model_xml
        self.c.set_exclude(["hw_resources_healthcheck", "nas_healthcheck",
                            "storagepool_healthcheck", "stale_mount_healthcheck",
                            "node_fs_healthcheck", "system_service_healthcheck",
                            "vcs_cluster_healthcheck", "vcs_llt_heartbeat_healthcheck",
                            "vcs_service_group_healthcheck", "consul_healthcheck",
                            "multipath_active_healthcheck", "puppet_enabled_healthcheck",
                            "san_alert_healthcheck", "lvm_conf_filter_healthcheck",
                            "mdt_healthcheck", "postgres_expiry_check",
                            "postgres_pre_uplift_check", "neo4j_availability_check",
                            "neo4j_raft_index_lag_check", "grub_cfg_healthcheck",
                            "network_bond_healthcheck"])

        self.assertEquals(self.c.enminst_healthcheck(verbose=True), None)

        self.assertTrue(hc_hw.called)
        self.assertTrue(self.c.is_healthcheck_excluded('hw_resources_healthcheck', 'Hardware Resources Healthcheck'))
        log_info.assert_any_call('Skipping Hardware Resources Healthcheck as excluded.')

        self.assertTrue(nas_hc.called)
        self.assertTrue(self.c.is_healthcheck_excluded('nas_healthcheck', 'NAS Healthcheck'))
        log_info.assert_called_with('Skipping NAS Healthcheck as excluded.')

        self.assertTrue(storage_san_hc.called)
        self.assertTrue(self.c.is_healthcheck_excluded('storagepool_healthcheck', 'SAN Storage Healthcheck'))
        log_info.assert_called_with('Skipping SAN Storage Healthcheck as excluded.')

        self.assertTrue(san_alert.called)
        self.assertTrue(self.c.is_healthcheck_excluded('san_alert_healthcheck', 'SAN alert Healthcheck'))
        log_info.assert_called_with('Skipping SAN alert Healthcheck as excluded.')

        self.assertTrue(service_status.called)
        self.assertTrue(self.c.is_healthcheck_excluded('system_service_healthcheck', 'System Service Healthcheck'))
        log_info.assert_called_with('Skipping System Service Healthcheck as excluded.')

        self.assertTrue(neo4j.called)
        self.assertTrue(self.c.is_healthcheck_excluded('neo4j_availability_check', 'Neo4j availability Healthcheck'))
        log_info.assert_called_with('Skipping Neo4j availability Healthcheck as excluded.')

        self.assertTrue(neo4j_lag.called)
        self.assertTrue(self.c.is_healthcheck_excluded('neo4j_raft_index_lag_check',
                                                       'Neo4j raft index lag Healthcheck'))
        log_info.assert_called_with('Skipping Neo4j raft index lag Healthcheck as excluded.')

        self.assertTrue(pgs.called)
        self.assertTrue(self.c.is_healthcheck_excluded('postgres_expiry_check', 'Postgres password expiry Healthcheck'))
        log_info.assert_called_with('Skipping Postgres password expiry Healthcheck as excluded.')

        self.assertTrue(pgs_uplift.called)
        self.assertTrue(self.c.is_healthcheck_excluded('postgres_pre_uplift_check',
                                                       'Postgres pre version uplift requirements Healthcheck'))
        log_info.assert_called_with('Skipping Postgres pre version uplift requirements Healthcheck as excluded.')

        self.assertTrue(llt.called)
        self.assertTrue(self.c.is_healthcheck_excluded('vcs_llt_heartbeat_healthcheck',
                                                       'VCS LLT Heartbeat Healthcheck'))
        log_info.assert_called_with('Skipping VCS LLT Heartbeat Healthcheck '
                                    'as excluded.')

        self.assertTrue(node_fs.called)
        self.assertTrue(self.c.is_healthcheck_excluded('node_fs_healthcheck', 'Node Filesystem Healthcheck'))
        log_info.assert_called_with('Skipping Node Filesystem Healthcheck as excluded.')

        self.assertTrue(stale_mount.called)
        self.assertTrue(self.c.is_healthcheck_excluded('stale_mount_healthcheck', 'Stale Mount Healthcheck'))
        log_info.assert_called_with('Skipping Stale Mount Healthcheck as excluded.')

        self.assertTrue(sg.called)
        self.assertTrue(self.c.is_healthcheck_excluded('vcs_service_group_healthcheck',
                                                       'VCS Service Group Healthcheck'))
        log_info.assert_called_with('Skipping VCS Service Group Healthcheck as excluded.')

        self.assertTrue(mdt.called)
        self.assertTrue(self.c.is_healthcheck_excluded('mdt_healthcheck', 'MDT Healthcheck'))
        log_info.assert_called_with('Skipping MDT Healthcheck as excluded.')

        self.assertTrue(dmp.called)
        self.assertTrue(self.c.is_healthcheck_excluded('multipath_active_healthcheck',
                                                       'multipath number of paths Healthcheck'))
        log_info.assert_called_with('Skipping multipath number of paths Healthcheck as excluded.')

        self.assertTrue(hc_consul.called)
        self.assertTrue(self.c.is_healthcheck_excluded('consul_healthcheck', 'Consul Healthcheck'))
        log_info.assert_called_with('Skipping Consul Healthcheck as excluded.')

        self.assertTrue(lvm_conf.called)
        self.assertTrue(self.c.is_healthcheck_excluded('lvm_conf_filter_healthcheck', 'lvm.conf filter Healthcheck'))
        log_info.assert_called_with('Skipping lvm.conf filter Healthcheck as excluded.')

        self.assertTrue(puppet.called)
        self.assertTrue(self.c.is_healthcheck_excluded('puppet_enabled_healthcheck', 'LITP Puppet enabled Healthcheck'))
        log_info.assert_called_with('Skipping LITP Puppet enabled Healthcheck as excluded.')

        self.assertTrue(net_bond.called)
        self.assertTrue(self.c.is_healthcheck_excluded('network_bond_healthcheck', 'Network Bond Healthcheck'))
        log_info.assert_called_with('Skipping Network Bond Healthcheck as excluded.')

        self.assertTrue(grub_cfg.called)
        self.assertTrue(self.c.is_healthcheck_excluded('grub_cfg_healthcheck', 'grub.cfg Healthcheck'))
        log_info.assert_called_with('Skipping grub.cfg Healthcheck as excluded.')

        self.assertTrue(cluster.called)
        self.assertTrue(self.c.is_healthcheck_excluded('vcs_cluster_healthcheck', 'VCS Cluster System Healthcheck'))
        log_info.assert_called_with('Skipping VCS Cluster System Healthcheck as excluded.')

    @patch('enm_healthcheck.LitpSanSnapshots')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    def test_multipath_active_healthcheck_with_nodes(self, m_exists,
                                                     m_get, lss):
        m_exists.return_value = False
        m_get.return_value = enm_dep_type_path

        lss().get_nodes_with_luns.return_value = 'n1'
        lss().get_deployment_type.return_value = 'vnx'
        with patch.object(self.hc, 'EnminstAgent') as ea:
            ea().get_redundancy_level.return_value = {
                'n1': dmp_subpaths_2ctlr_all_ok,
                'n2': multipath_ll_htype1}
            ea().get_mco_fact_disk_list.mp_config_value = {'n1': mco_fct_dsk_good_mpath}
            self.assertEqual(None, self.c.multipath_active_healthcheck())

        with patch.object(self.hc, 'EnminstAgent') as ea:
            ea().get_redundancy_level.return_value = {
                'n1': dmp_subpaths_2ctlr_all_ok,
                'n2': multipath_ll_htype1}
            ea().get_mp_bind_names_config.mco_facts_value = {'n1': mp_conf_three_mpath}
            self.assertEqual(None, self.c.multipath_active_healthcheck())

    @patch('enm_healthcheck.LitpSanSnapshots')
    def test_multipath_hc_not_running_without_san(self, lss):
        # if get_deployment_type returns empty then no san is configured
        # and the HC shouldn't run
        lss().get_deployment_type.return_value = ''
        self.c.get_global_property = MagicMock(return_value='')
        self.c.multipath_active_healthcheck()
        lss().get_nodes_with_luns.assert_has_calls([])

    @patch('enm_healthcheck.LitpSanSnapshots')
    def test_multipath_hc_not_running_openstack(self, lss):
        lss().get_deployment_type.return_value = ''
        self.c.get_global_property = MagicMock(return_value='vLITP_ENM_On_Rack_Servers')
        self.c.multipath_active_healthcheck()
        lss().get_deployment_type.assert_not_called()

    @patch('enm_healthcheck.LitpSanSnapshots')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    def test_multipath_active_healthcheck_raises_mcoagentexception(
            self, m_exists, m_get, lss):
        m_exists.return_value = False
        m_get.return_value = enm_dep_type_path

        lss().get_nodes_with_luns.return_value = 'n1'
        lss().get_deployment_type.return_value = 'vnx'
        with patch.object(self.hc, 'EnminstAgent') as ea:
            ea().get_redundancy_level.return_value = {
                'n1': dmp_subpaths_2ctlr_all_ok,
                'n2': multipath_ll_htype1}
            ea().get_mco_fact_disk_list.side_effect = McoAgentException
            self.assertRaises(McoAgentException,
                              self.c.multipath_active_healthcheck)

    @patch('enm_healthcheck.MPpathsHealthCheck')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('enm_healthcheck.EnminstAgent.get_redundancy_level')
    @patch('enm_healthcheck.EnminstAgent.get_mco_fact_disk_list')
    @patch('h_snapshots.litp_snapshots.get_nas_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_all_items_by_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_deployment_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_nodes_with_luns')
    @patch('enm_healthcheck.EnminstAgent.get_mp_bind_names_config')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    def test_multipath_hc_running_on_rack(self, m_get_clust_nodes,
                                          m_get_mp_bind,
                                          m_get_nodes,
                                          m_get_dep_type,
                                          m_get_all,
                                          m_get_nas_type,
                                          m_get_mco_fact,
                                          m_get_redun,
                                          m_exists,
                                          m_get,
                                          m_multipath_hc):

        m_exists.return_value = True
        m_get.return_value = {
            'properties': {
                'key': 'enm_deployment_type',
                'value': 'Extra_Large_ENM_On_Rack_Servers'
            }
        }

        m_get_dep_type.return_value = 'vnx'
        m_get_all.return_value = san1_path
        m_get_nodes.return_value = {'svc1', 'svc2', 'db1', 'db2'}

        svc1_object = MockLitpObject('/deployments/enm/clusters/svc_cluster/'
                                     'nodes/svc-1',
                                     'Applied',
                                     {'hostname': 'svc1'}, 'svc-1')
        svc2_object = MockLitpObject('/deployments/enm/clusters/svc_cluster/'
                                     'nodes/svc-2',
                                     'Applied',
                                     {'hostname': 'svc2'}, 'svc-2')
        db1_object = MockLitpObject('/deployments/enm/clusters/db_cluster/'
                                    'nodes/db-1',
                                    'Applied',
                                    {'hostname': 'db1'}, 'db-1')
        db2_object = MockLitpObject('/deployments/enm/clusters/db_cluster/'
                                    'nodes/db-2',
                                    'Applied',
                                    {'hostname': 'db2'}, 'db-2')
        mock_cluster_nodes = {'svc_cluster': {'svc-1': svc1_object,
                                              'svc-2': svc2_object},
                              'db_cluster': {'db-1': db1_object,
                                             'db-2': db2_object}}

        m_get_clust_nodes.return_value = mock_cluster_nodes

        m_get_redun.return_value = {'svc2': 'svc2_stdout',
                                    'svc1': 'svc1_stdout',
                                    'db2': 'db2_stdout',
                                    'db1': 'db1_stdout'}

        m_multipath_hc().process_dmp_paths_node_output.return_value = None

        self.c.multipath_active_healthcheck()

        m_get_redun.assert_called_with(hosts=['db1', 'db2', 'svc2', 'svc1'])
        m_get_mco_fact.assert_has_calls([mock.call(hosts='db1'),
                                         mock.call(hosts='db2'),
                                         mock.call(hosts='svc2'),
                                         mock.call(hosts='svc1')])
        self.assertEqual(m_get_mco_fact.call_count, 4)
        m_get_mp_bind.assert_has_calls([mock.call(hosts='db1'),
                                        mock.call(hosts='db2'),
                                        mock.call(hosts='svc2'),
                                        mock.call(hosts='svc1')])
        self.assertEqual(m_get_mp_bind.call_count, 4)

    @patch('enm_healthcheck.MPpathsHealthCheck')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_all_items_by_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_deployment_type')
    def test_multipath_hc_fc_switches_not_in_model(self,
                                          m_get_dep_type,
                                          m_get_all,
                                          m_exists,
                                          m_get,
                                          m_multipath_hc):

        m_exists.return_value = True
        m_get.return_value = {
            'properties': {
                'key': 'enm_deployment_type',
                'value': 'Extra_Large_ENM_On_Rack_Servers'
            }
        }
        m_get_dep_type.return_value = 'vnx'
        litp_san = [{'path': '/infrastructure/storage/storage_providers/san1', 'data': {'id': 'san1', 'item-type-name': 'san-emc', \
                                'applied_properties_determinable': True, 'state': 'Applied', '_links': {'self': \
                                {'href': 'http://127.0.0.1/litp/rest/v1/infrastructure/storage/storage_providers/san1'}, \
                                'item-type': {'href': 'http://127.0.0.1/litp/rest/v1/item-types/san-emc'}}, 'properties': \
                                {'username': 'admin', 'name': 'IEATVNX-112', 'storage_network': 'storage', 'storage_site_id': 'ENM336', 'login_scope': 'global', \
                                'password_key': 'key-for-san-IEATVNX-112', 'ip_b': '10.140.44.6', 'san_type': 'vnx2', 'ip_a': '10.140.44.5'}}}]

        m_get_all.return_value = litp_san
        try:
            self.c.multipath_active_healthcheck()
        except:
            self.assertRaises(SystemExit())

    @patch('enm_healthcheck.MPpathsHealthCheck')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('enm_healthcheck.EnminstAgent.get_redundancy_level')
    @patch('enm_healthcheck.EnminstAgent.get_mco_fact_disk_list')
    @patch('h_snapshots.litp_snapshots.get_nas_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_deployment_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_nodes_with_luns')
    @patch('enm_healthcheck.EnminstAgent.get_mp_bind_names_config')
    def test_multipath_hc_not_running_on_rack(self, m_get_mp_bind,
                                              m_get_nodes,
                                              m_get_dep_type,
                                              m_get_nas_type,
                                              m_get_mco_fact,
                                              m_get_redun,
                                              m_exists,
                                              m_get,
                                              m_multipath_hc):
        m_exists.return_value = True
        m_get.return_value = {
            'properties': {
                'key': 'enm_deployment_type',
                'value': 'Medium_ENM'
            }
        }

        m_get_dep_type.return_value = 'vnx'
        m_get_nodes.return_value = {'svc1', 'svc2', 'db1', 'db2'}

        m_get_redun.return_value = {'db1': 'db1_stdout',
                                    'db2': 'db2_stdout',
                                    'svc2': 'svc2_stdout',
                                    'svc1': 'svc1_stdout'}

        m_multipath_hc().process_dmp_paths_node_output.return_value = None

        self.c.multipath_active_healthcheck()

        m_get_redun.assert_called_with(hosts=['db1', 'db2', 'svc2', 'svc1'])
        m_get_mco_fact.assert_has_calls([mock.call(hosts='db1'),
                                         mock.call(hosts='db2'),
                                         mock.call(hosts='svc2'),
                                         mock.call(hosts='svc1')])
        self.assertEqual(m_get_mco_fact.call_count, 4)
        m_get_mp_bind.assert_has_calls([mock.call(hosts='db1'),
                                        mock.call(hosts='db2'),
                                        mock.call(hosts='svc2'),
                                        mock.call(hosts='svc1')])
        self.assertEqual(m_get_mp_bind.call_count, 4)

    @patch('enm_healthcheck.MPpathsHealthCheck')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch('h_litp.litp_rest_client.LitpRestClient.exists')
    @patch('enm_healthcheck.EnminstAgent.get_redundancy_level')
    @patch('enm_healthcheck.EnminstAgent.get_mco_fact_disk_list')
    @patch('h_snapshots.litp_snapshots.get_nas_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_deployment_type')
    @patch('enm_healthcheck.LitpSanSnapshots.get_nodes_with_luns')
    @patch('enm_healthcheck.EnminstAgent.get_mp_bind_names_config')
    def test_multipath_hc_enm_dep_type_none(self, m_get_mp_bind,
                                              m_get_nodes,
                                              m_get_dep_type,
                                              m_get_nas_type,
                                              m_get_mco_fact,
                                              m_get_redun,
                                              m_exists,
                                              m_get,
                                              m_multipath_hc):
        m_exists.return_value = True
        m_get.return_value = {
            'properties': {
                'key': 'enm_deployment_type',
                'value': None
            }
        }

        m_get_dep_type.return_value = 'vnx'
        m_get_nodes.return_value = {'svc1', 'svc2', 'db1', 'db2'}

        m_get_redun.return_value = {'db1': 'db1_stdout',
                                    'db2': 'db2_stdout',
                                    'svc2': 'svc2_stdout',
                                    'svc1': 'svc1_stdout'}

        m_multipath_hc().process_dmp_paths_node_output.return_value = None

        self.c.multipath_active_healthcheck()

        m_get_redun.assert_called_with(hosts=['db1', 'db2', 'svc2', 'svc1'])
        m_get_mco_fact.assert_has_calls([mock.call(hosts='db1'),
                                         mock.call(hosts='db2'),
                                         mock.call(hosts='svc2'),
                                         mock.call(hosts='svc1')])
        self.assertEqual(m_get_mco_fact.call_count, 4)
        m_get_mp_bind.assert_has_calls([mock.call(hosts='db1'),
                                        mock.call(hosts='db2'),
                                        mock.call(hosts='svc2'),
                                        mock.call(hosts='svc1')])
        self.assertEqual(m_get_mp_bind.call_count, 4)

    @patch('enm_healthcheck.Neo4jClusterOverview.is_single_mode')
    @patch('enm_healthcheck.Neo4jClusterOverview.raft_index_lag_check')
    def test_neo4j_raft_index_lag_check_on_60K(self, neo4j_lag, neo4j_mode):
        neo4j_mode.return_value = False
        result = self.c.neo4j_raft_index_lag_check()
        self.assertTrue(neo4j_lag.called)

    @patch('enm_healthcheck.Neo4jClusterOverview.is_single_mode')
    @patch('enm_healthcheck.Neo4jClusterOverview.raft_index_lag_check')
    def test_neo4j_raft_index_lag_check_on_single(self, neo4j_lag, neo4j_mode):
        neo4j_mode.return_value = True
        result = self.c.neo4j_raft_index_lag_check()
        self.assertFalse(neo4j_lag.called)

    @patch('enm_healthcheck.HealthCheck.run_fcaps_healthcheck')
    def test_fcaps_healthcheck_os_error(self, fcaps):
        fcaps.side_effect = OSError
        self.assertRaises(SystemExit, self.c.fcaps_healthcheck)

    @patch('enm_healthcheck.HealthCheck.run_fcaps_healthcheck')
    def test_fcaps_healthcheck_io_error(self, fcaps):
        fcaps.side_effect = IOError
        self.assertRaises(SystemExit, self.c.fcaps_healthcheck)

    @patch('enm_healthcheck.HealthCheck.run_fcaps_healthcheck')
    def test_fcaps_healthcheck_any_exception(self, fcaps):
        fcaps.side_effect = Exception
        self.assertRaises(SystemExit, self.c.fcaps_healthcheck)

    @patch('h_hc.hc_neo4j_cluster.DbNodesSshCredentials.validate_credentials_for_key_access')
    @patch('os.path.exists')
    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_pre_uplift_credentials_force_key_access(self, credentials, need_uplift_4x, need_uplift,
                                                           is_single_mode, exists, validate_credentials_for_key_access):
        def mocked_exists(path):
            if path == FORCE_SSH_KEY_ACCESS_FLAG_PATH:
                return True
            return builtin_os_path_exists(path)
        exists.side_effect = mocked_exists
        is_single_mode.return_value = False
        need_uplift.return_value = True
        credentials.side_effect = DbNodesSshCredentials()
        self.c.neo4j_uplift_creds_check(None)
        self.assertTrue(validate_credentials_for_key_access.called)

    @patch('h_hc.hc_neo4j_cluster.DbNodesSshCredentials.validate_credentials_for_key_access')
    @patch('os.path.exists')
    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_pre_uplift_credentials_force_key_access_force_hc(self, credentials, need_uplift, is_single_mode,
                                                                    exists, validate_credentials_for_key_access):
        def mocked_exists(path):
            if path == FORCE_SSH_KEY_ACCESS_FLAG_PATH:
                return True
            return builtin_os_path_exists(path)
        exists.side_effect = mocked_exists
        is_single_mode.return_value = False
        need_uplift.return_value = False
        credentials.side_effect = DbNodesSshCredentials()
        os.environ['FORCE_NEO4J_UPLIFT_CREDS_CHECK'] = 'true'
        self.c.neo4j_uplift_creds_check(None)
        self.assertTrue(validate_credentials_for_key_access.called)

    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_pre_uplift_credentials_fail(self, credentials, need_uplift_4x,
                                               need_uplift, is_single_mode):
        is_single_mode.return_value = False
        need_uplift.return_value = True
        credentials.side_effect = DbNodesSshCredentials()

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertRaises(SystemExit, self.c.neo4j_uplift_creds_check, cfg)

    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_need_uplift_fail(self, credentials, need_uplift_4x,
                                    need_uplift, is_single_mode):
        is_single_mode.return_value = False
        need_uplift.side_effect = Neo4jClusterOverviewException()

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertRaises(SystemExit, self.c.neo4j_uplift_creds_check, cfg)

    @patch('enm_healthcheck.HealthCheck.neo4j_uplift_space_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_uplift_creds_check')
    def test_fail_neo4j_uplift_healthcheck(self, m_creds, m_space):
        m_space.side_effect = SystemExit

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertRaises(SystemExit, self.c.neo4j_uplift_healthcheck, cfg)

    @patch('enm_healthcheck.HealthCheck.neo4j_uplift_space_check')
    @patch('enm_healthcheck.HealthCheck.neo4j_uplift_creds_check')
    def test_neo4j_uplift_healthcheck(self, m_creds, m_space):
        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        try:
            self.c.neo4j_uplift_healthcheck(cfg)
        except SystemExit:
            self.fail('neo4j_uplift_healthcheck unexpected exception')
        self.assertTrue(m_creds.called)
        self.assertTrue(m_space.called)

    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_single_mode_check_fail(self, credentials, need_uplift_4x,
                                          need_uplift, is_single_mode):
        need_uplift.return_value = True
        is_single_mode.side_effect = Neo4jClusterOverviewException()

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.assertRaises(SystemExit, self.c.neo4j_uplift_creds_check, cfg)

    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_pre_uplift_check_positive(self, credentials, need_uplift_4x,
                                             need_uplift, is_single_mode):
        is_single_mode.return_value = False
        need_uplift.return_value = True

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.c.neo4j_uplift_creds_check(cfg)
        self.assertEqual(credentials.call_count, 1)
        self.assertEqual(need_uplift.call_count, 1)
        self.assertEqual(is_single_mode.call_count, 1)

    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_pre_uplift_is_single_mode(self, credentials, need_uplift_4x,
                                             need_uplift, is_single_mode):
        need_uplift.return_value = True
        is_single_mode.return_value = True

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.c.neo4j_uplift_creds_check(cfg)
        self.assertEqual(credentials.call_count, 0)
        self.assertEqual(need_uplift.call_count, 1)
        self.assertEqual(is_single_mode.call_count, 1)

    @patch.object(Neo4jClusterOverview, "version", new_callable=PropertyMock)
    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch.object(DbNodesSshCredentials, 'validate_credentials')
    def test_neo4j_not_need_uplift(self, credentials, need_uplift_4x,
                                   need_uplift, is_single_mode, version):
        need_uplift.return_value = False
        need_uplift_4x.return_value = False

        class Args(object):
            model_xml = "/software/autoDeploy/Sed.xml"
        cfg = Args()
        self.c.neo4j_uplift_creds_check(cfg)
        self.assertEqual(credentials.call_count, 0)
        self.assertEqual(need_uplift.call_count, 1)
        self.assertEqual(is_single_mode.call_count, 0)

    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "get_pre_uplift_space_report")
    def test_neo4j_uplift_space_check(self, space_rep, need_uplift):
        need_uplift.return_value = True
        self.c.neo4j_uplift_space_check()
        self.assertEqual(need_uplift.call_count, 1)
        self.assertEqual(space_rep.call_count, 1)

    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "get_pre_uplift_space_report")
    def test_failed_neo4j_uplift_space_check(self, space_rep, need_uplift):
        need_uplift.return_value = True
        space_rep.side_effect = SystemExit
        self.assertRaises(SystemExit, self.c.neo4j_uplift_space_check)

    @patch('logging.Logger.info')
    def test_is_healthcheck_excluded(self, m_log):
        self.c.set_exclude(["first_healthcheck", "second_healthcheck"])
        self.assertTrue(self.c.is_healthcheck_excluded("first_healthcheck", "log_message"))
        m_log.assert_any_call('Skipping log_message as excluded.')
        self.assertTrue(self.c.is_healthcheck_excluded("second_healthcheck", "log_message"))
        self.assertFalse(self.c.is_healthcheck_excluded("third_healthcheck", "log_message"))

if __name__ == '__main__':
    unittest2.main()
