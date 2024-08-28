from datetime import datetime
from os import remove, makedirs
from os.path import exists, join
import shutil
import tempfile
from ConfigParser import SafeConfigParser, NoOptionError, NoSectionError
from re import match

import unittest2

from h_util.ini import IniReader


inidict = {'deployment': {'name': 'eps'},
           'cluster': {'nodes': '2',
                       'name': 'testcluster',
                       'nodenames': 'host1,host2'},
           'host1': {'hostname': 'sc1',
                     'ipaddress': '10.1.1.5',
                     'os': 'linux'},
           'host2': {'hostname': 'sc2',
                     'ipaddress': '10.1.1.6',
                     'os': 'linux'}}

TMP_DIR = join(tempfile.gettempdir(), 'TESTTEMP')

inifile = join(TMP_DIR, "ini_test_file.ini")


class TestIniReader(unittest2.TestCase):

    def _create_ini(self, inicontents, ini_file):
        tester = SafeConfigParser()
        tester.optionxform = str
        for section, values in inicontents.items():
            tester.add_section(section)
            for k, v in values.items():
                tester.set(section, k, v)
        inif = open(ini_file, 'w')
        tester.write(inif)
        inif.close()

    def setUp(self):

        if not exists(TMP_DIR):
            makedirs(TMP_DIR)

        # Setup ini file
        self._create_ini(inidict, inifile)
        self.reader = IniReader(inifile)

    def tearDown(self):
        if exists(TMP_DIR):
            shutil.rmtree(TMP_DIR)

    def test_get_option(self):
        # get option
        sec, opt = 'host1', 'hostname'
        self.assertEqual(self.reader.get_option(sec, opt), inidict[sec][opt])

        # get default option if section does not exist
        sec, opt, dv = 'NoSection', 'name', 'eps'
        self.assertEqual(self.reader.get_option(sec, opt, default=dv), dv)

        # get default option if option does not exist
        sec, opt, dv = 'cluster', 'noopt', '10.0.0.1'
        self.assertEqual(self.reader.get_option(sec, opt, default=dv), dv)

        # get non-existing option with no default value
        sec, opt = 'cluster', 'noopt'
        self.assertRaises(NoOptionError, self.reader.get_option, sec, opt)

        # get non-existing Section
        sec, opt = 'NoSection', 'name'
        self.assertRaises(NoSectionError, self.reader.get_option, sec, opt)

        # get value as list
        sec, opt = 'cluster', 'nodenames'
        self.assertListEqual(
            self.reader.get_option(sec, opt, seperator=','),
            ['host1', 'host2'])

    def test_get_section(self):
        sec = 'host2'
        self.assertEqual(self.reader.get_section(sec), inidict[sec])

        sec = 'NoSection'
        self.assertRaises(NoSectionError, self.reader.get_section, sec)

    def test_get_block_names(self):
        self.assertListEqual(self.reader.get_block_names(), inidict.keys())

    def test_get_site_value(self):
        # Get opt value from sec
        sec, opt = 'host1', 'hostname'
        self.assertEqual(self.reader.get_site_value(sec, opt),
                         inidict[sec][opt])

        # get default option if option does not exist
        sec, opt, dv = 'cluster', 'noopt', '10.0.0.1'
        self.assertEqual(
            self.reader.get_site_value(sec, opt, default_value=dv), dv)

        # get non-existing option with no default value
        sec, opt = 'cluster', 'noopt'
        self.assertRaises(NoOptionError, self.reader.get_site_value, sec, opt)

        # get value as list
        sec, opt = 'cluster', 'nodenames'
        self.assertListEqual(
            self.reader.get_site_value(sec, opt, seperator=','),
            ['host1', 'host2'])

    def test_get_site_section_keys(self):
        sec = 'host1'
        self.assertListEqual(sorted(self.reader.get_site_section_keys(sec)),
                             sorted(inidict[sec].keys()))

        fltr = '.*name.*'
        sec = 'cluster'
        keys = inidict[sec].keys()
        inilist = [key for key in keys if match(fltr, key)]
        self.assertListEqual(
            self.reader.get_site_section_keys(sec, key_filter=fltr), inilist)

    def test_object_init(self):
        nofile = 'no_such_file.ini'
        self.assertRaises(IOError, IniReader, nofile)

    def test_has_section(self):
        self.assertTrue(self.reader.has_section('host1'))

        self.assertFalse(self.reader.has_section('host5'))

    def test_has_option(self):
        self.assertTrue(self.reader.has_option('host1', 'hostname'))
        self.assertFalse(self.reader.has_option('host1', 'nooption'))
        self.assertFalse(self.reader.has_option('nosection', 'nooption'))

    def test_save_ini(self):
        fname = join(TMP_DIR, 'testdir/test.ini')
        if exists(fname):
            remove(fname)
        value = str(datetime.now())
        self.reader.set_option('deployment', 'name', value)
        self.reader.save_ini(fname)
        self.assertTrue(exists(fname))
        r = IniReader(fname)
        self.assertEqual(value, r.get_option('deployment', 'name'))

    def test_merge(self):
        ini_contents_a = inidict.copy()
        ini_contents_a['NEW_BLOCK'] = {'NEW_KEY': '"Q:V_A'}
        ini_file_a = join(TMP_DIR, 'a.ini')
        self._create_ini(ini_contents_a, ini_file_a)

        ini_contents_b = inidict.copy()
        ini_contents_b['NEW_BLOCK'] = {'NEW_KEY': 'V_B'}
        ini_file_b = join(TMP_DIR, 'b.ini')
        self._create_ini(ini_contents_b, ini_file_b)

        reader_a = IniReader(ini_file_a)
        reader_b = IniReader(ini_file_b)

        reader_b.merge(reader_a)

        self.assertEqual('V_B', reader_b.get_option('NEW_BLOCK', 'NEW_KEY'))

if __name__ == '__main__':
    unittest2.main()
