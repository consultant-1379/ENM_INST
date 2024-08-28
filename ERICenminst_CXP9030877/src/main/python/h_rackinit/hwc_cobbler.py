"""
Utility stuff for cobbler
"""
##############################################################################
# COPYRIGHT Ericsson AB 2018
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from base64 import b64encode
from crypt import crypt
from glob import glob1
from os import remove, urandom
from os.path import exists, join, dirname

from hwc_utils import BaseObject, Config, CobblerCliException, SiteDoc


class CobblerCli(BaseObject):  # pylint: disable=R0904
    """
    Cobbler CLI interface
    """

    def __init__(self, logger):
        super(CobblerCli, self).__init__(logger)

    @staticmethod
    def cobbler():
        """
        Get path of cobbler cli

        :returns: Path of cobbler cli
        @:rtype: str
        """
        return '/usr/bin/cobbler'

    @staticmethod
    def cobbler_dir():
        """
        Cobbler config base dir

        :returns: Cobbler config base dir
        @:rtype: str
        """
        return '/var/lib/cobbler'

    @staticmethod
    def cobbler_kickstarts():
        """
        Cobbler config kickstarts location

        :returns: Path of where to store cobbler kickstarts
        @:rtype: str
        """
        return join(CobblerCli.cobbler_dir(), 'kickstarts')

    @staticmethod
    def cobbler_snippets():
        """
        Cobbler config kickstart snippets location

        :returns: Path of where to store cobbler kickstart snippets
        @:rtype: str
        """
        return join(CobblerCli.cobbler_dir(), 'snippets')

    def _list(self, _type):
        """
        Execute a cobbler list commands

        :param _type: The type to list e.g. system or distro
        :type _type: str

        :returns: Output of the cobbler <type> list command
        :rtype: str
        """
        _types = []
        _list = self.exec_process([self.cobbler(), _type, 'list'])
        if _list:
            for _line in _list.split('\n'):
                _line = _line.strip()
                if _line:
                    _types.append(_line)
        return _types

    def list_systems(self):
        """
        Get a list of registered systems

        :returns: List of registered systems
        :rtype: str[]
        """
        return self._list('system')

    def list_profiles(self):
        """
        Get a list of registered profiles

        :returns: List of registered profiles
        :rtype: str[]
        """
        return self._list('profile')

    def list_distros(self):
        """
        Get a list of registered distros

        :returns: List of registered distros
        :rtype: str[]
        """
        return self._list('distro')

    def import_distro(self,  # pylint: disable=R0913
                      name, arch, breed, version, path):
        """
        Import a distro

        :param name: Distro name
        :type name: str
        :param arch: Disto arch
        :type arch: str
        :param breed: Distro breed
        :type breed: str
        :param version: Distro version
        :type version: str
        :param path: Path to import
        :type path: str
        """
        _cmd = [self.cobbler(), 'import',
                '--name', name,
                '--arch={0}'.format(arch),
                '--breed={0}'.format(breed),
                '--os-version={0}'.format(version),
                '--path={0}'.format(path)]
        self.exec_process(_cmd)

    def edit_distro(self, name, params):
        """
        Edit a registered distro

        :param name: The distro to edit
        :type name: str
        :param params: Parameters to set/update
        :type params: dict
        """
        _cmd = [self.cobbler(), 'distro', 'edit', '--name', name]
        for _key, _value in params.items():
            _cmd.append('--{0}={1}'.format(_key, _value))
        self.exec_process(_cmd)

    def edit_profile(self, profile, params):
        """
        Edit a registered profile

        :param profile: The profile to edit
        :type profile: str
        :param params: Parameters to set/update
        :type params: dict
        """
        _cmd = [self.cobbler(), 'profile', 'edit', '--name', profile]
        for _key, _value in params.items():
            _cmd.append('--{0}={1}'.format(_key, _value))
        self.exec_process(_cmd)

    def delete_profile(self, name, include_distro=True):
        """
        Edit a profile

        :param name: The profile to delete
        :type name: str
        :param include_distro: Delete the associated distro too
        :type include_distro: bool
        """
        if include_distro:
            self.exec_process([self.cobbler(), 'distro', 'remove',
                               '--name', name])
        self.exec_process([self.cobbler(), 'profile', 'remove',
                           '--name', name])

    def register_system(self, name, system_profile):
        """
        Register a system in cobbler

        :param name: The system name
        :type name: str
        :param system_profile: The profile to associate with the system
        :type system_profile: str
        """
        self.exec_process([self.cobbler(), 'system', 'add',
                           '--name={0}'.format(name),
                           '--profile={0}'.format(system_profile)])

    def deregister_system(self, name):
        """
        Deregister a system from cobbler

        :param name: The system name
        :type name: str
        """
        if name in self.list_systems():
            self.exec_process([self.cobbler(), 'system', 'remove',
                               '--name={0}'.format(name)])
            self._log.info('Removed system {0}'.format(name))

    def edit_system(self, name, **kwargs):
        """
        Edit a registered system

        :param name: The profile to edit
        :type name: str
        :param kwargs: Parameters to set/update
        :type kwargs: dict
        """
        _cmd = [self.cobbler(), 'system', 'edit',
                '--name={0}'.format(name)]
        for _key, _value in kwargs.items():
            if '_' in _key:
                _key = _key.replace('_', '-')
            _cmd.append('--{0}={1}'.format(_key, _value))
        self.exec_process(_cmd)
        self._log.debug('Modified system {0}: {1}'.format(name, kwargs))

    def configure_system(self,  # pylint: disable=R0913
                         system_name, config, ks_file, pxe_device,
                         pxe_ipaddress, profile=None):
        """
        Configure a system for PXE boot

        :param system_name: The system name
        :type system_name: str
        :param config: The SED containing the systems site values
        :type config: SiteDoc
        :param ks_file: The kist start to use for the PXE boot
        :type ks_file: str
        :param pxe_device: The device the system will PXE off of
        :type pxe_device: str
        :param pxe_ipaddress: The address to assign to the pxe_device
        :type pxe_ipaddress: str
        :param profile: Cobbler profile to use (or create)
        :type profile: str
        """
        cfg = Config.get_config()
        cfg_block = profile if profile else 'TEMP'
        if not cfg.has_section(cfg_block):
            raise CobblerCliException(
                    'No configuration for "{0}" found!'.format(profile))

        pxe_profile = cfg.get(cfg_block, 'name')
        self._log.info('Cobbler profile set to "{0}"'.format(pxe_profile))
        existing_distros = self.list_distros()
        dist_name = cfg.get(cfg_block, 'name')
        if dist_name not in existing_distros:
            path = cfg.get(cfg_block, 'path')
            self._log.info('Import distro "{0}" from {1}'.format(dist_name,
                                                                 path))
            self.import_distro(dist_name,
                               cfg.get(cfg_block, 'arch'),
                               cfg.get(cfg_block, 'breed'),
                               cfg.get(cfg_block, 'version'),
                               path)
            self.edit_distro(dist_name, {
                'ksmeta': '"tree=http://@@http_server@@/{0}"'.format(
                        cfg.get(cfg_block, 'url')
                )
            })
        else:
            self._log.info('Reusing cobbler distro "{0}"'.format(dist_name))

        existing_profiles = self.list_profiles()
        if pxe_profile not in existing_profiles:
            self.edit_profile(pxe_profile, {
                'kickstart': '/var/lib/cobbler/kickstarts/default.ks',
                'kopts-post': cfg.get(cfg_block, 'kopts-post')
            })
        else:
            self._log.info(
                    'Reusing cobbler profile "{0}"'.format(pxe_profile))

        self.register_system(system_name, pxe_profile)
        pxe_mac = config.get_sed_value('{0}_macaddress'.format(pxe_device))
        self._log.info('Setting up {0} to PXE boot from {1}/{2}/{3}'.format(
                system_name, pxe_device, pxe_mac, pxe_ipaddress))
        self.edit_system(system_name, interface=pxe_device, mac=pxe_mac)

        self.edit_system(system_name, ip_address=pxe_ipaddress)
        self.edit_system(system_name, hostname=config['hostname'])
        self.edit_system(system_name, kickstart=ks_file)
        self._log.info('Added {0} to cobbler'.format(system_name))

    def deconfigure_system(self, name):
        """
        Remove a configured system.

        :param name: The system to remove
        :type name: str
        """
        self.deregister_system(name)
        _ks = join(self.cobbler_kickstarts(), '{0}.ks'.format(name))
        if exists(_ks):
            remove(_ks)
            self._log.debug('Deleted {0}'.format(_ks))
        for _snippet in glob1(self.cobbler_snippets(),
                              '{0}.ks.*.snippet'.format(name)):
            _fp = join(self.cobbler_snippets(), _snippet)
            remove(_fp)
            self._log.debug('Deleted {0}'.format(_fp))

    def sync(self):
        """
        Sync cobbler

        """
        _stdout = self.exec_process([self.cobbler(), 'sync'])
        self._log.debug(_stdout)


class Kickstarts(BaseObject):
    """
    Class to generate kickstart files
    """

    def __init__(self, logger):
        super(Kickstarts, self).__init__(logger)
        self.kickstarts = join(dirname(__file__), 'kickstarts')
        self.t_bootloader_uuid = 'ks.bootloader.uuid.snippet'
        self.t_bootloader_named = 'ks.bootloader.named.snippet'
        self.t_partition_uuid = 'ks.partition.uuid.snippet'
        self.t_partition_named = 'ks.partition.named.snippet'
        self.t_udevrules = 'ks.udev_network.snippet'

    @staticmethod
    def is_named_disk(disk_id):
        """
        Is the disk_id a named disk or not.

        :param disk_id: The disk ID
        :returns: True of the disk_id is "kgb", False otherwise
        :rtype bool
        """
        return disk_id.lower() == 'kgb'

    @staticmethod
    def _convert_to_mb(size):
        """
        Convert a size to MB

        :param size: The size String to convert e.g. 5M or 10G or 2T
        :type size: str

        :returns:
        :rtype: int
        """
        for i in zip(range(3), ['M', 'G', 'T']):
            if size[-1] == i[1]:
                return int(size[:-1]) * 1024 ** i[0]

    def generate_bootloader(self, system_name, boot_disk_id, boot_disk_name):
        """
        Generate a bootloader snippet to <cobbler>/snippets

        :param system_name: The system name
        :type system_name: str
        :param boot_disk_id:  Boot disk ID
        :type boot_disk_id: str
        :param boot_disk_name: Boot disk name
        :type boot_disk_name: str
        """
        if self.is_named_disk(boot_disk_id):
            self._log.info('Generating booloader snippet based on disk name.')
            _snippet = self._readfile(join(self.kickstarts,
                                           self.t_bootloader_named))

            _snippet = ''.join(_snippet).replace('@@TARGET_NAME@@',
                                                 boot_disk_name)
        else:
            self._log.info('Generating booloader snippet based on disk UUID.')
            _snippet = self._readfile(join(self.kickstarts,
                                           self.t_bootloader_uuid))
            _snippet = ''.join(_snippet).replace('@@TARGET_UUID@@',
                                                 boot_disk_id)

        _output = join(CobblerCli(self._log).cobbler_snippets(),
                       '{0}.ks.bootloader.snippet'.format(system_name))
        self._log.debug('>> Bootloader <<')
        self._log.debug(_snippet)
        self._log.debug('>> Bootloader <<')
        self._writefile(_output, _snippet)
        self._log.debug('Generated bootloader snippet {0}'.format(_output))

    def generate_partition(self, system_name, boot_disk_id, boot_disk_name):
        """
        Generate a partitioning snippet to <cobbler>/snippets

        :param system_name: The system name
        :type system_name: str
        :param boot_disk_id:  Boot disk ID
        :type boot_disk_id: str
        :param boot_disk_name: Boot disk name
        :type boot_disk_name: str
        """
        cfg = Config.get_config()
        bootfs_size = cfg.get('PARTITIONS', 'bootfs_size')
        rootvg_size = cfg.get('PARTITIONS', 'rootvg_size')
        rootvg_pesize = cfg.get('PARTITIONS', 'rootvg_pesize')
        rootfs_size = cfg.get('PARTITIONS', 'rootfs_size')

        vg_name = 'vg_hwc'
        vol_snippets = [
            '\n\necho "part /boot --fstype=ext4 '
            '--size={0} --ondisk=${{disk_list["boot_disk"]}}" >>'
            ' /tmp/partitioninfo'.format(bootfs_size),

            'echo "part pv.01{0} --size={1} '
            '--ondisk=${{disk_list["boot_disk"]}}" >> '
            '/tmp/partitioninfo'.format(vg_name, rootvg_size),

            'echo "volgroup {1} --pesize={0} pv.01{1}" '
            '>> /tmp/partitioninfo'.format(rootvg_pesize, vg_name),

            'echo "logvol / '
            '--fstype=ext4 '
            '--name={vg_name}_root '
            '--vgname={vg_name} --size={size}" >> '
            '/tmp/partitioninfo'.format(vg_name=vg_name, size=rootfs_size)]

        if self.is_named_disk(boot_disk_id):
            _snippet = self._readfile(join(self.kickstarts,
                                           self.t_partition_named))
            _snippet = ''.join(_snippet).replace('@@TARGET_NAME@@',
                                                 boot_disk_name)
        else:
            _snippet = self._readfile(join(self.kickstarts,
                                           self.t_partition_uuid))
            _snippet = ''.join(_snippet).replace('@@TARGET_UUID@@',
                                                 boot_disk_id)

        _snippet += '\n'.join(vol_snippets)
        _output = join(CobblerCli(self._log).cobbler_snippets(),
                       '{0}.ks.partition.snippet'.format(system_name))
        self._log.debug('>> Partitions <<')
        self._log.debug(_snippet)
        self._log.debug('>> Partitions <<')
        self._writefile(_output, _snippet)
        self._log.debug('Generated partition snippet {0}'.format(_output))

    def generate_udevrules(self, system_name, system_config, pxe_device):
        """
        Generate a udev rules snippet to <cobbler>/snippets

        :param system_name: The system name
        :type system_name: str
        :param system_config: Node site values
        :type system_config: SiteDoc
        :param pxe_device: PXE device
        :type pxe_device: str
        """
        _snippet = self._readfile(join(self.kickstarts, self.t_udevrules))

        pxe_mac = system_config.get_sed_value(
                '{0}_macaddress'.format(pxe_device))

        _snippet = ''.join(_snippet).replace(
                '@@PXE_NIC_MAC@@', pxe_mac)
        _snippet = _snippet.replace(
                '@@PXE_NIC_NAME@@', pxe_device)
        _output = join(CobblerCli(self._log).cobbler_snippets(),
                       '{0}.{1}'.format(system_name, self.t_udevrules))
        self._log.debug('>> udev <<')
        self._log.debug(_snippet)
        self._log.debug('>> udev <<')
        self._writefile(_output, ''.join(_snippet))
        self._log.debug('Generated udev rules snippet {0}'.format(_output))

    def generate(self, config, root_pub_key, pxe_device, boot_disk_name):
        """
        Generate a kickstart and snippets to PXE a node.

        :param config: Node site values
        :type config: SiteDoc
        :param root_pub_key: The system name
        :type root_pub_key: str
        :param pxe_device: PXE device
        :type pxe_device: str
        :param boot_disk_name: Boot disk name
        :type boot_disk_name: str

        :returns: Path to the kickstart to PXE the node with.
        :rtype: str
        """
        system_name = config.get_sed_value('hostname')
        system_kickstart = join(CobblerCli(self._log).cobbler_kickstarts(),
                                '{0}.ks'.format(system_name))
        _ks = ''.join(self._readfile(join(self.kickstarts, 'kickstart.ks')))

        passwd = crypt(config.get_sed_value(SiteDoc.SK_ILO_PASSWORD),
                       "$6$" + b64encode(urandom(6)))
        _ks = _ks.replace('@@ROOT_PASSWD@@', passwd.strip())
        admin_pub_key = self._readfile(root_pub_key)[0]
        _ks = _ks.replace('@@ROOT_PUB_KEY@@', admin_pub_key)

        boot_disk_id = config.get('bootdisk_uuid', 'kgb').lower()

        self.generate_bootloader(system_name, boot_disk_id, boot_disk_name)
        self.generate_partition(system_name, boot_disk_id, boot_disk_name)
        self.generate_udevrules(system_name, config, pxe_device)
        self._log.debug('>> Kickstart <<')
        self._log.debug(_ks)
        self._log.debug('>> Kickstart <<')
        self._writefile(system_kickstart, _ks)
        self._log.info('Generated kickstart {0}'.format(system_kickstart))
        return system_kickstart
