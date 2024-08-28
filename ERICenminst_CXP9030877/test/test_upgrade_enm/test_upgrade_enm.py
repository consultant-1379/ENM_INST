import sys

from mock import MagicMock, mock_open

import test_hw_resources.test_hw_resources as test_hw
from hw_resources import HwResources
from litpd import LitpIntegration

sys.modules['sanapiexception'] = MagicMock()

import httplib
from json import dumps
import os
import shutil

from os import environ, makedirs
from os.path import isfile, join, exists, isdir, dirname
from tempfile import NamedTemporaryFile
from tempfile import gettempdir
from tempfile import mktemp

from argparse import Namespace
from itertools import cycle
from mock import patch, call, ANY
from unittest2 import TestCase
from unittest2 import main

import logging
import import_iso

sys.modules['naslib.log'] = MagicMock()
sys.modules['naslib.objects'] = MagicMock()
sys.modules['naslib.drivers'] = MagicMock()
sys.modules['naslib.drivers.sfs'] = MagicMock()
sys.modules['naslib.drivers.sfs.utils'] = MagicMock()

from enm_snapshots import UPGRADE_SNAPSHOTS_TAKEN
from h_litp.litp_rest_client import LitpException, LitpRestClient
from h_logging.enminst_logger import init_enminst_logging
from h_snapshots.san_snapshot import SanApiException

from h_util.h_utils import ExitCodes, touch
from tempfile import mkdtemp
from test_utils import mock_litp_get_requests, assert_exception_raised
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mocks
import test_utils

fcaps_healthcheck_modules = test_utils.mock_fcaps_healthcheck_module()
fcaps_healthcheck_module_patcher = patch.dict('sys.modules', fcaps_healthcheck_modules)
fcaps_healthcheck_module_patcher.start()
from enm_healthcheck import HealthCheck

from h_hc.hc_neo4j_cluster import Neo4jClusterOverview, \
    FORCE_SSH_KEY_ACCESS_FLAG_PATH
from h_util.h_utils import Sed

CMD_UPGRADE_ENM = 'upgrade_enm.sh'
CMD_UPGRADE_ENM_DEFAULT_OPTIONS = 'upgrade_enm.sh -v -y'

current_path = os.path.dirname(__file__)
logger = init_enminst_logging()
builtin_os_path_exists = os.path.exists

class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id

    def get_property(self, key):
        return self.properties[key]

GOSSIP_ROUTER_SG = MockLitpObject('/deployments/enm/clusters/db_cluster'\
'/services/gossiprouter_clustered_service', 'Applied',
                                {}, 'gossiprouter_clustered_service')

class TestENMUpgrade(TestCase):
    def __init__(self, method_name='runTest'):
        super(TestENMUpgrade, self).__init__(method_name)
        self.logger = logging.getLogger('enminst')
        self.maxDiff = None

    def log(self, message):
        self.logger.info(message)

    def mktmpfile(self, filename):
        filepath = join(self.tmpdir, filename)
        touch(filepath)
        return filepath

    def setUp(self):
        self.tmpdir = join(gettempdir(), 'TestENMUpgrade')
        if exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        os.makedirs(self.tmpdir)

        self.iso_filename = self.mktmpfile('ERICenm_CXP9027091-1.5.20.iso')
        self.sed_filename = self.mktmpfile('sed.txt')
        self.model_xml_filename = self.mktmpfile('enm-deployment_dd.xml')
        self.os_patch_filename = self.mktmpfile(
            'rhel-oss-patches-19089-CXP9041797-D.iso')
        self.os_patch_filename_rh7 = self.mktmpfile(
            'rhel-oss-patches-19089-CXP9041797-D.iso')
        self.os_patch_filename_rh8 = self.mktmpfile(
            'rhel-oss-patches-19089-CXP9043482-A.iso')
        self.litp_iso_filename = self.mktmpfile(
            'ERIClitp_CXP9024296-2.23.16.iso')
        self.rhel7_9_iso_filename = self.mktmpfile(
            'RHEL77_Media_CXP9041797-2.0.1.iso')
        self.rhel7_release_filename = self.mktmpfile(
            'ericrhel79-release')
        self.rhel8_release_filename = self.mktmpfile(
            'ericrhel88-release')

        environ['ENMINST_RUNTIME'] = gettempdir()

        with open(self.rhel7_release_filename, 'w') as _writer:
            _writer.writelines(['{',
                                '"cxp": "9041797",',
                                '"rhel_version": "7.9",'
                                '"parent_cxp": "9026759",',
                                '"gask_candidate": "AH",',
                                '"nexus_version": "1.28.1"',
                                '}'])

        with open(self.rhel8_release_filename, 'w') as _writer:
            _writer.writelines(['{',
                                '"cxp": "9043482",',
                                '"rhel_version": "8.8",'
                                '"parent_cxp": "9026759",',
                                '"gask_candidate": "AH",',
                                '"nexus_version": "1.28.1"',
                                '}'])

        self.snapshots_indicator_filename = \
            os.path.join(gettempdir(), UPGRADE_SNAPSHOTS_TAKEN)
        self.ms_patched_done_file = os.path.join(gettempdir(), 'ms_os_patched')
        self.deploy_diff_filename = self.mktmpfile('output_enm_deployment.txt')
        import upgrade_enm
        self.upgrade_enm = upgrade_enm
        self.reported_data = None
        self.check_message = None
        self.workingcfg = None

    def tearDown(self):
        del os.environ['ENMINST_RUNTIME']
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        try:
            os.remove(self.snapshots_indicator_filename)
        except OSError:
            pass

    def add_rhel7_9_iso_option(self):
        return ' --rhel7_10_iso ' + self.rhel7_9_iso_filename

    def add_os_patch_option(self):
        return ' --patch_rhel ' + self.os_patch_filename

    def add_os_patch_option_multiple(self):
        return ' --patch_rhel ' + self.os_patch_filename + ' ' + \
            self.os_patch_filename_rh8

    def add_litp_upgrade_option(self):
        return ' --litp_iso ' + self.litp_iso_filename

    def add_iso_option(self):
        return ' -e ' + self.iso_filename

    def add_sed_option(self):
        return ' -s ' + self.sed_filename

    def add_model_xml_option(self):
        return ' -m ' + self.model_xml_filename

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_reboot_required')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.apply_os_patches')
    @patch('upgrade_enm.manage_snapshots')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot(self,
                              m_verify_dd_expanding_nodes,
                              m_unity_updates,
                              m_neo4j_uplift,
                              m_validate_enm_deployment_xml,
                              m_neo4j_pre_check,
                              m_vcs,
                              m_postgres,
                              m_log_cmdline_args,
                              m_prepare_runtime_config,
                              enable_serialport_service,
                              exec_healthcheck,
                              m_infrastructure_changes,
                              m_exec_process,
                              m_check_any_snapshots_exist,
                              m_manage_snapshots,
                              m_apply_os_patches,
                              m_subparams,
                              check_upgrade_hw_provisions,
                              u_execute_post_upgrade_steps,
                              m_create_xml_diff_file,
                              m_create_removed_blades_info_file,
                              m_get_cxp_values,
                              m_verify_dd_not_reducing_nodes,
                              enable_puppet_on_nodes,
                              m_verify_gossip_router_upgrade,
                              m_check_postgres_uplift_requirements,
                              m_check_reboot_required,
                              m_nas_type):
        m_check_reboot_required.return_value = True
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        m_exec_process.return_value = 'Hewlett-Packard'
        m_check_any_snapshots_exist.return_value = False
        m_nas_type.return_value = ''

        args = '{0}{1}{2}{3}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                     self.add_os_patch_option(),
                                     self.add_model_xml_option(),
                                     self.add_sed_option())

        self.upgrade_enm.main(args.split())

        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_check_any_snapshots_exist.called)
        self.assertTrue(m_manage_snapshots.called)
        self.assertTrue(m_apply_os_patches.called)

    def mock_modeled_images(self, *images):
        items = []
        for image_info in images:
            _project = image_info[0]
            for _image in image_info[1]:
                image_modelid = _image[0]
                image_filename = _image[1]
                items.append({
                    'id': image_modelid,
                    'item-type-name': 'vm-image',
                    'state': 'Applied',
                    '_links': {
                        'self': {
                            'href': 'https://localhost:9999/litp/rest'
                                    '/v1/software/images/' + image_modelid
                        }
                    },
                    'properties': {
                        'source_uri':
                            'http://localhost/images/' +
                            _project + '/' + image_filename,

                    }
                })
        return dumps({
            '_embedded': {'item': items}, 'id': 'images'
        })

    @patch('import_iso.get_log')
    @patch('import_iso.create_mnt_dir')
    @patch('import_iso.umount')
    @patch('import_iso.mount')
    @patch('import_iso.read_enminst_config')
    def test_upgrade_applications_iso_only(self,
                                           m_read_enminst_config, m_mount,
                                           m_umount, m_create_mnt_dir,
                                           m_get_log):
        self.tmpdir = join(gettempdir(), 'temper')

        new_rhel7_image = 'ERICrhel79lsbimage_CXP9041915-1.9.1.qcow2'
        new_rhel7_jbossimage = 'ERICrhel79jbossimage_CXP9041916-1.9.1.qcow2'

        try:
            if isdir(self.tmpdir):
                shutil.rmtree(self.tmpdir)
            m_create_mnt_dir.return_value = self.tmpdir
            makedirs(join(self.tmpdir, 'images', 'ENM'))
            touch(join(self.tmpdir, 'images', 'ENM', new_rhel7_jbossimage))
            touch(join(self.tmpdir, 'images', 'ENM', new_rhel7_image))
            self.workingcfg = join(self.tmpdir, "enminst_working.cfg")
            with open(self.workingcfg, 'w') as _writer:
                _writer.writelines([
                    'ERICrhel79jbossimage='
                    'ERICrhel79jbossimage_CXP9041916-1.0.1.qcow2\n',
                    'ERICrhel7baseimage='
                    'ERICrhel79lsbimage_CXP9041915-1.0.1.qcow2\n'
                ])

            test_working_cfg = {
                'enminst_working_parameters': self.workingcfg
            }

            m_read_enminst_config.return_value = test_working_cfg

            upgrader = self.upgrade_enm.ENMUpgrade()
            setup_litp_mocks(
                    upgrader.litp, [
                        [
                            'GET',
                            self.mock_modeled_images(('ENM', [
                                ('rhel7-jboss-image',
                                 'ERICrhel79jbossimage_CXP9041916-1.0.1.qcow2'),
                                ('rhel7-lsb-image',
                                 'ERICrhel79lsbimage_CXP9041915-1.0.1.qcow2'),
                            ])),
                            httplib.OK
                        ], [
                            'PUT', dumps({}), httplib.OK
                        ], [
                            'PUT', dumps({}), httplib.OK
                        ]
                    ]
            )

            upgrader.config = test_working_cfg
            upgrader.import_enm_iso_for_upgrade = MagicMock()
            upgrader.upgrade_applications(Namespace(enm_iso='blaaaaaaa',
                                                    model_xml=None))

            if not upgrader.litp.get_https_connection().was_all_called():
                er = upgrader.litp.get_https_connection().expected_responses
                self.fail('Not all http requests called {0}'.format(er))

            with open(self.workingcfg, 'r') as _reader:
                data = _reader.readlines()

            self.assertEqual(3, len(data))

            self.assertIn('{0}={1}'.format(new_rhel7_image.split('_')[0],
                                           new_rhel7_image),
                          '\n'.join(data))

            self.assertIn('{0}={1}'.format(new_rhel7_jbossimage.split('_')[0],
                                           new_rhel7_jbossimage),
                          '\n'.join(data))

        finally:
            if isdir(self.tmpdir):
                shutil.rmtree(self.tmpdir)

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.validate_snapshots')
    @patch('upgrade_enm.manage_snapshots')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot_fails(self,
                                    m_verify_dd_expanding_nodes,
                                    m_nas_type,
                                    m_neo4j_uplift,
                                    m_unity_updates,
                                    m_validate_enm_deployment_xml,
                                    m_neo4j_pre_check,
                                    m_log_cmdline_args,
                                    m_prepare_runtime_config,
                                    m_enable_serialport_service,
                                    m_exec_healthcheck,
                                    m_infrastructure_changes,
                                    m_exec_process,
                                    m_check_any_snapshots_exist,
                                    m_manage_snapshots,
                                    m_validate_snapshots,
                                    m_subparams,
                                    check_upgrade_hw_provisions,
                                    m_create_xml_diff_file,
                                    m_create_removed_blades_info_file,
                                    m_verify_gossip_router_upgrade,
                                    m_verify_dd_not_reducing_nodes,
                                    enable_puppet_on_nodes,
                                    m_check_postgres_uplift_requirements):
        m_nas_type.return_value = 'veritas'
        m_exec_process.return_value = 'Hewlett-Packard'
        m_check_any_snapshots_exist.return_value = False
        m_validate_snapshots.side_effect = SanApiException

        args = '{0}{1}{2}{3}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option(),
                self.add_model_xml_option(),
                self.add_sed_option()
        )

        se = assert_exception_raised(SystemExit, self.upgrade_enm.main,
                                     args.split())
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertEquals(se.code, ExitCodes.INVALID_SNAPSHOTS)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(m_enable_serialport_service.called)
        self.assertTrue(m_exec_healthcheck.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_check_any_snapshots_exist.called)
        self.assertTrue(m_manage_snapshots.called)
        self.assertTrue(m_validate_snapshots.called)
        self.assertFalse(isfile(self.snapshots_indicator_filename))

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot_some_snapshots_exists(
            self,
            m_verify_dd_expanding_nodes,
            m_unity_updates,
            m_neo4j_uplift,
            m_validate_enm_deployment_xml,
            m_neo4j_pre_check,
            m_log_cmdline_args,
            m_exec_process,
            m_enable_serialport_service,
            m_exec_healthcheck,
            m_prepare_runtime_config,
            m_infrastructure_changes,
            m_checkanysnapshotsexist,
            m_subparams,
            check_upgrade_hw_provisions,
            m_create_xml_diff_file,
            m_create_removed_blades_info_file,
            m_verify_gossip_router_upgrade,
            m_verify_dd_not_reducing_nodes,
            enable_puppet_on_nodes,
            m_check_postgres_uplift_requirements):
        m_exec_process.return_value = 'Hewlett-Packard'
        m_checkanysnapshotsexist.return_value = True
        args = '{0}{1}{2}{3}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                     self.add_os_patch_option(),
                                     self.add_model_xml_option(),
                                     self.add_sed_option())

        se = assert_exception_raised(SystemExit, self.upgrade_enm.main,
                                     args.split())
        self.assertEquals(se.code, ExitCodes.ERROR)

        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(m_enable_serialport_service.called)
        self.assertTrue(m_exec_healthcheck.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_checkanysnapshotsexist.called)

    @patch('clean_san_luns.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_reboot_required')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.apply_os_patches')
    @patch('upgrade_enm.SanCleanup.get_san_info')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot_cloud_san_info_missing(
            self, m_verify_dd_expanding_nodes,
            m_unity_updates, m_neo4j_uplift,
            m_validate_enm_deployment_xml,
            m_neo4j_pre_check, m_vcs, m_postgres,
            m_log_cmdline_args, m_prepare_runtime_config,
            enable_serialport_service, exec_healthcheck,
            m_infrastructure_changes,
            m_exec_process, m_get_san_info,
            m_apply_os_patches,
            m_subparams,
            check_upgrade_hw_provisions,
            u_execute_post_upgrade_steps,
            m_create_xml_diff_file,
            m_create_removed_blades_info_file,
            m_get_cxp_values,
            m_verify_dd_not_reducing_nodes,
            enable_puppet_on_nodes,
            m_verify_gossip_router_upgrade,
            m_check_postgres_uplift_requirements,
            m_check_reboot_required,
            m_get_nas_type):
        m_check_reboot_required.return_value = True
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        m_exec_process.return_value = 'QEMU'
        m_get_san_info.return_value = []

        args = '{0}{1}{2}{3}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option(),
                self.add_model_xml_option(),
                self.add_sed_option())
        self.upgrade_enm.main(args.split())

        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_get_san_info.called)
        self.assertTrue(m_apply_os_patches.called)

    @patch('clean_san_luns.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_reboot_required')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.apply_os_patches')
    @patch('upgrade_enm.manage_snapshots')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.SanCleanup.get_san_info')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot_cloud_with_san_info(
            self,m_verify_dd_expanding_nodes,
            m_unity_updates, m_neo4j_uplift,
            m_validate_enm_deployment_xml,
            m_neo4j_pre_check, m_vcs, m_postgres,
            m_log_cmdline_args, m_prepare_runtime_config,
            enable_serialport_service,
            exec_healthcheck, m_infrastructure_changes,
            m_exec_process, m_get_san_info,
            m_check_any_snapshots_exist,
            m_manage_snapshots,
            m_apply_os_patches,
            m_subparams,
            check_upgrade_hw_provisions,
            u_execute_post_upgrade_steps,
            m_create_xml_diff_file,
            m_create_removed_blades_info_file,
            m_get_cxp_values,
            m_verify_dd_not_reducing_nodes,
            enable_puppet_on_nodes,
            m_verify_gossip_router_upgrade,
            m_check_postgres_uplift_requirements,
            m_check_reboot_required,
            m_get_nas_type):
        m_get_nas_type.return_value = ''
        m_check_reboot_required.return_value = True
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        m_exec_process.return_value = 'VMWare Inc.'
        m_get_san_info.return_value = [{'key': 'value'}]
        m_check_any_snapshots_exist.return_value = False
        args = '{0}{1}{2}{3}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option(),
                self.add_model_xml_option(),
                self.add_sed_option())
        self.upgrade_enm.main(args.split())

        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_get_san_info.called)
        self.assertTrue(m_manage_snapshots.called)
        self.assertTrue(m_apply_os_patches.called)

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_reboot_required')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.HealthCheck.enminst_healthcheck')
    @patch('upgrade_enm.HealthCheck.pre_checks')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.apply_os_patches')
    @patch('upgrade_enm.manage_snapshots')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot_continue(self,
                                       m_verify_dd_expanding_nodes,
                                       m_unity_updates,
                                       m_neo4j_uplift,
                                       m_validate_enm_deployment_xml,
                                       m_neo4j_pre_check,
                                       m_vcs,
                                       m_postgres,
                                       m_log_cmdline_args,
                                       m_prepare_runtime_config,
                                       m_infrastructure_changes,
                                       m_exec_process,
                                       m_manage_snapshots,
                                       m_apply_os_patches,
                                       m_subparams,
                                       check_upgrade_hw_provisions,
                                       m_healthcheck_pre_checks,
                                       m_enable_serialport_service,
                                       m_healthcheck_enminst_healthcheck,
                                       u_execute_post_upgrade_steps,
                                       m_create_xml_diff_file,
                                       m_create_removed_blades_info_file,
                                       m_get_cxp_values,
                                       m_verify_dd_not_reducing_nodes,
                                       enable_puppet_on_nodes,
                                       m_verify_gossip_router_upgrade,
                                       m_check_postgres_uplift_requirements,
                                       m_check_reboot_required,
                                       m_nas_type):
        m_check_reboot_required.return_value = True
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        m_exec_process.return_value = 'Hewlett-Packard'
        m_nas_type.return_value = ''

        touch(self.snapshots_indicator_filename)

        args = '{0}{1}{2}{3}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option(),
                self.add_model_xml_option(),
                self.add_sed_option())
        self.upgrade_enm.main(args.split())

        self.assertTrue(m_healthcheck_pre_checks.called)
        self.assertTrue(m_enable_serialport_service.called)
        self.assertTrue(m_healthcheck_enminst_healthcheck.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_manage_snapshots.called)
        self.assertTrue(m_apply_os_patches.called)

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.HealthCheck.enminst_healthcheck')
    @patch('upgrade_enm.HealthCheck.pre_checks')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.validate_snapshots')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_prepare_snapshot_continue_fails(self,
                                             m_verify_dd_expanding_nodes,
                                             m_nas_type,
                                             m_need_uplift,
                                             m_unity_updates,
                                             m_validate_enm_deployment_xml,
                                             m_neo4j_pre_check,
                                             m_vcs,
                                             m_postgres,
                                             m_log_cmdline_args,
                                             m_exec_process,
                                             m_prepare_runtime_config,
                                             m_infrastructure_changes,
                                             m_validate_snapshots,
                                             m_subparams,
                                             check_upgrade_hw_provisions,
                                             m_healthcheck_pre_checks,
                                             m_enable_serialport_service,
                                             m_enminst_healthcheck,
                                             m_create_xml_diff_file,
                                             m_create_removed_blades_info_file,
                                             m_verify_gossip_router_upgrade,
                                             m_verify_dd_not_reducing_nodes,
                                             enable_puppet_on_nodes,
                                             m_check_postgres_uplift_requirements,
                                             m_healthcheck_nas_type):
        m_nas_type.return_value = 'veritas'
        m_healthcheck_nas_type.return_value = ''
        m_exec_process.return_value = 'Hewlett-Packard'
        touch(self.snapshots_indicator_filename)
        m_validate_snapshots.side_effect = SanApiException
        m_nas_type.return_value = ''

        args = '{0}{1}{2}{3}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option(),
                self.add_model_xml_option(),
                self.add_sed_option())

        se = assert_exception_raised(SystemExit, self.upgrade_enm.main,
                                     args.split())
        self.assertEquals(se.code, ExitCodes.INVALID_SNAPSHOTS)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_validate_snapshots.called)
        self.assertTrue(m_healthcheck_pre_checks.called)
        self.assertTrue(m_enable_serialport_service.called)
        self.assertTrue(m_enminst_healthcheck.called)

    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_reboot_required')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.remove_rpm')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('tarfile.open')
    @patch('h_util.h_utils.RHELUtil.is_latest_version')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('os.makedirs')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_main_os_patches(self,
                             m_verify_dd_expanding_nodes,
                             m_check_celery,
                             m_unity_updates,
                             m_need_uplift,
                             m_vcs,
                             m_postgres,
                             m_makdirs,
                             m_log_cmdline_args,
                             m_update_rhel_version_and_history,
                             m_install_rpm,
                             m_prepare_runtime_config,
                             enable_serialport_service,
                             exec_healthcheck,
                             m_infrastructure_changes,
                             m_prepare_snapshot,
                             m_check_latest,
                             m_tarfile,
                             m_exec_process_via_pipes,
                             m_exec_process,
                             m_get_current_version,
                             m_ensure_version_manifest,
                             m_ensure_version_symlink,
                             locate_packages,
                             m_subparams,
                             check_upgrade_hw_provisions,
                             mktmp,
                             u_execute_post_upgrade_steps,
                             m_get_cxp_values,
                             m_create_xml_diff_file,
                             m_create_removed_blades_info_file,
                             remove_rpm,
                             m_verify_gossip_router_upgrade,
                             m_verify_dd_not_reducing_nodes,
                             m_validate_enm_deployment_xml,
                             enable_puppet_on_nodes,
                             m_check_postgres_uplift_requirements,
                             m_check_reboot_required,
                             remove_deployment_description_file):
        m_check_reboot_required.return_value = True
        m_check_rhel_latest = True
        m_get_current_version.return_value = '7.9'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', ]
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' +\
                                                '"cxp": "9041797"'
        locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'

        args = '{0}{1}{2}{3}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option(),
                self.add_model_xml_option(),
                self.add_sed_option())
        args += ' --noreboot'
        instance = self.upgrade_enm.ENMUpgrade()

        self.upgrade_enm.main(args.split())
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(m_subparams.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_prepare_runtime_config.called)
        self.assertTrue(m_infrastructure_changes.called)
        self.assertTrue(m_prepare_snapshot.called)
        self.assertTrue(mktmp.called)
        self.assertTrue(m_tarfile.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(locate_packages.called)

    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_version.display')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.harden_neo4j')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('crypto_service.crypto_service')
    def test_main_os_patches_ms_patched(self,
                                        crypto_service,
                                        m_nas_type,
                                        m_neo4j_uplift,
                                        m_harden_neo4j,
                                        m_neo4j_pre_check,
                                        m_vcs,
                                        m_postgres,
                                        m_cleanup_java_core_dumps_cron,
                                        m_log_cmdline_args,
                                        enable_serialport_service,
                                        exec_healthcheck,
                                        m_prepare_snapshot,
                                        litp_upgrade_deployment,
                                        create_run_plan,
                                        switch_db,
                                        m_litp_backup_state_cron,
                                        enm_version,
                                        m_get_cxp_values,
                                        m_verify_gossip_router_upgrade,
                                        m_verify_dd_not_reducing_nodes,
                                        m_create_san_fault_check_cron,
                                        m_enable_puppet_on_nodesi,
                                        m_create_nasaudit_errorcheck_cron,
                                        m_check_postgres_uplift_requirements,
                                        m_remove_deployment_description_file):
        m_nas_type.return_value = 'veritas'
        touch(self.ms_patched_done_file)
        m_get_cxp_values.side_effect = ['9041797', '9043482']

        with open(self.ms_patched_done_file, 'a') as pf:
            pf.write('patch_with_CXP9041797\n')
            pf.write('patch_with_CXP9043482\n')

        args = '{0}{1}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option())

        self.upgrade_enm.main(args.split())
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(m_prepare_snapshot.called)
        self.assertTrue(litp_upgrade_deployment.called)
        self.assertTrue(create_run_plan.called)
        self.assertTrue(switch_db.called)
        self.assertTrue(m_litp_backup_state_cron.called)
        self.assertTrue(enm_version.called)
        self.assertTrue(m_cleanup_java_core_dumps_cron.called)
        self.assertTrue(m_create_san_fault_check_cron.called)
        self.assertTrue(m_create_nasaudit_errorcheck_cron.called)
        self.assertTrue(crypto_service.called)

    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('upgrade_enm.install_rpm')
    @patch('enm_version.display')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('os.makedirs')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    @patch('crypto_service.crypto_service')
    def test_main_os_patches_ms_patched_one(self,
                                            crypto_service,
                                            m_check_celery,
                                            m_nas_type,
                                            m_need_uplift,
                                            m_neo4j_pre_check,
                                            m_vcs,
                                            m_postgres,
                                            m_makedirs,
                                            m_log_cmdline_args,
                                            enable_serialport_service,
                                            exec_healthcheck,
                                            m_prepare_snapshot,
                                            litp_upgrade_deployment,
                                            create_run_plan,
                                            switch_db,
                                            m_litp_backup_state_cron,
                                            m_cleanup_java_core_dumps_cron,
                                            enm_version,
                                            m_install_rpm,
                                            m_exec_process_via_pipes,
                                            m_exec_process,
                                            m_locate_packages,
                                            mktmp,
                                            m_get_cxp_values,
                                            m_create_san_fault_check_cron,
                                            m_create_nasaudit_errorcheck_cron,
                                            m_verify_gossip_router_upgrade,
                                            m_check_postgres_uplift_requirements,
                                            m_remove_deployment_description_file):
        m_nas_type.return_value = 'veritas'
        touch(self.ms_patched_done_file)

        with open(self.ms_patched_done_file, 'a') as pf:
            pf.write('patch_with_CXP9041797\n')
            pf.write('patch_with_CXP9043482\n')

        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        m_exec_process.return_value = 'rpm_path'
        m_exec_process_via_pipes.return_value = '"rhel_version": ' +\
                                                '"7.9" "cxp": "9041797"'
        m_get_cxp_values.side_effect = ['9041797', '9043482']

        args = '{0}{1}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option())

        self.upgrade_enm.main(args.split())

    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('tarfile.open')
    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('enm_version.display')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    @patch('crypto_service.crypto_service')
    def test_main_os_patches_ms_patched_one_prev(self,
                                                 crypto_service,
                                                 m_check_celery,
                                                 m_nas_type,
                                                 m_neo4j_uplift,
                                                 m_neo4j_pre_check,
                                                 m_vcs,
                                                 m_postgres,
                                                 m_log_cmdline_args,
                                                 enable_serialport_service,
                                                 exec_healthcheck,
                                                 m_prepare_snapshot,
                                                 litp_upgrade_deployment,
                                                 create_run_plan,
                                                 switch_db,
                                                 m_litp_backup_state_cron,
                                                 m_cleanup_java_core_dumps_cron,
                                                 enm_version,
                                                 m_exec_process_via_pipes,
                                                 m_exec_process,
                                                 m_locate_packages,
                                                 mktmp,
                                                 m_tar,
                                                 m_get_cxp_values,
                                                 m_create_san_fault_check_cron,
                                                 enable_puppet_on_nodes,
                                                 m_create_nasaudit_errorcheck_cron,
                                                 m_verify_gossip_router_upgrade,
                                                 m_check_postgres_uplift_requirements,
                                                 m_remove_deployment_description_file):
        m_nas_type.return_value = 'veritas'
        touch(self.ms_patched_done_file)

        with open(self.ms_patched_done_file, 'a') as pf:
            pf.write('patch_with_CXP9041797\n')

        m_tar.return_value.getnames.return_value = ['package1',
                              'RHEL_OS_Patch_Set_CXP9041797.rpm']
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": ' +\
                                                '"7.9" "cxp": "9041797"'
        m_get_cxp_values.side_effect = ['9041797', '9043482']

        args = '{0}{1}'.format(
                CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                self.add_os_patch_option())

        self.upgrade_enm.main(args.split())

    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('h_util.h_utils.touch')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.image_version_cfg')
    @patch('upgrade_enm.EnmLmsHouseKeeping')
    @patch('enm_version.display')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.update_model_vm_images')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('import_iso.main_flow')
    @patch('import_iso.umount')
    @patch('import_iso_version.handle_litp_version_history')
    @patch('import_iso.litp_import_iso')
    @patch('import_iso.mount')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('crypto_service.crypto_service')
    def test_main_litp_upgrade(self,
                               crypto_service,
                               m_nas_type,
                               m_neo4j_uplift,
                               m_neo4j_pre_check,
                               m_vcs,
                               m_postgres,
                               m_log_cmdline_args,
                               enable_serialport_service,
                               exec_healthcheck,
                               m_prepare_snapshot,
                               mount,
                               litp_import_iso,
                               m_handle_litp_version_history,
                               umount,
                               import_iso_main_flow,
                               litp_upgrade_deployment,
                               update_model_vm_images,
                               create_run_plan,
                               switch_db,
                               m_litp_backup_state_cron,
                               m_cleanup_java_core_dumps_cron,
                               enm_version,
                               doyler,
                               m_image_version_cfg,
                               m_create_removed_blades_info_file,
                               m_get_cxp_values,
                               m_touch,
                               m_san_fault_check_cron,
                               m_enable_puppet_on_nodes,
                               m_create_nasaudit_errorcheck_cron,
                               m_verify_gossip_router_upgrade,
                               m_check_postgres_uplift_requirements,
                               m_remove_deployment_description_file):
        m_nas_type.return_value = 'veritas'
        args = CMD_UPGRADE_ENM_DEFAULT_OPTIONS \
               + self.add_litp_upgrade_option() \
               + self.add_iso_option()

        m_get_cxp_values.side_effect = ['9041797', '9043482']

        self.upgrade_enm.main(args.split())
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(m_prepare_snapshot.called)
        self.assertTrue(mount.called)
        self.assertTrue(litp_import_iso.called)
        self.assertTrue(m_handle_litp_version_history.called)
        self.assertTrue(umount.called)
        self.assertTrue(import_iso_main_flow.called)
        self.assertTrue(litp_upgrade_deployment.called)
        self.assertTrue(m_image_version_cfg.called)
        self.assertTrue(update_model_vm_images.called)
        self.assertTrue(create_run_plan.called)
        self.assertTrue(switch_db.called)
        self.assertTrue(m_litp_backup_state_cron.called)
        self.assertTrue(enm_version.called)
        self.assertTrue(m_cleanup_java_core_dumps_cron.called)
        self.assertTrue(m_san_fault_check_cron.called)
        self.assertTrue(m_create_nasaudit_errorcheck_cron.called)
        doyler.assert_has_calls([
            call().housekeep_images(ANY),
            call().housekeep_yum(ANY)
        ], any_order=True)
        self.assertTrue(crypto_service.called)

    @patch('upgrade_enm.migrate_cleanup_cmd')
    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.deploy_neo4j_uplift_config')
    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.EnmLmsHouseKeeping')
    @patch('upgrade_enm.ENMUpgrade.image_version_cfg')
    @patch('upgrade_enm.copy_file')
    @patch('enm_version.display')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.load_xml')
    @patch('substitute_parameters.substitute')
    @patch('encrypt_passwords.encrypt')
    @patch('upgrade_enm.ENMUpgrade.update_ms_uuid')
    @patch('upgrade_enm.ENMUpgrade.update_ssh_key')
    @patch('upgrade_enm.ENMUpgrade.remove_items_from_model')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('import_iso.main_flow')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.process_arguments')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('upgrade_enm.ENMUpgrade.power_on_new_blades')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.harden_neo4j')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('crypto_service.crypto_service')
    def test_main(self,
                  crypto_service,
                  m_nas_type,
                  m_neo4j_uplift,
                  m_unity_updates,
                  m_validate_enm_deployment_xml,
                  m_harden_neo4j,
                  m_neo4j_pre_check,
                  m_vcs,
                  m_postgres,
                  m_power_on_new_blades,
                  m_log_cmdline_args,
                  enable_serialport_service,
                  exec_healthcheck,
                  infrastructure_changes,
                  process_arguments,
                  m_prepare_snapshot,
                  import_iso_main_flow,
                  litp_upgrade_deployment,
                  remove_items_from_model,
                  update_ssh_key,
                  update_ms_uuid,
                  encrypt_passwords,
                  substitute,
                  load_xml,
                  create_run_plan,
                  switch_db,
                  m_litp_backup_state_cron,
                  m_cleanup_java_core_dumps_cron,
                  enm_version,
                  cp_file,
                  m_image_version_cfg,
                  doyler,
                  check_upgrade_hw_provisions,
                  m_create_xml_diff_file,
                  create_removed_blades_info_file,
                  m_get_cxp_values,
                  m_verify_gossip_router_upgrade,
                  m_verify_dd_not_reducing_nodes,
                  m_san_fault_check_cron,
                  m_enable_puppet_on_nodes,
                  m_create_nasaudit_errorcheck_cron,
                  deploy_neo4j_uplift_config,
                  m_check_postgres_uplift_requirements,
                  m_remove_deployment_description_file,
                  m_migrate_cleanup_cmd):
        m_nas_type.return_value = 'veritas'
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        args = CMD_UPGRADE_ENM_DEFAULT_OPTIONS \
               + self.add_iso_option() + self.add_model_xml_option() + \
               self.add_sed_option()
        self.upgrade_enm.main([a for a in args.split(' ') if a])
        self.assertTrue(m_power_on_new_blades.called)
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(check_upgrade_hw_provisions.called)
        self.assertTrue(m_validate_enm_deployment_xml.called)
        self.assertTrue(m_create_xml_diff_file.called)
        self.assertTrue(infrastructure_changes.called)
        self.assertTrue(cp_file.called)
        self.assertTrue(process_arguments.called)
        self.assertTrue(m_prepare_snapshot.called)
        self.assertTrue(import_iso_main_flow.called)
        self.assertTrue(update_ms_uuid.called)
        self.assertTrue(deploy_neo4j_uplift_config.called)
        self.assertTrue(crypto_service.called)
        self.assertTrue(encrypt_passwords.called)
        self.assertTrue(substitute.called)
        self.assertTrue(load_xml.called)
        self.assertTrue(update_ssh_key.called)
        self.assertTrue(litp_upgrade_deployment.called)
        self.assertTrue(remove_items_from_model.called)
        self.assertTrue(create_run_plan.called)
        self.assertTrue(switch_db.called)
        self.assertTrue(m_litp_backup_state_cron.called)
        self.assertTrue(m_cleanup_java_core_dumps_cron.called)
        self.assertTrue(enm_version.called)
        self.assertTrue(m_image_version_cfg.called)
        self.assertTrue(m_san_fault_check_cron.called)
        self.assertTrue(m_create_nasaudit_errorcheck_cron.called)
        self.assertTrue(m_migrate_cleanup_cmd.called)
        doyler.assert_has_calls([
            call().housekeep_images(ANY),
            call().housekeep_yum(ANY)
        ], any_order=True)


    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch("upgrade_enm.ENMUpgrade.enable_puppet_on_nodes")
    @patch('upgrade_enm.check_package_installed', return_value=False)
    @patch("upgrade_enm.ENMUpgrade.persist_stage_data")
    @patch("upgrade_enm.ENMUpgrade.create_run_plan")
    @patch("upgrade_enm.ENMUpgrade.litp_upgrade_deployment")
    @patch("upgrade_enm.ENMUpgrade.prepare_snapshot")
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch("upgrade_enm.ENMUpgrade.enable_serialport_service")
    @patch("upgrade_enm.ENMUpgrade.exec_healthcheck")
    def test_rhel8_no_prev_patches(self, m_exec_healthcheck,
            enable_serialport_service,
            m_neo4j_uplift,
            m_prepare_snapshot,
            m_litp_upgrade_deployment,
            m_create_run_plan,
            m_persist_stage_data,
            m_check_package_installed,
            m_enable_puppet_on_nodes,
            m_verify_gossip_router_upgrade,
            m_check_postgres_uplift_requirements):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=False)
        instance.config['rhel8_release'] = self.rhel8_release_filename
        m_args = self.create_args_iso_sed_model()
        m_args.model_xml = None
        m_args.enm_iso = None

        instance.execute_standard_upgrade(m_args)
        self.assertTrue(m_exec_healthcheck.called)
        self.assertTrue(m_prepare_snapshot.called)
        self.assertTrue(m_litp_upgrade_deployment.called)
        self.assertTrue(m_create_run_plan.called)
        self.assertTrue(m_persist_stage_data.called)
        self.assertTrue(enable_serialport_service.called)

    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch("upgrade_enm.ENMUpgrade.persist_stage_data")
    @patch("upgrade_enm.ENMUpgrade.create_run_plan")
    @patch("upgrade_enm.ENMUpgrade.litp_upgrade_deployment")
    @patch("upgrade_enm.ENMUpgrade.prepare_snapshot")
    @patch("upgrade_enm.ENMUpgrade.exec_healthcheck")
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch("upgrade_enm.ENMUpgrade.enable_puppet_on_nodes")
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch("upgrade_enm.ENMUpgrade.check_postgres_uplift_req")
    def test_rhel6_missing_release_file(self,
            m_check_postgres_uplift_req,
            m_neo4j_uplift,
            m_enable_puppet_on_nodes,
            m_vcs, m_postgres,
            m_exec_healthcheck,
            m_prepare_snapshot,
            m_litp_upgrade_deployment,
            m_create_run_plan,
            m_persist_stage_data,
            m_verify_gossip_router_upgrade):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=False)
        m_args = self.create_args_iso_sed_model()
        m_args.model_xml = None
        m_args.enm_iso = None

        self.assertRaises(SystemExit,
                instance.execute_standard_upgrade, m_args)

    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch("upgrade_enm.check_package_installed", return_value=True)
    @patch("upgrade_enm.ENMUpgrade.persist_stage_data")
    @patch("upgrade_enm.ENMUpgrade.create_run_plan")
    @patch("upgrade_enm.ENMUpgrade.litp_upgrade_deployment")
    @patch("upgrade_enm.ENMUpgrade.prepare_snapshot")
    @patch("upgrade_enm.ENMUpgrade.exec_healthcheck")
    @patch("upgrade_enm.ENMUpgrade.enable_puppet_on_nodes")
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch("upgrade_enm.ENMUpgrade.check_postgres_uplift_req")
    def test_rhel7_missing_release_file(self,
            m_check_postgres_uplift_req,
            m_neo4j_uplift,
            m_enable_puppet_on_nodes,
            m_exec_healthcheck,
            m_prepare_snapshot,
            m_litp_upgrade_deployment,
            m_create_run_plan,
            m_persist_stage_data,
            m_check_package_installed,
            m_verify_gossip_router_upgrade):
        check_package_installed = MagicMock()
        check_package_installed.return_value = True
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=False)
        m_args = self.create_args_iso_sed_model()
        m_args.model_xml = None
        m_args.enm_iso = None

        self.assertRaises(SystemExit,
                instance.execute_standard_upgrade, m_args)

    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch("upgrade_enm.check_package_installed", return_value=True)
    @patch("upgrade_enm.ENMUpgrade.persist_stage_data")
    @patch("upgrade_enm.ENMUpgrade.create_run_plan")
    @patch("upgrade_enm.ENMUpgrade.litp_upgrade_deployment")
    @patch("upgrade_enm.ENMUpgrade.prepare_snapshot")
    @patch("upgrade_enm.ENMUpgrade.exec_healthcheck")
    @patch("upgrade_enm.ENMUpgrade.enable_puppet_on_nodes")
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch("upgrade_enm.ENMUpgrade.check_postgres_uplift_req")
    def test_rhel_invalid_json_release(self,
            m_check_postgres_uplift_req,
            m_neo4j_uplift,
            m_enable_puppet_on_nodes,
            m_exec_healthcheck,
            m_prepare_snapshot,
            m_litp_upgrade_deployment,
            m_create_run_plan,
            m_persist_stage_data,
            m_check_package_installed,
            m_verify_gossip_router_upgrade):
        check_package_installed = MagicMock()
        check_package_installed.return_value = True
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=False)
        m_args = self.create_args_iso_sed_model()
        m_args.model_xml = None
        m_args.enm_iso = None

        self.assertRaises(SystemExit,
                instance.execute_standard_upgrade, m_args)

    @patch('os.path.exists')
    @patch('h_xml.xml_validator.XMLValidator.validate')
    def test_validate_enm_deployment_xml_file_exists(self, m_validate_xml,
                                                     m_os_path_exists):
        instance = self.upgrade_enm.ENMUpgrade()
        m_os_path_exists.return_value = True
        instance.validate_enm_deployment_xml()
        self.assertTrue(m_validate_xml.called)

    @patch('os.path.exists')
    @patch('h_xml.xml_validator.XMLValidator.validate')
    def test_validate_enm_deployment_xml_file_not_exists(self, m_validate_xml,
                                                                    m_os_path_exists):
        instance = self.upgrade_enm.ENMUpgrade()
        m_os_path_exists.return_value = False
        instance.validate_enm_deployment_xml()
        self.assertFalse(m_validate_xml.called)

    @patch('os.path.exists')
    @patch('h_xml.xml_validator.XMLValidator.validate')
    def test_validate_enm_deployment_xml_exception_raised(self, m_validate_xml,
                                                     m_os_path_exists):
        instance = self.upgrade_enm.ENMUpgrade()
        m_os_path_exists.return_value = True
        m_validate_xml.side_effect = Exception()
        self.assertRaises(SystemExit, instance.validate_enm_deployment_xml)

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.copy_runtime_xml')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    def test_execute_standard_upgrade_validate_enm_deployment_xml_sys_exit_raised(self,
                                                           m_validate_enm_deployment_xml,
                                                           m_neo4j_uplift,
                                                           m_check_any_snapshots_exist,
                                                           m_copy_runtime_xml,
                                                           m_verify_dd_not_reducing_nodes,
                                                           m_verify_gossip_router_upgrade,
                                                           m_exec_healthcheck,
                                                           m_check_upgrade_hw_provisions,
                                                           m__handle_exec_process,
                                                           m_check_postgres_uplift_requirements):
        instance = self.upgrade_enm.ENMUpgrade()
        m_args = self.create_args_iso_sed_model()
        m_validate_enm_deployment_xml.side_effect = SystemExit(ExitCodes.ERROR)
        self.assertRaises(SystemExit, instance.execute_standard_upgrade, m_args)
        self.assertFalse(m_copy_runtime_xml.called)

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.persist_stage_data')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.upgrade_applications')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.check_db_node_removed')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.copy_runtime_xml')
    @patch('upgrade_enm.ENMUpgrade.copy_previous_xml')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    def test_validate_enm_deployment_xml_execute_standard_upgrade_xml_valid(self, m_unity_updates,
                                                                            m_neo4j_uplift,
                                                                            m_validate_enm_deployment_xml,
                                                                            m_check_any_snapshots_exist,
                                                                            m_copy_prev_xml,
                                                                            m_copy_runtime_xml,
                                                                            m_verify_dd_not_reducing_nodes,
                                                                            m_verify_gossip_router_upgrade,
                                                                            m_exec_healthcheck,
                                                                            m_check_upgrade_hw_provisions,
                                                                            m_prepare_runtime_config,
                                                                            m_sub_xml_params,
                                                                            m_create_xml_diff_file,
                                                                            m__handle_exec_process,
                                                                            m_check_db_node_removed,
                                                                            m_create_removed_blades_info_file,
                                                                            m_infrastructure_changes,
                                                                            m_prepare_snapshot,
                                                                            m_get_cxp_values,
                                                                            m_upgrade_applications,
                                                                            m_litp_upgrade_deployment,
                                                                            m_persist_stage_data,
                                                                            m_create_run_plan,
                                                                            m_check_postgres_uplift_requirements):
        instance = self.upgrade_enm.ENMUpgrade()
        m_args = self.create_args_iso_sed_model()
        m_args.litp_iso = None
        m_args.enm_iso = None
        m_args.os_patch = None
        m_args.regenerate_keys = None
        instance.execute_standard_upgrade(m_args)
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        instance.execute_standard_upgrade(m_args)
        self.assertTrue(m_validate_enm_deployment_xml.called)
        self.assertTrue(m_copy_runtime_xml.called)

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.check_db_node_removed')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.copy_runtime_xml')
    @patch('upgrade_enm.ENMUpgrade.copy_previous_xml')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    def test_create_xml_diff_failure_copy_xml(self, m_unity_updates,
                                                    m_neo4j_uplift,
                                                    m_validate_enm_deployment_xml,
                                                    m_check_any_snapshots_exist,
                                                    m_copy_prev_xml,
                                                    m_copy_runtime_xml,
                                                    m_verify_dd_not_reducing_nodes,
                                                    m_verify_gossip_router_upgrade,
                                                    m_exec_healthcheck,
                                                    m_check_upgrade_hw_provisions,
                                                    m_prepare_runtime_config,
                                                    m_sub_xml_params,
                                                    m_create_xml_diff_file,
                                                    m__handle_exec_process,
                                                    m_check_db_node_removed,
                                                    m_create_removed_blades_info_file,
                                                    m_infrastructure_changes,
                                                    m_check_postgres_uplift_requirements):
        instance = self.upgrade_enm.ENMUpgrade()
        m_args = self.create_args_iso_sed_model()
        m_create_xml_diff_file.side_effect = IOError
        self.assertRaises(IOError, instance.execute_standard_upgrade, m_args)
        self.assertTrue(m_copy_prev_xml.called)

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.persist_stage_data')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.upgrade_applications')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.check_db_node_removed')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.copy_runtime_xml')
    @patch('upgrade_enm.ENMUpgrade.copy_previous_xml')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    def test_execute_standard_upgrade_success_copy_xml(self, m_unity_updates,
                                                           m_neo4j_uplift,
                                                           m_validate_enm_deployment_xml,
                                                           m_check_any_snapshots_exist,
                                                           m_copy_prev_xml,
                                                           m_copy_runtime_xml,
                                                           m_verify_dd_not_reducing_nodes,
                                                           m_verify_gossip_router_upgrade,
                                                           m_exec_healthcheck,
                                                           m_check_upgrade_hw_provisions,
                                                           m_prepare_runtime_config,
                                                           m_sub_xml_params,
                                                           m_create_xml_diff_file,
                                                           m__handle_exec_process,
                                                           m_check_db_node_removed,
                                                           m_create_removed_blades_info_file,
                                                           m_infrastructure_changes,
                                                           m_prepare_snapshot,
                                                       m_get_cxp_values,
                                                       m_upgrade_applications,
                                                       m_litp_upgrade_deployment,
                                                       m_persist_stage_data,
                                                       m_create_run_plan,
                                                       m_check_postgres_uplift_requirements):
        instance = self.upgrade_enm.ENMUpgrade()
        m_args = self.create_args_iso_sed_model()
        m_args.litp_iso = None
        m_args.enm_iso = None
        m_args.os_patch = None
        m_args.regenerate_keys = None
        instance.execute_standard_upgrade(m_args)
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        self.assertTrue(m_copy_prev_xml.called)

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.upgrade_applications')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.check_db_node_removed')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.copy_runtime_xml')
    @patch('upgrade_enm.ENMUpgrade.copy_previous_xml')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.unity_model_updates')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.ENMUpgrade.upgrade_litp')
    def test_enm_litp_iso_not_copied_after_successful_infra_plan_and_failed_litp_plan(self,
                                                                               m_upgrade_litp,
                                                                               m_neo4j_uplift,
                                                                               m_unity_updates,
                                                                               m_validate_enm_deployment_xml,
                                                                               m_check_any_snapshots_exist,
                                                                               m_copy_prev_xml,
                                                                               m_copy_runtime_xml,
                                                                               m_verify_dd_not_reducing_nodes,
                                                                               m_verify_gossip_router_upgrade,
                                                                               m_exec_healthcheck,
                                                                               m_check_upgrade_hw_provisions,
                                                                               m_prepare_runtime_config,
                                                                               m_sub_xml_params,
                                                                               m_create_xml_diff_file,
                                                                               m__handle_exec_process,
                                                                               m_check_db_node_removed,
                                                                               m_create_removed_blades_info_file,
                                                                               m_infrastructure_changes,
                                                                               m_prepare_snapshot,
                                                                               m_get_cxp_values,
                                                                               m_upgrade_applications,
                                                                               m_litp_upgrade_deployment,
                                                                               m_create_run_plan,
                                                                               m_check_postgres_uplift_requirements):
        instance = self.upgrade_enm.ENMUpgrade()
        m_args = self.create_args_iso_sed_model()
        stage = "upgrade_plan"
        state = "failed"
        instance.persist_stage_data(stage, state)
        m_args.litp_iso = "litp_iso"
        m_args.enm_iso = None
        m_args.os_patch = None
        instance.execute_standard_upgrade(m_args)
        self.assertFalse(m_upgrade_applications.called)
        self.assertFalse(m_upgrade_litp.called)
        m_args = self.create_args_iso_sed_model()
        m_args.litp_iso = "litp_iso"
        m_args.enm_iso = None
        m_args.os_patch = None
        stage = "upgrade_plan"
        state = "start"
        instance.persist_stage_data(stage, state)
        instance.execute_standard_upgrade(m_args)
        self.assertTrue(m_upgrade_applications.called)
        self.assertTrue(m_upgrade_litp.called)

    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('upgrade_enm.ENMUpgrade.image_version_cfg')
    @patch('upgrade_enm.EnmLmsHouseKeeping')
    @patch('enm_version.display')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.update_model_vm_images')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('import_iso.main_flow')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.ENMUpgrade.process_arguments')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.harden_neo4j')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.get_nas_type')
    @patch('crypto_service.crypto_service')
    def test_main_without_sed(self,
                              crypto_service,
                              m_nas_type,
                              m_neo4j_uplift,
                              m_harden_neo4j,
                              m_neo4j_pre_check,
                              m_vcs,
                              m_postgres,
                              process_arguments,
                              m_log_cmdline_args,
                              enable_serialport_service,
                              exec_healthcheck,
                              m_prepare_snapshot,
                              import_iso_main_flow,
                              litp_upgrade_deployment,
                              update_model_vm_images,
                              create_run_plan,
                              switch_db,
                              m_litp_backup_state_cron,
                              m_cleanup_java_core_dumps_cron,
                              enm_version,
                              doyler,
                              m_image_version_cfg,
                              m_get_cxp_values,
                              m_create_san_fault_check_cron,
                              m_enable_puppet_on_nodesi,
                              m_create_nasaudit_errorcheck_cron,
                              m_verify_gossip_router_upgrade,
                              m_check_postgres_uplift_requirements,
                              remove_deployment_description_file):
        m_nas_type.return_value = 'veritas'
        args = CMD_UPGRADE_ENM_DEFAULT_OPTIONS + \
               self.add_iso_option()
        m_get_cxp_values.side_effect = ['9041797', '9043482']
        self.upgrade_enm.main([a for a in args.split(' ') if a])
        self.assertTrue(process_arguments.called)
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(m_prepare_snapshot.called)
        self.assertTrue(import_iso_main_flow.called)
        self.assertTrue(litp_upgrade_deployment.called)
        self.assertTrue(update_model_vm_images.called)
        self.assertTrue(create_run_plan.called)
        self.assertTrue(switch_db.called)
        self.assertTrue(m_litp_backup_state_cron.called)
        self.assertTrue(m_cleanup_java_core_dumps_cron.called)
        self.assertTrue(m_create_san_fault_check_cron.called)
        self.assertTrue(enm_version.called)
        self.assertTrue(m_image_version_cfg.called)
        self.assertTrue(m_create_nasaudit_errorcheck_cron.called)
        doyler.assert_has_calls([
            call().housekeep_images(ANY),
            call().housekeep_yum(ANY)
        ], any_order=True)
        self.assertTrue(crypto_service.called)

    def test_main_process_arguments_fails(self):
        args = 'upgrade_enm.sh -v' + \
               self.add_iso_option() + self.add_sed_option()
        self.assertRaises(SystemExit, self.upgrade_enm.main, args.split())

    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.ENMUpgrade.exec_healthcheck')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.ENMUpgrade.process_arguments')
    def test_main_execute_stages_fail(self,
                                      process_arguments,
                                      m_neo4j_uplift,
                                      m_log_cmdline_args,
                                      enable_serialport_service,
                                      exec_healthcheck,
                                      m_prepare_snapshot,
                                      enable_puppet_on_nodes,
                                      m_gossip_router_upgrade,
                                      m_check_postgres_uplift_requirements):

        m_prepare_snapshot.side_effect = SystemExit(ExitCodes.ERROR)
        args = '{0}{1}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                               self.add_iso_option())
        self.assertRaises(SystemExit, self.upgrade_enm.main, args.split())
        self.assertTrue(process_arguments.called)
        self.assertTrue(m_log_cmdline_args.called)
        self.assertTrue(enable_serialport_service.called)
        self.assertTrue(exec_healthcheck.called)
        self.assertTrue(m_prepare_snapshot.called)

    def create_args_iso_sed_model(self):
        class Args(object):
            verbose = True
            enm_iso = self.iso_filename
            model_xml = self.model_xml_filename
            sed_file = self.sed_filename
            regenerate_keys = False
            os_patch = None
            litp_iso = None
            disable_hc = False
            disable_hcs = None
            resume = False
            assumeyes = False
            rhel7_9_iso = None

        return Args

    def create_args_iso_only(self):
        class Args(object):
            verbose = True
            regenerate = True
            enm_iso = self.iso_filename
            sed_file = None

        return Args

    def create_args_rhel_iso_only(self):
        class Args(object):
            verbose = True
            enm_iso = self.iso_filename
            rhel7_9_iso = self.rhel7_9_iso_filename
        return Args

    def create_args_patch_iso_only(self, **kwargs):
        class Args(object):
            verbose = True
            enm_iso = self.iso_filename
            model_xml = self.model_xml_filename
            sed_file = self.sed_filename
            if kwargs and 'multiple_patch' in kwargs:
                os_patch = [self.os_patch_filename_rh8,
                            self.os_patch_filename_rh7]
            elif kwargs and 'multiple_patch_same' in kwargs:
                os_patch = [self.os_patch_filename_rh7,
                            self.os_patch_filename_rh7]
            else:
                os_patch = [self.os_patch_filename_rh7]
            noreboot = True

        return Args

    def create_args_litp_upgrade_only(self):
        class Args(object):
            verbose = True
            litp_iso = self.litp_iso_filename

        return Args

    def test_check_patch_without_model_returns_True(self):

        instance = self.upgrade_enm.ENMUpgrade()

        touch(self.ms_patched_done_file)
        with open(self.ms_patched_done_file, 'w') as f:
            f.write('patch_without_model')

        self.assertTrue(instance.check_patch_without_model())
        os.remove(self.ms_patched_done_file)

    def test_check_patch_without_model_returns_False(self):
        instance = self.upgrade_enm.ENMUpgrade()
        touch(self.ms_patched_done_file)
        with open(self.ms_patched_done_file, 'w') as f:
            f.write('wrongtext')
        self.assertFalse(instance.check_patch_without_model())
        os.remove(self.ms_patched_done_file)

    @patch('os.path.isdir')
    @patch('os.makedirs')
    @patch('upgrade_enm.import_iso.create_mnt_dir')
    @patch('upgrade_enm.import_iso.mount')
    @patch('upgrade_enm.exec_process')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('shutil.rmtree')
    @patch('upgrade_enm.import_iso.umount')
    @patch('upgrade_enm.import_iso.cleanup_mnt_points')
    def test_copy_rhel_os(self, m_cleanup_mnt, m_umount, m_rmtree, m_rhel_cur_ver,
                          m_rhel_sym, m_exec, m_mnt, m_mntdir, m_mkdirs, m_isdir):
        m_rhel_cur_ver.return_value = '7.9'
        m_isdir.side_effect = [False, True, True, True]
        m_mntdir.return_value = self.tmpdir
        m_exec.return_value = ''
        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_rhel_iso_only()
        instance.copy_rhel_os(args)
        m_exec.assert_has_calls(
                [call(['rsync', '-rtd', self.tmpdir + '/', '/var/www/html/7.9/os/x86_64']),
                 call(['createrepo', '-C', '/var/www/html/7.9/os/x86_64/Packages']),
                 call(['createrepo', '-C', '/var/www/html/7.9/updates/x86_64/Packages']),
                 call(['puppet', 'agent', '--disable'])])

        m_isdir.side_effect = [False, False]
        m_mkdirs.side_effect = OSError('Permission denied')
        self.assertRaises(SystemExit, instance.copy_rhel_os, args)

        m_exec.side_effect = [IOError('No such file or directory')]
        self.assertRaises(SystemExit, instance.copy_rhel_os, args)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp', return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_new_patches_available(
            self,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_puppet_exe,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_locate_packages,
            mktmp,
            remove_rpm):
        m_get_current_version.return_value = '7.9'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' +\
                                                '"cxp": "9041797"'
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.rhel_patch_cxps['8.8'] = '9043482'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        instance.check_reboot_required = MagicMock(return_value=False)
        args = self.create_args_patch_iso_only()
        ms_patched_done_file = os.path.join(
                os.environ['ENMINST_RUNTIME'], 'ms_os_patched')
        if os.path.isfile(ms_patched_done_file):
            os.remove(ms_patched_done_file)
        instance.apply_os_patches(args)
        self.assertTrue(os.path.isfile(ms_patched_done_file))
        self.assertTrue(m_tarfile.called)
        self.assertTrue(mktmp.called)
        m_exec_process.assert_has_calls(
                [call(['file', '-b', args.os_patch[0]]),
                 call(['find', '<function', '<lambda>', 'at',
                       mktmp.return_value.split()[-1] + '/RHEL/',
                       '-name', 'RHEL_OS_Patch_Set_CXP*']),
                 call(['/usr/bin/litp', 'import',
                       '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5',
                       '/var/www/html/7.9/updates/x86_64/Packages']),
                 call(['puppet', 'agent', '--disable']),
                 call(['yum', 'clean', 'all']),
                 call(['yum', '-y', '--disablerepo=*', '--enablerepo=UPDATES',
                       'upgrade']),
                 call(['puppet', 'agent', '--enable'])])
        self.assertTrue(m_update_rhel_version_and_history.called)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.get_rpm_info')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    @patch('upgrade_enm.glob')
    def test_apply_rhel8_patches_with_newer_litpcore(
            self,
            g_glob,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_puppet_exe,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_rpm_info,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_mktmp,
            remove_rpm):
        m_get_current_version.return_value = '8.8'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "8.8"' +\
                                                '"cxp": "9043482"'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel_patch_cxps['8.8'] = '9043482'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        instance.check_reboot_required = MagicMock(return_value=False)
        args = self.create_args_patch_iso_only(multiple_patch=True)
        ms_patched_done_file = os.path.join(
                os.environ['ENMINST_RUNTIME'], 'ms_os_patched')
        if os.path.isfile(ms_patched_done_file):
            os.remove(ms_patched_done_file)
        instance.valid_rhel_patch_versions = ('8.8')
        instance.vers_conf_key_map = {'8.8': 'rhel8'}
        instance.patch_rhel_ver = '8.8'
        instance.rhel8_ver = '8.8'
        instance.config['rhel8_os_patch_cxp_iso'] = '9043482'
        args.os_patch = ['/tmp/TestENMUpgrade/'
                         'rhel-oss-patches-19089-CXP9043482-A.iso']
        m_mktmp.return_value = '/tmp/tmpFpzzZP'
        g_glob.side_effect = [
            ['/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages'],
            ['/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages/']]
        m_get_rpm_info.return_value = {'version': '2.19.1'}
        instance.apply_os_patches(args)
        self.assertTrue(os.path.isfile(ms_patched_done_file))
        self.assertTrue(m_tarfile.called)
        self.assertTrue(m_mktmp.called)
        m_exec_process.assert_any_call((['/usr/bin/litp', 'import',
                       '/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages/',
                       '/var/www/html/8.8/updates_AppStream/x86_64/Packages'
                       ]))
        m_exec_process.assert_any_call((['file', '-b', args.os_patch[0]]))
        m_exec_process.assert_any_call((['find', '/tmp/tmpFpzzZP/RHEL/',
                                          '-name', 'RHEL_OS_Patch_Set_CXP*']))
        m_exec_process.assert_any_call((['/usr/bin/litp', 'import',
                       '/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages',
                       '/var/www/html/8.8/updates_BaseOS/x86_64/Packages']))
        m_exec_process.assert_any_call((['puppet', 'agent', '--disable']))
        m_exec_process.assert_any_call((['yum', 'clean', 'all']))
        m_exec_process.assert_any_call((['puppet', 'agent', '--enable']))
        self.assertTrue(m_update_rhel_version_and_history.called)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.get_rpm_info')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    @patch('upgrade_enm.glob')
    def test_apply_rhel8_patches_with_older_litpcore(
            self,
            g_glob,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_puppet_exe,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_rpm_info,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_mktmp,
            remove_rpm):
        m_get_current_version.return_value = '8.8'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "8.8"' +\
                                                '"cxp": "9043482"'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel_patch_cxps['8.8'] = '9043482'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        instance.check_reboot_required = MagicMock(return_value=False)
        args = self.create_args_patch_iso_only(multiple_patch=True)
        ms_patched_done_file = os.path.join(
                os.environ['ENMINST_RUNTIME'], 'ms_os_patched')
        if os.path.isfile(ms_patched_done_file):
            os.remove(ms_patched_done_file)
        instance.valid_rhel_patch_versions = ('8.8')
        instance.vers_conf_key_map = {'8.8': 'rhel8'}
        instance.patch_rhel_ver = '8.8'
        instance.rhel8_ver = '8.8'
        # instance.rhel_os_patch_rpms = ['8.8']
        instance.config['rhel8_os_patch_cxp_iso'] = '9043482'
        args.os_patch = ['/tmp/TestENMUpgrade/'
                         'rhel-oss-patches-19089-CXP9043482-A.iso']
        m_mktmp.return_value = '/tmp/tmpFpzzZP'
        g_glob.side_effect = [
            ['/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages'],
            ['/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages/']]
        m_get_rpm_info.return_value = {'version': '2.17.1'}
        instance.apply_os_patches(args)
        self.assertTrue(os.path.isfile(ms_patched_done_file))
        self.assertTrue(m_tarfile.called)
        self.assertTrue(m_mktmp.called)
        m_exec_process.assert_any_call((['rsync', '-rtd', '--delete-before',
                       '/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages/',
                       '/var/www/html/8.8/updates_AppStream/x86_64/Packages']))
        m_exec_process.assert_any_call((['file', '-b', args.os_patch[0]]))
        m_exec_process.assert_any_call((['find', '/tmp/tmpFpzzZP/RHEL/',
                                          '-name', 'RHEL_OS_Patch_Set_CXP*']))
        m_exec_process.assert_any_call((['/usr/bin/litp', 'import',
                       '/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages',
                       '/var/www/html/8.8/updates_BaseOS/x86_64/Packages']))
        m_exec_process.assert_any_call((['puppet', 'agent', '--disable']))
        m_exec_process.assert_any_call((['yum', 'clean', 'all']))
        m_exec_process.assert_any_call((['puppet', 'agent', '--enable']))
        self.assertTrue(m_update_rhel_version_and_history.called)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp',
            return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_no_new_patches_available(
            self,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_puppet_exe,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_locate_packages,
            mktmp,
            remove_rpm):
        m_get_current_version.return_value = '7.9'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' +\
                                                '"cxp": "9041797"'
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.check_for_os_patch_updates = MagicMock(return_value=False)
        instance.check_reboot_required = MagicMock(return_value=False)
        args = self.create_args_patch_iso_only()
        ms_patched_done_file = os.path.join(
                os.environ['ENMINST_RUNTIME'], 'ms_os_patched')
        if os.path.isfile(ms_patched_done_file):
            os.remove(ms_patched_done_file)
        instance.apply_os_patches(args)
        self.assertTrue(os.path.isfile(ms_patched_done_file))
        self.assertTrue(m_tarfile.called)
        self.assertTrue(mktmp.called)
        m_exec_process.assert_has_calls(
                [call(['file', '-b', self.os_patch_filename_rh7]),
                 call(['find', '<function', '<lambda>', 'at',
                       mktmp.return_value.split()[-1] + '/RHEL/',
                       '-name', 'RHEL_OS_Patch_Set_CXP*']),
                 call(['/usr/bin/litp', 'import',
                       '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5',
                       '/var/www/html/7.9/updates/x86_64/Packages']),
                 call(['puppet', 'agent', '--disable']),
                 call(['yum', 'clean', 'all']),
                 call(['puppet', 'agent', '--enable'])])
        self.assertFalse(call([
            'yum', '-y', '--disablerepo=*', '--enablerepo=UPDATES', 'upgrade']
        ) in m_exec_process.call_args_list)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp', return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait')
    @patch('os.makedirs')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_simple(
            self,
            m_check_celery,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_makedirs,
            m_puppet_exe,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_locate_packages,
            mktmp,
            remove_rpm):
        m_get_current_version.return_value = '7.9'
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' +\
                                                '"cxp": "9041797"'
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        instance.handle_reboot = MagicMock(return_value=None)
        instance.rhel_ver = '7.9'
        args = self.create_args_patch_iso_only()
        instance.apply_os_patches(args)
        self.assertTrue(m_tarfile.called)
        self.assertTrue(mktmp.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_update_rhel_version_and_history.called)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('litp.core.rpc_commands.PuppetExecutionProcessor.wait')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    @patch('upgrade_enm.glob')
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.import_iso.umount')
    @patch('upgrade_enm.import_iso.mount')
    @patch('upgrade_enm.get_rpm_info')
    def test_apply_multiple_os_patches_simple(
            self,
            m_get_rpm_info,
            m_mount,
            m_umount,
            m_locate_packages,
            g_glob,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_puppet_exe,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_mktmp,
            remove_rpm):
        m_get_rpm_info.return_value = {'version': '2.19.1'}
        m_locate_packages.side_effect = [
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5',
            ('/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages',
            '/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages')]
        m_get_current_version.side_effect = ['7.9', '8.8']
        m_exec_process.side_effect = cycle(['ISO 9660 CD-ROM filesystem data'])
        m_exec_process_via_pipes.side_effect = ['"rhel_version": "7.9"' +\
            '"cxp": "9041797"', '"rhel_version": "8.8""cxp": "9043482"']
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.handle_reboot = MagicMock(return_value=None)
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.rhel_patch_cxps['8.8'] = '9043482'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        instance.check_reboot_required = MagicMock(return_value=False)
        args = self.create_args_patch_iso_only(multiple_patch=True)
        ms_patched_done_file = os.path.join(
            os.environ['ENMINST_RUNTIME'], 'ms_os_patched')
        if os.path.isfile(ms_patched_done_file):
            os.remove(ms_patched_done_file)
        instance.valid_rhel_patch_versions = ('7.9', '8.8')
        instance.vers_conf_key_map = {'7.9': 'rhel7', '8.8': 'rhel8'}
        instance.rhel8_ver = '8.8'
        instance.rhel7_ver = '7.9'
        instance.config['rhel8_os_patch_cxp_iso'] = '9043482'
        instance.config['rhel7_os_patch_cxp_iso'] = '9041797'
        args.os_patch = ['/tmp/TestENMUpgrade/'
                         'rhel-oss-patches-19089-CXP9043482-A.iso',
                         'rhel-oss-patches-19089-CXP9041797-D.iso']
        m_mktmp.return_value = '/tmp/tmpFpzzZP'
        g_glob.side_effect = [
            ['/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages'],
            ['/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages']]
        instance.apply_os_patches(args)
        self.assertTrue(os.path.isfile(ms_patched_done_file))

        m_exec_process.assert_any_call(['/usr/bin/litp', 'import',
            '/tmp/tmpFpzzZP/RHEL/RHEL8.8_AppStream-1.0.8/Packages',
            '/var/www/html/8.8/updates_AppStream/x86_64/Packages'])
        m_exec_process.assert_any_call(['file', '-b', args.os_patch[0]])
        m_exec_process.assert_any_call(['file', '-b', args.os_patch[1]])
        m_exec_process.assert_any_call(['/usr/bin/litp', 'import',
            '/tmp/tmpFpzzZP/RHEL/RHEL8.8_BaseOS-1.0.8/Packages',
            '/var/www/html/8.8/updates_BaseOS/x86_64/Packages'])
        m_exec_process.assert_any_call(['puppet', 'agent', '--disable'])
        m_exec_process.assert_any_call(['yum', 'clean', 'all'])
        m_exec_process.assert_any_call(['puppet', 'agent', '--enable'])
        m_exec_process.assert_any_call(['/usr/bin/litp', 'import',
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5',
            '/var/www/html/7.9/updates/x86_64/Packages'])
        self.assertTrue(m_update_rhel_version_and_history.called)

        updates_repo_dir = '/var/www/html/{0}/updates/x86_64/Packages'\
            .format(instance.rhel7_ver)
        assert call(updates_repo_dir) in m_makedirs.mock_calls

        updates_repo_dir = '/var/www/html/{0}/updates/x86_64/Packages'\
            .format(instance.rhel8_ver)
        assert call(updates_repo_dir) not in m_makedirs.mock_calls

    @patch('upgrade_enm.import_iso.mount')
    @patch('upgrade_enm.import_iso.umount')
    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('filecmp.cmp')
    @patch('shutil.rmtree')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_invalid_simple(
            self,
            m_check_celery,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_rmtree,
            m_filecmp,
            m_exec_process_via_pipes,
            m_exec_process,
            m_locate_packages,
            mktmp,
            m_umount,
            m_mount):
        m_filecmp.return_value = False
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path']
        m_exec_process_via_pipes.return_value = ''
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'

        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only(multiple_patch=True)
        args.noreboot = False

        se = assert_exception_raised(SystemExit, instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)
        self.assertTrue(m_tarfile.called)
        self.assertTrue(mktmp.called)
        self.assertTrue(m_rmtree.called)


    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('filecmp.cmp')
    @patch('shutil.rmtree')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_invalid_format(
            self,
            m_check_celery,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_rmtree,
            m_filecmp,
            m_exec_process_via_pipes,
            m_exec_process,
            m_locate_packages,
            mktmp):
        m_filecmp.return_value = False
        m_exec_process.side_effect = ['ASCII English text',
                                      'rpm_path']
        m_exec_process_via_pipes.return_value = ''
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'

        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only(multiple_patch=True)
        args.noreboot = False

        se = assert_exception_raised(SystemExit, instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)

    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    def test_apply_os_patches_rhel7_9_not_copied(self,
                                       m_exec_process_via_pipes,
                                       m_exec_process,
                                       m_locate_packages):

        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' + \
                                                '"cxp": "9041797"'
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = False
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only()
        args.noreboot = False
        se = assert_exception_raised(SystemExit, instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)

    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    def test_apply_os_patches_rhel7_9_copied_wrong_patches(self,
                                                  m_exec_process_via_pipes,
                                                  m_exec_process,
                                                  m_locate_packages):

        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' + \
                                                '"cxp": "9041797"'
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only()
        args.noreboot = False
        se = assert_exception_raised(SystemExit, instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)


    @patch('upgrade_enm.ENMUpgrade._handle_exec_process',
            return_value='ASCII English text')
    def test_prev_apply_patches_invalid_format(
            self,
            m_exec_process):

        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_patch_iso_only(multiple_patch=True)
        args.noreboot = False

        os_patch_arg = ""

        se = assert_exception_raised(SystemExit, instance.patch_previously_applied,
                                     os_patch_arg)
        self.assertEquals(se.code, ExitCodes.ERROR)

    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('filecmp.cmp')
    @patch('shutil.rmtree')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_invalid_simple_alt(
            self,
            m_check_celery,
            m_vcs, m_postgres,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_rmtree,
            m_filecmp,
            m_exec_process_via_pipes,
            m_exec_process,
            m_locate_packages,
            mktmp):
        m_filecmp.return_value = False
        m_exec_process.return_value = 'gzip compressed data, from Unix'
        m_exec_process_via_pipes.return_value = ''
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'

        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only(multiple_patch=True)
        args.noreboot = False

        se = assert_exception_raised(SystemExit, instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)
        self.assertTrue(m_tarfile.called)
        self.assertTrue(mktmp.called)
        self.assertTrue(m_rmtree.called)

    @patch('upgrade_enm.mkdtemp',
           return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('shutil.rmtree')
    @patch('upgrade_enm.exec_process')
    @patch('tarfile.open')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_tar_fails(self,
                                        m_check_celery,
                                        m_tarfile,
                                        m_exec_process,
                                        m_rmtree,
                                        mktmp):
        m_rmtree.side_effect = OSError
        m_tarfile.side_effect = IOError
        m_exec_process.return_value = 'gzip compressed data, from Unix'
        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_patch_iso_only()

        se = assert_exception_raised(SystemExit, instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)
        self.assertTrue(m_tarfile.called)
        self.assertTrue(mktmp.called)
        self.assertTrue(m_rmtree.called)

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.mkdtemp',
               return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.isfile')
    @patch('os.access')
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_patch_config_script_nonexisting(
            self,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_locate_packages,
            m_access,
            m_isfile,
            mktmp,
            remove_rpm):
        m_get_current_version.return_value = '7.9'
        m_isfile.return_value = False
        m_access.return_value = False
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' +\
                                                '"cxp": "9041797"'
        m_locate_packages.return_value = \
            '/tmp/tmpFpzzZP/RHEL/RHEL7_9.z-3.0.5'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only()
        args.noreboot = True
        instance.apply_os_patches(args)
        self.assertFalse(call([
            '/tmp/tmpFpzzZP/RHEL/config_patches.sh']
        ) in m_exec_process.call_args_list)
        self.assertTrue(mktmp.called)


    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_check_RHEL_OS_Patch_Set_CXP9041797_version_bigger(self, m_exec_process):
        m_exec_process.side_effect = ['RHEL_OS_Patch_Set_CXP9041797.noarch                              1.14.2-1                               @/RHEL_OS_Patch_Set_CXP9041797-1.13.1-1.noarch',
                                      '', '']
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_and_reboot_celery()
        m_exec_process.assert_any_call("systemctl restart celery", 'Restarting Celery',
                'Restarting Celery has failed')
        m_exec_process.assert_any_call("systemctl restart celerybeat", 'Restarting Celerybeat',
                'Restarting Celerybeat has failed')

    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_check_RHEL_OS_Patch_Set_CXP9041797_version_equal(self, m_exec_process):
        m_exec_process.side_effect = [
            'RHEL_OS_Patch_Set_CXP9041797.noarch                              1.14.1-1                               @/RHEL_OS_Patch_Set_CXP9041797-1.13.1-1.noarch',
            '', '']
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_and_reboot_celery()
        m_exec_process.assert_any_call("systemctl restart celery", 'Restarting Celery',
                                         'Restarting Celery has failed')
        m_exec_process.assert_any_call("systemctl restart celerybeat", 'Restarting Celerybeat',
                                         'Restarting Celerybeat has failed')

    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_check_RHEL_OS_Patch_Set_CXP9041797_version_smaller(self, m_exec_process):
        m_exec_process.side_effect = [
            'RHEL_OS_Patch_Set_CXP9041797.noarch                              1.13.9-1                               @/RHEL_OS_Patch_Set_CXP9041797-1.13.1-1.noarch',
            '', '']
        instance = self.upgrade_enm.ENMUpgrade()
        instance.check_and_reboot_celery()
        m_exec_process.assert_has_calls([call('yum list RHEL_OS_Patch_Set_CXP9041797.noarch', 'Getting RHEL_OS_Patch_Set_CXP9041797',
            'Failed Getting RHEL_OS_Patch_Set_CXP9041797')])
        m_exec_process.assert_not_called("systemctl restart celery", 'Restarting Celery',
                                       'Restarting Celery has failed')
        m_exec_process.assert_not_called("systemctl restart celerybeat", 'Restarting Celerybeat',
                                       'Restarting Celerybeat has failed')

    @patch('upgrade_enm.remove_rpm')
    @patch('upgrade_enm.isfile')
    @patch('os.access')
    @patch('upgrade_enm.mkdtemp')
    @patch('upgrade_enm.ENMUpgrade.locate_packages')
    @patch('h_util.h_utils.RHELUtil.ensure_version_manifest')
    @patch('h_util.h_utils.RHELUtil.ensure_version_symlink')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    @patch('tarfile.open')
    @patch('upgrade_enm.install_rpm')
    @patch('upgrade_enm.import_iso_version.update_rhel_version_and_history')
    @patch('os.makedirs')
    @patch('upgrade_enm.ENMUpgrade.check_and_reboot_celery')
    def test_apply_os_patches_patch_config_script_existing(
            self,
            m_check_celery,
            m_makedirs,
            m_update_rhel_version_and_history,
            m_install_rpm,
            m_tarfile,
            m_exec_process_via_pipes,
            m_exec_process,
            m_get_current_version,
            m_ensure_rhel_version_symlink,
            m_ensure_rhel_version_manifest,
            m_locate_packages,
            m_mkdtemp,
            m_access,
            m_isfile,
            remove_rpm):
        m_get_current_version.return_value = '7.9'
        m_isfile.return_value = True
        m_access.return_value = True
        tempdir = '/tmp/tmpFpzzZP'
        m_mkdtemp.return_value = tempdir
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path', 'rpm_path',
                                      'rpm_path', 'rpm_path']
        m_exec_process_via_pipes.return_value = '"rhel_version": "7.9"' +\
                                                '"cxp": "9041797"'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.rhel7_9_copied = True
        instance.rhel_patch_cxps['7.9'] = '9041797'
        instance.check_for_os_patch_updates = MagicMock(return_value=True)
        args = self.create_args_patch_iso_only()
        args.noreboot = True
        instance.apply_os_patches(args)
        self.assertTrue(call([
            tempdir + '/RHEL/config_patches.sh'
        ]) in m_exec_process.call_args_list)

    @patch('upgrade_enm.exec_process')
    def test_check_for_os_patch_updates_with_updates_avail(self,
                                                           m_exec_process):
        m_exec_process.side_effect = IOError(100, 'yum yum', 'process')
        instance = self.upgrade_enm.ENMUpgrade()
        self.assertTrue(instance.check_for_os_patch_updates())

    @patch('upgrade_enm.mkdtemp',
               return_value=str(lambda x: mkdtemp(dir=self.tmpdir)))
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.exec_process_via_pipes')
    def test_get_patch_cxp_fail(self, m_exec_process_via_pipes,
                                m_exec_process,
                                mktmp):
        m_exec_process.side_effect = ['gzip compressed data, from Unix',
                                      'rpm_path', '"cxp": "9041797"']
        m_exec_process_via_pipes.side_effect = IOError
        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_patch_iso_only()
        se = assert_exception_raised(SystemExit,
                                     instance.apply_os_patches,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)

    @patch('upgrade_enm.exec_process')
    def test_check_for_os_patch_updates_with_no_updates_avail(
            self, m_exec_process):
        m_exec_process.return_value = 'no updates'
        instance = self.upgrade_enm.ENMUpgrade()
        self.assertFalse(instance.check_for_os_patch_updates())

    @patch('os.walk')
    def test_locate_packages_in_os_patch_folder(self, os_walk):
        os_walk.side_effect = walk_directories_for_os_patches
        unpacked_os_patches = '/tmp/tmpfJq19d'
        patch_rhel_ver = '7.9'
        enm_upgrade = self.upgrade_enm.ENMUpgrade()
        result = enm_upgrade.locate_packages(
                unpacked_os_patches, patch_rhel_ver)
        expected = '/'.join([unpacked_os_patches, 'RHEL', 'RHEL7_9.z-3.0.5',
                             'packages'])
        self.assertEquals(result, expected)

    @patch('upgrade_enm.glob')
    def test_locate_packages_in_rhel8_os_patch_folder(self, glob):
        glob.side_effect = [['/tmp/tmprhel8/RHEL/RHEL8.8_BaseOS-1.0.8/Packages'],
                            ['/tmp/tmprhel8/RHEL/RHEL8.8_AppStream-1.0.8/Packages']]
        unpacked_os_patches = '/tmp/tmprhel8'
        patch_rhel_ver = '8.8'
        enm_upgrade = self.upgrade_enm.ENMUpgrade()
        result_baseos, result_appstream = enm_upgrade.locate_packages(
                unpacked_os_patches, patch_rhel_ver)

        common_str = '/'.join([unpacked_os_patches, 'RHEL'])
        expected_baseos = '/'.join([common_str, 'RHEL8.8_BaseOS-1.0.8','Packages'])
        expected_appstream = '/'.join([common_str, 'RHEL8.8_AppStream-1.0.8','Packages'])

        self.assertEquals(result_baseos, expected_baseos)
        self.assertEquals(result_appstream, expected_appstream)

    @patch('os.listdir')
    def test_locate_packages_in_os_patch_folder_fail(self, list_dir):
        list_dir.return_value = ['ABC']
        unpacked_os_patches = '/var/tmp/unpacked_os_patches'
        patch_rhel_ver = '7.9'
        enm_upgrade = self.upgrade_enm.ENMUpgrade()
        self.assertRaises(ValueError,
                          enm_upgrade.locate_packages,
                          unpacked_os_patches,
                          patch_rhel_ver)
    @patch('upgrade_enm.glob')
    def test_locate_packages_in_rhel8_os_patch_folder_fail(self, glob):
        glob.side_effect = [[],
                            ['/tmp/tmprhel8/RHEL/RHEL8.8_AppStream-1.0.8/Packages']]
        unpacked_os_patches = '/tmp/tmprhel8'
        patch_rhel_ver = '8.8'
        enm_upgrade = self.upgrade_enm.ENMUpgrade()
        self.assertRaises(ValueError,
                          enm_upgrade.locate_packages,
                          unpacked_os_patches,
                          patch_rhel_ver)

    @patch('upgrade_enm.uname')
    @patch('upgrade_enm.exec_process')
    def test_check_reboot_required(self, m_exec_process, m_uname):
        rpm_query_results = \
            'kernel-2.6.32-504.12.2.el6.x86_64     ' \
            '        Thu 23 Jul 2015 12:05:45 IST\n' \
            'kernel-2.6.32-504.el6.x86_64          ' \
            '        Wed 22 Jul 2015 12:50:14 IST\n'
        uname_results = '2.6.32-504.el6.x86_64'
        m_uname.return_value = ('', '', uname_results, '', '', '')
        m_exec_process.side_effect = [rpm_query_results]
        instance = self.upgrade_enm.ENMUpgrade()
        self.assertTrue(instance.check_reboot_required())

    @patch('upgrade_enm.uname')
    @patch('upgrade_enm.exec_process')
    def test_check_reboot_required_false(self, m_exec_process, m_uname):
        rpm_query_results = \
            'kernel-2.6.32-504.el6.x86_64          ' \
            '        Wed 22 Jul 2015 12:50:14 IST\n'
        uname_results = '2.6.32-504.el6.x86_64'
        m_uname.return_value = ('', '', uname_results, '', '', '')
        m_exec_process.side_effect = [rpm_query_results]
        instance = self.upgrade_enm.ENMUpgrade()
        self.assertFalse(instance.check_reboot_required())
        self.assertTrue(m_uname.called)

    @patch('upgrade_enm.exec_process')
    def test_check_reboot_unable_to_determine_kernel(self, m_exec_process):
        rpm_query_results = ''
        uname_results = '2.6.32-504.el6.x86_64'
        m_exec_process.side_effect = [rpm_query_results, uname_results]
        instance = self.upgrade_enm.ENMUpgrade()
        self.assertTrue(instance.check_reboot_required())

    @patch('upgrade_enm.exec_process')
    def test_check_reboot_exec_process_fails(self, m_exec_process):
        m_exec_process.side_effect = IOError
        instance = self.upgrade_enm.ENMUpgrade()
        se = assert_exception_raised(SystemExit,
                                     instance.check_reboot_required)
        self.assertEquals(se.code, ExitCodes.ERROR)

    @patch('import_iso.umount')
    @patch('import_iso_version.handle_litp_version_history')
    @patch('import_iso.litp_import_iso')
    @patch('import_iso.mount')
    def test_upgrade_litp(self, mount, litp_import_iso,
                          m_handle_litp_version_history, umount):
        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_litp_upgrade_only()
        instance.upgrade_litp(args)
        self.assertTrue(mount.called)
        self.assertTrue(litp_import_iso.called)
        self.assertTrue(m_handle_litp_version_history.called)
        self.assertTrue(umount.called)

    @patch('import_iso.umount')
    @patch('import_iso_version.handle_litp_version_history')
    @patch('import_iso.litp_import_iso')
    @patch('import_iso.mount')
    def test_upgrade_litp_fails(self, mount, litp_import_iso,
                                m_handle_litp_version_history, umount):
        instance = self.upgrade_enm.ENMUpgrade()
        mount.side_effect = SystemExit(ExitCodes.ERROR)
        args = self.create_args_litp_upgrade_only()
        ex = assert_exception_raised(SystemExit, instance.upgrade_litp, args)
        self.assertEquals(ex.code, ExitCodes.ERROR)
        self.assertTrue(mount.called)
        self.assertFalse(litp_import_iso.called)
        self.assertFalse(m_handle_litp_version_history.called)
        self.assertTrue(umount.called)

    @patch('import_iso.umount')
    @patch('import_iso_version.handle_litp_version_history')
    @patch('import_iso.litp_import_iso')
    @patch('import_iso.mount')
    def test_upgrade_litp_keyboard_interrupted(self, mount, litp_import_iso,
                                               m_handle_litp_version_history,
                                               umount):
        instance = self.upgrade_enm.ENMUpgrade()
        litp_import_iso.side_effect = KeyboardInterrupt
        args = self.create_args_litp_upgrade_only()
        ex = assert_exception_raised(SystemExit, instance.upgrade_litp, args)
        self.assertEquals(ex.code, ExitCodes.INTERRUPTED)
        self.assertTrue(mount.called)
        self.assertTrue(litp_import_iso.called)
        self.assertFalse(m_handle_litp_version_history.called)
        self.assertFalse(umount.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.upgrade')
    def test_litp_upgrade_deployment(self, upgrade):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp_upgrade_deployment()
        self.assertTrue(upgrade.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.upgrade')
    def test_litp_upgrade_deployment_fails(self, upgrade):
        instance = self.upgrade_enm.ENMUpgrade()

        upgrade.side_effect = LitpException
        self.assertRaises(SystemExit, instance.litp_upgrade_deployment)
        self.assertTrue(upgrade.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.upgrade')
    def test_litp_upgrade_deployment_fails_message(self, upgrade):
        instance = self.upgrade_enm.ENMUpgrade()

        messages_list = [{'message': 'Upgrade can only be run on deployments'
                                     ', clusters or nodes',
                          'type': 'InvalidLocationError'}]

        upgrade.side_effect = \
            LitpException(404, {'path': 'https://localhost:9999/litp/upgrade',
                                'reason': 'Not Found',
                                'messages': messages_list})
        self.assertRaises(SystemExit, instance.litp_upgrade_deployment)
        self.assertTrue(upgrade.called)

    def test_sub_xml_params_arg_passwords_store_file_not_defined(self):
        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_iso_sed_model()

        try:
            instance.sub_xml_params(args)
            self.fail('Exception not raised')
        except ValueError as ve:
            self.assertTrue('not defined' in str(ve))

    @patch('__builtin__.raw_input')
    def test_sub_xml_reducing_nodes(self, m_raw_input):
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1', 'str-2'])
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        m_raw_input.return_value = 'YeS'

        dd_model = join(dirname(__file__), 'models/model2.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.assumeyes = False
        test_args.model_xml = dd_model

        self.check_message = None

        def patched_info(message):
            if 'WARNING: This deployment description contains' in message:
                self.check_message = message

        with patch('h_util.h_utils.LOG') as p_logger:
            p_logger.info.side_effect = patched_info
            instance.verify_dd_not_reducing_nodes(test_args)
            self.assertIsNotNone(self.check_message)
            self.assertTrue('node deletion' in self.check_message)

    @patch('__builtin__.raw_input')
    def test_sub_xml_reducing_clusters(self, m_raw_input):
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1', 'str-2'])
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        m_raw_input.return_value = 'YeS'

        dd_model = join(dirname(__file__), 'models/model3.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.assumeyes = False
        test_args.model_xml = dd_model

        self.check_message = None

        def patched_info(message):
            if 'WARNING: This deployment description contains' in message:
                self.check_message = message

        with patch('h_util.h_utils.LOG') as p_logger:
            p_logger.info.side_effect = patched_info
            instance.verify_dd_not_reducing_nodes(test_args)
            self.assertIsNotNone(self.check_message)
            self.assertTrue('cluster deletion' in self.check_message)

    @patch('h_util.h_utils.strong_confirmation_or_exit')
    @patch('__builtin__.raw_input')
    def test_sub_xml_not_reducing_nodes(self, m_raw_input, m_conf):
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1', 'str-2'])

        dd_model = join(dirname(__file__), 'models/model.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        m_raw_input.return_value = 'no'
        test_args.assumeyes = False
        instance.verify_dd_not_reducing_nodes(test_args)
        self.assertFalse(m_conf.called)

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('__builtin__.raw_input')
    def test_sub_verify_gossip_router_upgrade_gossip_exists_in_both_assyes(self,
                                        m_raw_input,
                                        m_get_current_version):
        litpd = LitpIntegration()
        litpd.setup_empty_model()
        litpd.create_litp_vcscluster('enm', 'db_cluster')
        litpd.create_item('/deployments/enm/clusters/db_cluster/services'\
        '/gossiprouter_clustered_service')
        dd_model = join(dirname(__file__), 'models/model4.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        test_args.assumeyes = True
        instance.verify_gossip_router_upgrade(test_args)
        self.assertFalse(instance.gossip_upgrade)

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    def test_sub_verify_gossip_router_upgrade_gossip_exists_in_both(self,
                                        m_get_current_version):
        litpd = LitpIntegration()
        litpd.setup_empty_model()
        litpd.create_litp_vcscluster('enm', 'db_cluster')
        litpd.create_item('/deployments/enm/clusters/db_cluster/services'\
        '/gossiprouter_clustered_service')
        dd_model = join(dirname(__file__), 'models/model4.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        test_args.assumeyes = False

        instance.verify_gossip_router_upgrade(test_args)
        self.assertFalse(instance.gossip_upgrade)

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('__builtin__.raw_input')
    def test_sub_verify_gossip_router_upgrade_gossip_exists_in_both_initial(self,
                                        m_raw_input,
                                        m_get_current_version):
        litpd = LitpIntegration()
        litpd.setup_empty_model()
        litpd.create_litp_vcscluster('enm', 'db_cluster')
        litpd.create_item('/deployments/enm/clusters/db_cluster/services'\
        '/gossiprouter_clustered_service',
        state=LitpRestClient.ITEM_STATE_INITIAL)
        dd_model = join(dirname(__file__), 'models/model4.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd

        m_raw_input.return_value = 'YeS'
        test_args.assumeyes = False

        instance.verify_gossip_router_upgrade(test_args)
        self.assertTrue(m_raw_input.called)
        self.assertTrue(instance.gossip_upgrade)

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('__builtin__.raw_input')
    def test_sub_verify_gossip_router_upgrade_gossip_doesnt_exist_in_litp_n(self,
                                            m_raw_input,
                                            m_get_current_version):
        litpd = LitpIntegration()
        litpd.setup_empty_model()
        litpd.create_litp_vcscluster('enm', 'db_cluster')
        dd_model = join(dirname(__file__), 'models/model4.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        m_raw_input.return_value = 'no'
        test_args.assumeyes = False

        with self.assertRaises(SystemExit) as cm:
            instance.verify_gossip_router_upgrade(test_args)
        self.assertEqual(cm.exception.code, 0)

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('__builtin__.raw_input')
    def test_sub_verify_gossip_router_upgrade_gossip_doesnt_exist_in_litp_y(self,
                                            m_raw_input,
                                            m_get_current_version):
        litpd = LitpIntegration()
        litpd.setup_empty_model()
        litpd.create_litp_vcscluster('enm', 'db_cluster')
        dd_model = join(dirname(__file__), 'models/model4.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        m_raw_input.return_value = 'YeS'
        test_args.assumeyes = False

        instance.verify_gossip_router_upgrade(test_args)
        self.assertTrue(m_raw_input.called)
        self.assertTrue(instance.gossip_upgrade)

    def test_sub_xml_params_arg_passwords_store_file_not_existing(self):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.passwords_store_file = NamedTemporaryFile(delete=True)
        instance.passwords_store_file.close()
        self.assertFalse(os.path.isfile(instance.passwords_store_file.name))

        args = self.create_args_iso_sed_model()
        try:
            instance.sub_xml_params(args)
        except ValueError as ve:
            self.assertTrue('does not exist' in str(ve))

    @patch('os.remove')
    @patch('substitute_parameters.substitute')
    def test_sub_xml_params_fails(self, substitute_parameters, os_remove):
        os_remove.side_effect = OSError
        instance = self.upgrade_enm.ENMUpgrade()

        _, upgrade_args = self.create_upgrade_args(
                'upgrade_enm.sh ' + self.add_iso_option() +
                self.add_sed_option() + self.add_model_xml_option())
        substitute_parameters.side_effect = IOError

        self.prepare_passwords_store_file(instance)
        self.assertRaises(SystemExit, instance.sub_xml_params, upgrade_args)

        self.assertTrue(substitute_parameters.called)
        self.assertTrue(os_remove.called)

    @patch('ms_uuid.update_uuid')
    def test_update_ms_uuid(self, update_uuid):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.update_ms_uuid()
        self.assertTrue(update_uuid.called)

    @patch('h_litp.litp_utils.get_xml_deployment_file')
    @patch('h_litp.litp_utils.get_dd_xml_file')
    @patch('h_litp.litp_utils.is_custom_service')
    @patch('h_litp.litp_utils.get_enm_version_deployed')
    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch('hw_resources.report_tab_data')
    @patch('hw_resources.HwResources.litp')
    def test_check_upgrade_hw_provisions(self, m_litp, m_report_tab_data,
                                         m_run_rpc_command, m_enm_version,
                                         m_is_custom, m_dd, m_xml):
        instance = self.upgrade_enm.ENMUpgrade()
        ug_model = join(gettempdir(), 'upgrade_model.xml')
        with open(ug_model, 'w') as ofile:
            ofile.write(test_hw.UPGRADE_MODEL)
        args = self.create_args_iso_sed_model()
        args.model_xml = ug_model
        args.verbose = True

        get_mem = {
            'cloud-db-1': {'data': {'retcode': 0, 'out': 198188760},
                           'errors': ''},
            'cloud-db-2': {'data': {'retcode': 0, 'out': 198188760},
                           'errors': ''},
            'cloud-scp-1': {'data': {'retcode': 0, 'out': 198188760},
                            'errors': ''},
            'cloud-scp-2': {'data': {'retcode': 0, 'out': 198188760},
                            'errors': ''},
            'cloud-svc-1': {'data': {'retcode': 0, 'out': 198188760},
                            'errors': ''},
            'cloud-svc-2': {'data': {'retcode': 0, 'out': 198188760},
                            'errors': ''}
        }

        get_cores = {
            'cloud-db-1': {'data': {'retcode': 0, 'out': 2}, 'errors': ''},
            'cloud-db-2': {'data': {'retcode': 0, 'out': 2}, 'errors': ''},
            'cloud-scp-1': {'data': {'retcode': 0, 'out': 16}, 'errors': ''},
            'cloud-scp-2': {'data': {'retcode': 0, 'out': 16}, 'errors': ''},
            'cloud-svc-1': {'data': {'retcode': 0, 'out': 2}, 'errors': ''},
            'cloud-svc-2': {'data': {'retcode': 0, 'out': 2}, 'errors': ''}
        }

        m_run_rpc_command.side_effect = [get_mem, get_cores]

        stubbed_litp = LitpRestClient()
        deployments = {'_embedded': {'item': [{'id': 'enm'}]}}
        clusters = {'_embedded': {'item': [
            {'id': 'db_cluster'},
            {'id': 'svc_cluster'},
            {'id': 'scp_cluster'}
        ]}}
        db_cluster_nodes = {'_embedded': {'item': [
            {'id': 'db-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-db-1'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}},
            {'id': 'db-2',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-db-2'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}}
        ]}}
        scp_cluster_nodes = {'_embedded': {'item': [
            {'id': 'scp-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-scp-1'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}},
            {'id': 'scp-2',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-scp-2'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}}
        ]}}
        svc_cluster_nodes = {'_embedded': {'item': [
            {'id': 'svc-1',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-svc-1'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}},
            {'id': 'svc-2',
             'state': 'Applied',
             'item-type-name': 'node',
             'properties': {'hostname': 'cloud-svc-2'},
             '_links': {'self': {'href': '/litp/rest/v1/'}}}
        ]}}
        get_lms = {'id': 'ms',
                   'state': 'Applied',
                   'item-type-name': 'node',
                   'properties': {'hostname': 'cloud-ms-1'},
                   '_links': {'self': {'href': '/litp/rest/v1/'}}}
        setup_litp_mocks(stubbed_litp, [
            ['GET', dumps({}), httplib.OK],
            ['GET', test_hw.MODEL, httplib.OK],
            ['GET', dumps(deployments), httplib.OK],
            ['GET', dumps(clusters), httplib.OK],
            ['GET', dumps(db_cluster_nodes), httplib.OK],
            ['GET', dumps(scp_cluster_nodes), httplib.OK],
            ['GET', dumps(svc_cluster_nodes), httplib.OK],
            ['GET', dumps(get_lms), httplib.OK]
        ])
        m_litp.return_value = stubbed_litp
        self.reported_data = None

        def stubbed_report_tab_data(report_type, headers,
                                    table_data, verbose=True):
            self.reported_data = table_data

        m_report_tab_data.side_effect = stubbed_report_tab_data

        instance.check_upgrade_hw_provisions(args)
        self.assertEqual(4, len(self.reported_data))
        for row in self.reported_data:
            self.assertEqual(HwResources.STATE_OK, row[HwResources.H_STATE])

        self.reported_data = None
        get_mem['cloud-svc-1']['data']['out'] = 1
        m_run_rpc_command.reset_mock()
        m_run_rpc_command.side_effect = [get_mem, get_cores]
        setup_litp_mocks(stubbed_litp, [
            ['GET', dumps({}), httplib.OK],
            ['GET', test_hw.MODEL, httplib.OK],
            ['GET', dumps(deployments), httplib.OK],
            ['GET', dumps(clusters), httplib.OK],
            ['GET', dumps(db_cluster_nodes), httplib.OK],
            ['GET', dumps(scp_cluster_nodes), httplib.OK],
            ['GET', dumps(svc_cluster_nodes), httplib.OK],
            ['GET', dumps(get_lms), httplib.OK]
        ])

        with self.assertRaises(SystemExit) as sysexit:
            instance.check_upgrade_hw_provisions(args)
        self.assertEqual(sysexit.exception.code, 1)
        self.assertEqual(4, len(self.reported_data))
        error_found = False
        for row in self.reported_data:
            if row[HwResources.H_NODE] == 'svc-1':
                error_found = True
                self.assertEqual(HwResources.STATE_NOK,
                                 row[HwResources.H_STATE])
        if not error_found:
            self.fail('Expected error for overprovisioned RAM on '
                      'svc-1 not found!')

    def test_copy_runtime_xml(self):
        instance = self.upgrade_enm.ENMUpgrade()
        touch(instance.runtime_xml_deployment)
        instance.copy_runtime_xml()
        self.assertTrue(os.path.isfile(instance.prev_dep_xml))

    def test_copy_runtime_xml_if_prev_xml_exists(self):
        instance = self.upgrade_enm.ENMUpgrade()
        touch(instance.runtime_xml_deployment)
        touch(instance.prev_dep_xml)
        instance.copy_runtime_xml()
        self.assertTrue(os.path.isfile(instance.prev_dep_xml))

    def test_copy_previous_xml(self):
        instance = self.upgrade_enm.ENMUpgrade()
        touch(instance.prev_dep_xml)
        instance.copy_previous_xml()
        self.assertTrue(os.path.isfile(instance.runtime_xml_deployment))

    def test_copy_previous_xml_if_run_xml_exists(self):
        instance = self.upgrade_enm.ENMUpgrade()
        touch(instance.runtime_xml_deployment)
        touch(instance.prev_dep_xml)
        instance.copy_previous_xml()
        self.assertTrue(os.path.isfile(instance.runtime_xml_deployment))

    @patch('h_util.h_utils.exec_process')
    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('upgrade_enm.exec_process')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.pre_snap_changes')
    def test_infrastructure_changes(self, m_pre_snap_changes,
                                    m_create_run_plan,
                                    m_exec_proc,
                                    m_check_any_snapshots_exist,
                                    m_exec_process):

        instance = self.upgrade_enm.ENMUpgrade()
        m_exec_process.return_value = 'Hewlett-Packard'
        m_check_any_snapshots_exist.return_value = False
        args = self.create_args_iso_sed_model()
        m_pre_snap_changes.side_effect = [
            ['litp update -p /ms -o hostname=ieatlms4074',
             'litp update -p /ms -o hostname=ieatlms4074'], ]
        instance.infrastructure_changes(args)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_check_any_snapshots_exist.called)
        self.assertTrue(m_exec_proc.called)
        self.assertTrue(m_create_run_plan.called)
        self.assertTrue(m_pre_snap_changes.called)

    @patch('enm_snapshots.EnmSnap.check_any_snapshots_exist')
    @patch('h_util.h_utils.exec_process')
    @patch('upgrade_enm.pre_snap_changes')
    def test_infrastructure_changes_snaps_exist(self,
                                                m_pre_snap_changes,
                                                m_exec_process,
                                                m_check_any_snapshots_exist):
        instance = self.upgrade_enm.ENMUpgrade()
        m_exec_process.return_value = 'Hewlett-Packard'
        m_check_any_snapshots_exist.return_value = True
        m_pre_snap_changes.return_value = (
            ['litp update -p /ms -o hostname=ieatlms4074',
             'litp update -p /ms -o hostname=ieatlms4074'], False)

        args = self.create_args_iso_sed_model()

        se = assert_exception_raised(SystemExit,
                                     instance.infrastructure_changes,
                                     args)
        self.assertEquals(se.code, ExitCodes.ERROR)

        self.assertTrue(m_pre_snap_changes.called)
        self.assertTrue(m_exec_process.called)
        self.assertTrue(m_check_any_snapshots_exist.called)

    def prepare_passwords_store_file(self, instance):
        instance.passwords_store_file = NamedTemporaryFile(delete=False)
        instance.passwords_store_file.write('password=secret')
        instance.passwords_store_file.close()

    @patch('enm_snapshots.EnmSnap.get_node_cred')
    @patch('enm_snapshots.EnmSnap.start_nodes')
    def test_power_on_new_blades_no_new_blades(self, m_start_nodes,
                                               m_get_node_cred):
        instance = self.upgrade_enm.ENMUpgrade()
        cluster = \
            {'_embedded':
                 {'item': [{
                     'id': 'db-1_system',
                     'item-type-name': 'blade',
                     'state': 'Applied',
                     '_links': {'self': {'href': '/litp/rest/v1/'}},
                     'properties': {'system_name': 'db-1'}},
                     {'id': 'svc-1_system',
                      'item-type-name': 'blade',
                      'state': 'Applied',
                      '_links': {'self': {'href': '/litp/rest/v1/'}},
                      'properties': {'system_name': 'svc-1'}}]}}
        setup_litp_mocks(instance.litp, [
            ['GET', dumps(cluster), httplib.OK]
        ])
        m_get_node_cred.return_value = \
            {'db-1': {'username': 'root',
                      'iloaddress': '10.32.231.108',
                      'password': 'psw', 'id': 'db-1_system'},
             'svc-1': {'username': 'root',
                       'iloaddress': '10.32.231.108',
                       'password': 'psw', 'id': 'svc-1_system'}}
        instance.power_on_new_blades()
        self.assertFalse(m_start_nodes.called)

    @patch('enm_snapshots.EnmSnap.get_node_cred')
    @patch('enm_snapshots.EnmSnap.start_nodes')
    def test_power_on_new_blades_one_new_blade(self, m_start_nodes,
                                               m_get_node_cred):
        instance = self.upgrade_enm.ENMUpgrade()
        cluster = \
            {'_embedded':
                 {'item': [{
                     'id': 'db-1_system',
                     'item-type-name': 'blade',
                     'state': 'Applied',
                     '_links': {'self': {'href': '/litp/rest/v1/'}},
                     'properties': {'system_name': 'db-1'}},
                     {'id': 'svc-1_system',
                      'item-type-name': 'blade',
                      'state': 'Initial',
                      '_links': {'self': {'href': '/litp/rest/v1/'}},
                      'properties': {'system_name': 'svc-1'}}]}}
        setup_litp_mocks(instance.litp, [
            ['GET', dumps(cluster), httplib.OK],
        ])
        m_get_node_cred.return_value = \
            {'db-1': {'username': 'root',
                      'iloaddress': '10.32.231.108',
                      'password': 'psw', 'id': 'db-1_system'},
             'svc-1': {'username': 'root',
                       'iloaddress': '10.32.231.108',
                       'password': 'psw', 'id': 'svc-1_system'}}
        instance.power_on_new_blades()
        new_node_cred = {'svc-1': {'username': 'root',
                                   'iloaddress': '10.32.231.108',
                                   'password': 'psw', 'id': 'svc-1_system'}}
        m_start_nodes.assert_called_with(ANY, new_node_cred, ignore_if_on=True)

    @patch('h_litp.litp_rest_client.LitpRestClient.load_xml')
    @patch('h_litp.litp_rest_client.LitpRestClient.set_debug')
    def test_load_xml_with_sed(self, litp_set_debug, litp_load_xml):
        instance = self.upgrade_enm.ENMUpgrade()

        args = self.create_args_iso_sed_model()

        instance.load_xml(args)
        self.assertTrue(litp_set_debug.called)
        self.assertTrue(litp_load_xml.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.load_xml')
    def test_load_xml_exception(self, litp_load_xml):
        instance = self.upgrade_enm.ENMUpgrade()

        args = self.create_args_iso_sed_model()

        litp_load_xml.side_effect = IOError
        self.assertRaises(SystemExit, instance.load_xml, args)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_update_model_vm_images_no_changes(self, litp_update):

        mock_litp_get = mock_litp_get_requests(current_path,
                                               ["/software/images"])
        print "mock litp value: {0}".format(mock_litp_get)
        imported_images = {
            'ERICrhel79jbossimage':
                'ERICrhel79jbossimage_CXP9041916-1.9.1.qcow2',
            'ERICrhel79lsbimage':
                'ERICrhel79lsbimage_CXP9041915-1.9.1.qcow2'}

        self.du_update_model_vm_images(mock_litp_get, imported_images)

        self.assertFalse(litp_update.called)

    @patch('h_litp.litp_rest_client.LitpRestClient.update')
    def test_update_model_vm_images_changed(self, litp_update):

        mock_litp_get = mock_litp_get_requests(current_path,
                                               ["/software/images"])

        imported_images = {
            'ERICrhel79jbossimage': 'ERICrhel79jbossimage_CXP9041916-1.0.1.qcow2',
            'ERICrhel79lsbimage': 'ERICrhel79lsbimage_CXP9041915-1.0.1.qcow2'
        }

        self.du_update_model_vm_images(mock_litp_get, imported_images)

        self.assertTrue(litp_update.called)

    def du_update_model_vm_images(self, mock_litp_get, imported_images):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp.get = mock_litp_get
        tmp_filename = mktemp()
        try:
            with open(tmp_filename, "a") as f:
                for key, value in imported_images.items():
                    f.write('%s=%s' % (key, value))
                    f.write('\n')

            instance.config['enminst_working_parameters'] = tmp_filename

            instance.update_model_vm_images()
        finally:
            os.remove(tmp_filename)

    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_enable_serialport_service(self, m_handle_exec_process):
        enable_serialport_cmd = \
            '/usr/bin/systemctl enable serial-getty@ttyS0.service'
        start_serialport_cmd = '/usr/bin/systemctl start serial-getty@ttyS0.service'
        instance = self.upgrade_enm.ENMUpgrade()
        instance.enable_serialport_service()
        self.assertEqual(m_handle_exec_process.call_args_list,
                         [call(enable_serialport_cmd,
                  'LITP enabling service "serial-getty@ttySO.service"',
                  'Problem with enabling service ''"serial-getty@ttySO.service"'),
                          call(start_serialport_cmd,
                  'LITP starting service "serial-getty@ttySO.service"',
                  'Problem with starting service "serial-getty@ttySO.service"')])


    @patch('deployer.Deployer.reset_litp_debug')
    @patch('deployer.Deployer.wait_plan_complete')
    @patch('deployer.Deployer.run_plan')
    @patch('deployer.Deployer.create_plan')
    @patch('deployer.Deployer.enable_litp_debug')
    def test_create_run_plan_iso_only(self, enable_litp_debug,
                                      create_plan,
                                      run_plan,
                                      wait_plan_complete,
                                      reset_litp_debug):
        instance = self.upgrade_enm.ENMUpgrade()

        instance.create_run_plan(self.create_args_iso_only())
        self.assertTrue(enable_litp_debug.called)
        self.assertTrue(create_plan.called)
        self.assertTrue(run_plan.called)
        self.assertTrue(wait_plan_complete.called)
        self.assertTrue(reset_litp_debug.called)

    @patch('deployer.Deployer.reset_litp_debug')
    @patch('deployer.Deployer.wait_plan_complete')
    @patch('deployer.Deployer.run_plan')
    @patch('deployer.Deployer.create_plan')
    @patch('deployer.Deployer.enable_litp_debug')
    def test_create_run_plan_with_sed_and_model(self, enable_litp_debug,
                                                create_plan,
                                                run_plan,
                                                wait_plan_complete,
                                                reset_litp_debug):
        instance = self.upgrade_enm.ENMUpgrade()

        instance.create_run_plan(self.create_args_iso_sed_model())
        self.assertTrue(enable_litp_debug.called)
        self.assertTrue(create_plan.called)
        self.assertTrue(run_plan.called)
        self.assertTrue(wait_plan_complete.called)
        self.assertTrue(reset_litp_debug.called)

    @patch('upgrade_enm.deployer.deploy')
    def test_create_run_plan_do_nothing_plan_error(self, deployer_mock):
        instance = self.upgrade_enm.ENMUpgrade()

        status = 422
        path = '/plans'
        reason = ''
        messages = {'message': 'Create plan failed: no tasks were generated',
                    'type': 'DoNothingPlanError'}
        deployer_mock.side_effect = LitpException(status, {'reason': reason,
                                                           'path': path,
                                                           'messages': [
                                                               messages]})

        instance.create_run_plan(self.create_args_iso_sed_model())
        self.assertTrue(deployer_mock.called)

    @patch('upgrade_enm.deployer.deploy')
    @patch('h_litp.litp_rest_client.LitpRestClient.restore_model')
    def test_create_run_plan_persisted_stage_file(self, m_restore_model, deployer_mock):

        instance = self.upgrade_enm.ENMUpgrade()

        deployer_mock.side_effect = SystemExit()

        self.assertRaises(SystemExit, instance.create_run_plan,
                          self.create_args_iso_sed_model())

        (pstage, pstate) = instance.fetch_persisted_stage_data()
        self.assertTrue(m_restore_model.called)
        self.assertEqual(self.upgrade_enm.UPGRADE_PLAN, pstage)
        self.assertEqual(self.upgrade_enm.STATE_FAILED, pstate)
        self.assertTrue(deployer_mock.called)

    @patch('upgrade_enm.deployer.deploy')
    def test_create_run_plan_litp_exception(self, deployer_mock):
        instance = self.upgrade_enm.ENMUpgrade()

        deployer_mock.side_effect = LitpException(IOError)

        self.assertRaises(SystemExit, instance.create_run_plan,
                          self.create_args_iso_sed_model())

        self.assertTrue(deployer_mock.called)

    @patch('upgrade_enm.deployer.deploy')
    def test_create_run_plan_exception(self, deployer_mock):
        instance = self.upgrade_enm.ENMUpgrade()

        deployer_mock.side_effect = IOError

        self.assertRaises(SystemExit, instance.create_run_plan,
                          self.create_args_iso_sed_model())
        self.assertTrue(deployer_mock.called)

    def load_file_from_path(self, path):
        file_current_path = current_path + path
        with open(file_current_path, "r") as myfile:
            data = myfile.read()
        return data

    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('deployer.Deployer.update_version_and_history')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('enm_version.display')
    @patch('upgrade_enm.get_nas_type')
    def test_post_upgrade_enm_version_exception_handled(
            self, m_nas_type, enm_version, m_litp_backup_state_cron,
            switch_db, version_and_history, m_cleanup_java_core_dumps_cron,
            m_create_san_fault_check_cron,
            m_create_nasaudit_errorcheck_cron, os_system=None):
        m_nas_type.return_value = 'veritas'
        instance = self.upgrade_enm.ENMUpgrade()
        enm_version.side_effect = AttributeError(
                "'NoneType' object has no attribute 'encode'")
        instance.post_upgrade()
        self.assertTrue(version_and_history.called)
        self.assertTrue(enm_version.called)
        self.assertTrue(switch_db.called)
        self.assertTrue(m_litp_backup_state_cron.called)
        self.assertTrue(m_cleanup_java_core_dumps_cron.called)
        self.assertTrue(m_create_san_fault_check_cron.called)
        self.assertTrue(m_create_nasaudit_errorcheck_cron.called)

    @patch('upgrade_enm.create_nasaudit_errorcheck_cron')
    @patch('upgrade_enm.create_san_fault_check_cron')
    @patch('deployer.Deployer.update_version_and_history')
    @patch('upgrade_enm.switch_dbcluster_groups')
    @patch('upgrade_enm.litp_backup_state_cron')
    @patch('upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('enm_version.display')
    @patch('upgrade_enm.os.path.isfile')
    @patch('upgrade_enm.os.system')
    @patch('upgrade_enm.get_nas_type')
    def test_post_upgrade_enm_scripts_called(
            self, m_nas_type, os_system, m_os_isfile, enm_version,
            m_litp_backup_state_cron, switch_db,
            version_and_history, m_cleanup_java_core_dumps_cron,
            m_create_san_fault_check_cron,
            m_create_nasaudit_errorcheck_cron):
        m_nas_type.return_value = 'veritas'
        m_os_isfile.return_value = True
        es_admin_pwd_file = "/opt/ericsson/enminst/bin/esadmin_password_set.sh"
        es_admin_pwd_file_cmd = 'sh %s' % es_admin_pwd_file
        pib_reset_execution_file = "/ericsson/pib-scripts/scripts/" \
                                   "pib_reset_status_all.sh"
        pib_reset_execution_file_cmd = 'sh %s' % pib_reset_execution_file
        instance = self.upgrade_enm.ENMUpgrade()
        instance.post_upgrade()
        os_system.assert_has_calls([call(es_admin_pwd_file_cmd),
                                    call(pib_reset_execution_file_cmd)],
                                   any_order=True)

    @patch('h_vcs.vcs_utils.getstatusoutput')
    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    @patch('h_vcs.vcs_cli.Vcs.get_neo4j_cluster_information')
    @patch('h_vcs.vcs_cli.Vcs.neo4j_offline_freeze')
    def test_neo4j_pre_check_neoj4_not_in_use(
            self, m_neo4j_offline_freeze,
            m_get_neo4j_cluster_information,
            m_get_cluster_group_status,
            m_getstatusoutput):

        m_getstatusoutput.return_value = 1, ''
        instance = self.upgrade_enm.ENMUpgrade()
        instance.neo4j_pre_check()
        self.assertTrue(m_get_neo4j_cluster_information.called)
        self.assertTrue(m_neo4j_offline_freeze.called)

    @patch('os.path.exists')
    @patch('upgrade_enm.exec_process_via_pipes')
    def test_harden_neo4j(
            self, m_exec_process_via_pipes, m_script_exists):
        m_exec_process_via_pipes.return_value = ""
        m_script_exists.return_value=True
        instance = self.upgrade_enm.ENMUpgrade()
        instance.harden_neo4j()
        self.assertTrue(m_exec_process_via_pipes.called)

    @patch('os.path.exists')
    @patch('upgrade_enm.exec_process_via_pipes')
    def test_harden_neo4j_not_called(
            self, m_exec_process_via_pipes, m_script_exists):
        m_exec_process_via_pipes.return_value = ""
        m_script_exists.return_value=False
        instance = self.upgrade_enm.ENMUpgrade()
        instance.harden_neo4j()
        self.assertFalse(m_exec_process_via_pipes.called)

    @patch('upgrade_enm.LitpRestClient')
    @patch('upgrade_enm.ENMUpgrade.parse_deploy_diff_output')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    def test_item_property_removed_from_model(self, output_file, diff_output,
                                              litp):
        output_file.return_value = None
        diff_output.return_value = [('/path1', None), ('path2', 'prop1')]
        litp.return_value.delete_path.return_value = True
        litp.return_value.delete_property.return_value = True
        instance = self.upgrade_enm.ENMUpgrade()
        instance.remove_items_from_model()
        self.assertTrue(litp.return_value.delete_path.called)
        self.assertTrue(litp.return_value.delete_property.called)
        self.assertTrue(output_file.called)
        self.assertTrue(diff_output.called)

    @patch('upgrade_enm.LitpRestClient')
    @patch('upgrade_enm.ENMUpgrade.parse_deploy_diff_output')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    def test_item_property_not_in_model(self, output_file, diff_output, litp):
        output_file.return_value = None
        diff_output.return_value = [('/path1', None), ('path2', 'prop1')]
        litp.return_value.delete_path.return_value = False
        litp.return_value.delete_property.return_value = False
        instance = self.upgrade_enm.ENMUpgrade()
        instance.remove_items_from_model()
        self.assertTrue(litp.return_value.delete_path.called)
        self.assertTrue(litp.return_value.delete_property.called)
        self.assertTrue(output_file.called)
        self.assertTrue(diff_output.called)

    @patch('upgrade_enm.LitpRestClient')
    @patch('upgrade_enm.ENMUpgrade.parse_deploy_diff_output')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    def test_diff_output_empty(self, output_file, diff_output, litp):
        output_file.return_value = None
        diff_output.return_value = []
        instance = self.upgrade_enm.ENMUpgrade()
        instance.remove_items_from_model()
        self.assertFalse(litp.return_value.delete_path.called)
        self.assertFalse(litp.return_value.delete_property.called)
        self.assertTrue(output_file.called)
        self.assertTrue(diff_output.called)

    def test_parse_deploy_diff_output(self):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.deploy_diff_out = self.deploy_diff_filename
        # property and path to remove
        with open(self.deploy_diff_filename, 'w') as f:
            f.write('y property@/path/to/item')
        result = instance.parse_deploy_diff_output()
        self.assertListEqual(result, [('/path/to/item', 'property')])
        # only path to remove
        with open(self.deploy_diff_filename, 'w') as f:
            f.write('y /path/to/item')
        result = instance.parse_deploy_diff_output()
        self.assertListEqual(result, [('/path/to/item', None)])
        # no items to remove
        with open(self.deploy_diff_filename, 'w') as f:
            f.write('n /path/to/item')
        result = instance.parse_deploy_diff_output()
        self.assertListEqual(result, [])
        # empty file
        with open(self.deploy_diff_filename, 'w') as f:
            f.write('')
        result = instance.parse_deploy_diff_output()
        self.assertListEqual(result, [])

    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.HealthCheck')
    @patch('upgrade_enm.ENMUpgrade.is_snapshots_supported')
    @patch('upgrade_enm.check_snapshots_indicator_file_exists')
    def test_exec_healthcheck(self, snap_indicator, snap_support, hc,
                              m_create_xml_diff_file):
        instance = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_iso_sed_model()
        snap_indicator.return_value = False
        snap_support.return_value = True
        instance.exec_healthcheck(args)
        self.assertTrue(hc.return_value.pre_checks.called)
        self.assertTrue(hc.return_value.enminst_healthcheck.called)

    @patch('upgrade_enm.os.path.isfile')
    @patch('upgrade_enm.delete_file')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_create_xml_diff_file(self, m_handle_exec_process,
                                m_delete_file, m_os_isfile):

        m_os_isfile.return_value = True
        instance = self.upgrade_enm.ENMUpgrade()
        instance.create_xml_diff_file()
        self.assertTrue(m_handle_exec_process.called)
        self.assertTrue(m_delete_file.called)

    @patch('ssh_key_creation.SshCreation.manage_ssh_action')
    def test_regenerate_ssh_keys(self, ssh):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.regenerate_ssh_keys()
        self.assertTrue(ssh.called)

    @patch('upgrade_enm.os.path.isfile')
    @patch('upgrade_enm.delete_file')
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_create_xml_diff_file_exception(self, m_handle_exec_process,
                                          m_delete_file, m_os_isfile):

        m_os_isfile.return_value = False
        instance = self.upgrade_enm.ENMUpgrade()
        with self.assertRaises(SystemExit) as cm:
            instance.create_xml_diff_file()
        the_exception = cm.exception
        self.assertEqual(the_exception.code, ExitCodes.ERROR)
        self.assertFalse(m_handle_exec_process.called)
        self.assertFalse(m_delete_file.called)

    def test_process_help(self):
        self.assertRaises(SystemExit, self.create_upgrade_args,
                          'upgrade_enm.sh -h')

    def test_process_arguments(self):
        parser, upgrade_args = self.create_upgrade_args(
                'upgrade_enm.sh ' + self.add_iso_option())
        instance = self.upgrade_enm.ENMUpgrade()
        instance.process_arguments(parser, upgrade_args)

    def create_upgrade_args(self, command_line):
        args = command_line.split()
        parser = self.upgrade_enm.create_parser()
        parsed_args = parser.parse_args(args[1:])
        return parser, parsed_args

    def process_arguments_assert_error(self, *cmd_options):
        command = 'upgrade_enm.sh '
        for cmd_opt in cmd_options:
            command += cmd_opt
        parser, upgrade_args = self.create_upgrade_args(command)
        instance = self.upgrade_enm.ENMUpgrade()
        self.assertRaises(SystemExit, instance.process_arguments,
                          parser, upgrade_args)

    def process_arguments_assert_ok(self, *cmd_options):
        command = 'upgrade_enm.sh '
        for cmd_opt in cmd_options:
            command += cmd_opt
        parser, upgrade_args = self.create_upgrade_args(command)
        instance = self.upgrade_enm.ENMUpgrade()
        instance.process_arguments(parser, upgrade_args)

    def test_process_arguments_model_patch_only(self):
        touch(self.ms_patched_done_file)
        with open(self.ms_patched_done_file, 'w') as f:
            f.write('patch_without_model')
        self.process_arguments_assert_error(self.add_iso_option(),
                                            self.add_model_xml_option(),
                                            self.add_sed_option())
        os.remove(self.ms_patched_done_file)

    def test_process_arguments_sed_only(self):
        self.process_arguments_assert_error(self.add_iso_option(),
                                            self.add_sed_option())

    def test_process_arguments_model_xml_only(self):
        self.process_arguments_assert_error(self.add_iso_option(),
                                            self.add_model_xml_option())

    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_process_arguments_sed_model_xml_iso(self, m_verify_dd_expanding_nodes):
        self.process_arguments_assert_ok(self.add_iso_option(),
                                         self.add_sed_option(),
                                         self.add_model_xml_option())

    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_process_arguments_sed_and_model_xml(self, m_verify_dd_expanding_nodes):
        self.process_arguments_assert_ok(self.add_sed_option(),
                                         self.add_model_xml_option())

    def test_process_arguments_os_patch_full(self):
        self.process_arguments_assert_ok(self.add_os_patch_option())

    def test_process_arguments_os_patch_and_sed(self):
        self.process_arguments_assert_error(self.add_os_patch_option(),
                                            self.add_sed_option())

    def test_process_arguments_os_patch_and_model(self):
        self.process_arguments_assert_error(self.add_os_patch_option(),
                                            self.add_model_xml_option())

    def test_process_arguments_os_patch_and_iso(self):
        self.process_arguments_assert_ok(self.add_os_patch_option(),
                                         self.add_iso_option())

    def test_process_arguments_os_patch_and_litp_iso(self):
        self.process_arguments_assert_ok(self.add_os_patch_option(),
                                         self.add_litp_upgrade_option())

    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_process_arguments_os_patch_and_sed_and_model(self, m_verify_dd_expanding_nodes):
        self.process_arguments_assert_ok(self.add_os_patch_option(),
                                         self.add_sed_option(),
                                         self.add_model_xml_option())

    @patch('filecmp.cmp')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_expanding_nodes')
    def test_process_arguments_os_multi_patch_and_sed_and_model(self,
                                                                m_verify_dd_expanding_nodes,
                                                                m_filecmp):
        m_filecmp.return_value = False
        self.process_arguments_assert_ok(self.add_os_patch_option_multiple(),
                                         self.add_sed_option(),
                                         self.add_model_xml_option())

    @patch('filecmp.cmp')
    def test_process_arguments_os_multi_same_patch_and_sed_and_model(self,
                                                                     m_filecmp):
        m_filecmp.return_value = True
        self.process_arguments_assert_error(self.add_os_patch_option_multiple(),
                                            self.add_sed_option(),
                                            self.add_model_xml_option())

    def test_process_arguments_enm_iso_and_noreboot(self):
        self.process_arguments_assert_error(
                self.add_iso_option(),
                ' ' + self.upgrade_enm.CMD_OPTION_NOREBOOT_SHORT)

    def test_process_arguments_no_options(self):
        self.process_arguments_assert_error()

    @patch('import_iso.main_flow')
    @patch('upgrade_enm.EnmLmsHouseKeeping')
    def test_import_enm_iso_for_upgrade_housekeeping(self, doyler,
                                                     m_main_flow):
        mocked_yum = MagicMock('iso_yum_contents')
        mocked_images = MagicMock('iso_image_contents')
        mainflow_iso_contents = {import_iso.ISO_CONTENTS_YUM: mocked_yum,
                                 import_iso.ISO_CONTENTS_IMAGES: mocked_images}
        m_main_flow.side_effect = [mainflow_iso_contents]
        self.upgrade_enm.ENMUpgrade.import_enm_iso_for_upgrade(Namespace(enm_iso=None,
                                                        verbose=False))
        doyler.assert_has_calls([
            call().housekeep_images(mocked_images),
            call().housekeep_yum(mocked_yum)
        ], any_order=True)

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.remove_deployment_description_file')
    @patch('upgrade_enm.ENMUpgrade.check_postgres_uplift_req')
    @patch('upgrade_enm.ENMUpgrade.enable_puppet_on_nodes')
    @patch('upgrade_enm.ENMUpgrade.verify_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.verify_dd_not_reducing_nodes')
    @patch('upgrade_enm.ENMUpgrade.get_cxp_values')
    @patch('enm_snapshots.create_removed_blades_info_file')
    @patch('upgrade_enm.ENMUpgrade.create_xml_diff_file')
    @patch('upgrade_enm.ENMUpgrade.post_upgrade')
    @patch('upgrade_enm.ENMUpgrade.create_run_plan')
    @patch('upgrade_enm.ENMUpgrade.litp_upgrade_deployment')
    @patch('upgrade_enm.ENMUpgrade.upgrade_applications')
    @patch('upgrade_enm.ENMUpgrade.prepare_snapshot')
    @patch('upgrade_enm.copy_file')
    @patch('upgrade_enm.ENMUpgrade.infrastructure_changes')
    @patch('upgrade_enm.ENMUpgrade.sub_xml_params')
    @patch('upgrade_enm.ENMUpgrade.prepare_runtime_config')
    @patch('upgrade_enm.ENMUpgrade.check_upgrade_hw_provisions')
    @patch('upgrade_enm.HwResources')
    @patch('upgrade_enm.ENMUpgrade.enable_serialport_service')
    @patch('upgrade_enm.HealthCheck.enminst_healthcheck')
    @patch('upgrade_enm.HealthCheck.pre_checks')
    @patch('h_puppet.mco_agents.PostgresAgent.call_postgres_service_reload')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host')
    @patch('upgrade_enm.ENMUpgrade.neo4j_pre_check')
    @patch('upgrade_enm.ENMUpgrade.harden_neo4j')
    @patch('upgrade_enm.ENMUpgrade.validate_enm_deployment_xml')
    @patch('upgrade_enm.ENMUpgrade.check_setup_neo4j_uplift')
    @patch('upgrade_enm.unity_model_updates')
    @patch('crypto_service.crypto_service')
    def test_upgrade_healthchecks_disabled(self,
                                           crypto_service,
                                           m_unity_updates,
                                           m_neo4j_uplift,
                                           m_validate_enm_deployment_xml,
                                           m_harden_neo4j,
                                           m_neo4j_pre_check,
                                           m_vcs,
                                           m_postgres,
                                           m_prechecks,
                                           m_enminst_healthcheck,
                                           enable_serialport_service,
                                           m_hwresources,
                                           m_check_upgrade_hw_provisions,
                                           m_prepare_runtime_config,
                                           m_sub_xml_params,
                                           m_infrastructure_changes,
                                           m_copy_file,
                                           m_prepare_snapshot,
                                           m_upgrade_applications,
                                           m_litp_upgrade_deployment,
                                           m_create_run_plan,
                                           m_post_upgrade,
                                           m_create_xml_diff_file,
                                           m_create_removed_blades_info_file,
                                           m_get_cxp_values,
                                           m_verify_dd_not_reducing_nodes,
                                           m_verify_gossip_router_upgrade,
                                           m_enable_puppet_on_nodes,
                                           m_check_postgres_uplift_requirements,
                                           m_remove_deployment_description_file,
                                           m_nas_type):

        # Only checking that the healthchecks are called or not, not
        # checking anything else so mocked it all out

        m_nas_type.return_value = ''

        # Default is healthchecks are done.
        m_get_cxp_values.side_effect = ['9041797', '9035024',
                                           '9041797', '9035024']
        upgrader = self.upgrade_enm.ENMUpgrade()
        args = self.create_args_iso_sed_model()
        upgrader.execute_stages(args)
        self.assertTrue(m_prechecks.called)
        self.assertTrue(m_enminst_healthcheck.called)
        self.assertTrue(m_check_upgrade_hw_provisions.called)
        self.assertTrue(upgrader.validate_enm_deployment_xml.called)
        self.assertTrue(upgrader.prepare_runtime_config.called)

        # Disable checks from cli args and verify calls arnt made.
        args.disable_hc = True
        args.disable_mp_hc = False
        m_prechecks.reset_mock()
        m_enminst_healthcheck.reset_mock()
        m_check_upgrade_hw_provisions.reset_mock()
        m_validate_enm_deployment_xml.reset_mock()
        m_prepare_runtime_config.reset_mock()
        upgrader.execute_stages(args)
        self.assertFalse(m_prechecks.called)
        self.assertFalse(m_enminst_healthcheck.called)
        self.assertFalse(m_check_upgrade_hw_provisions.called)
        self.assertTrue(upgrader.validate_enm_deployment_xml.called)
        self.assertTrue(upgrader.prepare_runtime_config.called)
        self.assertTrue(crypto_service.called)

    def test_process_arguments_torf_190544(self):
        data = [('lvm_snapsize', 20),
                ('regenerate_keys', None),
                ('dhc', None),
                ('noreboot', None),
                ('patch_rhel', __file__),
                ('litp_iso', __file__),
                ('sed', __file__),
                ('model', __file__),
                ('enm_iso', __file__)]
        for (param, value) in data:
            command = 'upgrade_enm.sh --resume --' + param + ' ' + \
                      str(value) if value else ''

            parser, upgrade_args = self.create_upgrade_args(command)
            upgrader = self.upgrade_enm.ENMUpgrade()
            self.assertRaises(SystemExit, upgrader.process_arguments,
                              parser, upgrade_args)

    def test_persisted_params_torf_190544(self):

        upgrader = self.upgrade_enm.ENMUpgrade()

        upgrader.remove_persisted_params_file()

        persisted_params = upgrader.fetch_params()
        self.assertEquals({}, persisted_params)

        args = self.create_args_patch_iso_only()
        args.lvm_snapsize = 20
        args.regenerate_keys = True
        args.disable_hc = False
        args.disable_hcs = None
        args.litp_iso = self.litp_iso_filename

        upgrader.persist_params(args)

        expected_params = {'model_xml': self.model_xml_filename,
                           'lvm_snapsize': args.lvm_snapsize,
                           'disable_hc': args.disable_hc,
                           'disable_hcs': args.disable_hcs,
                           'sed_file': self.sed_filename,
                           'litp_iso': args.litp_iso,
                           'noreboot': True,
                           'os_patch': [self.os_patch_filename_rh7],
                           'enm_iso': self.iso_filename,
                           'regenerate_keys': args.regenerate_keys}

        persisted_params = upgrader.fetch_params()
        self.assertEquals(expected_params, persisted_params)

        upgrader.remove_persisted_params_file()
        self.assertFalse(os.path.isfile(upgrader.gen_params_filename()))

    def test_persisted_stage_file_torf_190544(self):

        upgrader = self.upgrade_enm.ENMUpgrade()
        upgrader.remove_persisted_stage_file()

        (pstage, pstate) = upgrader.fetch_persisted_stage_data()
        self.assertNotEqual(self.upgrade_enm.UPGRADE_PLAN, pstage)
        self.assertNotEqual(self.upgrade_enm.STATE_START, pstate)

        stage = 'foo'
        state = 'bar'
        upgrader.persist_stage_data(stage, state)
        (pstage, pstate) = upgrader.fetch_persisted_stage_data()
        self.assertEqual(stage, pstage)
        self.assertEqual(state, pstate)

        upgrader.remove_persisted_stage_file()
        self.assertFalse(os.path.isfile(upgrader.gen_stage_data_filename()))

    @patch('deployer.deploy')
    def test_resume_failed_upgrade_plan_torf_190544(self, u_deploy):
        upgrader = self.upgrade_enm.ENMUpgrade()
        upgrader.resume_failed_upgrade_plan(False)
        self.assertTrue(u_deploy.called)

        # ----
        u_deploy.side_effect = LitpException('something went wrong')

        self.assertRaises(SystemExit,
                          upgrader.resume_failed_upgrade_plan, False)
        self.assertTrue(u_deploy.called)

        # ----
        u_deploy.side_effect = Exception('something went wrong')

        self.assertRaises(SystemExit,
                          upgrader.resume_failed_upgrade_plan, False)
        self.assertTrue(u_deploy.called)

    @patch('h_util.h_utils.db_node_removed')
    def test_check_db_node_removed(self, m_db_node_removed):
        upgrader = self.upgrade_enm.ENMUpgrade()
        m_db_node_removed.return_value = False
        result = upgrader.check_db_node_removed()
        self.assertEqual(None, result)

        m_db_node_removed.return_value = True
        self.assertRaises(SystemExit,
                          upgrader.check_db_node_removed)

    def test_is_model_only_upgrade(self):
        cfg = MagicMock()
        cfg.model_xml = True
        cfg.sed_file = True
        cfg.os_patch = True
        cfg.litp_iso = True
        cfg.enm_iso = True
        self.assertFalse(self.upgrade_enm.ENMUpgrade()._is_model_only_upgrade(cfg))
        cfg.model_xml = cfg.sed_file = cfg.os_patch = \
            cfg.litp_iso = cfg.enm_iso = False
        self.assertFalse(self.upgrade_enm.ENMUpgrade()._is_model_only_upgrade(cfg))
        cfg.model_xml = cfg.sed_file = True
        self.assertTrue(self.upgrade_enm.ENMUpgrade()._is_model_only_upgrade(cfg))
        cfg.sed_file = False
        self.assertFalse(self.upgrade_enm.ENMUpgrade()._is_model_only_upgrade(cfg))

    @patch('upgrade_enm.EnmLmsHouseKeeping.get_repo_images')
    @patch('import_iso.update_working_params')
    @patch('import_iso.get_cfg_file')
    def test_update_vmimage_version(self, gcf, uwp, gri):
        gri.return_value = {'ENNNNM': []}
        self.upgrade_enm.ENMUpgrade()._update_vmimage_version()
        uwp.assert_has_calls([])

        gcf.return_value = 'config'
        gri.return_value = {'ENM': ['a_vm_image.qcow2']}
        self.upgrade_enm.ENMUpgrade()._update_vmimage_version()
        uwp.assert_called_once_with('config', ['a_vm_image.qcow2'])

    @patch('h_puppet.mco_agents.run_rpc_command')
    @patch('h_vcs.vcs_cli.Vcs.get_cluster_group_status')
    def test_call_postgres_service_reload(self, m_vcs, m_run_rpc_command):
        rpc_results = {'node1': {'errors': '', 'data': {'retcode': 0, 'err': '',
                                                     'out': ''}}}
        m_run_rpc_command.return_value = rpc_results
        vcs_group_result = [{'ServiceState': 'ONLINE',
                   'Cluster': u'db_cluster',
                   'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
                   'GroupState': 'OK', 'HAType': 'active-standby',
                   'System': 'node1'},
                   {'ServiceState': 'OFFLINE',
                   'Cluster': u'db_cluster',
                   'Group': 'Grp_CS_db_cluster_postgres_clustered_service',
                   'GroupState': 'OK', 'HAType': 'active-standby',
                   'System': 'node2'}
                   ]
        m_vcs.return_value = vcs_group_result, ''

        instance = self.upgrade_enm.ENMUpgrade()
        instance.postgres_reload()
        self.assertTrue(m_run_rpc_command.called)

    @patch('enm_healthcheck.get_nas_type')
    @patch.object(Sed, "get_value")
    @patch("h_util.h_utils.Sed.__init__", autospec=True, return_value=None, _sedfile="/software/autoDeploy/sed")
    @patch.object(HealthCheck, "neo4j_uplift_healthcheck")
    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jClusterOverview, "check_sed_credentials")
    @patch.object(Neo4jClusterOverview, "is_neo4j_4_in_dd")
    @patch('upgrade_enm.ENMUpgrade.create_neo4j_cred_file')
    def test_check_setup_neo4j_uplift_cluster(self,
                                              m_cred_file,
                                              m_neo_dd,
                                              m_check_cred,
                                              m_on_rack,
                                              m_need_uplift_4x,
                                              m_need_uplift,
                                              m_is_single_mode,
                                              m_h_check,
                                              m_sed,
                                              m_get_val,
                                              m_nas_type):
        m_nas_type.return_value = ''
        m_neo_dd.return_value = True
        m_is_single_mode.return_value = False
        m_need_uplift.return_value = True
        m_need_uplift_4x.return_value = False
        m_on_rack.return_value = False
        instance = self.upgrade_enm.ENMUpgrade()
        class Args(object):
            model_xml = "/software/autoDeploy/AAA.xml"
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()
        instance.check_setup_neo4j_uplift(cfg)
        self.assertTrue(m_cred_file.called)

    @patch('h_litp.litp_rest_client.get_connection_type')
    @patch('os.path.exists')
    @patch('enm_healthcheck.get_nas_type')
    @patch.object(Sed, "get_value")
    @patch("h_util.h_utils.Sed.__init__", autospec=True, return_value=None, _sedfile="/software/autoDeploy/sed")
    @patch.object(HealthCheck, "neo4j_uplift_healthcheck")
    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "need_uplift_4x")
    @patch("h_hc.hc_neo4j_cluster.is_env_on_rack")
    @patch.object(Neo4jClusterOverview, "check_sed_credentials")
    @patch.object(Neo4jClusterOverview, "is_neo4j_4_in_dd")
    @patch('upgrade_enm.ENMUpgrade.create_neo4j_cred_file')
    def test_check_setup_neo4j_uplift_cluster_force_ssh_key_access(self,
                                              m_cred_file,
                                              m_neo_dd,
                                              m_check_cred,
                                              m_on_rack,
                                              m_need_uplift_4x,
                                              m_need_uplift,
                                              m_is_single_mode,
                                              m_h_check,
                                              m_sed,
                                              m_get_val,
                                              m_nas_type,
                                              os_path_exists,
                                              get_connection_type):

        def mocked_exists(path):
            if path == FORCE_SSH_KEY_ACCESS_FLAG_PATH:
                return True
            return builtin_os_path_exists(path)

        os_path_exists.side_effect = mocked_exists
        get_connection_type.return_value = ('unix', '')
        m_nas_type.return_value = ''
        m_neo_dd.return_value = True
        m_is_single_mode.return_value = False
        m_need_uplift.return_value = True
        m_need_uplift_4x.return_value = False
        m_on_rack.return_value = False
        instance = self.upgrade_enm.ENMUpgrade()
        class Args(object):
            model_xml = "/software/autoDeploy/AAA.xml"
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()
        instance.check_setup_neo4j_uplift(cfg)
        self.assertFalse(m_check_cred.called)
        self.assertFalse(m_cred_file.called)
        self.assertTrue(m_h_check.called)

    @patch('enm_healthcheck.get_nas_type')
    @patch.object(Sed, "get_value")
    @patch("h_util.h_utils.Sed.__init__", autospec=True, return_value=None, _sedfile="/software/autoDeploy/sed")
    @patch.object(HealthCheck, "neo4j_uplift_healthcheck")
    @patch.object(Neo4jClusterOverview, "is_single_mode")
    @patch.object(Neo4jClusterOverview, "need_uplift")
    @patch.object(Neo4jClusterOverview, "is_neo4j_4_in_dd")
    @patch('upgrade_enm.ENMUpgrade.create_neo4j_cred_file')
    def test_check_setup_neo4j_uplift_single(self,
                                             m_cred_file,
                                             m_neo_dd,
                                             m_need_uplift,
                                             m_is_single_mode,
                                             m_h_check,
                                             m_sed,
                                             m_get_val,
                                             m_nas_type):
        m_nas_type.return_value = ''
        m_neo_dd.return_value = True
        m_is_single_mode.return_value = True
        m_need_uplift.return_value = True
        instance = self.upgrade_enm.ENMUpgrade()
        class Args(object):
            model_xml = "/software/autoDeploy/AAA.xml"
            sed_file = "/software/autoDeploy/sed"
        cfg = Args()
        instance.check_setup_neo4j_uplift(cfg)
        self.assertFalse(m_cred_file.called)

    @patch('yaml.dump')
    def test_create_neo4j_cred_file(self, m_yaml):
        instance = self.upgrade_enm.ENMUpgrade()
        creds = dict()
        with patch('__builtin__.open', new_callable=mock_open()):
            instance.create_neo4j_cred_file(creds)
            self.assertTrue(m_yaml.called)

    @patch('yaml.dump')
    def test_failed_create_neo4j_cred_file(self, m_yaml):
        m_yaml.side_effect = IOError
        instance = self.upgrade_enm.ENMUpgrade()
        creds = dict()
        with patch('__builtin__.open', new_callable=mock_open()):
            with self.assertRaises(SystemExit) as sysexit:
                instance.create_neo4j_cred_file(creds)

    @patch('upgrade_enm.ENMUpgrade._handle_exec_process_via_pipes')
    def test_is_puppet_running_on_nodes(self, exec_process):
        instance = self.upgrade_enm.ENMUpgrade()
        exec_process.return_value = '0'
        self.assertFalse(instance.is_puppet_running_on_nodes())
        exec_process.return_value = '3'
        self.assertTrue(instance.is_puppet_running_on_nodes())

    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    def test_puppet_action_on_nodes(self, exec_process):
        instance = self.upgrade_enm.ENMUpgrade()
        instance._puppet_action_on_nodes('enable')
        exec_process.assert_called_with(
            'mco puppet enable -W puppet_master=false',
            'Will enable Puppet on nodes',
            'Failed to enable Puppet on nodes',
            allowed_error_codes=[2]
        )
        instance._puppet_action_on_nodes('disable')
        exec_process.assert_called_with(
            'mco puppet disable -W puppet_master=false',
            'Will disable Puppet on nodes',
            'Failed to disable Puppet on nodes',
            allowed_error_codes=[2]
        )

    @patch('upgrade_enm.ENMUpgrade._puppet_action_on_nodes')
    def test_enable_puppet_on_nodes(self, puppet_action):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.enable_puppet_on_nodes()
        puppet_action.assert_called_with('enable')

    @patch('upgrade_enm.ENMUpgrade._puppet_action_on_nodes')
    def test_disable_puppet_on_nodes(self, puppet_action):
        instance = self.upgrade_enm.ENMUpgrade()
        instance.disable_puppet_on_nodes()
        puppet_action.assert_called_with('disable')

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.store_and_set_pib')
    @patch('upgrade_enm.ENMUpgrade.litp_set_cs_initial_online')
    @patch('h_util.h_utils.read_pib_param')
    @patch('h_util.h_utils.set_pib_param')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host',
           return_value=['db-1'])
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('enm_bouncer.EnmBouncer.bounce_clusters')
    @patch('time.sleep', return_value=None)
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck',
            return_value=True)
    @patch('upgrade_enm.PreOnlineProvisioner', autospec=True)
    @patch('upgrade_enm.switch_dbcluster_groups')
    def test_post_gossip_router_upgrade(self,
                                   m_switch_dbcluster_groups,
                                   m_preonlineprovisioner,
                                   m_vcs_service_group_healthcheck,
                                   m_sleep,
                                   m_bounce_cluster,
                                   m_exec_process,
                                   m_get_current_version,
                                   m_get_cluster_nodes,
                                   m_get_postgres_active_host,
                                   m_hagrp_offline,
                                   m_hagrp_online,
                                   m_set_pib_param,
                                   m_read_pib_param,
                                   m_litp_set_cs_initial_online,
                                   m_store_and_set_pib,
                                   m_nas_type):

        m_nas_type.return_value = ''

        cfg = MagicMock()
        cfg.verbose = True
        m_exec_process.side_effect = [IOError(1), '']
        instance = self.upgrade_enm.ENMUpgrade()

        with patch.object(logger, 'info') as mock_info:
            instance.post_gossip_router_upgrade(cfg)
            self.assertTrue(mock_info.called)

        self.assertTrue(mock_info.called_with('System successfully upgraded'))
        self.assertEqual(m_bounce_cluster.call_args_list[0],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'off', 120, True))
        self.assertEqual(m_bounce_cluster.call_args_list[1],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'on', 120, True))
        self.assertEqual(m_hagrp_offline.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))
        self.assertTrue(m_hagrp_online.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))
        m_exec_process.assert_has_calls([
            call('/bin/grep "fmemergency_ips=" '
                 '/ericsson/tor/data/global.properties', use_shell=True),
            call(
            ['curl', '-X', 'DELETE', '-d', 'true', 'http://ms-1:8500/v1/kv/jgroups_protocol_migration'])
        ])

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.store_and_set_pib')
    @patch('upgrade_enm.ENMUpgrade.litp_set_cs_initial_online')
    @patch('h_util.h_utils.read_pib_param')
    @patch('h_util.h_utils.set_pib_param')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host',
           return_value=['db-1'])
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('enm_bouncer.EnmBouncer.bounce_clusters')
    @patch('time.sleep', return_value=None)
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck',
            return_value=False)
    @patch('upgrade_enm.PreOnlineProvisioner', autospec=True)
    @patch('upgrade_enm.switch_dbcluster_groups')
    def test_post_gossip_router_upgrade_failure_hc_timeout(self,
                                   m_switch_dbcluster_groups,
                                   m_preonlineprovisioner,
                                   m_vcs_service_group_healthcheck,
                                   m_sleep,
                                   m_bounce_cluster,
                                   m_exec_process,
                                   m_get_current_version,
                                   m_get_cluster_nodes,
                                   m_get_postgres_active_host,
                                   m_hagrp_offline,
                                   m_hagrp_online,
                                   m_set_pib_param,
                                   m_read_pib_param,
                                   m_litp_set_cs_initial_online,
                                   m_store_and_set_pib,
                                   m_nas_type):

        m_vcs_service_group_healthcheck.side_effect = SystemExit()
        m_nas_type.return_value = ''

        cfg = MagicMock()
        cfg.verbose = True
        m_exec_process.return_value = ''
        instance = self.upgrade_enm.ENMUpgrade()
        self.upgrade_enm.POST_BOUNCE_TIMEOUT_SECONDS = 1

        with patch.object(logger, 'info') as mock_info:
            with patch.object(logger, 'error') as mock_error:
                with patch.object(logger, 'exception') as mock_exception:
                    instance.post_gossip_router_upgrade(cfg)

        self.assertTrue(mock_error.called)
        self.assertEqual(mock_error.call_args,
            call('Post upgrade bounce health check timeout. Please verify service health check manually.'))
        self.assertTrue(m_vcs_service_group_healthcheck.call_count > 0)
        self.assertEqual(m_bounce_cluster.call_args_list[0],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'off', 120, True))
        self.assertEqual(m_bounce_cluster.call_args_list[1],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'on', 120, True))
        self.assertEqual(m_hagrp_offline.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))
        self.assertTrue(m_hagrp_online.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))
        self.assertEqual(m_exec_process.call_args,
            call(['/opt/ericsson/enminst/bin/enm_post_restore.sh', 'get_check_clear_non_dbcluster_groups']))
        self.assertEqual(m_preonlineprovisioner.method_calls,
            [call().set_preonline_trigger(), call().unset_preonline_trigger()])

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.store_and_set_pib')
    @patch('upgrade_enm.ENMUpgrade.litp_set_cs_initial_online')
    @patch('h_util.h_utils.read_pib_param')
    @patch('h_util.h_utils.set_pib_param')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host',
           return_value=['db-1'])
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('enm_bouncer.EnmBouncer.bounce_clusters')
    @patch('time.sleep', return_value=None)
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck')
    @patch('upgrade_enm.PreOnlineProvisioner', autospec=True)
    @patch('upgrade_enm.ENMUpgrade._handle_exec_process')
    @patch('upgrade_enm.switch_dbcluster_groups')
    def test_post_gossip_router_upgrade_failed_faulted_service_checkhc(self,
                                   m_switch_dbcluster_groups,
                                   m__handle_exec_process,
                                   m_preonlineprovisioner,
                                   m_vcs_service_group_healthcheck,
                                   m_sleep,
                                   m_bounce_cluster,
                                   m_exec_process,
                                   m_get_current_version,
                                   m_get_cluster_nodes,
                                   m_get_postgres_active_host,
                                   m_hagrp_offline,
                                   m_hagrp_online,
                                   m_set_pib_param,
                                   m_read_pib_param,
                                   m_litp_set_cs_initial_online,
                                   m_store_and_set_pib,
                                   m_nas_type):

        m_vcs_service_group_healthcheck.side_effect = SystemExit()
        m__handle_exec_process.side_effect = SystemExit()
        m_nas_type.return_value = ''

        cfg = MagicMock()
        cfg.verbose = True
        m_exec_process.return_value = ''
        instance = self.upgrade_enm.ENMUpgrade()
        self.upgrade_enm.POST_BOUNCE_TIMEOUT_SECONDS = 1

        with patch.object(logger, 'info') as mock_info:
            with patch.object(logger, 'error') as mock_error:
                with patch.object(logger, 'exception') as mock_exception:
                    instance.post_gossip_router_upgrade(cfg)

        self.assertTrue(mock_error.called)
        self.assertEqual(mock_error.call_args,
            call('Post upgrade bounce health check timeout. Please verify service health check manually.'))
        self.assertTrue(m_vcs_service_group_healthcheck.call_count > 0)
        self.assertEqual(m_bounce_cluster.call_args_list[0],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'off', 120, True))
        self.assertEqual(m_bounce_cluster.call_args_list[1],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'on', 120, True))
        self.assertEqual(m_hagrp_offline.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))
        self.assertTrue(m_hagrp_online.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))
        self.assertEqual(m__handle_exec_process.call_args,
            call('/opt/ericsson/enminst/bin/enm_post_restore.sh get_check_clear_non_dbcluster_groups',
                 'Executing post upgrade bounce faulted service check',
                 'Post upgrade bounce faulted service check failed.'))
        self.assertEqual(m_preonlineprovisioner.method_calls,
            [call().set_preonline_trigger(), call().unset_preonline_trigger()])

    @patch('enm_healthcheck.get_nas_type')
    @patch('upgrade_enm.ENMUpgrade.store_and_set_pib')
    @patch('upgrade_enm.ENMUpgrade.litp_set_cs_initial_online')
    @patch('h_util.h_utils.read_pib_param')
    @patch('h_util.h_utils.set_pib_param')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_online')
    @patch('h_vcs.vcs_cli.Vcs.hagrp_offline')
    @patch('upgrade_enm.ENMUpgrade.get_postgres_active_host',
           return_value=['db-1'])
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.exec_process')
    @patch('enm_bouncer.EnmBouncer.bounce_clusters')
    @patch('time.sleep', return_value=None)
    @patch('enm_healthcheck.HealthCheck.vcs_service_group_healthcheck',
            return_value=False)
    @patch('upgrade_enm.PreOnlineProvisioner', autospec=True)
    @patch('upgrade_enm.switch_dbcluster_groups')
    def test_post_gossip_router_upgrade_failure_postgres(self,
                                   m_switch_dbcluster_groups,
                                   m_preonlineprovisioner,
                                   m_vcs_service_group_healthcheck,
                                   m_sleep,
                                   m_bounce_cluster,
                                   m_exec_process,
                                   m_get_current_version,
                                   m_get_cluster_nodes,
                                   m_get_postgres_active_host,
                                   m_hagrp_offline,
                                   m_hagrp_online,
                                   m_set_pib_param,
                                   m_read_pib_param,
                                   m_litp_set_cs_initial_online,
                                   m_store_and_set_pib,
                                   m_nas_type):

        def my_side_effect(*args, **kwargs):
            raise SystemExit(ExitCodes.VCS_INVALID_STATE)

        m_hagrp_offline.side_effect = my_side_effect
        m_nas_type.return_value = ''

        cfg = MagicMock()
        cfg.verbose = True
        m_exec_process.return_value = ''
        instance = self.upgrade_enm.ENMUpgrade()
        self.upgrade_enm.POST_BOUNCE_TIMEOUT_SECONDS = 1

        with patch.object(logger, 'info') as mock_info:
            with patch.object(logger, 'error') as mock_error:
                with patch.object(logger, 'exception') as mock_exception:
                    instance.post_gossip_router_upgrade(cfg)

        self.assertTrue(m_hagrp_offline.called)
        self.assertFalse(m_hagrp_online.called)
        self.assertEqual(mock_error.call_args_list[0],
            call('Failed to offline/online Postgres SG', exc_info=True))
        self.assertTrue(m_vcs_service_group_healthcheck.call_count > 0)
        self.assertEqual(m_bounce_cluster.call_args_list[0],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'off', 120, True))
        self.assertEqual(m_bounce_cluster.call_args_list[1],
            call(['svc_cluster', 'scp_cluster', 'eba_cluster', 'ebs_cluster', 'str_cluster', 'asr_cluster', 'evt_cluster', 'aut_cluster'], 'on', 120, True))
        self.assertEqual(m_hagrp_offline.call_args, call(
            '.*postgres_clustered_service', 'db-1', 'db_cluster', -1))

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.ENMUpgrade.post_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.resume_failed_upgrade_plan')
    @patch('upgrade_enm.ENMUpgrade.fetch_persisted_stage_data')
    @patch('upgrade_enm.ENMUpgrade.is_consul_flag')
    def test_main_execute_stages_fail_resume_gossip(self,
                                      m_is_consul_flag,
                                      m_fetch_persisted_stage_data,
                                      m_resume_failed_upgrade_plan,
                                      m_post_gossip_router_upgrade,
                                      m_execute_post_upgrade_steps,
                                      m_log_cmdline_args,
                                      m_get_current_version):

        m_fetch_persisted_stage_data.side_effect = [('upgrade_plan', 'start')]
        args = 'upgrade_enm.sh --resume --assumeyes'
        self.upgrade_enm.main(args.split())
        self.assertTrue(m_resume_failed_upgrade_plan.called)
        self.assertTrue(m_is_consul_flag.called)
        self.assertTrue(m_post_gossip_router_upgrade.called)
        self.assertTrue(m_execute_post_upgrade_steps)

    @patch('h_util.h_utils.RHELUtil.get_current_version')
    @patch('upgrade_enm.log_cmdline_args')
    @patch('upgrade_enm.ENMUpgrade.execute_post_upgrade_steps')
    @patch('upgrade_enm.ENMUpgrade.post_gossip_router_upgrade')
    @patch('upgrade_enm.ENMUpgrade.resume_failed_upgrade_plan')
    @patch('upgrade_enm.ENMUpgrade.fetch_persisted_stage_data')
    @patch('upgrade_enm.ENMUpgrade.is_consul_flag')
    def test_main_execute_stages_fail_resume_no_gossip(self,
                                      m_is_consul_flag,
                                      m_fetch_persisted_stage_data,
                                      m_resume_failed_upgrade_plan,
                                      m_post_gossip_router_upgrade,
                                      m_execute_post_upgrade_steps,
                                      m_log_cmdline_args,
                                      m_get_current_version):

        m_fetch_persisted_stage_data.side_effect = [('upgrade_plan', 'start')]
        m_is_consul_flag.side_effect = [False]
        args = 'upgrade_enm.sh --resume --assumeyes'
        self.upgrade_enm.main(args.split())
        self.assertTrue(m_resume_failed_upgrade_plan.called)
        self.assertTrue(m_is_consul_flag.called)
        self.assertFalse(m_post_gossip_router_upgrade.called)
        self.assertTrue(m_execute_post_upgrade_steps)

    def test_validate_log4j_cleanup_nofiles(self):
        instance = self.upgrade_enm.ENMUpgrade()
        with patch.object(logger, 'debug') as mock_debug:
            instance.cleanup_log4j_ec_files()
        self.assertTrue(mock_debug.called_with('not found'))

    @patch('os.remove')
    @patch('os.path.exists')
    def test_validate_log4j_cleanup(self, m_os_path_exists, m_os_remove):
        instance = self.upgrade_enm.ENMUpgrade()
        m_os_path_exists.return_value = True
        m_os_remove.return_value = True
        with patch.object(logger, 'info') as mock_info:
            instance.cleanup_log4j_ec_files()
        self.assertTrue(mock_info.called_with('Removing file'))

    def test_verify_dd_expanding_nodes(self):
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1'])
        dd_model = join(dirname(__file__), 'models/model.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        test_args.expansion_upgrade = False
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        self.assertRaises(SystemExit,
                          instance.verify_dd_expanding_nodes, test_args)

    def test_reverse_verify_dd_expanding_nodes(self):
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1', 'str-2', 'str-3'])
        dd_model = join(dirname(__file__), 'models/model.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        test_args.expansion_upgrade = False
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        result = instance.verify_dd_expanding_nodes(test_args)
        self.assertEqual(result, None)

    def test_new_cluster_verify_dd_expanding_nodes(self):
        litpd = LitpIntegration()
        litpd.setup_str_cluster_multiple_nodes(['str-1', 'str-2'])
        dd_model = join(dirname(__file__), 'models/model5.xml')
        test_args = self.create_args_iso_sed_model()
        test_args.model_xml = dd_model
        test_args.expansion_upgrade = False
        instance = self.upgrade_enm.ENMUpgrade()
        instance.litp = litpd
        self.assertRaises(SystemExit,
                          instance.verify_dd_expanding_nodes, test_args)

def walk_directories_for_os_patches(args):
    del args
    return [('/tmp/tmpfJq19d/', '', ''),
            ('/tmp/tmpfJq19d/RHEL', '', ''),
            ('/tmp/tmpfJq19d/RHEL/RHEL_Errata', '', ''),
            ('/tmp/tmpfJq19d/RHEL/RHEL7_9.z-3.0.5', '', ''),
            ('/tmp/tmpfJq19d/RHEL/RHEL7_9.z-3.0.5/repodata', '', ''),
            ('/tmp/tmpfJq19d/RHEL/RHEL7_9.z-3.0.5/packages', '', ''),
            ('/tmp/tmpfJq19d/RHEL/CONFIG', '', '')]

def walk_directories_for_rhel8_os_patches(args):
    return [('/tmp/tmprhel8/', '', ''),
            ('/tmp/tmprhel8/RHEL', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL_Errata', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL8.8_AppStream-1.0.8', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL8.8_AppStream-1.0.8/Packages', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL8.8_AppStream-1.0.8/Packages/repodata', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL8.8_BaseOS-1.0.8', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL8.8_BaseOS-1.0.8/repodata', '', ''),
            ('/tmp/tmprhel8/RHEL/RHEL8.8_BaseOS-1.0.8/Packages', '', ''),
            ('/tmp/tmprhel8/RHEL/CONFIG', '', '')]


if __name__ == "__main__":
    main()
