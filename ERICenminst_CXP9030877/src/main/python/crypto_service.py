"""
This script does the following:
    Invokes a rest to the gic-service with the purpose to harden
    the ENM cryptography service.
    It will create a new encryption key for the cryptography service
    if not already created.
    In case the key was already created this rest is harmless
    In case of an error invoking the rest API the error is
    only logged as warning
"""
from h_logging.enminst_logger import init_enminst_logging, set_logging_level
from h_litp.litp_utils import main_exceptions
from argparse import ArgumentParser

import sys
import requests
GIC_SERVICE = "gic-service"
GIC_URL = "http://" + GIC_SERVICE + ":8080/"


class CryptoService(object):  # pylint: disable=too-few-public-methods
    """
    Class to handle encrypting passwords by cryptoservice
    """
    def __init__(self, verbose):
        """Initialize instance
        :param verbose: if verbose logging mode is required
        """

        self.log = init_enminst_logging()
        if verbose:
            set_logging_level(self.log, 'DEBUG')

    def crypto_service_update(self):
        """
        Execute the rest to create the first encryption key in vault
        :return: response code for the called rest
        """
        self.log.info('Calling rest for first encryption key creation')
        curl_url = GIC_URL + "oss/internal/cryptoservice/1.0/hardening"
        try:
            res = requests.post(curl_url, headers={'host': GIC_SERVICE})
            self.log.info("Http code: {0}".format(res.status_code))
            if res.status_code != 200:
                self.log.warn("Cryptoservice Hardening is failed. "
                              "Http code {0}".format(res.status_code))
            return res.status_code
        except requests.exceptions.RequestException as ex:
            self.log.warn("Cryptoservice Hardening is failed. "
                           "Exception {}".format(str(ex)))
            return 0


def crypto_service(parsed_args):
    """Calls execution of rest to create the first encryption key to be used
     in a hardened system
    :param parsed_args: configuration of crypto_service
    """
    instance = CryptoService(parsed_args.verbose)
    instance.crypto_service_update()


def create_parser():
    """Create and configure command line parser instance
    :return: parser instance
    :rtype: ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true',
                        default=True, help="Enable all debugging output")
    return parser


# =============================================================================
# Main
# =============================================================================
def main(args):
    """
    Main function to run crypto_service
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args[1:])
    crypto_service(parsed_args)


if __name__ == '__main__':
    main_exceptions(main, sys.argv)
