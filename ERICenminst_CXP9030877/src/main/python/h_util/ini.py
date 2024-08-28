"""
The purpose of this script is to gather information for the ini
file that is passed to it
"""
# ********************************************************************
# Ericsson LMI                                    SCRIPT
# ********************************************************************
#
# (c) Ericsson LMI 2015 - All rights reserved.
#
# The copyright to the computer program(s) herein is the property of
# Ericsson LMI. The programs may be used and/or copied only  with the
# written permission from Ericsson LMI or in accordance with the terms
# and conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
#
# ********************************************************************
# Name    : ini.py
# Date    : 10/03/2015
# Revision: A1
# Purpose : The purpose of this script is to gather information for
#  the ini file that is passed to it
# ********************************************************************
from ConfigParser import SafeConfigParser, NoOptionError, NoSectionError
from os import makedirs
from os.path import abspath, dirname, exists
from re import search

from collections import OrderedDict


class IniReader(object):
    """
    Class to handle access to an ini file
    """

    def __init__(self, ini_file=None, config_parser=None):
        if config_parser:
            self.inireader = config_parser
        else:
            if not exists(ini_file):
                raise IOError(2, '{0} not found'.format(ini_file))
            self.ini_file = ini_file
            self.inireader = SafeConfigParser(dict_type=OrderedDict)
            self.inireader.optionxform = str
            self.inireader.read(self.ini_file)

    def get_file_path(self):
        """
        Function Description:
        get_file_path function returns the path of the ini files
        :param - none
        :type - none
        """
        return abspath(self.ini_file)

    def get_option(self, section, option, seperator=None, default=None):
        """
        Function Description:
        The get_option function checks if the ini file has the passed
        section or block & if so, locates the passed option and returns
        its value.
        :param section: Ini section name
        :param option: Ini section option name
        :param seperator: Character to seperate value by
        :param default: Default value to return if sesion:option is not found
        """
        if self.inireader.has_section(section):
            if self.inireader.has_option(section, option):
                value = self.inireader.get(section, option)
            elif default is not None:
                value = default
            else:
                raise NoOptionError(option, section)
        elif default is not None:
            value = default
        else:
            raise NoSectionError(section)
        if seperator is not None:
            value = value.split(seperator)
        return value

    def has_option(self, section, option):
        """
        Function Description:
        The has_option takes in a section and option and returns
        the values from the ini file
        :param section: The ini section name
        :param option: The ini section option name
        :returns: `True` if the section exists and has the option,
        `False` otherwise
        """
        return self.inireader.has_option(section, option)

    def has_section(self, section):
        """
        Function Description:
        The has_section ensures the section passed is valid
        :param section: The ini section name
        :returns: `True` if the secion exists, `False` otherwise
        """
        return self.inireader.has_section(section)

    def get_section(self, section):
        """
        Function Description:
        The get_section function loops through the ini file
        and populates a list with entries from section
        provided
        :param section: The ini section name
        """
        if self.inireader.has_section(section):
            items = self.inireader.items(section)
            data = {}
            for item in items:
                data[item[0]] = item[1]
            return data
        else:
            raise NoSectionError(section)

    def get_block_names(self):
        """
        Function Description:
        the get_block_names returns a list of block names from the ini file
        :param - none
        :type - none
        """
        return self.inireader.sections()

    def get_site_value(self, section, option, default_value=None,
                       seperator=None):
        """
        Function Description:
        The get_site_section function uses values from the ini
        file and returns a list
        :param section: The ini section name
        :param option: The ini section option name
        :param default_value: Default value to return if section or option
        are not found
        :param seperator: Character to use to split values into a list
        """
        if self.inireader.has_option(section, option):
            _value = self.inireader.get(section, option)
        elif default_value is not None:
            _value = default_value
        else:
            raise NoOptionError(option, section)
        if seperator is not None:
            _value = _value.split(seperator)
        return _value

    def get_site_section_keys(self, section, key_filter=None):
        """
        Function Description:
        The get_site_section function uses key values from the ini
        file and returns a list
        :param section: The ini section name
        :param key_filter: Regex to match wanted keys
        """
        keys = self.inireader.options(section)
        if key_filter:
            keys[:] = [key for key in keys if search(key_filter, key)]
        return keys

    def set_option(self, section, option, value):
        """
        Function Description:
        The set_option function reads ini values passed by the user
        and using the set command, sets new value.
        :param section: The ini section name
        :param option: The ini section option name
        :param value: The value to set
        """
        self.inireader.set(section, option, value)

    def merge(self, other):
        """
        Function Description:
        The merge function merges sections within a specified ini file
        :param other: The ini file to merge to this one

        """
        for block in self.get_block_names():
            if other.has_section(block):
                for key in self.get_site_section_keys(block):
                    this_value = self.get_option(block, key)
                    if this_value.startswith('"Q:') and other.has_option(block,
                                                                         key):
                        orig_value = other.get_option(block, key)
                        self.set_option(block, key, orig_value)

    def save_ini(self, fullpath=None):
        """
        Function Description:
        The function save_ini enables a file to be written to a directory.
        :param fullpath: The path to save the ini to
        """
        if fullpath:
            inifile = fullpath
        else:
            inifile = self.ini_file
        absfpath = abspath(inifile)
        fdir = dirname(absfpath)
        if not exists(fdir):
            makedirs(fdir)
        with open(absfpath, 'w') as ini_file:
            self.inireader.write(ini_file)
