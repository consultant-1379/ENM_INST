#!/usr/bin/env python

#********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2020 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property
# of Ericsson LMI. The programs may be used and/or copied only with
# the written permission from Ericsson LMI or in accordance with the
# terms and conditions stipulated in the agreement/contract under
# which the program(s) have been supplied.
#
# ********************************************************************
# Name    : pib_set.py
# Purpose : Enforce setting a PIB parameter, used in conjunction with cron jobs
#
# Usage   : pib_set.py <pram name> <param value> <name of cron file to delete>
#
# ********************************************************************
from h_util import h_utils
from h_litp.litp_utils import main_exceptions
import sys
import os
from datetime import datetime
import time


def main(args):

    param = args[0]
    value = args[1]
    cron_file_name = args[2]

    full_cron_file_path = '/etc/cron.d/' + cron_file_name

    current_value = h_utils.read_pib_param(param)
    print str(datetime.now()) + ' Initially, pib param=' + param +\
     ' current_value=' + current_value + ' required_value=' + value
    if current_value != value:
        print str(datetime.now()) + ' Setting pib param=' + param +\
        ' value=' + value
        h_utils.set_pib_param(param, value)
        time.sleep(5)  # required before read or previous set value returned
        current_value = h_utils.read_pib_param(param)
        print str(datetime.now()) + ' Finally, pib param=' + param +\
        ' value=' + current_value
        if current_value == value:
            os.remove(full_cron_file_path)
    else:
        os.remove(full_cron_file_path)

if __name__ == '__main__':
    main_exceptions(main, sys.argv[1:])
