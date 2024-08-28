"""
Script to update the deployment description if the Unity SAN array is being
used - removing RAID Group entries and updating Fencing LUNs to use the
Storage Pool.  Also removing the 2nd IP address for the array.
"""
##############################################################################
# COPYRIGHT Ericsson AB 2019
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import sys
import os
from os.path import join
from h_xml.xml_utils import unity_model_updates


def main():
    """
    Main function
    :return:
    """
    runtime_dir = '/opt/ericsson/enminst/runtime/'

    if 'ENMINST_RUNTIME' in os.environ:
        runtime_dir = os.environ['ENMINST_RUNTIME']

    enm_xml = join(runtime_dir, 'enm_deployment.xml')

    unity_model_updates(enm_xml)

if __name__ == '__main__':
    main()
    sys.exit(0)
