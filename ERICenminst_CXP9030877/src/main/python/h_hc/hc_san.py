"""
SAN StoragePool health checks
"""
# ********************************************************************
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
# ********************************************************************

from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpObject
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_nas_console import normalize_size
from h_util.h_utils import ExitCodes, read_enminst_config
from litp.core.base_plugin_api import BasePluginApi
from litp.core.model_manager import ModelManager
from sanapi import api_builder
from san_fault_check import SanFaultCheck
from sanapiexception import SanApiOperationFailedException


class SanHealthChecks(object):
    """
    Class to check the usage of the deployments StoragePool usage.
    """
    P_STORAGE = '/infrastructure/storage'
    P_PROFILES = P_STORAGE + '/storage_profiles'
    P_PROVIDERS = P_STORAGE + '/storage_providers'
    P_SYSTEMS = '/infrastructure/systems'
    R_CONTAINERS = 'storage_containers'

    C_SAN_POOL_USE_NS = 'san_pool_usage_ns'
    C_SAN_POOL_USE_WS = 'san_pool_usage_ws'

    K_DATA = 'data'
    K_IP_A = 'ip_a'
    K_IP_B = 'ip_b'
    K_LOGIN_SCOPE = 'login_scope'
    K_LUN_NAME = 'lun_name'
    K_NAME = 'name'
    K_PASSWORD_KEY = 'password_key'
    K_SAN_TYPE = 'san_type'
    K_SIZE = 'size'
    K_SHARED = 'shared'
    K_SNAP_SIZE = 'snap_size'
    K_STORAGE_CONTAINER = 'storage_container'
    K_STORAGE_SITE_ID = 'storage_site_id'
    K_TYPE = 'type'
    K_USERNAME = 'username'

    T_FILE_SYSTEM = 'file-system'
    T_LUN_DISK = 'lun-disk'
    T_PROVIDERS_TYPES = ['san-emc']

    V_VXFS = 'vxfs'
    V_POOL_TYPES = ['POOL']

    SAN_ALERT_THRESHOLD = 2
    ALARM_INACTIVE = 2

    def __init__(self, verbose=False):
        """
        Constructor

        :param verbose: Enable debug log
        :type verbose: bool
        """
        super(SanHealthChecks, self).__init__()
        self.__logger = init_enminst_logging(logger_name='enmhealthcheck')
        self._litp = LitpRestClient()
        self._verbose = verbose
        self.alert_filter = [SanFaultCheck.make_alert_filter()]

    def info(self, message):
        """
        Log a message at INFO level

        :param message: The message to log
        :type message: str
        """
        self.__logger.info(message)

    def error(self, message):
        """
        Log a message at ERROR level

        :param message: The message to log
        :type message: str
        """
        self.__logger.error(message)

    def verbose(self, message):
        """
        Log a message at VERBOSE level. VERBOSE is enabled by specifying the
         '-v' flag to the CLI calling the healthcheck.

        :param message: The message to log
        :type message: str
        """
        if self._verbose:
            self.__logger.info(message)

    def _get_modeled_providers(self):
        """
        Get a list of SAN providers and the StoragePool they contain.

        :returns: Collection of StoragePool providers
        :rtype: dict
        """
        _groups = {}
        self.verbose('Getting SAN Providers.')
        for _provider in self._litp.get_children(SanHealthChecks.P_PROVIDERS):
            _pvder = LitpObject(None, _provider[SanHealthChecks.K_DATA],
                                self._litp.path_parser)
            if _pvder.item_type in SanHealthChecks.T_PROVIDERS_TYPES:
                cpath = '{0}/{1}'.format(_pvder.path,
                                         SanHealthChecks.R_CONTAINERS)
                for _container in self._litp.get_children(cpath):
                    _cntr = LitpObject(_provider,
                                       _container[SanHealthChecks.K_DATA],
                                       self._litp.path_parser)
                    ctype = _cntr.get_property(SanHealthChecks.K_TYPE)
                    if ctype in SanHealthChecks.V_POOL_TYPES:
                        if _pvder not in _groups:
                            _groups[_pvder] = []
                        _groups[_pvder].append(_cntr)
        return _groups

    @staticmethod
    def _get_api(san):
        """
        Get a sanapi instance for a SAN.

        :param san: Model entry with SAN env details.
        :type san: LitpObject

        :returns: SanApi instance.
        :rtype: SanApi
        """
        sps = [
            san.get_property(SanHealthChecks.K_IP_A),
            san.get_property(SanHealthChecks.K_IP_B)
        ]
        username = san.get_property(SanHealthChecks.K_USERNAME)
        pass_key = san.get_property(SanHealthChecks.K_PASSWORD_KEY)

        model_manager = ModelManager()
        base_api = BasePluginApi(model_manager)
        passwd = base_api.get_password(pass_key, username)

        atype = san.get_property(SanHealthChecks.K_SAN_TYPE)
        _api = api_builder(atype, None)
        _api.initialise(sps, username, passwd,
                        san.get_property(SanHealthChecks.K_LOGIN_SCOPE),
                        esc_pwd=True)

        return _api

    def _get_total_pool_required(self):
        """
        Get the size of the StoragePools required to hold all LUN's defined in
         the model.

        :returns: Size of a StoragePool, in Mb, to hold all modeled LUNs.
        :rtype: dict
        """
        lun_disks = []
        self._litp.get_items_by_type(SanHealthChecks.P_SYSTEMS,
                                     SanHealthChecks.T_LUN_DISK,
                                     lun_disks)

        # LUN snaps are either OFF (snap_size == 0) or ON (snap_size >= 1)
        # so to hold snaps for all LUNs you'de need free capacity equal to
        # total LUN size....
        _shared_luns = []
        pools = {}
        snaps = {}
        for item in lun_disks:
            _lun = LitpObject(None, item[SanHealthChecks.K_DATA],
                              self._litp.path_parser)
            l_size = normalize_size(
                    _lun.get_property(SanHealthChecks.K_SIZE))
            lun_name = _lun.get_property(SanHealthChecks.K_LUN_NAME)
            shared = _lun.get_bool_property(SanHealthChecks.K_SHARED)
            if shared and lun_name in _shared_luns:
                self.verbose('Skipping {0}, already '
                             'counted.'.format(lun_name))
                continue
            vmessage = 'Counting {0} {1}M'.format(lun_name, l_size)
            _shared_luns.append(lun_name)
            lunsp = _lun.get_property(SanHealthChecks.K_STORAGE_CONTAINER)
            tots = pools.get(lunsp, 0) + l_size
            pools[lunsp] = tots
            if _lun.get_int_property(SanHealthChecks.K_SNAP_SIZE) > 0:
                snap_alloc = l_size * .15
                tots = snaps.get(lunsp, 0) + snap_alloc
                snaps[lunsp] = tots
                vmessage += ' plus 15% ({0}M) snapshot allocation'.format(
                        snap_alloc)
            self.verbose(vmessage)
        return pools, snaps

    def check_storagepool(self, storage_api,  # pylint: disable=R0913,R0914
                          storage_pool, pool_watermark, lun_require,
                          snap_alloc, has_snaps, san_type):
        """
        Check the StoragePool usage is below a certain percentage.

        :param storage_api: Storage API
        :type storage_api: SanApi
        :param storage_pool: The storage pool to check
        :type storage_pool: LitpObject
        :param pool_watermark: Max usage percent
        :type pool_watermark: int
        :param lun_require: Total space, in Gb, required to hold all LUNs
         modeled in the StorageGroup
        :type lun_require: float
        :param snap_alloc: Total space, in Gb, required to hold all LUN
         snapshots (as defined in the LITP model)
        :type snap_alloc: float
        :param has_snaps: Are there snapshots in the storage pools.
        :type has_snaps: bool

        :returns: True if the pools usage percentage is above "pool_watermark",
         False otherwise
        :rtype: bool
        """
        pool_name = storage_pool.get_property(SanHealthChecks.K_NAME)
        pool = storage_api.get_storage_pool(pool_name)

        if san_type != "unity":
            try:
                storage_api.modify_storage_pool(pool_name, 99)
            except AttributeError:
                self.info('modify_storage_pool functionality not available')

        # For these checks the total allowable capacity is 99% of what the
        # SAN reports as available. Once the SAN reaches 99% it will start
        # dropping snaps if they exist.
        total_cap = float(pool.size)  # User Capacity (GBs)
        total_cap_gb = round((total_cap / 1024), 2)
        avail_cap = float(pool.available)  # Available Capacity (GBs)

        usage = (total_cap * .99) - avail_cap
        usage_perc = round((usage / (total_cap * .99)) * 100, 2)

        usage_gb = round((usage / 1024), 2)
        avail_cap_gb = round((avail_cap / 1024), 2)

        lun_require_gb = round((lun_require / 1024), 2)
        snap_alloc_gb = round((snap_alloc / 1024), 2)
        total_required = lun_require + snap_alloc

        total_required_gb = round((total_required / 1024), 2)

        dim_error = 'Please ensure the StoragePool "{0}" has been correctly' \
                    ' defined based on the "Storage Layouts" section in the' \
                    ' "ENM Installation Instructions" for this' \
                    ' deployment.'.format(pool_name)
        self.info('The calculation for this check is based on 99 percent of ' \
                    'total capacity in the StoragePool. Above that, SAN ' \
                    'emergency correction will begin to delete snapshots ' \
                    ' which would prevent successful rollback.')
        self.info('StoragePool {0} requires a capacity of {1}Gb '
                '({2}Gb for LUNs + snap reserve of {3}Gb)'.format(
                        pool_name, total_required_gb,
                        lun_require_gb, snap_alloc_gb))
        self.info('StoragePool {0} total usable capacity is {1}Gb'.format(
                pool_name, (total_cap_gb * .99)))
        if total_required_gb >= (total_cap_gb * .99):
            self.error(
                    'StoragePool {0} has insuffecient capacity '
                    'for modeled LUNs and snapshot reserve!'.format(pool_name))
            self.error(dim_error)
            return True
        self.info('StoragePool {0} has {1}Gb in use.'.format(
                pool_name, usage_gb))
        self.info('StoragePool {0} has {1}Gb available.'.format(
                pool_name, avail_cap_gb))
        self.info('StoragePool {0} current usage at '
                  '{1}%'.format(pool_name, usage_perc))

        if usage_perc >= pool_watermark:
            self.error('StoragePool {0} exceeds {1}% '
                       'usage!'.format(pool_name, pool_watermark))
            if has_snaps:
                self.error('Once the StoragePool {0} capacity reaches 99%'
                           ' it will start dropping snaps'.format(pool_name))
                self.error('If that happens it will not be possible '
                           'to rollback.'.format(pool_name))
                self.error('Either remove the existing snapshots or rollback'
                           ' the deployment.')
            else:
                self.error(dim_error)
            return True
        return False

    @staticmethod
    def has_snapshots(storage_api, storage_site_id):
        """
        Check if there are snapshots present in the site or not.

        :param storage_api: Storage API
        :type storage_api: SanApi
        :param storage_site_id: The SAN Base Storage Site Id
        :type storage_site_id: str
        :return:
        """
        _snaps = storage_api.get_snapshots()
        lun_prefix = 'LITP2_{0}_'.format(storage_site_id)
        return any([snap for snap in _snaps
                    if snap.resource_name.startswith(lun_prefix)])

    @staticmethod
    def get_watermark(snapshots_included):
        """
        Get the watermark to check the Pool against. This value depends on
        snapshots existing in the pool or not.

        :param snapshots_included: Are there snapshots in the pool or not.
        :type snapshots_included: bool
        :returns: The %usage value to raise an error.
        :rtype: int
        """
        config_key = SanHealthChecks.C_SAN_POOL_USE_WS if snapshots_included \
            else SanHealthChecks.C_SAN_POOL_USE_NS
        config = read_enminst_config()
        return int(config.get(config_key))

    def get_san_critical_alerts(self, storage_api, san_type):
        """
        Get the list of alerts from the SAN that are critical severity.

        :param storage_api: Storage API
        :type storage_api: SanApi
        :param san_type: vnx or unity
        :type san_type: String
        :return: The list of critical alerts from the SAN.
        :rtype: list
        :raises: SystemExit if it failed to get alerts from the SAN (unity).
        """
        self.info("Checking SAN alerts.")
        san_alerts = storage_api.get_san_alerts()
        self.info("Checking SAN HW alerts.")
        san_hw_alerts = storage_api.get_hw_san_alerts()
        if san_type == "unity":
            try:
                san_alerts = storage_api.get_filtered_san_alerts(
                             self.alert_filter)
            except SanApiOperationFailedException:
                self.error("Failed to get alerts from the SAN.")
                raise SystemExit(ExitCodes.ERROR)

            san_alerts_list = [alert for alert in san_alerts
                          if alert.severity ==
                          SanHealthChecks.SAN_ALERT_THRESHOLD
                          and alert.state != SanHealthChecks.ALARM_INACTIVE]
            return san_alerts_list, san_hw_alerts
        else:
            return san_alerts, san_hw_alerts

    def san_minor_major_alerts(self, san_dimm_alerts):
        """
        saparates the major and minor alerts
        from list of san HW alerts
        """
        minor_hw_alerts = [alert for alert in san_dimm_alerts\
                                 if '7' in alert[0] or '0' in alert[0]]
        if len(minor_hw_alerts) == len(san_dimm_alerts):
            self.info("There are Minor or Unknown HW alerts on the SAN")
            self.info("DIMM Slots: Health Status")
            for alert in san_dimm_alerts:
                alert = alert[1:]
                alert = alert.split(':')[0]
                self.info(': '.join(\
                             alert.split('[')).split(']')[0])
        else:
            self.error("There are alerts on the SAN.")
            self.error("DIMM Slots: Health Status")
            for alert in san_dimm_alerts:
                if '7' in alert[0] or '0' in alert[0]:
                    alert = alert[1:]
                alert = alert.split(':')[0]
                self.error(': '.join(\
                          alert.split('[')).split(']')[0])
            self.error("Contact DELL EMC Support"
                                 " Administrator.")
            raise SystemExit(ExitCodes.ERROR)

    def san_critical_alert_healthcheck(self):
        """
        Checks if the SAN is unity and checks if there
        are critical alerts.

        :raise SystemExit: If there are critical alerts on the SAN.
        """
        self.verbose('Getting modeled requirements.')
        _providers = self._get_modeled_providers()

        for _provider, _ in _providers.items():
            _api = self._get_api(_provider)

            if _provider.get_property(SanHealthChecks.K_SAN_TYPE) \
                    .lower() == "unity":
                san_alerts, san_hw_alerts = \
                   self.get_san_critical_alerts(_api, "unity")
                if san_alerts or san_hw_alerts:
                    if san_alerts:
                        self.error("There are alerts on the SAN.")
                        for alert in san_alerts:
                            self.verbose(alert)
                        self.error("Follow DELL EMC SAN Storage"
                                   " Critical Alert OPI.")
                        raise SystemExit(ExitCodes.ERROR)
                    if san_hw_alerts:
                        self.san_minor_major_alerts(san_hw_alerts)
                else:
                    self.info("There are no alerts on the SAN.")
            else:
                san_alerts, san_hw_alerts = \
                    self.get_san_critical_alerts(_api, "vnx")
                if san_alerts or san_hw_alerts:
                    self.error("There are alerts on the SAN.")
                    if san_alerts:
                        self.error(san_alerts)
                    if san_hw_alerts:
                        self.error('\n'.join(map(str, san_hw_alerts)))
                    self.error("Contact Local Ericsson Support "
                               "or EMC Support Administrator.")
                    raise SystemExit(ExitCodes.ERROR)
                self.info("There are no alerts on the SAN.")

    def healthcheck_san(self):
        """
        StoragePool usage check. Checks the StoragePool usage is below a
         certain value.

        :raise SystemExit: If current StoragePool usage is above a
         certain value.
        """
        self.verbose('Getting modeled requirements.')
        required_free, snap_reserve = self._get_total_pool_required()
        _providers = self._get_modeled_providers()
        usage_error = False

        for _provider, _pools in _providers.items():
            _site_id = _provider.get_property(
                    SanHealthChecks.K_STORAGE_SITE_ID)
            self.info('Checking Site {0}'.format(_site_id))
            _api = self._get_api(_provider)
            san_type = _provider.get_property(SanHealthChecks.K_SAN_TYPE) \
                    .lower()
            has_snaps = SanHealthChecks.has_snapshots(_api, _site_id)
            san_watermark = SanHealthChecks.get_watermark(has_snaps)
            if has_snaps:
                self.info('LUN snaps exist, watermark set to {0}%'.format(
                        san_watermark))
            else:
                self.info('No LUN snaps, watermark set to {0}%'.format(
                        san_watermark))
            for _pool in _pools:
                _poolname = _pool.get_property(SanHealthChecks.K_NAME)
                self.info('Checking StoragePool {0}'.format(_poolname))
                if self.check_storagepool(_api, _pool, san_watermark,
                                          required_free[_poolname],
                                          snap_reserve[_poolname],
                                          has_snaps, san_type):
                    usage_error = True
        if usage_error:
            raise SystemExit(ExitCodes.ERROR)
