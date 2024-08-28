from simplejson import loads
from mock import Mock, MagicMock
from h_logging.enminst_logger import init_enminst_logging
import datetime
from os import mkdir
import os
from os.path import join
from h_util.h_utils import touch

logger = init_enminst_logging()


def load_file_from_path(path):
    current_path = os.path.dirname(__file__)
    file_current_path = current_path + path
    with open(file_current_path, "r") as myfile:
        data = myfile.read()
    return data


def mock_litp_get_requests(current_path, request_urls, paths=None):
    litp_response_json_map = {}
    json_requests_urls = set(request_urls)
    index = 0
    for url in json_requests_urls:
        if paths:
            path = current_path + '/responses/' + paths[index]
        else:
            path = current_path + '/responses/' + url.replace('/',
                                                              '_') + ".json"
        with open(path, "r") as json_file:
            text_data = json_file.read()
            json_response = loads(text_data)
            litp_response_json_map[url] = json_response
        index += 1

    def get_side_effect(arg, log):
        logger.debug("json_requests_url path {0} log {1} ".format(arg, log))
        logger.debug("log enabled {0}".format(log))
        return litp_response_json_map[arg]

    mock_litp_get = Mock()
    mock_litp_get.side_effect = get_side_effect
    return mock_litp_get


def assert_exception_raised(exc_class, callable_obj=None, *args, **kwargs):
    try:
        callable_obj(*args, **kwargs)
    except exc_class as e:
        return e
    except BaseException as err:
        if hasattr(exc_class, '__name__'):
            excName = exc_class.__name__
        else:
            excName = str(exc_class)
        raise AssertionError("{0} not raised. Got type {1}"\
                .format(excName, type(err)))

    raise AssertionError("No exception caught or other issue occured")


def increase_file_modification_time(filepath, interval):
    """
    Increases (change to later) the given files modification time
    by the given interval
    :param filepath: Path to file to modify
    :param interval: Time interval to modify file mod time by
    """
    _change_files_modification_time(filepath, interval, "increase")


def decrease_file_modification_time(filepath, interval):
    """
    Decreases (change to earlier) the given files modification time
    by the given interval
    :param filepath: Path to file to modify
    :param interval: Time interval to modify file mod time by
    """
    _change_files_modification_time(filepath, interval, "decrease")


def _change_files_modification_time(filepath, interval, action):
    """
    Performs the given action on the given files
    modification time by the given interval
    :param filepath: Path to file to modify
    :param interval: Time interval to modify file mod time by
    :param action: Increase or decrease file mod time
    """
    #  posix.stat_result(st_mode, st_ino, st_dev, st_nlink,
    #  st_uid, st_gid, st_size, st_atime, st_mtime, st_ctime)
    st = os.stat(filepath)
    atime = st[7]
    mtime = st[8]
    if action == "increase":
        new_mtime = mtime + interval
    elif action == "decrease":
        new_mtime = mtime - interval
    os.utime(filepath, (atime, new_mtime))


def mock_fcaps_healthcheck_module():
    modules = {
        'enmfcapshealthcheck': MagicMock(),
        'enmfcapshealthcheck.h_hc': MagicMock(),
        'enmfcapshealthcheck.h_hc.hc_fcaps': MagicMock()
    }

    return modules


def validate_timestamp_format(time_stamp, format_str):
    """
    Validates that a given time_stamp conforms with
    a given format
    :param time_stamp: time_stamp to be validated
    :param format_str: format to validate time_stamp against
    """
    try:
        datetime.datetime.strptime(time_stamp, format_str)
    except ValueError:
        raise


def make_directory(path):
    """
    Create a directory at a given path
    and returns it
    :param path: Path to create directory
    :return path: Path of created directory
    """
    mkdir(path)
    return path


def make_file(filename, path=None):
    """
    Creates a file - filename at a
    given path
    :param filename: name of file or file path
    :param path: filepath
    :return filename: filename of created file
    """
    if path:
        filename = join(path, filename)
    touch(filename)
    return filename


def read_file(filename, path=None):
    """
    Reads a file at a given path
    :param filename:
    :return output: Lines from file
    :type list:
    """
    output = []
    if path:
        filename = join(path, filename)
    with open(filename, "r") as ofile:
        lines = ofile.readlines()
    for line in lines:
        output.append(line.strip())
    return output

