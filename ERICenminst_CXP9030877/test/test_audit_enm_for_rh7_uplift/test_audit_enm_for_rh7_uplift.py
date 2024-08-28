"""
Unit test for ENM auditor for RHEL 7.x uplift
"""

import os
import sys
import string
from tempfile import gettempdir, NamedTemporaryFile
from mock import patch, Mock, MagicMock, call
from unittest2 import TestCase
from audit_enm_for_rh7_uplift import EnmAuditForUplift


class TestEnmAuditForUplift(TestCase):

    @patch('audit_enm_for_rh7_uplift.os.system')
    @patch('audit_enm_for_rh7_uplift.os.path.exists')
    def setUp(self, mock_exists, mock_system):
        self.exported_model = os.path.join(os.sep, 'tmp', 'exported_model.xml')

        mock_exists.return_value = False
        mock_system.return_value = True

        self.auditor = EnmAuditForUplift()
        ht = self.auditor.print_help_text()

    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._run_command')
    def test_export_model(self, mock_run):
        filename = 'foobar.xml'
        expected = 'litp export -p / -f {0}'.format(filename)
        self.auditor._export_model(filename)
        mock_run.assert_has_calls([call(expected)])

        # ----

        mock_run.side_effect = SystemExit
        self.assertRaises(SystemExit, self.auditor._export_model, filename)

    def test_gen_itype_name(self):
        for itemtype in ('firewall-rule', 'package', 'alias'):
            expected = '{http://www.ericsson.com/litp}' + itemtype
            self.assertEqual(expected,
                             self.auditor._gen_itype_name(itemtype))

    def test_iter_by_itype(self):
        valid_itypes = ['user', 'group', 'eth', 'bond']
        invalid_itypes = ['vm-package', 'vm-firewall-rule', 'file-system']
        ns = '{http://www.ericsson.com/litp}'

        expected1 = set(['/ms/item1', '/ms/item1/item2'])
        for (itypes, valid, expected) in [(valid_itypes, True, expected1),
                                          (invalid_itypes, False, set())]:
            for itype in itypes:
                tag = (ns + itype) if valid else 'bogus'
                grand_kid1 = Mock(tag=tag,
                                  get = lambda x: 'item2',
                                  getchildren = lambda: [])
                kid1 = Mock(tag=tag,
                            get = lambda x: 'item1',
                            getchildren = lambda: [grand_kid1])
                root_element = Mock(tag = (ns + 'ms'),
                                    get = lambda x: 'ms',
                                    getchildren = lambda: [kid1])

                items = set()
                self.auditor._iter_by_itype(root_element, itype, '',
                                            items, None)
                self.assertEqual(expected, items)

        # ----
        all_types = valid_itypes + ['blade', 'bmc', 'cluster', 'disk']

        for itype in all_types:
            tag = ns + itype
            element = Mock(tag= tag,
                           get = lambda x: 'item1',
                           getchildren = lambda: [])
            expected = set([itype +'::/item1'])
            items = set()
            self.auditor._iter_by_itype(element, None, '', items, None)
            self.assertEqual(expected, items)

    def test_process_xml_file(self):
        xml_hdr = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<litp:root xmlns:litp="http://www.ericsson.com/litp" '
                   'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                   'xsi:schemaLocation="http://www.ericsson.com/litp '
                   'litp--schema/litp.xsd" id="root">'
                   '<litp:ms id="ms">')

        xml_ftr = '</litp:ms></litp:root>'

        test_data = {'alias': ['kvstore', 'esm-alias'],
                     'package': ['enm_configuration', 'postgres_package'],
                     'user': ['mdt_user', 'elasticsearch_user'],
                     'group': ['jboss'],
                     'bond': ['bond0', 'bond1']}

        extra_xml = ''
        for (itype, ids) in test_data.iteritems():
            for item_id in ids:
                extra_xml += '<litp:{0} id="{1}"></litp:{0}>'.format(itype,
                                                                     item_id)

        xml = xml_hdr + extra_xml + xml_ftr

        tmp_file1 = NamedTemporaryFile().name
        with open(tmp_file1, 'w') as fd1:
            fd1.write(xml)

        data1 = self.auditor._process_xml_file(tmp_file1)
        os.remove(tmp_file1)

        expected = {itype:set(['/ms/{0}'.format(x) for x in ids])
                    for (itype, ids) in test_data.items()}

        self.assertEqual(expected, data1)

        # ----
        open_xml = ''
        close_xml = ''
        for itype in sorted(test_data.keys()):
            for item_id in sorted(test_data[itype]):
                open_xml += '<litp:{0} id="{1}">'.format(itype, item_id)
                close_xml = '</litp:{0}>'.format(itype) + close_xml

        xml = xml_hdr + open_xml + close_xml + xml_ftr

        tmp_file2 = NamedTemporaryFile().name
        with open(tmp_file2, 'w') as fd2:
            fd2.write(xml)

        data2 = self.auditor._process_xml_file(tmp_file2)
        os.remove(tmp_file2)

        expected = {}
        vpath = '/ms'
        for itype in sorted(test_data.keys()):
            items = []
            for item_id in sorted(test_data[itype]):
                vpath += '/' + item_id
                items.append(vpath)
            expected[itype] = set(items)

        self.assertEqual(expected, data2)

    @patch('audit_enm_for_rh7_uplift.os.path.exists')
    @patch('audit_enm_for_rh7_uplift.os.remove')
    def test_do_cleanup(self, mock_remove, mock_exists):
        self.auditor.cleanup_required = True
        mock_exists.return_value = False
        self.auditor.do_cleanup()
        mock_remove.assert_not_called()

        # ----
        mock_exists.return_value = True
        mock_remove.return_value = True
        self.auditor.do_cleanup()
        mock_remove.assert_called_once_with(self.exported_model)

        # ----
        mock_remove.side_effect = SystemExit
        self.assertRaises(SystemExit, self.auditor.do_cleanup)

        # ----
        mock_remove.side_effect = OSError
        self.auditor.do_cleanup()

    def test_custom_items(self):

        itemtypes = ['alias', 'package', 'user', 'group', 'bond']

        model1_data = {itemtypes[x]:set(['/{0}'.format(v)])
                       for x in range(0, 4)
                       for v in string.ascii_lowercase[x]}
        model2_data = {itemtypes[x]:set(['/{0}'.format(v)])
                       for x in range(0, 5)
                       for v in string.ascii_lowercase[x]}
        def _mock_process_xml(filename):
            if filename == self.exported_model:
                return model2_data
            else:
                return model1_data

        self.auditor._process_xml_file = _mock_process_xml

        custom_items = self.auditor.get_custom_items()
        expected = {'bond': set(['/e'])}
        self.assertEqual(expected, custom_items)

    @patch('__builtin__.open')
    def test_render_custom_items(self, mock_open):
        custom_items = {'foo': set(['/a/b/c/bar', '/a/b/d/baz'])}
        self.auditor.gen_reportfile = False
        self.auditor.render_custom_items(custom_items)
        mock_open.assert_not_called()

        # ----
        self.auditor.gen_reportfile = True
        self.auditor.reportfile = ''

        self.auditor.render_custom_items(custom_items)
        mock_open.assert_not_called()

        # ----
        mock_open.reset_mock()
        self.auditor.render_custom_items(custom_items)
        mock_open.assert_called_once_with('rh7_uplift_audit.log', 'w')

        expected = 'Custom items of ItemType "foo": /a/b/c/bar /a/b/d/baz\n'
        fh = mock_open.return_value.__enter__.return_value
        fh.write.assert_called_once_with(expected)

        # ----
        test_data = {'High': {'user': ['/a']},
                     'Medium': {'route6': ['/b']},
                     'Low': {'vm-disk': ['/c']},
                     'Unknown': {'something': ['/d']}}

        expectedh = 'Custom items of ItemType "user": /a\n'
        expectedm = 'Custom items of ItemType "route6": /b\n'
        expectedl = 'Custom items of ItemType "vm-disk": /c\n'
        expectedk = 'Custom items of ItemType "something": /d\n'

        ecalls = [call('rh7_uplift_audit.log.high', expectedh),
                  call('rh7_uplift_audit.log.medium', expectedm),
                  call('rh7_uplift_audit.log.low', expectedl),
                  call('rh7_uplift_audit.log.unknown', expectedk)]

        self.auditor._write_to_log_file = Mock(return_value=True)

        self.auditor.render_custom_items(test_data, categorized=True)

        self.auditor._write_to_log_file.assert_has_calls(ecalls)

    def test_encode_decode_item(self):
        ns = '{http://www.ericsson.com/litp}'
        token1 = 'foo'
        token2 = 'bar'
        self.assertEquals((token1, token2),
          self.auditor._decode_item(self.auditor._encode_item(ns + token1,
                                                              token2)))
    @patch('audit_enm_for_rh7_uplift.os.path.exists')
    def test_get_xml_root(self, mock_exists):
        mock_exists.return_value = False

        self.assertRaises(SystemExit, self.auditor._get_xml_root, 'bogus')

        # ----

        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<litp:root xmlns:litp="http://www.ericsson.com/litp" '
               'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
               'xsi:schemaLocation="http://www.ericsson.com/litp '
               'litp--schema/litp.xsd" id="root">'
               '<litp:ms id="ms"/>'
               '</litp:root>')

        tmp_file1 = NamedTemporaryFile().name
        with open(tmp_file1, 'w') as fd1:
            fd1.write(xml)

        mock_exists.return_value = True
        self.auditor._get_xml_root(tmp_file1)

        os.remove(tmp_file1)

    def test_get_all_custom_items(self):
        set1 = set(['/a', '/b'])
        set2 = set(['/a', '/b', '/c'])
        root1 = Mock(tag='root1')
        root2 = Mock(tag='root2')
        self.auditor._get_xml_root = Mock(side_effect=[root1, root2])
        self.auditor._get_all_items = Mock(side_effect=[set2, set1])
        expected = set(['/c'])
        citems = self.auditor._get_all_custom_items()
        self.assertEquals(expected, citems)

        # ---
        self.auditor._get_xml_root = Mock(side_effect=[root1, root2])
        self.auditor._get_all_items = Mock(side_effect=[set1, set2])
        expected = set([])
        citems = self.auditor._get_all_custom_items()
        self.assertEquals(expected, citems)

    def test_get_itype_risk_categories(self):
        risk_data = self.auditor._get_itype_risk_categories()
        self.assertEquals(['High', 'Medium', 'Low'], risk_data.keys())

        # ---
        for hval in ['blade', 'bmc', 'package', 'system', 'user']:
            self.assertTrue(hval in risk_data['High'])
        for hval in ['bogus', 'route', 'bridge', 'alias']:
            self.assertFalse(hval in risk_data['High'])

        # ---
        for hval in ['network', 'route6', 'storage-profile']:
            self.assertTrue(hval in risk_data['Medium'])
        for hval in ['bogus', 'sysparam', 'volume-group', 'alias']:
            self.assertFalse(hval in risk_data['Medium'])

        #---
        for hval in ['alias', 'bridge', 'vip', 'vlan']:
            self.assertTrue(hval in risk_data['Low'])
        for hval in ['bogus', 'user', 'sysparam', 'route6']:
            self.assertFalse(hval in risk_data['Low'])

    def test_categorize_custom_items(self):
        test_itypes = [['group', 'package', 'sysparam'],
                       ['network', 'sfs-cache', 'route6'],
                       ['alias', 'bond', 'vm-alias']]

        all_citems = set(['{0}::/{1}'.format(itype, string.ascii_lowercase[x])
                          for (x, itype) in enumerate([itype
                                                    for category in test_itypes
                                                    for itype in category])])
        self.auditor._get_all_custom_items = Mock(return_value=all_citems)

        expected = \
            dict(zip(['High', 'Medium', 'Low', 'Unknown'],
                     [dict(zip(test_itypes[0],
                               [set(['/{0}'.format(string.ascii_lowercase[x])])
                                       for x in range(3)])),
                      dict(zip(test_itypes[1],
                               [set(['/{0}'.format(string.ascii_lowercase[x])])
                                       for x in range(3,6)])),
                      dict(zip(test_itypes[2],
                               [set(['/{0}'.format(string.ascii_lowercase[x])])
                                       for x in range(6,9)])),
                      {}]))

        rc_items = self.auditor.categorize_custom_items()
        self.assertEqual(expected, rc_items)

    def test_get_all_items(self):
        def _mock_iterator(element, itype, vpath, items, ref_counts):
            items.add(element)

        root = Mock(getchildren=Mock(return_value=range(5)))
        self.auditor._iter_by_itype = _mock_iterator
        items = self.auditor._get_all_items(root, None)
        expected = set(range(5))
        self.assertEqual(expected, items)

    def _assert_itypes(self, itypes=None):
        print "inherited itypes:" + str(self.auditor.all_inherit_types)

        random_itypes = ('blade', 'model-package', 'package', 'service',
                         'storage-profile', 'system')
        if not itypes:
            itypes = random_itypes

        for itype in itypes:
            self.assertTrue(itype in self.auditor.all_inherit_types)

    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._get_ext_classpaths')
    def test_get_all_inherit_itemtypes1(self, mock_get_cps):
        mock_get_cps.side_effect = Exception('Something CP happened')
        self.auditor.get_all_inherit_itemtypes()
        self._assert_itypes()

        # ----

        mock_get_cps.reset_mock()
        mock_get_cps.return_value = ['a.b.c', 'd.e.f']
        self.auditor.get_all_inherit_itemtypes()
        self._assert_itypes()

        # ----
        mock_get_cps.reset_mock()
        mock_get_cps.return_value = ['garbage']
        self.auditor.get_all_inherit_itemtypes()
        self._assert_itypes()

    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._get_ext_itemtypes')
    def test_get_all_inherit_itemtypes2(self, mock_get_itypes):
        mock_get_itypes.side_effect = Exception('Something IT happened')
        self.auditor.get_all_inherit_itemtypes()
        self._assert_itypes()

    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._get_ext_classpaths')
    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._get_ext_itemtypes')
    def test_get_all_inherit_itemtypes3(self, mock_get_itypes, mock_get_cps):
        class Reference(object):
            def __init__(self, itype_type_id):
                self.item_type_id = itype_type_id

        class RefCollection(object):
            def __init__(self, itype_type_id):
                self.item_type_id = itype_type_id
            pass

        mock_get_cps.return_value = []

        it1 = Mock(item_type_id='base1', structure={})
        it2 = Mock(item_type_id='base2', structure={})
        it3 = Mock(item_type_id='itype3',
                   extend_item=it1.item_type_id, structure={})
        it4 = Mock(item_type_id='itype4',
                   extend_item=it2.item_type_id, structure={})
        it5 = Mock(item_type_id='itype5',
                   structure={'c1': Reference(it3.item_type_id)})
        it6 = Mock(item_type_id='itype6',
                   structure={'c1': RefCollection(it4.item_type_id)})

        mock_get_itypes.return_value = [it1, it2, it3, it4, it5, it6]

        self.auditor.get_all_inherit_itemtypes()
        self._assert_itypes((it3.item_type_id, it4.item_type_id))

    @patch('audit_enm_for_rh7_uplift.ConfigParser.get')
    @patch('audit_enm_for_rh7_uplift.ConfigParser.read')
    @patch('audit_enm_for_rh7_uplift.os.listdir')
    def test_get_ext_classpaths(self, mock_listdir, mock_read, mock_get):
        mock_listdir.return_value = ['file1.conf']
        mock_read.return_value = ''
        mock_get.return_value = 'a.b.c'

        cps = self.auditor._get_ext_classpaths()
        self.assertEquals(['a.b.c'], cps)

    def test_get_ext_itemtypes1(self):
        class MockModelExtension(object):
            def define_item_types(self):
                return [Mock(item_type_id='X'),
                        Mock(item_type_id='Y')]
        cps = ['a.b.c', 'd.e.f']

        self.assertRaises(ImportError, self.auditor._get_ext_itemtypes, cps)

    @patch('__builtin__.__import__')
    def test_get_ext_itemtypes2(self, mock_import):
        orig_import = __import__

        it1 = Mock(item_type_id='AnItemType')

        def mock_class():
            return Mock(define_item_types=lambda: [it1])

        def b_mock():
            return Mock(mockClass=mock_class)

        def import_mock(name, *args, **kwargs):
            if name == 'mockModule':
                return b_mock()
            return orig_import(name, *args, **kwargs)

        mock_import.side_effect = import_mock

        expected = [it1]
        cps = ['mockModule.mockClass']
        itypes = self.auditor._get_ext_itemtypes(cps)
        self.assertEquals(expected, itypes)

    def test_timeout(self):
        timer = self.auditor.Timeout(60)
        timer.get_cur_time()
        timer.take_a_nap(1)
        self.assertFalse(timer.has_time_elapsed())
        self.assertEquals(60 - timer.get_time_elapsed(),
                          timer.get_remaining_time())

    def test_get_rtd_13032_ndm_rpm_names(self):
        ndm_rpms = self.auditor._get_rtd_13032_ndm_rpm_names()
        self.assertEquals(54, len(ndm_rpms))
        for rname in ('ERICsbgmodel16a_CXP9032973',
                      'ERICvrsmnodemodel_CXP9036241',
                      'ERICmediationmgwnodemodel16a_CXP9032454',
                      'ERICbscpocned_CXP9033388'):
            self.assertTrue(rname in ndm_rpms)
        for rname in ('ERICfoobar_CXP9031234',
                      'ERICbogus_CXP9035678',
                      'ERICinvalid_CXP9039876'):
            self.assertFalse(rname in ndm_rpms)

    def test_hndl_removable_item(self):
        self.auditor._hndl_model_pkg = Mock(return_value=True)
        vpath = '/a/b/c'
        self.assertEquals(self.auditor.removable_items, None)

        self.auditor._hndl_removable_item('model-package', vpath)
        self.assertEquals(self.auditor.removable_items, set())
        self.auditor._hndl_model_pkg.assert_called_once_with(vpath)

        # ----

        self.auditor._hndl_model_pkg.reset_mock()
        self.auditor._hndl_removable_item('bogus-itype', vpath)
        self.auditor._hndl_model_pkg.assert_not_called()

    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._get_rtd_13032_ndm_rpm_names')
    def test_hndl_model_pkg(self, mock_ndm):
        vpath = '/a/b/c'
        rpmname = 'ERICmodelX'
        self.auditor._run_command = Mock(return_value=(0, rpmname))

        mock_ndm.return_value = []
        self.auditor._get_models_yum_repo = Mock(return_value=[])

        self.auditor._hndl_model_pkg(vpath)
        expected = 'litp show -p {0} -o name'.format(vpath)
        self.auditor._run_command.assert_called_with(expected)

        self.assertEquals(None, self.auditor.removable_items)

        #----

        self.auditor.removable_items = set()
        mock_ndm.return_value = [rpmname]

        self.auditor._hndl_model_pkg(vpath)

        expected = set([vpath])
        self.assertEquals(expected, self.auditor.removable_items)

        #----

        mock_ndm.return_value = []
        self.auditor.removable_items = set()
        self.auditor._get_models_yum_repo = Mock(return_value=[rpmname])
        self.auditor._hndl_model_pkg(vpath)
        self.assertEquals(expected, self.auditor.removable_items)

    @patch('audit_enm_for_rh7_uplift.os.walk')
    @patch('audit_enm_for_rh7_uplift.os.path.exists')
    def test_get_models_yum_repo(self, mock_exists, mock_walk):
        mock_exists.return_value = False
        self.assertRaises(SystemExit, self.auditor._get_models_yum_repo)

        # ----

        mock_exists.return_value = True
        rpms = ['ERICmodel{0}-{1}.rpm'.format(string.ascii_uppercase[idx], idx)
                for idx in range(0, 5)]
        mock_walk.return_value = [(None, None, rpms)]

        self.auditor._get_models_yum_repo()
        expected = ['ERICmodel{0}'.format(string.ascii_uppercase[idx])
                    for idx in range(0, 5)]
        self.assertEquals(expected, self.auditor.models_yum_repo_rpmnames)

        # ----

        rpms += ['nonesense.rpm', 'ERICinvalid', 'not-an-rpm', 'what is this']
        mock_walk.return_value = [(None, None, rpms)]
        self.auditor._get_models_yum_repo()
        self.assertEquals(expected, self.auditor.models_yum_repo_rpmnames)

    @patch('__builtin__.open')
    @patch('audit_enm_for_rh7_uplift.EnmAuditForUplift._run_command')
    def test_process_removable_items(self, mock_run, mock_open):
        vpaths = ['/a/b/c', '/d/e/f', '/g/h/i']
        self.auditor.removable_items = vpaths

        mock_run.return_value = (0, '')

        hdr = '#!/bin/bash\nset -x\n'
        ftr = 'litp create_plan\nlitp run_plan\n' + \
              '/opt/ericsson/enminst/bin/monitor_plan.sh\n'
        body = '\n'.join(['litp remove -p {0}'.format(vpath)
                          for vpath in vpaths])

        filename = 'audit_enm_for_rh7_uplift.remove_items'

        expected_txt = hdr + body + '\n' + ftr
        expected_cmd = 'chmod +x {0}'.format(filename)

        self.auditor.process_removable_items()

        mock_open.assert_called_with(filename, 'w')
        handle = mock_open.return_value.__enter__.return_value
        handle.write.assert_called_once_with(expected_txt)
        mock_run.assert_called_with(expected_cmd)

    @patch('audit_enm_for_rh7_uplift.platform.dist')
    def test_assert_rhel_version(self, mock_dist):
        test_data = [(('redhat', '6.10', 'Santiago'), '6.10', False),
                     (('redhat', '6.10', 'Santiago'), '7.9', True),
                     (('redhat', '7.9', 'Maipo'), '7.9', True),
                     (('redhat', '7.9', 'Maipo'), '6.10', True),
                     (('centos', '7.9', 'enm'), '7.9', True),
                     (('centos', '7.7', 'enm-inst'), '7.9', True),
                     (('centos', '8.0', 'Ootpa'), '7.9', True)]

        for (ver_data, version, exception_expected) in test_data:
            mock_dist.return_value = ver_data
            try:
                self.auditor.assert_rhel_version(version)
            except SystemExit:
                self.assertEqual(exception_expected, True)
            else:
                self.assertEqual(exception_expected, False)
