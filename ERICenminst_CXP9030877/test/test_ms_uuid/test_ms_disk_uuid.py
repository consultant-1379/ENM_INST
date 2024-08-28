import os
import sys

from mock import MagicMock, patch
from unittest2 import TestCase

from h_litp.litp_utils import main_exceptions
from h_util.h_utils import ExitCodes
from ms_uuid import get_ms_disk_uuid, update_enminst_working, update_uuid

if sys.platform.lower().startswith('win'):
    sys.modules['pwd'] = MagicMock()


class TestGetMsDiskUuid(TestCase):
    def setUp(self):
        with open('empty_file.txt', 'a') as f:
            pass
        with open('existing_uuid_file.txt', 'w') as f:
            f.write('ms_uuid_disk0=2222222222222')

    def tearDown(self):
        if os.path.exists('missing_file.txt'):
            os.remove('missing_file.txt')
        os.remove('empty_file.txt')
        os.remove('existing_uuid_file.txt')

    @patch('ms_uuid.exec_process')
    def test_get_ms_disk_uuid(self, exec_p):
        log = MagicMock()
        pvscan_out = "    /dev/sda2,vg_root\n"

        uid_short = '600508b1001c66734845018c88'
        uid_long = '600508b1001c66734845018c88b41d3c453c'
        uid_norm = '600508b1001c66734845018c88b41d3c'
        for uid in (uid_short, uid_long, uid_norm):
            udevadm_out = \
                "E: ID_TYPE=disk\n" \
                "E: ID_SERIAL_RAW=3{0}\n" \
                "E: ID_SERIAL=3{0}\n" \
                "E: ID_SERIAL_SHORT={0}\n" \
                "E: ID_WWN=0x600508b1001c6673".format(uid)

            exec_p.side_effect = [pvscan_out, udevadm_out]
            ms_uuid = get_ms_disk_uuid(log)
            self.assertEquals(ms_uuid, uid)

    @patch('ms_uuid.exec_process')
    def test_get_ms_disk_uuid_with_full_lvm_snapshot(self, exec_p):
        log = MagicMock()
        pvscan_out = \
            '  /dev/vg_root/Snapshot_lv_var: read failed after 0 of 4096 at ' \
            '53687025664: Input/output error\n' \
            '  /dev/vg_root/Snapshot_lv_var: read failed after 0 of 4096 at ' \
            '53687083008: Input/output error\n' \
            '  /dev/vg_root/Snapshot_lv_var: read failed after 0 of 4096 at ' \
            '0: Input/output error\n' \
            '  /dev/vg_root/Snapshot_lv_var: read failed after 0 of 4096 at ' \
            '4096: Input/output error\n' \
            '  /dev/sda2,vg_root\n'
        udevadm_out = \
            "E: ID_TYPE=disk\n" \
            "E: ID_SERIAL_RAW=3600508b1001c66734845018c88b41d3c\n" \
            "E: ID_SERIAL=3600508b1001c66734845018c88b41d3c\n" \
            "E: ID_SERIAL_SHORT=600508b1001c66734845018c88b41d3c\n" \
            "E: ID_WWN=0x600508b1001c6673"

        exec_p.side_effect = [pvscan_out, udevadm_out]
        uuid = get_ms_disk_uuid(log)
        self.assertEquals(uuid, '600508b1001c66734845018c88b41d3c')

    @patch('ms_uuid.exec_process')
    def test_get_ms_disk_uuid_failed(self, exec_p):
        log = MagicMock()
        pvscan_out = "    /dev/sda2,vg_root\n"

        udevadm_tmpl = "E: ID_TYPE=disk\n" \
                       "E: ID_SERIAL_RAW=3{0}\n" \
                       "E: ID_SERIAL=3{0}\n" \
                       "E: ID_SERIAL_SHORT={0}\n" \
                       "E: ID_WWN=0x600508b1001c6673"

        uid_norm = '600508b1001c66734845018c88b41d3c'
        udevadm_out = udevadm_tmpl.format(uid_norm)

        exec_p.side_effect = ['', udevadm_out]
        self.assertRaises(ValueError, get_ms_disk_uuid, log)

        exec_p.side_effect = [pvscan_out, '']
        self.assertRaises(ValueError, get_ms_disk_uuid, log)

        # ----

        udevadm_out = udevadm_tmpl.format('')
        exec_p.side_effect = [pvscan_out, udevadm_out]
        try:
            get_ms_disk_uuid(log)
        except ValueError as e:
            self.assertEqual(str(e), 'Failed to get valid UUID.')
        else:
            raise Exception('Expected invalid UUID, not found')

    @patch('ms_uuid.get_ms_disk_uuid')
    def test_update_enminst_working(self, get_ms_disk_u):
        log = MagicMock()
        get_ms_disk_u.return_value = '600508b1001c66734845018c88b41d3c'
        update_enminst_working('empty_file.txt', log)
        get_ms_disk_u.assert_called_with(log)
        self.assertIn(get_ms_disk_u.return_value,
                      open('empty_file.txt').read())

        update_enminst_working('missing_file.txt', log)
        self.assertTrue(os.path.exists('missing_file.txt'))

        update_enminst_working('existing_uuid_file.txt', log)
        get_ms_disk_u.assert_called_with(log)
        self.assertIn(get_ms_disk_u.return_value,
                      open('existing_uuid_file.txt').read())

    @patch('ms_uuid.init_enminst_logging')
    @patch('ms_uuid.read_enminst_config')
    @patch('ms_uuid.update_enminst_working')
    def test_update_uuid(self, enminst_w, config, log):
        update_uuid()
        enminst_w.assert_called_with(
                config.return_value['enminst_working_parameters'],
                log.return_value)

    @patch('ms_uuid.update_enminst_working')
    def test_KeyboardInterrupt_handling(self, uew):
        uew.side_effect = KeyboardInterrupt()
        with self.assertRaises(SystemExit) as error:
            main_exceptions(update_uuid)
        self.assertEqual(ExitCodes.INTERRUPTED, error.exception.code)

        uew.reset_mock()
        uew.side_effect = IOError()
        self.assertRaises(IOError, main_exceptions, update_uuid)
