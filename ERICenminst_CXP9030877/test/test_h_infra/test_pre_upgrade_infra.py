import os
import unittest2
from mock import patch

from h_infra.pre_upgrade_infra import pre_snap_changes, ParentIdIterator
from h_litp.litp_rest_client import LitpException

LITP_UPDATE_LV_VAR = 'litp update -p /infrastructure/storage/' \
                     'storage_profiles/db_node_storage_profile/' \
                     'volume_groups/vg1/file_systems/lv_var -o snap_size=40 size=52G'
LITP_CREATE_LV_VAR2 = 'litp create -t file-system -p /infrastructure/' \
                      'storage/storage_profiles/db_node_storage_profile/' \
                      'volume_groups/vg1/file_systems/lv_var2 -o ' \
                      'snap_size=0 mount_point=/var2 type=ext4 size=2G'
LITP_CREATE_SFS_NEW_FS = 'litp create -t sfs-filesystem -p /infrastructure/' \
                         'storage/storage_providers/sfs/pools/ENM266-pool/' \
                         'file_systems/fs_new_fs -o path=/vx/ENM266-new_fs ' \
                         'snap_size=0 cache_name=ENM266_cache size=20G'
LITP_CREATE_EXPORT = 'litp create -t sfs-export -p /infrastructure/storage/' \
                     'storage_providers/sfs/pools/ENM266-pool/file_systems/' \
                     'fs_new_fs/exports/new_fs -o ' \
                     'ipv4allowed_clients=10.144.8.0/24 ' \
                     'options=rw,sync,no_root_squash'
LITP_CREATE_LUN_DISK = 'litp create -t lun-disk -p /infrastructure/' \
                       'systems/db-x/disks/lun_disk1 -o lun_name=LUN_DB ' \
                       'name=sdj balancing_group=high bootable=false ' \
                       'snap_size=0 storage_container=SAN_POOL shared=true ' \
                       'external_snap=false size=2G'

LITP_UPDATE_LUN_DISK2 = 'litp update -p /infrastructure/systems/db-x/disks/' \
                        'lun_disk2 -o size=5G'

LITP_UPDATE_LV_VAR_AFTER_PLAN_FAILURE = \
    'litp update -p /infrastructure/storage/storage_profiles/' \
    'db_node_storage_profile/volume_groups/vg1/file_systems/lv_var -o snap_size=40 size=50G'

REST_GET_LV_VAR_INITIAL = {
    "id": "lv_var",
    "item-type-name": "file-system",
    "applied_properties_determinable": True,
    "state": "Initial",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/infrastructure/' \
            'storage/storage_profiles/db_node_storage_profile/volume_groups/' \
            'vg1/file_systems/lv_var"
        },
        "item-type": {
            "href":
                "https://localhost:9999/litp/rest/v1/item-types/file-system"
        }
    },
    "properties": {
        "size": "50G",
        "snap_size": "40",
        "mount_point": "/var",
        "type": "ext4",
        "snap_external": "false"
    }
}

REST_GET_LV_VAR_APPLIED = {
    "id": "lv_var",
    "item-type-name": "file-system",
    "applied_properties_determinable": True,
    "state": "Applied",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/infrastructure/' \
            'storage/storage_profiles/db_node_storage_profile/volume_groups/' \
            'vg1/file_systems/lv_var"
        },
        "item-type": {
            "href":
                "https://localhost:9999/litp/rest/v1/item-types/file-system"
        }
    },
    "properties": {
        "size": "50G",
        "snap_size": "40",
        "mount_point": "/var",
        "type": "ext4",
        "snap_external": "false"
    }
}

REST_GET_LV_VAR_UPDATED = {
    "id": "lv_var",
    "item-type-name": "file-system",
    "applied_properties_determinable": True,
    "state": "Updated",
    "_links": {
        "self": {
            "href": "https://localhost:9999/litp/rest/v1/infrastructure/' \
            'storage/storage_profiles/db_node_storage_profile/volume_groups/' \
            'vg1/file_systems/lv_var"
        },
        "item-type": {
            "href":
                "https://localhost:9999/litp/rest/v1/item-types/file-system"
        }
    },
    "properties": {
        "size": "50G",
        "snap_size": "40",
        "mount_point": "/var",
        "type": "ext4",
        "snap_external": "false"
    }
}

REST_GET_LUN_DISK2 = {
    'id': 'lun_disk2',
    'item-type-name': 'lun-disk',
    'applied_properties_determinable': True,
    'state': 'Applied',
    '_links': {'self':
               {'href': 'http://127.0.0.1/litp/rest/v1/infrastructure/'
                        'systems/db-x_system/disks/lun_disk2'},
               'item-type': {'href': 'http://127.0.0.1/litp/rest/v1/'
                                     'item-types/lun-disk'}},
    'properties': {
        'lun_name': 'LUN_DB2',
        'name': 'sdb',
        'balancing_group': 'high',
        'external_snap': 'false',
        'bootable': 'false',
        'disk_part': 'false',
        'storage_container': 'SAN_POOL',
        'snap_size': '0',
        'shared': 'true',
        'size': '3G',
        'uuid': '600601606A703C009009CF603F69E611'}}


class TestPreUpgradeInfra(unittest2.TestCase):

    @patch('h_infra.pre_upgrade_infra.LitpRestClient.exists')
    @patch('h_infra.pre_upgrade_infra.LitpRestClient.get')
    def test_update_create_items(self, get, m_exists):
        """
        Test cases: update LV size, create new LV FS, create SFS FS,
        create SFS export, create NFS mount, create VM NFS mount,
        create inherit NFS
        """
        current_path = os.path.dirname(__file__)
        litp_commands = [LITP_UPDATE_LV_VAR, LITP_CREATE_LV_VAR2,
                         LITP_CREATE_SFS_NEW_FS, LITP_CREATE_EXPORT,
                         LITP_CREATE_LUN_DISK, LITP_UPDATE_LUN_DISK2]

        get.side_effect = [REST_GET_LV_VAR_INITIAL,
                           LitpException(404, 'Not Found'),
                           LitpException(404, 'Not Found'),
                           LitpException(404, 'Not Found'),
                           LitpException(404, 'Not Found'),
                           REST_GET_LUN_DISK2]

        m_exists.return_value = True
        comm_list = pre_snap_changes('{0}/dd_example_1.xml'.format(
                                                 current_path))
        self.assertTupleEqual(comm_list, (litp_commands, True))

    @patch('h_infra.pre_upgrade_infra.LitpRestClient.exists')
    @patch('h_infra.pre_upgrade_infra.LitpRestClient.get')
    def test_no_changes_to_litp_model(self, get, m_exists):
        """
        Test case: No updates to the LITP model required. The item state is
        applied.
        """
        current_path = os.path.dirname(__file__)
        get.return_value = REST_GET_LV_VAR_APPLIED
        m_exists.return_value = True
        comm_list = pre_snap_changes('{0}/dd_example_2.xml'.format(
                current_path))
        self.assertTupleEqual(comm_list, ([], False))

    @patch('h_infra.pre_upgrade_infra.LitpRestClient.exists')
    @patch('h_infra.pre_upgrade_infra.LitpRestClient.get')
    def test_update_litp_model_after_plan_failure(self, get, m_exists):
        """
        Test case: Update LITP model after plan failure
        """
        current_path = os.path.dirname(__file__)
        get.return_value = REST_GET_LV_VAR_UPDATED
        m_exists.return_value = True
        comm_list = pre_snap_changes('{0}/dd_example_2.xml'.format(
            current_path))
        self.assertTupleEqual(comm_list,
                             ([LITP_UPDATE_LV_VAR_AFTER_PLAN_FAILURE], True))

    @patch('h_infra.pre_upgrade_infra.LitpRestClient.get')
    def test_raise_litp_rest_exception(self, get):
        """
        Test case: raise LitpException with fault code different than 404
        """
        current_path = os.path.dirname(__file__)
        get.side_effect = LitpException(40, 'test error')
        self.assertRaises(LitpException, pre_snap_changes,
                          '{0}/dd_example_2.xml'.format(current_path))


class TestParentIdIterator(unittest2.TestCase):
    def test_raise_stop_iteration(self):
        it = ParentIdIterator(None)
        self.assertRaises(StopIteration, it.next)
