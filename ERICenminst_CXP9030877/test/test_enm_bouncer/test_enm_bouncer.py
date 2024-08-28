import unittest2
from mock import patch, call, ANY
from io import StringIO
from io import BytesIO as StringIO
from argparse import Namespace
from h_litp.litp_rest_client import LitpRestClient
from enm_upgrade_prechecks import EnmPreChecks
import enm_bouncer
import logging

CMD_ENM_BOUNCER = 'enm_bouncer.py'
ILO1_NODE = 'svc-1'
ILO2_NODE = 'svc-2'
ILO3_NODE = 'scp-1'
ILO4_NODE = 'scp-2'
ILO1_ADDRESS = '10.10.10.10'
ILO2_ADDRESS = '10.10.10.11'
ILO3_ADDRESS = '10.10.10.12'
ILO4_ADDRESS = '10.10.10.13'
ILO_USER = 'root'
ILO_PASSWORD = '12shroot'

MOCK_SYS_BMC = {ILO1_NODE:{'iloaddress': ILO1_ADDRESS,
                           'username': ILO_USER, 'password': ILO_PASSWORD},
                ILO2_NODE: {'iloaddress': ILO2_ADDRESS,
                           'username': ILO_USER, 'password': ILO_PASSWORD},
                ILO3_NODE: {'iloaddress': ILO3_ADDRESS,
                           'username': ILO_USER, 'password': ILO_PASSWORD},
                ILO4_NODE: {'iloaddress': ILO4_ADDRESS,
                           'username': ILO_USER, 'password': ILO_PASSWORD}
                }


MOCK_SYS_BMC_1 = {ILO1_NODE:{'iloaddress': ILO1_ADDRESS,
                           'username': ILO_USER, 'password': ILO_PASSWORD}}


class MockLitpObject(object):
    def __init__(self, path, state, properties, item_id):
        self.path = path
        self.state = state
        self.properties = properties
        self.item_id = item_id

    def get_property(self, key):
        return self.properties[key]

svc1_object  =  MockLitpObject("/deployments/enm/clusters/svc_cluster/nodes/svc-1" ,'Applied',
                                {'is_locked': 'false', 'hostname': 'ieatrcxb3388'},'svc-1')
svc2_object  =  MockLitpObject("/deployments/enm/clusters/svc_cluster/nodes/svc-2" ,'Applied',
                                {'is_locked': 'false', 'hostname': 'ieatrcxb3565'},'svc-2')

SVC_CLUSTER = 'svc_cluster'

SVC_CLUSTER_NODES = {'svc-1':svc1_object,
                     'svc-2':svc2_object}

MOCK_CLUSTER_NODES = {SVC_CLUSTER: SVC_CLUSTER_NODES}


SVC_CLUSTER_1 = 'svc_cluster'

SVC_CLUSTER_NODES_1 = {'svc-1':svc1_object}

MOCK_CLUSTER_NODES_1 = {SVC_CLUSTER_1: SVC_CLUSTER_NODES_1}

power_status_svc_1 = 0
power_status_svc_2 = 0
power_off_svc_1 = 0
power_on_svc_1 = 0


class TestEnmBouncer(unittest2.TestCase):

    def setUp(self):
        import enm_bouncer
        self.enm_bouncer = enm_bouncer
        self.clusters = "svc_cluster scp_cluster"
        self.nodes = "svc-1 svc-2"

        global power_status_svc_1
        global power_status_svc_2
        global power_off_svc_1
        global power_on_svc_1
        power_status_svc_1 = 0
        power_status_svc_2 = 0
        power_off_svc_1 = 0
        power_on_svc_1 = 0



    def add_clusters_option(self):
        return ' --clusters ' + self.clusters

    def add_nodes_option(self):
        return ' --nodes ' + self.nodes

    def add_bounce_option(self):
        return ' --action bounce'

    def add_on_option(self):
        return ' --action on'

    def add_off_option(self):
        return ' --action off'

    @patch('requests.get')
    def test_power_status_rf(self, mock_get):
        mock_get.return_value.status_code = 200 # Mock status code of response.
        result = {'PowerState':'On'}
        mock_get.return_value.json.return_value = result
        response = self.enm_bouncer.power_status_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD)
        self.assertTrue(mock_get.called)
        self.assertTrue(response)

    @patch('requests.get')
    def test_power_status_rf_off(self, mock_get):
        mock_get.return_value.status_code = 200 # Mock status code of response.
        result = {'PowerState':'Off'}
        mock_get.return_value.json.return_value = result
        response = self.enm_bouncer.power_status_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD)
        self.assertTrue(mock_get.called)
        self.assertFalse(response)

    @patch('requests.get')
    def test_power_status_rf_error(self, mock_get):
        mock_get.return_value.status_code = 404
        response = self.enm_bouncer.power_status_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD)
        self.assertTrue(mock_get.called)
        self.assertEquals(None, response)

    @patch('requests.post')
    def test_power_on_rf_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'Messages':[{'MessageID':'Base.0.10.Success'}]}
        response = self.enm_bouncer.power_action_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD, 'On')
        self.assertTrue(mock_post.called)
        self.assertEquals("Powering on", response)

    @patch('requests.post')
    def test_power_on_rf_already_on(self, mock_post):
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {'Messages':[{'MessageArgs':['Power is on']}]}
        response = self.enm_bouncer.power_action_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD, 'On')
        self.assertTrue(mock_post.called)
        self.assertEquals("Power is on", response)

    @patch('requests.post')
    def test_power_on_rf_error(self, mock_post):
        mock_post.return_value.status_code = 404
        response = self.enm_bouncer.power_action_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD, 'On')
        self.assertTrue(mock_post.called)
        self.assertEquals(None, response)

    @patch('requests.post')
    def test_power_off_rf_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'Messages':[{'MessageID':'Base.0.10.Success'}]}
        response = self.enm_bouncer.power_action_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD, 'ForceOff')
        self.assertTrue(mock_post.called)
        self.assertEquals("Powering off", response)

    @patch('requests.post')
    def test_power_off_rf_already_off(self, mock_post):
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {'Messages':[{'MessageArgs':['Power is off']}]}
        response = self.enm_bouncer.power_action_rf(ILO1_ADDRESS, ILO_USER, ILO_PASSWORD, 'ForceOff')
        self.assertTrue(mock_post.called)
        self.assertEquals("Power is off", response)

    @patch('enm_upgrade_prechecks.EnmPreChecks.is_virtual_environment')
    @patch('time.sleep', return_value=None)
    @patch('enm_bouncer.power_action_rf')
    @patch('enm_bouncer.power_status_rf')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_nodes_when_on(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock_power_status,
                                mock_power_action,
                                mock_sleep,
                                mock_is_virt
                                ):

        def ps_side_effect(*args, **kwargs):
            global power_status_svc_1
            global power_status_svc_2

            if '10.10.10.10' in args[0]:
                power_status_svc_1 +=1

                if power_status_svc_1 == 1:
                    return True
                if power_status_svc_1 == 2:
                    return False
                if power_status_svc_1 == 3:
                    return False
                if power_status_svc_1 == 4:
                    return True

            if '10.10.10.11' in args[0]:
                power_status_svc_2 +=1

                if power_status_svc_2 == 1:
                    return True
                if power_status_svc_2 == 2:
                    return False
                if power_status_svc_2 == 3:
                    return False
                if power_status_svc_2 == 4:
                    return True
        mock_power_status.side_effect = ps_side_effect

        mock_power_action.side_effect = ['Power is off', 'Power is off', 'Power is on', 'Power is on']

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES
        mock_is_virt.return_value = False
        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_nodes(['svc-1', 'svc-2'], 'bounce', 120)

        self.assertEquals(8,mock_power_status.call_count)
        self.assertEquals(4,mock_power_action.call_count)

    @patch('enm_upgrade_prechecks.EnmPreChecks.is_virtual_environment')
    @patch('time.sleep', return_value=None)
    @patch('enm_bouncer.power_action_rf')
    @patch('enm_bouncer.power_status_rf')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_off_nodes_when_off(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock_power_status,
                                mock_power_action,
                                mock_sleep,
                                mock_is_virt):

        def ps_side_effect(*args, **kwargs):
            return False
        mock_power_status.side_effect = ps_side_effect

        def poff_side_effect(*args, **kwargs):
            return True
        mock_power_action.side_effect = poff_side_effect

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES

        mock_is_virt.return_value = False

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_nodes(['svc-1', 'svc-2'], 'off', 120)

        self.assertEquals(2,mock_power_status.call_count)
        self.assertEquals(0,mock_power_action.call_count)

    @patch('enm_upgrade_prechecks.EnmPreChecks.is_virtual_environment')
    @patch('time.sleep', return_value=None)
    @patch('enm_bouncer.power_action_rf')
    @patch('enm_bouncer.power_status_rf')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_off_nodes_when_on(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock_power_status,
                                mock_power_action,
                                mock_sleep,
                                mock_is_virt):

        def ps_side_effect(*args, **kwargs):
            global power_status_svc_1
            global power_status_svc_2

            if '10.10.10.10' in args[0]:
                if power_status_svc_1 >=2:
                    return False
                else :
                    power_status_svc_1 +=1
                    return True

            if '10.10.10.11' in args[0]:
                if power_status_svc_2 >=2:
                    return False
                else :
                    power_status_svc_2 +=1
                    return True
        mock_power_status.side_effect = ps_side_effect

        def poff_side_effect(*args, **kwargs):
            global power_off_svc_1

            if '10.10.10.10' in args[0]:
                if power_off_svc_1 >=1:
                    return 'Power is off'
                else :
                    power_off_svc_1 +=1
                    return ''

            if '10.10.10.11' in args[0]:
                return 'Power is off'
        mock_power_action.side_effect = poff_side_effect

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES

        mock_is_virt.return_value = False

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_nodes(['svc-1', 'svc-2'], 'off', 120)

        self.assertEquals(6,mock_power_status.call_count)
        self.assertEquals(3,mock_power_action.call_count)

    @patch('enm_upgrade_prechecks.EnmPreChecks.is_virtual_environment')
    @patch('time.sleep', return_value=None)
    @patch('enm_bouncer.power_action_rf')
    @patch('enm_bouncer.power_status_rf')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_on_nodes_when_on(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock_power_status,
                                mock_power_action,
                                mock_sleep,
                                mock_is_virt):

        def ps_side_effect(*args, **kwargs):
            return True
        mock_power_status.side_effect = ps_side_effect

        def pon_side_effect(*args, **kwargs):
            return True
        mock_power_action.side_effect = pon_side_effect

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES
        mock_is_virt.return_value = False

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_nodes(['svc-1', 'svc-2'], 'on', 120)

        self.assertEquals(2,mock_power_status.call_count)
        self.assertEquals(0,mock_power_action.call_count)

    @patch('enm_upgrade_prechecks.EnmPreChecks.is_virtual_environment')
    @patch('time.sleep', return_value=None)
    @patch('enm_bouncer.power_action_rf')
    @patch('enm_bouncer.power_status_rf')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_on_nodes_when_off(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock_power_on_status,
                                mock_power_action,
                                mock_sleep,
                                mock_is_virt):
        def ps_side_effect(*args, **kwargs):
            global power_status_svc_1
            global power_status_svc_2

            if '10.10.10.10' in args[0]:
                if power_status_svc_1 >=2:
                    return True
                else :
                    power_status_svc_1 +=1
                    return False

            if '10.10.10.11' in args[0]:
                if power_status_svc_2 >=2:
                    return True
                else :
                    power_status_svc_2 +=1
                    return False
        mock_power_on_status.side_effect = ps_side_effect

        def pon_side_effect(*args, **kwargs):
            global power_on_svc_1

            if '10.10.10.10' in args[0]:
                if power_on_svc_1 >=1:
                    return 'Power is on'
                else :
                    power_on_svc_1 +=1
                    return ''

            if '10.10.10.11' in args[0]:
                return 'Power is on'
        mock_power_action.side_effect = pon_side_effect

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES

        mock_is_virt.return_value = False

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_nodes(['svc-1', 'svc-2'], 'on', 120)

        self.assertEquals(6,mock_power_on_status.call_count)
        self.assertEquals(3,mock_power_action.call_count)

    @patch('enm_bouncer.EnmBouncer._bounce_nodes')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_off_node(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock__bounce_nodes):

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_nodes(['svc-1'], 'off', 120)

        expected_calls = [call({'svc-1': {'iloaddress': '10.10.10.10',
                                           'username': 'root',
                                           'password': '12shroot'}},
                                           'off', 120)]

        mock__bounce_nodes.assert_has_calls(expected_calls, False)

    @patch('enm_bouncer.EnmBouncer._bounce_clusters')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    def test__EnmBouncer_bounce_on_cluster(self, mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock__bounce_clusters):

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_clusters(['svc_cluster'], 'on', 120)

        expected_calls = [call({'svc_cluster':
                                {'svc-1': {'iloaddress': '10.10.10.10',
                                           'username': 'root',
                                           'password': '12shroot'},
                                'svc-2': {'iloaddress': '10.10.10.11',
                                           'username': 'root',
                                           'password': '12shroot'}}},
                                           'on', 120, False)]

        mock__bounce_clusters.assert_has_calls(expected_calls, False)

    @patch('enm_upgrade_prechecks.EnmPreChecks.is_virtual_environment')
    @patch('time.sleep', return_value=None)
    @patch('enm_bouncer.power_action_rf')
    @patch('enm_bouncer.power_status_rf')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_items_by_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.get_cluster_nodes')
    @patch('enm_bouncer.EnmBouncer.get_sys_bmcs')
    @patch('enm_bouncer.EnmBouncer.get_cluster_seed',return_value=1)
    def test__EnmBouncer_bounce_cluster_when_on_seed(self,
                                mock_get_cluster_seed,
                                mock_get_sys_bmcs,
                                mock_get_cluster_nodes,
                                mock_get_items_by_type,
                                mock_power_status,
                                mock_power_action,
                                mock_sleep,
                                mock_is_virt
                                ):

        def ps_side_effect(*args, **kwargs):
            global power_status_svc_1
            global power_status_svc_2

            if '10.10.10.10' in args[0]:
                power_status_svc_1 +=1

                if power_status_svc_1 == 1:
                    return True
                if power_status_svc_1 == 2:
                    return False
                if power_status_svc_1 == 3:
                    return False
                if power_status_svc_1 == 4:
                    return True

            if '10.10.10.11' in args[0]:
                power_status_svc_2 +=1

                if power_status_svc_2 == 1:
                    return True
                if power_status_svc_2 == 2:
                    return False
                if power_status_svc_2 == 3:
                    return False
                if power_status_svc_2 == 4:
                    return True
        mock_power_status.side_effect = ps_side_effect

        mock_power_action.side_effect = ['Power is off', 'Power is on']

        mock_get_sys_bmcs.return_value = MOCK_SYS_BMC_1
        mock_get_cluster_nodes.return_value = MOCK_CLUSTER_NODES_1
        mock_is_virt.return_value = False

        bouncer = self.enm_bouncer.EnmBouncer()
        bouncer.bounce_clusters(['svc_cluster'], 'bounce', 120, seeded=True)

        self.assertEquals(4,mock_power_status.call_count)
        self.assertEquals(2,mock_power_action.call_count)

    @patch('enm_bouncer.bounce')
    def test_main_off_clusters(self, mock_bounce):
        args = '{0}{1}{2}'.format('',
                                     self.add_off_option(),
                                     self.add_clusters_option())

        self.enm_bouncer.main(args.split())

        expected_calls = [call(Namespace(action='off',
                         clusters=['svc_cluster', 'scp_cluster'],
                         nodes=[], seeded=False, timeout=60))]

        mock_bounce.assert_has_calls(expected_calls, False)

    @patch('enm_bouncer.bounce')
    def test_main_on_nodes(self, mock_bounce):
        args = '{0}{1}{2}'.format('',
                                     self.add_on_option(),
                                     self.add_nodes_option())

        self.enm_bouncer.main(args.split())

        expected_calls = [call(Namespace(action='on', clusters=[],
                         nodes=['svc-1', 'svc-2'], seeded=False, timeout=60))]

        mock_bounce.assert_has_calls(expected_calls, False)

    @patch('sys.stderr', new_callable = StringIO)
    def test_main_err(self, mock_stderr):

        args = ''

        with self.assertRaises(SystemExit) as cm:
            self.enm_bouncer.main(args)
        self.assertEqual(cm.exception.code, 2)
        self.assertRegexpMatches(mock_stderr.getvalue(),
        r"error: one of the arguments --clusters --nodes is required")

    @patch('sys.stdout', new_callable = StringIO)
    def test_main_help(self, mock_stdout):

        args = ['','-h']

        with self.assertRaises(SystemExit) as cm:
            self.enm_bouncer.main(args)
        self.assertEqual(cm.exception.code, 0)
        print(mock_stdout.getvalue())
        self.assertRegexpMatches(mock_stdout.getvalue(),
                                 r"power off/on clusters or nodes")


if __name__ == '__main__':
    unittest2.main()
