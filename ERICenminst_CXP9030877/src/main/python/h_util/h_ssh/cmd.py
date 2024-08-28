""" Module to build and format commands sent via ssh or in a shell pipe"""
from collections import OrderedDict
import re


def _escape(value):
    """ Removes escape '\\' characters """
    return re.escape(value).replace('\\%s', '%s')


def to_list(value, convert_tuple=True):
    """ Converts passed value into a list
    :param value:
    :param convert_tuple:
    :return: list
    """
    iterables = list
    if convert_tuple:
        iterables = (list, tuple)
    return list(value) if isinstance(value, iterables) \
                       else [value] if value is not None else []


# pylint: disable=too-many-instance-attributes
class Command(object):
    """ Command builder
    """

    masks = {}

    _formats = ([
        ('sudo', 'sudo sh -c "%s"', r'^%s$', r'(.*)'),
        ('su_user', 'su %s -c "%s"', r'^%s$', (r'([\w\-.]+)', r'(.*)')),
        ('sh_source_path', ". %s; ", r'^%s(.*)$', r'([/\w_\-.]+)'),
        ('env', "%s='%s'", r"^%s (.*)$", (r'([\w\-]+)', r"([^']+)")),
        ('timeout', '/usr/bin/timeout %s sh -c "%s"', r'^%s$',
         (r'(\d+)', r'(.*)'))
    ])

    formats = OrderedDict([f[:2] for f in _formats])

    reverse_regexes = OrderedDict([(f[0], re.compile(f[2] %
                      _escape(f[1]) % f[3])) for f in _formats])

    # pylint: disable=too-many-arguments
    def __init__(self, cmd, su_user=None, sudo=False, env=None,
                 sh_source_path=None, timeout=None, mask=None):
        """ Command builder
        :param cmd: str
        :param su_user: str
        :param sudo: bool
        :param env: dict
        :param sh_source_path: str
        :param timeout: int
        """
        self.cmd = cmd
        self.su_user = su_user[0] if isinstance(su_user, list) and \
                                     len(su_user) == 1 else su_user
        self.su_users = to_list(su_user)
        self.su_users.reverse()
        self.sudo = sudo
        self.env = env
        self.sh_source_path = sh_source_path
        self.timeout = timeout
        self.mask = re.compile(mask) if isinstance(mask, basestring) else mask

    @staticmethod
    def escape(cmd):
        """ Add escape characters to a command """
        return cmd.replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def unescape(cmd):
        """ Remove escape characters from a command """
        return cmd.replace('\\\\', '\\').replace('\\"', '"')

    def __str__(self):
        cmd = self.cmd
        env_str = ''
        if self.timeout:
            cmd = self.escape(cmd)
            cmd = self.formats['timeout'] % (self.timeout, cmd)
        if self.env:
            env_str = ' '.join([self.formats['env'] % (k, v)
                                for k, v in self.env.items()])
            env_str = "%s " % env_str if env_str else ""
        src = ""
        if self.sh_source_path:
            src = self.formats['sh_source_path'] % self.sh_source_path
        for su_user in self.su_users:
            cmd = "%s%s%s" % (src, env_str, self.escape(cmd))
            cmd = self.formats['su_user'] % (su_user, cmd)
            env_str = ''
            src = ''
        if self.sudo:
            cmd = "%s%s%s" % (src, env_str, self.escape(cmd))
            cmd = self.formats['sudo'] % cmd
            env_str = ''
            src = ''
        cmd = "%s%s%s" % (src, env_str, cmd)
        return cmd

    def __repr__(self):
        return "<Command: %s>" % str(self)

    @property
    def masked(self):
        """ Masking sensitive data from a command when logging """
        extra_mask = [self.mask] if self.mask else []
        masked_cmd = str(self)
        for mask in self.masks.values() + extra_mask:
            for occurrences in mask.findall(masked_cmd):
                if not isinstance(occurrences, tuple):
                    occurrences = (occurrences,)
                for item in occurrences:
                    masked_cmd = masked_cmd.replace(item, "******")
        return masked_cmd
