"""
Module containing functions involved with shutting down and booting
up Blades
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
import logging
from datetime import datetime
from time import sleep

from h_expansion.expansion_sed_utils import ExpansionSedHandler
from h_expansion.expansion_settings import BOOT_BLADE_SLEEP, DNS_DOMAIN_NAME, \
    LOOP_SLEEP, POST_ILO_SLEEP, REPORT_FILE, UNLOCK_NEXT_NODE_SLEEP, \
    WAIT_FOR_SERIAL_SLEEP, VCS_TIMEOUT, PING_TIMEOUT, SHUTDOWN_TIMEOUT, \
    SERIAL_TIMEOUT
from h_expansion.expansion_utils import get_bays_from_server_output, \
    get_info_from_network_output, ExpansionException, progress_bar, \
    display_time, get_ilo_bays_from_ebipa_output
from h_puppet.mco_agents import EnminstAgent, VcsCmdApiAgent, McoAgentException
from h_util.h_utils import ping, exec_process
from h_vcs.vcs_cli import Vcs
from h_vcs.vcs_utils import filter_tab_data, VCS_GRP_SVS_STATE_OFFLINE, \
    VcsCodes, VcsStates
from switch_db_groups import switch_dbcluster_groups

LOGGER = logging.getLogger("enminst")


def get_system_names(nodes):
    """
    Return a string listed in 'nodes'
    :param nodes: List of Blade objects
    :type nodes: list
    :return string of space separated hostnames
    """
    node_str = [b.hostname for b in nodes]
    node_str = ' '.join(node_str)
    return node_str


def boot_systems(bays, enclosure_oa):
    """
    Boot all systems in the provided list of bays
    :param bays: List of bay numbers to boot
    :type bays: list
    :param enclosure_oa: oa to boot system on
    :type enclosure_oa: OnboardAdmininstratorHandler object
    :return None
    """
    LOGGER.debug('Entered boot_systems')
    LOGGER.info('Powering on the Blades in the following bays: %s', bays)
    for bay in bays:
        try:
            LOGGER.info('Powering on blade in bay %s', bay)
            enclosure_oa.power_on_system(bay)
            LOGGER.info('Blade powered on')
        except (OSError, IOError) as err:
            LOGGER.error('Failed to power on blade: %s', err)
            raise
    LOGGER.info('Blades powered on')
    return


def run_hwcomm(sed, component):
    """
    Run the hwcomm script to configure the OA and VCs
    :param sed: Path to SED file
    :type sed: str
    :param component: The HWcomm component to run e.g. configure_oa
    :type component: str
    """
    LOGGER.debug('Entered run_hwcomm')
    cmd = '/opt/ericsson/hw_comm/bin/hw_comm.sh -y {0} {1}'.format(component,
                                                                   sed)
    LOGGER.info('Running %s, this may take several minutes', cmd)
    try:
        stdout = exec_process(cmd.split())
    except(IOError, OSError) as err:
        LOGGER.error('hw_comm.sh failed with: %s', err)
        raise
    LOGGER.info('Hwcomm script completed successfully:\n%s', stdout)
    return stdout


def wait_for_ping(nodes):
    """
    Wait until all Blades are pingable
    :param nodes: List of Blade objects to unlock
    :type nodes: list
    :return None
    """
    LOGGER.debug('Entered wait_for_ping')
    # Wait for blades to shut down
    # error_count = 0
    # max_errors = 3  still to implement
    completed_blades = []
    start_time = datetime.now()
    log_blades = get_system_names(nodes)
    LOGGER.info('Waiting to ping these Blades: %s', log_blades)
    while True:
        for node in nodes:
            LOGGER.info('total: %s  completed: %s', len(nodes),
                        len(completed_blades))
            if node.hostname in completed_blades:
                continue

            if ping(node.hostname):
                LOGGER.info('%s is now pinging', node.hostname)
                completed_blades.append(node.hostname)
                if len(completed_blades) == len(nodes):
                    LOGGER.info('All systems are pinging')
                    return
                continue

            LOGGER.info('%s is not yet pingable', node.hostname)
            current_time = datetime.now()
            elapsed_secs = (current_time - start_time).seconds
            if elapsed_secs > PING_TIMEOUT:
                LOGGER.error('Not all nodes became pingable in time')
                raise ExpansionException('Not all Blades are pingable')
        sleep(LOOP_SLEEP)


def vcs_running(hostname):
    """
    Check if VCS is running on a system
    :param hostname: The hostname to unlock
    :type hostname: str
    :return bool, True if VCS is running
    """
    agent = EnminstAgent()
    LOGGER.info('Checking if VCS is running on %s', hostname)
    try:
        _, states = agent.hasys_state(hostname)
        state = [d['State'][0] for d in states if d['Name'] == hostname][0]
        if state == VcsStates.RUNNING:
            LOGGER.info('VCS is running')
            return True
        else:
            LOGGER.warning('VCS state is %s', state)
            return False
    except (McoAgentException, KeyError, IndexError) as err:
        LOGGER.debug('VCS is not running, exception is: %s', err)
        return False


def wait_for_vcs(nodes):
    """
    Wait until VCS is running on the nodes
    :param nodes: List of Blades to wait for
    :type nodes: list
    :return None
    """
    # Wait for Blades to shut down
    # error_count = 0
    # max_errors = 3  still to implement
    completed_blades = []
    start_time = datetime.now()
    log_blades = get_system_names(nodes)
    LOGGER.info('Waiting for VCS to start on these Blades: %s', log_blades)
    while True:
        for node in nodes:
            LOGGER.info('total: %s  completed: %s', len(nodes),
                        len(completed_blades))
            if node.hostname in completed_blades:
                continue

            if vcs_running(node.hostname):
                LOGGER.info('VCS is now running on %s',
                            node.hostname)
                completed_blades.append(node.hostname)
                if len(completed_blades) == len(nodes):
                    LOGGER.info('VCS has started on all systems')
                    return
                continue

            LOGGER.info('VCS not yet running on: %s', node.hostname)
            current_time = datetime.now()
            elapsed_secs = (current_time - start_time).seconds
            if elapsed_secs > VCS_TIMEOUT:
                LOGGER.error('VCS did not start  on all the Blades')
                # notify user to fix the problem and rerun
                raise ExpansionException('VCS did not start on all Blades')
        sleep(LOOP_SLEEP)


def unlock_system(hostname):
    """
    Unlock a VCS system
    :param hostname: The hostname to unlock
    :type hostname: str
    :return None
    """
    # vcs_system can be a regex
    agent = VcsCmdApiAgent()
    LOGGER.info('Unlocking %s', hostname)
    try:
        agent.unlock(hostname, 300)
        LOGGER.info('Unlocked %s', hostname)
    except McoAgentException as err:
        LOGGER.error('Failed to unlock %s: %s', hostname, err)
        raise
    LOGGER.info('%s is now unlocked', hostname)
    return


def unlock_systems(nodes):
    """
    Unlock all VCS systems listed in 'nodes'
    :param nodes: List of Blade objects to unlock
    :type nodes: list
    :return None
    """
    log_blades = get_system_names(nodes)
    LOGGER.info('Unlocking the following Blades: %s', log_blades)

    first_iteration = True
    for node in nodes:
        if first_iteration:
            first_iteration = False
        else:
            LOGGER.info('Sleeping for %s before unlocking next node',
                        display_time(UNLOCK_NEXT_NODE_SLEEP))
            progress_bar(UNLOCK_NEXT_NODE_SLEEP)

        LOGGER.info('Unlocking %s', node.hostname)
        unlock_system(node.hostname)
    LOGGER.info('All Blades unlocked')
    return


def freeze_system(hostname):
    """
    Freeze and evacuate a VCS system
    :param hostname: The hostname to freeze
    :type hostname: str
    :return None
    """
    agent = EnminstAgent()

    try:
        LOGGER.info('Freezing: %s', hostname)
        agent.hasys_freeze(hostname, persistent=True, evacuate=True)
        LOGGER.info('Successfully froze: %s', hostname)
    except McoAgentException as error:
        if VcsCodes.is_error(VcsCodes.V_16_1_40206, error):
            LOGGER.warning('%s is already persistently frozen', hostname)
            return
        LOGGER.error('Failed to freeze %s: %s', hostname, error)
        raise
    LOGGER.info('%s is now frozen', hostname)
    return


def freeze_systems(nodes):
    """
    Freeze and evacuate all systems listed in 'nodes'
    :param nodes: List of Blade objects to freeze
    :type nodes: list
    :return None
    """
    # Freeze each blade
    log_blades = get_system_names(nodes)
    LOGGER.info('Freezing the following Blades: %s', log_blades)
    for node in nodes:
        freeze_system(node.hostname)
    LOGGER.info('All Blades frozen')
    return


def services_offline(hostname):
    """
    Check if all VCS services are offline on a node
    :param hostname: The hostname to check
    :type hostname: str
    :return bool, True if all VCS services are offline
    """
    sys_filter = '^{0}$'.format(hostname)
    view_type = 'v'
    LOGGER.info('Checking service groups on %s', hostname)
    vcs_info, _ = Vcs.get_cluster_group_status(system_filter=sys_filter,
                                               view_type=view_type)
    vcs_info = filter_tab_data(vcs_info, sys_filter, Vcs.H_SYSTEM)
    vcs_info = Vcs.neo4j_health_check(vcs_info)
    states = [v['ServiceState'] for v in vcs_info]
    LOGGER.debug('%s has states of %s', hostname, states)
    return all(s == VCS_GRP_SVS_STATE_OFFLINE for s in states)


def wait_for_offline_services(nodes):
    """
    Wait for all systems listed in 'nodes' to have their VCS services offline
    :param nodes: List of Blade objects to wait for
    :type nodes: list
    :return None
    """
    # Wait until services are stopped before continuing
    start_time = datetime.now()
    completed_blades = []
    error_count = 0
    max_errors = 3
    LOGGER.info('Waiting for VCS services to OFFLINE on blades')

    while True:
        for node in nodes:
            LOGGER.info('total: %s  completed: %s', len(nodes),
                        len(completed_blades))
            if node.hostname in completed_blades:
                continue

            try:
                if services_offline(node.hostname):
                    LOGGER.info('%s services are now offline', node.hostname)
                    completed_blades.append(node.hostname)
                    if len(completed_blades) == len(nodes):
                        LOGGER.info('All Blades services are now offline')
                        return
                    continue

            except McoAgentException as err:
                # If comm failure checking then don't necessarily
                #  want to exit immediately
                error_count += 1
                if error_count >= max_errors:
                    LOGGER.error('Failed checking services on %s: %s',
                                 node.hostname, err)
                    raise

            LOGGER.debug('%s still has services running on it', node.hostname)
            current_time = datetime.now()
            elapsed_secs = (current_time - start_time).seconds
            if elapsed_secs > VCS_TIMEOUT:
                LOGGER.error('Timed out waiting for services to offline')
                # notify user to fix the problem and rerun
                raise ExpansionException('Services did not offline in time')
        sleep(LOOP_SLEEP)


def shutdown_systems(nodes):
    """
    Shutdown all systems listed in 'nodes'
    :param nodes: List of Blade objects to shutdown
    :type nodes: list
    :return None
    """
    # Issue shutdown to each blade
    log_blades = get_system_names(nodes)
    LOGGER.info('Sending shutdown to: %s', log_blades)
    agent = EnminstAgent()

    for node in nodes:
        if not ping(node.hostname):
            LOGGER.info('%s is already shut down', node.hostname)
            continue
        try:
            LOGGER.info('Shutting down %s', node.hostname)
            agent.shutdown_host(node.hostname)
            LOGGER.info('Issued shutdown request')
        except McoAgentException as error:
            LOGGER.error('shutdown of %s failed: %s', node.hostname, error)
            raise
    LOGGER.info('All systems have received the shutdown request')
    return


def wait_for_shutdown(nodes):
    """
    Wait for all systems listed in 'nodes' to shutdown
    :param nodes: List of Blade objects to wait for
    :type nodes: list
    :return None
    """
    LOGGER.debug('Entered wait_for_shutdown')
    # Wait for Blades to shut down
    completed_blades = []
    start_time = datetime.now()
    log_blades = get_system_names(nodes)
    LOGGER.info('Waiting for the following Blades to shutdown: %s', log_blades)
    while True:
        for node in nodes:
            if node.hostname in completed_blades:
                continue

            if not ping(node.hostname):
                LOGGER.info('%s is now shut down', node.hostname)
                completed_blades.append(node.hostname)
                if len(completed_blades) == len(nodes):
                    LOGGER.info('All Blades shut down SUCCESSFULLY')
                    return
                continue

            LOGGER.info('%s is still shutting down', node.hostname)
            current_time = datetime.now()
            elapsed_secs = (current_time - start_time).seconds
            if elapsed_secs > SHUTDOWN_TIMEOUT:
                LOGGER.error('Not all Blades have shutdown in time')
                raise ExpansionException('Blades failed to shut down in time')
        sleep(LOOP_SLEEP)


def freeze_and_shutdown_systems(nodes, freeze=True):
    """
    Freeze and shutdown  systems listed in 'nodes'
    :param nodes: List of Blade objects to wait for
    :type nodes: list
    :param freeze: If VCS freeze is to be performed
    :type freeze: bool
    :return None
    """
    LOGGER.debug('Entered freeze_and_shutdown_systems')
    try:
        if freeze:
            err_text = 'Failed to freeze all the Blades'
            freeze_systems(nodes)
            err_text = 'Failed to offline all the Blades'
            wait_for_offline_services(nodes)

        err_text = 'Failed to shutdown all the Blades'
        shutdown_systems(nodes)
        err_text = 'Failed waiting on the Blades shutdown'
        wait_for_shutdown(nodes)
    except McoAgentException as err:
        LOGGER.error('%s: %s', err_text, err)
        raise
    except Exception as err:
        LOGGER.error('Unexpected exception, %s: %s', err_text, err)
        raise
    LOGGER.info('All Blades frozen and shut down')
    return


def get_new_blade_bays(server_output):
    """
    Parse the report file to see what bays were originally in use
    and compare with current OA output from SHOW SERVER NAMES
    to determine which bays contain the newly moved Blades
    :param server_output: output from OA command
    :type server_output: string
    :return bays (list of blade numbers)
    """
    LOGGER.debug('Entered get_new_blade_bays')
    with open(REPORT_FILE, 'r') as rep:
        report_contents = rep.read()
    LOGGER.debug('Server names: %s', server_output)
    LOGGER.debug('=================================================')
    LOGGER.debug('Report contents: %s', report_contents)

    orig_bays = get_bays_from_server_output(report_contents)
    LOGGER.debug('Server names:\n%s', server_output)
    LOGGER.debug('orig_bays = %s', orig_bays)
    current_bays = get_bays_from_server_output(server_output)
    LOGGER.debug('current_bays = %s', current_bays)

    bays = list(set(current_bays) - set(orig_bays))
    bays.sort()
    LOGGER.info('The new Blades are in bays: %s', bays)
    return bays


def set_correct_bays(nodes, enclosure_oa):
    """
    Set the correct dest_bay numbers for the Blades using the serial
    and bay numbers from the OA
    :param nodes: List of Blade objects
    :type nodes: list
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :return None
    """
    LOGGER.debug('Entered set_correct_bays')
    # get bay and serial number information from enclosure
    LOGGER.info('Checking blade serial numbers')
    server_output = enclosure_oa.show_server_names()
    bay_serial_dict = get_bays_from_server_output(server_output)
    LOGGER.info('bay_serial_dict = %s', bay_serial_dict)

    # Iterate through nodes and set the dest_bay from the OA info
    # in the bay_serial_dict
    change_bay_nodes = []
    for node in nodes:
        LOGGER.info('%s has bay of %s', node.sys_name, node.dest_bay)
        # Compare serial number of node with serial num found in expected bay
        if node.dest_bay == 'Unknown' or \
                node.serial_no != bay_serial_dict[node.dest_bay]:
            old_dest_bay = node.dest_bay
            node.dest_bay = [k for k, v in bay_serial_dict.iteritems()
                             if v == node.serial_no][0]
            LOGGER.info('Changing %s bay from %s to %s', node.sys_name,
                        old_dest_bay, node.dest_bay)
            change_bay_nodes.append(node)
        else:
            LOGGER.info('The bay is already set correctly')
    LOGGER.info('All Blades have the correct bays')
    return change_bay_nodes


def configure_ebipa(nodes, enclosure_oa, gateway, netmask, domain):
    """
    Configure the Blades' Ebipa/iLO addresses and perform an efuse reset
    :param nodes: List of Blade objects
    :type nodes: list
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :param: gateway: Gateway for iLO
    :type gateway: string
    :param: netmask: Netmask for iLO
    :type netmask: string
    :param: domain: Domain for iLO
    :type domain: string
    :return None
    """
    LOGGER.debug('Entered configure_ebipa')
    for node in nodes:
        LOGGER.info('Setting bay %s to IP %s', node.dest_bay, node.dest_ilo)
        enclosure_oa.set_ebipa_server(node.dest_bay, node.dest_ilo, netmask,
                                      gateway, domain)

        LOGGER.info('%s EBIPA configured (%s)', node.hostname, node.sys_name)
    enclosure_oa.save_ebipa()
    LOGGER.info('EBIPA saved')
    for node in nodes:
        enclosure_oa.efuse_reset(node.dest_bay)
    LOGGER.info('EBIPA configured for all Blades')
    return


def check_ilos_not_configured(nodes, enclosure_oa):
    """
    Check that no Blade iLO addresses are configured in the enclosure
    :param nodes: List of Blade objects
    :type nodes: list
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :return None
    """
    LOGGER.debug('Entered check_ilos_not_configured')
    ebipa_out = enclosure_oa.show_ebipa_server()
    ilos_bays = get_ilo_bays_from_ebipa_output(ebipa_out)

    ilo_in_use = False
    for node in nodes:
        if node.dest_ilo in ilos_bays.keys():
            LOGGER.error('The iLO IP %s is already configured in bay %s',
                         node.dest_ilo, ilos_bays[node.dest_ilo])
            ilo_in_use = True

    if ilo_in_use:
        raise ExpansionException('Required ILO addresses are already in use')

    LOGGER.info('No Blade iLO IPs are configured in the enclosure')
    return


def remove_ebipa_entries(enclosure_oa, bays):
    """
    Remove Ebipa/iLO entries for Blades in bays
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :param: bays: List of bay numbers in the enclosure
    :type bays: List of strings
    :return None
    """
    LOGGER.debug('Disabling EBIPA for bays %s', bays)
    for bay in bays:
        LOGGER.info('Disabling EBIPA in bay %s', bay)
        enclosure_oa.disable_ebipa_server(bay)
    enclosure_oa.save_ebipa()
    LOGGER.info('EBIPA entries disabled for all Blades')
    return


# pylint: disable=R0913
def configure_ilo(nodes, bays, enclosure_oa, gateway, netmask, domain):
    """
    Configure the Blades' iLO addresses
    :param nodes: List of Blade objects
    :type nodes: list
    :param: bays: List of bay numbers in the enclosure
    :type bays: List of strings
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :param: gateway: Gateway for iLO
    :type gateway: string
    :param: netmask: Netmask for iLO
    :type netmask: string
    :param: domain: Domain for iLO
    :type domain: string
    :return None
    """
    LOGGER.debug('Entered configure_ilo')
    LOGGER.info('Tearing down any iLO configuration in the following bays: %s',
                bays)
    # Remove any pre-existing iLO configuration
    remove_ebipa_entries(enclosure_oa, bays)

    # Check the iLO IPs are not configued in any other bay in the enclosure
    check_ilos_not_configured(nodes, enclosure_oa)

    # Assign any of the bays in use to any of the Blades to get the serial
    # numbers.  Until we get the serial numbers we don't know which Blade
    # is in which bay.
    for node, bay in zip(nodes, bays):
        LOGGER.info('Setting %s bay temporarily to %s', node.sys_name, bay)
        node.dest_bay = bay

    LOGGER.info('Assigning arbitrary iLO IPs to get blade serial numbers')
    configure_ebipa(nodes, enclosure_oa, gateway, netmask, domain)
    LOGGER.info('Sleeping for %s before retrieving serial numbers',
                display_time(WAIT_FOR_SERIAL_SLEEP))
    progress_bar(WAIT_FOR_SERIAL_SLEEP)

    # Now we have the serial numbers the correct Blade bays can be set
    nodes_to_assign_ip = set_correct_bays(nodes, enclosure_oa)
    if not nodes_to_assign_ip:
        LOGGER.info('All blade iLOs set correctly')
        return

    # Tear down temporary iLO config and configure correct iLO config
    LOGGER.info('Tearing down temporary iLO configuration in the Blades')
    remove_ebipa_entries(enclosure_oa, bays)
    check_ilos_not_configured(nodes, enclosure_oa)
    LOGGER.info('Assigning correct iLO IPs to Blades')
    configure_ebipa(nodes_to_assign_ip, enclosure_oa, gateway, netmask, domain)
    LOGGER.info('All iLO IPs now assigned')
    return


def get_network_info(enclosure_oa, sed):
    """
    Get domain from SED, and gateway & netmask from OA
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :param: sed: Path to SED
    :type sed: string
    :return tuple containing gateway, netmask & domain
    """
    LOGGER.info('Getting network information from the OA')
    sed_handler = ExpansionSedHandler(sed)
    domain = sed_handler.get_sed_entry(DNS_DOMAIN_NAME)
    network_info = enclosure_oa.show_oa_network()
    gateway, netmask = get_info_from_network_output(network_info)
    LOGGER.info('Gateway: %s, Netmask: %s, Domain: %s',
                gateway, netmask, domain)
    return gateway, netmask, domain


def serial_numbers_ok(bays, enclosure_oa):
    """
    Check that serial numbers are present in the relevant bays
    :param bays: Dict of bay:serial numbers
    :type bays: dict
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :return Bool, True if all bays are showing Blade serial numbers
    """
    LOGGER.debug('Checking serial numbers in bays: %s', bays)
    server_output = enclosure_oa.show_server_names()
    bays_serial = get_bays_from_server_output(server_output)
    relevant_bays_serial = {}
    for bay, serial in bays_serial.iteritems():
        if bay in bays:
            relevant_bays_serial[bay] = serial

    serials = [s for s in relevant_bays_serial.values() if s != '[Unknown]']
    LOGGER.debug('Serial numbers are %s', relevant_bays_serial.values())
    LOGGER.info('We have %s serial numbers for %s bays',
                len(serials), len(bays))
    return len(serials) == len(bays)


def wait_for_serials(bays, enclosure_oa):
    """
    Wait until serial numbers are visible on the OA
    :param bays: List of bay numbers
    :type bays: List
    :param: enclosure_oa: OA Handler object
    :type enclosure_oa: OnboardAdminstratorHandler
    :return None
    """
    start_time = datetime.now()
    LOGGER.info('Waiting for OA to show Blade serial numbers')
    while True:
        if serial_numbers_ok(bays, enclosure_oa):
            LOGGER.info('All serial numbers present on the OA')
            return

        LOGGER.info('Still waiting for serial numbers')
        current_time = datetime.now()
        elapsed_secs = (current_time - start_time).seconds
        if elapsed_secs > SERIAL_TIMEOUT:
            LOGGER.error('Serial numbers did not show in time')
            raise ExpansionException('Serial numbers are missing on the OA')
        sleep(LOOP_SLEEP)


def boot_systems_and_unlock_vcs(nodes, enclosure_oa, sed, rollback):
    """
    Power and unlock systems listed in 'nodes'
    :param nodes: List of Blade objects to wait for
    :type nodes: list
    :param enclosure_oa:
    :type: OnboardAdminstratorHandler object
    :param sed: Path to SED
    :param rollback: if rollback action is being performed
    :type rollback: bool
    :return None
    """
    LOGGER.debug('Entered boot_systems_and_unlock_vcs')
    LOGGER.info('Checking the OA for new Blades')
    server_output = enclosure_oa.show_server_names()

    if rollback:
        LOGGER.info('Rollback, getting bays from Blade objects')
        bays = [b.dest_bay for b in nodes]
    else:
        LOGGER.info('Getting bay informataion from OA')
        bays = get_new_blade_bays(server_output)
        LOGGER.info('New Blades found in the following bays: %s', bays)
        if len(bays) != len(nodes):
            LOGGER.error('Expected %s new Blades but found %s in enclosure',
                         len(nodes), len(bays))
            raise ExpansionException('Unexpected number of new Blades found')

    if rollback:
        LOGGER.info('Rollback, skipping iLO configuration, powering on Blades')
    else:
        gateway, netmask, domain = get_network_info(enclosure_oa, sed)
        LOGGER.info('Configuring the iLO')
        configure_ilo(nodes, bays, enclosure_oa, gateway, netmask, domain)
        LOGGER.info('Sleeping for %s minutes for OA server info to be updated',
                    display_time(POST_ILO_SLEEP))
        progress_bar(POST_ILO_SLEEP)

        wait_for_serials(bays, enclosure_oa)
        output = run_hwcomm(sed, 'configure_oa')
        if 'WARNING: The SED Serial numbers' in output:
            raise ExpansionException('hw_comm cannot see all serial numbers')
        wait_for_serials(bays, enclosure_oa)
        output = run_hwcomm(sed, 'configure_vc')
        if 'WARNING: The SED Serial numbers' in output:
            raise ExpansionException('hw_comm cannot see all serial numbers')

    wait_for_serials(bays, enclosure_oa)
    LOGGER.info('Powering on Blades')

    boot_systems(bays, enclosure_oa)
    LOGGER.info('Sleeping for %s while Blades boot',
                display_time(BOOT_BLADE_SLEEP))
    progress_bar(BOOT_BLADE_SLEEP)

    LOGGER.info('Waiting until nodes become pingable')
    wait_for_ping(nodes)
    LOGGER.info('Waiting for VCS to start')
    wait_for_vcs(nodes)
    LOGGER.info('VCS started, unlocking nodes')
    unlock_systems(nodes)
    LOGGER.info('Balancing DB cluster service groups')
    switch_dbcluster_groups()
    LOGGER.info('Booting Blades and enabling VCS completed successfully')
