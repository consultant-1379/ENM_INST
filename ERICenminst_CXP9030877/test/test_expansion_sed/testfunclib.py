'''
Created on 15 Jul 2014

Common functions for unit test code

@author: edavmax
'''

import re
import tempfile

# -----------------------------------------------------
# CLASSES


class MockProc():
    # Use this class when Popen/proc  needs to be mocked
    # and several different xml outputs need to be
    # returned (e.g. get_luns calls Popen twice and expects
    # output from both getlun and lun -list.
    #
    # Here's how to use it:
    # 1) The constructor takes three list arguments:
    #   a) a list of files representing stdout
    #   b) a list of files representing stderr
    #   c) a list of exit codes for each call
    # 2) Create a MockProc object with these lists
    # 3) Mock subprocess.Popen to return this object
    #
    # Example:
    # We want to test get_luns, and we know that this will
    # perform a getlun, then a lun -list.
    # Let's assume we already have the xml output for the
    # commands.  Also, there's no stderr and the exit code
    # is 0...
    #
    # outlist = [ './getlun.xml', './lunlist.xml' ]
    # errlist = [ './empty.txt', './empty.txt' ]
    # extlist = [ 0, 0 ]
    # mokproc = MockProc(outlist, errlist, extlist)
    # subprocess.Popen = mock.Mock(return_value=mokproc)
    #
    # And that's it.  The get_luns can be tested with:
    # vnx.initialise(spa, spb, user, pass, scope, getcert=False, vcheck=False)
    # result = vnx.get_luns()
    #
    # NOTE: remember by default navisec will handle certificates, which will
    # result in calls to Popen you might not have catered for in your xml.
    # so ensure you initialise the api with getcert=False.
    # For more examples look in test_empty_vnx.py.

    def __init__(self, stdoutfiles, stderrfiles, rets):
        self.returncode = 0
        self.outs = stdoutfiles
        self.errs = stderrfiles
        self.rets = rets
        self.count = -1

    def communicate(self):
        self.count += 1

        self.returncode = self.rets[self.count]
        output = self._read_file(self.outs[self.count])
        err = self._read_file(self.errs[self.count])
        return (output, err)

    def _read_file(self, filename):
        with open(filename, "r") as outfile:
            outdata = outfile.read()
        return outdata

# -----------------------------------------------------
# DECORATORS


# Decorator for 2.6 to implement unittest.skip @unittest.skip("")
def skip(func):
    return


def myassert_raises_regexp(tstobj, exceptiontype, message, function, *args,
                           **kwargs):
    '''
    implementation of AssertRaisesRegexp for 2.6 (AssertRaisesRegexp was added
    to 2.7)

    '''
    try:
        function(*args, **kwargs)
    except exceptiontype as e:
        print str(e)
        if not re.search(message, str(e)):
            tstobj.fail("Exception " + str(exceptiontype) +
                        " does not contain expected message " + message +
                        ". Contents of exception:" + str(e))
    except Exception as e:
        tstobj.fail("No Exception of type " + str(exceptiontype) + " raised," +
                    "Exception '" + str(e) + "' raised instead.")
    else:
        tstobj.fail("No Exception of any type raised")


def myassert_is_instance(tstobj, objtotest, classname):
    """
    Implementation of assertIsInstance (which is available in 2.7)
    """
    cname = classname.__name__
    oname = objtotest.__class__.__name__

    if oname != cname:
        tstobj.fail("Object is type %s, should be %s" % (oname, cname))


def myassert_in(tstobj, first, second, msg):
    """
    Implementation of assertIn from 2.7
    """
    success = False
    for item in second:
        if first == item:
            success = True
            break

    if success is False:
        tstobj.fail(msg)


def create_sed(sedfile, params):
    '''
    Create sed file from user-supplied params
    '''
    with open(sedfile, 'w') as f:
        for key in params:
            f.write(key + "=" + params[key] + "\n")


def create_profile(ip_profs_file, op_profs_file, params):
    '''
    Create new blade profile file from template and list
    of substitution parameters
    '''
    print ip_profs_file
    print op_profs_file
    with open(op_profs_file, 'w') as fout:
        with open(ip_profs_file, 'r') as fin:
            for line in fin:
                for param in params:
                    line = line.replace(param, params[param])
                fout.write(line)


def my_assert_lists_equal(testobj, l1, l2):
    """

    :param l1: list1
    :param l2: list to compare
    :return:
    """
    if len(l1) != len(l2) or sorted(l1) != sorted(l2):
        testobj.fail('lists are not equal')


def write_output_to_tmpfile(output):
    """
    Writes supplied string to a temp file and return tmp filename
    :param ouput:
    :return:
    """
    sf = tempfile.NamedTemporaryFile(delete=False)
    sf.write(output)
    sf.close()
    return sf.name
