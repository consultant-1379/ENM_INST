import httplib
import os
import shutil
from ConfigParser import SafeConfigParser
from datetime import datetime
from io import BytesIO
from json import dumps
from os import makedirs, remove
from os.path import exists
from os.path import join, dirname
from tempfile import gettempdir
from xml.sax import make_parser

import argparse
import unittest2
from mock import patch, MagicMock, call

import deployer
from deployer import Deployer, main
from h_litp.litp_rest_client import LitpException
from h_litp.litp_utils import UNIX_CONNECTION
from h_litp.litp_utils import main_exceptions
from h_util.h_utils import ExitCodes, touch
from h_xml.xml_parser import SAXParser
from test_h_litp.test_h_litp_rest_client import setup_mock
from test_utils import load_file_from_path

document = """\
<litp:attr id="abc">
  <first/>
  <second/>
  <third/>
</litp:attr>
"""


class TestDeployer(unittest2.TestCase):
    def __init__(self, method_name='runTest'):
        super(TestDeployer, self).__init__(method_name)
        self.tmpdir = join(gettempdir(), 'TestDeployer')
        self.tmp_version_dir = join(self.tmpdir, 'etc')
        self.cmd_file_text = load_file_from_path(
                '/test_deployer/serverfiles/cmd_file.txt')
        self.make_parser = None
        self.content_handler = None
        self.input_file = None

    def setUp(self):
        if not exists(self.tmpdir):
            makedirs(self.tmpdir)
        if not exists(self.tmp_version_dir):
            makedirs(self.tmp_version_dir)
        self.cmd_file = join(gettempdir(), 'cmd_file')
        self.write_file(self.cmd_file, self.cmd_file_text)
        basepath = dirname(dirname(dirname(__file__.replace(os.sep, '/'))))
        os.environ['ENMINST_CONF'] = join(basepath, 'src/main/resources/conf')
        os.environ['TEST_HOME'] = self.tmpdir
        self.model_xml_filename = join(self.tmpdir, 'model.xml')
        self.save_xml_file(self.model_xml_filename)
        deployer.log = MagicMock()
        deployer.config = MagicMock()

    def create_temp_file(self, contents, fname):
        scp = SafeConfigParser()
        scp.optionxform = str
        scp.readfp(BytesIO(contents))
        self.save_tmp_file(scp, fname)
        return scp

    def save_tmp_file(self, config_parser, fname):
        with open(fname, 'w') as f:
            config_parser.write(f)

    def save_xml_file(self, model_xml_file):
        self.make_parser = make_parser()
        self.content_handler = SAXParser()
        self.make_parser.setContentHandler(self.content_handler)
        self.input_file = model_xml_file
        f = open(self.input_file, 'w+')
        f.write(document)
        f.close()
        return f

    def tearDown(self):
        del os.environ['TEST_HOME']
        if exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)
        try:
            remove(self.cmd_file)
        except OSError:
            pass

    def write_file(self, location, contents):
        with open(location, 'w') as _f:
            _f.writelines(contents)

    def _patch_connection(self, m_get_connection_type):
        m_get_connection_type.side_effect = [(UNIX_CONNECTION,
                                              '/var/run/litpd/litpd.sock')]

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_litp_debug_enable(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        with patch('h_litp.litp_rest_client.LitpRestClient.set_debug') as mock:
            test_deployer.enable_litp_debug()
            self.assertTrue(mock.called)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_litp_debug_reset(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        with patch('h_litp.litp_rest_client.LitpRestClient.set_debug') as mock:
            test_deployer.reset_litp_debug()
            self.assertTrue(mock.called)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_run_plan(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        with patch('h_litp.litp_rest_client.'
                   'LitpRestClient.set_plan_state') as mock:
            mock.set_plan_state.return_value = 0
            test_deployer.run_plan()
            self.assertTrue(mock.called,
                            'Expected a litp.set_plan_state() call!')

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_wait_plan_complete(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        with patch('h_litp.litp_rest_client.'
                   'LitpRestClient.monitor_plan') as mock:
            mock.wait_plan_complete.return_value = 0
            test_deployer.wait_plan_complete()
            self.assertTrue(mock.called,
                            'Expected a litp.wait_plan_complete() call!')

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_load_xml(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        with patch('h_litp.litp_rest_client.LitpRestClient.load_xml') as mock:
            mock.load_xml.return_value = 0
            test_deployer.load_xml('a', 'b')
            self.assertTrue(mock.called, 'Expected a litp.load_xml() call!')

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('deployer.logging.getLogger')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_load_xml_exception(self, m_get_connection_type, m_getlogger,
                                m_pwd, m_os):
        self._patch_connection(m_get_connection_type)

        m_logger = MagicMock()
        m_getlogger.side_effect = m_logger

        test_deployer = Deployer()

        litp_error = {'messages': [{'_links': {'self': {
            'href': 'https://localhost:9999/litp/xml/path_1'}},
            'message': 'This is a validation error.',
            'type': 'ValidationError',
            'uri': '/path_1',
            'error': 'ValidationError'},
            {'_links': {'self': {
                'href': 'https://localhost:9999/litp/xml/path_2'}},
                'message': 'Another error!',
                'type': 'ValidationError',
                'uri': '/path_2',
                'error': 'ValidationError'}
        ], '_links': {'self': {'href': 'https://localhost:9999/litp/xml/'}}}

        tmpfile = join(gettempdir(), 'somefile.xml')
        touch(tmpfile)

        try:
            setup_mock(test_deployer.litp, [
                ['POST', dumps(litp_error), httplib.UNPROCESSABLE_ENTITY]
            ])
            with self.assertRaises(SystemExit) as sysexit:
                test_deployer.load_xml('/', tmpfile)
            self.assertEqual(sysexit.exception.code, ExitCodes.LOAD_PLAN_FAILED)

            m_logger.assert_has_calls([
                call().error('This is a validation error. /path_1'),
                call().error('Another error! /path_2')
            ], any_order=True
            )
        finally:
            if exists(tmpfile):
                remove(tmpfile)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('deployer.logging.getLogger')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_load_xml_unknown_litp_exception(self, m_get_connection_type,
                                             m_getlogger, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)

        m_logger = MagicMock()
        m_getlogger.side_effect = m_logger

        test_deployer = Deployer()

        tmpfile = join(gettempdir(), 'somefile.xml')
        touch(tmpfile)

        try:
            setup_mock(test_deployer.litp, [
                ['POST', dumps('Some error!'), httplib.UNPROCESSABLE_ENTITY]
            ])

            with self.assertRaises(SystemExit) as sysexit:
                test_deployer.load_xml('/', tmpfile)
            self.assertEqual(sysexit.exception.code,
                             ExitCodes.LOAD_PLAN_FAILED)
            m_logger.assert_has_calls([call().error('"Some error!"')],
                                      any_order=True)
        finally:
            if exists(tmpfile):
                remove(tmpfile)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.LitpRestClient.load_xml')
    @patch('deployer.logging.getLogger')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_load_xml_unknown_exception_str(self, m_get_connection_type,
                                            m_getlogger, m_load_xml,
                                            m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        m_load_xml.side_effect = LitpException(1, 'Some unknown error')

        m_logger = MagicMock()
        m_getlogger.side_effect = m_logger

        test_deployer = Deployer()

        tmpfile = join(gettempdir(), 'somefile.xml')
        touch(tmpfile)

        try:
            with self.assertRaises(SystemExit) as sysexit:
                test_deployer.load_xml('/', tmpfile)
            self.assertEqual(sysexit.exception.code,
                             ExitCodes.LOAD_PLAN_FAILED)
            m_logger.assert_has_calls([
                call().error('Some unknown error'),
                call().error('Failed to load {0} into /'.format(tmpfile))],
                    any_order=True)

        finally:
            if exists(tmpfile):
                remove(tmpfile)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.LitpRestClient.load_xml')
    @patch('deployer.logging.getLogger')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_load_xml_unknown_exception_dict(self, m_get_connection_type,
                                             m_getlogger, m_load_xml,
                                             m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        m_load_xml.side_effect = LitpException(1,
                                               {'key': 'Some unknown error'})

        m_logger = MagicMock()
        m_getlogger.side_effect = m_logger

        test_deployer = Deployer()

        tmpfile = join(gettempdir(), 'somefile.xml')
        touch(tmpfile)

        try:
            with self.assertRaises(SystemExit) as sysexit:
                test_deployer.load_xml('/', tmpfile)
            self.assertEqual(sysexit.exception.code,
                             ExitCodes.LOAD_PLAN_FAILED)
            m_logger.assert_has_calls([
                call().error('\tkey -> Some unknown error\n')],
                    any_order=True)

        finally:
            if exists(tmpfile):
                remove(tmpfile)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_create_plan(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        with patch('h_litp.litp_rest_client.'
                   'LitpRestClient.create_plan') as mock:
            mock.create_plan.return_value = 0
            test_deployer.create_plan()
            self.assertTrue(mock.called,
                            'Expected a litp.create_plan() call!')

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    @patch('h_litp.litp_rest_client.LitpRestClient.create_plan')
    def test_create_plan_exception(self, m_create_plan, m_get_connection_type,
                                   m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        test_deployer = Deployer()
        m_create_plan.side_effect = LitpException(1, {})
        self.assertRaises(SystemExit, test_deployer.create_plan)
        m_create_plan.side_effect = \
            LitpException(422, {'path': '/plans', 'reason': '',
                                'messages':
                                    [{'type': 'ValidationError',
                                      'message': 'Create plan failed: IP'
                                                 ' address "10.141.1.43"'
                                                 ' not within subnet".',
                                      '_links': {'self': {
                                          'href': 'https://127.0.0.1'
                                                  ':9999/litp/rest/v1'
                                                  '/ms/network_'
                                                  'interfaces/eth1'}}}]})

        with self.assertRaises(SystemExit) as sysexit:
            test_deployer.create_plan()
        self.assertEqual(sysexit.exception.code, ExitCodes.CREATE_PLAN_FAILED)

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_get_error_msg_from_exception(self, m_get_connection_type, _, __):
        self._patch_connection(m_get_connection_type)
        d = Deployer()

        # error with HAL response
        err = {'type': 'ValidationError',
              'message': 'Create plan failed: IP'
                         ' address "10.141.1.43"'
                         ' not within subnet".',
              '_links': {'self': {
                  'href': 'https://127.0.0.1'
                          ':9999/litp/rest/v1'
                          '/ms/network_'
                          'interfaces/eth1'}}}
        self.assertEqual('Create plan failed: Create plan failed: IP address '
                         '"10.141.1.43" not within subnet".',
                         d._get_error_msg_from_exception(err))

        # error with no HAL response
        err = {'message': 'Create plan failed: no tasks were generated',
               'type': 'DoNothingPlanError'}
        self.assertEqual('Create plan failed: Create plan failed: '
                         'no tasks were generated',
                         d._get_error_msg_from_exception(err))

        # hardcore error from CherryPy
        err = """Unrecoverable error in the server.\n
               Traceback (most recent call last):\n
               File "/opt/ericsson/nms/litp/3pps/lib/pytho
                n/cherrypy/_cpwsgi.py", line 169, in trap\n
               return func(*args, **kwargs)\n
               File "/opt/ericsson/nms/litp/3pps/lib/python/cherrypy/
               _cpwsgi.py", line 96, in __call__\n
               return self.nextapp(environ, start_response)\n
               File "/opt/ericsson/nms/litp/3pps/lib/python/cherryp
               y/_cpwsgi.py", line 380, in tail\n
               raise cherrypy.TimeoutError()\nTimeoutError\n"""
        self.assertEqual('Create plan failed: TimeoutError',
                         d._get_error_msg_from_exception(err))

        err = 'Some other random error coming from Cherrypy'
        self.assertEqual(err, d._get_error_msg_from_exception(err))

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    @patch('h_litp.litp_rest_client.PlanMonitor')
    def test_show_plan(self, pm, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        m_root = MagicMock()
        m_root.state = 'Initial'
        pm.return_value.get_root.return_value = m_root

        test_deployer = Deployer()
        test_deployer.show_plan()
        pm.assert_has_calls([call().log_plan('Initial')])

    def test_main_invalid_model_file(self):

        cmd_args = 'deployer.py --model_xml a/b/c.xml'

        self.assertRaises(SystemExit, main, cmd_args.split())

    @patch('h_litp.litp_rest_client.os')
    @patch('h_litp.litp_rest_client.pwd')
    @patch('h_litp.litp_rest_client.get_connection_type')
    def test_exec_time(self, m_get_connection_type, m_pwd, m_os):
        self._patch_connection(m_get_connection_type)
        d = Deployer()
        d.exec_time('TEST', datetime.now().replace(microsecond=0))

    @patch('deployer.Deployer')
    def test_main(self, deployer_mock):
        deployer.deploy(model_xml=self.model_xml_filename,
                        litpd_host='localhost',
                        verbose=False,
                        load_plan=False,
                        load_create_plan=False,
                        create_run_plan=False
                        )
        self.assertTrue(deployer_mock.return_value.load_xml.called,
                        'Expected a call to load XML!')
        self.assertTrue(deployer_mock.return_value.create_plan.called,
                        'Expected a call to create_plan()!')
        self.assertTrue(deployer_mock.return_value.run_plan.called,
                        'Expected a call to run_plan()!')
        self.assertTrue(deployer_mock.return_value.wait_plan_complete.called,
                        'Expected a call to wait_plan_complete()!')

    @patch('deployer.Deployer')
    def test_disable_litp_debug(self, deployer_mock):
        deployer.deploy(model_xml=self.model_xml_filename,
                        litpd_host='localhost',
                        verbose=False,
                        load_plan=False,
                        load_create_plan=False,
                        create_run_plan=False
                        )
        self.assertFalse(deployer_mock.return_value.enable_litp_debug.called,
                         'Did not expect a call to enable LITP debug!')

    @patch('deployer.Deployer')
    def test_load_plan(self, deployer_mock):
        deployer.deploy(model_xml=self.model_xml_filename,
                        litpd_host='localhost',
                        verbose=False,
                        load_plan=True,
                        load_create_plan=False,
                        create_run_plan=False
                        )
        self.assertTrue(deployer_mock.return_value.load_xml.called,
                        'Expected a call to load XML!')
        self.assertFalse(deployer_mock.return_value.create_plan.called,
                         'Did not expect a call to create_plan()!')
        self.assertFalse(deployer_mock.return_value.show_plan.called,
                         'Did not expect a call to show the plan!')
        self.assertFalse(deployer_mock.return_value.run_plan.called,
                         'Did not expect a call to run_plan()!')
        self.assertFalse(deployer_mock.return_value.wait_plan_complete.called,
                         'Did not expect call to wait_plan_complete()!')

    @patch('deployer.Deployer')
    def test_load_create_plan(self, deployer_mock):
        deployer.deploy(model_xml=self.model_xml_filename,
                        litpd_host='localhost',
                        verbose=True,
                        load_plan=False,
                        load_create_plan=True,
                        create_run_plan=False)
        self.assertTrue(deployer_mock.return_value.load_xml.called,
                        'Expected a call to load XML!')
        self.assertTrue(deployer_mock.return_value.create_plan.called,
                        'Expected a call to create_plan()!')
        self.assertTrue(deployer_mock.return_value.show_plan.called,
                        'Expected a call to show the plan!')
        self.assertFalse(deployer_mock.return_value.run_plan.called,
                         'Did not expect a call to run_plan()!')
        self.assertFalse(deployer_mock.return_value.wait_plan_complete.called,
                         'Did not expect call to wait_plan_complete()!')

    @patch('deployer.main')
    def test_main_exceptions(self, deployer_main):
        class Args(object):
            model_xml = self.model_xml_filename
            litpd_host = 'localhost'
            verbose = False
            load_plan = False
            load_create_plan = False
            create_run_plan = False

        deployer_main.side_effect = KeyboardInterrupt()
        self.assertRaises(SystemExit, main_exceptions, deployer_main, Args)

        deployer_main.side_effect = LitpException(1,
                                                  'This is an expected error')
        self.assertRaises(SystemExit, main_exceptions, deployer_main, Args)

        deployer_main.side_effect = LitpException(
                1, {'a': 'This is an expected error'})
        self.assertRaises(SystemExit, main_exceptions, deployer_main, Args)

        deployer_main.side_effect = LitpException(
                1, {'messages': {'a': 'This is an expected error'}})
        self.assertRaises(SystemExit, main_exceptions, deployer_main, Args)

    @patch('deployer.Deployer')
    @patch('deployer.create_parser')
    def test_KeyboardInterrupt_handling(self, create_parser, dep):
        dep.return_value.wait_plan_complete.side_effect = KeyboardInterrupt()
        testargs = argparse.Namespace(
                model_xml=None,
                sed=None,
                vebose=False,
                verbose=False,
                litpd_host=None,
                create_run_plan=True,
                load_create_plan=False,
                load_plan=False
        )
        create_parser.return_value = MagicMock()
        create_parser.return_value.parse_args.side_effect = [testargs]

        with self.assertRaises(SystemExit) as error:
            main([])
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        dep.reset_mock()
        create_parser.reset_mock()
        create_parser.return_value.reset_mock()
        create_parser.return_value.parse_args.side_effect = [testargs]
        dep.return_value.wait_plan_complete.side_effect = SystemExit(2)
        with self.assertRaises(SystemExit) as error:
            main([])
        self.assertEqual(2, error.exception.code)

    @patch('deployer.Deployer')
    def test_deployer_resumed_plan_torf_190544(self, deployer_mock):
        deployer_mock.return_value.get_plan_state.return_value = 'failed'

        deployer.deploy(resume_plan=True)

        self.assertTrue(deployer_mock.return_value.resume_plan.called,
                        'Expected a call to resume_plan()!')
        self.assertTrue(deployer_mock.return_value.wait_plan_complete.called,
                        'Expected a call to wait_plan_complete()!')

    @patch('deployer.Deployer')
    def test_deployer_non_resumed_plan_torf_190544(self, deployer_mock):

        deployer.deploy(resume_plan=False)

        self.assertFalse(deployer_mock.return_value.resume_plan.called,
                         'Did not expect a call to resume_plan()!')

    @patch('deployer.Deployer')
    def test_resume_plan_not_in_failed_state(self, deployer_mock):
        deployer_mock.return_value.get_plan_state.return_value = 'initial'
        with self.assertRaises(SystemExit) as sysexit:
            deployer.deploy(resume_plan=True)
        self.assertEqual(sysexit.exception.code, ExitCodes.ERROR)

    @patch('deployer.Deployer')
    def test_resume_plan_exception(self, deployer_mock):
        deployer_mock.return_value.get_plan_state.side_effect = \
            LitpException(404, {'path': '/plans/plan', 'reason': 'Not Found',
                     'messages': [{u'type': u'InvalidLocationError',
                            u'message':
                                u'Plan does not exist',
                                u'_links': {u'self': {u'href':
                                u'http://127.0.0.1/litp/rest/v1/plans'}}}]})

        with self.assertRaises(SystemExit) as sysexit:
            deployer.deploy(resume_plan=True)
        self.assertEqual(sysexit.exception.code, ExitCodes.ERROR)

if __name__ == '__main__':
    unittest2.main()
