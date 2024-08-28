"""
The purpose of this script is create both private and public SSH keys for
each KVM and populate the model with the key chain.
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
# Name    : ssh_key_creation.py
# Purpose : The purpose of this script is create both private and public
# SSH keys for each KVM and populate the model with the key chain.
##############################################################################
import os
import sys
from base64 import b64encode
import fileinput
import argparse
from M2Crypto import RSA
import re

from h_litp.litp_rest_client import LitpRestClient, LitpException, LitpObject
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import logging, log_header, init_enminst_logging
from h_util.h_utils import read_enminst_config, EnminstWorking, \
    keyboard_interruptable, ExitCodes

LOGGER = init_enminst_logging()


class SshCreation(object):
    """
    Class to run the creation of ssh keys

    """
    PARAMS_FILE = 'enminst_working_parameters'
    SSH_PATH = '/root/.ssh/'
    PRIVATE_KEY_FILE = SSH_PATH + 'vm_private_key'
    PUBLIC_KEY_FILE = PRIVATE_KEY_FILE + '.pub'
    SOFTWARE_SERVICES_PATH = '/software/services'
    MS_SERVICES_PATH = '/ms/services'
    SSH_KEY_PATH = '/vm_ssh_keys/vm-ssh-key-id'
    KEY_ITEM_TYPE_NAME = 'item-type-name'
    KEY_PROPERTIES = 'properties'
    SSH_KEY_SOURCE = 'ssh_key'

    def __init__(self):
        """
        Initializes instance
        """
        super(SshCreation, self).__init__()
        self.log = logging.getLogger('enminst')
        self.config = read_enminst_config()
        self.litp = LitpRestClient()

    def get_ssh_key_value(self):
        """
        Generates both private and public keys. Stores the private key in
        a path on the LMS (and changes its access rights) and returns
        the public key.
        :returns: Public key
        :rtype: str
        """
        self.log.info('Generating SSH Key')
        if not os.path.isdir(self.SSH_PATH):
            try:
                os.mkdir(self.SSH_PATH)
                os.chmod(self.SSH_PATH, 0700)
                self.log.info('Created path: {0} '.format(self.SSH_PATH))
            except OSError:
                self.log.exception('Unable to create path: {0} '
                                   .format(self.SSH_PATH))
                raise SystemExit(ExitCodes.ERROR)
        try:
            key = RSA.gen_key(2048, 65537)
            b64key = b64encode('\x00\x00\x00\x07ssh-rsa%s%s' % (key.pub()[0],
                                                                key.pub()[1]))
            key.save_key(self.PRIVATE_KEY_FILE, cipher=None)
            host = 'cloud-user'
            self.log.info('Private SSH key has been successfully '
                          'created & stored in {0}'
                          .format(self.PRIVATE_KEY_FILE))
            public_key = 'ssh-rsa %s %s' % (b64key, host)
            with open(self.PUBLIC_KEY_FILE, 'w+') as public_file:
                public_file.write(public_key)
            os.chmod(self.PRIVATE_KEY_FILE, 0600)
            os.chmod(self.PUBLIC_KEY_FILE, 0600)
            self.log.info('Public key has been successfully generated.')
        except OSError as error:
            self.log.error('Unable to generate SSH key. Exiting ...')
            raise SystemExit(error)
        return public_key

    def collect_all_vm_service_paths(self, litp_path):
        """
        Collects all VM service paths that already have ssh keys stored
        in their model dictionary. Generates initially a list of services
        and from the checks if the child has keys stored
        :return: dictionary mapping VM service paths
        :rtype: list
        """
        all_vm_service_paths = []
        service_items = self.litp.get_children(litp_path)
        for service_item in service_items:
            vm_lo = LitpObject(None, service_item['data'],
                               self.litp.path_parser)
            if vm_lo.item_type == 'vm-service':
                vm_path = vm_lo.path + '/vm_ssh_keys'
                vm_path_list = self.litp.get_children(vm_path)
                for path in vm_path_list:
                    ssh_lo = LitpObject(None, path['data'],
                                        self.litp.path_parser)
                    if ssh_lo.item_type == 'vm-ssh-key':
                        full_vm_path = vm_path + '/' + ssh_lo.item_id
                        all_vm_service_paths.append(full_vm_path)
        return all_vm_service_paths

    def regenerate_keys(self, pubkey, list_of_paths, no_litp_plan=False):
        """
        Executes the litp update command to update the ssh keys. The litp
        create, run and monitor plan is executed there after
        :param pubkey: public key which has been generated
        :param list_of_paths: litp path that will be updated
        :param no_litp_plan: If `True` only make the model updates and dont
        create/run a plan. If `False` then create/run a plan to push the
        changes to the VMs.
        """
        self.log.info("Beginning regeneration of SSH Keys ")
        for model_path in list_of_paths:
            try:
                self.litp.update(model_path, {'ssh_key': pubkey},
                                 verbose=False)
            except LitpException as error:
                self.log.error('Failed to update the LITP model with '
                               'regenerated SSH keys')
                raise SystemExit(error)
        if no_litp_plan is False:
            self.log.info('Beginning to create and run the plan')
            self.create_run_plan()

    def create_run_plan(self):
        """
        Create an run a plan and wait for it tom complete.
        :return:
        """
        try:
            self.litp.create_plan('plan')
            self.litp.set_plan_state('plan', 'running')
            self.litp.monitor_plan('plan')
        except LitpException as error:
            self.log.error('Failed to upgrade SSH keys for ENM')
            raise SystemExit(error)

    def update_enminst_working(self, params_file):
        """
        Update the enminst_working.cfg file with the path to the
        SSH Public Key.
        :param params_file: Path to the enminst_working.cfg
        :type params_file: str
        :return: public ssh key
        :rtype: str
        """
        log_header(self.log, 'Getting SSH Key for KVMs')
        ssh_key = self.get_ssh_key_value()
        ssh_key_param = "vm_ssh_key"
        cfg = EnminstWorking(params_file)
        cfg.set_site_key(ssh_key_param,
                         'file://{0}'.format(self.PUBLIC_KEY_FILE))
        cfg.write()
        self.log.info('SSH Key successfully fetched.')
        return ssh_key

    def check_enminst_working(self, params_file):
        """
        Check the enminst_working.cfg file for the SSH Key.
        :param params_file: Path to the enminst_working.cfg
        :type params_file: str
        """
        self.log.info('Checking runtime config file for SSH Key')
        ssh_key_param = 'vm_ssh_key='
        cfg = EnminstWorking(params_file)
        cfg_file = cfg.get_file()
        value = ''
        for search in open(cfg_file):
            _match = re.match(ssh_key_param + '(.*)', search)
            if _match:
                value = _match.group(1)
        if 'ssh-rsa' in value:
            for line in fileinput.FileInput(cfg_file, inplace=1):
                if ssh_key_param in line and value is not None:
                    sys.stdout.write('{0}file://{1}\n'.format(
                            ssh_key_param, self.PUBLIC_KEY_FILE))
                else:
                    sys.stdout.write(line)
            with open(self.PUBLIC_KEY_FILE, 'w') as _writer:
                _writer.write('{0}\n'.format(value))
        with open(cfg_file) as reader:
            return ssh_key_param in reader.read()

    def manage_ssh_action(self, regenerate=False, no_litp_plan=False):
        """
        Manages ssh_action performing dedicated actions
        :param regenerate: used to regenerate private and public
        :param no_litp_plan: If `True` create and run the plan otherwise done
        create/run a plan
        keys and config file if required.
        """
        parameters = self.config['enminst_working_parameters']
        if regenerate:
            list_of_service_paths = \
                self.collect_all_vm_service_paths(self.SOFTWARE_SERVICES_PATH)
            list_of_service_paths.extend( \
                self.collect_all_vm_service_paths(self.MS_SERVICES_PATH))
            if list_of_service_paths:
                pub_key = self.update_enminst_working(parameters)
                self.regenerate_keys(pub_key, list_of_service_paths,
                                     no_litp_plan)
            else:
                self.log.info('No SSH Keys to regenerate. Exiting ...')
        else:
            if not self.check_enminst_working(parameters):
                self.log.info('Creating SSH Keys ...')
                self.update_enminst_working(parameters)


def create_argument_parser():
    """
    Creates and configures parser to process command line arguments
    :return: argument parser instance
    :rtype ArgumentParser
    """
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--regenerate', action='store_true', default=False,
                            help="Enable regeneration of SSH Keys")
    arg_parser.add_argument('--no_litp_plan', action='store_true',
                            default=False,
                            help="Ensure the LITP plan is not executed")
    return arg_parser


def interrupt_handler():
    """
    Callback for when CTRL-c is detected
    :return:
    """
    LOGGER.warning('CTRL-C: SSH Key creation interrupted.'
                   ' Please re-run again to ensure everything is completed.')


@keyboard_interruptable(callback=interrupt_handler)
def main(args):
    """
    Main function.
    Runs ssh key operation depending on the argument given.
    :param args: sys args
    """
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args[1:])
    ssh = SshCreation()
    ssh.manage_ssh_action(regenerate=parsed_args.regenerate,
                          no_litp_plan=parsed_args.no_litp_plan)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
