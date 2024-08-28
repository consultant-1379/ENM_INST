"""
Unit Test the RHEL 7.9 ENM Upgrader tool
"""
import os
import argparse
import copy
import platform
import collections
import shutil
import stat
import random
import tempfile
import time
import errno
from functools import partial
from mock import patch, Mock, MagicMock, call, PropertyMock
from unittest2 import TestCase
from os.path import exists
from tempfile import gettempdir, NamedTemporaryFile
from h_util.h_postgres import PostgresService
from h_util.h_utils import touch, get_enable_cron_on_expiry_cmd, \
                            cmd_DISABLE_CRON_ON_EXPIRY
from h_litp.litp_utils import LitpException
from h_puppet.mco_agents import McoAgentException
from h_logging.enminst_logger import init_enminst_logging

from rh7_upgrade_enm import Rh7EnmUpgrade
import rh7_upgrade_enm

LOGGER = init_enminst_logging()

CMD_UPGRADE_ENM_DEFAULT_OPTIONS = 'rh7_upgrade_enm.sh '

FROM_STATE_LITP_VERSION_R6 = "LITP 20.11 CSA 113 110 R2EV02_SNAPSHOT"
FROM_STATE_LITP_VERSION_R7 = "LITP 21.14 CSA 113 110 R3AZ09"
TO_STATE_LITP_VERSION_R6 = "R2ZA01"
TO_STATE_LITP_VERSION_R7 = "R4AZ99"
TO_STATE_LITP_VERSION_INCORRECT_FORMAT = "RRrrs0"

LITP_PUPPET_PLUGINS_MANIFEST_DIR = '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins'

LITP_MODEL_PROFILES_2_NODE_RHEL7 = [
    {'path': '/deployments/d1/clusters/c1/nodes/n1/os',
     'data': {u'id': u'os',
              u'item-type-name': u'reference-to-os-profile',
              u'applied_properties_determinable': True,
              u'state': u'Applied',
              u'_links': {u'inherited-from':
                          {u'href': u'http://127.0.0.1/litp/rest/v1/software/profiles/os_prof1'},
                          u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/deployments/d1/clusters/c1/nodes/n1/os'},
                          u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/os-profile'}
                          },
              u'properties': {u'name': u'os-profile1',
                              u'kopts_post': u'console=ttyS0,115200',
                              u'breed': u'redhat',
                              u'version': u'rhel7',
                              u'path': u'/var/www/html/7/os/x86_64/',
                              u'arch': u'x86_64'}
              }
     },
    {'path': '/deployments/d1/clusters/c1/nodes/n2/os',
     'data': {u'id': u'os',
              u'item-type-name': u'reference-to-os-profile',
              u'applied_properties_determinable': True,
              u'state': u'Applied',
              u'_links': {u'inherited-from': {u'href': u'http://127.0.0.1/litp/rest/v1/software/profiles/os_prof1'},
                          u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/deployments/d1/clusters/c1/nodes/n2/os'},
                          u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/os-profile'}
                          },
              u'properties': {u'name': u'os-profile1',
                              u'kopts_post': u'console=ttyS0,115200',
                              u'breed': u'redhat',
                              u'version': u'rhel7',
                              u'path': u'/var/www/html/7/os/x86_64/',
                              u'arch': u'x86_64'}
              }
     }]

LITP_BRIDGES = [
    {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/network_interfaces/br3',
    'data': {u'id': u'br3',
             u'item-type-name': u'bridge',
             u'applied_properties_determinable': True,
             u'state': u'Initial',
             u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/deployments/enm/clusters/svc_cluster/nodes/svc-1/network_interfaces/br3'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/bridge'}},
                 u'properties': {u'hash_max': u'512',
                                 u'ipaddress': u'10.250.246.2',
                                 u'hash_elasticity': u'4',
                                 u'device_name': u'br3',
                                 u'forwarding_delay': u'0',
                                 u'multicast_router': u'1',
                                 u'stp': u'false',
                                 u'multicast_snooping': u'0',
                                 u'network_name': u'jgroups',
                                 u'multicast_querier': u'0'}}
                },
    {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/network_interfaces/br2',
    'data':{u'id': u'br2',
            u'item-type-name': u'bridge',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/deployments/enm/clusters/svc_cluster/nodes/svc-1/network_interfaces/br2'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/bridge'}},
                 u'properties': {u'hash_max': u'512',
                                 u'ipaddress': u'10.250.246.2',
                                 u'hash_elasticity': u'4',
                                 u'device_name': u'br3',
                                 u'forwarding_delay': u'4',
                                 u'multicast_router': u'1',
                                 u'stp': u'false',
                                 u'multicast_snooping': u'0',
                                 u'network_name': u'jgroups',
                                 u'multicast_querier': u'0'}
                 }
                }]
LITP_MS_BRIDGES = [
                {'path': '/ms/network_interfaces/br1',
                'data':{u'id': u'br1',
                 u'item-type-name': u'bridge',
                 u'applied_properties_determinable': True,
                 u'state': u'Initial',
                 u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/ms/network_interfaces/br1'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/bridge'}},
                 u'properties': {u'hash_max': u'512',
                                 u'ipaddress': u'10.250.246.2',
                                 u'hash_elasticity': u'4',
                                 u'device_name': u'br3',
                                 u'forwarding_delay': u'31',
                                 u'multicast_router': u'1',
                                 u'stp': u'false',
                                 u'multicast_snooping': u'0',
                                 u'network_name': u'jgroups',
                                 u'multicast_querier': u'0'}}
                }]

LITP_YUM_REPOS = [
    {'path': '/software/items/custom_model_repo',
    'data':{u'id': u'model_repo',
            u'item-type-name': u'yum-repository',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/software/items/custom_model_repo'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/yum-repository'}},
                 u'properties': {u'cache_metadata': u'false',
                                 u'checksum': u'a3fa29581326c60d5e2115de7d85090d',
                                 u'ms_url_path': u' /ENM_models/'}
                 }
                },
    {'path': '/software/items/model_repo',
    'data':{u'id': u'model_repo',
            u'item-type-name': u'yum-repository',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/software/items/custom_model_repo'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/yum-repository'}},
                 u'properties': {u'cache_metadata': u'false',
                                 u'checksum': u'a3fa29581326c60d5e2115de7d85090d',
                                 u'ms_url_path': u' /ENM_models_rhel7/'}
                 }
                },]

LITP_MS_VM_YUM_REPOS = [
    {'path': '/ms/services/customized/vm_yum_repos/3pp',
    'data':{u'id': u'3pp',
            u'item-type-name': u'vm-yum-repo',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/ms/services/customized/vm_yum_repos/3pp'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/vm-yum-repo'}},
                 u'properties': {u'cache_metadata': u'false',
                                 u'checksum': u'a3fa29581326c60d5e2115de7d85090d',
                                 u'base_url': u'http://10.247.246.2/3pp/'}
                 }
                },
    {'path': '/ms/services/esmon/vm_yum_repos/3pp',
    'data':{u'id': u'3pp',
            u'item-type-name': u'vm-yum-repo',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/ms/services/esmon/vm_yum_repos/3pp'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/vm-yum-repo'}},
                 u'properties': {u'cache_metadata': u'false',
                                 u'checksum': u'a3fa29581326c60d5e2115de7d85090d',
                                 u'base_url': u'http://10.247.246.2/3pp_rhel7/'}
                 }
                },
    ]
LITP_VM_YUM_REPOS = [
    {'path': '/software/services/oneflowca/vm_yum_repos/common',
    'data':{u'id': u'common_repo',
            u'item-type-name': u'vm-yum-repo',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/software/services/oneflowca/vm_yum_repos/common'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/vm-yum-repo'}},
                 u'properties': {u'cache_metadata': u'false',
                                 u'checksum': u'a3fa29581326c60d5e2115de7d85090d',
                                 u'base_url': u'http://10.247.246.2/ENM_common/'}
                 }
                },
    {'path': '/software/services/cnom/vm_yum_repos/common',
    'data':{u'id': u'common_repo',
            u'item-type-name': u'vm-yum-repo',
            u'applied_properties_determinable': True,
            u'state': u'Initial',
            u'_links': {u'self': {u'href': u'http://127.0.0.1/litp/rest/v1/software/services/cnom/vm_yum_repos/common'},
                             u'item-type': {u'href': u'http://127.0.0.1/litp/rest/v1/item-types/vm-yum-repo'}},
                 u'properties': {u'cache_metadata': u'false',
                                 u'checksum': u'a3fa29581326c60d5e2115de7d85090d',
                                 u'base_url': u'http://10.247.246.2/ENM_common_rhel7/'}
                 }
                },
    ]
ENM_REPO_NAMES = [
        '3pp',
        'ENM', 'ENM_asrstream', 'ENM_automation', 'ENM_common',
        'ENM_db', 'ENM_eba', 'ENM_ebsstream', 'ENM_esnstream',
        'ENM_events', 'ENM_models', 'ENM_ms', 'ENM_scripting',
        'ENM_services', 'ENM_streaming']

def add_get_upgrade_type_option():
    """Function to mock adding of the action get_upgrade_type.
    :return: Command argument to_state_litp_version with incorrect format
    :rtype: String
    """
    return ' --action get_upgrade_type'


def add_create_backup_option():
    """Function to mock adding of the action create_backup.
    :return: Command action create_backup
    :rtype: String
    """
    return ' --action create_backup'


def add_to_state_litp_version_option_r6():
    """
    Function to mock adding of the parameter to_state_litp_version with a RHEL6
    TO_STATE LITP version.
    :return: Command action to_state_litp_version with RHEL6 R-state version
    :rtype: String
    """
    return " --to_state_litp_version " + TO_STATE_LITP_VERSION_R6


def add_to_state_litp_version_option_r7():
    """
    Function to mock adding of the parameter to_state_litp_version with a RHEL7
    TO_STATE LITP version.
    :return: Command action to_state_litp_version with RHEL7 R-state version
    :rtype: String
    """
    return " --to_state_litp_version " + TO_STATE_LITP_VERSION_R7


def add_to_state_litp_version_option_incorrect_format():
    """
    Function to mock adding of the parameter to_state_litp_version with a
    TO_STATE LITP version in an incorrect format.
    :return: Command action to_state_litp_version with incorrect R-State format
    :rtype: String
    """
    return (" --to_state_litp_version " +
            TO_STATE_LITP_VERSION_INCORRECT_FORMAT)


def mock_list_dir(dir_list):
    """
    Return a list of directory contents. Can be used for multiple directories.
    :param dir_list: Single List of directory contents or list of multiple
                     directory contents
    :rtype dir_list: list
    :return: List of directory contents
    :rtype: list
    """
    for _, dlist in enumerate(dir_list):
        return dir_list.pop(0)


def mock_run_command(cmd, timeout_secs=0, do_logging=True, **kwargs):
    """
    Function to mock run_command.
    :param cmd: The command to mock
    :rtype cmd: string
    :param timeout_secs: The command timeout
    :rtype timeout_secs: int
    :param do_logging: Logging switch
    :rtype do_logging: bool
    :param kwargs: Holder for extra parameters
    :rtype kwargs: various

    An Example of a kwargs parameter:
        :param kwargs.rc
        :rtype kwargs.rc: int
        :param kwargs.stdout: output string
        :rtype kwargs.stdout: string
    :return: returncode, stdout
    :rtype: int, string
    """
    return kwargs.pop('rc'), kwargs.pop('stdout')


def mock_get_all_items_by_type(path, item_type, items, hint):
    """
    Function to mock get_items_by_type. Will return a LITP Model string
    based on the input parameters.
    :param path: A path to search in the LITP model
    :type path: str
    :param item_type: Item type, e.g. san-emc
    :type item_type: str
    :param items: An initial list of items, it can be an empty list
    :items items: list
    :param hint: Holder for extra parameters
    :rtype hint: string

    :return: LITP Model profiles list
    :rtype: list
    """

    if (path == "/deployments" and item_type == "reference-to-os-profile" and
            hint == "2node_rhel6"):
        # Copy the original list to keep the original unchanged.
        litp_model_profiles = copy.deepcopy(LITP_MODEL_PROFILES_2_NODE_RHEL7)
        for profile in litp_model_profiles:
            profile['data']['properties']['version'] = "rhel6"
            profile['data']['state'] = "Applied"
        return [litp_model_profiles]

    if (path == "/deployments" and item_type == "reference-to-os-profile" and
            hint == "2node_hybrid"):
        # Copy the original list to keep the original unchanged.
        litp_model_profiles = copy.deepcopy(LITP_MODEL_PROFILES_2_NODE_RHEL7)
        litp_model_profiles[1]['data']['properties']['version'] = "rhel6"
        litp_model_profiles[1]['data']['state'] = "Applied"
        return [litp_model_profiles]

    return [LITP_MODEL_PROFILES_2_NODE_RHEL7]


class TestRh7UpgradeEnm(TestCase):
    """Test the rh7_upgrade_enm script"""

    CMD_TIMEOUT = 14400

    def setUp(self):
        self.upgrader = Rh7EnmUpgrade()
        self.upgrader.set_verbosity_level()
        self.upgrader.tracker = ''

    def mktmpfile(self, filename):
        filepath = os.path.join(self.tmpdir, filename)
        touch(filepath)
        return filepath

    def mktmpdir(self, dirname):
        if exists(dirname):
            shutil.rmtree(dirname, ignore_errors = False)
        os.makedirs(dirname)

    def rmtmpdir(self, dirname):
        try:
            shutil.rmtree(dirname)  # delete directory
        except OSError as exc:
            if exc.errno != errno.ENOENT:  # ENOENT - no such file or directory
                raise  # re-raise exception

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_elect_files')
    @patch('rh7_upgrade_enm.copy_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('platform.dist', MagicMock())
    @patch('__builtin__.open')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_yum_repo_bkup_dirs')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_create_backup_data1(self, m_getsize, m_exists,
                                 m_get_yum_repo_bkup_dirs, m_open,
                                 mock_run_command, mock_copy_file,
                                 mock_elect):
        m_getsize.return_value = 10
        m_exists.return_value = True
        mock_elect.return_value = []
        m_get_yum_repo_bkup_dirs.return_value = []
        mock_run_command.return_value = (0,'')
        mock_copy_file.return_value = None
        platform.dist.return_value = ('redhat', '6.10', 'Santiago')

        self.upgrader._get_backup_esmon_data = Mock()
        self.upgrader._get_backup_litp_state = Mock()
        self.upgrader._create_backup_data()
        self.assertTrue(m_open.called)
        self.assertTrue(mock_run_command.called)

    @patch('platform.dist', MagicMock())
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_create_backup_data2(self, m_getsize, m_exists):
        platform.dist.return_value = ('redhat', '6.10', 'Santiago')
        m_exists.return_value = True
        m_getsize.return_value = 0
        self.assertRaises(SystemExit, self.upgrader._create_backup_data)

    @patch('rh7_upgrade_enm.copy_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('platform.dist', MagicMock())
    @patch('__builtin__.open')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_yum_repo_bkup_dirs')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('glob.glob')
    def test_create_backup_data3(self, m_globs, m_getsize, m_exists,
                                 m_get_yum_repo_bkup_dirs, m_open,
                                 mock_run_command, mock_copy_file):

        zfname = 'zero_file.log'
        nzfname = 'non_zero_file.log'
        def mock_getsize_hndlr(path):
            if path.startswith(zfname):
                return 0
            else:
                return 10

        platform.dist.return_value = ('redhat', '6.10', 'Santiago')
        m_getsize.side_effect = mock_getsize_hndlr
        m_exists.return_value = True
        m_get_yum_repo_bkup_dirs.return_value = []
        mock_run_command.return_value = (0,'')
        mock_copy_file.return_value = None
        m_globs.return_value = [nzfname, zfname]

        self.upgrader._get_backup_litp_state = Mock(return_value='bkup1')
        self.upgrader._get_backup_esmon_data = Mock(return_value='bkup2')

        self.upgrader._create_backup_data()
        self.assertTrue(m_open.called)
        self.assertTrue(mock_run_command.called)

        expected = \
"""F /opt/ericsson/enminst/runtime/enm_deployment.xml
F /etc/mcollective/server_public.pem
F /etc/mcollective/server_private.pem
F /opt/ericsson/nms/litp/keyset/keyset1
F /opt/ericsson/nms/litp/etc/litp_shadow
F /root/.ssh/vm_private_key
F /root/.ssh/vm_private_key.pub
F /etc/enm-version
F /opt/ericsson/enminst/runtime/exported_enm_from_state_deployment.xml
F /opt/ericsson/enminst/runtime/previous_enm_deployment.xml
F bkup1
F bkup2
F /var/tmp/mco_list_backup
F /etc/enm-history
F /opt/ericsson/enminst/log/cmd_arg.log
F /root/SecuredCLISecurityFile.xml
F /root/SecuredCLIXMLEncrypted.key
F {0}
D /var/lib/puppet/ssl/
D /etc/puppetdb/ssl/
D /etc/rabbitmq/ssl/
D /opt/SentinelRMSSDK/licenses/
D /var/spool/cron/
D /root/.emc/
""".format(nzfname + '.rhel6')

        fh = m_open.return_value.__enter__.return_value
        fh.write.assert_called_with(expected)

    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('rh7_upgrade_enm.copy_file')
    @patch('platform.dist', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_all_non_plugin_repo_paths')
    def test_create_backup_data4(self, m_get_all_non_plugin_repo_paths,
                                 mock_write_to_file, mock_cpfile, mock_getsize,
                                 mock_exists):

        mock_exists.return_value = True
        mock_getsize.return_value = 10
        m_get_all_non_plugin_repo_paths.return_value = [
            "/var/www/html/6.10/",
            "/var/www/html/7.6/",
            "/var/www/html/ENM/",
            "/var/www/html/ENM_asrstream/",
            "/var/www/html/ENM_automation/",
            "/var/www/html/ENM_common/",
            "/var/www/html/ENM_db/",
            "/var/www/html/ENM_eba/",
            "/var/www/html/ENM_ebsstream/",
            "/var/www/html/ENM_esnstream/",
            "/var/www/html/ENM_events/",
            "/var/www/html/ENM_models/",
            "/var/www/html/ENM_ms/",
            "/var/www/html/ENM_scripting/",
            "/var/www/html/ENM_services/",
            "/var/www/html/ENM_streaming/",
            "/var/www/html/3pp/"]
        platform.dist.return_value = ('redhat', '6.10', 'Santiago')
        mock_cpfile.return_value = None
        self.upgrader._get_backup_litp_state = Mock(return_value='bkf1')
        self.upgrader._get_backup_esmon_data = Mock(return_value='bkf2')
        self.upgrader._export_litp_model = Mock()
        self.upgrader._create_mco_peer_list_backup = Mock()

        self.upgrader._create_backup_data()

        expected = \
"""F /opt/ericsson/enminst/runtime/enm_deployment.xml
F /etc/mcollective/server_public.pem
F /etc/mcollective/server_private.pem
F /opt/ericsson/nms/litp/keyset/keyset1
F /opt/ericsson/nms/litp/etc/litp_shadow
F /root/.ssh/vm_private_key
F /root/.ssh/vm_private_key.pub
F /etc/enm-version
F /opt/ericsson/enminst/runtime/exported_enm_from_state_deployment.xml
F /opt/ericsson/enminst/runtime/previous_enm_deployment.xml
F bkf1
F bkf2
F /var/tmp/mco_list_backup
F /etc/enm-history
F /opt/ericsson/enminst/log/cmd_arg.log
F /root/SecuredCLISecurityFile.xml
F /root/SecuredCLIXMLEncrypted.key
D /var/lib/puppet/ssl/
D /etc/puppetdb/ssl/
D /etc/rabbitmq/ssl/
D /opt/SentinelRMSSDK/licenses/
D /var/spool/cron/
D /var/www/html/6.10/
D /var/www/html/7.6/
D /var/www/html/ENM/
D /var/www/html/ENM_asrstream/
D /var/www/html/ENM_automation/
D /var/www/html/ENM_common/
D /var/www/html/ENM_db/
D /var/www/html/ENM_eba/
D /var/www/html/ENM_ebsstream/
D /var/www/html/ENM_esnstream/
D /var/www/html/ENM_events/
D /var/www/html/ENM_models/
D /var/www/html/ENM_ms/
D /var/www/html/ENM_scripting/
D /var/www/html/ENM_services/
D /var/www/html/ENM_streaming/
D /var/www/html/3pp/
D /var/www/html/images/
D /var/www/html/vm_scripts/
D /root/.emc/
"""
        filename = '/opt/ericsson/enminst/runtime/rh7_upgrade_data_backup_list.txt'
        mock_write_to_file.assert_called_once_with(filename, expected)

    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('rh7_upgrade_enm.copy_file')
    @patch('platform.dist', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_all_non_plugin_repo_paths')
    def test_create_backup_data5(self, m_get_all_non_plugin_repo_paths,
                                 mock_write_to_file, mock_cpfile, mock_getsize,
                                 mock_exists):

        def optional_files_mocker(filepath):
            if filepath in ['/etc/enm-history',
                            '/opt/ericsson/enminst/log/cmd_arg.log',
                            '/root/SecuredCLISecurityFile.xml',
                            '/root/SecuredCLIXMLEncrypted.key',
                            '/root/.emc/']:
                return False
            return True

        mock_exists.side_effect = optional_files_mocker
        mock_getsize.return_value = 10
        m_get_all_non_plugin_repo_paths.return_value = [
            "/var/www/html/6.10/",
            "/var/www/html/7.6/",
            "/var/www/html/ENM/",
            "/var/www/html/ENM_asrstream/",
            "/var/www/html/ENM_automation/",
            "/var/www/html/ENM_common/",
            "/var/www/html/ENM_db/",
            "/var/www/html/ENM_eba/",
            "/var/www/html/ENM_ebsstream/",
            "/var/www/html/ENM_esnstream/",
            "/var/www/html/ENM_events/",
            "/var/www/html/ENM_models/",
            "/var/www/html/ENM_ms/",
            "/var/www/html/ENM_scripting/",
            "/var/www/html/ENM_services/",
            "/var/www/html/ENM_streaming/",
            "/var/www/html/3pp/"]
        platform.dist.return_value = ('redhat', '6.10', 'Santiago')
        mock_cpfile.return_value = None
        self.upgrader._get_backup_litp_state = Mock(return_value='bkf1')
        self.upgrader._get_backup_esmon_data = Mock(return_value='bkf2')
        self.upgrader._export_litp_model = Mock()
        self.upgrader._create_mco_peer_list_backup = Mock()

        self.upgrader._create_backup_data()

        expected = \
"""F /opt/ericsson/enminst/runtime/enm_deployment.xml
F /etc/mcollective/server_public.pem
F /etc/mcollective/server_private.pem
F /opt/ericsson/nms/litp/keyset/keyset1
F /opt/ericsson/nms/litp/etc/litp_shadow
F /root/.ssh/vm_private_key
F /root/.ssh/vm_private_key.pub
F /etc/enm-version
F /opt/ericsson/enminst/runtime/exported_enm_from_state_deployment.xml
F /opt/ericsson/enminst/runtime/previous_enm_deployment.xml
F bkf1
F bkf2
F /var/tmp/mco_list_backup
D /var/lib/puppet/ssl/
D /etc/puppetdb/ssl/
D /etc/rabbitmq/ssl/
D /opt/SentinelRMSSDK/licenses/
D /var/spool/cron/
D /var/www/html/6.10/
D /var/www/html/7.6/
D /var/www/html/ENM/
D /var/www/html/ENM_asrstream/
D /var/www/html/ENM_automation/
D /var/www/html/ENM_common/
D /var/www/html/ENM_db/
D /var/www/html/ENM_eba/
D /var/www/html/ENM_ebsstream/
D /var/www/html/ENM_esnstream/
D /var/www/html/ENM_events/
D /var/www/html/ENM_models/
D /var/www/html/ENM_ms/
D /var/www/html/ENM_scripting/
D /var/www/html/ENM_services/
D /var/www/html/ENM_streaming/
D /var/www/html/3pp/
D /var/www/html/images/
D /var/www/html/vm_scripts/
"""
        filename = '/opt/ericsson/enminst/runtime/rh7_upgrade_data_backup_list.txt'
        mock_write_to_file.assert_called_once_with(filename, expected)

    def test_timeout(self):
        timer = self.upgrader.Timeout(60)
        timer.get_time()
        timer.sleep_for(1)
        self.assertFalse(timer.has_time_elapsed())
        self.assertEquals(60 - timer.get_time_elapsed(),
                          timer.get_remaining_time())

    def test_verbose(self):
        self.upgrader.processed_args = Mock()
        self.upgrader.processed_args.verbose = True
        self.upgrader.set_verbosity_level()
        self.upgrader.processed_args.verbose = False
        self.upgrader.set_verbosity_level()

    def test_bool_arg_handling(self):
        self.upgrader.create_arg_parser()
        valid_bool_options = [('-v', 'verbose'),
                              ('--resume', 'resume'),
                              ('--hybrid_state', 'hybrid_state')]
        valid_args = [opt[0] for opt in valid_bool_options]
        processed = self.upgrader.parser.parse_args(valid_args)
        for _, param in valid_bool_options:
            self.assertTrue(getattr(processed, param, False))

    def test_str_arg_handling(self):
        self.upgrader.create_arg_parser()
        valid_str_args = ['to_state_enm', 'to_state_litp',
                          'model', 'sed', 'to_state_litp_version']
        valid_args = [val for arg in valid_str_args
                      for val in ('--{0}'.format(arg), 'aValue')]
        processed = self.upgrader.parser.parse_args(valid_args)
        for param in valid_str_args:
            self.assertEquals(getattr(processed, param, False), 'aValue')

    @patch('os.path.exists')
    def test_process_action(self, m_exists):
        m_exists.return_value = True
        for hndlr in ('_get_upgrade_type',
                      '_create_backup_data',
                      '_do_rh7_uplift',
                      '_process_restored_data',
                      '_validate_deployment',
                      '_perform_checks',
                      '_cmplt_sfha_uplift'):
            setattr(self.upgrader, hndlr, Mock(return_value=True))

        self.upgrader.create_arg_parser()

        test_data = {'rh7_uplift': {
                         'valid_args': ['to_state_enm', 'model',
                                        'to_state_litp', 'sed'],
                         'invalid_args': ['to_state_litp_version']},
                     'get_upgrade_type': {
                         'valid_args': ['to_state_litp_version'],
                         'invalid_args': ['sed', 'model']},
                     'validate_deployment': {
                         'valid_args': ['model'],
                         'invalid_args': ['to_state_litp_version', 'sed']}
                    }
        for action in ('create_backup',
                       'process_restored_data',
                       'perform_checks',
                       'complete_sfha_uplift'):
            test_data[action] = {'valid_args': [],
                                 'invalid_args': ['to_state_litp_version',
                                                  'sed', 'model']}

        for tkey, tdata in test_data.iteritems():
            # Required args present
            args = ['--action', tkey]
            args.extend([val for arg in tdata['valid_args']
                         for val in ('--{0}'.format(arg), 'aValue')])
            self.upgrader.processed_args = self.upgrader.parser.parse_args(args)
            self.upgrader.process_action()

            # Files do not exist
            if 'rh7_uplift' == tkey:
                m_exists.return_value = False
                self.assertRaises(SystemExit, self.upgrader.process_action)
                m_exists.return_value = True

            # Required and invalid args present
            args.extend([val for arg in tdata['invalid_args']
                         for val in ('--{0}'.format(arg), 'aValue')])
            self.upgrader.processed_args = self.upgrader.parser.parse_args(args)
            self.assertRaises(SystemExit, self.upgrader.process_action)

            # Required args not present
            if tdata['valid_args']:
                args = ['--action', tkey]
                self.upgrader.processed_args = self.upgrader.parser.parse_args(args)
                self.assertRaises(SystemExit, self.upgrader.process_action)

        for arg in ([],
                    ['--action', 'bogus']):
            self.upgrader.processed_args = self.upgrader.parser.parse_args(arg)
            self.assertRaises(SystemExit, self.upgrader.process_action)

    def test_assert_return_code(self):
        self.upgrader._assert_return_code(0, '')
        self.upgrader._assert_return_code(1, '', allowed_codes=[1])
        self.assertRaises(SystemExit, self.upgrader._assert_return_code, 1, '')

    def test_init_node_data(self):
        data1 = collections.OrderedDict()
        data1['d1'] = ['c1']
        data1['d2'] = ['c2', 'c3']

        data2 = collections.OrderedDict()
        data2['c1'] = collections.OrderedDict()
        data2['c1']['n1'] = None
        data2['c1']['n2'] = None
        data2['c2'] = collections.OrderedDict()
        data2['c2']['n3'] = None
        data2['c3'] = collections.OrderedDict()
        data2['c3']['n4'] = None
        data2['c3']['n5'] = None

        self.upgrader.litp = MagicMock()
        self.upgrader.litp.get_deployment_clusters.return_value = data1
        self.upgrader.litp.get_cluster_nodes.return_value = data2

        self.upgrader._init_node_data()

        expected = collections.OrderedDict()
        expected['d1'] = collections.OrderedDict()
        expected['d1']['c1'] = ['n1', 'n2']
        expected['d2'] = collections.OrderedDict()
        expected['d2']['c2'] = ['n3']
        expected['d2']['c3'] = ['n4', 'n5']

        self.assertEquals(self.upgrader.deps_clusters_nodes, expected)

    @patch('__builtin__.open')
    def test_write_to_file(self, m_open):
        filename = '/a/file/somewhere'
        content = 'Mary had a little lamb'
        self.upgrader._write_to_file(filename, content)
        m_open.assert_called_with(filename, 'w')
        handle = m_open.return_value.__enter__.return_value
        handle.write.assert_called_once_with(content)

    @patch('rh7_upgrade_enm.getgrnam')
    @patch('rh7_upgrade_enm.getpwnam')
    @patch('rh7_upgrade_enm.os.fchown')
    @patch('__builtin__.open')
    def test_write_to_file_with_user_group(
            self, m_open, m_fchown, m_getpwnam, m_getgrnam):
        """test_write_to_file_with_user_group"""
        filename = '/a/file/somewhere'
        content = 'Mary had a little lamb'
        m_user = "celery"
        m_group = "puppet"

        uid = 88
        gid = 99
        m_getpwnam.return_value = Mock(pw_uid=uid)
        m_getgrnam.return_value = Mock(gr_gid=gid)

        self.upgrader._write_to_file(
            filename, content, user=m_user, group=m_group)

        m_open.assert_called_with(filename, 'w')
        open_handle = m_open.return_value.__enter__.return_value
        open_handle.write.assert_called_once_with(content)
        m_getpwnam.assert_called_once_with(m_user)
        m_getgrnam.assert_called_once_with(m_group)
        m_fchown.assert_called_with(open_handle.fileno(), uid, gid)

    @patch('rh7_upgrade_enm.getgrnam', MagicMock())
    @patch('rh7_upgrade_enm.getpwnam', MagicMock())
    @patch('rh7_upgrade_enm.os.fchown', MagicMock())
    @patch('__builtin__.open')
    def test_write_to_file_failure(self, m_open):
        """test_write_to_file_failure"""

        filename = '/a/file/somewhere'
        content = 'Mary had a little lamb'

        m_open.side_effect = IOError

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._write_to_file(
                    filename, content, user='uuser', group='ggroup') == 1
            mock_error.assert_called_with(
                "***** FAILED: Could not write to file '{0}'. "
                "Do not proceed with the uplift. For more information, "
                "contact your local Ericsson support team. *****"
                .format(filename)
                )
            self.assertEqual(sysexit.exception.code, 1)

    @patch('rh7_upgrade_enm.getgrnam', MagicMock())
    @patch('rh7_upgrade_enm.getpwnam', MagicMock())
    @patch('rh7_upgrade_enm.os.fchown')
    @patch('__builtin__.open', MagicMock())
    def test_write_to_file_failure_update_details(self, m_fchown):
        """test_write_to_file_failure_update_details"""

        filename = '/a/file/somewhere'
        content = 'Mary had a little lamb'

        m_fchown.side_effect = KeyError

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._write_to_file(
                    filename, content, user='uuser', group='ggroup') == 1
            mock_error.assert_called_with(
                "***** FAILED: Could not set file ownership on {0}. "
                "Do not proceed with the uplift. For more "
                "information, contact your local Ericsson support team. *****"
                .format(filename)
                )
            self.assertEqual(sysexit.exception.code, 1)

    def test_run_command_set(self):
        self.upgrader._run_command = Mock(return_value=(0, ''))
        cmds = ['cmd1', 'cmd2']
        self.upgrader._run_command_set(cmds, 'preamble')

    def test_printers(self):
        self.upgrader._print_success('text')
        self.upgrader._print_error('text')
        self.upgrader._print_error('text', add_suffix=False)
        self.upgrader._print_message('text')

        self.upgrader.current_stage = None
        self.upgrader._print_stage_start()
        self.upgrader._print_stage_failure()
        self.upgrader._print_stage_success()

        self.upgrader.current_stage = {'idx': 0, 'label': 'Test'}
        self.upgrader._print_stage_start()
        self.upgrader._print_stage_failure()
        self.upgrader._print_stage_success()

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_stg_from_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    def test_print_stage_success_disruption(self, mock_write_file,
                                            mock_read_file):
        self.upgrader.current_stage = {'idx': '05', 'label': 'Test'}

        tracker = '/tmp/.rh7_uplift_tracker'
        self.upgrader.tracker = tracker

        mock_read_file.return_value = '04'
        text = 'stage was successful'

        self.upgrader._print_stage_success(text)
        mock_write_file.assert_called_once_with(tracker, '05')

        # ----

        mock_read_file.reset_mock()
        mock_read_file.return_value = self.upgrader.current_stage['idx']
        self.assertRaises(SystemExit,
                          self.upgrader._print_stage_success, text)

        # ----
        mock_read_file.reset_mock()
        mock_read_file.return_value = ''
        self.upgrader._print_stage_success(text)

    @patch('glob.glob')
    @patch('os.path.getctime')
    @patch('os.path.exists')
    def test_get_backup_litp_state(self, m_exists, m_getctime, m_glob):
        def mock_run_command(cmd, timeout_secs=0, do_logging=True):
            return (0, '')

        bkups = ('bkup1.txt', 'bkup2.txt')

        self.upgrader._run_command = mock_run_command
        m_exists.return_value = True
        m_glob.return_value = bkups
        m_getctime.return_value = '1610126577.409477'

        litp_bkup = self.upgrader._get_backup_litp_state()
        self.assertEqual(bkups[0], litp_bkup)

    @patch('os.listdir')
    @patch('os.path.isdir')
    def test_get_elect_files_no_policies(self, mock_is_dir, mock_listdir):
        mock_is_dir.return_value = False
        elect_files = self.upgrader._get_elect_files()
        self.assertFalse(mock_listdir.called)
        self.assertEquals(elect_files, [])

    @patch('os.listdir')
    @patch('os.path.isdir')
    def test_get_elect_files_with_one_policy(self, mock_is_dir, mock_listdir):
        mock_is_dir.return_value = True
        mock_listdir.return_value = ['policy1.json']
        expected_files = ['/opt/ericsson/elasticsearch/policies/policy1.json',
                          '/etc/cron.d/policy1']
        elect_files = self.upgrader._get_elect_files()
        self.assertTrue(mock_listdir.called)
        self.assertEquals(elect_files, expected_files)

    @patch('os.listdir')
    @patch('os.path.isdir')
    def test_get_elect_files_with_policies(self, mock_is_dir, mock_listdir):
        mock_is_dir.return_value = True
        mock_listdir.return_value = ['policy2.json', 'policy1.json']
        expected_files = ['/opt/ericsson/elasticsearch/policies/policy2.json',
                          '/etc/cron.d/policy2',
                          '/opt/ericsson/elasticsearch/policies/policy1.json',
                          '/etc/cron.d/policy1']
        elect_files = self.upgrader._get_elect_files()
        self.assertTrue(mock_listdir.called)
        self.assertEquals(elect_files, expected_files)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_tarfile', MagicMock())
    def test_get_backup_esmon_data(self):
        snap_size = '21474836480B'   # ESMon LV is 20G

        def mock_run_command(cmd, timeout_secs=0, do_logging=True):
            return (0, snap_size)

        self.upgrader._run_command = mock_run_command

        self.upgrader._run_command_set = MagicMock(return_value=None)
        desc1 = 'Prepare ESMon data for backup'
        cmds1 = ['/opt/ericsson/nms/litp/lib/litpmnlibvirt/litp_libvirt_adaptor.py esmon stop-undefine --stop-timeout=45',
                 'mkdir -p /mnt/tmp_esmon_data',
                 'mount /dev/vg_root/vg1_fs_data /mnt/tmp_esmon_data']

        desc2 = 'Cleanup after backing up ESMon data'
        cmds2 = ['umount /mnt/tmp_esmon_data',
                 'rmdir /mnt/tmp_esmon_data',
                 'service esmon start']
        expected_calls = [call(c, d) for (c, d) in ((cmds1, desc1),
                                                    (cmds2, desc2))]

        self.upgrader._get_backup_esmon_data()

        self.upgrader._run_command_set.assert_has_calls(expected_calls)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_get_mco_peer_list(self, mock_cmd):
        """test_get_mco_peer_list"""

        mco_data = "node1\nnode2\ndb-1\ndb-2\nsvc-1\nsvc-2"
        mock_cmd.return_value = (0, mco_data)

        found_data = self.upgrader._get_mco_peer_list()

        self.assertEqual(mco_data, found_data, "Didn't return correct data")

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_get_mco_peer_list_failure(self, mock_cmd):
        """test_get_mco_peer_list_failure"""
        mock_cmd.return_value = (1, '-bash: mco: command not found')

        with self.assertRaises(SystemExit) as sysexit:
            assert self.upgrader._get_mco_peer_list() == 1
        self.assertEqual(sysexit.exception.code, 1)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    def test_create_mco_list_backup(self, mock_write_file, mock_cmd):
        """test_create_mco_list_backup"""

        mco_data = "node1\nnode2\ndb-1\ndb-2\nsvc-1\nsvc-2"
        mock_cmd.side_effect = partial(mock_run_command, rc=0, stdout=mco_data)

        self.upgrader._create_mco_peer_list_backup()

        mock_write_file.assert_called_once_with("/var/tmp/mco_list_backup",
                                                mco_data)

    @patch('platform.dist', MagicMock())
    def test_assert_rhel_version(self):
        test_data = [(('redhat', '6.10', 'Santiago'), '6.10', False),
                     (('redhat', '6.10', 'Santiago'), '7.9', True),
                     (('redhat', '7.9', 'Maipo'), '7.9', False),
                     (('redhat', '7.9', 'Maipo'), '6.10', True),
                     (('centos', '7.9', 'enm'), '7.9', True),
                     (('centos', '7.7', 'enm-inst'), '7.9', True)]

        for (ver_data, version, exception_expected) in test_data:
            platform.dist.return_value = ver_data
            try:
                self.upgrader._assert_rhel_version(version)
            except SystemExit:
                self.assertEqual(exception_expected, True)
            else:
                self.assertEqual(exception_expected, False)

    @patch('glob.glob')
    def test_el6_pkgs_present(self, m_glob):
        m_glob.return_value = []
        self.assertFalse(self.upgrader._is_present_infoscale_el6_pkgs('/fake'))

        m_glob.return_value = ['file1.rpm', 'file2.rpm']
        self.assertTrue(self.upgrader._is_present_infoscale_el6_pkgs('/real'))

    def test_vrts_pkgs_pattern(self):
        root = '/somewhere'
        self.assertEqual(self.upgrader._gen_vrts_pkgs_pattern(root),
                         '{0}/litp/3pp_el6/VRTS*.rpm'.format(root))

    def _get_vpaths_set_data1(self):
        self.upgrader.deps_clusters_nodes = collections.OrderedDict()
        self.upgrader.deps_clusters_nodes['dA'] = collections.OrderedDict()
        self.upgrader.deps_clusters_nodes['dA']['cA'] = ['nA', 'nB']
        self.upgrader.deps_clusters_nodes['dA']['cB'] = ['nC', 'nD']
        self.upgrader.deps_clusters_nodes['dB'] = collections.OrderedDict()
        self.upgrader.deps_clusters_nodes['dB']['cC'] = ['nE']

        return ['/deployments/dA/clusters/cA/nodes/nA/upgrade',
                '/deployments/dA/clusters/cA/nodes/nB/upgrade',
                '/deployments/dA/clusters/cB/nodes/nC/upgrade',
                '/deployments/dA/clusters/cB/nodes/nD/upgrade',
                '/deployments/dB/clusters/cC/nodes/nE/upgrade']

    def test_get_node_vpaths(self):
        expected = self._get_vpaths_set_data1()
        self.assertEquals(set(self.upgrader._get_node_upgrd_vpaths()),
                          set(expected))

    @patch('os.path.exists')
    @patch('os.path.ismount')
    def test_mount_iso(self, m_ismount, m_exists):
        m_exists.return_value = True
        m_ismount.return_value = False

        iso_path = '/X'
        mnt_dir = '/Y'
        expected_cmd = 'mount -o loop {0} {1}'.format(iso_path, mnt_dir)
        self.upgrader._run_command = MagicMock(return_value=(0, None))

        self.upgrader._mount_iso(iso_path, mnt_dir)

        self.upgrader._run_command.assert_has_call(expected_cmd)

        self.upgrader._run_command.reset_mock()

        self.upgrader.processed_args = Mock()
        self.upgrader.processed_args.to_state_litp = iso_path
        self.upgrader._mount_to_state_litp_iso(mnt_dir)
        self.upgrader._run_command.assert_has_call(expected_cmd)

        self.upgrader._run_command.reset_mock()
        self.upgrader.processed_args = Mock()
        self.upgrader.processed_args.to_state_enm = iso_path
        self.upgrader._mount_to_state_enm_iso(mnt_dir)
        self.upgrader._run_command.assert_has_call(expected_cmd)

    @patch('os.path.exists')
    @patch('os.path.ismount')
    @patch('os.rmdir')
    def test_umount_iso(self, m_rmdir, m_ismount, m_exists):
        m_exists.return_value = True
        m_ismount.return_value = True
        mnt_dir = '/Y'
        expected_cmd = 'umount {0}'.format(mnt_dir)
        self.upgrader._run_command = MagicMock(return_value=(0, None))
        self.upgrader._umount_iso('', mnt_dir, rm_mnt_dir=False)
        self.upgrader._run_command.assert_called_once_with(expected_cmd)

        self.upgrader._run_command.reset_mock()
        m_rmdir.return_value = 0
        self.upgrader._umount_iso('', mnt_dir, rm_mnt_dir=True)
        self.upgrader._run_command.assert_called_once_with(expected_cmd)

    @patch('os.path.exists')
    def test_cp_files(self, m_exists):
        m_exists.return_value = True
        src = './A/'
        dst = './B/'
        expected_cmd = 'cp -r {0} {1}'.format(src, dst)
        self.upgrader._run_command = MagicMock(return_value=(0, None))
        self.upgrader._cp_files(src, dst)
        self.upgrader._run_command.assert_called_once_with(expected_cmd)

        self.upgrader._run_command.reset_mock()

        expected_cmd = 'cp -r {0}litp/3pp_el6/VRTS*.rpm {1}'.format(src, dst)
        self.upgrader._fetch_infoscale_el6_pkgs(src, dst)
        self.upgrader._run_command.assert_called_once_with(expected_cmd)

    def test_set_dplymnts_upgrd(self):
        self._get_vpaths_set_data1()
        self.upgrader._run_command_set = MagicMock(return_value=(0, None))
        desc = 'Upgrade deployments'
        expected = ['litp upgrade -p /deployments/{0}'.format(d)
                    for d in self.upgrader.deps_clusters_nodes.keys()]
        self.upgrader._set_dplymnts_upgrd()
        self.upgrader._run_command_set.assert_called_once_with(expected, desc)

    def test_set_unset_upgrd_props(self):
        vpaths = self._get_vpaths_set_data1()
        self.upgrader._set_dplymnts_upgrd = MagicMock(return_value=0)

        pname = 'property1'

        self.upgrader._run_command_set = MagicMock(return_value=(0, None))
        desc1 = 'Set {0} to true'.format([pname])
        expected1 = ['litp update -p {0} -o {1}=true'.format(vpath, pname)
                     for vpath in vpaths]
        self.upgrader._set_upgrd_props([pname])
        self.upgrader._run_command_set.assert_called_once_with(expected1, desc1)

        self.upgrader._run_command_set.reset_mock()

        desc2 = 'Unset {0}'.format([pname])
        expected2 = ['litp update -p {0} -d {1}'.format(vpath, pname)
                      for vpath in vpaths]
        self.upgrader._unset_upgrd_props([pname])
        self.upgrader._run_command_set.assert_called_once_with(expected2, desc2)

    def test_create_litp_plan(self):
        self.upgrader._run_command = MagicMock(return_value=(0, None))
        for (initial_loc_tsks, no_loc_tsks) in ((False, False),
                                                (False, True),
                                                (True, False)):
            self.upgrader._create_litp_plan('', ilt=initial_loc_tsks, nlt=no_loc_tsks)

        secs = 7200
        expected_calls = [call('litp create_plan', timeout_secs=secs),
                          call('litp create_plan --no-lock-tasks', timeout_secs=secs),
                          call('litp create_plan --initial-lock-tasks', timeout_secs=secs)]
        self.assertEquals(expected_calls, self.upgrader._run_command.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_create_litp_plan_return_value(self, mock_run_cmd):
        mock_run_cmd.side_effect = [
             (0, ''),
             (1, 'DoNothingPlanError    Create plan failed: no tasks were '
                 'generated'),
             (1, 'DoNothingPlanError    Create plan failed: no tasks were '
                 'generated'),
             (1, '/deployments/d1/clusters/c1/services/cups\nValidationError '
                 '    Create plan failed: Number of nodes must match active '
                 'plus standby')
                                   ]
        plan_created = self.upgrader._create_litp_plan('')
        self.assertTrue(plan_created)

        plan_created = self.upgrader._create_litp_plan('', dnpe_allowed=True)
        self.assertFalse(plan_created)

        self.assertRaises(SystemExit, self.upgrader._create_litp_plan, '')

        self.assertRaises(SystemExit, self.upgrader._create_litp_plan, '')

    def test_run_plan(self):
        self.upgrader._run_command = MagicMock(return_value=(0, None))
        for resume in (False, True):
            self.upgrader._run_command.reset_mock()
            expected = 'litp run_plan'
            expected += ' --resume' if resume else ''
            self.upgrader._run_litp_plan('', resume=resume)
            self.upgrader._run_command.assert_called_once_with(expected)

    def test_monitor_litp_plan(self):
        '''test_monitor_litp_plan'''
        self.upgrader.litp = MagicMock(return_value=None)

        with patch.object(LOGGER, 'info') as mock_info:
            self.upgrader._monitor_litp_plan('Good')

            mock_info.assert_called_once_with(
                "LITP Good Plan completed successfully")

    def test_monitor_litp_plan_failure(self):
        '''test_monitor_litp_plan_failure'''
        self.upgrader.litp = MagicMock(return_value=None)
        self.upgrader.litp.monitor_plan.side_effect = LitpException

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._monitor_litp_plan('Bad') == 1
            mock_error.assert_called_with(
                "***** FAILED: LITP Bad Plan execution failed. Do not "
                "proceed with the uplift. For more information, contact your "
                "local Ericsson support team. *****")
            self.assertEqual(sysexit.exception.code, 1)

    def test_mng_plugins(self):
        pkgs = ['ERIClitpyum_CXP9030585',
                'ERIClitplibvirt_CXP9030547',
                'ERIClitpnetwork_CXP9030513',
                'ERIClitpvcs_CXP9030870',
                'ERIClitpopendj_CXP9031976']
        pkgs_str = ' '.join(pkgs)

        for verb in ('install', 'remove'):
            expected = 'yum {0} -y {1}'.format(verb, pkgs_str)
            self.upgrader._run_command = MagicMock(return_value=(0, None))
            self.upgrader._mng_plugins(verb, pkgs)
            self.upgrader._run_command.assert_called_once_with(expected)

    def test_get_to_state_iso_qcow_names(self):
        test_data = {'ERICrhel79lsbimage_CXP9041915': 'E',
                     'ERICrhel79jbossimage_CXP9041916': 'F',
                     'ERICsles15image_CXP9041763': 'G'}
        def mock_run_command(cmd):
            for tkey, tval in test_data.iteritems():
                if tkey in cmd:
                    return 0, '/some/directory/somewhere/' + tval
            return -1, ''

        self.upgrader._mount_to_state_enm_iso = Mock()
        self.upgrader._umount_iso = Mock()
        self.upgrader._run_command = mock_run_command
        output = {}
        expected = {}
        for tkey, tval in test_data.iteritems():
            name, _ = tkey.split('_')
            expected[name] = tval

        self.upgrader._get_to_state_iso_qcow_names(output)
        self.assertEquals(expected, output)

    def test_get_ms_uuid_val(self):
        test_uuid = '6000c29777d014bc8c0866fae16bc956'

        def mock_run_command(cmd):
            if '/dev/disk/by-id' in cmd:
                return 0, test_uuid

        self.upgrader._run_command = mock_run_command
        output = {}
        expected = {'uuid_ms_disk0': test_uuid}
        self.upgrader._get_ms_uuid_val(output)
        self.assertEquals(expected, output)


    @patch('os.path.getsize')
    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.copy_file', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file', MagicMock())
    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_tarfile', MagicMock())
    @patch('platform.dist', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_yum_repo_bkup_dirs')
    def test_create_backup(self, mock_get_yum_repo_bkup_dirs,
                           mock_cmd, mock_os_path, mock_exists, mock_getsize):
        """test_create_backup"""
        mock_getsize.return_value = 10
        mock_exists.return_value = True
        platform.dist.return_value = ('redhat', '6.10', 'Santiago')
        mock_os_path.return_value = True
        mock_get_yum_repo_bkup_dirs.return_value = []

        mock_cmd.side_effect = partial(
            mock_run_command, rc=0, stdout=FROM_STATE_LITP_VERSION_R6)

        args = '{0}{1}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                               add_create_backup_option())

        with patch.object(LOGGER, 'info') as mock_info:
            rh7_upgrade_enm.main(args.split())

            mock_info.assert_any_call(
                "***** PASSED: ESMon data successfully backed up "
                "/ericsson/enm/dumps/esmon_vol_data_backup.tgz *****")
            mock_info.assert_any_call(
                "***** PASSED: Contract/manifest file "
                "/opt/ericsson/enminst/runtime/rh7_upgrade_data_backup_list."
                "txt created *****")

        cmd_strs = ['/opt/ericsson/nms/litp/lib/litpmnlibvirt/litp_libvirt_adaptor.py esmon stop-undefine --stop-timeout=45',
                    'mkdir -p /mnt/tmp_esmon_data',
                    'mount /dev/vg_root/vg1_fs_data /mnt/tmp_esmon_data',
                    'umount /mnt/tmp_esmon_data',
                    'rmdir /mnt/tmp_esmon_data',
                    'service esmon start',
                    '/opt/ericsson/nms/litp/bin/litp_state_backup.sh /opt/ericsson/nms/litp/runtime',
                    'litp export -p / -f /opt/ericsson/enminst/runtime/exported_enm_from_state_deployment.xml',
                    '/usr/bin/mco find -W puppet_master=false']
        expected_calls = [call(s, timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)
                          for s in cmd_strs]

        self.assertEquals(len(expected_calls), mock_cmd.call_count)
        self.assertEquals(expected_calls, mock_cmd.call_args_list)

    def test_is_valid_r_state(self):
        for value in ['R2EV02', 'R3AZ09', 'R24Z01',
                      'r456abc99', 'R3A', 'R3A/1']:
            # MRRN external RState (truncated) for an IP1 = R3A/1
            self.assertTrue(self.upgrader._is_valid_r_state(value))
        for value in ['x2EV02', 'rAZ09', 'R1234Z01']:
            self.assertFalse(self.upgrader._is_valid_r_state(value))

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    def test_get_upgrade_type_rh6_to_rh6(
            self, mock_litprestclient, mock_read_file):
        """test_get_upgrade_type_rh6_to_rh6"""

        expected_upgrade_type = "1 (Legacy Upgrade)"

        mock_read_file.return_value = FROM_STATE_LITP_VERSION_R6

        mock_litprestclient.side_effect = \
            mock_get_all_items_by_type(path='/deployments',
                                       item_type='reference-to-os-profile',
                                       items=[], hint="2node_rhel6")

        args = '{0}{1}{2}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                  add_get_upgrade_type_option(),
                                  add_to_state_litp_version_option_r6())

        with patch.object(LOGGER, 'debug') as debug_info:
            rh7_upgrade_enm.main(args.split())

            debug_info.assert_any_call("This Upgrade type will be: {0}"
                                       .format(expected_upgrade_type))

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    def test_get_upgrade_type_rh6_to_rh7(
            self, mock_litprestclient, mock_read_file):
        """test_get_upgrade_type_rh6_to_rh7"""

        expected_upgrade_type = "2 (RH7 uplift)"

        mock_read_file.return_value = FROM_STATE_LITP_VERSION_R6

        mock_litprestclient.side_effect = \
            mock_get_all_items_by_type(path='/deployments',
                                       item_type='reference-to-os-profile',
                                       items=[], hint="2node_rhel6")

        args = '{0}{1}{2}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                  add_get_upgrade_type_option(),
                                  add_to_state_litp_version_option_r7())

        with patch.object(LOGGER, 'debug') as debug_info:
            rh7_upgrade_enm.main(args.split())

            debug_info.assert_any_call("This Upgrade type will be: {0}"
                                       .format(expected_upgrade_type))

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    def test_get_upgrade_type_rh7_to_rh7(
            self, mock_litprestclient, mock_read_file):
        """test_get_upgrade_type_rh7_to_rh7"""

        expected_upgrade_type = "3 (RH7 upgrade off)"

        mock_read_file.return_value = FROM_STATE_LITP_VERSION_R7

        mock_litprestclient.side_effect = \
            mock_get_all_items_by_type(path='/deployments',
                                       item_type='reference-to-os-profile',
                                       items=[], hint="")

        args = '{0}{1}{2}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                  add_get_upgrade_type_option(),
                                  add_to_state_litp_version_option_r7())

        with patch.object(LOGGER, 'debug') as debug_info:
            rh7_upgrade_enm.main(args.split())

            debug_info.assert_any_call("This Upgrade type will be: {0}"
                                       .format(expected_upgrade_type))

    @patch('rh7_upgrade_enm.platform.node')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_do_consul_action(self, mock_run_command, ms_node):
        """Test to set/unset Consul properties"""

        mock_run_command.return_value = (0, '')
        ms_node.return_value = 'ms'

        self.upgrader._do_consul_action('put', 'rh7_uplift_opendj')
        self.upgrader._do_consul_action('delete', 'rh7_uplift_opendj')

        expected_calls = [
            call("/usr/bin/consul kv put -http-addr=http://ms:8500 rh7_uplift_opendj "),
            call("/usr/bin/consul kv delete -http-addr=http://ms:8500 rh7_uplift_opendj ")
        ]

        self.assertEquals(2, mock_run_command.call_count)
        self.assertEqual(expected_calls, mock_run_command.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    def test_get_upgrade_type_hybrid(
            self, mock_litprestclient, mock_read_file):
        """test_get_upgrade_type_hybrid"""

        expected_upgrade_type = "4 (RH6-RH7 hybrid)"

        mock_read_file.return_value = FROM_STATE_LITP_VERSION_R7

        mock_litprestclient.side_effect = \
            mock_get_all_items_by_type(path='/deployments',
                                       item_type='reference-to-os-profile',
                                       items=[], hint="2node_hybrid")

        args = '{0}{1}{2}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                  add_get_upgrade_type_option(),
                                  add_to_state_litp_version_option_r7())

        with patch.object(LOGGER, 'debug') as debug_info:
            rh7_upgrade_enm.main(args.split())

            debug_info.assert_any_call("This Upgrade type will be: {0}"
                                       .format(expected_upgrade_type))

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    def test_get_upgrade_type_validate_from_state_r_version_failure(
            self, mock_read_file):
        """test_get_upgrade_type_validate_from_state_r_version_failure"""

        mock_read_file.return_value =\
            ("LITP 20.11 CSA 113 110 {0}"
             .format(TO_STATE_LITP_VERSION_INCORRECT_FORMAT))

        args = '{0}{1}{2}'.format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                                  add_get_upgrade_type_option(),
                                  add_to_state_litp_version_option_r7())

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert rh7_upgrade_enm.main(args.split()) == 1
            mock_error.assert_called_with(
                "***** FAILED: The current LITP R Version 'RRrrs0' is not in "
                "the correct format. Do not proceed with the uplift. For "
                "more information, contact your local Ericsson support team. "
                "*****")
            self.assertEqual(sysexit.exception.code, 1)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file', MagicMock())
    def test_get_upgrade_type_validate_to_state_r_version_failure(self):
        """test_get_upgrade_type_validate_to_state_r_version_failure"""

        args = ('{0}{1}{2}'
                .format(CMD_UPGRADE_ENM_DEFAULT_OPTIONS,
                        add_get_upgrade_type_option(),
                        add_to_state_litp_version_option_incorrect_format()))

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert rh7_upgrade_enm.main(args.split()) == 1
            mock_error.assert_called_with(
                "***** FAILED: The To-state R Version 'RRrrs0' is not in the "
                "correct format. Do not proceed with the uplift. For more "
                "information, contact your local Ericsson support team. *****")
            self.assertEqual(sysexit.exception.code, 1)

    @patch('__builtin__.open')
    def test_read_file_ioerror(self, mock_open):
        """test_read_file_ioerror"""

        mock_open.side_effect = IOError

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._read_file('/etc/litp-release') == 1
            mock_error.assert_called_with(
                "***** FAILED: Could not read the file '/etc/litp-release'. "
                "Do not proceed with the uplift. For more information, "
                "contact your local Ericsson support team. *****"
                )
            self.assertEqual(sysexit.exception.code, 1)

    @patch('__builtin__.open')
    def test_read_file_error(self, mock_open):
        """test_read_file_error"""

        mock_open.side_effect = Exception('general error')

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._read_file('/etc/litp-release') == 1
            mock_error.assert_called_with(
                "***** FAILED: Exception occurred: 'general error'. "
                "Do not proceed with the uplift. For more information, "
                "contact your local Ericsson support team. *****"
                )
            self.assertEqual(sysexit.exception.code, 1)

    @patch('rh7_upgrade_enm.EnmLmsHouseKeeping')
    @patch('os.path.exists')
    @patch('import_iso.main_flow')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_import_to_state_enm(self, mock_run_cmd, mock_flow, mock_exists,
                                 mock_hkeeper):
        self.upgrader._mount_to_state_enm_iso = Mock()
        mock_exists.return_value = False
        mock_run_cmd.return_value = (0, '')
        self.upgrader._umount_iso = Mock()
        self.upgrader._import_to_state_enm()

    def test_gen_sgmnts_data(self):
        rtdir = '/opt/ericsson/enminst/runtime/'
        expected = {'/infrastructure/storage/storage_providers': rtdir +
                    'to_state_infra_storage_providers.xml',
                    '/software': rtdir + 'to_state_software.xml',
                    '/infrastructure/storage/managed_files': rtdir +
                    'to_state_infra_managed_files.xml',
                    '/infrastructure/networking/routes': rtdir +
                    'to_state_infra_routes.xml',
                    '/infrastructure/storage/nfs_mounts': rtdir +
                    'to_state_infra_nfs_mounts.xml',
        '/infrastructure/storage/storage_profiles/ms_storage_profile': rtdir +
        'to_state_ms_infra_storage_profile.xml',
        '/ms': rtdir + 'to_state_ms.xml',
        '/infrastructure/systems/management_server': rtdir +
        'to_state_ms_infra_systems.xml',
        '/infrastructure/items': rtdir + 'to_state_infra_items.xml',
        '/infrastructure/service_providers': rtdir +
        'to_state_infra_service_providers.xml',
        '/infrastructure/system_providers': rtdir +
        'to_state_infra_system_providers.xml'}
        self.assertEquals(expected, self.upgrader._gen_sgmnts_data())

    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._gen_sgmnts_data')
    def test_create_to_state_dd_sgmnts(self, mock_gen_data, mock_exists):
        mock_gen_data.return_value = {'/foo': 'bar.xml'}
        mock_exists.return_value = True

        self.upgrader._run_command_set = MagicMock(return_value=None)
        self.upgrader.the_to_state_dd = 'the_to_state_dd.xml'

        cmds1 = ['systemctl stop litpd.service',
                 '/usr/local/bin/litpd.sh --purgedb',
                 'systemctl start litpd.service']
        cmds2 = ['litp load -p / -f the_to_state_dd.xml --merge']
        cmds3 = ['litp export -p /foo -f bar.xml']

        desc = 'Create To-state DD segments'
        expected = [call(cmds1 + cmds2 + cmds3 + cmds1, desc)]

        self.upgrader._create_to_state_dd_sgmnts()
        self.upgrader._run_command_set.assert_has_calls(expected)

        # ----
        self.upgrader.to_state_sgmnts_data = None
        self.upgrader._run_command_set.reset_mock()
        mock_gen_data.return_value = {'/foo': 'bar.xml',
                                      '/ms': 'ms.xml'}

        cmds3 = ['litp export -p /ms -f ms.xml',
                 'litp export -p /foo -f bar.xml']
        cmds4 = ["sed -i -e '/^ *<litp:sshd-config .*$/d' " + \
                        "-e '/^ *<permit_root_login>.*$/d' " + \
                        "-e '/^ *<\\/litp:sshd-config> *$/d' ms.xml"]
        expected = [call(cmds1 + cmds2 + cmds3 + cmds4 + cmds1, desc)]

        self.upgrader._create_to_state_dd_sgmnts()
        self.upgrader._run_command_set.assert_has_calls(expected)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_process_lms_services_failure(self, mock_cmd):
        """test_process_lms_services_failure"""

        services = ['wrong_service']

        mock_cmd.side_effect = partial(
            mock_run_command, rc=1, stdout='unknown service')

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._process_lms_services(
                    services, 'stop') == 1
            mock_error.assert_called_with(
                "***** FAILED: Failed to run command, error: stop systemd "
                "services: /usr/bin/systemctl stop wrong_service. Do not "
                "proceed with the uplift. For more information, contact your "
                "local Ericsson support team. *****")
            self.assertEqual(sysexit.exception.code, 1)

    @patch('rh7_upgrade_enm.os.path.isfile', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.platform.node')
    def test_create_hollow_manifests_not_ms(
            self, mock_platform_node, mock_read_file, mock_write_file):
        """test_create_hollow_manifests_not_ms"""

        mock_platform_node.return_value = 'ms1'
        plugin_host_list = ['node1', 'node2']

        mock_read_file.return_value = """ms1
node1
node2"""

        self.upgrader._create_hollow_manifests()

        # Verify _write_to_file was called for the Puppet Plugin Manifest files
        # with user 'celery' and group 'puppet'.
        basic_node_man = """node "{0}" {{

    class {{'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }}
}}"""
        for host in plugin_host_list:
            basic_man = basic_node_man.format(host)

            mock_write_file.assert_any_call(
                os.path.join(LITP_PUPPET_PLUGINS_MANIFEST_DIR,
                             "{0}.pp".format(host)),
                basic_man, user="celery", group="puppet")

    @patch('rh7_upgrade_enm.os.path.isfile', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.platform.node')
    def test_create_hollow_manifests_uppercase(
            self, mock_platform_node, mock_read_file, mock_write_file):
        """test_create_hollow_manifests_uppercase"""

        mock_platform_node.return_value = 'MS1'
        plugin_host_list = ['NODE1', 'Node2']

        mock_read_file.return_value = """MS1
NODE1
Node2"""

        self.upgrader._create_hollow_manifests()

        # Verify _write_to_file was called for the Puppet Plugin Manifest files
        # with user 'celery' and group 'puppet' and filenames are lowercase.
        basic_node_man = """node "{0}" {{

    class {{'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }}
}}"""
        for host in plugin_host_list:
            host = host.lower()
            basic_man = basic_node_man.format(host)

            mock_write_file.assert_any_call(
                os.path.join(LITP_PUPPET_PLUGINS_MANIFEST_DIR,
                             "{0}.pp".format(host)),
                basic_man, user="celery", group="puppet")

    @patch('rh7_upgrade_enm.os.path.isfile', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_mco_peer_list')
    def test_compare_mco_backup_list(self, mock_mco_find):
        """test_compare_mco_backup_list"""
        self.upgrader.mco_backup_list = ['node1', 'node2', 'node3']
        mock_mco_find.return_value = "node1\nnode2\nnode3"

        with patch.object(LOGGER, 'debug') as mock_debug:
            self.upgrader._compare_mco_backup_list()
            mock_debug.assert_called_with(
                "Current Peer Node list is the same as the list in the backup "
                "file."
                )

    @patch('rh7_upgrade_enm.os.path.isfile', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_mco_peer_list')
    def test_compare_mco_backup_list_failure(
            self, mock_mco_find):
        """test_compare_mco_backup_list_failure"""
        self.upgrader.mco_backup_list = ['node1', 'node2', 'node3']
        mock_mco_find.return_value = "node1\nnode2"

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._compare_mco_backup_list() == 1
            mock_error.assert_called_with(
                "***** FAILED: The Backup and Current Peer Node lists "
                "differ. Backup: ['node1', 'node2', 'node3']. "
                "Current ['node1', 'node2']. Do not proceed with the "
                "uplift. For more information, contact your local Ericsson "
                "support team. *****")
            self.assertEqual(sysexit.exception.code, 1)

    @patch('rh7_upgrade_enm.puppet_trigger_wait')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_mco_peer_list')
    @patch('rh7_upgrade_enm.platform.node')
    def test_trigger_puppet_and_wait(
            self, mock_platform_node, mock_mco_find, mock_trigger_and_wait):
        """test_trigger_puppet_and_wait"""

        mock_platform_node.return_value = 'ms1'
        mock_mco_find.return_value = """node1
node2"""
        mco_list = ['node1', 'node2']
        self.upgrader.mco_peer_list = mco_list

        expected_call = [call(True, self.upgrader.log.info, mco_list)]

        self.upgrader._trigger_puppet_and_wait()

        mock_trigger_and_wait.assert_has_calls(expected_call)

    @patch('rh7_upgrade_enm.os.path.isfile', MagicMock())
    @patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
           'trigger_and_wait')
    @patch('litp.core.rpc_commands.PuppetCatalogRunProcessor.'
           'update_config_version')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_mco_peer_list')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    @patch('rh7_upgrade_enm.os.path.exists')
    @patch('rh7_upgrade_enm.platform.node')
    def test_restore_mco_conn(
            self, mock_platform_node, mock_path_exists, mock_write_file,
            mock_cmd, mock_read_file, mock_mco_find,
            mock_update_config_version, mock_trigger_and_wait):
        """test_restore_mco_conn"""

        mock_platform_node.return_value = 'ms1'
        mock_path_exists.return_value = True

        services = ['puppet', 'puppetserver', 'puppetdb', 'rabbitmq-server',
                    'mcollective', 'litpd']

        mock_cmd.side_effect = partial(
            mock_run_command, rc=0, stdout='')
        mock_mco_find.return_value = """node1
node2"""

        plugin_host_list = ['node1', 'node2']

        mock_read_file.return_value = """node1
node2"""

        catalog_version = "2"
        mock_update_config_version.return_value = catalog_version
        expected_call = [call(catalog_version, ['node1', 'node2'])]

        self.upgrader._wait_for_services = Mock()

        self.upgrader._restore_mco_conn()

        # Ensure all services were stopped and started.
        for svc in services:
            mock_cmd.assert_any_call("/usr/bin/systemctl {0} {1}"
                                     .format('stop', svc),
                                     timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)
            mock_cmd.assert_any_call("/usr/bin/systemctl {0} {1}"
                                     .format('start', svc),
                                     timeout_secs=Rh7EnmUpgrade.CMD_TIMEOUT)

        # Verify _write_to_file was called for the Puppet Plugin Manifest files
        # with user 'celery' and group 'puppet'.
        basic_node_man = """node "{0}" {{

    class {{'litp::mn_node':
        ms_hostname => "ms1",
        cluster_type => "NON-CMW"
        }}
}}"""
        for host in plugin_host_list:
            basic_man = basic_node_man.format(host)

            mock_write_file.assert_any_call(
                os.path.join(LITP_PUPPET_PLUGINS_MANIFEST_DIR,
                             "{0}.pp".format(host)),
                basic_man, user="celery", group="puppet")

        mock_trigger_and_wait.assert_has_calls(expected_call)
        mock_cmd.assert_any_call("/usr/bin/puppet agent --test")

    @patch('tarfile.TarFile.getmember', MagicMock())
    @patch('tarfile.open', MagicMock())
    @patch('glob.glob')
    @patch('os.path.getctime')
    def test_restore_litp_state(self, m_getctime, m_glob):
        bkups = ('bkup1.txt', 'bkup2.txt')
        self.upgrader._run_command = mock_run_command
        m_glob.return_value = bkups
        m_getctime.return_value = '1610126577.409477'
        self.upgrader._restore_litp_db = MagicMock(return_value=None)

        self.upgrader._restore_litp_state()

        self.assertEquals(1, self.upgrader._restore_litp_db.call_count)
        self.assertEquals(1, m_glob.call_count)
        self.assertEquals(2, m_getctime.call_count)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_purge_persistent_tasks(self, mock_run_command):
        """test _purge_persistent_tasks"""

        mock_run_command.return_value = (0,'')

        self.upgrader._purge_persistent_tasks()

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -c '\
                 '\\\"delete from persisted_tasks\\\"\"',
                timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_purge_persistent_tasks_hardened(self, mock_run_command, mock_exists):
        """test _purge_persistent_tasks hardened """

        mock_run_command.return_value = (0,'')
        mock_exists.return_value = True
        self.upgrader._get_hostname = Mock(return_value='ms1')
        self.upgrader._purge_persistent_tasks()

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -h ms1 -c \\\"delete from persisted_tasks\\\"\"',
                timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_update_apd(self, mock_run_command):
        """test_update_apd"""

        mock_run_command.return_value = (0,'')

        self.upgrader._update_apd()

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -c \\\"update model set '\
        'applied_properties_determinable=\'t\' where model_id=\'LIVE\' '\
        'and class_name=\'ModelItem\'\\\"\"',
                timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_update_apd_hardened(self, mock_run_command, mock_exists):
        """test_update_apd hardened"""

        mock_exists.return_value = True
        mock_run_command.return_value = (0,'')
        self.upgrader._get_hostname = Mock(return_value='ms1')

        self.upgrader._update_apd()

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -h ms1 -c \\\"update model set '\
        'applied_properties_determinable=\'t\' where model_id=\'LIVE\' '\
        'and class_name=\'ModelItem\'\\\"\"',
                timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch("rh7_upgrade_enm.Rh7EnmUpgrade.HTML_DIR",'/tmp/TestRh7UpgradeEnm')
    def test_get_enm_repo_names_from_paths(self):
        self.tmpdir = os.path.join(gettempdir(), 'TestRh7UpgradeEnm')

        self.mktmpdir(self.tmpdir)
        Rh7EnmUpgrade.HTML_DIR = self.tmpdir

        tmpdir1 = os.path.join(self.tmpdir, 'ENM_rhel7', 'repodata')
        self.mktmpdir(tmpdir1)
        touch(os.path.join(tmpdir1, 'repomd.xml'))

        tmpdir2 = os.path.join(self.tmpdir, 'ENM', 'repodata')
        self.mktmpdir(tmpdir2)
        touch(os.path.join(tmpdir2, 'repomd.xml'))

        tmpdir3 = os.path.join(self.tmpdir, 'litp', 'repodata')
        self.mktmpdir(tmpdir3)
        self.mktmpfile(os.path.join(tmpdir3, 'repomd.xml'))

        tmpdir4 = os.path.join(self.tmpdir, 'ENM_common', 'repodata')
        self.mktmpdir(tmpdir4)
        self.mktmpfile(os.path.join(tmpdir4, 'repomd.xml'))

        tmpdir5 = os.path.join(self.tmpdir, 'ENM_common_rhel7', 'repodata')
        self.mktmpdir(tmpdir5)
        self.mktmpfile(os.path.join(tmpdir5, 'repomd.xml'))

        actual_names = self.upgrader._get_enm_repo_names_from_paths()
        expected_names = ['ENM', 'ENM_common']
        self.assertSequenceEqual(actual_names, expected_names)

        self.rmtmpdir(self.tmpdir)

    @patch("rh7_upgrade_enm.Rh7EnmUpgrade.HTML_DIR",'/tmp/TestRh7UpgradeEnm')
    def test_get_all_non_plugin_repo_paths(self):
        self.tmpdir = os.path.join(gettempdir(), 'TestRh7UpgradeEnm')

        self.mktmpdir(self.tmpdir)
        Rh7EnmUpgrade.HTML_DIR = self.tmpdir

        tmpdir1 = os.path.join(self.tmpdir, 'testrepo1_root', 'repodata')
        self.mktmpdir(tmpdir1)
        touch(os.path.join(tmpdir1, 'repomd.xml'))

        tmpdir2 = os.path.join(self.tmpdir, 'testrepo2_root', 'repodata')
        self.mktmpdir(tmpdir2)
        touch(os.path.join(tmpdir2, 'repomd.xml'))

        tmpdir3 = os.path.join(self.tmpdir, 'litp', 'repodata')
        self.mktmpdir(tmpdir3)
        self.mktmpfile(os.path.join(tmpdir3, 'repomd.xml'))

        tmpdir4 = os.path.os.path.join(self.tmpdir, 'litp_plugins', 'repodata')
        self.mktmpdir(tmpdir4)

        actual_paths = self.upgrader._get_all_non_plugin_repo_paths()
        expected_paths = [os.path.join(self.tmpdir,'testrepo1_root',''),
                          os.path.join(self.tmpdir,'testrepo2_root',''),]
        self.assertSequenceEqual(actual_paths, expected_paths)

        self.rmtmpdir(self.tmpdir)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_enm_repo_names_from_paths')
    @patch('rh7_upgrade_enm.LitpRestClient.update')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    def test_migrate_repo_urls(self, mock_litprestclient_get_all,
                                     mock_litprestclient_update,
                                     mock__get_enm_repo_names_from_paths):
        """test _migrate_repo_urls"""

        mock__get_enm_repo_names_from_paths.return_value = ENM_REPO_NAMES

        def litprestclient_get_all_side_effect(*args, **kwargs):

            if '/software' in args[0] and\
            'yum-repository' in args[1]:
                return LITP_YUM_REPOS
            if '/software' in args[0] and\
            'vm-yum-repo' in args[1]:
                return LITP_VM_YUM_REPOS
            if '/ms' in args[0] and 'vm-yum-repo' in args[1]:
                return LITP_MS_VM_YUM_REPOS

        mock_litprestclient_get_all.side_effect = \
        litprestclient_get_all_side_effect
        mock_litprestclient_update.return_value = 0
        mock_run_command.return_value = (0,'')

        self.upgrader._migrate_repo_urls()

        expected_litprestclient_update_calls = [
           call('/software/items/custom_model_repo',
                {'ms_url_path': u' /ENM_models_rhel7/'}),
            call('/ms/services/customized/vm_yum_repos/3pp',
                {'base_url': u'http://10.247.246.2/3pp_rhel7/'}),
            call('/software/services/oneflowca/vm_yum_repos/common',
                 {'base_url': u'http://10.247.246.2/ENM_common_rhel7/'}),
            ]

        self.assertEquals(3, mock_litprestclient_update.call_count)
        self.assertEquals(expected_litprestclient_update_calls,
                          mock_litprestclient_update.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('rh7_upgrade_enm.LitpRestClient.update')
    @patch('rh7_upgrade_enm.LitpRestClient.get_items_by_type')
    def test_migrate_forwarding_delay(self, mock_litprestclient_get_all,
                                      mock_litprestclient_update,
                                      mock_run_command):
        """test_migrate_forwarding_delay stage"""

        def litprestclient_get_all_side_effect(*args, **kwargs):

            if '/deployments' in args[0] and 'bridge' in args[1]:
                return LITP_BRIDGES
            if '/ms' in args[0] and 'bridge' in args[1]:
                return LITP_MS_BRIDGES

        mock_litprestclient_get_all.side_effect = \
        litprestclient_get_all_side_effect
        mock_litprestclient_update.return_value = 0
        mock_run_command.return_value = (0,'')

        self.upgrader._migrate_forwarding_delay()
        expected_litprestclient_update_calls = [
            call('/deployments/enm/clusters/svc_cluster/nodes/svc-1/network_interfaces/br3',
                  {'forwarding_delay': '4'}),
            call('/ms/network_interfaces/br1', {'forwarding_delay': '30'})]
        expected_run_command_calls = [
            call('sudo su - postgres -c "psql -d litp -c '\
                 '\\"update model set state=\'Initial\' where vpath like \'%\' '\
                 'and model_id=\'LIVE\'\\""', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)
        self.assertEquals(2, mock_litprestclient_update.call_count)
        self.assertEquals(expected_litprestclient_update_calls,
                          mock_litprestclient_update.call_args_list)

    @patch('rh7_upgrade_enm.LitpRestClient.delete_path')
    @patch('rh7_upgrade_enm.LitpRestClient.delete_property')
    def test_remove_items_from_model(self, mock_litprestclient_delete_prop,
                                      mock_litprestclient_delete_path):
        """test _remove_items_from_model"""

        items=[('/software/item1', None),
               ('/doesnt_exist_path', None),
               ('/software/item1', 'doesnt_exist_prop'),
               ('/ms/item1', None),
               ('/ms/item2', 'property1')]

        def mock_litprestclient_delete_path_side_effect(*args, **kwargs):

            if 'doesnt_exist_path' in args[0]:
                return False
            else:
                return True
        mock_litprestclient_delete_path.side_effect = \
                mock_litprestclient_delete_path_side_effect

        def mock_litprestclient_delete_prop_side_effect(*args, **kwargs):

            if 'doesnt_exist_prop' in args[1]:
                return False
            else:
                return True

        mock_litprestclient_delete_prop.side_effect = \
                mock_litprestclient_delete_prop_side_effect

        self.upgrader._remove_items_from_model(items)

        expected_litprestclient_delete_path_calls = [
            call('/software/item1'),
            call('/doesnt_exist_path'),
            call('/ms/item1')]
        self.assertEquals(expected_litprestclient_delete_path_calls,
                          mock_litprestclient_delete_path.call_args_list)

        expected_litprestclient_delete_prop_calls = [
            call('/software/item1','doesnt_exist_prop'),
            call('/ms/item2', 'property1')]
        self.assertEquals(expected_litprestclient_delete_prop_calls,
                          mock_litprestclient_delete_prop.call_args_list)


        self.upgrader._remove_items_from_model(items, ms_only=True)

        expected_litprestclient_delete_path_calls = [
            call('/software/item1'),
            call('/doesnt_exist_path'),
            call('/ms/item1'),
            call('/ms/item1')]
        self.assertEquals(expected_litprestclient_delete_path_calls,
                          mock_litprestclient_delete_path.call_args_list)

        expected_litprestclient_delete_prop_calls = [
            call('/software/item1','doesnt_exist_prop'),
            call('/ms/item2', 'property1'),
            call('/ms/item2', 'property1')]
        self.assertEquals(expected_litprestclient_delete_prop_calls,
                          mock_litprestclient_delete_prop.call_args_list)

    @patch('os.path.isfile')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._remove_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_create_xml_diff_file(self, mock_run_command,
                                        mock_remove_file,
                                        mock_isfile):
        """test _create_xml_diff_file"""
        mock_isfile.return_value = True
        mock_run_command.return_value = (0,'')
        mock_remove_file.return_value = None

        self.upgrader._create_xml_diff_file('from_state.xml', 'to_state.xml')

        self.assertEquals(1, mock_run_command.call_count)
        expected_run_command_calls = [
            call('/opt/ericsson/dstutilities/bin/dst_dd_delta_generator.sh '
                 'from_state.xml to_state.xml '
                 '/opt/ericsson/enminst/runtime/output_enm_deployment.txt',
                  timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)
        mock_remove_file.assert_called_once_with(Rh7EnmUpgrade.DELTA_OUTPUT)

    @patch("rh7_upgrade_enm.Rh7EnmUpgrade.DELTA_OUTPUT",
           '/tmp/output_enm_deployment.txt')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_parse_model_packages_from_diff_output(self, mock_run_command):
        """test_parse_model_packages_from_diff"""

        mock_run_command.return_value = (0,'type: model-package')
        self.tmpdir = os.path.join(gettempdir(), 'TestRh7UpgradeEnm')
        self.mktmpdir(self.tmpdir)

        deltafile = self.mktmpfile(self.upgrader.DELTA_OUTPUT)
        # no items to remove
        with open(deltafile, 'w') as f:
            f.write('y property@/path/to/item')
        result = self.upgrader._parse_model_packages_from_diff()
        self.assertListEqual(result, [])
        # no items to remove
        with open(deltafile, 'w') as f:
            f.write('y /path/to/item')
        result = self.upgrader._parse_model_packages_from_diff()
        self.assertListEqual(result, [])
        # no item to remove
        with open(deltafile, 'w') as f:
            f.write('n /software/items/model_package/packages/present')
        result = self.upgrader._parse_model_packages_from_diff()
        self.assertListEqual(result, [('/software/items/model_package/packages/present', None)])
        # no item to remove
        mock_run_command.return_value = (0,'    InvalidLocationError    Not found')
        with open(deltafile, 'w') as f:
            f.write('n /software/items/model_package/packages/notpresent')
        result = self.upgrader._parse_model_packages_from_diff()
        self.assertListEqual(result, [])
        # empty file
        with open(deltafile, 'w') as f:
            f.write('')
        result = self.upgrader._parse_model_packages_from_diff()
        self.assertListEqual(result, [])

        self.rmtmpdir(self.tmpdir)

    @patch("rh7_upgrade_enm.Rh7EnmUpgrade.DELTA_OUTPUT",
           '/tmp/output_enm_deployment.txt')
    def test_parse_deploy_diff_output(self):
        """test_parse_deploy_diff_output"""

        self.tmpdir = os.path.join(gettempdir(), 'TestRh7UpgradeEnm')
        self.mktmpdir(self.tmpdir)

        deltafile = self.mktmpfile(self.upgrader.DELTA_OUTPUT)
        with open(deltafile, 'w') as f:
            f.write('y property@/path/to/item')
        result = self.upgrader._parse_deploy_diff_output()
        self.assertListEqual(result, [('/path/to/item', 'property')])
        # only path to remove
        with open(deltafile, 'w') as f:
            f.write('y /path/to/item')
        result = self.upgrader._parse_deploy_diff_output()
        self.assertListEqual(result, [('/path/to/item', None)])
        # no items to remove
        with open(deltafile, 'w') as f:
            f.write('n /path/to/item')
        result = self.upgrader._parse_deploy_diff_output()
        self.assertListEqual(result, [])
        # empty file
        with open(deltafile, 'w') as f:
            f.write('')
        result = self.upgrader._parse_deploy_diff_output()
        self.assertListEqual(result, [])

        self.rmtmpdir(self.tmpdir)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_set_model_state(self, mock_run_command):
        """test _set_model_state"""

        mock_run_command.return_value = (0,'')

        self.upgrader._set_model_state('/deployments', 'Applied')

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -c \\\"update model '\
              'set state=\'Applied\' '\
              'where vpath like \'/deployments%\' and '\
              'model_id=\'LIVE\'\\\"\"', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_set_model_state_hardened(self, mock_run_command, mock_exists):
        """test _set_model_state"""

        mock_run_command.return_value = (0,'')
        mock_exists.return_value = True
        self.upgrader._get_hostname = Mock(return_value='ms1')

        self.upgrader._set_model_state('/deployments', 'Applied')

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -h ms1 -c \\\"update model '\
              'set state=\'Applied\' '\
              'where vpath like \'/deployments%\' and '\
              'model_id=\'LIVE\'\\\"\"', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_set_model_state_no_recurse(self, mock_run_command):
        """test _set_model_state"""

        mock_run_command.return_value = (0,'')

        self.upgrader._set_model_state('/deployments', 'Applied',
                                       recurse=False)

        expected_run_command_calls = [
            call('sudo su - postgres -c \"psql -d litp -c \\\"update model '\
              'set state=\'Applied\' '\
              'where vpath = \'/deployments\' and '\
              'model_id=\'LIVE\'\\\"\"', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_command.call_count)
        self.assertEquals(expected_run_command_calls,
                          mock_run_command.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_set_vcs_clustered_service_apd(self, mock_run_cmd):
        mock_run_cmd.return_value = (0, '')

        self.upgrader._set_vcs_clustered_service_apd('/software/services/s1',
                                                     'f')

        expected_run_cmd_calls = [
            call('sudo su - postgres -c \"psql -d litp -c \\\"update model '\
              'set applied_properties_determinable=\'f\' where model_id='\
              '\'LIVE\' and item_type_id=\'vcs-clustered-service\' and '\
              'vpath in (select grandparent.vpath from model child '\
              'inner join model parent on child.parent_vpath = parent.vpath '\
              'and child.model_id = parent.model_id '\
              'inner join model grandparent on parent.parent_vpath = '\
              'grandparent.vpath and parent.model_id = grandparent.model_id '\
              'where child.model_id=\'LIVE\' and child.source_vpath='\
              '\'/software/services/s1\')\\\"\"', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_cmd.call_count)
        self.assertEquals(expected_run_cmd_calls, mock_run_cmd.call_args_list)

    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_set_vcs_clustered_service_apd_hardened(self, mock_run_cmd, mock_exists):
        mock_run_cmd.return_value = (0, '')
        mock_exists.return_value = True
        self.upgrader._get_hostname = Mock(return_value='ms1')

        self.upgrader._set_vcs_clustered_service_apd('/software/services/s1',
                                                     'f')

        expected_run_cmd_calls = [
            call('sudo su - postgres -c \"psql -d litp -h ms1 -c \\\"update model '\
              'set applied_properties_determinable=\'f\' where model_id='\
              '\'LIVE\' and item_type_id=\'vcs-clustered-service\' and '\
              'vpath in (select grandparent.vpath from model child '\
              'inner join model parent on child.parent_vpath = parent.vpath '\
              'and child.model_id = parent.model_id '\
              'inner join model grandparent on parent.parent_vpath = '\
              'grandparent.vpath and parent.model_id = grandparent.model_id '\
              'where child.model_id=\'LIVE\' and child.source_vpath='\
              '\'/software/services/s1\')\\\"\"', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)]

        self.assertEquals(1, mock_run_cmd.call_count)
        self.assertEquals(expected_run_cmd_calls, mock_run_cmd.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._monitor_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._parse_deploy_diff_output')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_xml_diff_file')
    def test_post_redeploy_nodes(self, mock_create_xml_diff,
                                 mock_parse_diff_file,
                                 mock_create_plan, mock_run_plan, mock_monitor_plan):

        self.upgrader.litp = MagicMock()
        self.upgrader.litp.delete_path = MagicMock(return_value=True)
        self.upgrader.litp.delete_property = MagicMock(return_value=True)

        expected_remove_items = [
            ('/infrastructure/storage/storage_providers/sfs_service_sp1/'
             'pools/sfs_pool1/file_systems/managed_fs1', None),

            ('/infrastructure/storage/storage_providers/sfs_service_sp1/'
             'pools/sfs_pool1/file_systems/managed_fs2', None)
        ]

        mock_parse_diff_file.return_value = expected_remove_items

        self.upgrader._post_redeploy_nodes()

        self.upgrader.litp.delete_path.assert_has_calls(
            [call(item[0]) for item in expected_remove_items[:2]])

        self.upgrader.litp.delete_property.assert_has_calls(
            [call(item[0], item[1]) for item in expected_remove_items[2:]])

        mock_create_plan.assert_called_with('R+1', dnpe_allowed=True)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._monitor_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._parse_deploy_diff_output')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_xml_diff_file')
    def test_post_redeploy_nodes_no_plan(self, mock_create_xml_diff,
                                 mock_parse_diff_file,
                                 mock_create_plan, mock_run_plan, mock_monitor_plan):

        self.upgrader.litp = MagicMock()
        self.upgrader.litp.delete_path = MagicMock(return_value=True)
        self.upgrader.litp.delete_property = MagicMock(return_value=True)

        expected_remove_items = []

        mock_parse_diff_file.return_value = expected_remove_items

        self.upgrader._post_redeploy_nodes()

        self.upgrader.litp.delete_path.assert_not_called()

        self.upgrader.litp.delete_property.assert_not_called()

        mock_create_plan.assert_not_called()

    def test_load_sgmnts_ms_redeploy(self):
        """test _load_sgmnts_ms_redeploy stage"""

        self.upgrader._restore_litp_state = MagicMock(return_value=None)
        self.upgrader._update_apd = MagicMock(return_value=None)
        self.upgrader._migrate_forwarding_delay = MagicMock(return_value=None)
        self.upgrader._purge_persistent_tasks = MagicMock(return_value=None)
        self.upgrader._load_model = MagicMock(return_value=None)
        #self.upgrader._run_command_set = MagicMock(return_value=None)
        self.upgrader._remove_items_from_model = MagicMock(return_value=None)
        self.upgrader._set_model_state = MagicMock(return_value=None)
        self.upgrader._create_xml_diff_file = MagicMock(return_value=None)
        self.upgrader._parse_deploy_diff_output = MagicMock(return_value=None)
        self.upgrader._migrate_repo_urls = MagicMock(return_value=None)
        self.upgrader._parse_model_packages_from_diff = MagicMock(return_value=None)
        self.upgrader._load_sgmnts_ms_redeploy()

        expected_calls = [
            call('/opt/ericsson/enminst/runtime/to_state_infra_storage_providers.xml', '/infrastructure/storage'),
            call('/opt/ericsson/enminst/runtime/to_state_software.xml', '/'),
            call('/opt/ericsson/enminst/runtime/to_state_infra_managed_files.xml', '/infrastructure/storage'),
            call('/opt/ericsson/enminst/runtime/to_state_infra_routes.xml', '/infrastructure/networking'),
            call('/opt/ericsson/enminst/runtime/to_state_infra_nfs_mounts.xml', '/infrastructure/storage'),
            call('/opt/ericsson/enminst/runtime/to_state_ms_infra_storage_profile.xml', '/infrastructure/storage/storage_profiles'),
            call('/opt/ericsson/enminst/runtime/to_state_ms.xml', '/'),
            call('/opt/ericsson/enminst/runtime/to_state_ms_infra_systems.xml', '/infrastructure/systems'),
            call('/opt/ericsson/enminst/runtime/to_state_infra_items.xml', '/infrastructure'),
            call('/opt/ericsson/enminst/runtime/to_state_infra_service_providers.xml', '/infrastructure'),
            call('/opt/ericsson/enminst/runtime/to_state_infra_system_providers.xml', '/infrastructure')
            ]

        self.assertEquals(1, self.upgrader._restore_litp_state.call_count)
        self.assertEquals(1, self.upgrader._update_apd.call_count)
        self.assertEquals(1, self.upgrader._migrate_forwarding_delay.call_count)
        self.assertEquals(1, self.upgrader._purge_persistent_tasks.call_count)
        self.assertEquals(2, self.upgrader._create_xml_diff_file.call_count)
        self.assertEquals(2, self.upgrader._remove_items_from_model.call_count)
        self.assertEquals(1, self.upgrader._parse_model_packages_from_diff.call_count)
        self.assertEquals(1, self.upgrader._set_model_state.call_count)
        self.assertEquals(expected_calls, self.upgrader._load_model.call_args_list)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._remove_items_from_model')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._parse_deploy_diff_output')
    @patch('rh7_upgrade_enm.LitpRestClient.delete_path')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_xml_diff_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._load_model')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_model_state')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_load_to_state_model(
            self, mock_run_command, mock_litprestclient, mock_set_model_state,
            mock_load_model, mock_create_xml_diff,
            mock_litprestclient_delete_path, mock_parse_deploy_diff_output,
            mock_remove_items_from_model):
        '''test_load_to_state_model'''

        mock_run_command.return_value = (0,'')

        mock_litprestclient.side_effect = \
            mock_get_all_items_by_type(path='/deployments',
                                       item_type='reference-to-os-profile',
                                       items=[], hint="2node_rhel6")

        deployment_diff = [('/path/to/item', 'property')]
        mock_parse_deploy_diff_output.return_value = deployment_diff

        # Run the production code
        self.upgrader._load_to_state_model()

        mock_set_model_state.assert_called_with('', 'Initial')
        for profile in mock_litprestclient:
            self.upgrader.delete_path.assert_called_with(profile['path'])
        mock_load_model.assert_called_with(self.upgrader.ENM_DD)
        mock_create_xml_diff.assert_called_with(self.upgrader.ENM_PREVIOUS_DD,
                                                self.upgrader.ENM_DD)
        mock_remove_items_from_model.assert_called_with(deployment_diff)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._remove_dupe_es_resources')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._update_kickstart_template')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._monitor_litp_plan')
    @patch("rh7_upgrade_enm.Rh7EnmUpgrade._run_litp_plan")
    @patch("rh7_upgrade_enm.Rh7EnmUpgrade._create_litp_plan")
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._unset_upgrd_props')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_upgrd_props')
    @patch("rh7_upgrade_enm.HealthCheck", MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_redeploy_nodes(
            self, mock_cmd, mock_set_upgr_prop, mock_unset_upgr_prop,
            mock_create_litp_plan, mock_run_litp_plan, mock_monitor_litp_plan,
            mock_update_kickstart_template, mock_remove_dupe_es_res):
        '''test_redeploy_nodes'''

        self.upgrader.deps_clusters_nodes = \
            collections.OrderedDict([(u'd1', collections.OrderedDict([(u'c1', [u'n1', u'n2'])]))])

        self.upgrader._run_command_set = MagicMock(return_value=None)
        mock_cmd.side_effect = partial(
            mock_run_command, rc=0, stdout='')
        self.upgrader.litp = MagicMock(return_value=None)

        self.upgrader._redeploy_nodes()

        mock_create_litp_plan.assert_called_with('R', ilt=True)
        mock_run_litp_plan.assert_called_with('R', resume=False)
        mock_monitor_litp_plan.assert_called_with('R', resume=False)
        mock_set_upgr_prop.assert_called_with(['os_reinstall'])
        mock_unset_upgr_prop.assert_called_with(['os_reinstall'])
        expected_calls= [call(
            get_enable_cron_on_expiry_cmd(
               rh7_upgrade_enm.Rh7EnmUpgrade.RHEL7_SYSTEM_AUTH)),
            call(cmd_DISABLE_CRON_ON_EXPIRY)]
        mock_update_kickstart_template.assert_has_calls(expected_calls)
        mock_remove_dupe_es_res.assert_called_once()

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._remove_dupe_es_resources')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._update_kickstart_template')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._unset_upgrd_props')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_upgrd_props')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._monitor_litp_plan')
    @patch("rh7_upgrade_enm.Rh7EnmUpgrade._run_litp_plan")
    @patch("rh7_upgrade_enm.Rh7EnmUpgrade._create_litp_plan")
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_redeploy_nodes_resume(
            self, mock_cmd, mock_create_litp_plan, mock_run_litp_plan,
            mock_monitor_litp_plan, mock_set_upgr_prop, mock_unset_upgr_prop,
            mock_update_kickstart_template, mock_remove_dupe_es_res):
        '''test_redeploy_nodes_resume'''

        self.upgrader.processed_args = Mock(resume=True)

        self.upgrader._run_command_set = MagicMock(return_value=None)
        mock_cmd.side_effect = partial(
            mock_run_command, rc=0, stdout='')
        self.upgrader.litp = MagicMock(return_value=None)

        self.upgrader._redeploy_nodes()

        mock_run_litp_plan.assert_called_with('R', resume=True)
        mock_create_litp_plan.assert_not_called()
        mock_run_litp_plan.assert_called_with('R', resume=True)
        mock_monitor_litp_plan.assert_called_with('R', resume=True)
        mock_set_upgr_prop.assert_not_called()
        mock_unset_upgr_prop.assert_called_with(['os_reinstall'])

        expected_calls = [call(cmd_DISABLE_CRON_ON_EXPIRY)]
        mock_update_kickstart_template.assert_has_calls(expected_calls)
        mock_remove_dupe_es_res.assert_called_once()

    def test_remove_dupe_es_resources(self):
        dbhost1 = 'db-1'
        self.upgrader.sfha_nodes = {dbhost1: 'DB node 1',
                                    'db-2': 'DB node 2'}
        results1 = {'db-1': {'errors': '',
                             'data': {'retcode': 0}}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, results1))
        self.upgrader._remove_dupe_es_resources()

        dg_res = 'Res_DG_db_cluster_elasticsearch_clustered_service__c22c5abd'
        expected_call1 = call('mco rpc -I {0} enminst hares_display resource={1}'.format(dbhost1, dg_res))

        expected_calls = [call('mco rpc -I {0} vcs_cmd_api {1}'.format(dbhost1, cmd))
                          for cmd in [\
    'haconf haaction=makerw read_only=False',
    'hares_unlink parent=Res_App_db_cluster_elasticsearch_elasticsearch child=Res_Mnt_db_cluster_elasticsearch_clustered_service_3c5968b4',
    'hares_unlink parent=Res_Mnt_db_cluster_elasticsearch_clustered_service_3c5968b4 child={0}'.format(dg_res),
    'hares_unlink parent=Res_App_db_cluster_elasticsearch_elasticsearch child=Res_IP_db_cluster_elasticsearch_clustered_service__822195a7',
    'hares_unlink parent=Res_IP_db_cluster_elasticsearch_clustered_service__822195a7 child=Res_NIC_Proxy_db_cluster_elasticsearch_clustered_s_cd8e72bb']]

        expected_calls += [call('mco rpc -I {0} enminst {1}'.format(dbhost1, cmd))
                           for cmd in [\
    'hares_delete_no_offline resource=Res_IP_db_cluster_elasticsearch_clustered_service__822195a7',
    'hares_delete_no_offline resource=Res_Mnt_db_cluster_elasticsearch_clustered_service_3c5968b4',
    'hares_delete_no_offline resource={0}'.format(dg_res)]]

        expected_calls += [call('mco rpc -I {0} vcs_cmd_api {1}'.format(dbhost1, cmd))
                           for cmd in ['haconf haaction=dump read_only=True']]

        expected = [expected_call1] + expected_calls

        self.assertEqual(expected, self.upgrader._run_rpc_mco.mock_calls)

        # ----
        results2 = {'db-1': {'errors': 'VCS WARNING V-16-1-40130 Resource {0} does not exist in the local cluster'.format(dg_res),
                             'data': {'retcode': 1}}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, results2))
        self.upgrader._remove_dupe_es_resources()

        expected = [expected_call1]
        self.assertEqual(expected, self.upgrader._run_rpc_mco.mock_calls)

    @patch('os.geteuid')
    @patch('platform.dist', MagicMock())
    def test_do_rh7_uplift_failure_incorrect_user(self, m_geteuid):
        mock_run_command.return_value = (0, '')
        platform.dist.return_value = ('redhat', '7.9', 'Maipo')
        m_geteuid.return_value = 131

        with patch.object(LOGGER, 'error') as mock_error:
            with self.assertRaises(SystemExit) as sysexit:
                assert self.upgrader._do_rh7_uplift() == 1
            mock_error.assert_called_with(
                '***** FAILED: This script must be run as the root user. '
                'Do not proceed with the uplift. For more information, '
                'contact your local Ericsson support team. *****')
            self.assertEqual(sysexit.exception.code, 1)

    @patch('os.geteuid')
    @patch('platform.dist', MagicMock())
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_do_rh7_uplift(self, mock_run_command, m_geteuid):
        mock_run_command.return_value = (0, '')
        platform.dist.return_value = ('redhat', '7.9', 'Maipo')
        m_geteuid.return_value = 0

        self.upgrader.processed_args = Mock(action='rh7_uplift',
                                            hybrid_state=False,
                                            resume=False)

        self.upgrader._update_cmd_arg_log = Mock()
        self.upgrader._do_infoscale_plan = Mock()
        self.upgrader._create_to_state_dd_sgmnts = Mock()
        self.upgrader._create_to_state_dd = Mock()
        self.upgrader._do_infra_plan = Mock()
        self.upgrader._load_sgmnts_ms_redeploy = Mock()
        self.upgrader._redeploy_ms = Mock()
        self.upgrader._import_to_state_enm = Mock()
        self.upgrader._restore_mco_conn = Mock()
        self.upgrader._restore_esmon_data = Mock()
        self.upgrader._take_snaps = Mock()
        self.upgrader._upgrd_pre_chks_and_hlth_chks = Mock()
        self.upgrader._pre_nodes_push_artifacts = Mock()
        self.upgrader._pre_redeploy_nodes = Mock()
        self.upgrader._load_to_state_model = Mock()
        self.upgrader._redeploy_nodes = Mock()
        self.upgrader._post_redeploy_nodes = Mock()
        self.upgrader._post_upgrd = Mock()

        self.upgrader._do_rh7_uplift()

        self.assertTrue(self.upgrader._update_cmd_arg_log.called)
        self.assertTrue(self.upgrader._do_infoscale_plan.called)
        self.assertTrue(self.upgrader._create_to_state_dd_sgmnts.called)
        self.assertTrue(self.upgrader._create_to_state_dd.called)
        self.assertTrue(self.upgrader._load_sgmnts_ms_redeploy.called)
        self.assertTrue(self.upgrader._redeploy_ms.called)
        self.assertTrue(self.upgrader._restore_mco_conn.called)
        self.assertTrue(self.upgrader._restore_esmon_data.called)
        self.assertTrue(self.upgrader._take_snaps.called)
        self.assertTrue(self.upgrader._import_to_state_enm.called)
        self.assertTrue(self.upgrader._do_infra_plan.called)
        self.assertTrue(self.upgrader._upgrd_pre_chks_and_hlth_chks.called)
        self.assertTrue(self.upgrader._pre_nodes_push_artifacts)
        self.assertTrue(self.upgrader._pre_redeploy_nodes.called)
        self.assertTrue(self.upgrader._load_to_state_model.called)
        self.assertTrue(self.upgrader._redeploy_nodes.called)
        self.assertTrue(self.upgrader._post_redeploy_nodes.called)
        self.assertTrue(self.upgrader._post_upgrd.called)

    @patch('rh7_upgrade_enm.LitpRestClient.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file', MagicMock())
    def test_do_infra_plan(self, m_exists):

        m_exists.return_value = True

        xml_hdr = ("<?xml version='1.0' encoding='utf-8'?> " +
                   '<litp:root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' +
                   'xmlns:litp="http://www.ericsson.com/litp" ' +
                   'xsi:schemaLocation="http://www.ericsson.com/litp ' +
                   'litp-xml-schema/litp.xsd" id="root">')
        xml_ftr = '</litp:root>'
        sfs_fs_xml_tmplt = ('<litp:sfs-filesystem id="managed_fs2">' +
                            '<path>/vx/CIcdb-managed-fs1</path>' +
                            '<size>{0}</size>' +
                            '<litp:sfs-filesystem-exports-collection id="exports">' +
                            '<litp:sfs-export id="export1">' +
                            '<ipv4allowed_clients>1.2.3.4/16</ipv4allowed_clients>' +
                            '<options>rw,no_wdelay,no_root_squash</options>' +
                            '</litp:sfs-export>' +
                            '</litp:sfs-filesystem-exports-collection>' +
                            '</litp:sfs-filesystem>')
        sfs_fs_small_xml = sfs_fs_xml_tmplt.format('50M')
        sfs_fs_big_xml = sfs_fs_xml_tmplt.format('500M')

        ext4_fs_xml = ('<litp:file-system id="lv_test">' +
                       '<backup_policy>no_restore</backup_policy>' +
                       '<fsck_pass>2</fsck_pass>' +
                       '<mount_point>/x/y/z</mount_point>' +
                       '<size>2G</size>' +
                       '<snap_external>false</snap_external>' +
                       '<snap_size>0</snap_size>' +
                       '<type>ext4</type>' +
                       '</litp:file-system>')

        vxfs_fs_xml = ('<litp:file-system id="elastic_fs">' +
                       '<fsck_pass>2</fsck_pass>' +
                       '<mount_point>/a/b/c</mount_point>' +
                       '<size>500G</size>' +
                       '<snap_external>false</snap_external>' +
                       '<snap_size>4</snap_size>' +
                       '<type>vxfs</type>' +
                       '</litp:file-system>')

        lun_disk_xml_tmplt = ('<litp:lun-disk id="app_disk">' +
                              '<balancing_group>low</balancing_group>' +
                              '<bootable>false</bootable>' +
                              '<disk_part>false</disk_part>' +
                              '<external_snap>false</external_snap>' +
                              '<lun_name>LITP_ENM_app1</lun_name>' +
                              '<name>sda</name>' +
                              '<shared>false</shared>' +
                              '<size>{0}</size>' +
                              '<snap_size>100</snap_size>' +
                              '<storage_container>LITP1</storage_container>' +
                              '</litp:lun-disk>')
        lun_disk_small_xml = lun_disk_xml_tmplt.format('10G')
        lun_disk_big_xml = lun_disk_xml_tmplt.format('100G')

        # ----
        empty_xml = xml_hdr + xml_ftr
        self.do_infra_plan_wrkr(empty_xml)

        # ----
        from_state_sfs_xml = xml_hdr + sfs_fs_small_xml + xml_ftr
        to_state_sfs_xml = xml_hdr + sfs_fs_big_xml + xml_ftr
        self.do_infra_plan_wrkr(from_state_sfs_xml)

        expected = ('litp create -t sfs-export -p ' +
                    '/managed_fs2/exports/export1 -o ' +
                    'ipv4allowed_clients=1.2.3.4/16 ' +
                    'options=rw,no_wdelay,no_root_squash' + '\n' +
                    'litp create -t sfs-filesystem -p //managed_fs2 ' +
                    '-o path=/vx/CIcdb-managed-fs1 size=500M\n')

        self.do_infra_plan_wrkr(empty_xml, to_state_sfs_xml,
                                expected_clis=expected)

        expected = 'litp update -p //managed_fs2 -o size=500M\n'
        self.do_infra_plan_wrkr(from_state_sfs_xml, to_state_sfs_xml,
                                expected_clis=expected)

        # ----
        to_state_lvm_xml = xml_hdr + ext4_fs_xml + xml_ftr
        self.do_infra_plan_wrkr(empty_xml, to_state_lvm_xml,
                                infra_plan_expected_with_xml_diff=False)

        # ----
        to_state_vxfs_xml = xml_hdr + vxfs_fs_xml + xml_ftr
        expected = ('litp create -t file-system -p //elastic_fs -o ' +
                    'mount_point=/a/b/c snap_external=false fsck_pass=2 ' +
                    'snap_size=4 type=vxfs size=500G\n')
        self.do_infra_plan_wrkr(empty_xml, to_state_vxfs_xml,
                                expected_clis=expected)

        # ----
        from_state_lun_xml = xml_hdr + lun_disk_small_xml + xml_ftr
        to_state_lun_xml = xml_hdr + lun_disk_big_xml + xml_ftr
        self.do_infra_plan_wrkr(from_state_lun_xml)

        expected = ('litp create -t lun-disk -p //app_disk ' +
                    '-o lun_name=LITP_ENM_app1 name=sda ' +
                    'balancing_group=low bootable=false snap_size=100 ' +
                    'disk_part=false storage_container=LITP1 shared=false ' +
                    'external_snap=false size=100G\n')
        self.do_infra_plan_wrkr(empty_xml, to_state_lun_xml,
                                expected_clis=expected)

        expected = 'litp update -p //app_disk -o size=100G\n'
        self.do_infra_plan_wrkr(from_state_lun_xml, to_state_lun_xml,
                                expected_clis=expected)

    def do_infra_plan_wrkr(self, from_state_xml, to_state_xml=None,
                           infra_plan_expected_with_xml_diff=True,
                           expected_clis=None):

        tmp_file2 = None

        tmp_file1 = NamedTemporaryFile().name
        with open(tmp_file1, 'w') as fd1:
            fd1.write(from_state_xml)
        self.upgrader.EXPORTED_ENM_FROM_STATE_DD = tmp_file1
        if not to_state_xml:
            self.upgrader.the_to_state_dd = tmp_file1
        else:
            tmp_file2 = NamedTemporaryFile().name
            with open(tmp_file2, 'w') as fd2:
                fd2.write(to_state_xml)
            self.upgrader.the_to_state_dd = tmp_file2

        self.upgrader._set_upgrd_props = Mock()
        self.upgrader._unset_upgrd_props = Mock()
        self.upgrader._mng_plugins = Mock()
        self.upgrader._monitor_litp_plan = Mock()
        self.upgrader._run_command = MagicMock(return_value=(0, None))

        self.upgrader._do_infra_plan()

        os.remove(tmp_file1)
        if tmp_file2:
            os.remove(tmp_file2)

        if from_state_xml and to_state_xml and \
           (from_state_xml != to_state_xml) and \
           infra_plan_expected_with_xml_diff:

            expected = [call('sh infra_plan_clis.sh'),
                        call('litp create_plan --no-lock-tasks', timeout_secs=7200),
                        call('litp run_plan')]

            self.assertEquals(self.upgrader._run_command.call_args_list,
                              expected)

            if expected_clis:
                self.upgrader._write_to_file.assert_called_with(
                                                         'infra_plan_clis.sh',
                                                         expected_clis)

    def test_do_infra_plan_resume(self):

        self.upgrader.processed_args = Mock(resume=True)
        self.upgrader.litp = MagicMock(return_value=None)
        self.upgrader._mng_plugins = Mock()
        self.upgrader._monitor_litp_plan = Mock()
        self.upgrader._run_litp_plan = Mock()

        self.upgrader._do_infra_plan()

        self.upgrader._run_litp_plan.assert_called_once_with(
            'Infra', resume=True)
        self.upgrader._monitor_litp_plan.assert_called_once_with(
            'Infra', resume=True)
        self.upgrader._mng_plugins.assert_called_once_with('install',
                     ['ERIClitpvcs_CXP9030870'])

    @patch('os.path.exists')
    @patch('rh7_upgrade_enm.load_xml', MagicMock())
    def test_do_infra_no_plan(self, m_exists):

        self.upgrader.processed_args = Mock(resume=False)
        self.upgrader.litp = MagicMock(return_value=None)
        self.upgrader._mng_plugins = Mock()
        m_exists.return_value = True
        self.upgrader._monitor_litp_plan = Mock()
        self.upgrader._run_litp_plan = Mock()

        self.upgrader._do_infra_plan()
        self.assertTrue(self.upgrader.last_plan_do_nothing_plan)

    def test_redeploy_ms(self):

        self.upgrader.processed_args = Mock(resume=False)
        self.upgrader.litp = MagicMock(return_value=None)
        self.upgrader._set_upgrd_props = Mock()
        self.upgrader._mng_plugins = Mock()
        self.upgrader._set_model_state = Mock(return_value=None)
        self.upgrader._create_litp_plan = Mock()
        self.upgrader._monitor_litp_plan = Mock()
        self.upgrader._run_litp_plan = Mock()
        self.upgrader._unset_upgrd_props = Mock()

        self.upgrader._redeploy_ms()

        self.upgrader._set_upgrd_props.assert_called_once_with(['redeploy_ms'])
        self.upgrader._set_model_state.assert_called_with('/deployments', 'Applied')
        self.upgrader._run_litp_plan.assert_called_once_with(
            'MS Redeploy', resume=False)
        self.upgrader._monitor_litp_plan.assert_called_once_with(
            'MS Redeploy', resume=False)
        self.upgrader._mng_plugins.assert_has_calls(
            [call('remove', ['ERIClitpmodeldeployment_CXP9031595', 'ERIClitpvcs_CXP9030870', 'ERIClitpopendj_CXP9031976']),
             call('install', ['ERIClitpmodeldeployment_CXP9031595', 'ERIClitpvcs_CXP9030870', 'ERIClitpopendj_CXP9031976'])]
            )
        self.upgrader._unset_upgrd_props.assert_called_once_with(['redeploy_ms'])

    def test_redeploy_ms_resume(self):

        self.upgrader.processed_args = Mock(resume=True)
        self.upgrader.litp = MagicMock(return_value=None)
        self.upgrader._mng_plugins = Mock()
        self.upgrader._monitor_litp_plan = Mock()
        self.upgrader._run_litp_plan = Mock()
        self.upgrader._unset_upgrd_props = Mock()

        self.upgrader._redeploy_ms()

        self.upgrader._run_litp_plan.assert_called_once_with(
            'MS Redeploy', resume=True)
        self.upgrader._monitor_litp_plan.assert_called_once_with(
            'MS Redeploy', resume=True)
        self.upgrader._mng_plugins.assert_called_once_with('install',
                      ['ERIClitpmodeldeployment_CXP9031595',
                       'ERIClitpvcs_CXP9030870',
                       'ERIClitpopendj_CXP9031976'])
        self.upgrader._unset_upgrd_props.assert_called_once_with(['redeploy_ms'])

    @patch('rh7_upgrade_enm.create_snapshots_indicator_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade.create_lockfile')
    @patch('rh7_upgrade_enm.manage_snapshots')
    def test_do_take_snaps(self, mock_manage_snaps, mock_lockfile, mock_ifile):
        expected_create_call = call(action='create_snapshot', verbose=False)
        expected_remove_call = call(action='remove_snapshot', verbose=False)

        self.upgrader._take_snaps()
        self.assertEqual(1, mock_manage_snaps.call_count)
        self.assertEqual(1, mock_lockfile.call_count)
        self.assertEqual(1, mock_ifile.call_count)
        self.assertEqual(expected_create_call, mock_manage_snaps.mock_calls[0])

        mock_manage_snaps.reset_mock()
        self.upgrader.processed_args = argparse.Namespace(hybrid_state=True)
        self.upgrader._take_snaps()
        self.assertEqual(2, mock_manage_snaps.call_count)
        self.assertEqual(2, mock_lockfile.call_count)
        self.assertEqual(2, mock_ifile.call_count)
        self.assertEqual(expected_remove_call, mock_manage_snaps.mock_calls[0])
        self.assertEqual(expected_create_call, mock_manage_snaps.mock_calls[1])

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_stage_data')
    @patch('os.geteuid')
    @patch('rh7_upgrade_enm.os.path.exists')
    def test_stage_tracker(self, mock_exists, mock_geteuid, mock_get_sdata):
        mock_exists.return_value = True
        mock_geteuid.return_value = 0
        self.upgrader._assert_rhel_version = Mock(return_value=True)
        self.upgrader.tracker = '/tmp/tracker'

        mock_stage_data = [{'idx': idx,
                            'label': 'mock-stage-{0}'.format(idx),
                            'hndlr': '_mock_stage_{0}'.format(idx)}
                            for idx in range(1, 6)]
        mock_stage_data[3]['label'] = 'take-snapshots'
        mock_stage_data[4]['label'] = 'rolling-nodes-redeploy'

        mock_get_sdata.return_value = mock_stage_data

        for idx in range(1, 6):
            setattr(self.upgrader, '_mock_stage_{0}'.format(idx), Mock())

        for (hybrid, resume, track_data, raise_exit,
             s1_called, s2_called, s3_called, s4_called, s5_called) in \
          [(False, False, 'garbage', False, True,  True,  True,  True,  True),
           (False, False, '',        False, True,  True,  True,  True,  True),
           (False, False, '01',      False, False, True,  True,  True,  True),
           (False, False, '02',      False, False, False, True,  True,  True),
           (False, False, '03',      False, False, False, False, True,  True),
           (False, False, '04',      False, False, False, False, False, True),
           (False, False, '05',      True,  False, False, False, False, False),
           (False, False, '99',      True,  False, False, False, False, False),
           (True,  False, '',        True, False, False, False, False,  False),
           (True,  False, '03',      False, False, False, False, True,  True),
           (False, True,  '01',      False, False, False, False, False, True),
           (True,  True,  '03',      False, False, False, False, True, True)]:

            self.upgrader._read_file = Mock(return_value=track_data)
            self.upgrader.processed_args = Mock(hybrid_state=hybrid,
                                                resume=resume)

            for idx in range(1, 6):
                getattr(self.upgrader,
                        '_mock_stage_{0}'.format(idx)).reset_mock()

            self.assertRaises(SystemExit, self.upgrader._do_rh7_uplift) \
            if raise_exit else self.upgrader._do_rh7_uplift()

            for (called, hndlr) in ((s1_called, self.upgrader._mock_stage_1),
                                    (s2_called, self.upgrader._mock_stage_2),
                                    (s3_called, self.upgrader._mock_stage_3),
                                    (s4_called, self.upgrader._mock_stage_4),
                                    (s5_called, self.upgrader._mock_stage_5)):
                self.assertTrue(hndlr.called) if called \
                else self.assertFalse(hndlr.called)

    def test_get_restored_files(self):
        expected = "/opt/ericsson/nms/litp/keyset/keyset1 root litp-admin 0440\n" + \
                   "/etc/puppetdb/ssl puppetdb puppetdb 0700\n" + \
                   "/etc/puppetdb/ssl/ca.pem puppetdb puppetdb 0600\n" + \
                   "/etc/puppetdb/ssl/private.pem puppetdb puppetdb 0600\n" + \
                   "/etc/puppetdb/ssl/public.pem puppetdb puppetdb 0600"
        self.assertEquals(expected, self.upgrader._get_restored_files())

    @patch('rh7_upgrade_enm.os.stat')
    @patch('rh7_upgrade_enm.os.chmod')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_restored_files')
    @patch('rh7_upgrade_enm.getgrnam')
    @patch('rh7_upgrade_enm.getpwnam')
    @patch('rh7_upgrade_enm.os.path.exists')
    def test_process_restored_data_parts(self, mock_exists,
                                         mock_getpwnam, mock_getgrnam,
                                         mock_get_rfiles,
                                         mock_chmod, mock_stat):

        self.upgrader._assert_rhel_version = Mock(return_value=True)

        file_data_str = "/tmp/file1 puppet root 0600\n" + \
                        "/tmp/file2 bob litp-admin 0400\n" + \
                        "/tmp/file3 celery groupy 0700"

        mock_get_rfiles = Mock(return_value=file_data_str)

        file_data = Rh7EnmUpgrade._gen_file_data(file_data_str)

        # ----
        mock_exists.return_value = False
        self.assertRaises(SystemExit,
                          self.upgrader._assert_files_exist, file_data)

        # ----
        mock_exists.return_value = True

        mock_getgrnam.side_effect = KeyError
        self.upgrader._run_command_set = MagicMock()

        self.upgrader._create_groups(file_data)
        expected = ['groupadd -r litp-admin -g 1000',
                    'groupadd -r root',
                    'groupadd -r groupy']
        self.upgrader._run_command_set.assert_called_with(expected,
                                                       'Create system groups')

        # ---
        mock_getgrnam = Mock(return_value=Mock(gr_gid=1))
        self.upgrader._run_command_set.reset_mock()
        self.upgrader._create_groups(file_data)
        self.upgrader._run_command_set.assert_not_called()

        # ---
        self.upgrader._run_command_set.reset_mock()

        mock_getpwnam.side_effect = KeyError

        self.upgrader._create_users(file_data)

        expected = ['useradd -m -r celery ' + \
                       '-G litp-admin,celery,puppet,litp-access ' + \
                       '-c Celery user -s /bin/bash -d /home/celery',
                    'useradd -m -r bob',
                    'useradd -m -r puppet -u 52 -c Puppet ' + \
                       '-s /sbin/nologin -d /var/lib/puppet']

        self.upgrader._run_command_set.assert_called_with(expected,
                                                       'Create system users')

        # ---
        mock_getpwnam = Mock(return_value=Mock(pw_uid=1))
        self.upgrader._run_command_set.reset_mock()
        self.upgrader._create_users(file_data)
        self.upgrader._run_command_set.assert_not_called()

        # ---
        mock_stat = Mock(st_mode=33188)  # 0644
        for (mode, mask) in (('0400', stat.S_IRUSR),
                             ('0600', stat.S_IRUSR|stat.S_IWUSR),
                             ('0700', stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR)):
            mock_chmod.reset_mock()
            self.upgrader._chmod_file('/a/file', mode)
            mock_chmod.assert_called_with('/a/file', mask)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_restored_files')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._chmod_file')
    def test_process_restored_data(self, mock_chmod, mock_get_rfiles):
        self.upgrader._assert_rhel_version = Mock(return_value=True)

        file_data_str = "/f1 u1 g1 0600\n" + \
                        "/f2 u2 g2 0400\n" + \
                        "/f3 u3 g3 0700"

        mock_get_rfiles.return_value=file_data_str

        file_data = Rh7EnmUpgrade._gen_file_data(file_data_str)

        self.upgrader._reload_sentinel_licesnses = Mock(return_value=True)
        self.upgrader._create_symlinks = Mock(return_value=True)
        self.upgrader._refresh_yum_repos = Mock(return_value=True)
        self.upgrader._assert_files_exist = Mock(return_value=True)
        self.upgrader._create_groups = Mock(return_value=True)
        self.upgrader._create_users = Mock(return_value=True)
        self.upgrader._chown_file = Mock(return_value=True)
        mock_chmod.return_value = True

        self.upgrader._process_restored_data()

        self.upgrader._assert_files_exist.assert_called_with(file_data)
        self.upgrader._create_groups.assert_called_with(file_data)
        self.upgrader._create_groups.assert_called_with(file_data)

        chown_expected = [call(entry['path'], entry['user'], entry['group'])
                          for entry in file_data]
        chmod_expected = [call(entry['path'], entry['mode'])
                          for entry in file_data]

        self.upgrader._chown_file.assert_has_calls(chown_expected)
        self.upgrader._chmod_file.assert_has_calls(chmod_expected)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._process_lms_services')
    def _reload_sentinel_licesnses(self, mock_process_lms_services):
        mock_process_lms_services.return_value = (0, '')

        self.upgrader._reload_sentinel_licesnses()
        mock_process_lms_services.assert_has_calls(
                [call(['sentinel'], 'stop'),
                 call(['sentinel'], 'start')])

    @patch('rh7_upgrade_enm.os.path.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_all_non_plugin_repo_paths')
    def test_refresh_yum_repos(self, m_get_all_non_plugin_repo_paths,
                               mock_exists):
        mock_exists.return_value = True
        self.upgrader._get_hostname = Mock(return_value='ms1')
        m_get_all_non_plugin_repo_paths.return_value = [
                    '/var/www/html/6.10/os/x86_64/Packages',
                    '/var/www/html/7.6/os/x86_64/Packages',
                    '/var/www/html/7.9/os/x86_64/Packages',
                    '/var/www/html/6.10/updates/x86_64/Packages',
                    '/var/www/html/7.6/updates/x86_64/Packages',
                    '/var/www/html/7.9/updates/x86_64/Packages',
                    '/var/www/html/3pp',
                    '/var/www/html/3pp_rhel7',
                    '/var/www/html/ENM',
                    '/var/www/html/ENM_rhel7',
                    '/var/www/html/ENM_asrstream',
                    '/var/www/html/ENM_asrstream_rhel7',
                    '/var/www/html/ENM_automation',
                    '/var/www/html/ENM_automation_rhel7',
                    '/var/www/html/ENM_common',
                    '/var/www/html/ENM_common_rhel7',
                    '/var/www/html/ENM_db',
                    '/var/www/html/ENM_db_rhel7',
                    '/var/www/html/ENM_eba',
                    '/var/www/html/ENM_eba_rhel7',
                    '/var/www/html/ENM_ebsstream',
                    '/var/www/html/ENM_ebsstream_rhel7',
                    '/var/www/html/ENM_esnstream',
                    '/var/www/html/ENM_esnstream_rhel7',
                    '/var/www/html/ENM_events',
                    '/var/www/html/ENM_events_rhel7',
                    '/var/www/html/ENM_models',
                    '/var/www/html/ENM_models_rhel7',
                    '/var/www/html/ENM_ms',
                    '/var/www/html/ENM_ms_rhel7',
                    '/var/www/html/ENM_scripting',
                    '/var/www/html/ENM_scripting_rhel7',
                    '/var/www/html/ENM_services',
                    '/var/www/html/ENM_services_rhel7',
                    '/var/www/html/ENM_streaming',
                    '/var/www/html/ENM_streaming_rhel7']

        prefix = 'createrepo /var/www/html/'

        expected = ['yum clean metadata',
                    prefix + 'litp',
                    prefix + 'litp_plugins',
                    prefix + '3pp',
                    prefix + 'ENM',
                    prefix + 'ENM_asrstream',
                    prefix + 'ENM_automation',
                    prefix + 'ENM_common',
                    prefix + 'ENM_db',
                    prefix + 'ENM_eba',
                    prefix + 'ENM_ebsstream',
                    prefix + 'ENM_esnstream',
                    prefix + 'ENM_events',
                    prefix + 'ENM_models',
                    prefix + 'ENM_ms',
                    prefix + 'ENM_scripting',
                    prefix + 'ENM_services',
                    prefix + 'ENM_streaming',
                    prefix + '6.10/os/x86_64/Packages',
                    prefix + '7.6/os/x86_64/Packages',
                    prefix + '6.10/updates/x86_64/Packages',
                    prefix + '7.6/updates/x86_64/Packages',
                    ]

        self.upgrader._run_command_set = MagicMock()

        self.upgrader._refresh_yum_repos()
        self.upgrader._run_command_set.assert_called_with(expected,
                                                          'Refresh yum repositories')

    @patch('rh7_upgrade_enm.os.symlink')
    @patch('rh7_upgrade_enm.os.path.exists')
    @patch('rh7_upgrade_enm.os.path.islink')
    def test_create_symlinks(self, mock_islink, mock_exists, mock_symlink):
        srcs = ['/var/www/html/7.9/', '/var/www/html/6.10/']
        dsts = ['/var/www/html/7', '/var/www/html/6']

        src_calls = [call(x) for x in srcs]
        dst_calls = [call(x) for x in dsts]
        symlink_calls = {'7': call(srcs[0], dsts[0]),
                         '6': call(srcs[1], dsts[1])}

        for (islink, exists) in ((False, False),
                                 (False, True),
                                 (True, False),
                                 (True, True)):

            mock_symlink.reset_mock()
            mock_exists.reset_mock()
            mock_islink.reset_mock()

            mock_exists.return_value = exists
            mock_islink.return_value = islink

            if not islink and not exists:
                self.assertRaises(SystemExit, self.upgrader._create_symlinks)
                mock_islink.assert_has_calls(dst_calls[0])
                mock_exists.assert_has_calls(src_calls[0])
            else:
                self.upgrader._create_symlinks()

                mock_islink.assert_has_calls(dst_calls)
                if not islink:
                    mock_exists.assert_has_calls(src_calls)
                    if exists:
                        self.assertEquals(2, mock_symlink.call_count)
                        mock_symlink.assert_has_calls([symlink_calls['7'],
                                                       symlink_calls['6']])

    @patch('rh7_upgrade_enm.getgrnam', Mock(return_value=Mock(gr_gid=1)))
    @patch('rh7_upgrade_enm.getpwnam', Mock(return_value=Mock(pw_uid=1)))
    @patch('rh7_upgrade_enm.os.fchown')
    @patch('__builtin__.open')
    def test_chown_file(self, mock_open, mock_fchown):

        self.upgrader._chown_file('/a/file', 'freddy', 'groupy', 100)
        mock_open.assert_not_called()
        mock_fchown.assert_called_once_with(100, 1, 1)

        # ---
        mock_open.reset_mock()
        self.upgrader._chown_file('/a/file', 'freddy', 'groupy')
        mock_open.assert_called_with('/a/file', 'r')
        open_handle = mock_open()
        mock_fchown.assert_called_with(open_handle.__enter__().fileno(), 1, 1)

    @patch('rh7_upgrade_enm.shutil')
    @patch('rh7_upgrade_enm.tarfile')
    @patch("rh7_upgrade_enm.tempfile")
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._change_svc_state')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_restore_esmon_data(self, mock_run_cmd, mock_change_svc_state,
                                mock_tempfile, mock_tarfile, mock_shutil):
        esmon_vm_name = 'esmon'
        esmon_volume = '/dev/mapper/vg_root-vg1_fs_data'
        temp_dir = '/tmp/dir'
        mock_tempfile.mkdtemp.return_value = temp_dir
        mock_run_cmd.return_value = (0, '')

        with patch.object(LOGGER, 'debug') as debug_obj:
            self.upgrader._restore_esmon_data()

            mock_tarfile.open.assert_called_once_with(
                    Rh7EnmUpgrade._gen_esmon_backup_name(), 'r:gz')
            debug_obj.assert_any_call('Extracting data to {0}'.
                                      format(temp_dir))
            mock_change_svc_state.assert_has_calls(
                [call(esmon_vm_name, 'start')],
                any_order=False
            )
            mock_run_cmd.assert_has_calls(
                [call('/usr/bin/systemctl stop puppet', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT),
                 call('/opt/ericsson/nms/litp/lib/litpmnlibvirt/litp_libvirt_adaptor.py esmon stop-undefine --stop-timeout=45'),
                 call('mount {0} {1}'.format(esmon_volume, temp_dir)),
                 call('umount {0}'.format(esmon_volume)),
                 call('/usr/bin/systemctl start puppet', timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT),
                 call('/usr/bin/systemctl is-active --quiet puppet')],
                any_order=False)
            mock_shutil.rmtree.assert_called_once_with(temp_dir)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_change_service_state(self, mock_run_cmd):
        domain_name = 'test'
        mock_run_cmd.return_value = (0, '')

        state = 'start'
        self.upgrader._change_svc_state(domain_name, state)
        mock_run_cmd.assert_called_with(
            '/usr/bin/systemctl {0} {1}.service'.format(state, domain_name))

    @patch('rh7_upgrade_enm.EnmPreChecks.process_actions')
    def test_do_upgrd_prechecks(self, mock_process_actions):
        upc_test_data = {0x1: 'storage_setup_check',
                         0x2: 'check_lvm_conf_non_db_nodes',
                         0x4: 'elastic_search_status_check',
                         0x8: 'opendj_replication_check',
                         0x10: 'unmount_iso_image_check',
                         0x20: 'check_fallback_status',
                         0x40: 'remove_seed_file_after_check'}

        stage_upc_mask = random.randint(1, 2**len(upc_test_data.keys()))

        expected = []
        for (idx, name) in upc_test_data.iteritems():
            if bool(stage_upc_mask & idx):
                expected.append(name)

        if expected:
            mock_process_actions.reset_mock()
            self.upgrader._do_upgrd_prechks(upc_test_data, stage_upc_mask)
            mock_process_actions.assert_called_with(expected)


    @patch('rh7_upgrade_enm.HealthCheck.consul_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.multipath_active_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.vcs_service_group_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.vcs_llt_heartbeat_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.vcs_cluster_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.system_service_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.puppet_enabled_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.node_fs_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.stale_mount_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.storagepool_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.nas_healthcheck')
    @patch('rh7_upgrade_enm.HealthCheck.san_alert_healthcheck')
    @patch('enm_healthcheck.get_nas_type')
    def test_do_healthchecks(self, mock_nas_type,
                             mock_hc1, mock_hc2, mock_hc3, mock_hc4,
                             mock_hc5, mock_hc6, mock_hc7, mock_hc8, mock_hc9,
                             mock_hc10, mock_hc11, mock_hc12):
        mock_nas_type.return_value = ''

        hc_bits = [0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80,
                   0x100, 0x200, 0x400, 0x800]

        hc_mocks = [mock_hc1, mock_hc2,
                    mock_hc3, mock_hc4, mock_hc5, mock_hc6, mock_hc7,
                    mock_hc8, mock_hc9, mock_hc10, mock_hc11, mock_hc12]

        hc_names = ['san_alert', 'nas', 'storagepool', 'stale_mount',
                    'node_fs', 'puppet_enabled', 'system_service', 'vcs_cluster',
                    'vcs_llt_heartbeat', 'vcs_service_group', 'multipath_active',
                    'consul']

        hc_data = dict(zip(hc_bits, hc_names))
        hc_mock_data = dict(zip(hc_bits, hc_mocks))

        stage_hc_mask = random.randint(1, 2**len(hc_data.keys()))

        expected = [the_mock
                    for (idx, the_mock) in hc_mock_data.iteritems()
                    if bool(stage_hc_mask & idx)]

        if expected:
            not_expected = list(set(set(hc_mock_data.values()) -
                                    set(expected)))

            for amock in hc_mock_data.values():
                amock.reset_mock()

            self.upgrader._do_health_chks(hc_data, stage_hc_mask)

            for amock in expected:
                amock.assert_called_once()

            for amock in not_expected:
                amock.assert_not_called()

    def test_upgrd_pre_chks_and_hlth_chks(self):
        self.upgrader.current_stage = None

        self.assertRaises(SystemExit,
                          self.upgrader._upgrd_pre_chks_and_hlth_chks)

        # ---

        invalid_stages = ['03', '05', '09', '99']
        for sidx in invalid_stages:
            self.upgrader.current_stage = {'idx': sidx,
                                           'label': 'some-invalid-label',
                                           'hndlr': 'some-invalid-handler'}
            self.assertRaises(SystemExit,
                              self.upgrader._upgrd_pre_chks_and_hlth_chks)

        # ---

        upc_data = {0x1: 'storage_setup_check',
                    0x2: 'check_lvm_conf_non_db_nodes',
                    0x4: 'elastic_search_status_check',
                    0x8: 'opendj_replication_check',
                    0x10: 'unmount_iso_image_check',
                    0x20: 'check_fallback_status',
                    0x40: 'remove_seed_file_after_check'}

        hc_data = {0x1: 'san_alert',
                   0x2: 'nas',
                   0x4: 'storagepool',
                   0x8: 'stale_mount',
                   0x10: 'node_fs',
                   0x20: 'puppet_enabled',
                   0x40: 'system_service',
                   0x80: 'vcs_cluster',
                   0x100: 'vcs_llt_heartbeat',
                   0x200: 'vcs_service_group',
                   0x400: 'consul',
                   0x4000: 'hw_resources'}

        self.upgrader._do_upgrd_prechks = Mock()
        self.upgrader._do_health_chks = Mock()

        valid_stages = ['08', '10', '12', '14', '17', '20', '22']
        for sidx in valid_stages:
            self.upgrader.current_stage = {'idx': sidx,
                                           'label': 'some-valid-label',
                                           'hndlr': 'some-valid-handler'}

            self.upgrader._do_upgrd_prechks.reset_mock()
            self.upgrader._do_health_chks.reset_mock()
            self.upgrader.last_plan_do_nothing_plan = False

            self.upgrader._upgrd_pre_chks_and_hlth_chks()

            if sidx not in ('20', '22'):
                self.upgrader._do_upgrd_prechks.assert_called_with(upc_data,
                                                                   0x7F)

            if sidx == '14':
                stage_hcs = 0x47FD
            else:
                stage_hcs = 0x47FF

            self.upgrader._do_health_chks.assert_called_with(hc_data,
                                                             stage_hcs)

            if sidx in ('17', '22'):
                self.upgrader.last_plan_do_nothing_plan = True
                self.upgrader._do_health_chks.reset_mock()
                self.upgrader._upgrd_pre_chks_and_hlth_chks()
                stage_hcs = 0x47FD
                self.upgrader._do_health_chks.assert_called_with(hc_data,
                                                                 stage_hcs)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._write_to_file')
    def test_create_lockfile(self, p_write_to_file):
        self.upgrader.create_lockfile()
        self.assertTrue(p_write_to_file.called)

    @patch('rh7_upgrade_enm.migrate_cleanup_cmd')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._update_software_services')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._monitor_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._pre_rollover_mng_plugins')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._parse_deploy_diff_output')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_xml_diff_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('rh7_upgrade_enm.pre_rollover_changes')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._unset_upgrd_props')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_upgrd_props')
    def test_pre_redeploy_nodes(self, mock_set_upgr_prop, mock_unset_upgr_prop,
            mock_pre_rollover_chngs, mock_run_cmd, mock_create_xml_diff,
            mock_parse_diff_file, mock_mng_plugins, mock_create_plan,
            mock_run_plan, mock_monitor_plan, mock_upd_services, mock_cleanup_cmd):
        mock_run_cmd.return_value = (0, '')
        self.upgrader.litp = MagicMock()
        self.upgrader.litp.delete_path = MagicMock(return_value=True)
        self.upgrader.litp.delete_property = MagicMock(return_value=True)

        LITP_CREATE_VIP = ('litp create -t vip -p /deployments/test/clusters/'
                           'c1/services/cs1/cs_vip -o network_name=internal '
                           'ipaddress=10.11.12.13')
        LITP_CS_CONTRACTION = ('litp update -p /deployments/test/clusters/c1/'
                               'services/cs1 -o standby=0 node_list=n1')
        LITP_CS_MIGRATE_PLUS_NL = ('litp update -p /deployments/test/clusters/c1/'
                        'services/cs1 -o standby=0 active=2 node_list=n1,n2')
        LITP_CS_MIGRATE_PLUS_T = ('litp update -p /deployments/test/clusters/c1/'
                        'services/cs1 -o standby=0 active=2 status_timeout=15')
        LITP_CS_MIGRATE_MINUS_AS = ('litp update -p /deployments/test/clusters/c1/'
                        'services/cs1 -o status_timeout=15')
        LITP_CS_MIGRATE_FILTERED = ('litp update -p /deployments/test/clusters/c1/'
                               'services/cs1 -o standby=0 active=2')
        LITP_UPD_HA_CONF = ('litp update -p /deployments/test/clusters/c1/'
                            'services/cs2/ha_configs/conf1 -o '
                            'status_timeout=15 clean_timeout=65')
        expected_updates = [LITP_CREATE_VIP, LITP_CS_CONTRACTION,
                            LITP_UPD_HA_CONF, LITP_CS_MIGRATE_PLUS_NL,
                            LITP_CS_MIGRATE_PLUS_T,
                            LITP_CS_MIGRATE_FILTERED]
        expected_updates_filtered = [LITP_CREATE_VIP, LITP_CS_CONTRACTION,
                            LITP_UPD_HA_CONF, LITP_CS_MIGRATE_PLUS_NL,
                            LITP_CS_MIGRATE_MINUS_AS]

        expected_remove_items = [
                ('/deployments/d1/clusters/c1/services/cs1', None),
                ('/deployments/d1/clusters/c1/services/cs2/cs2_vip', None),
                ('/deployments/d1/clusters/c1/services/cs2/cs2_vip',
                 'initial_online_dependency_list')
                                ]
        mock_pre_rollover_chngs.return_value = expected_updates
        mock_parse_diff_file.return_value = expected_remove_items

        self.upgrader._pre_redeploy_nodes()

        mock_run_cmd.assert_has_calls([call(cmd, timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)
                                    for cmd in expected_updates_filtered])
        mock_create_xml_diff.assert_called_with(self.upgrader.ENM_PREVIOUS_DD,
                                                self.upgrader.ENM_DD)
        self.upgrader.litp.delete_path.assert_has_calls(
                [call(expected_remove_items[0][0])])
        self.assertFalse(self.upgrader.litp.delete_property.called)
        self.assertTrue(mock_mng_plugins.called)
        mock_create_plan.assert_called_with('R-1', nlt=True, dnpe_allowed=True)
        self.assertTrue(mock_upd_services.called)
        props = ['pre_os_reinstall', 'os_reinstall']
        mock_set_upgr_prop.assert_called_with(props)
        mock_unset_upgr_prop.assert_called_with(props)

    @patch('rh7_upgrade_enm.migrate_cleanup_cmd')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._update_software_services')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_litp_plan')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._pre_rollover_mng_plugins')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._parse_deploy_diff_output')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._create_xml_diff_file')
    @patch('rh7_upgrade_enm.pre_rollover_changes')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._unset_upgrd_props')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_upgrd_props')
    def test_pre_redeploy_nodes_no_changes(self, mock_set_upgr_prop,
            mock_unset_upgr_prop, mock_pre_rollover_chngs,
            mock_create_xml_diff, mock_parse_diff_file, mock_mng_plugins,
            mock_create_plan, mock_upd_services, mock_cleanup_cmd):
        mock_pre_rollover_chngs.return_value = []
        mock_parse_diff_file.return_value = []
        mock_upd_services.return_value = set()

        self.upgrader._pre_redeploy_nodes()

        self.assertTrue(mock_upd_services.called)
        self.assertTrue(mock_pre_rollover_chngs.called)
        self.assertTrue(mock_create_xml_diff.called)
        self.assertTrue(mock_parse_diff_file.called)
        self.assertFalse(mock_mng_plugins.called)
        self.assertFalse(mock_create_plan.called)

    @patch('glob.glob')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_pre_rollover_mng_plugins(self, mock_run_cmd, mock_glob_glob):
        mock_run_cmd.return_value = (0, '')
        enm_pkgs = ['ERIClitpopendjapi_CXP9031975-1.2.1.rpm',
                    'ERIClitpopendj_CXP9031976-1.23.1.rpm',
                    'ERIClitpopendjapi_CXP9031975-1.3.1.rpm',
                    'ERIClitpopendj_CXP9031976-1.24.1.rpm',
                    'ERIClitpconsul_CXP9035344-1.3.2.rpm',
                    'ERIClitpconsulapi_CXP9035345-1.0.5.rpm',
                    'EXTRpuppetlabspostgresql_CXP9031509-1.27.1.rpm']
        mock_glob_glob.return_value = ['/var/www/html/litp_plugins/' + pkg
                                       for pkg in enm_pkgs]
        expected_enm_pkgs = ['ERIClitpconsul_CXP9035344',
                             'ERIClitpopendj_CXP9031976',
                             'EXTRpuppetlabspostgresql_CXP9031509']
        pkgs = ['ERIClitppackage_CXP9030581',
                'ERIClitpdhcpservice_CXP9031640', 'ERIClitpnetwork_CXP9030513',
                'ERIClitphosts_CXP9030589']

        self.upgrader._pre_rollover_mng_plugins('remove')
        mock_run_cmd.assert_has_calls(
               [call('yum remove -y {0}'.format(' '.join(pkgs))),
                call('yum remove -y {0}'.format(' '.join(expected_enm_pkgs)))]
                                     )

        self.upgrader._pre_rollover_mng_plugins('install')
        mock_run_cmd.assert_has_calls(
               [call('yum install -y {0}'.format(' '.join(pkgs))),
                call('yum install -y {0}'.format(' '.join(expected_enm_pkgs)))]
                                     )

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_vcs_clustered_service_apd')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._set_model_state')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._item_collection_compare')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_xml_software_services')
    def test_update_software_services(self, mock_get_services, mock_compare,
                                       mock_set_state, mock_set_cs_apd):
        modified_services = ['/software/services/s0', '/software/services/s1']
        mock_compare.return_value = (None, None, modified_services)

        result = self.upgrader._update_software_services()

        mock_set_state.assert_has_calls([call(vpath, 'Updated', recurse=False)
                                         for vpath in modified_services])
        mock_set_cs_apd.assert_has_calls(
                [call(vpath, 'f') for vpath in modified_services])
        self.assertEqual(modified_services, result)

    def test_item_collection_compare(self):
        from_items = {'/software/services/s0': {'prop0': 0},
                      '/software/services/s1': {'prop0': 0},
                      '/software/services/s2': {'prop0': 0},
                      '/software/services/s3': {'prop0': 0}
                     }
        to_items = {'/software/services/s1': {'prop0': 1},
                    '/software/services/s2': {'prop0': 0},
                    '/software/services/s3': {'prop0': 0},
                    '/software/services/s4': {'prop0': 0}
                   }

        added, removed, modified = \
                self.upgrader._item_collection_compare(from_items, to_items)

        self.assertEqual(set(['/software/services/s4']), added)
        self.assertEqual(set(['/software/services/s0']), removed)
        self.assertEqual(set(['/software/services/s1']), modified)

    def test_get_xml_software_services(self):

        xml_text = """<?xml version='1.0' encoding='utf-8'?>
<litp:root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:litp="http://www.ericsson.com/litp" xsi:schemaLocation="http://www.ericsson.com/litp litp-xml-schema/litp.xsd" id="root">
  <litp:software id="software">
    <litp:software-deployables-collection id="deployables"/>
    <litp:software-images-collection id="images"/>
    <litp:software-items-collection id="items">
      <litp:package id="pkg0">
        <epoch>0</epoch>
        <name>httpd<!--note: this property is not updatable--></name>
      </litp:package>
      <litp:package id="pkg1">
        <epoch>0</epoch>
        <name>EXTRlitppkg1_CXP1234567<!--note: this property is not updatable--></name>
      </litp:package>
    </litp:software-items-collection>
    <litp:software-profiles-collection id="profiles"/>
    <litp:software-runtimes-collection id="runtimes"/>
    <litp:software-services-collection id="services">
      <litp:service id="serv0">
        <cleanup_command>/bin/true</cleanup_command>
        <service_name>serv0</service_name>
        <start_command>/sbin/start_serv0.sh</start_command>
        <litp:service-packages-collection id="packages">
          <litp:package-inherit source_path="/software/items/pkg0" id="pkg0"/>
        </litp:service-packages-collection>
      </litp:service>
      <litp:service id="serv1">
        <cleanup_command>/bin/true</cleanup_command>
        <service_name>serv1</service_name>
        <start_command>/sbin/serv1.sh start</start_command>
        <status_command>/sbin/serv1.sh status</status_command>
        <stop_command>/sbin/serv1.sh stop</stop_command>
        <litp:service-packages-collection id="packages">
          <litp:package-inherit source_path="/software/items/pkg1" id="pkg1"/>
        </litp:service-packages-collection>
      </litp:service>
    </litp:software-services-collection>
  </litp:software>
</litp:root>
"""
        self.tmpdir = os.path.join(gettempdir(), 'TestRh7UpgradeEnm')
        self.mktmpdir(self.tmpdir)
        xmlfile = self.mktmpfile('/tmp/doc.xml')
        with open(xmlfile, 'w') as f:
            f.write(xml_text)

        expected_services = {'/software/services/serv0':
                                 {'cleanup_command': '/bin/true',
                                  'start_command': '/sbin/start_serv0.sh'
                                 },
                             '/software/services/serv1':
                                 {'cleanup_command': '/bin/true',
                                  'start_command': '/sbin/serv1.sh start',
                                  'status_command': '/sbin/serv1.sh status',
                                  'stop_command': '/sbin/serv1.sh stop'
                                 }
                            }

        services = self.upgrader._get_xml_software_services(xmlfile)
        self.assertEqual(expected_services, services)

        self.rmtmpdir(self.tmpdir)

    @patch('rh7_upgrade_enm.LitpRestClient.exists')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._read_file')
    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    @patch('rh7_upgrade_enm.LitpRestClient.get')
    @patch('rh7_upgrade_enm.LitpRestClient.get_all_items_by_type')
    def test_pre_nodes_push_artifactss(self,
                                 mock_litprestclient_get_by_type,
                                 mock_litprestclient_get,
                                 mock_run_cmd,
                                 mock_read_file,
                                 mock_exists):
        mock_run_cmd.return_value = (0, '')

        CLUSTERED_SERVICE = {u'properties': {u'name': u'neo4jbur_cluster_service',
                                    u'standby': u'1',
                                    u'node_list': u'db-1,db-2',
                                    u'offline_timeout': u'10'}}

        NODES = [{'path': '/deployments/enm/clusters/db_cluster/nodes/db-1',
             'data': {u'id': u'db-1',
                      u'item-type-name': u'node',
                      u'applied_properties_determinable': True,
                      u'state': u'Applied',
                      u'properties': {u'is_locked': u'false',
                                      u'hostname': u'ieatrcxb3055'}}},
                    {'path': '/deployments/enm/clusters/db_cluster/nodes/db-2',
            'data': {u'id': u'db-2',
                     u'item-type-name': u'node',
                     u'applied_properties_determinable': True,
                     u'state': u'Applied',
                     u'properties': {u'is_locked': u'false',
                                     u'hostname': u'ieatrcxb6146'}}},
                    {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1',
            'data': {u'id': u'svc-1',
                     u'item-type-name': u'node',
                     u'applied_properties_determinable': True,
                     u'state': u'Applied',
                     u'properties': {u'is_locked': u'false',
                                     u'hostname': u'ieatrcxb6147'}}},
                    {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-2',
            'data': {u'id': u'svc-2',
                     u'item-type-name': u'node',
                     u'applied_properties_determinable': True,
                     u'state': u'Applied',
                     u'properties': {u'is_locked': u'false',
                                     u'hostname': u'ieatrcxb6148'}}},
                    {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-3',
            'data': {u'id': u'svc-3',
                     u'item-type-name': u'node',
                     u'applied_properties_determinable': True,
                     u'state': u'Applied',
                     u'properties': {u'is_locked': u'false',
                                     u'hostname': u'ieatrcxb6149'}}}]

        VM_SERVICES = [{'data': {u'properties':
                        {u'adaptor_version': u'2.0.3-1',
                         u'internal_status_check': u'on',
                         u'service_name': u'nedoserv',
                         u'node_hostname_map': u"{'svc-1': 'svc-1-nedoserv', 'svc-3': 'svc-3-nedoserv'}",
                         u'ram': u'5120M',
                         u'cpus': u'2',
                         u'image_name': u'jboss-image',
                         u'cleanup_command': u'/usr/share/litp_libvirt/vm_utils nedoserv stop-undefine --stop-timeout=300',
                         u'image_checksum': u'b72e4e7dc2376d2da876fb5f1e4bbd39'}}},
                       {'data': {u'properties':
                        {u'adaptor_version': u'2.0.3-1',
                         u'internal_status_check': u'on',
                         u'service_name': u'nedoserv',
                         u'node_hostname_map': u"{'svc-1': 'svc-1-nedo2serv', 'svc-2': 'svc-2-nedo2serv'}",
                         u'ram': u'5120M',
                         u'cpus': u'2',
                         u'image_name': u'jboss-image',
                         u'cleanup_command': u'/usr/share/litp_libvirt/vm_utils nedo2serv stop-undefine --stop-timeout=300',
                         u'image_checksum': u'b72e4e7dc2376d2da876fb5f1e4bbd39'}}}]


        def mock_litprestclient_get_by_type_side_effect(*args, **kwargs):

            if 'node' in args[1]:
                return NODES
            if 'reference-to-vm-service' in args[1]:
                return VM_SERVICES

        mock_litprestclient_get_by_type.side_effect = \
        mock_litprestclient_get_by_type_side_effect

        mock_litprestclient_get.return_value = CLUSTERED_SERVICE
        mock_run_command.return_value = (0,'')
        mock_read_file.return_value = 'blaaaa'
        self.upgrader._do_consul_action = Mock()

        self.upgrader._pre_nodes_push_artifacts()

        self.upgrader._do_consul_action.assert_has_calls([
                    call('put', 'enminst/vcs_lsb_vm_status_script', 'YmxhYWFh'),
                    call('delete', 'enminst/vcs_lsb_vm_status_script'),
                    call('put', 'enminst/vm_utils_script', 'YmxhYWFh'),
                    call('delete', 'enminst/vm_utils_script')
                    ])
        mock_run_cmd.assert_has_calls([
        call("mco rpc filemanager pull_file 'consul_url=http://ms-1:8500/v1/kv/enminst/vcs_lsb_vm_status_script' 'file_path=/usr/share/litp/vcs_lsb_vm_status' -I ieatrcxb6147  -I ieatrcxb6148  -I ieatrcxb6149 ",
            timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT),
        call("mco rpc filemanager pull_file 'consul_url=http://ms-1:8500/v1/kv/enminst/vm_utils_script' 'file_path=/usr/share/litp_libvirt/vm_utils' -I ieatrcxb6147  -I ieatrcxb6148  -I ieatrcxb6149 ",
            timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)])

        mock_exists.return_value = True
        self.upgrader._do_consul_action.reset_mock()
        mock_run_cmd.reset_mock()

        self.upgrader._pre_nodes_push_artifacts()
        mock_read_file.assert_has_calls([call('/opt/ericsson/nms/litp/etc/puppet/modules/neo4j/templates/neo4jbur_rhel7.erb')])
        self.upgrader._do_consul_action.assert_has_calls([
                    call('put', 'enminst/neo4jbur_script', 'YmxhYWFh'),
                    call('delete', 'enminst/neo4jbur_script'),
                    call('put', 'enminst/vcs_lsb_vm_status_script', 'YmxhYWFh'),
                    call('delete', 'enminst/vcs_lsb_vm_status_script'),
                    call('put', 'enminst/vm_utils_script', 'YmxhYWFh'),
                    call('delete', 'enminst/vm_utils_script')
                    ])
        mock_run_cmd.assert_has_calls([
        call("mco rpc filemanager pull_file 'consul_url=http://ms-1:8500/v1/kv/enminst/neo4jbur_script' 'file_path=/ericsson/3pp/neo4j/dbscripts/neo4jbur_sg_service.sh' -I ieatrcxb3055  -I ieatrcxb6146 ",
            timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT),
        call("mco rpc filemanager pull_file 'consul_url=http://ms-1:8500/v1/kv/enminst/vcs_lsb_vm_status_script' 'file_path=/usr/share/litp/vcs_lsb_vm_status' -I ieatrcxb6147  -I ieatrcxb6148  -I ieatrcxb6149 ",
            timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT),
        call("mco rpc filemanager pull_file 'consul_url=http://ms-1:8500/v1/kv/enminst/vm_utils_script' 'file_path=/usr/share/litp_libvirt/vm_utils' -I ieatrcxb6147  -I ieatrcxb6148  -I ieatrcxb6149 ",
            timeout_secs=TestRh7UpgradeEnm.CMD_TIMEOUT)])

    def test_upgrd_vx_ver(self):
        self.upgrader._run_rpc_mco = Mock(return_value=(0, {}))
        node_data = {'db-1': {}, 'db-2': {}}
        self.upgrader.sfha_nodes = node_data
        self.upgrader._upgrd_vx_ver()

        expected = 'mco rpc -I db-1 -I db-2 enminst upgrade_dg_versions ' + \
                   'dg_target_ver=240 dl_target_ver=13'

        self.upgrader._run_rpc_mco.assert_called_with(expected)

        # ---
        results = {'db-1': {'errors': '',
                            'data': {'retcode': 0}},
                   'db-2': {'errors': 'Error running command',
                            'data': {'retcode': 1,
                                     'err': 'Error running command'}}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, results))
        self.assertRaises(SystemExit, self.upgrader._upgrd_vx_ver)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_enm_repo_names_from_paths')
    @patch('rh7_upgrade_enm.shutil.rmtree')
    @patch('rh7_upgrade_enm.os.path.exists')
    def test_clean_yum_repos(self, mock_exists, mock_rmtree,
                             mock__get_enm_repo_names_from_paths):
        mock_exists.return_value = True
        mock__get_enm_repo_names_from_paths.return_value = ENM_REPO_NAMES

        Rh7EnmUpgrade._clean_yum_repos()

        prefix = '/var/www/html/'
        expected = [call(prefix + '3pp'),
                    call(prefix + '3pp_rhel6'),
                    call(prefix + 'ENM'),
                    call(prefix + 'ENM_rhel6'),
                    call(prefix + 'ENM_asrstream'),
                    call(prefix + 'ENM_asrstream_rhel6'),
                    call(prefix + 'ENM_automation'),
                    call(prefix + 'ENM_automation_rhel6'),
                    call(prefix + 'ENM_common'),
                    call(prefix + 'ENM_common_rhel6'),
                    call(prefix + 'ENM_db'),
                    call(prefix + 'ENM_db_rhel6'),
                    call(prefix + 'ENM_eba'),
                    call(prefix + 'ENM_eba_rhel6'),
                    call(prefix + 'ENM_ebsstream'),
                    call(prefix + 'ENM_ebsstream_rhel6'),
                    call(prefix + 'ENM_esnstream'),
                    call(prefix + 'ENM_esnstream_rhel6'),
                    call(prefix + 'ENM_events'),
                    call(prefix + 'ENM_events_rhel6'),
                    call(prefix + 'ENM_models'),
                    call(prefix + 'ENM_models_rhel6'),
                    call(prefix + 'ENM_ms'),
                    call(prefix + 'ENM_ms_rhel6'),
                    call(prefix + 'ENM_scripting'),
                    call(prefix + 'ENM_scripting_rhel6'),
                    call(prefix + 'ENM_services'),
                    call(prefix + 'ENM_services_rhel6'),
                    call(prefix + 'ENM_streaming'),
                    call(prefix + 'ENM_streaming_rhel6')]

        mock_rmtree.assert_has_calls(expected)

    @patch('rh7_upgrade_enm.PostgresService.version')
    @patch('rh7_upgrade_enm.PostgresService.can_uplift')
    @patch('rh7_upgrade_enm.PostgresService.need_uplift')
    @patch('rh7_upgrade_enm.PostgresService.is_contactable')
    def test_all_postgres_uplift_req(self, is_contactable, need_uplift,
                                     can_uplift, version):

        is_contactable.return_value = True
        need_uplift.return_value = True
        can_uplift.return_value = True

        self.upgrader.processed_args = argparse.Namespace(model='/path/to/model')
        self.upgrader._chk_postgres_uplift_req()

        for mock in [is_contactable, need_uplift, can_uplift]:
            mock.assert_called_once()

    @patch('rh7_upgrade_enm.PostgresService.need_uplift')
    @patch('rh7_upgrade_enm.PostgresService.is_contactable')
    def test_postgres_not_contactable(self, is_contactable, need_uplift):

        is_contactable.return_value = False

        self.upgrader.processed_args = argparse.Namespace(model='/path/to/model')
        with self.assertRaises(SystemExit):
            self.upgrader._chk_postgres_uplift_req()

        is_contactable.assert_called_once()
        need_uplift.assert_not_called()

    @patch('rh7_upgrade_enm.PostgresService.version')
    @patch('rh7_upgrade_enm.PostgresService.can_uplift')
    @patch('rh7_upgrade_enm.PostgresService.need_uplift')
    @patch('rh7_upgrade_enm.PostgresService.is_contactable')
    def test_postgres_no_need_uplift(self, is_contactable, need_uplift,
                                     can_uplift, version):

        is_contactable.return_value = True
        need_uplift.return_value = False

        self.upgrader.processed_args = argparse.Namespace(model='/path/to/model')
        self.upgrader._chk_postgres_uplift_req()

        for mock in [is_contactable, need_uplift]:
            mock.assert_called_once()

        can_uplift.assert_not_called()

    @patch('rh7_upgrade_enm.PostgresService.perc_space_used')
    @patch('rh7_upgrade_enm.PostgresService.version')
    @patch('rh7_upgrade_enm.PostgresService.can_uplift')
    @patch('rh7_upgrade_enm.PostgresService.need_uplift')
    @patch('rh7_upgrade_enm.PostgresService.is_contactable')
    def test_postgres_cant_uplift(self, is_contactable, need_uplift,
                                  can_uplift, version, perc_space_used):

        is_contactable.return_value = True
        need_uplift.return_value = True
        can_uplift.return_value = False

        self.upgrader.processed_args = argparse.Namespace(model='/path/to/model')
        with self.assertRaises(SystemExit):
            self.upgrader._chk_postgres_uplift_req()

        for mock in [is_contactable, need_uplift, can_uplift]:
            mock.assert_called_once()

    def test_enable_selinux(self):
        node_data = {'db-1': {'cluster':'/a/b/c'}}
        self.upgrader._set_selinux_on_nodes = Mock()
        self.upgrader.sfha_nodes = node_data
        self.upgrader._enable_selinux()

    def test_reboot_nodes(self):
        node_data = {'db-1': {'cluster':'/a/b/c'}}
        self.upgrader._ordered_reboot_nodes = Mock()
        self.upgrader.sfha_nodes = node_data
        self.upgrader._reboot_nodes()

    def _get_node_test_data(self):
        return {'db-1': {'cluster': '/a/b/c1',
                         'node': '/x/y/db1',
                         'node-id': 'db1'},
                'db-2': {'cluster': '/a/b/c1',
                         'node': '/x/y/db2',
                         'node-id': 'db2'}}

    def test_assert_uniq_cluster(self):
        node_data = self._get_node_test_data()
        self.upgrader.sfha_nodes = node_data
        self.upgrader._assert_uniq_cluster()

        # ----

        node_data['db-2']['cluster'] = '/a/b/c2'
        self.upgrader.sfha_nodes = node_data
        self.assertRaises(SystemExit, self.upgrader._assert_uniq_cluster)

    def test_set_selinux_on_nodes(self):
        node_data = self._get_node_test_data()
        result_data1 = {'db-1': {}, 'db-2': {}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, result_data1))

        self.upgrader._set_selinux_on_nodes(node_data.keys())

        expected = 'mco rpc -I db-1 -I db-2 enminst set_selinux mode=enforcing'
        self.upgrader._run_rpc_mco.assert_called_with(expected)

        # ----
        result_data2 = {'db-1': {'errors': 'Something went wrong'},
                        'db-2': {}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, result_data2))
        self.assertRaises(SystemExit, self.upgrader._set_selinux_on_nodes,
                          node_data.keys())
        # ----
        result_data3 = {'db-2': {'errors': 'Something else went wrong'},
                        'db-1': {}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, result_data3))
        self.assertRaises(SystemExit, self.upgrader._set_selinux_on_nodes,
                          node_data.keys())

        # ----
        result_data4 = {'db-1': {'errors': 'More things went wrong'},
                        'db-2': {'errors': 'Even more things went wrong'}}
        self.upgrader._run_rpc_mco = Mock(return_value=(0, result_data4))
        self.assertRaises(SystemExit, self.upgrader._set_selinux_on_nodes,
                          node_data.keys())

    def test_ordered_reboot_nodes(self):
        def _create_pac(order=['db1', 'db2']):
            # Create a PluginApiContext mock
            qitem = Mock(node_upgrade_ordering=order)
            pac = Mock()
            pac.query_by_vpath = Mock(return_value=qitem)
            return pac

        self.upgrader._run_litp_plan = Mock()
        self.upgrader._monitor_litp_plan = Mock()
        self.upgrader._run_command = Mock(return_value=(0, None))

        node_data = self._get_node_test_data()
        self.upgrader.plugin_api_context = _create_pac()

        crp_prefix = 'litp create_reboot_plan -p '
        expected = [call(crp_prefix + '/x/y/db1'),
                    call(crp_prefix + '/x/y/db2')]

        self.upgrader._ordered_reboot_nodes('/a/b/c1', node_data)
        self.upgrader._run_command.assert_has_calls(expected)

        # ---

        self.upgrader.plugin_api_context = _create_pac(order=['db2', 'db1'])
        self.upgrader._run_command.reset_mock()
        expected = [call(crp_prefix + '/x/y/db2'),
                    call(crp_prefix + '/x/y/db1')]

        self.upgrader._ordered_reboot_nodes('/a/b/c1', node_data)
        self.upgrader._run_command.assert_has_calls(expected)

        # ---
        self.upgrader._run_command = Mock(return_value=(-1,None))
        self.assertRaises(SystemExit, self.upgrader._ordered_reboot_nodes,
                          '/a/b/c1', node_data)

    def test_write_working_file(self):
        self.upgrader._write_to_file = Mock()
        content = 'Mary had a little lamb'
        self.upgrader._write_working_file(content)
        filename = '/opt/ericsson/enminst/runtime/enminst_working.cfg'
        self.upgrader._write_to_file.assert_called_with(filename, content,
                                                        user='root', group='root')

    @patch('rh7_upgrade_enm.EncryptPassword')
    @patch('rh7_upgrade_enm.Substituter')
    @patch('rh7_upgrade_enm.os.path.exists')
    @patch('rh7_upgrade_enm.os.remove')
    @patch('rh7_upgrade_enm.unity_model_updates')
    def test_create_to_state_dd(self, mock_unity_model_updates, mock_remove,
                                mock_exists,
                                mock_subr, mock_encrypter):
        mock_remove.return_value = True
        mock_exists.return_value = True
        expected_xml = '''\
<?xml version="1.0" encoding="UTF-8"?>
  <litp:root xmlns:litp="http://www.ericsson.com/litp"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.ericsson.com/litp litp--schema/litp.xsd" id="root">
  <litp:root-deployments-collection id="deployments">
  </litp:root>
'''

        mock_subr.output_xml = ''
        mock_subr.enminst_working = None
        mock_subr.build_full_file.return_value = True
        mock_subr.read_file.return_value = ''
        mock_subr.replace_values = expected_xml
        mock_subr.verify_xml.return_value = True
        mock_subr.write_file.return_value = True
        mock_unity_model_updates.return_value = True

        mock_encrypter.encrypt_configmanager_passwords.return_value = True

        self.upgrader._get_to_state_iso_qcow_names = Mock(return_value=True)
        self.upgrader._get_ms_uuid_val = Mock(return_value=True)
        self.upgrader._write_to_file = Mock(return_value=True)
        self.upgrader._write_working_file = Mock(return_value=True)
        self.upgrader.processed_args = Mock(verbose=False,
                                            model='',
                                            sed='')

        expected = 'vm_ssh_key=file:///root/.ssh/vm_private_key.pub'

        self.upgrader._create_to_state_dd()

        self.upgrader._write_working_file.assert_valled_with(expected)

        expected = '/opt/ericsson/enminst/runtime/enm_deployment.xml'
        mock_unity_model_updates.assert_called_once_with(expected)

    @patch('litp.core.plugin_context_api.PluginApiContext.query_by_vpath')
    @patch('os.listdir')
    def test_init_plugin_api_context(self, mock_listdir, mock_query):

        mock_listdir.return_value = []

        def query_side_effect(*args):
            from sqlalchemy.exc import ProgrammingError
            raise ProgrammingError('select', 'unknown params', 'unknown orig')

        mock_query.side_effect = query_side_effect

        tmp_file = tempfile.NamedTemporaryFile().name
        with open(tmp_file, 'w') as ofile:
            ofile.write('[global]\nsqlalchemy.url: "sqlite://"')

        self.assertRaises(SystemExit,
                          self.upgrader._init_plugin_api_context,
                          conf_file=tmp_file, timeout=2)

        # ----

        mock_query.reset_mock()
        mock_query.side_effect = None
        mock_query.return_value = Mock()

        self.upgrader._init_plugin_api_context(conf_file=tmp_file)

        os.remove(tmp_file)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._get_stage_data')
    def test_assert_uplift_p1_done(self, mock_get_sdata):
        final_stage = '99'
        mock_get_sdata.return_value = [{'idx': final_stage}]

        for (cmpltd_stage, error_expected) in \
            (('80', True), ('98', True), ('100', True),
             ('110', True), ('', True), (None, True), (final_stage, False)):
            self.upgrader._read_trckr_stg_idx = Mock(return_value=cmpltd_stage)
            if error_expected:
                self.assertRaises(SystemExit,
                                  self.upgrader._assert_uplift_p1_done)
            else:
                self.upgrader._assert_uplift_p1_done()

    def test_cmplt_sfha_uplift(self):
        self.upgrader.processed_args = Mock(action='complete_sfha_uplift')

        self.upgrader._assert_rhel_version = Mock(return_value=True)
        self.upgrader._assert_uplift_p1_done = Mock(return_value=True)
        self.upgrader._assert_passwd_age = Mock(return_value=True)
        self.upgrader._unset_pam_config = Mock(return_value=True)
        self.upgrader._get_sfha_nodes = Mock(return_value={'db-1': {},
                                                           'db-2': {}})
        self.upgrader._assert_uniq_cluster = Mock(return_value=True)
        self.upgrader._upgrd_vx_ver = Mock(return_value=True)
        self.upgrader._enable_selinux = Mock(return_value=True)
        self.upgrader._reboot_nodes = Mock(return_value=True)
        self.upgrader._switch_db_grps = Mock(return_value=True)
        self.upgrader._create_crons = Mock(return_value=True)
        self.upgrader._perform_cmpltn_hlthchcks = Mock(return_value=True)
        self.upgrader._cmplt_sfha_uplift()

    def test_perform_cmpltn_hlthchcks(self):
        hc_data = {0x1: 'san_alert',
                   0x2: 'nas',
                   0x4: 'storagepool',
                   0x8: 'stale_mount',
                   0x10: 'node_fs',
                   0x20: 'puppet_enabled',
                   0x40: 'system_service',
                   0x80: 'vcs_cluster',
                   0x100: 'vcs_llt_heartbeat',
                   0x200: 'vcs_service_group',
                   0x400: 'consul',
                   0x4000: 'hw_resources'}

        self.upgrader._do_health_chks = Mock(return_value=True)
        self.upgrader._perform_cmpltn_hlthchcks()
        stage_hcs = sum(hc_data.keys()) - 0x4   # storagepool HC excluded
        self.upgrader._do_health_chks.assert_called_once_with(hc_data, stage_hcs)

    @patch('rh7_upgrade_enm.switch_dbcluster_groups')
    def test_switch_db_grps(self, mock_switcher):
        mock_switcher.side_effect = SystemExit('Something went wrong in DBs')
        self.assertRaises(SystemExit, self.upgrader._switch_db_grps)
        # ----
        mock_switcher.side_effect = None
        self.upgrader._switch_db_grps()

    @patch('rh7_upgrade_enm.litp_backup_state_cron')
    @patch('rh7_upgrade_enm.cleanup_java_core_dumps_cron')
    @patch('rh7_upgrade_enm.create_san_fault_check_cron')
    @patch('rh7_upgrade_enm.create_nasaudit_errorcheck_cron')
    def test_create_crons(self, mock_nas, mock_san, mock_java, mock_litp):
        for mocker in (mock_nas, mock_san, mock_java, mock_litp):
            mocker = Mock()

        self.upgrader._create_crons()

        mock_nas.assert_called_with('/etc/cron.d/nasaudit_error_check')
        mock_san.assert_called_with('/etc/cron.d/san_fault_checker')
        mock_java.assert_called_with('/etc/cron.daily/cleanup_java_core_dumps')
        mock_litp.assert_called_with('/etc/cron.d/litp_state_backup',
                                     '/ericsson/tor/data/enmbur/lmsdata/')

    def test_remove_files(self):
        self.upgrader._remove_file = Mock()
        self.upgrader._remove_files()
        rt_dir = '/opt/ericsson/enminst/runtime/'
        expected = [call(rt_dir + 'upgrade_enm_stage_data.txt'),
                    call(rt_dir + 'upgrade_enm_params.txt'),
                    call('/ericsson/tor/data/neo4j/dbcreds.yaml')]
        self.upgrader._remove_file.assert_has_calls(expected)

        # ----
        dd_name = '/tmp/deployment-description.xml'
        self.upgrader.processed_args = Mock()
        self.upgrader.processed_args.model = dd_name

        self.upgrader._remove_file.reset_mock()
        self.upgrader._remove_files()
        expected.append(call(dd_name))
        self.upgrader._remove_file.assert_has_calls(expected)

    @patch('os.remove')
    def test_remove_file(self, mock_remove):
        filename = '/foobar'

        mock_remove.side_effect = SystemExit
        self.assertRaises(SystemExit, self.upgrader._remove_file, filename)

        # ----
        mock_remove.side_effect = IOError(99, 'Error', filename)
        self.assertRaises(IOError, self.upgrader._remove_file, filename)

        # ----
        mock_remove.side_effect = OSError(99, 'Error', filename)
        self.assertRaises(OSError, self.upgrader._remove_file, filename)

        # ---
        mock_remove.side_effect = IOError(2, 'Not found', filename)
        self.upgrader._remove_file(filename)

        #----
        mock_remove.side_effect = OSError(2, 'Not found', filename)
        self.upgrader._remove_file(filename)

    @patch('os.system')
    @patch('os.path.isfile')
    @patch('rh7_upgrade_enm.ENMUpgrade.postgres_reload')
    def test_run_procedures(self, mock_reload, mock_isfile, mock_sys):
        os.environ['ENMINST_RUNTIME'] = '/tmp'

        mock_reload.side_effect = SystemExit
        self.assertRaises(SystemExit, self.upgrader._run_procedures)

        # ----
        mock_reload.side_effect = McoAgentException('Nothing serious')

        the_sed = '/tmp/the_sed.txt'
        self.upgrader.processed_args = Mock()
        self.upgrader.processed_args.sed = the_sed

        mock_isfile.return_value = False

        self.upgrader._run_procedures()

        script1 = '/opt/ericsson/enminst/bin/esadmin_password_set.sh'
        script2 = '/opt/ericsson/hw_comm/bin/hw_comm.sh'
        expected = [call(script) for script in (script1, script2)]

        mock_isfile.assert_has_calls(expected)

        #----
        mock_isfile.reset_mock()
        mock_isfile.return_value = True
        expected_list = [call(script1),
                         call(script2 + ' configure_ipmi -o disable ' + the_sed)]

        self.upgrader._run_procedures()
        self.assertTrue(all([expected in mock_sys.mock_calls
                             for expected in expected_list]))

    @patch('rh7_upgrade_enm.Deployer.update_version_and_history')
    def test_update_logs(self, mock_updater):
        msg = 'Something wrong with version or history'
        mock_updater.side_effect = IOError(msg)

        self.upgrader._update_logs()

        self.assertEquals(1, mock_updater.call_count)

    @patch('__builtin__.open')
    def test_update_cmd_arg_log(self, mock_open):
        self.upgrader.cmd_args = ['<ignore>', '--action', 'rh7_uplift', '-v']

        self.upgrader._update_cmd_arg_log()
        mock_open.assert_called_with('/opt/ericsson/enminst/log/cmd_arg.log', 'a')

        expected = './upgrade [rh7_upgrade_enm.sh] ' + \
                   ' '.join(self.upgrader.cmd_args[1:]) + '\n'

        fh = mock_open.return_value.__enter__.return_value
        fh.write.assert_called_once_with(expected)

    @patch('rh7_upgrade_enm.Rh7EnmUpgrade._run_command')
    def test_update_kickstart_template(self, mock_run_cmd):
        '''update_kickstart_template'''

        mock_run_cmd.return_value = (0, '')
        self.upgrader._update_kickstart_template("test command ")
        mock_run_cmd.assert_called_once_with('test command ')

    @patch('os.path.exists')
    def test_get_psql_host_option(self, mock_exists):
        '''test get_psql_host_option'''

        mock_exists.return_value = True
        self.upgrader._get_hostname = Mock(return_value='ms1')
        option_str = self.upgrader.get_psql_host_option()

        self.assertEqual(option_str, ' -h ms1')

    @patch('os.path.exists')
    def test_get_psql_host_option_none(self, mock_exists):
        '''test get_psql_host_option'''

        mock_exists.return_value = False
        self.upgrader._get_hostname = Mock(return_value='ms1')
        option_str = self.upgrader.get_psql_host_option()

        self.assertEqual(option_str, '')
