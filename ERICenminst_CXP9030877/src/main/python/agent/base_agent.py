"""

Some of the action implementations are in this module, the ruby agent
 will forward the action to this module via the 'implemented_by' keyword

Results and Exceptions
0   OK
1   Failed. All the data parsed ok, we have a action matching the request
    but the requested action could not be completed.  RPCAborted
2   Unknown action  UnknownRPCAction
3   Missing data    MissingRPCData
4   Invalid data    InvalidRPCData
5   Other error     UnknownRPCError

Request format:
{ "callerid": null,
  "agent": "enminst",
  "data":{"process_results":true},
  "uniqid":"e8937c54738d5cb09b3ca8d668d821ce",
  "sender":"ms1",
  "action":"pythontest"
}
"""
import json
import os
from subprocess import Popen, PIPE

import sys

OK = 0
RPCABORTED = 1
UNKNOWNRPCACTION = 2
MISSINGRPCDATA = 3
INVALIDRPCDATA = 4
UNKNOWNRPCERROR = 5

MCOLLECTIVE_REPLY_FILE = "MCOLLECTIVE_REPLY_FILE"
MCOLLECTIVE_REQUEST_FILE = "MCOLLECTIVE_REQUEST_FILE"


class RPCAgent(object):
    """
    Base action method that handles the puppet input and output file.
    """

    def action(self):
        """
        Run an action request.

        Reads in action input file ${MCOLLECTIVE_REQUEST_FILE} to get
        the action to call and any arguments for the action, execute action
        and write results to ${MCOLLECTIVE_REPLY_FILE}
        :return:
        """
        exit_value = OK
        with open(os.environ[MCOLLECTIVE_REQUEST_FILE], 'r') as infile:
            request = json.load(infile)

        action = request["action"]
        method = getattr(self, action, None)
        if callable(method):
            reply = method(request['data'])
        else:
            reply = {}
            exit_value = UNKNOWNRPCACTION

        with open(os.environ[MCOLLECTIVE_REPLY_FILE], 'w') as outfile:
            json.dump(reply, outfile)

        sys.exit(exit_value)

    @staticmethod
    def get_return_struct(returncode, stdout='', stderr=''):
        """
        Construct the MCO response data structure
        :param returncode: The exit code of the MCO action.
        :param stdout: Any STDOUT from the MCO action.
        :param stderr: Any STDERR from the MCO action.
        :returns: A struct that can be returned to whom ever called the action.
        :rtype: dict
        """
        return {'retcode': returncode,
                'out': stdout,
                'err': stderr}

    @staticmethod
    def execute(command, env=None, use_shell=False):
        """
        Execute a command, handling I/O and errors
        and returning a tuple of ( returncode, stdout, stderr )


        :param command: The command to run
        :type command: list(str)
        :param env:  Environment variables to pass to the process
        :type env: dict/None
        :param use_shell: run command in shell
        :type use_shell: bool
        :returns: (exit code of process, process stdout, process stderr)
        :rtype: tuple
        """
        _process = Popen(command, stdout=PIPE, stderr=PIPE, shell=use_shell,
                         env=env)
        out, err = _process.communicate()
        returncode = _process.returncode
        stdout = out.strip()
        stderr = err.strip()
        return returncode, stdout, stderr
