import unittest2
import enm_grub_cfg_check
from enm_grub_cfg_check import GrubConfCheck
from mock import patch


class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id

    def get_property(self, key):
        return self.properties[key]


class TestGrubConfCheck(unittest2.TestCase):
    @patch('enm_grub_cfg_check.LitpRestClient')
    def setUp(self, rest_client):
        self.gcc = GrubConfCheck()
        self.rest = rest_client
        self.gcc.lvs_report = [{'cluster': 'svc_cluster', 'node': 'svc-1'},
                               {'cluster': 'db_cluster', 'node': 'db-2'},
                               {'cluster': 'asr_cluster', 'node': 'asr-1'}]

    def test_cluster_lv_enable(self):
        cluster1 = {'path': '/deployments/enm/clusters//svc_cluster',
             'data': {'id': 'svc_cluster', 'properties': {'grub_lv_enable': 'true'}}}
        cluster2 = {'path': '/deployments/enm/clusters//scp_cluster',
             'data': {'id': 'scp_cluster', 'properties': {'grub_lv_enable': 'true'}}}
        cluster3 = {'path': '/deployments/enm/clusters//db_cluster',
             'data': {'id': 'db_cluster', 'properties': {'grub_lv_enable': 'false'}}}

        self.rest.return_value.get_children.return_value = [cluster1, cluster2, cluster3]
        lv_enable_dict = {'svc_cluster': 'true', 'scp_cluster': 'true', 'db_cluster': 'false'}
        self.assertEquals(lv_enable_dict, self.gcc.cluster_lv_enable())

        cluster1 = {'path': '/deployments/enm/clusters//svc_cluster',
             'data': {'id': 'svc_cluster', 'properties': {}}}
        cluster2 = {'path': '/deployments/enm/clusters//scp_cluster',
             'data': {'id': 'scp_cluster'}}

        self.rest.return_value.get_children.return_value = [cluster1, cluster2]
        lv_enable_dict = {'svc_cluster': 'false', 'scp_cluster': 'false'}
        self.assertEquals(lv_enable_dict, self.gcc.cluster_lv_enable())

    @patch('enm_grub_cfg_check.GrubConfCheck.handle_vg')
    def test_report_lvs(self, handle_vg):
        svc1_object = MockLitpObject('/deployments/enm/clusters/svc_cluster/',
                                        'Applied',
                                        {'hostname': 'svc1'}, 'svc-1')

        mock_cluster_nodes = {'svc_cluster': {'svc-1': svc1_object}}
        self.gcc.nodes = mock_cluster_nodes
        self.gcc.cluster_lv_enable_dict = {'svc_cluster': 'true',
                                           'db_cluster': 'false',
                                           'asr_cluster': 'true'}

        svc1_out = [{'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/storage_profile/volume_groups/vg_root',
               'data': {'id': 'vg_root', 'state': 'Applied'}}]
        self.rest.return_value.get_children.return_value = svc1_out
        handle_vg.return_value = {
            'Cluster': 'svc_cluster', 'Node': 'svc-1',
            'VG': 'vg_root', 'Grub State': 'OK',
            'Missing LV': '-', 'Extra LV': '-'
        }

        expected_report = [{'cluster': 'svc_cluster', 'node': 'svc-1'},
                           {'cluster': 'db_cluster', 'node': 'db-2'},
                           {'cluster': 'asr_cluster', 'node': 'asr-1'},
                           {'Cluster': 'svc_cluster', 'Node': 'svc-1',
                            'VG': 'vg_root', 'Grub State': 'OK',
                            'Missing LV': '-', 'Extra LV': '-'}]
        self.assertEquals(self.gcc.report_lvs(), expected_report)

        db2_object = MockLitpObject('/deployments/enm/clusters/db_cluster/',
                                    'Applied',
                                    {'hostname': 'db2'}, 'db-2')
        self.gcc.nodes = {'db_cluster': {'db-2': db2_object}}

        db2_out = [{'path': '/deployments/enm/clusters/db_cluster/nodes/db-2/storage_profile/volume_groups/vg1',
               'data': {'id': 'vg1', 'state': 'Applied'}}]
        self.rest.return_value.get_children.return_value = db2_out
        expected_report = [{'cluster': 'svc_cluster', 'node': 'svc-1'},
                           {'cluster': 'db_cluster', 'node': 'db-2'},
                           {'cluster': 'asr_cluster', 'node': 'asr-1'},
                           {'Cluster': 'svc_cluster', 'Node': 'svc-1',
                            'VG': 'vg_root', 'Grub State': 'OK',
                            'Missing LV': '-', 'Extra LV': '-'},
                           {'Cluster': 'db_cluster', 'Node': '-',
                            'VG': '-', 'Grub State': 'OK',
                            'Missing LV': '-', 'Extra LV': '-'}]
        self.assertEquals(self.gcc.report_lvs(), expected_report)

        asr1_object = MockLitpObject('/deployments/enm/clusters/asr_cluster/',
                                    'Applied',
                                    {'hostname': 'asr1'}, 'asr-1')
        self.gcc.nodes = {'asr_cluster': {'asr-1': asr1_object}}

        asr1_out = [{'path': '/deployments/enm/clusters/asr_cluster/nodes/asr-1/storage_profile/volume_groups/vg2',
               'data': {'id': 'vg2', 'state': 'Applied'}}]
        self.rest.return_value.get_children.return_value = asr1_out
        handle_vg.return_value = {
            'Cluster': 'asr_cluster', 'Node': 'asr-1',
            'VG': 'vg2', 'Grub State': 'OK',
            'Missing LV': 'lv_var, lv_tmp', 'Extra LV': 'lv_swap'
        }
        expected_report = [{'cluster': 'svc_cluster', 'node': 'svc-1'},
                           {'cluster': 'db_cluster', 'node': 'db-2'},
                           {'cluster': 'asr_cluster', 'node': 'asr-1'},
                           {'Cluster': 'svc_cluster', 'Node': 'svc-1',
                            'VG': 'vg_root', 'Grub State': 'OK',
                            'Missing LV': '-', 'Extra LV': '-'},
                            {'Cluster': 'db_cluster', 'Node': '-',
                            'VG': '-', 'Grub State': 'OK',
                            'Missing LV': '-', 'Extra LV': '-'},
                            {'Cluster': 'asr_cluster', 'Node': 'asr-1',
                            'VG': 'vg2', 'Grub State': 'OK',
                            'Missing LV': 'lv_var, lv_tmp',
                            'Extra LV': 'lv_swap'}]
        self.assertEquals(self.gcc.report_lvs(), expected_report)

    @patch('enm_grub_cfg_check.compare_lvs')
    @patch('enm_grub_cfg_check.get_model_lvs')
    @patch('enm_grub_cfg_check.EnminstAgent')
    def test_handle_vg(self, enminst_agent, model_lvs, compare_lvs):
        enminst_agent.get_grub_conf_lvs.return_value = 'vg_lv_root\nvg1_lv_var' \
                                                        '\nvg2_lv_tmp'
        lv1 = MockLitpObject('/deployments/enm/clusters/svc_cluster/nodes/svc-1/' \
                             'storage_profile/volume_groups/vg1/file_systems',
                             'Applied', {}, 'lv_root')
        lv2 = MockLitpObject('/deployments/enm/clusters/db_cluster/nodes/db-1/' \
                             'storage_profile/volume_groups/vg2/file_systems',
                             'Applied', {}, 'lv_var')
        lv3 = MockLitpObject('/deployments/enm/clusters/asr_cluster/nodes/asr-1/' \
                             'storage_profile/volume_groups/vg/file_systems',
                             'Applied', {}, 'lv_tmp')
        self.rest.return_value.get_children.return_value = [lv1, lv2, lv3]
        model_lvs.return_value = ['lv_root', 'lv_var', 'lv_tmp']
        compare_lvs.return_value = [[], [], False]
        expected_report = {'Cluster': 'scp_cluster', 'Node': 'scp-1', 'VG': 'vg1',
                           'Grub State': 'OK', 'Missing LV': '-', 'Extra LV': '-'}
        vg1 = {'data': {'id': 'vg1'}}
        self.assertEquals(expected_report, self.gcc.handle_vg('hostname', 'scp_cluster', 'scp-1', vg1))

        enminst_agent.get_grub_conf_lvs.return_value = 'vg_lv_root\nvg1_lv_swap'
        lv1 = MockLitpObject('/deployments/enm/clusters/svc_cluster/nodes/svc-1/' \
                             'storage_profile/volume_groups/vg1/file_systems',
                             'Applied', {}, 'lv_root')
        lv2 = MockLitpObject('/deployments/enm/clusters/asr_cluster/nodes/asr-1/' \
                             'storage_profile/volume_groups/vg/file_systems',
                             'Applied', {}, 'lv_tmp')
        lv3 = MockLitpObject('/deployments/enm/clusters/db_cluster/nodes/db-1/' \
                             'storage_profile/volume_groups/vg2/file_systems',
                             'Applied', {}, 'lv_var')
        self.rest.return_value.get_children.return_value = [lv1, lv2, lv3]
        model_lvs.return_value = ['lv_root', 'lv_tmp', 'lv_var']
        compare_lvs.return_value = ['lv_tmp, lv_var', 'lv_swap', True]
        expected_report = {'Cluster': 'scp_cluster', 'Node': 'scp-1', 'VG': 'vg1',
                           'Grub State': 'NOT OK', 'Missing LV': 'lv_tmp, lv_var',
                           'Extra LV': 'lv_swap'}
        vg1 = {'data': {'id': 'vg1'}}
        self.assertEquals(expected_report, self.gcc.handle_vg('hostname', 'scp_cluster', 'scp-1', vg1))

    def test_get_model_lvs(self):
        lv1 = {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/' \
               'storage_profile/volume_groups/vg1/file_systems/lv_root',
               'data': {'id': 'lv_root'}}
        lv2 = {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/' \
               'storage_profile/volume_groups/vg1/file_systems/lv_swap',
               'data': {'id': 'lv_swap'}}
        lv3 = {'path': '/deployments/enm/clusters/svc_cluster/nodes/svc-1/' \
               'storage_profile/volume_groups/vg1/file_systems/lv_var',
               'data': {'id': 'lv_var'}}
        lvs = ['lv_root', 'lv_swap', 'lv_var']
        self.assertEquals(enm_grub_cfg_check.get_model_lvs([lv1, lv2, lv3]), lvs)

    def test_compare_lvs(self):
        model_lvs = ['lv_root', 'lv_var', 'lv_swap']
        grub_lvs = ['lv_root']
        expected_out = ('lv_swap, lv_var', '', True)
        self.assertEquals(enm_grub_cfg_check.compare_lvs(model_lvs, grub_lvs), expected_out)

        model_lvs = ['lv_root', 'lv_var']
        grub_lvs = ['lv_root', 'lv_swap']
        expected_out = ('lv_var', 'lv_swap', True)
        self.assertEquals(enm_grub_cfg_check.compare_lvs(model_lvs, grub_lvs), expected_out)

        model_lvs = ['lv_root']
        grub_lvs = ['lv_root', 'lv_var', 'lv_swap']
        expected_out = ('', 'lv_swap, lv_var', True)
        self.assertEquals(enm_grub_cfg_check.compare_lvs(model_lvs, grub_lvs), expected_out)

        model_lvs = ['lv_root', 'lv_var', 'lv_swap']
        grub_lvs = ['lv_root', 'lv_swap', 'lv_var']
        expected_out = ('', '', False)
        self.assertEquals(enm_grub_cfg_check.compare_lvs(model_lvs, grub_lvs), expected_out)


if __name__ == '__main__':
    unittest2.main()
