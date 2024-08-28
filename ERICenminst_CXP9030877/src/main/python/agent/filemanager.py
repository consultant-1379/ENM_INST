#!/bin/env python
# pylint: disable=C0103
"""
 Enminst MCO agent implementation for vcs triggers.
"""

##############################################################################
# COPYRIGHT Ericsson AB 2017
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
import logging
import logging.config
from os.path import dirname, abspath, join
from urllib2 import urlopen, URLError, HTTPError
import json
from base_agent import RPCAgent
from base64 import standard_b64decode
import sys
import os


class FileManager(RPCAgent):
    """
    Agent implementation of remote file pull from consul
    """
    def __init__(self):
        _lcfg = join(dirname(abspath(__file__)), 'logging.cfg')
        logging.config.fileConfig(_lcfg)
        self.logger = logging.getLogger('enminst_filemanager_agent')

    @staticmethod
    def enable_debug(args):
        """
        Enable debug logging of 'verbose' passed from client
        :param args: Arguments from the 'mco rpc ...' command issued on the
        LMS

        """
        if 'verbose' in args and args['verbose'].lower() == 'true':
            logging.getLogger().setLevel(logging.DEBUG)

    def pull_file(self, args):
        """
        :param args: Arguments from the 'mco rpc ...' command issued on the
        LMS
        :type args: dict
        :returns: Results of file retrieval from consul
        :rtype: dict
        """

        _results = []
        self.enable_debug(args)
        url = args['consul_url']
        file_path = args['file_path']

        try:
            response = urlopen(url)
        except (HTTPError, URLError) as ex:
            msg = 'Request "{0}" failed with Error "{1}"'.format(
                    url, str(ex))
            self.logger.info(msg)
            return self.get_return_struct(1, stderr=msg)
        else:
            retcode = response.getcode()
            if retcode != 200:
                msg = 'Request "{0}" failed with Error "{1}"'.format(
                        url, str(retcode))

                self.logger.info(msg)
                return self.get_return_struct(1, stderr=msg)
        msg = 'Request "{0}" returned "{1}"'.format(
                url, str(retcode))
        _results.append(msg)
        self.logger.debug(msg)
        data = json.load(response)
        value = standard_b64decode(data[0]['Value'])
        value = standard_b64decode(value)

        try:
            directory = os.path.dirname(file_path)
            if not os.path.exists(directory):
                os.makedirs(directory)

            f = open(file_path, "w")
            f.write(value)
            f.close()
            os.chmod(file_path, 0755)
        except IOError as e:
            msg = "I/O error({0}): {1}".format(e.errno, e.strerror)
            return self.get_return_struct(1, stderr=msg)
        except:
            e = sys.exc_info()[1]
            msg = "Unexpected error: {0}".format(str(e))
            return self.get_return_struct(1, stderr=msg)

        msg = 'File "{0}" written successfully'.format(
            file_path)
        _results.append(msg)
        self.logger.debug(_results)
        return self.get_return_struct(0, '\n'.join(_results))


if __name__ == '__main__':
    FileManager().action()
