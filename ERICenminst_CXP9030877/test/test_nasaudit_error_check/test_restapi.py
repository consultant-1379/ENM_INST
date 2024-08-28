##############################################################################
# COPYRIGHT Ericsson AB 2014
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

'''
Created on 17.03.2015

@author: xsamsil (samuli.silvius@tieto.com)
'''
import unittest
import os.path
from urlparse import urlparse
from urllib2 import URLError, HTTPError
from restapi import RESTapi
from mock import patch


def fake_urlopen(url):
    """
    A stub urlopen() implementation that load json responses from
    the filesystem.
    """
    # Map path from url to a file
    parsed_url = urlparse(url)
    resource_file = os.path.normpath('tests/resources%s' % parsed_url.path)
    # Must return a file-like object
    return open(resource_file, mode='rb')


class TestRESTapi(unittest.TestCase):

    def setUp(self):
        self.client = RESTapi("test_url")

    @patch("restapi.urlopen")
    def test_send_success(self, urlopen_mock):
        urlopen_mock.return_value.read.return_value = "paluu"
        rest_json = {'specificProblem': "Alarmin syy",
                     'probableCause': "101",
                     'eventType': "alarm_type",
                     'managedObjectInstance': "ENM"}
        response = self.client.post(rest_json)
        self.assertEquals(response, True)

    @patch("restapi.urlopen")
    def test_send_HttpError(self, urlopen_mock):
        urlopen_mock.side_effect = HTTPError("url", "code", "msg", "hdrs", None)
        rest_json = {'specificProblem': "Alarmin syy",
                     'probableCause': "101",
                     'eventType': "alarm_type",
                     'managedObjectInstance': "ENM",
                     'perceivedSeverity': "INDETERMINATE",
                     'recordType': "ERROR"}
        response = self.client.post(rest_json)
        self.assertEquals(response, False)

    @patch("restapi.urlopen")
    def test_send_URLError(self, urlopen_mock):
        urlopen_mock.side_effect = URLError("reason1")
        rest_json = {'specificProblem': "Alarmin syy",
                     'probableCause': "101",
                     'eventType': "alarm_type",
                     'managedObjectInstance': "ENM",
                     'perceivedSeverity': "INDETERMINATE",
                     'recordType': "ERROR"}
        response = self.client.post(rest_json)
        self.assertEquals(response, False)

