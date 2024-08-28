import os
from mock import patch
from tempfile import gettempdir
from unittest2 import TestCase

from h_expansion.validate_expansion_sed import ExpansionSedValidation
from h_expansion.expansion_sed_utils import ExpansionSedHandler
from h_expansion.expansion_utils import Blade, ValidationException


def dummy_get_blades_to_move():
    """
    Dummy version of the get_blades_to_move function which will return
    a list of blade objects like the real function but without needing
    to contact LITP or the OA.
    params are src & dest OA credentials and the dict of system name /ilos
    none are use and don't have to be passed.
    :return: blade list
    """
    db_2 = ['ieatrcxb3184', 'db-2', 'CZ3328JJT6',
            '10.151.179.37', '10.151.119.10', '8', 'Unknown']
    scp_2 = ['ieatrcxb3774', 'scp-2', 'CZJ423002Q',
             '10.151.179.35', '10.151.111.12', '6', 'Unknown']
    svc_2 = ['ieatrcxb1958', 'svc-2', 'CZ36071H37',
             '10.151.179.31', '10.151.111.13', '2', 'Unknown']
    svc_4 = ['ieatrcxb3175', 'svc-4', 'CZ3328JD3P',
             '10.151.179.32', '10.151.111.14', '3', 'Unknown']

    blades = []
    for blade_cfg in [db_2, scp_2, svc_2, svc_4]:
        blade = Blade()
        blade.hostname = blade_cfg[0]
        blade.sys_name = blade_cfg[1]
        blade.serial_no = blade_cfg[2]
        blade.src_ilo = blade_cfg[3]
        blade.dest_ilo = blade_cfg[4]
        blade.src_bay = blade_cfg[5]
        blade.dest_bay = blade_cfg[6]
        blades.append(blade)

    return blades


class TestExpansionSedValidation(TestCase):

    @patch('h_expansion.expansion_utils.LitpRestClient')
    def setUp(self, litp_rest):
        os.environ['ENMINST_RUNTIME'] = gettempdir()

        dir_path = os.path.dirname(os.path.realpath(__file__))
        target_sed = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_sed')
        sed_validator = ExpansionSedHandler(target_sed)
        self.sed_validator = ExpansionSedValidation(sed_validator)

    def tearDown(self):
        del os.environ['ENMINST_RUNTIME']

    @patch('h_expansion.validate_expansion_sed.ping')
    def test_validate_sed(self, m_ping):
        m_ping.return_value = False
        blades_to_move = dummy_get_blades_to_move()
        exc_dep_info = {
            'scp-2': {
                'src_bay': '6', 'dest_ilo': '10.151.111.12', 'key': None,
                'src_ilo': '10.151.179.35', 'ilo_user': None,
                'dest_bay': 'Unknown', 'serial': 'CZJ423002Q',
                'hostname': 'ieatrcxb3774'},
            'db-2': {
                'src_bay': '8', 'dest_ilo': '10.151.119.10', 'key': None,
                'src_ilo': '10.151.179.37', 'ilo_user': None,
                'dest_bay': 'Unknown', 'serial': 'CZ3328JJT6',
                'hostname': 'ieatrcxb3184'},
            'svc-4': {
                'src_bay': '3', 'dest_ilo': '10.151.111.14', 'key': None,
                'src_ilo': '10.151.179.32', 'ilo_user': None,
                'dest_bay': 'Unknown', 'serial': 'CZ3328JD3P',
                'hostname': 'ieatrcxb3175'},
            'svc-2': {
                'src_bay': '2', 'dest_ilo': '10.151.111.13', 'key': None,
                'src_ilo': '10.151.179.31', 'ilo_user': None,
                'dest_bay': 'Unknown', 'serial': 'CZ36071H37',
                'hostname': 'ieatrcxb1958'}}
        self.sed_validator.validate_sed(blades_to_move)
        self.assertTrue(m_ping.called)
        self.assertEqual(self.sed_validator.deployment_info, exc_dep_info)

    @patch('h_expansion.validate_expansion_sed.ping')
    def test_validate_sed_same_ilos(self, m_ping):
        m_ping.return_value = False
        blades_to_move = dummy_get_blades_to_move()

        for blade in blades_to_move:
            blade.dest_ilo = blade.src_ilo

        self.sed_validator.validate_sed(blades_to_move)
        self.assertFalse(m_ping.called)

    @patch('h_expansion.validate_expansion_sed.ping')
    def test_validate_sed_duplicate_ilos(self, m_ping):
        m_ping.return_value = False
        blades_to_move = dummy_get_blades_to_move()

        self.sed_validator.target_sed.sed['duplicate_ilo_1'] = '10.151.119.10'
        self.sed_validator.target_sed.sed['duplicate_ilo_2'] = '10.151.119.10'

        self.assertRaises(ValidationException, self.sed_validator.validate_sed,
                          blades_to_move)

    @patch('os.remove')
    @patch('os.path.exists')
    @patch('h_expansion.validate_expansion_sed.query_strong_yes_no')
    def test_validate_sed_model_exists(self, m_query, m_exists, m_remove):
        # Model exists, but delete fails
        m_query.return_value = True
        m_exists.return_value = True
        m_remove.side_effect = OSError()
        blades_to_move = dummy_get_blades_to_move()

        self.assertRaises(OSError,
                          self.sed_validator.validate_sed,
                          blades_to_move)

        # Model exists, but prompt to delete declined
        m_query.return_value = False
        m_exists.return_value = True
        blades_to_move = dummy_get_blades_to_move()

        self.assertRaises(Exception,
                          self.sed_validator.validate_sed,
                          blades_to_move)

    def test_validate_sed_serial_mismatch(self):
        invalid_serial_blade = Blade()
        invalid_serial_blade.hostname = 'ieatrcxb3184'
        invalid_serial_blade.sys_name = 'db-2'
        invalid_serial_blade.serial_no = 'CZ35230JVD'
        invalid_serial_blade.src_ilo = '10.151.179.37'
        invalid_serial_blade.dest_ilo = '10.151.119.10'
        invalid_serial_blade.src_bay = '8'
        invalid_serial_blade.dest_bay = '3'

        blades_to_move = [invalid_serial_blade]

        self.assertRaises(ValidationException,
                          self.sed_validator.validate_sed,
                          blades_to_move)

    def test_validate_sed_fail_ping_test(self):
        invalid_serial_blade = Blade()
        invalid_serial_blade.hostname = 'ieatrcxb3184'
        invalid_serial_blade.sys_name = 'db-2'
        invalid_serial_blade.serial_no = 'CZ3328JJT6'
        invalid_serial_blade.src_ilo = '10.151.179.37'
        invalid_serial_blade.dest_ilo = '127.0.0.1'
        invalid_serial_blade.src_bay = '8'
        invalid_serial_blade.dest_bay = '3'

        blades_to_move = [invalid_serial_blade]

        self.assertRaises(ValidationException,
                          self.sed_validator.validate_sed,
                          blades_to_move)

    @patch('__builtin__.open')
    def test_write_model_file(self, m_open):
        self.sed_validator.write_model_file()

        self.assertTrue(m_open.called)

    @patch('__builtin__.open')
    def test_write_model_file_exception(self, m_open):
        m_open.side_effect = IOError()

        self.assertRaises(IOError, self.sed_validator.write_model_file)
