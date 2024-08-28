
import httplib
import os
import sys
from StringIO import StringIO
from json import dumps, load
from os.path import join, dirname, abspath, exists
from tempfile import gettempdir
from time import time, sleep

from base64 import encodestring

import unittest2
from mock import Mock, MagicMock
from mock import patch, call
from unittest2 import TestCase

sys.modules['pwd'] = MagicMock()

from h_litp.litp_rest_client import LitpRestClient, LitpObject, PlanMonitor
from h_litp.litp_rest_client import UnixSocketConnection
from h_litp.litp_utils import TCP_CONNECTION, UNIX_CONNECTION
from h_litp.litp_utils import LitpException, LitprcConfig
from h_util.h_utils import ExitCodes
from test_utils import assert_exception_raised
import re


def get_node_json(item_type, item_id, state,
                  model_path, properties=None, children=None):
    data = {
        "item-type-name": item_type,
        "applied_properties_determinable": "true",
        "state": state,
        "_links": {
            "self": {
                "href": "https://localhost:9999/litp/rest/v1" + model_path
            },
            "item-type": {
                "href": "https://localhost:9999/litp/rest/v1/item-types/" +
                        item_type
            }
        },
        "id": item_id
    }
    if properties:
        data["properties"] = properties
    if children:
        data['_embedded'] = {'item': []}
        for collection_type, child_path in children.items():
            data['_embedded']['item'].append(
                    {
                        "item-type-name": "collection-of-" + collection_type,
                        "applied_properties_determinable": "true",
                        "state": "Applied",
                        "_links": {
                            "self": {
                                "href":
                                    "https://localhost:9999/litp/rest/v1/" +
                                    child_path
                            },
                            "collection-of": {
                                "href":
                                    "https://localhost:9999/litp/rest/v1/"
                                    "item-types/" + collection_type
                            }
                        },
                        "id": child_path.split('/')[-1]
                    }
            )
    return data


def get_json(filename):
    jdir = join(dirname(abspath(__file__)), 'data')
    with open(join(jdir, filename)) as infile:
        return load(infile)


def setup_mock(client, call_stack, debug=False):
    _https = MockHTTPSConnection('', 1, debug)
    _https.expected_responses = []
    for frame in call_stack:
        _https.add_to_expected_calls(frame[0])
        reason = None
        if len(frame) >= 4:
            reason = frame[3]
        content_type = LitpRestClient.CONTENT_TYPE_JSON
        if len(frame) >= 4:
            content_type = frame[3]
        _https.add_to_expected_responses(frame[1], status=frame[2],
                                         reason=reason,
                                         content_type=content_type)

    client.get_https_connection = MagicMock()
    client.get_https_connection.return_value = _https


class MockHTTPResponse(object):
    def __init__(self, data, status, reason, content_type='application/json'):
        self.data = data
        self.status = status
        self.reason = reason
        self.content_type = content_type

    def read(self):
        return self.data

    def __repr__(self):
        return 'Data:{0} Status:{1} Reason:{2}'.format(self.data, self.status,
                                                       self.reason)

    def getheader(self, name, default=None):
        return self.content_type


class MockHTTPSConnection(httplib.HTTPSConnection):
    data = '{}'
    status = 0
    reason = ''

    def __init__(self, host, port, debug):
        self.expected_responses = []
        self.expected_calls = []
        self.debug = debug

    def set_expected_response(self, data, status=httplib.OK, reason='OK'):
        self.data = data
        self.status = status
        self.reason = reason

    def add_to_expected_calls(self, method):
        self.expected_calls.insert(0, method)

    def add_to_expected_responses(self, data, status=httplib.OK, reason='OK',
                                  content_type='application/json'):
        self.expected_responses.insert(
                0, MockHTTPResponse(data, status, reason,
                                    content_type=content_type))

    def getresponse(self):
        if len(self.expected_responses) == 0:
            return MockHTTPResponse(self.data, self.status, self.reason)
        else:
            _resdata = self.expected_responses.pop()
            if self.debug:
                print 'LITP response| {0}'.format(_resdata)
            return _resdata

    def request(self, method, url, body=None, headers=None):
        if headers is None:
            headers = {}
        if self.debug:
            print 'LITP call: {0} {1}'.format(method, url)
        if not self.expected_calls:
            raise AssertionError(
                'No more calls expected but recieved {0} {1}'.format(
                        method, url))
        expected_call = self.expected_calls.pop()
        if method != expected_call:
            raise AssertionError(
                'Unexpected HTTP request \'{0}\', expected \'{1}\''.format(
                    method, expected_call))

    def was_all_called(self):
        return len(self.expected_responses) == 0


class TestUnixSocketConnection(TestCase):
    def test_init(self):
        test_path = "/some/path"
        usc = UnixSocketConnection(test_path)
        self.assertEqual(test_path, usc.path)
        self.assertTrue(isinstance(usc, UnixSocketConnection))

    @patch('h_litp.litp_rest_client.socket.socket.connect')
    def test_connect(self, socket_connection):
        test_path = "/some/path"
        usc = UnixSocketConnection(test_path)
        usc.connect()
        calls = [call(test_path)]
        self.assertEqual(calls, socket_connection.mock_calls)


class TestLitpSocketClient(TestCase):

    @patch('h_litp.litp_rest_client.pwd.getpwuid')
    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_https_connection_unix(
        self, get_connection_type, read_litprc, getpwuid):
        litprc_data_path = 'path/to/socket'
        litprc_data = LitprcConfig(path=litprc_data_path)

        logged_in_user = 'logged_in_user'

        get_connection_type.side_effect = lambda x: (
            UNIX_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        getpwuid.side_effect = lambda x: Mock(pw_name=logged_in_user)

        client = LitpRestClient()
        result = client.get_https_connection()
        self.assertTrue(result.__class__ == UnixSocketConnection)


    @patch('h_litp.litp_rest_client.pwd.getpwuid')
    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_https_connection_tcp(
        self, get_connection_type, read_litprc, getpwuid):
        litprc_data_path = 'path/to/tcp'
        litprc_data = LitprcConfig(path=litprc_data_path)
        litprc_data['username'] = 'litp_username'
        litprc_data['password'] = 'litp_password'
        logged_in_user = 'logged_in_user'

        get_connection_type.side_effect = lambda x: (
            TCP_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        getpwuid.side_effect = lambda x: Mock(pw_name=logged_in_user)
        client = LitpRestClient()
        result = client.get_https_connection()
        self.assertTrue(result.__class__ == httplib.HTTPSConnection)

    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_litprc_and_connection_type_unix(
        self, get_connection_type, read_litprc):
        litprc_data_path = 'path/to/socket'
        litprc_data = LitprcConfig(path=litprc_data_path)

        get_connection_type.side_effect = lambda x: (
            UNIX_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        client = LitpRestClient()
        result = (client.connection_type, client.unix_socket_path)

        expected = (UNIX_CONNECTION, litprc_data_path)
        self.assertEqual(expected, result)

    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_litprc_and_connection_type_tcp(
        self, get_connection_type, read_litprc):
        litprc_data_path = 'path/to/tcp'
        litprc_data = LitprcConfig(path=litprc_data_path)
        litprc_data['username'] = 'litp_username'
        litprc_data['password'] = 'litp_password'

        get_connection_type.side_effect = lambda x: (
            TCP_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        client = LitpRestClient()
        result = (client.connection_type, client.unix_socket_path)

        expected = (TCP_CONNECTION, litprc_data_path)
        self.assertEqual(expected, result)

    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    @patch.object(LitpRestClient, 'RETRY_INTERVAL', 1)
    @patch.object(LitpRestClient, 'MAX_ATTEMPTS', 1)
    def test_get_litprc_and_connection_type_tcp_no_litprc(
        self, get_connection_type, read_litprc):
        litprc_data_path = 'path/to/tcp'
        litprc_data = LitprcConfig(path=litprc_data_path)
        litprc_data.file_missing = True

        get_connection_type.side_effect = lambda x: (
            TCP_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        with self.assertRaises(IOError):
            LitpRestClient()

    @patch('h_litp.litp_rest_client.pwd.getpwuid')
    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_auth_header_unix_connection(
        self, get_connection_type, read_litprc, getpwuid):
        litprc_data_path = 'path/to/socket'
        litprc_data = LitprcConfig(path=litprc_data_path)

        logged_in_user = 'logged_in_user'

        get_connection_type.side_effect = lambda x: (
            UNIX_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        getpwuid.side_effect = lambda x: Mock(pw_name=logged_in_user)

        client = LitpRestClient()
        result = client.auth_header

        test_input = logged_in_user + ':' + ''
        expected = 'Basic ' + encodestring(test_input).strip()
        self.assertEqual(expected, result.get('Authorization'))

    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_auth_header_tcp_no_password(
        self, get_connection_type, read_litprc):
        litprc_data_path = 'path/to/tcp'
        litprc_data = LitprcConfig(path=litprc_data_path)
        litprc_data['username'] = 'litp_username'

        get_connection_type.side_effect = lambda x: (
            TCP_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data
        with self.assertRaises(LitpException) as le:
            client = LitpRestClient()
            self.assertEqual(
                "No password entry in %s file" % litprc_data_path,
                le.exception)
            self.assertEqual(le.error_code, 1)

    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_auth_header_tcp_no_username(
        self, get_connection_type, read_litprc):
        litprc_data_path = 'path/to/tcp'
        litprc_data = LitprcConfig(path=litprc_data_path)
        litprc_data['password'] = 'litp_password'

        get_connection_type.side_effect = lambda x: (
            TCP_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        with self.assertRaises(LitpException) as le:
            client = LitpRestClient()
            self.assertEqual(
                "No username entry in %s file" % litprc_data_path,
                le.exception)
            self.assertEqual(le.error_code, 1)

    @patch('h_litp.litp_rest_client.read_litprc')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_auth_header_tcp_username_password(
        self, get_connection_type, read_litprc):
        litprc_data_path = 'path/to/tcp'
        litprc_data = LitprcConfig(path=litprc_data_path)
        litprc_data['username'] = 'litp_username'
        litprc_data['password'] = 'litp_password'

        get_connection_type.side_effect = lambda x: (
            TCP_CONNECTION, litprc_data_path)
        read_litprc.side_effect = lambda: litprc_data

        client = LitpRestClient()
        result = client.auth_header

        test_input = litprc_data.get('username') + ':' + \
            litprc_data.get('password')
        expected = 'Basic ' + encodestring(test_input).strip()
        self.assertEqual(expected, result.get('Authorization'))


class TestLitpClient(TestCase):
    litp_client = 'litp-client'
    litp_username = 'litp-admin'
    litp_password = '4lackwar31'

    litprc_data = {litp_client: {
        'username': litp_username,
        'password': litp_password
    }}

    if 'HOME' in os.environ:
        _home = os.environ['HOME']
    else:
        _home = os.environ['USERPROFILE']
    litprc = join(_home, '.litprc')

    def setUp(self):
        f = open(self.litprc, 'w')
        for key, data in self.litprc_data.items():
            f.write('[{0}]\n'.format(key))
            for k, v in data.items():
                f.write('{0} = {1}\n'.format(k, v))
        f.close()

        self.old_stdout = sys.stdout
        sys.stdout = self.stdout = StringIO()

        self.old_stderr = sys.stderr
        sys.stderr = self.stderr = StringIO()

    def tearDown(self):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr

    def assertAllCalled(self, client):
        if not client.get_https_connection().was_all_called():
            self.fail(
                    'Not all http requests called {0}'.format(
                            client.https.expected_responses))

    def test_get_https_connection(self):
        pass

    def test_value_error(self):
        """
        TORF-48542
        :return:
        """
        client = LitpRestClient()
        non_json = 'ha....hahahah'
        setup_mock(client, [
            ['GET', non_json, httplib.OK]
        ])
        get_result = client.https_request('GET', '')
        self.assertEqual(non_json, get_result)

    def test_request_result_BAD_REQUEST(self):
        client = LitpRestClient()
        http_response = MagicMock()
        http_response.status = httplib.BAD_REQUEST
        http_response.read.side_effect = ['Error message']
        try:
            client._request_result(http_response, '/path')
            self.fail('Expected a LitpException to be thrown!')
        except LitpException as error:
            self.assertEqual(error.args[0], httplib.BAD_REQUEST)
            self.assertEqual(error.args[1], 'Error message')

    def test_request_result_UNAUTHORIZED(self):
        client = LitpRestClient()
        http_response = MagicMock()
        http_response.status = httplib.UNAUTHORIZED
        http_response.read.side_effect = ['Error message']
        try:
            client._request_result(http_response, '/path')
            self.fail('Expected a LitpException to be thrown!')
        except LitpException as error:
            self.assertEqual(error.args[0], httplib.UNAUTHORIZED)
            self.assertEqual(error.args[1], 'Unauthorized access')

    def test_request_result_litp_fmt_errors(self):
        client = LitpRestClient()
        http_response = MagicMock()
        http_response.status = httplib.NOT_FOUND
        http_response.reason = 'Not Found'
        http_response.getheader.side_effect = [
            LitpRestClient.CONTENT_TYPE_JSON]
        error_data = {'messages': [
            {'type': 'InvalidLocationError', 'message': 'Not found',
             '_links': {'self': {
                 'href': 'https://localhost:9999/litp/rest/v1/path'}}}],
            '_links': {'self': {
                'href': 'https://localhost:9999/litp/rest/v1/path'}}}
        http_response.read.side_effect = [dumps(error_data)]
        try:
            client._request_result(http_response, '/path')
            self.fail('Expected a LitpException to be thrown!')
        except LitpException as error:
            self.assertEqual(error.args[0], httplib.NOT_FOUND)
            self.assertTrue(type(error.args[1] is dict))
            self.assertEqual(error.args[1]['path'], '/path')
            self.assertEqual(error.args[1]['reason'], 'Not Found')
            self.assertEqual(error.args[1]['messages'], error_data['messages'])

    def test_request_result_unknown_fmt_errors(self):
        client = LitpRestClient()
        http_response = MagicMock()
        http_response.status = httplib.NOT_FOUND
        http_response.reason = 'Generic Error!'
        http_response.getheader.side_effect = [
            LitpRestClient.CONTENT_TYPE_JSON]
        error_data = 'Some unknown error!'
        http_response.read.side_effect = [error_data]
        try:
            client._request_result(http_response, '/path')
            self.fail('Expected a LitpException to be thrown!')
        except LitpException as error:
            self.assertEqual(error.args[0], httplib.NOT_FOUND)
            self.assertTrue(type(error.args[1] is dict))
            self.assertEqual(error.args[1]['path'], '/path')
            self.assertEqual(error.args[1]['reason'], 'Generic Error!')
            self.assertListEqual([error_data], error.args[1]['messages'])

    @patch('h_litp.litp_rest_client.LitpRestClient.get_deployment_clusters')
    def test_get_deployment_clusters_2_clusters(self, m_get_deployment_clusters):
        m_get_deployment_clusters.return_value = {u'enm': [u'svc_cluster', u'db_cluster']}
        expected_list = [u'svc_cluster', u'db_cluster']
        client = LitpRestClient()
        self.assertEquals(expected_list, client.get_deployment_cluster_list())

    @patch('h_litp.litp_rest_client.LitpRestClient.get_deployment_clusters')
    def test_get_deployment_clusters_no_clusters(self, m_get_deployment_clusters):
        m_get_deployment_clusters.return_value = {u'enm': []}
        expected_list = []
        client = LitpRestClient()
        self.assertEquals(expected_list, client.get_deployment_cluster_list())

    def test_get(self):
        client = LitpRestClient()
        data = {'name1': 'value1'}
        setup_mock(client, [
            ['GET', dumps(data), httplib.OK]
        ])
        response = client.get('/abc')
        self.assertAllCalled(client)
        self.assertDictEqual(data, response)

        setup_mock(client, [
            ['GET', dumps({'messages': 'not found'}), httplib.NOT_FOUND]
        ])
        self.assertRaises(LitpException, client.get, '/abc')

    def test_create_plan(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['POST', dumps({}), httplib.OK]
        ])
        client.create_plan('plan')
        self.assertAllCalled(client)

    def test_restore_model(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['PUT', dumps({}), httplib.OK]
        ])
        client.restore_model()
        self.assertAllCalled(client)

    def test_set_plan_state(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['PUT', dumps({}), httplib.OK]
        ])
        client.set_plan_state('plan', 'started')
        self.assertAllCalled(client)

    def test_get_plan_state(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['GET', dumps({'properties': {'state': 'OK'}}), httplib.OK]
        ])
        client.get_plan_state('plan')
        self.assertAllCalled(client)

    def test_set_debug(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['PUT', dumps({}), httplib.OK]
        ])
        client.set_debug('override')
        self.assertAllCalled(client)

    def test_upgrade(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['POST', dumps({}), httplib.OK]
        ])
        client.upgrade('deployment/enm')
        self.assertAllCalled(client)

    def test_export_model_to_xml(self):
        model = join(gettempdir(), 'exported_model.xml')
        client = LitpRestClient()
        data = '{gobbledygook}'

        try:
            setup_mock(client, [
                ['GET', dumps({}), httplib.OK],
                ['GET', dumps(data), httplib.OK,
                 LitpRestClient.CONTENT_TYPE_XML]])
            client.export_model_to_xml(xml_output_file=model)
            self.assertTrue(os.path.exists(model))
            result = open(model).read()
            result = re.sub('\"', '', result)
            self.assertEqual(data, result)
            self.assertAllCalled(client)
        finally:
            if exists(model):
                os.remove(model)

        setup_mock(client, [
            ['GET', dumps({}), httplib.NOT_FOUND]
        ])

        self.assertRaises(LitpException, client.export_model_to_xml,
                          os.path.abspath(model), model_path='blah')

    def test_get_children(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['GET', dumps({}), httplib.OK]
        ])
        children = client.get_children('/a')
        self.assertAllCalled(client)
        self.assertFalse(children)

        data = {'_embedded': {'item': [
            {'id': 'c1'},
            {'id': 'c2'}
        ]}}
        expected_children = ['/a/c1', '/a/c2']
        setup_mock(client, [
            ['GET', dumps(data), httplib.OK]
        ])
        children = client.get_children('/a')
        self.assertAllCalled(client)
        self.assertTrue(len(children) == 2)
        for child in children:
            self.assertTrue(child['path'] in expected_children)

    def test_get_plan_status(self):
        client = LitpRestClient()

        data_phases = {'_embedded': {'item': [
            {'id': '1'},
            {'id': '2'}
        ]}}
        data_1_tasks = {'_embedded': {'item': [
            {'id': 'task_a'},
            {'id': 'task_b'}
        ]}}
        data_1_task_1 = {'state': 'state_a',
                         'description': 'description'}
        data_1_task_2 = {'state': 'state_b',
                         'description': 'description'}
        data_2_tasks = {'_embedded': {'item': [
            {'id': 'task_c'},
            {'id': 'task_d'}
        ]}}
        data_2_task_1 = {'state': 'state_c',
                         'description': 'description'}
        data_2_task_2 = {'state': 'state_d',
                         'description': 'description'}
        setup_mock(client, [
            ['GET', dumps(data_phases), httplib.OK],
            ['GET', dumps(data_1_tasks), httplib.OK],
            ['GET', dumps(data_1_task_1), httplib.OK],
            ['GET', dumps(data_1_task_2), httplib.OK],
            ['GET', dumps(data_2_tasks), httplib.OK],
            ['GET', dumps(data_2_task_1), httplib.OK],
            ['GET', dumps(data_2_task_2), httplib.OK]
        ])
        status = client.get_plan_status('plan')
        self.assertAllCalled(client)
        # There are 4 tasks defined above (in 2 phases)"
        self.assertTrue(len(status) == 4)
        api_path = []
        for task in status:
            api_path.append(task['path'])

        self.assertIn('/plans/plan/phases/1/tasks/task_a', api_path)
        self.assertEqual(status[0]['state'], 'state_a')
        self.assertIn('/plans/plan/phases/1/tasks/task_b', api_path)
        self.assertEqual(status[1]['state'], 'state_b')
        self.assertIn('/plans/plan/phases/2/tasks/task_c', api_path)
        self.assertEqual(status[2]['state'], 'state_c')
        self.assertIn('/plans/plan/phases/2/tasks/task_d', api_path)
        self.assertEqual(status[3]['state'], 'state_d')

    def test_load_xml(self):
        f = join(gettempdir(), 'model.xml')
        with open(f, 'w+') as _f:
            _f.writelines('')
        client = LitpRestClient()

        self.assertRaises(LitpException, client.load_xml, '', 'b.xml')

        setup_mock(client, [
            ['POST', dumps(''), httplib.OK]
        ])
        client.load_xml('/', f)
        self.assertAllCalled(client)

    def test_is_plan_running(self):
        test_data = {
            'item-type-name': 'plan',
            'id': 'plan',
            'properties': {
                'state': ''
            }
        }

        def assert_running_state(plan_state, litp_api, is_running):
            test_data['properties']['state'] = plan_state
            setup_mock(litp_api, [
                ['GET', dumps({}), httplib.OK],
                ['GET', dumps(test_data), httplib.OK]
            ])
            if is_running:
                self.assertTrue(litp_api.is_plan_running('plan'))
            else:
                self.assertFalse(litp_api.is_plan_running('plan'))

        client = LitpRestClient()
        assert_running_state('Initial', client, False)
        assert_running_state('initial', client, False)
        assert_running_state('Failed', client, False)
        assert_running_state('stopping', client, True)
        assert_running_state('running', client, True)

        # TORF-70691
        setup_mock(client, [
            ['GET',
             dumps({
                 'path': '/plans/plan',
                 'reason': 'Not Found',
                 'messages': [
                     {
                         'type': 'InvalidLocationError',
                         'message': 'Plan does not exist',
                         '_links': {
                             'self': {
                                 'href':
                                     'https://1.1.1.1:9999/litp/rest/v1/plans'
                             }
                         }
                     }
                 ]
             }),
             httplib.NOT_FOUND,
             'Not Found']
        ])
        self.assertFalse(client.is_plan_running('plan'))

    def test_get_key_value_no_message_dictionary(self):

        le = LitpException()
        self.assertFalse(
                le.get_key_value(key='a', value='b'))

    def test_get_key_value_no_iterable(self):

        le = LitpException(IOError, httplib.UNPROCESSABLE_ENTITY)
        self.assertFalse(
                le.get_key_value(key='a', value='b'))

    def test_get_key_value_no_messages(self):

        le = LitpException(IOError, {'errors': []})
        self.assertFalse(
                le.get_key_value(key='a', value='b'))

    def test_get_key_value_messages_l1(self):

        le = LitpException(IOError, {'messages': []})
        self.assertFalse(
                le.get_key_value(key='a', value='b'))

    def test_get_key_value_messages_empty(self):

        le = LitpException(IOError, {'messages': [
            {'message': 'Create plan failed: no tasks were generated'}]})
        self.assertFalse(
                le.get_key_value(key='a', value='b'))

    def test_get_key_value(self):
        exp = 'DoNothingPlanError'

        message_create_plan_failed = 'Create plan failed: no tasks were ' \
                                     'generated'
        le = LitpException(IOError, {'messages': [
            {'message': message_create_plan_failed,
             'type': exp}]})

        self.assertTrue(le.get_key_value(key='type', value=exp))
        message_extracted = le.get_message_from_messages('message')
        self.assertEqual(message_extracted, message_create_plan_failed)

    def test_exists(self):
        client = LitpRestClient()
        setup_mock(client, [
            ['GET', dumps({}), httplib.OK]
        ])
        self.assertTrue(client.exists('/blaa'))

        setup_mock(client, [
            ['GET', dumps({}), httplib.NOT_FOUND]
        ])
        self.assertFalse(client.exists('/blaa'))

        setup_mock(client, [
            ['GET', dumps({}), httplib.FORBIDDEN]
        ])
        self.assertRaises(LitpException, client.exists, '')

    def test_update(self):
        mp = "/deployment/test"
        prop = {'[abc]': '123'}
        client = LitpRestClient()
        setup_mock(client, [
            ['PUT', dumps({}), httplib.OK]
        ])
        client.update(mp, prop, verbose=True)
        self.assertAllCalled(client)

    @patch('h_litp.litp_rest_client.LitpObject')
    def test_delete_property(self, litp_obj):
        mp = "/deployment/test"
        prop = 'abc'
        client = LitpRestClient()
        # Path not found
        setup_mock(client, [
            ['GET', dumps({}), httplib.NOT_FOUND],
        ])
        result = client.delete_property(mp, prop)
        self.assertFalse(result)
        self.assertAllCalled(client)
        # Path exists and property deleted
        setup_mock(client, [
            ['GET', dumps({}), httplib.OK],
            ['GET', dumps({}), httplib.OK],
            ['PUT', dumps({}), httplib.OK]
        ])
        litp_obj.return_value = MagicMock()
        litp_obj.return_value.get_property.return_value = '123'
        result = client.delete_property(mp, prop)
        self.assertTrue(result)
        self.assertAllCalled(client)
        # Path exists and property not found
        setup_mock(client, [
            ['GET', dumps({}), httplib.OK],
            ['GET', dumps({}), httplib.OK],
        ])
        litp_obj.return_value = MagicMock()
        litp_obj.return_value.get_property.return_value = ''
        result = client.delete_property(mp, prop)
        self.assertFalse(result)
        self.assertAllCalled(client)

    def test_delete_path(self):
        path = "/deployment/test"
        client = LitpRestClient()
        # Path exists and get deleted
        setup_mock(client, [
            ['GET', dumps({}), httplib.OK],
            ['DELETE', dumps({}), httplib.OK]
        ])
        result = client.delete_path(path)
        self.assertTrue(result)
        self.assertAllCalled(client)
        # Path not found
        setup_mock(client, [
            ['GET', dumps({}), httplib.NOT_FOUND]
        ])
        result = client.delete_path(path)
        self.assertFalse(result)
        self.assertAllCalled(client)

    def test_create(self):
        client = LitpRestClient()

        setup_mock(client, [
            ['GET', dumps({}), httplib.NOT_FOUND],
            ['POST', dumps({}), httplib.OK]
        ])
        created = client.create('/parent', 'new', 'itemtype', {'a': 'b'})
        self.assertEqual('/parent/new', created)

        setup_mock(client, [
            ['GET', dumps({}), httplib.NOT_FOUND],
            ['POST', dumps({}), httplib.BAD_REQUEST]
        ])
        self.assertRaises(LitpException, client.create, '/abc', 'node_name',
                          'node_type')

        setup_mock(client, [
            ['GET', dumps({}), httplib.OK]
        ])
        self.assertRaises(LitpException, client.create, '/abc', 'node_name',
                          'node_type')

    def test_inherit(self):
        client = LitpRestClient()

        setup_mock(client, [
            ['POST', dumps({}), httplib.OK]
        ])
        try:
            client.inherit('/a/b', '/i/b', {})
        except Exception as e:
            self.fail('Failed to inherit: {0}'.format(str(e)))

        setup_mock(client, [
            ['POST', dumps({}), httplib.BAD_REQUEST]
        ])
        self.assertRaises(LitpException, client.inherit, '/a', '/b')

    def test_remove_snapshot(self):
        remove_response = {"item-type-name": "plan",
                           "_embedded": {"item": []},
                           "id": "plan", "properties": {"state": "initial"}}
        test_client = LitpRestClient()
        setup_mock(test_client, [
            ['PUT', dumps(remove_response), httplib.OK]
        ])
        test_client.remove_snapshot()
        self.assertAllCalled(test_client)

        setup_mock(test_client, [
            ['PUT', dumps({}), httplib.BAD_REQUEST]
        ])
        self.assertRaises(LitpException, test_client.remove_snapshot)

    def test_create_snapshot(self):
        create_response = {"item-type-name": "plan",
                           "_embedded": {"item": []},
                           "id": "plan", "properties": {"state": "initial"}}
        test_client = LitpRestClient()
        setup_mock(test_client, [
            ['POST', dumps(create_response), httplib.OK]
        ])
        test_client.create_snapshot()
        self.assertAllCalled(test_client)

        setup_mock(test_client, [
            ['POST', dumps({}), httplib.BAD_REQUEST]
        ])
        self.assertRaises(LitpException, test_client.create_snapshot)

    def test_restore_snapshot(self):
        restore_response = {"item-type-name": "plan",
                            "_embedded": {"item": []},
                            "id": "plan", "properties": {"state": "initial"}}
        test_client = LitpRestClient()
        setup_mock(test_client, [
            ['PUT', dumps(restore_response), httplib.OK]
        ])
        test_client.restore_snapshot()
        self.assertAllCalled(test_client)

        setup_mock(test_client, [
            ['PUT', dumps({}), httplib.BAD_REQUEST]
        ])
        self.assertRaises(LitpException, test_client.restore_snapshot)

    def test_get_items_by_type(self):
        mock_model = {
            '/deployments': [
                {'path': '/deployments/enm', 'data':
                    get_node_json('deployments', 'enm', 'Applied',
                                  '/deployments/enm')}],
            '/deployments/enm': [
                {'path': '/deployments/enm/clusters', 'data':
                    get_node_json('collection-of-cluster', 'clusters',
                                  'Applied', '/deployments/enm/clusters')}
            ],
            '/deployments/enm/clusters': [
                {'path': '/deployments/enm/clusters/db', 'data':
                    get_node_json('deployment', 'db', 'Applied',
                                  '/deployments/enm/clusters/db')},
                {'path': '/deployments/enm/clusters/svc', 'data':
                    get_node_json('deployment', 'svc', 'Applied',
                                  '/deployments/enm/clusters/svc')}
            ],
            '/deployments/enm/clusters/db': [
                {'path': '/deployments/enm/clusters/db/nodes', 'data':
                    get_node_json('collection-of-nodes', 'nodes', 'Applied',
                                  '/deployments/enm/clusters/db/nodes')}
            ],
            '/deployments/enm/clusters/svc': [
                {'path': '/deployments/enm/clusters/svc/nodes', 'data':
                    get_node_json('collection-of-nodes', 'nodes', 'Applied',
                                  '/deployments/enm/clusters/svc/nodes')}
            ],
            '/deployments/enm/clusters/db/nodes': [
                {'path': '/deployments/enm/clusters/db/nodes/dbn1', 'data':
                    get_node_json('node', 'dbn1', 'Applied',
                                  '/deployments/enm/clusters/db/nodes/dbn1',
                                  properties={'hostname': 'hdbn1'})},
                {'path': '/deployments/enm/clusters/db/nodes/dbn2', 'data':
                    get_node_json('node', 'dbn2', 'Applied',
                                  '/deployments/enm/clusters/db/nodes/dbn2',
                                  properties={'hostname': 'hdbn2'})}
            ],
            '/deployments/enm/clusters/svc/nodes': [
                {'path': '/deployments/enm/clusters/svc/nodes/svcn1', 'data':
                    get_node_json('node', 'svcn1', 'Applied',
                                  '/deployments/enm/clusters/svc/nodes/svcn1',
                                  properties={'hostname': 'svcn1'})}
            ]
        }

        def mock_get_children(path):
            return mock_model[path]

        test_client = LitpRestClient()
        test_client.get_children = mock_get_children

        matching_items = []
        test_client.get_items_by_type('/deployments', 'deployments',
                                      matching_items)
        self.assertEqual(1, len(matching_items))
        self.assertIn('/deployments/enm', matching_items[0]['path'])

        matching_items = []
        test_client.get_items_by_type('/deployments', 'node', matching_items)
        self.assertEqual(3, len(matching_items))

        for mpath in ['/deployments/enm/clusters/db/nodes/dbn1',
                      '/deployments/enm/clusters/db/nodes/dbn2',
                      '/deployments/enm/clusters/svc/nodes/svcn1']:
            found = False
            for entry in matching_items:
                if entry['path'] == mpath:
                    found = True
                    break
            self.assertTrue(found, 'Path {0} was not found!'.format(mpath))

        test_client.get_children = MagicMock()
        test_client.get_children.side_effect = LitpException(
                'This is expected')
        self.assertRaises(LitpException, test_client.get_items_by_type,
                          '/path', 'node', matching_items)


class TestLitpObject(TestCase):
    def test_con(self):
        litp = LitpRestClient()
        data = get_node_json('deployment', 'enm', 'Applied',
                             '/deployments/enm',
                             properties={'p1': 'v1', 'enabled': 'true'},
                             children={
                                 'clusters': '/deployments/enm/clusters'})
        obj = LitpObject(None, data, litp.path_parser)
        self.assertEqual('/deployments/enm', obj.path)
        self.assertFalse(obj.is_task)
        self.assertIsNone(obj.task_item)
        self.assertIsNone(obj.parent)
        self.assertEqual('Applied', obj.state)
        self.assertEqual('enm', obj.item_id)
        self.assertEqual('deployment', obj.item_type)
        self.assertEqual(1, len(obj.children))
        self.assertIn('clusters', obj.children)
        self.assertTrue(type(obj.children['clusters'] is LitpObject))
        self.assertIsNone(obj.description)
        self.assertTrue('/deployments/enm' in str(obj))

        self.assertEqual('v1', obj.get_property('p1'))
        self.assertIsNone(obj.get_property('p2'))
        self.assertTrue(obj.get_bool_property("enabled"))
        ve1 = assert_exception_raised(ValueError, obj.get_bool_property, "p2")
        self.assertTrue("No value defined for property p2" in str(ve1))
        ve2 = assert_exception_raised(ValueError, obj.get_bool_property, "p1")
        self.assertTrue("No expected JSON boolean value" in str(ve2))

        del data['state']
        data['description'] = 'description'
        data['properties']['state'] = 'Failed'
        obj = LitpObject(None, data, litp.path_parser)
        self.assertEqual('Failed', obj.state)
        self.assertEqual('description', obj.description)

        data['_links']['rel'] = {'href': 'https://localhost:9999/litp/rest/v1'
                                         '/a/b/c'}
        data['item-type-name'] = 'task'
        obj = LitpObject(None, data, litp.path_parser)
        self.assertEqual('/a/b/c', obj.task_item)

    def test_get_properties(self):
        litp = LitpRestClient()
        data = get_node_json('deployment', 'enm', 'Applied',
                             '/deployments/enm',
                             properties={'p1': 'v1', 'enabled': 'true'},
                             children={
                                 'clusters': '/deployments/enm/clusters'})
        obj = LitpObject(None, data, litp.path_parser)
        self.assertEqual('v1', obj.get_property('p1'))
        self.assertIsNone(obj.get_property('none'))
        self.assertEqual('default', obj.get_property('none', 'default'))

        data = get_node_json('deployment', 'enm', 'Applied',
                             '/deployments/enm',
                             children={
                                 'clusters': '/deployments/enm/clusters'})
        obj = LitpObject(None, data, litp.path_parser)
        self.assertIsNone(obj.get_property('none'))
        self.assertEqual('default', obj.get_property('none', 'default'))


class TestPlanMonitor(TestCase):
    @patch('h_litp.litp_rest_client.LitpRestClient')
    @patch('h_litp.litp_rest_client.init_enminst_logging')
    def test_monitorinfo(self, miel, litp):
        mlog = MagicMock()
        miel.side_effect = [mlog]

        pm = PlanMonitor()
        pm.monitorinfo('abc')
        mlog.assert_has_calls([call.info('abc')], any_order=True)

    @patch('h_litp.litp_rest_client.LitpRestClient')
    @patch('h_litp.litp_rest_client.init_enminst_logging')
    def test_error(self, miel, litp):
        mlog = MagicMock()
        miel.side_effect = [mlog]

        pm = PlanMonitor()
        pm.error('abc')
        mlog.assert_has_calls([call.error('abc')], any_order=True)

    @patch('h_litp.litp_rest_client.Formatter.format_color')
    def test_merge_model(self, m_format_color):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo

        litp = LitpRestClient()
        pm = PlanMonitor(litp, verbose=True)

        data = get_json('phase_tasks.json')

        phases = LitpObject(None, data, litp.path_parser)
        pm.merge_model(phases)
        self.assertEqual(1, len(pm.phases))
        self.assertListEqual(['1'], pm.get_phase_ids())
        self.assertIn('/plans/plan/phases/1', pm.phases)
        self.assertEqual(2, len(pm.phase_tasks['1']))
        self.assertEqual([1], pm.get_active_phases())
        self.assertListEqual(['task_1', 'task_2'], pm.get_phase_tasks_ids('1'))

        self.assertEqual('task_1', pm.get_phase_task('1', 'task_1').item_id)
        self.assertEqual('task_2', pm.get_phase_task('1', 'task_2').item_id)

        data['_embedded']['item'][0]['_embedded']['item'][0][
            'state'] = 'Running'

        phases = LitpObject(None, data, litp.path_parser)
        mlog = MagicMock()
        pm.monitorinfo = mlog

        pm.merge_model(phases)
        mlog.assert_has_calls([call('Task: Initial>Running'),
                               call('  Item: /model/task_1'),
                               call('  Info: description task_1')])

    @patch('h_litp.litp_rest_client.LitpRestClient')
    def test_is_plan_running(self, litp):
        litp.get_plan_state.side_effect = ['Initial', 'Running']
        pm = PlanMonitor(litp)
        self.assertFalse(pm.is_plan_running())
        self.assertTrue(pm.is_plan_running())

    @patch('h_litp.litp_rest_client.Formatter.format_color')
    def test_show_failed_plan(self, m_format_color):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo

        m_t1 = MagicMock()
        m_t1.state = 'Failed'
        m_t1.task_item = 't1_item'
        m_t1.description = 'description'

        m_t2 = MagicMock()
        m_t2.state = 'Running'
        m_t2.task_item = 't2_item'
        m_t2.description = 'description'

        pm = PlanMonitor(None, verbose=True)
        pm.phase_tasks = {
            'p1': {
                't1': m_t1,
                't2': m_t2
            }
        }
        mlog = MagicMock()
        pm.monitorinfo = mlog

        pm.show_failed_plan(['1'])
        mlog.assert_has_calls([call('Phase-p1'),
                               call('Task: Failed'),
                               call('  Item: t1_item'),
                               call('  Info: description'),
                               call('Total Phases: 1 | Active Phase(s): 1 | '\
                                    'PlanState: Failed | '
                                    'TotalTasks: 0 | Initial: 0 | '
                                    'Running: 0 | Success: 0 | Failed: 0 | '
                                    'Stopped: 0')])

    @patch('h_litp.litp_rest_client.Formatter.format_color')
    def test_show_running_tasks(self, m_format_color):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo

        m_t1 = MagicMock()
        m_t1.state = 'Failed'
        m_t1.task_item = 't1_item'
        m_t1.description = 'description'

        m_t2 = MagicMock()
        m_t2.state = 'Running'
        m_t2.task_item = 't2_item'
        m_t2.description = 'description'

        pm = PlanMonitor(None)
        pm.phase_tasks = {
            'p1': {
                't1': m_t1,
                't2': m_t2
            }
        }
        mlog = MagicMock()
        pm.monitorinfo = mlog

        pm.show_running_tasks()
        mlog.assert_has_calls([call('Phase-p1'),
                               call('Task: Running'),
                               call('  Item: t2_item'),
                               call('  Info: description')])

    @patch('h_litp.litp_rest_client.LitpRestClient')
    def test_get_root(self, litp):
        litp.get.side_effect = LitpException(404, '')
        pm = PlanMonitor(litp)
        self.assertRaises(LitpException, pm.get_root, 'plan')

        litp.get.side_effect = [
            get_node_json('deployment', 'enm', 'Applied',
                          '/deployments/enm',
                          properties={'p1': 'v1'},
                          children={
                              'clusters': '/deployments/enm/clusters'})]
        root = pm.get_root('pp')
        self.assertEqual('enm', root.item_id)
        self.assertEqual(1, len(root.children))
        self.assertIn('clusters', root.children)
        self.assertTrue(type(root.children['clusters'] is LitpObject))

    @patch('h_litp.litp_rest_client.LitpRestClient')
    def test_get_root_raise(self, litp):
        litp.get.side_effect = LitpException(1, '')
        pm = PlanMonitor(litp)
        self.assertRaises(Exception, pm.get_root, 'plan')

    @patch('h_litp.litp_rest_client.PlanMonitor.log_plan')
    @patch('h_litp.litp_rest_client.PlanMonitor.monitorinfo')
    @patch('h_litp.litp_rest_client.Formatter.format_color')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_plan_monitor_running_success(self, litp_get, m_format_color,
                                          m_monitorinfo, m_log_plan):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo
        data_v1 = get_json('phase_tasks.json')
        data_v2 = get_json('phase_tasks.json')

        data_v2['_embedded']['item'][0]['_embedded']['item'][0][
            'state'] = 'Success'
        data_v2['_embedded']['item'][0]['_embedded']['item'][1][
            'state'] = 'Success'
        data_v2['state'] = 'successful'

        litp_get.get.side_effect = [data_v1, data_v2]

        pm = PlanMonitor(litp_get)
        pm.monitor_plan_progress('plan', 0)

        self.assertEqual(2, litp_get.get.call_count)
        litp_get.get.assert_has_calls([
            call('/plans/plan?recurse_depth=1000', log=False),
            call('/plans/plan?recurse_depth=1000', log=False)
        ])

        m_log_plan.assert_has_calls([call('running', active_phases=[1]),
                                     call('successful')])
        m_monitorinfo.assert_any_call('RUN_PLAN BEGIN')
        m_monitorinfo.assert_any_call('RUN_PLAN END')

    @patch('h_litp.litp_rest_client.PlanMonitor.log_plan')
    @patch('h_litp.litp_rest_client.PlanMonitor.monitorinfo')
    @patch('h_litp.litp_rest_client.Formatter.format_color')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_plan_monitor_running_failed(self, litp_get, m_format_color,
                                         m_monitorinfo, m_log_plan):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo
        data_v1 = get_json('phase_tasks.json')
        data_v2 = get_json('phase_tasks.json')

        data_v2['_embedded']['item'][0]['_embedded']['item'][0][
            'state'] = 'Success'
        data_v2['_embedded']['item'][0]['_embedded']['item'][1][
            'state'] = 'Success'
        data_v2['state'] = 'failed'

        litp_get.get.side_effect = [data_v1, data_v2]

        pm = PlanMonitor(litp_get)
        self.assertRaises(LitpException, pm.monitor_plan_progress, 'plan', 0)
        self.assertEqual(2, litp_get.get.call_count)
        litp_get.get.assert_has_calls([
            call('/plans/plan?recurse_depth=1000', log=False),
            call('/plans/plan?recurse_depth=1000', log=False)
        ])
        m_log_plan.assert_has_calls([call('running', active_phases=[1]),
                                     call('failed', active_phases=[])])
        m_monitorinfo.assert_any_call('RUN_PLAN BEGIN')
        m_monitorinfo.assert_any_call('RUN_PLAN END')

    @patch('h_litp.litp_rest_client.PlanMonitor.log_plan')
    @patch('h_litp.litp_rest_client.PlanMonitor.monitorinfo')
    @patch('h_litp.litp_rest_client.Formatter.format_color')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_plan_monitor_running_stopped(self, litp_get, m_format_color,
                                          m_monitorinfo, m_log_plan):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo
        data_v1 = get_json('phase_tasks.json')
        data_v2 = get_json('phase_tasks.json')

        data_v2['_embedded']['item'][0]['_embedded']['item'][0][
            'state'] = 'Success'
        data_v2['_embedded']['item'][0]['_embedded']['item'][1][
            'state'] = 'Success'
        data_v2['state'] = 'stopped'

        litp_get.get.side_effect = [data_v1, data_v2]

        pm = PlanMonitor(litp_get)
        self.assertRaises(LitpException, pm.monitor_plan_progress, 'plan', 0)
        self.assertEqual(2, litp_get.get.call_count)
        litp_get.get.assert_has_calls([
            call('/plans/plan?recurse_depth=1000', log=False),
            call('/plans/plan?recurse_depth=1000', log=False)
        ])
        m_log_plan.assert_has_calls([call('running', active_phases=[1]),
                                     call('stopped', active_phases=[])])
        m_monitorinfo.assert_any_call('RUN_PLAN BEGIN')
        m_monitorinfo.assert_any_call('RUN_PLAN END')

    @patch('h_litp.litp_rest_client.Formatter.format_color')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_plan_monitor_running_unknown(self, litp_get, m_format_color):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo
        data_v1 = get_json('phase_tasks.json')
        data_v2 = get_json('phase_tasks.json')

        data_v2['_embedded']['item'][0]['_embedded']['item'][0][
            'state'] = 'Success'
        data_v2['_embedded']['item'][0]['_embedded']['item'][1][
            'state'] = 'Success'
        data_v2['state'] = 'bbbbbbbbbbb'

        litp_get.get.side_effect = [data_v1, data_v2]

        pm = PlanMonitor(litp_get)
        self.assertRaises(LitpException, pm.monitor_plan_progress, 'plan', 0)
        self.assertEqual(2, litp_get.get.call_count)
        litp_get.get.assert_has_calls([
            call('/plans/plan?recurse_depth=1000', log=False),
            call('/plans/plan?recurse_depth=1000', log=False)
        ])

    @patch('h_litp.litp_rest_client.Formatter.format_color')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    def test_plan_monitor_initial_state_wait(self, litp_get, m_format_color):
        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo
        m_root_initial = MagicMock()
        m_root_initial.state = LitpRestClient.PLAN_STATE_INITIAL

        m_get_root = MagicMock()
        m_get_root.return_value = m_root_initial
        pm = PlanMonitor(litp_get)
        pm.get_root = m_get_root

        timeout = 3
        try:
            with self.assertRaises(LitpException) as ex:
                start_ts = time()
                pm.monitor_plan_progress('plan', 0, timeout)
        finally:
            end_ts = time()
        self.assertEqual(ex.exception.args[0], ExitCodes.PLAN_START_TIMEOUT)
        self.assertGreaterEqual(end_ts - start_ts, timeout)
        # asserts we're not just using the default time (300s)
        self.assertLess((end_ts - start_ts), timeout+2)

        m_get_root.reset_mock()
        m_root_running = MagicMock()
        m_root_running.state = LitpRestClient.PLAN_STATE_RUNNING
        m_root_success = MagicMock()
        m_root_success.state = LitpRestClient.PLAN_STATE_SUCCESSFUL

        m_get_root.side_effect = [m_root_initial, m_root_running,
                                  m_root_success]
        pm.monitor_plan_progress('plan', 0)
        self.assertEqual(3, m_get_root.call_count)

    @patch('h_litp.litp_rest_client.Formatter.format_color')
    @patch('h_litp.litp_rest_client.LitpRestClient.get')
    @patch.object(PlanMonitor, 'monitorinfo')
    def test_plan_monitor_many_active_phases(
                self, mock_monitorinfo, litp_get, m_format_color):
        def itemgetter(dictionary, *keys):
            result_dictionary = dictionary
            for key in keys:
                result_dictionary = result_dictionary[key]
            return result_dictionary

        def get_phases(plan_dict):
            return itemgetter(
                    data_v2, '_embedded', 'item', 0, '_embedded', 'item')

        def get_tasks(phases_dict, phase_index):
            return phases_dict[phase_index]\
                    ['_embedded']['item'][0]['_embedded']['item']

        def m_echo(_state, task_color):
            return _state

        m_format_color.side_effect = m_echo
        data_v1 = get_json('plan.json')
        data_v2 = get_json('plan.json')
        data_v3 = get_json('plan.json')

        phases = get_phases(data_v2)
        phase_0_tasks = get_tasks(phases, phase_index=0)
        phase_3_tasks = get_tasks(phases, phase_index=3)
        task0 = phase_0_tasks[0]
        task3 = phase_3_tasks[0]
        task0['state'] = 'Running'
        task3['state'] = 'Running'
        data_v2['state'] = 'running'

        data_v3['state'] = 'successful'

        litp_get.get.side_effect = [data_v1, data_v2, data_v3]

        pm = PlanMonitor(litp_get, verbose=True)
        pm.monitor_plan_progress(plan_name='plan', delay=0)

        expected_log = call.info(
            'Total Phases: 7 | Active Phase(s): 1, 4 | TotalTasks: 7 | '
            'Initial: 5 | Running: 2 | Success: 0 | Failed: 0 | Stopped: 0')
        mock_monitorinfo.assert_has_calls([expected_log], any_order=True)

    def test_plan_monitor_plan_state_changing_torf_190544(self):
        pm = PlanMonitor(self, verbose=False)

        self.assertFalse(pm.plan_state_changing(0, 0, 'Failed'))
        self.assertFalse(pm.plan_state_changing(time(), 60, 'Failed'))

        start_time = time()
        sleep(2)
        self.assertRaises(LitpException,
                          pm.plan_state_changing,
                          start_time, 1, 'Failed')

    def test_plan_monitor_monitor_plan_progress_torf_190544(self):
        pm = PlanMonitor(self, verbose=False)

        root_obj = Mock()
        root_obj.state = LitpRestClient.PLAN_STATE_FAILED

        pm.get_root = lambda x: root_obj
        pm.merge_model = lambda x, y: []
        pm.get_active_phases = pm.show_running_tasks = lambda: []

        self.assertRaises(LitpException,
                          pm.monitor_plan_progress,
                          'plan', 0, state_timeout=4, resume_plan=True)


if __name__ == '__main__':
    unittest2.main()
