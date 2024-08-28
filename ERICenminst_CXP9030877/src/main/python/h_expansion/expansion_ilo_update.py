"""
Module to update the iLO IP addresses in LITP.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property
# of Ericsson AB. The programs may be used and/or copied only with
# the written permission from Ericsson AB or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
##############################################################################
import time
import logging

from expansion_utils import ExpansionException, LitpHandler
from h_litp.litp_utils import LitpException

LOGGER = logging.getLogger("enminst")


def create_run_plan(litp, tries=20, delay=30):
    """
    Function that creates a LITP plan to update the BMC items
    in the LITP model.
    :param litp: Instance of the LITPHandler class
    :param tries: Number of attempts to call LITP
    :param delay: Delay between LITP calls
    :return:
    """
    LOGGER.info('Creating LITP plan to remove BMC items from systems')
    try:
        litp.rest.create_plan('plan')
    except LitpException as err:
        if 'DoNothingPlanError' in str(err):
            LOGGER.info('No tasks were generated so no plan to run')
            return
        LOGGER.error('LITP plan creation failed: %s', err)
        raise

    LOGGER.info('Plan created:')
    LOGGER.info('Going to run the LITP plan to remove the iLO entries')
    litp.rest.set_plan_state('plan', 'running')
    LOGGER.info('LITP plan running')

    while tries >= 0:
        plan_state = litp.rest.get_plan_state('plan')
        LOGGER.info('LITP plan state is %s', plan_state)

        if plan_state == litp.rest.PLAN_STATE_SUCCESSFUL:
            LOGGER.info('LITP plan completed successfully')
            return
        elif plan_state == litp.rest.PLAN_STATE_FAILED:
            LOGGER.error('LITP plan failed')
            raise ExpansionException('LITP plan has failed')
        elif plan_state == litp.rest.PLAN_STATE_STOPPED:
            LOGGER.error('LITP plan has been stopped')
            raise ExpansionException('LITP plan has been stopped')
        elif plan_state == litp.rest.PLAN_STATE_INVALID:
            LOGGER.error('LITP plan is invalid')
            raise ExpansionException('LITP plan is invalid')

        tries -= 1
        LOGGER.info('Sleeping for %s seconds, %s attempt(s) left',
                    delay, tries)
        time.sleep(delay)

    LOGGER.error('Timed out waiting for LITP plan to complete, state is %s:',
                 plan_state)

    raise ExpansionException('LITP plan timed out')


def add_new_ilos_to_litp(blades):
    """
    :param blades:
    :return:
    """
    LOGGER.debug("Entered add_new_ilos_to_litp")

    litp = LitpHandler()

    plan_required = False
    blades_to_create = []

    for blade in blades:
        LOGGER.debug("Getting iLO props for %s", blade.sys_name)
        try:
            props = litp.get_ilo_properties(blade.sys_name)
            LOGGER.info('%s iLO properties: %s', blade.sys_name, props)
        except LitpException as err:
            if 'InvalidLocationError' in str(err):
                LOGGER.info('iLO for %s is already removed', blade.sys_name)
                blades_to_create.append(blade)
                continue
            else:
                LOGGER.error('Failed to get iLO entry: %s', err)
                raise

        if props['ipaddress'] == blade.dest_ilo:
            LOGGER.info('%s iLO is already set correctly', blade.sys_name)
            continue
        else:
            LOGGER.info('%s iLO needs changing', blade.sys_name)
            blades_to_create.append(blade)

        if props['state'] == 'Initial':
            LOGGER.info('%s iLO is in initial state', blade.sys_name)
        else:
            LOGGER.info('%s iLO is in %s state', blade.sys_name,
                        props['state'])
            plan_required = True

        LOGGER.info('Removing iLO entry for %s', blade.sys_name)
        litp.delete_ilo_entry(blade.sys_name)
        LOGGER.info("%s iLO will be changed from: %s to %s",
                    blade.sys_name, blade.src_ilo, blade.dest_ilo)

    LOGGER.info('Plan required: %s', plan_required)
    if plan_required:
        create_run_plan(litp)
    else:
        LOGGER.info('No plan needs running')

    for blade in blades_to_create:
        LOGGER.info('Creating new iLO entry for %s in LITP', blade.sys_name)
        blade_bmc = {'ipaddress': blade.dest_ilo,
                     'username': blade.ilo_user,
                     'password_key': blade.ilo_pass_key}

        LOGGER.info('BMC dict for %s is %s', blade.sys_name, blade_bmc)
        res = litp.create_ilo_entry(blade.sys_name, blade_bmc)
        LOGGER.info('Created LITP entry for %s: %s', blade.sys_name, res)
