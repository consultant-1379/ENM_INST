"""
Constant variables for the ENM Expansion script
"""
import os


WORKAROUND_SERVICE_LIST_IPV4 = {
    "amos": ["ipaddress", "ip_internal", "ip_jgroups", "ip_storage"],
    "dlms": ["ip_internal", "ip_jgroups"],
    "elementmanager": ["ipaddress", "ip_internal", "ip_jgroups", "ip_storage"],
    "fmx": ["ip_internal", "ip_jgroups"],
    "fmalarmprocessing": ["ip_internal", "ip_jgroups"],
    "fmhistory": ["ip_internal", "ip_jgroups"],
    "msap": ["ip_internal", "ip_jgroups"],
    "mspmip": ["ip_internal", "ip_jgroups", "ip_storage"]
    }

WORKAROUND_SERVICE_EXTRAS_IPV6 = {
    "amos": ["ipv6address"],
    "elementmanager": ["ipv6address"],
    "fmx": ["ipv6address"],
    "msap": ["ipv6address"],
    "mspmip": ["ipv6address"]
    }

DEFAULT_LOG_DIR = os.getcwd()
FAILSAFE_LOG_DIR = '/var/tmp'
