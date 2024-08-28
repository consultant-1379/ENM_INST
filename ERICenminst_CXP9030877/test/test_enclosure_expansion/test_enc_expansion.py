import os
import json
from mock import patch
from unittest2 import TestCase

from h_expansion.expansion_boot_utils import ExpansionException
from h_expansion.expansion_utils import Blade, OnboardAdministratorHandler
from enc_expansion import create_parser, report_generation, \
    validate_expansion_sed, generate_enclosure_report, shutdown_blades, \
    power_on_blades, update_ilo_ips_in_litp_model, expansion_cleanup, main


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
            '10.151.179.37', '10.151.119.10', '8', '3']
    scp_2 = ['ieatrcxb3774', 'scp-2', 'CZJ423002Q',
             '10.151.179.35', '10.151.111.12', '6', '5']
    svc_2 = ['ieatrcxb1958', 'svc-2', 'CZ36071H37',
             '10.151.179.31', '10.151.111.13', '2', '6']
    svc_4 = ['ieatrcxb3175', 'svc-4', 'CZ3328JD3P',
             '10.151.179.32', '10.151.111.14', '3', '7']

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


class TestEncExpansion(TestCase):
    def setUp(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.target_sed = os.path.join(dir_path,
                                       '../Resources/chassis_expansion_sed')
        self.parser = create_parser()

        model_path = os.path.join(dir_path,
                                  '../Resources/chassis_expansion_model.json')

        with open(model_path, 'r') as model_file:
            self.exp_model = json.load(model_file)

    def tearDown(self):
        pass

    def test_arg_parsing_validate_sed(self):
        input_args = ['validate-sed', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'validate-sed')
        self.assertEqual(args.sed, self.target_sed)

    @patch('enc_expansion.sys.stderr')
    def test_arg_parsing_validate_sed_exception(self, m_stderr):
        input_args = ['validate-sed', '--sed', '/path/to/invalid/sed']

        self.assertRaises(SystemExit, self.parser.parse_args, input_args)

    def test_arg_parsing_generate_report(self):
        input_args = ['enclosure-report', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'enclosure-report')
        self.assertEqual(args.sed, self.target_sed)

    @patch('enc_expansion.sys.stderr')
    def test_arg_parsing_generate_report_exception(self, m_stderr):
        input_args = ['enclosure-report', '--sed', '/path/to/invalid/sed']

        self.assertRaises(SystemExit, self.parser.parse_args, input_args)

    def test_arg_parsing_shutdown_blades(self):
        input_args = ['shutdown-blades', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'shutdown-blades')
        self.assertEqual(args.sed, self.target_sed)
        self.assertEqual(args.rollback, False)

    def test_arg_parsing_shutdown_blades_rollback(self):
        input_args = ['shutdown-blades', '--sed', self.target_sed,
                      '--rollback']

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'shutdown-blades')
        self.assertEqual(args.sed, self.target_sed)
        self.assertEqual(args.rollback, True)

    @patch('enc_expansion.sys.stderr')
    def test_arg_parsing_shutdown_blades_exception(self, m_stderr):
        input_args = ['shutdown-blades', '--sed', '/path/to/invalid/sed']

        self.assertRaises(SystemExit, self.parser.parse_args, input_args)

    def test_arg_parsing_boot_blades(self):
        input_args = ['boot-blades', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'boot-blades')
        self.assertEqual(args.sed, self.target_sed)
        self.assertEqual(args.rollback, False)

    def test_arg_parsing_boot_blades_rollback(self):
        input_args = ['boot-blades', '--sed', self.target_sed, '--rollback']

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'boot-blades')
        self.assertEqual(args.sed, self.target_sed)
        self.assertEqual(args.rollback, True)

    @patch('enc_expansion.sys.stderr')
    def test_arg_parsing_boot_blades_exception(self, m_stderr):
        input_args = ['boot-blades', '--sed', '/path/to/invalid/sed']

        self.assertRaises(SystemExit, self.parser.parse_args, input_args)

    def test_arg_parsing_update_ilos(self):
        input_args = ['update-ilo-ips', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'update-ilo-ips')
        self.assertEqual(args.sed, self.target_sed)

    @patch('enc_expansion.sys.stderr')
    def test_arg_parsing_update_ilos_exception(self, m_stderr):
        input_args = ['update-ilo-ips', '--sed', '/path/to/invalid/sed']

        self.assertRaises(SystemExit, self.parser.parse_args, input_args)

    def test_arg_parsing_cleanup(self):
        input_args = ['cleanup', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'cleanup')
        self.assertEqual(args.sed, self.target_sed)
        self.assertEqual(args.clean_src_oa, False)

    def test_arg_parsing_cleanup_clean_src_oa(self):
        input_args = ['cleanup', '--sed', self.target_sed, '--clean_src_oa']

        args = self.parser.parse_args(input_args)

        self.assertEqual(args.command, 'cleanup')
        self.assertEqual(args.sed, self.target_sed)
        self.assertEqual(args.clean_src_oa, True)

    @patch('enc_expansion.sys.stderr')
    def test_arg_parsing_cleanup_exception(self, m_stderr):
        input_args = ['cleanup', '--sed', '/path/to/invalid/sed']

        self.assertRaises(SystemExit, self.parser.parse_args, input_args)

    @patch('__builtin__.open')
    @patch('os.path.exists', side_effect=[True])
    @patch('enc_expansion.exec_process')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_report_generation(self, m_oa, m_exec, mock_data, m_open):
        blades_list = dummy_get_blades_to_move()
        m_oa.return_value = 'Server Names'
        enclosure_oa = OnboardAdministratorHandler('oa_ip1',
                                                   'oa_ip2',
                                                   'oa_username',
                                                   'oa_password')

        blade_str = report_generation(blades_list, enclosure_oa)
        blade_count = 0

        for line in blade_str.splitlines():
            if 'Enclosure report' in line or 'Name' in line or '====' in line \
                    or 'DETAILS' in line or not line:
                continue
            entries = line.split()
            try:
                matching_blade = [b for b in blades_list
                                  if b.sys_name == entries[0]][0]
                # If an IndexError happens not all the blades were found
            except IndexError:
                raise AssertionError(
                    'Not all blades are present in this report')

            blade_count += 1
            self.assertEqual(matching_blade.sys_name, entries[0])
            self.assertEqual(matching_blade.serial_no, entries[1])
            self.assertEqual(matching_blade.src_ilo, entries[2])
            self.assertEqual(matching_blade.dest_ilo, entries[3])
            self.assertEqual(matching_blade.src_bay, entries[4])
            self.assertEqual(matching_blade.dest_bay, entries[5])
            self.assertEqual(matching_blade.hostname, entries[6])
            self.assertTrue(m_oa.called)
            self.assertTrue(m_exec.called)
            self.assertTrue(m_open.called)

        self.assertEqual(len(blades_list), blade_count)

    @patch('__builtin__.open')
    @patch('os.path.exists', side_effect=[True])
    @patch('enc_expansion.exec_process')
    @patch('h_expansion.expansion_utils.OnboardAdministratorHandler.show_server_names')
    def test_report_generation_error(self, m_oa, m_exec, mock_data, m_open):
        blades_list = dummy_get_blades_to_move()
        m_oa.return_value = 'Server Names'
        m_exec.side_effect = [IOError]
        enclosure_oa = OnboardAdministratorHandler('oa_ip1',
                                                   'oa_ip2',
                                                   'oa_username',
                                                   'oa_password')

        self.assertRaises(IOError, report_generation, blades_list, enclosure_oa)

    @patch('os.path.exists')
    @patch('enc_expansion.LitpHandler')
    @patch('enc_expansion.get_blade_info')
    @patch('h_expansion.validate_expansion_sed.LitpHandler')
    @patch('h_expansion.validate_expansion_sed.ExpansionSedValidation.validate_sed')
    @patch('h_expansion.validate_expansion_sed.ExpansionSedValidation.write_model_file')
    @patch('h_expansion.expansion_sed_utils.ExpansionSedHandler.get_enclosure_oa_info')
    def test_validate_expansion_sed(self, m_oa_info, m_write_model, m_val_sed,
                                    m_val_litp, m_blade_info, m_litp, m_exists):
        m_exists.return_value = True

        input_args = ['validate-sed', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        validate_expansion_sed(args)

        self.assertTrue(m_litp.called)
        self.assertTrue(m_oa_info.called)
        self.assertTrue(m_blade_info.called)
        self.assertTrue(m_val_litp.called)
        self.assertTrue(m_val_sed.called)
        self.assertTrue(m_write_model.called)

    @patch('os.path.exists')
    def test_validate_expansion_sed_hwcomm_exception(self, m_exists):
        m_exists.return_value = False

        input_args = ['validate-sed', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        self.assertRaises(Exception, validate_expansion_sed, args)

    @patch('enc_expansion.LitpHandler')
    @patch('enc_expansion.get_blade_info')
    @patch('enc_expansion.report_generation')
    @patch('h_expansion.expansion_sed_utils.ExpansionSedHandler.get_enclosure_oa_info')
    def test_generate_enclosure_report(self, m_oa_info, m_report,
                                       m_blade_info, m_litp):
        input_args = ['enclosure-report', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        generate_enclosure_report(args)

        self.assertTrue(m_litp.called)
        self.assertTrue(m_oa_info.called)
        self.assertTrue(m_blade_info.called)
        self.assertTrue(m_report.called)

    @patch('enc_expansion.LitpHandler')
    @patch('enc_expansion.get_blade_info')
    @patch('enc_expansion.freeze_and_shutdown_systems')
    @patch('h_expansion.expansion_sed_utils.ExpansionSedHandler.get_enclosure_oa_info')
    def test_shutdown_blades(self, m_oa_info, m_freeze, m_blade_info, m_litp):
        input_args = ['shutdown-blades', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        shutdown_blades(args)

        self.assertTrue(m_litp.called)
        self.assertTrue(m_oa_info.called)
        self.assertTrue(m_blade_info.called)
        self.assertTrue(m_freeze.called)

    @patch('enc_expansion.LitpHandler')
    @patch('enc_expansion.get_blade_info')
    @patch('enc_expansion.boot_systems_and_unlock_vcs')
    @patch('h_expansion.expansion_sed_utils.ExpansionSedHandler.get_enclosure_oa_info')
    def test_power_on_blades(self, m_oa_info, m_unlock, m_blade_info, m_litp):
        input_args = ['boot-blades', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        power_on_blades(args)

        self.assertTrue(m_litp.called)
        self.assertTrue(m_oa_info.called)
        self.assertTrue(m_blade_info.called)
        self.assertTrue(m_unlock.called)

    @patch('enc_expansion.add_new_ilos_to_litp')
    @patch('h_expansion.expansion_model_handler.ExpansionModelHandler.read_expansion_model')
    def test_update_ilo_ips_in_litp_model(self, m_read, m_update_ilos):
        m_read.return_value = self.exp_model

        input_args = ['boot-blades', '--sed', self.target_sed]

        args = self.parser.parse_args(input_args)

        update_ilo_ips_in_litp_model(args)

        self.assertTrue(m_update_ilos.called)

    @patch('enc_expansion.report_file_ok')
    @patch('enc_expansion.cleanup_source_oa')
    @patch('enc_expansion.cleanup_arp_cache')
    @patch('enc_expansion.cleanup_runtime_files')
    def test_expansion_cleanup(self, m_runtime, m_arp, m_oa, m_report):
        m_report.return_value = True

        input_args = ['cleanup', '--sed', self.target_sed, '--clean_src_oa']

        args = self.parser.parse_args(input_args)

        expansion_cleanup(args)

        self.assertTrue(m_oa.called)
        self.assertTrue(m_arp.called)
        self.assertTrue(m_runtime.called)

    @patch('enc_expansion.report_file_ok')
    def test_expansion_cleanup_exception(self, m_report):
        m_report.return_value = False
        input_args = ['cleanup', '--sed', self.target_sed, '--clean_src_oa']
        args = self.parser.parse_args(input_args)
        self.assertRaises(ExpansionException, expansion_cleanup, args)

    @patch('enc_expansion.power_on_blades')
    @patch('enc_expansion.report_file_ok')
    def test_main(self, m_report_file, m_power_on):
        m_report_file.return_value = True
        input_args = ['enc_expansion.py', 'boot-blades', '--sed', self.target_sed]
        main(input_args)
        self.assertTrue(m_power_on.called)
        self.assertTrue(m_report_file.called)

    @patch('enc_expansion.create_parser')
    @patch('enc_expansion.power_on_blades')
    @patch('enc_expansion.report_file_ok')
    def test_main_invalid_cmd(self, m_report_file, m_power_on, m_parser):
        class ParsedArgs(object):
            command = 'shoot-blades'
        parsed_args = ParsedArgs()
        m_parser.return_value.parse_args.return_value = parsed_args
        m_report_file.return_value = True
        input_args = ['enc_expansion.py', 'shoot-blades', '--sed', self.target_sed]
        self.assertRaises(KeyError, main, input_args)
        self.assertFalse(m_power_on.called)
        self.assertFalse(m_report_file.called)

    @patch('enc_expansion.power_on_blades')
    @patch('enc_expansion.report_file_ok')
    def test_main_invalid_report(self, m_report_file, m_power_on):
        m_report_file.return_value = False
        input_args = ['enc_expansion.py', 'boot-blades', '--sed', self.target_sed]
        self.assertRaises(ExpansionException, main, input_args)
        self.assertFalse(m_power_on.called)
        self.assertTrue(m_report_file.called)
