from __future__ import print_function
from h_expansion.expansion_ilo_update import add_new_ilos_to_litp, create_run_plan
from h_expansion.expansion_utils import ExpansionException
from h_litp.litp_utils import LitpException
from test_validate_expansion_sed import dummy_get_blades_to_move

import unittest2
from mock import patch

src_oa_1 = '10.151.179.22'
src_oa_2 = '10.151.179.23'
src_user = 'fw_user'
src_passwd = '12shroot'
dest_oa_1 = '10.151.179.22'
dest_oa_2 = '10.151.179.23'
dest_user = 'fw_user'
dest_passwd = '12shroot'


def get_litp_ilo_from_blades(blades, src_ilo=True, applied_state=True):
    litp_ilos = []
    for blade in blades:
        ilo_dict = {}
        if src_ilo:
            ilo = blade.src_ilo
        else:
            ilo = blade.dest_ilo
        ilo_dict['ipaddress'] = ilo
        if applied_state:
            state = 'Applied'
        else:
            state = 'Initial'
        ilo_dict['state'] = state
        ilo_dict['username'] = 'root'
        ilo_dict['password_key'] = 'ilo-key-{0}'.format(blade.sys_name)
        litp_ilos.append(ilo_dict)
    return litp_ilos


class TestExpansionIloUpdate(unittest2.TestCase):
    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan(self, m_litp, m_sleep):
        m_litp.rest.get_plan_state.return_value = 'successful'
        m_litp.rest.PLAN_STATE_SUCCESSFUL = 'successful'
        create_run_plan(m_litp)
        self.assertTrue(m_litp.rest.create_plan.called)
        self.assertTrue(m_litp.rest.set_plan_state.called)
        self.assertTrue(m_litp.rest.get_plan_state.called)

    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan_failed(self, m_litp, m_sleep):
        m_litp.rest.get_plan_state.return_value = 'failed'
        m_litp.rest.PLAN_STATE_FAILED = 'failed'
        self.assertRaises(ExpansionException, create_run_plan, m_litp)

    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan_stopped(self, m_litp, m_sleep):
        m_litp.rest.get_plan_state.return_value = 'stopped'
        m_litp.rest.PLAN_STATE_STOPPED = 'stopped'
        self.assertRaises(ExpansionException, create_run_plan, m_litp)

    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan_invalid(self, m_litp, m_sleep):
        m_litp.rest.get_plan_state.return_value = 'invalid'
        m_litp.rest.PLAN_STATE_INVALID = 'invalid'
        self.assertRaises(ExpansionException, create_run_plan, m_litp)

    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan_create_fail(self, m_litp, m_sleep):
        m_litp.rest.create_plan.side_effect = [LitpException]
        self.assertRaises(LitpException, create_run_plan, m_litp)

    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan_create_do_nothing(self, m_litp, m_sleep):
        m_litp.rest.create_plan.side_effect = [LitpException('DoNothingPlanError')]
        create_run_plan(m_litp)
        self.assertTrue(m_litp.rest.create_plan.called)
        self.assertFalse(m_litp.rest.set_plan_state.called)
        self.assertFalse(m_litp.rest.get_plan_state.called)

    @patch('h_expansion.expansion_ilo_update.time.sleep')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_create_run_plan_create_timeout(self, m_litp, m_sleep):
        m_litp.rest.get_plan_state.return_value = 'running'
        self.assertRaises(ExpansionException, create_run_plan, m_litp)
        self.assertTrue(m_litp.rest.create_plan.called)
        self.assertTrue(m_litp.rest.set_plan_state.called)
        self.assertTrue(m_litp.rest.get_plan_state.called)

    @patch('h_expansion.expansion_ilo_update.create_run_plan')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_add_new_ilos_to_litp(self, m_litp, m_plan):
        blades = dummy_get_blades_to_move()
        ilos = get_litp_ilo_from_blades(blades, src_ilo=True, applied_state=True)
        m_get_ilo = m_litp.return_value.get_ilo_properties
        m_get_ilo.side_effect = ilos
        add_new_ilos_to_litp(blades)
        self.assertEqual(m_get_ilo.call_count, 4)

    @patch('h_expansion.expansion_ilo_update.create_run_plan')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_add_new_ilos_to_litp_no_plan(self, m_litp, m_plan):
        blades = dummy_get_blades_to_move()
        ilos = get_litp_ilo_from_blades(blades, src_ilo=True, applied_state=False)
        m_get_ilo = m_litp.return_value.get_ilo_properties
        m_get_ilo.side_effect = ilos
        add_new_ilos_to_litp(blades)
        self.assertTrue(m_get_ilo.call_count, 4)
        self.assertTrue(m_litp.return_value.delete_ilo_entry.called)
        self.assertFalse(m_plan.called)
        self.assertTrue(m_litp.return_value.create_ilo_entry.called)

    @patch('h_expansion.expansion_ilo_update.create_run_plan')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_add_new_ilos_to_litp_invalid_location(self, m_litp, m_plan):
        blades = dummy_get_blades_to_move()
        exception_list = [LitpException('InvalidLocationError')] * 4

        m_get_ilo = m_litp.return_value.get_ilo_properties
        m_get_ilo.side_effect = exception_list
        add_new_ilos_to_litp(blades)
        self.assertTrue(m_get_ilo.call_count, 4)
        self.assertFalse(m_litp.return_value.delete_ilo_entry.called)
        self.assertFalse(m_plan.called)
        self.assertTrue(m_litp.return_value.create_ilo_entry.called)

    @patch('h_expansion.expansion_ilo_update.create_run_plan')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_add_new_ilos_to_litp_exception(self, m_litp, m_plan):
        blades = dummy_get_blades_to_move()
        m_get_ilo = m_litp.return_value.get_ilo_properties
        m_get_ilo.side_effect = [LitpException('Failed to retrieve')]
        self.assertRaises(LitpException, add_new_ilos_to_litp, blades)

    @patch('h_expansion.expansion_ilo_update.create_run_plan')
    @patch('h_expansion.expansion_ilo_update.LitpHandler')
    def test_add_new_ilos_to_litp_dest_ip(self, m_litp, m_plan):
        blades = dummy_get_blades_to_move()
        ilos = get_litp_ilo_from_blades(blades, src_ilo=False, applied_state=True)
        m_get_ilo = m_litp.return_value.get_ilo_properties
        m_get_ilo.side_effect = ilos
        add_new_ilos_to_litp(blades)
        self.assertTrue(m_get_ilo.call_count, 4)
        self.assertFalse(m_litp.return_value.delete_ilo_entry.called)
        self.assertFalse(m_plan.called)
        self.assertFalse(m_litp.return_value.create_ilo_entry.called)
