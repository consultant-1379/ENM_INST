"""
A program substituting all the parameters in the deployment description
template specified by the user as input
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

from argparse import ArgumentParser
from os.path import exists
import sys
import re
import os
from os.path import join
from h_litp.litp_utils import main_exceptions
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
import logging


class Substituter(object):
    """
    A program substituting all the parameters in the deployment description
    template specified by the user as input. It needs the SED as the other
    input by the user and also use the enminst_working.cfg and in the
    /opt/ericsson/enminst/runtime directory to find all the keys needed to
    populate all the values in the deployment description. If any keys are
    missing as part of a validation step then the program will exit prompting
    the user of the missing values in the deployment description xml template.
    """

    def __init__(self, verbose=False):
        """
        Initializes instance
        :param verbose: if True the enable verbose logging
        :return:
        """
        if 'ENMINST_RUNTIME' in os.environ:
            self.runtime_dir = os.environ['ENMINST_RUNTIME']
        self.output_xml = join(self.runtime_dir, 'enm_deployment.xml')
        self.enminst_working = join(self.runtime_dir, 'enminst_working.cfg')
        self.full_parameter_list = {}
        self.log = logging.getLogger('enminst')
        if verbose:
            set_logging_level(self.log, 'DEBUG')

    def build_full_file(self, sed_file, property_file=None):
        """
        A function to populate all the keys and values needed to produce
        a fully populated deployment description looping over the SED file
        , property_file and enminst_working.cfg files in the
        runtime directory.

        :param sed_file: The SED file location as input by the user.
        :type sed_file: file
        :param property_file: The property file location containing additional
                             properties
        :type property_file: file
        """
        p_files = [sed_file, self.enminst_working]
        if property_file is not None:
            p_files = p_files + [property_file]

        for p_file in p_files:
            self.build_param_file(p_file)

    def build_param_file(self, param_file):
        """
        Looks at the contents of the param_file and strips out comments
        and whitespace, then splits on = character. The keys and values
        are then passed included in the full_parameter_list

        :param param_file: A file with keys and values eg SED
        :type param_file: str
        :return: Keys and values found in the param_file
        :rtype: dict
        :raises: IOError if it cannot find the file.
        """
        if not exists(param_file):
            raise IOError('File {0} not found!'.format(param_file))
        with open(param_file, 'r') as _file:
            lines = _file.readlines()
        lines = [line.strip() for line in lines]
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            _match = re.match('(.*?)=(.*)', line)
            if _match:
                key = _match.group(1)
                value = _match.group(2)
                if value:
                    if value.startswith('file://'):
                        _file = value.replace('file://', '')
                        self.log.info('Reading contents of {0}'.format(_file))
                        with open(_file, 'r') as _reader:
                            value = '\n'.join(_reader.readlines()).strip()
                    self.full_parameter_list[key] = value
        return self.full_parameter_list

    def replace_values(self, xml):
        """
        Replaces all the keys in the xml with their coresponding values.

        :param xml: xml template with keys needed to be replaced by values
        :type xml: str
        :returns: An xml with keys found replaced by the corresponding value
        :rtype: str
        """
        for key, value in self.full_parameter_list.items():
            xml = xml.replace('%%{0}%%'.format(key), value)
        return xml

    def verify_xml(self, xml):
        """
        Verification step checking that no parameters in the supposed fully
        populated xml are not substituted.

        :param xml: A deployment description xml after the values have been
                    replaced.
        :type xml: str
        :raises: SystemExit if not all parameters are replaced.
        """
        outstanding = set(re.findall('%%.*%%', xml))
        if outstanding:
            self.log.error('Not all parameters are substituted!!')
            for parameter in outstanding:
                if ',' in parameter:
                    for param in parameter.split(','):
                        if param not in outstanding:
                            self.log.error('Parameter {0} not substituted'
                                           .format(param))
                else:
                    self.log.error('Parameter {0} not substituted'.format(
                            parameter))
            raise SystemExit(5)
        else:
            self.log.info('Successfully substituted all parameters')
        return outstanding

    def write_file(self, contents):
        """
        A function to write a fully populated xml to the runtime directory
        and calling it enm_deployment.xml.

        :param contents: The fully populated deployment description
        :type contents: str
        """
        with open(self.output_xml, 'w') as _writer:
            _writer.writelines(contents)
        self.log.info('Fully populated xml can be found in {0}'
                      .format(self.output_xml))

    @staticmethod
    def read_file(_file):
        """
        Read a file
        :param _file: Path of file to read
        :return:
        """
        if not exists(_file):
            raise IOError('File {0} not found!'.format(_file))
        with open(_file, 'r') as _reader:
            string_file = ''.join(_reader.readlines())
        return string_file


def substitute(args):
    """
    Executes substitution of parameters
    :param args: configuration of substitution
    """
    log = init_enminst_logging()
    if args.verbose:
        set_logging_level(log, 'DEBUG')

    log.info('Substituting parameters...')
    log.info('SED file set to {0}'.format(args.sed_file))
    log.info('XML Template set to {0}'.format(args.xml_template))
    if args.property_file:
        log.debug('Property file set to {0}'.format(args.property_file))
    instance = Substituter(args.verbose)
    instance.build_full_file(args.sed_file, args.property_file)
    prepared_xml_template = instance.read_file(args.xml_template)
    xml_with_values_replaced = instance.replace_values(prepared_xml_template)
    instance.verify_xml(xml_with_values_replaced)
    instance.write_file(xml_with_values_replaced)


def create_parser():
    """
    Creates and configures argument parser for command line arguments handling
    :return: argument parser instance
    """
    arg_parser = ArgumentParser(prog="substituteParams.sh", )

    arg_parser.add_argument('-v', '--verbose',
                            action='store_true',
                            default=False,
                            help="Verbose logging")
    arg_parser.add_argument('--xml_template',
                            required=True,
                            help='Deployment Model XML file')
    arg_parser.add_argument('--sed',
                            dest='sed_file',
                            required=True,
                            help='Site Engineering Document file')
    arg_parser.add_argument('--propertyfile',
                            dest='property_file',
                            help='File providing additional properties ')
    return arg_parser


def main(args):
    """
    Main function
    :param args: sys args
    :return:
    """
    arg_parser = create_parser()
    parsed_args = arg_parser.parse_args(args[1:])
    substitute(parsed_args)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
