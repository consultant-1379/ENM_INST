"""
Class to handle deployment operations
"""
##############################################################################
# COPYRIGHT Ericsson AB 2015
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import logging
import sys
from datetime import datetime

from argparse import ArgumentParser

from h_litp.litp_rest_client import LitpRestClient, LitpException, LitpObject
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_util.h_utils import is_valid_file, \
    keyboard_interruptable, ExitCodes, time_delta
from import_iso_version import update_enm_version_and_history,\
                               create_litp_history

_PLAN_RUNNING = False
_PLAN_TYPE = 'N/A'
_LOGGER = None


def init_logging(verbose):
    """
    Setup a logger
    :param verbose: Verbose or not
    :return:
    """
    global _LOGGER  # pylint: disable=W0603
    _LOGGER = init_enminst_logging()
    if verbose:
        set_logging_level(_LOGGER, 'DEBUG')


def get_logger():
    """
    Get the logger
    :return:
    """
    global _LOGGER  # pylint: disable=W0602,W0603
    return _LOGGER


def set_plan_type(plan_type):
    """
    Set the plan type
    :param plan_type: The plan type i.e. install/upgrade/etc.
    :return:
    """
    global _PLAN_TYPE  # pylint: disable=W0603
    _PLAN_TYPE = plan_type


def get_plan_type():
    """
    Get the plan type
    :return:
    """
    global _PLAN_TYPE  # pylint: disable=W0602,W0603
    return _PLAN_TYPE


def is_plan_running():
    """
    Check if the plan has been started
    :return:
    """
    global _PLAN_RUNNING  # pylint: disable=W0602,W0603
    return _PLAN_RUNNING


def set_plan_running(is_running):
    """
    Set flag indicating if the plan has been started or not
    :param is_running: `True` is the plan has been started, `False` otherwise
    :return:
    """
    global _PLAN_RUNNING  # pylint: disable=W0603
    _PLAN_RUNNING = is_running


class DeployerException(Exception):
    """ Deployment failed """
    pass


class Deployer(object):
    """
    This class is used to take a populated model XML and load it into LITP,
    followed by a plan creation and execution. It will display the status of
    the plan as it executes
    """
    INST_UPG_PLAN_NAME = 'plan'
    REMOTE_EXECUTION = False

    def __init__(self, litpd_host='localhost',
                 litpd_port=LitpRestClient.DEFAULT_LITPD_PORT):

        self.log = logging.getLogger('enminst')
        self.litpd_host = litpd_host
        self.litpd_port = litpd_port
        self.litp = LitpRestClient(litpd_host=self.litpd_host,
                                   litpd_port=self.litpd_port)

        if self.litpd_host != 'localhost':
            Deployer.REMOTE_EXECUTION = True

    def enable_litp_debug(self):
        """
        Sets LITP log level to 'debug'
        :return: Returns nothing
        """
        self.litp.set_debug('debug')

    def load_xml(self, load_point, xml_file):
        """
        Loads the specified model XML into / in LITP, using the merge=True
        paramater
        :param xml_file: The XML file to load
        :param load_point: The path in the model to load the XML into
        :return: Returns nothing
        """
        try:
            func_start_time = datetime.now().replace(microsecond=0)
            self.log.info('Loading {0} into {1} (merge=True)'
                          .format(xml_file, load_point))
            self.litp.load_xml(load_point, xml_file, merge=True)
            self.exec_time('XML load', func_start_time)
        except LitpException as exception:
            if isinstance(exception.args[1], dict):
                error_details = exception.args[1]
                if 'messages' in error_details:
                    for error in error_details['messages']:
                        if isinstance(error, dict):
                            msg = '{0} {1}'.format(error['message'],
                                                   error['uri'])
                        else:
                            msg = '{0}'.format(error)
                        self.log.error(msg)
                else:
                    for _key, _value in exception.args[1].items():
                        self.log.error('\t{0} -> {1}\n'.format(_key,
                                                               _value))
            else:
                self.log.error('{0}'.format(exception.args[1]))
            self.log.error('Failed to load {0} into {1}'.format(
                    xml_file, load_point))
            raise SystemExit(ExitCodes.LOAD_PLAN_FAILED)

    def create_plan(self, no_lock_tasks=None, no_lock_tasks_list=None):
        """
        Creates a LITP plan
        :return: Returns nothing
        """
        try:
            func_start_time = datetime.now().replace(microsecond=0)
            self.log.info('Creating LITP plan: {0}'
                          .format(Deployer.INST_UPG_PLAN_NAME))
            self.litp.create_plan(Deployer.INST_UPG_PLAN_NAME,
                                   no_lock_tasks, no_lock_tasks_list)
            self.exec_time('Plan Creation', func_start_time)
        except LitpException as litp_err:
            if litp_err.args:
                if 'messages' in litp_err.args[1]:
                    for err in litp_err.args[1]['messages']:
                        self.log.error(self._get_error_msg_from_exception(err))
                elif isinstance(litp_err.args[1], dict):
                    for _key, _value in litp_err.args[1]:
                        self.log.error('\t{0} -> {1}\n'.format(_key, _value))
                else:
                    self.log.error(litp_err)
            else:
                self.log.error(litp_err)
            raise SystemExit(ExitCodes.CREATE_PLAN_FAILED)

    def _get_error_msg_from_exception(self, err):
        """
        Parses an error response and returns the
         string error
        :return: Returns a string with the error
        """
        message = ''
        try:
            # CherryPy could return an error with no json format at all
            if isinstance(err, str):
                # if cherrypy sends a traceback it's out of LITP control to
                # handle it. Better than displaying such traceback to the user
                # we better take that last bit with the exact error
                if err.startswith('Unrecoverable error in the server'):
                    message = 'Create plan failed: {0}'.format(err.split()[-1])
                else:
                    message = err
            else:
                obj = LitpObject(None, err, self.litp.path_parser)
                message = '{0} - {1}'.format(obj.path, err['message'])
        except:  # pylint: disable=W0702
            # will happen with some 4XX errors, which might not always
            # have a full HAL format
            message = 'Create plan failed: {0}'.format(err['message'])
        finally:
            return message  # pylint: disable=W0150

    def show_plan(self):
        """
        Displays the current tasks in the plan in order
        :return: Returns nothing
        """
        self.litp.show_plan(Deployer.INST_UPG_PLAN_NAME)

    def run_plan(self):
        """
        Runs the LITP plan
        :return: Returns nothing
        """
        self.litp.set_plan_state(Deployer.INST_UPG_PLAN_NAME, 'running')

    def resume_plan(self):
        """
        Resume the LITP plan
        :return: Returns nothing
        """
        self.litp.set_plan_state(Deployer.INST_UPG_PLAN_NAME, 'running',
                                 resume=True)

    def get_plan_state(self):
        """
        Get the state of a LITP plan
        :return: the state of the LITP plan queried
        """
        return self.litp.get_plan_state(Deployer.INST_UPG_PLAN_NAME)

    def wait_plan_complete(self, verbose=False, resume_plan=False):
        """
        Waits for the LITP plan to complete, showing the user the current
        status and active tasks on standard out
        :return: Returns nothing
        """
        self.litp.monitor_plan(Deployer.INST_UPG_PLAN_NAME, verbose=verbose,
                               resume_plan=resume_plan)

    def reset_litp_debug(self):
        """
        Sets LITP log level to 'info'
        :return: Returns nothing
        """
        self.litp.set_debug('info')

    def exec_time(self, run_type, start_time):
        """
        Calculates how long a particualar part of the script has taken to
        execute, and logs the time in the appropiate logfile
        :param start_time: The datatime timestamp the operation started at
        :param run_type: The execution type; used in loggings
        :return: Returns nothing
        """
        hours, minutes, seconds = time_delta(start_time)
        self.log.info('Completed {0} at {1}'.format(run_type, datetime.now()))
        self.log.info('{0} took {1}h:{2}m:{3}s'
                      .format(run_type, hours, minutes, seconds))

    @staticmethod
    def update_version_and_history():
        """
        Updates files storing ENM version and history of upgrades
        Creates LITP history file if does not exist
        """
        create_litp_history()
        update_enm_version_and_history()


def interrupt_handler():
    """
    Callback for CTRL-c handling
    :return:
    """
    get_logger().error('CTRL-C: Interrupting {0}'.format(get_plan_type()))
    if is_plan_running():
        get_logger().error('Stopping monitoring of {0} plan'.format(
                get_plan_type()))
        get_logger().error('The {0} plan is still executing, '
                           'use \'litp show_plan\' to check status.'
                           .format(get_plan_type()))
        get_logger().error(
                'Further stages of this deployment will not be executed')


def deploy(model_xml=None,  # pylint: disable=R0912, R0913
           verbose=False,
           litpd_host=LitpRestClient.DEFAULT_LITPD_HOST,
           load_plan=False,
           load_create_plan=False,
           create_run_plan=False,
           run_type='ENM Deployment',
           resume_plan=False,
           no_lock_tasks=None,
           no_lock_tasks_list=None):
    """
    Performs deployment
    :param model_xml: XML file to load in
    :param verbose: Set enminst verbose logging
    :param litpd_host: LMS address
    :param create_run_plan: Only create and run the plan, dont load any xml
    :param load_create_plan: Only load and create the plan, dont run it
    :param load_plan: If `True` only load the XML ans stop
    :param run_type: type of run
    :param resume_plan: Resume a Failed upgrade plan
    """
    set_plan_type(run_type)
    set_plan_running(False)
    init_logging(verbose)

    deployer = Deployer(litpd_host=litpd_host)
    main_start_time = datetime.now().replace(microsecond=0)

    preamble = 'Starting'
    if resume_plan:
        preamble = 'Resuming'

    try:
        get_logger().info(preamble +
                ' {0} at {1}'.format(run_type, datetime.now()))
        if verbose:
            deployer.enable_litp_debug()

        if resume_plan:
            try:
                current_plan_state = str(deployer.get_plan_state())
            except LitpException as litp_err:
                if litp_err.args[1].get('reason') == 'Not Found':
                    get_logger().error(
                        "Cannot Resume Plan. Plan Doesn't Exist")
                raise SystemExit(ExitCodes.ERROR)
            if current_plan_state == 'failed':
                get_logger().info("Resuming Failed LITP Plan")
                deployer.resume_plan()
                deployer.show_plan()
            else:
                get_logger().error(
                    "Cannot Resume Plan in state {0}"
                    .format(current_plan_state)
                )
                raise SystemExit(ExitCodes.ERROR)
        else:
            if not create_run_plan:
                deployer.load_xml('/', model_xml)
                if load_plan:
                    return
            deployer.create_plan(no_lock_tasks, no_lock_tasks_list)
            if load_create_plan:
                deployer.show_plan()
                return
            deployer.run_plan()

        set_plan_running(True)
        deployer.wait_plan_complete(verbose=verbose,
                                    resume_plan=resume_plan)
        set_plan_running(False)
        deployer.exec_time(run_type, main_start_time)
    except Exception:
        get_logger().exception(
                "An error occurred running {0}".format(run_type))
        raise
    finally:
        try:
            deployer.reset_litp_debug()
        except Exception:  # pylint: disable=W0703
            pass


def monitor(verbose=False,
           litpd_host=LitpRestClient.DEFAULT_LITPD_HOST,
           run_type='ENM Deployment - Monitor Plan'):
    """
    Performs deployment monitor
    :param verbose: Set enminst verbose logging
    :param litpd_host: LMS address
    :param run_type: type of run
    """
    set_plan_type(run_type)
    set_plan_running(False)
    init_logging(verbose)

    deployer = Deployer(litpd_host=litpd_host)
    main_start_time = datetime.now().replace(microsecond=0)

    preamble = 'Continuing'

    try:
        get_logger().info(preamble +
                ' {0} at {1}'.format(run_type, datetime.now()))
        if verbose:
            deployer.enable_litp_debug()

        set_plan_running(True)
        deployer.wait_plan_complete(verbose=verbose)
        set_plan_running(False)
        deployer.exec_time(run_type, main_start_time)
    except Exception:
        get_logger().exception(
                "An error occurred running {0}".format(run_type))
        raise
    finally:
        try:
            deployer.reset_litp_debug()
        except Exception:  # pylint: disable=W0703
            pass


def get_plan_state(litpd_host=LitpRestClient.DEFAULT_LITPD_HOST):
    """
    Get the state of a LITP plan
    :param litpd_host: LMS address
    :return: the state of the LITP plan queried
    """
    return Deployer(litpd_host=litpd_host).get_plan_state()


def create_parser():
    """
    Creates and configures argument parser
    :return: argument parser instance
    :rtype ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument('--model_xml', dest='model_xml', required=True,
                        type=lambda x:
                        is_valid_file(parser, 'model_xml', x),
                        help='Populated deployment model XML file')
    parser.add_argument('--sed', dest='sed', required=True,
                        type=lambda x:
                        is_valid_file(parser, 'sed', x),
                        help='SED being used to deploy the system')
    parser.add_argument('--litpd_host', dest='litpd_host',
                        default=LitpRestClient.DEFAULT_LITPD_HOST,
                        help='LITPD host, default is \'localhost\'')
    debug_group = parser.add_mutually_exclusive_group()
    debug_group.add_argument('--verbose', action='store_true', default=False,
                             help="Enable all debugging output")
    plan_group = parser.add_mutually_exclusive_group()
    plan_group.add_argument('--load_plan', action='store_true', default=False,
                            help='Loads a LITP plan from a '
                                 'deployment model XML')
    plan_group.add_argument('--load_create_plan', action='store_true',
                            default=False,
                            help='Load and create a LITP plan from a '
                                 'deployment model XML')
    plan_group.add_argument('--create_run_plan', action='store_true',
                            default=False,
                            help='Create and run a LITP plan')
    return parser


@keyboard_interruptable(callback=interrupt_handler)
def main(args):
    """
    Main function parsing command arguments and running deployment
    :param args: configuration of deployment
    :type args: Namespace
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args[1:])
    deploy(model_xml=parsed_args.model_xml,
           litpd_host=parsed_args.litpd_host,
           verbose=parsed_args.verbose,
           load_plan=parsed_args.load_plan,
           load_create_plan=parsed_args.load_create_plan,
           create_run_plan=parsed_args.create_run_plan)


if __name__ == '__main__':
    main(sys.argv)
