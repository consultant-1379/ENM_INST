"""
Checks whether neo4j is the only service active on db-2,
if any db clusters found will switch to db-1
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

from switch_db_groups import switch_dbcluster_groups


def main():
    """
    Checks if any db cluster groups other than neo4j are
    running on db-2 and switch those from db-2 to db-1
    """
    switch_dbcluster_groups()


if __name__ == "__main__":
    main()
