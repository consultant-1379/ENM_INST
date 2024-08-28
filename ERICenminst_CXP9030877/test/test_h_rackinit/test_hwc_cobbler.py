import shutil
from os import makedirs
from os.path import join, isdir, exists
from tempfile import gettempdir

from mock import patch, call, ANY, MagicMock
from unittest2 import TestCase

from h_rackinit.hwc_cobbler import CobblerCli, Kickstarts
from h_rackinit.hwc_utils import CobblerCliException, SiteDoc


class TestCobblerCli(TestCase):
    def test_properties(self):
        self.assertTrue(
                CobblerCli.cobbler_kickstarts().endswith('/kickstarts'))
        self.assertTrue(
                CobblerCli.cobbler_snippets().endswith('/snippets'))

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_list_systems(self, p_exec_process):
        p_exec_process.return_value = 's1\ns2'
        cli = CobblerCli(MagicMock())
        systems = cli.list_systems()
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'system', 'list'])
        ])
        self.assertEqual(2, len(systems))
        self.assertIn('s1', systems)
        self.assertIn('s2', systems)

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_list_profiles(self, p_exec_process):
        p_exec_process.return_value = 'p1\np2'
        cli = CobblerCli(MagicMock())
        profiles = cli.list_profiles()
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'profile', 'list'])
        ])
        self.assertEqual(2, len(profiles))
        self.assertIn('p1', profiles)
        self.assertIn('p2', profiles)

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_list_distros(self, p_exec_process):
        p_exec_process.return_value = 'd1\nd2'
        cli = CobblerCli(MagicMock())
        distros = cli.list_distros()
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'distro', 'list'])
        ])
        self.assertEqual(2, len(distros))
        self.assertIn('d1', distros)
        self.assertIn('d2', distros)

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_import_distro(self, p_exec_process):
        cli = CobblerCli(MagicMock())
        cli.import_distro('dist-name', 'x86', 'redhat', '1', '/path')
        self.assertEqual(1, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'import', '--name', 'dist-name',
                  ANY, ANY, ANY, ANY])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_edit_distro(self, p_exec_process):
        cli = CobblerCli(MagicMock())
        cli.edit_distro('dist-name', {'p': 'v'})
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'distro', 'edit', '--name',
                  'dist-name', '--p=v'])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_edit_profile(self, p_exec_process):
        cli = CobblerCli(MagicMock())
        cli.edit_profile('profile-name', {'p': 'v'})
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'profile', 'edit', '--name',
                  'profile-name', '--p=v'])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_delete_profile(self, p_exec_process):
        cli = CobblerCli(MagicMock())
        cli.delete_profile('name', include_distro=False)
        self.assertEqual(1, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'profile', 'remove', '--name', 'name'])
        ])

        p_exec_process.reset_mock()
        cli.delete_profile('name')
        self.assertEqual(2, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'distro', 'remove', '--name', 'name']),
            call(['/usr/bin/cobbler', 'profile', 'remove', '--name', 'name'])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_register_system(self, p_exec_process):
        cli = CobblerCli(MagicMock())
        cli.register_system('system', 'profile')
        self.assertEqual(1, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'system', 'add', '--name=system',
                  '--profile=profile'])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_deregister_system(self, p_exec_process):
        p_exec_process.side_effect = [[], None]
        cli = CobblerCli(MagicMock())
        cli.deregister_system('system')
        self.assertEqual(1, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'system', 'list'])])

        p_exec_process.reset_mock()
        p_exec_process.side_effect = ['system', None]
        cli.deregister_system('system')
        self.assertEqual(2, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'system', 'list']),
            call(['/usr/bin/cobbler', 'system', 'remove', '--name=system'])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_edit_system(self, p_exec_process):
        cli = CobblerCli(MagicMock())
        cli.edit_system('system', p='v', a_b='c')
        self.assertEqual(1, p_exec_process.call_count)
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'system', 'edit', '--name=system',
                  '--p=v', '--a-b=c'])
        ])

    @patch('h_rackinit.hwc_cobbler.CobblerCli.list_profiles')
    @patch('h_rackinit.hwc_cobbler.CobblerCli.list_distros')
    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_configure_system(self, p_exec_process, p_list_distros,
                              p_list_profiles):
        cli = CobblerCli(MagicMock())
        p_list_distros.return_value = []
        p_list_profiles.return_value = []
        cfg = SiteDoc(None)
        cfg.sed = {
            'hostname': 'host-name',
            'eth3_macaddress': 'eth3mac',
            'eth9_macaddress': 'eth9mac'
        }

        cli.configure_system('system', cfg, 'ks_file', 'eth3', '1.1.1.1')
        # Just check for certain main cobbler config calls.
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'import',
                  '--name', 'cobbler_temp-x86_64',
                  ANY, ANY, ANY, ANY]),
            call(['/usr/bin/cobbler', 'distro', 'edit',
                  '--name', 'cobbler_temp-x86_64', ANY]),
            call(['/usr/bin/cobbler', 'profile', 'edit',
                  '--name', 'cobbler_temp-x86_64', ANY, ANY]),
            call(['/usr/bin/cobbler', 'system', 'add', '--name=system',
                  '--profile=cobbler_temp-x86_64']),
            call(['/usr/bin/cobbler', 'system', 'edit', '--name=system',
                  '--interface=eth3', '--mac=eth3mac']),
            call(['/usr/bin/cobbler', 'system', 'edit', '--name=system',
                  '--ip-address=1.1.1.1']),
            call(['/usr/bin/cobbler', 'system', 'edit', '--name=system',
                  '--hostname=host-name']),
            call(['/usr/bin/cobbler', 'system', 'edit', '--name=system',
                  '--kickstart=ks_file'])
        ], any_order=True)

        p_exec_process.reset_mock()
        self.assertRaises(CobblerCliException, cli.configure_system,
                          's', cfg, 'ks', 'eth9', '1.1.1.2', profile='abc')

        p_exec_process.reset_mock()
        p_list_distros.return_value = ['cobbler_temp-x86_64']
        p_list_profiles.return_value = ['cobbler_temp-x86_64']
        cli.configure_system('s', cfg, 'ks', 'eth9', '1.1.1.2')
        p_exec_process.assert_has_calls([
            call(['/usr/bin/cobbler', 'system', 'add', '--name=s',
                  '--profile=cobbler_temp-x86_64'])
        ])
        self.assertRaises(AssertionError, p_exec_process.assert_has_calls,
                          call(['/usr/bin/cobbler', 'import',
                                '--name', 'cobbler_temp-x86_64',
                                ANY, ANY, ANY, ANY]),
                          )
        self.assertRaises(AssertionError, p_exec_process.assert_has_calls,
                          call(['/usr/bin/cobbler', 'profile', 'edit',
                                '--name', 'cobbler_temp-x86_64', ANY, ANY]))

    @patch('h_rackinit.hwc_cobbler.glob1')
    @patch('h_rackinit.hwc_cobbler.remove')
    @patch('h_rackinit.hwc_cobbler.exists')
    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_deconfigure_system(self, p_exec_process, p_exists, p_remove,
                                p_glob1):
        cli = CobblerCli(MagicMock())

        p_exists.return_value = True
        p_exec_process.side_effect = [
            's', None
        ]
        p_glob1.return_value = ['snip1']

        cli.deconfigure_system('s')
        p_remove.assert_has_calls([
            call(join(CobblerCli.cobbler_kickstarts(), 's.ks')),
            call(join(CobblerCli.cobbler_snippets(), 'snip1'))
        ], any_order=True)
        p_exec_process.assert_has_calls(
                call(['/usr/bin/cobbler', 'system', 'remove', '--name=s'])
        )

    @patch('h_rackinit.hwc_cobbler.CobblerCli.exec_process')
    def test_sync(self, p_exec_process):
        p_exec_process.side_effect = [
            'nothing...'
        ]
        cli = CobblerCli(MagicMock())
        cli.sync()

        p_exec_process.assert_called_once_with(['/usr/bin/cobbler', 'sync'])


class TestKickstarts(TestCase):
    def setUp(self):
        super(TestKickstarts, self).setUp()
        self.tmpdir = join(gettempdir(), 'TestKickstarts')
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        makedirs(self.tmpdir)

    def tearDown(self):
        super(TestKickstarts, self).tearDown()
        if isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def test_is_named_disk(self):
        self.assertFalse(Kickstarts.is_named_disk('abc'))
        self.assertFalse(Kickstarts.is_named_disk('ABC'))
        self.assertTrue(Kickstarts.is_named_disk('kgb'))
        self.assertTrue(Kickstarts.is_named_disk('KGB'))

    def test_convert_to_mb(self):
        self.assertEqual(1, Kickstarts._convert_to_mb('1M'))
        self.assertEqual(1024, Kickstarts._convert_to_mb('1G'))
        self.assertEqual(1048576, Kickstarts._convert_to_mb('1T'))

    @patch('h_rackinit.hwc_cobbler.CobblerCli.cobbler_snippets')
    def test_generate_bootloader(self, p_cobbler_snippets):
        p_cobbler_snippets.return_value = self.tmpdir
        ks = Kickstarts(MagicMock())

        ks.generate_bootloader('ieatrcxb1234', 'diskid', 'diskname')
        _file = join(CobblerCli(MagicMock()).cobbler_snippets(),
                     'ieatrcxb1234.ks.bootloader.snippet')
        self.assertTrue(exists(_file))
        with open(_file) as _reader:
            data = ''.join(_reader.readlines())
        self.assertFalse('@@TARGET_NAME@@' in data)
        self.assertFalse('@@TARGET_UUID@@' in data)

        ks.generate_bootloader('ieatrcxb1234', 'kgb', 'sda')
        _file = join(CobblerCli(MagicMock()).cobbler_snippets(),
                     'ieatrcxb1234.ks.bootloader.snippet')
        self.assertTrue(exists(_file))
        with open(_file) as _reader:
            data = ''.join(_reader.readlines())
        self.assertFalse('@@TARGET_NAME@@' in data)
        self.assertFalse('@@TARGET_UUID@@' in data)

    @patch('h_rackinit.hwc_cobbler.CobblerCli.cobbler_snippets')
    def test_generate_partition(self, p_cobbler_snippets):
        p_cobbler_snippets.return_value = self.tmpdir
        ks = Kickstarts(MagicMock())

        ks.generate_partition('ieatrcxb1234', 'diskid', 'diskname')
        _file = join(CobblerCli(MagicMock()).cobbler_snippets(),
                     'ieatrcxb1234.ks.partition.snippet')
        self.assertTrue(exists(_file))
        with open(_file) as _reader:
            data = ''.join(_reader.readlines())
        self.assertFalse('@@TARGET_NAME@@' in data)
        self.assertFalse('@@TARGET_UUID@@' in data)

        ks.generate_partition('ieatrcxb1234', 'kgb', 'sda')
        _file = join(CobblerCli(MagicMock()).cobbler_snippets(),
                     'ieatrcxb1234.ks.partition.snippet')
        self.assertTrue(exists(_file))
        with open(_file) as _reader:
            data = ''.join(_reader.readlines())
        self.assertFalse('@@TARGET_NAME@@' in data)
        self.assertFalse('@@TARGET_UUID@@' in data)

    @patch('h_rackinit.hwc_cobbler.CobblerCli.cobbler_snippets')
    def test_generate_udevrules(self, p_cobbler_snippets):
        p_cobbler_snippets.return_value = self.tmpdir
        ks = Kickstarts(MagicMock())

        cfg = SiteDoc(None)
        cfg.sed = {'eth5_macaddress': 'aa:bb:'}
        ks.generate_udevrules('ie1234', cfg, 'eth5')
        _file = join(CobblerCli(MagicMock()).cobbler_snippets(),
                     'ie1234.ks.udev_network.snippet')
        self.assertTrue(exists(_file))
        with open(_file) as _reader:
            data = ''.join(_reader.readlines())
        self.assertFalse('@@PXE_NIC_MAC@@' in data)
        self.assertFalse('@@PXE_NIC_NAME@@' in data)

    @patch('h_rackinit.hwc_cobbler.exists')
    @patch('h_rackinit.hwc_cobbler.CobblerCli.cobbler_kickstarts')
    @patch('h_rackinit.hwc_cobbler.Kickstarts._readfile')
    @patch('h_rackinit.hwc_cobbler.Kickstarts.generate_udevrules')
    @patch('h_rackinit.hwc_cobbler.Kickstarts.generate_partition')
    @patch('h_rackinit.hwc_cobbler.Kickstarts.generate_bootloader')
    def test_generate(self, p_generate_bootloader,
                      p_generate_partition, p_generate_udevrules,
                      p_readfile, p_cobbler_kickstarts, p_exists):
        p_exists.return_value = True
        p_cobbler_kickstarts.return_value = self.tmpdir
        ks = Kickstarts(MagicMock())
        cfg = SiteDoc(None)
        cfg.sed = {'hostname': 'ieatr444',
                   'iloPassword': 'aaaa'}
        key_file = 'key'
        p_readfile.return_value = ['aaaaaaaaaa']

        actual_file = ks.generate(cfg, key_file, 'eth0', 'aaa')
        expected_file = join(CobblerCli(MagicMock()).cobbler_kickstarts(),
                             'ieatr444.ks')
        self.assertEqual(expected_file, actual_file)
        self.assertTrue(exists(expected_file))
        with open(expected_file) as _reader:
            data = ''.join(_reader.readlines())
        self.assertFalse('@@ROOT_PASSWD@@' in data)
        self.assertFalse('@@ROOT_PUB_KEY@@' in data)

        p_generate_bootloader.assert_called_once_with('ieatr444', 'kgb', 'aaa')
        p_generate_partition.assert_called_once_with('ieatr444', 'kgb', 'aaa')
        p_generate_udevrules.assert_called_once_with('ieatr444', cfg, 'eth0')
