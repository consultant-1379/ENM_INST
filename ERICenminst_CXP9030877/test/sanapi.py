from sanapiinfo import StorageGroupInfo, StoragePoolInfo, SnapshotInfo

class SanApiIntegration(object):
    _POOLS = {}
    _SNAPS = []
    _ALERTS = []

    @staticmethod
    def api_builder(array_type, logger=None):
        if 'vnx1' == array_type.lower():
            return Vnx1Api()
        elif 'vnx2' == array_type.lower():
            return Vnx2Api()
        elif 'unity' == array_type.lower():
            return UnityApi()
        else:
            raise Exception()

    @staticmethod
    def setup_storage_pool(name, size, available):
        SanApiIntegration._POOLS[name] = StoragePoolInfo(name, name, '1',
                                                         size, available)

    @staticmethod
    def get_storage_pool(name):
        return SanApiIntegration._POOLS[name]

    @staticmethod
    def modify_storage_pool(name, size):
        return SanApiIntegration._POOLS[name]

    @staticmethod
    def get_snapshots():
        return SanApiIntegration._SNAPS

    @staticmethod
    def get_san_alerts():
        return SanApiIntegration._ALERTS

    @staticmethod
    def get_hw_san_alerts():
        return SanApiIntegration._ALERTS

    @staticmethod
    def get_filtered_san_alerts(alert_filter):
        return SanApiIntegration._ALERTS

    @staticmethod
    def clear_snapshots():
        SanApiIntegration._SNAPS = []

    @staticmethod
    def snapshot(storage_site_id):
        """
        Add a snapshot to the pool.

        :param storage_site_id: The SAN Base Storage Site Id (Storage
            Group Prefix)
        :type storage_site_id: str
        """
        SanApiIntegration._SNAPS.append(SnapshotInfo('10',
                            'LITP2_' + storage_site_id + '_boot2',
                            'now',
                            'available',
                            'LITP2_' + storage_site_id + '_boot2'))


    def __init__(self, resource_lun_id, snapshot_name, created_time,
                 snap_state, resource_lun_name, description=None):
        super(SanApiIntegration, self).__init__()
        self._res_id = resource_lun_id
        self._snap_name = snapshot_name
        self._creation_time = created_time
        self._state = snap_state
        self._res_name = resource_lun_name
        self._description = description


class SanApi(object):
    def __init__(self):
        super(SanApi, self).__init__()
        self.initialised = False

    def initialise(self, sp_ips, username, password, scope, getcert=True,
                   vcheck=True, esc_pwd=False):
        self.initialised = True

    def get_storage_groups(self):
        pass

    def get_storage_group(self, sg_name, logmsg=True):
        return StorageGroupInfo(sg_name, None, False, [], [])

    def get_lun(self, lun_id=None, lun_name=None, logmsg=True):
        pass

    def get_luns(self, container_type=None, container=None, sg_name=None):
        pass

    def get_version(self):
        raise NotImplementedError()

    def get_storage_pool(self, name):
        return SanApiIntegration.get_storage_pool(name)

    def modify_storage_pool(self, name, size):
        return SanApiIntegration.modify_storage_pool(name, size)

    def get_snapshots(self):
        return SanApiIntegration.get_snapshots()

    def disconnect_host(self, sg_name, host):
        return True

    def deregister_hba_uid(self, hba_uid):
        return True

    def delete_lun(self, lun_id=None, array_specific_options=None):
        return True

    def remove_luns_from_storage_group(self, sg_name, hlus):
        return True

    def delete_storage_group(self, sg_name):
        return True

    def get_san_info(self):
        return True

    def get_san_alerts(self):
        return SanApiIntegration.get_san_alerts()

    def get_hw_san_alerts(self):
        return SanApiIntegration.get_hw_san_alerts()

    def get_filtered_san_alerts(self, alert_filter):
        return SanApiIntegration.get_filtered_san_alerts(alert_filter)

    def _get_pool_lun_name_from_lun_id(self, lun_id):
        return True

    def create_snapshot(self, lun, snap, description=None):
        return True

    def create_snapshot_with_id(self, lun_id, snap_name, description=None):
        return True

    def delete_snapshot(self, snap):
        return True

    def _restore_snapshot(self, lun_id, snap_name, delete_backup_snap, backup_name=None):
        return True

    def restore_snapshot_by_id(self, lun_id, snap_name, delete_backup_snap=True, backup_name=None):
        return True

    def get_hba_port_info(self, wwn=None, host=None, storage_processor=None, sp_port=None):
        return []


class VnxCommonApi(SanApi):
    def get_version(self):
        return '-1'


class Vnx1Api(VnxCommonApi):
    def get_version(self):
        return '1'


class Vnx2Api(VnxCommonApi):
    def get_version(self):
        return '2'


class UnityApi(SanApi):
    def get_version(self):
        return '-1'


def api_builder(array_type, logger=None):
    return SanApiIntegration.api_builder(array_type, logger)
