"""
Workaround script for TORF-65895 where the SAN SP addresses are
one the Management VLAN. This adds a default route using the Storage VLAN
gateway which has the Management VLAN routed.
"""
