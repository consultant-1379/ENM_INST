import unittest2
from mock import patch, call, ANY
from io import StringIO
from io import BytesIO as StringIO
from argparse import Namespace
from preonlinedep import PreOnlineProvisioner

CMD_PEONLINEDEP = 'preonlinedep.py'

class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id
 
    def get_property(self, key):
        return self.properties[key]

SVC_CLUSTER  =  {'properties': {'app_agent_num_threads': '50'}}

svc1_object  =  {'data':
                    {'properties':
                        {'is_locked': 'false',
                         'hostname': 'ieatrcxb3388'}
                    }
                }

svc2_object  =  {'data':
                    {'properties':
                        {'is_locked': 'false',
                         'hostname': 'ieatrcxb3389'}
                    }
                }
NODES = [svc1_object,svc2_object]

service1_object = {'data':
                    {'properties':
                     {'name': 'lvsrouter',
                      'initial_online_dependency_list': '',
                      'node_list': 'svc-1,svc-2'}
                    }
                  }

service2_object = {'data':
                    {'properties':
                     {'name': 'mscm',
                      'initial_online_dependency_list': 'lvsrouter,sps',
                       'node_list': 'svc-1,svc-2'}
                    }
                  }

service3_object = {'data':
                    {'properties':
                     {'name': 'mscm-ce-2',
                      'initial_online_dependency_list': 'lvsrouter,sps',
                       'node_list': 'svc-1,svc-2'}
                    }
                  }

service4_object = {'data':
                    {'properties':
                     {'name': 'fmserv',
                      'initial_online_dependency_list': 'lvsrouter',
                      'node_list': 'svc-1'}
                    }
                  }

service5_object = {'data':
                    {'properties':
                     {'name': 'fmserv1',
                      'initial_online_dependency_list': 'lvsrouter',
                      'node_list': 'svc-1,svc-2'}
                    }
                  }

service6_object = {'data':
                    {'properties':
                     {'name': 'haproxy-int',
                      'initial_online_dependency_list': '',
                       'node_list': 'svc-1,svc-2'}
                    }
                  }

service7_object = {'data':
                    {'properties':
                     {'name': 'haproxy-ext',
                      'initial_online_dependency_list': 'sps',
                      'node_list': 'svc-1,svc-2'}
                    }
                  }

CLUSTERED_SERVICES = [service1_object,
                      service2_object,
                      service3_object,
                      service4_object,
                      service5_object,
                      service6_object,
                      service7_object]

class TestEnmBouncer(unittest2.TestCase):

    def setUp(self):
        import preonlinedep
        self.preonlinedep = preonlinedep

    def add_set_option(self):
        return ' --action set'

    def add_unset_option(self):
        return ' --action unset'

    @patch('preonlinedep.exec_process')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test__PreOnlineProvisioner_init(self,
                                         mock_rest_get,
                                         mock_rest_get_items_by_type,
                                         mock_exec_process):

        mock_rest_get.return_value = SVC_CLUSTER
        def get_items_by_type_side_effect(*args, **kwargs):

            if 'node' in args[1]:
                return NODES

            if 'vcs-clustered-service' in args[1]:
                return CLUSTERED_SERVICES

        mock_rest_get_items_by_type.side_effect = get_items_by_type_side_effect
        pop = self.preonlinedep.PreOnlineProvisioner()
        self.assertEqual(pop.all_sgs,['Grp_CS_svc_cluster_mscm-ce_2',
                                      'Grp_CS_svc_cluster_haproxy_ext',
                                      'Grp_CS_svc_cluster_fmserv',
                                      'Grp_CS_svc_cluster_fmserv1',
                                      'Grp_CS_svc_cluster_mscm'
                                      ])
        self.assertEqual(pop.nodes,[{'data':
                                     {'properties':
                                      {'is_locked': 'false', 'hostname': 'ieatrcxb3388'}
                                      }},
                                     {'data':
                                      {'properties':
                                       {'is_locked': 'false', 'hostname': 'ieatrcxb3389'}
                                       }}
                                     ])

    @patch('time.sleep', return_value=None)
    @patch('preonlinedep.exec_process')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test__PreOnlineProvisioner_set_preonline_trigger(self,
                                         mock_rest_get,
                                         mock_rest_get_items_by_type,
                                         mock_exec_process,
                                         mock_time_sleep):

        mock_rest_get.return_value = SVC_CLUSTER
        mock_exec_process.return_value = ''
        def get_items_by_type_side_effect(*args, **kwargs):

            if 'node' in args[1]:
                return NODES

            if 'vcs-clustered-service' in args[1]:
                return CLUSTERED_SERVICES

        mock_rest_get_items_by_type.side_effect = get_items_by_type_side_effect
        pop = PreOnlineProvisioner()
        pop.set_preonline_trigger()
        #print(mock_exec_process.mock_calls)
        self.assertEqual(pop.all_sgs,['Grp_CS_svc_cluster_mscm-ce_2',
                                      'Grp_CS_svc_cluster_haproxy_ext',
                                      'Grp_CS_svc_cluster_fmserv',
                                      'Grp_CS_svc_cluster_fmserv1',
                                      'Grp_CS_svc_cluster_mscm'])
        self.assertEqual(mock_exec_process.call_args_list[0],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_display',
                         'groups=Grp_CS_svc_cluster_haproxy_ext',
                         '-I', 'ieatrcxb3388']))
        self.assertEqual(mock_exec_process.call_args_list[1],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_display',
                         'groups=Grp_CS_svc_cluster_mscm-ce_2',
                         '-I', 'ieatrcxb3388']))
        cmd_str = mock_exec_process.call_args_list[2][0][0]

        self.assertTrue("curl --request PUT --data" in cmd_str)
        self.assertTrue("http://ms-1:8500/v1/kv/enminst/preonline" in cmd_str)

        self.assertEqual(mock_exec_process.call_args_list[3],
                         call(['mco', 'rpc', 'filemanager',
                         'pull_file',
                         'consul_url=http://ms-1:8500/v1/kv/enminst/preonline',
                         'file_path=/opt/VRTSvcs/bin/triggers/preonline',
                         '-I', 'ieatrcxb3388', '-I', 'ieatrcxb3389']))

        self.assertEqual(mock_exec_process.call_args_list[4],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_add_triggers_enabled',
                         'group_name=Grp_CS_svc_cluster_mscm-ce_2',
                         'attribute_val=PREONLINE',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[5],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_modify',
                         'group_name=Grp_CS_svc_cluster_mscm-ce_2',
                         'attribute=PreonlineTimeout', 'attribute_val=1500',
                         '-I', 'ieatrcxb3388']))
 
        self.assertEqual(mock_exec_process.call_args_list[6],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_modify',
                         'group_name=Grp_CS_svc_cluster_mscm-ce_2',
                         'attribute=PreOnline', 'attribute_val=1',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[7],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_add_triggers_enabled',
                         'group_name=Grp_CS_svc_cluster_haproxy_ext',
                         'attribute_val=PREONLINE',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[8],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_modify',
                         'group_name=Grp_CS_svc_cluster_haproxy_ext',
                         'attribute=PreonlineTimeout', 'attribute_val=1500',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[9],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_modify', 
                         'group_name=Grp_CS_svc_cluster_haproxy_ext',
                         'attribute=PreOnline', 'attribute_val=1',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[19],
                         call(['mco', 'rpc', 'enminst',
                         'cluster_app_agent_num_threads',
                         'app_agent_num_threads=10',
                         '-I', 'ieatrcxb3388']))

        self.assertTrue(mock_exec_process.call_count, 20)

    @patch('time.sleep', return_value=None)
    @patch('preonlinedep.exec_process')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test__PreOnlineProvisioner_unset_preonline_trigger(self,
                                         mock_rest_get,
                                         mock_rest_get_items_by_type,
                                         mock_exec_process,
                                         mock_time_sleep):

        mock_rest_get.return_value = SVC_CLUSTER
        mock_exec_process.return_value = ''
        def get_items_by_type_side_effect(*args, **kwargs):

            if 'node' in args[1]:
                return NODES

            if 'vcs-clustered-service' in args[1]:
                return CLUSTERED_SERVICES

        mock_rest_get_items_by_type.side_effect = get_items_by_type_side_effect
        pop = PreOnlineProvisioner()
        pop.unset_preonline_trigger()
        #print(mock_exec_process.mock_calls)
        self.assertEqual(pop.all_sgs,['Grp_CS_svc_cluster_mscm-ce_2',
                                      'Grp_CS_svc_cluster_haproxy_ext',
                                      'Grp_CS_svc_cluster_fmserv',
                                      'Grp_CS_svc_cluster_fmserv1',
                                      'Grp_CS_svc_cluster_mscm'])

        self.assertEqual(mock_exec_process.call_args_list[0],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_display',
                         'groups=Grp_CS_svc_cluster_haproxy_ext',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[1],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_display',
                         'groups=Grp_CS_svc_cluster_mscm-ce_2',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[2],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_delete_triggers_enabled',
                         'group_name=Grp_CS_svc_cluster_mscm-ce_2',
                         'attribute_val=PREONLINE',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[3],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_modify',
                         'group_name=Grp_CS_svc_cluster_mscm-ce_2',
                         'attribute=PreOnline', 'attribute_val=0',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[4],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_delete_triggers_enabled',
                         'group_name=Grp_CS_svc_cluster_haproxy_ext',
                         'attribute_val=PREONLINE',
                        '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[5],
                         call(['mco', 'rpc', 'enminst',
                         'hagrp_modify',
                         'group_name=Grp_CS_svc_cluster_haproxy_ext',
                         'attribute=PreOnline', 'attribute_val=0',
                         '-I', 'ieatrcxb3388']))

        self.assertEqual(mock_exec_process.call_args_list[12],
                        call(['mco', 'rpc', 'enminst',
                        'cluster_app_agent_num_threads',
                        'app_agent_num_threads=50',
                        '-I', 'ieatrcxb3388']))
        self.assertTrue(mock_exec_process.call_count, 13)

    @patch('preonlinedep.preonline')
    def test_main_unset(self, mock_preonline):
        args = '{0}{1}'.format('',self.add_unset_option())
        self.preonlinedep.main(args.split())

        expected_calls = [call(Namespace(action='unset'))]
        mock_preonline.assert_has_calls(expected_calls, False)

    @patch('preonlinedep.preonline')
    def test_main_set(self, mock_preonline):
        args = '{0}{1}'.format('', self.add_set_option())
        self.preonlinedep.main(args.split())

        expected_calls = [call(Namespace(action='set'))]
        mock_preonline.assert_has_calls(expected_calls, False)

    @patch('sys.stderr', new_callable = StringIO)
    def test_main_err(self, mock_stderr):

        args = ''

        with self.assertRaises(SystemExit) as cm:
            self.preonlinedep.main(args)
        self.assertEqual(cm.exception.code, 2)
        self.assertRegexpMatches(mock_stderr.getvalue(),
        r"error: argument --action is required")

    @patch('sys.stdout', new_callable = StringIO)
    def test_main_help(self, mock_stdout):

        args = ['','-h']

        with self.assertRaises(SystemExit) as cm:
            self.preonlinedep.main(args)
        self.assertEqual(cm.exception.code, 0)
        #print(mock_stdout.getvalue())
        self.assertRegexpMatches(mock_stdout.getvalue(),
        r"provision/deprovision dependency based VCS preonline trigger on the svc cluster")


if __name__ == '__main__':
    unittest2.main()
