"""
The purpose of this script is raise the alarm for
REST api for any REST client operations
"""

#!/usr/bin/python
##############################################################################
# COPYRIGHT Ericsson AB 2020
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import logging
from urllib2 import urlopen, Request
import json

LOG = logging.getLogger(__name__)


class RESTapi(object):  # pylint: disable=too-few-public-methods
    """
    Class for restapi
    """

    def __init__(self, url):
        self.service_url = url

    def post(self, json_data):
        """
        json_data is a Python dictionary containing data to be send to REST
        service.
        """
        data = json.dumps(json_data)
        req = Request(self.service_url,
                      data,
                      {'Content-Type': 'application/json'})
        try:
            response = urlopen(req)
        except IOError as message:
            if hasattr(message, 'code'):  # HTTPError
                LOG.error("The server couldn\'t fulfill the request. "
                          "Error code: %s", message.code)
            elif hasattr(message, 'reason'):  # URLError
                LOG.error("Failed reach server,Reason: %s", message.reason)
        else:
            msg = ("Successfully send '{oper}' to URL '{url}' "
                   "with data '{data}'".format(oper=req.get_method(),
                                               url=req.get_full_url(),
                                               data=data))
            LOG.debug(msg)
            LOG.debug("Response output: " + response.msg)
            return True
        return False
