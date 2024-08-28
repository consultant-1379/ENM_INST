"""
Classes containing some general ENM house keeping activities
"""

##############################################################################
# COPYRIGHT Ericsson AB 2016
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################
from glob import glob1
from os import listdir, remove
from os.path import exists, join, basename, dirname
from re import match

from h_litp.litp_rest_client import LitpRestClient
from h_litp.litp_utils import LitpObject
from h_logging.enminst_logger import init_enminst_logging
from h_util.h_utils import exec_process

PATH_SW_IMAGES = '/software/images'

REPOMANAGE = '/usr/bin/repomanage'
CREATEREPO = '/usr/bin/createrepo'


class EnmHouseKeepingException(Exception):
    """ Housekeeping operation failed """

    def __init__(self, *args, **kwargs):
        super(EnmHouseKeepingException, self).__init__(*args, **kwargs)


class EnmLmsHouseKeeping(object):
    """
    General LMS house keeping stuff. Removes unused Images

    """

    def __init__(self):
        self.repo_basepath = '/var/www/html'
        self._litp = LitpRestClient()
        self._log = init_enminst_logging()

    def info(self, message):
        """
        Log a message at INFO level
        :param message: Message to log
        """
        self._log.info(message)

    def warning(self, message):
        """
        Log a message at WARNING level
        :param message: Message to log
        """
        self._log.warning(message)

    def debug(self, message):
        """
        Log a message at DEBUG level
        :param message: Message to log
        """
        self._log.debug(message)

    @staticmethod
    def version_from_filename(filename):
        """
        Get a name and version string tuple from a versioned file.
        The filename format is <name>_<version_string>.extension

        :param filename: The filename e.g. EBC_1.1.1-3.ext
        :returns: Tuple with name and version
        :rtype: tuple
        """
        _match = match(r'^(.*?)-(([0-9]+\.){2}[0-9]+(-SNAPSHOT)?).*',
                       filename)
        if _match:
            return _match.group(1), _match.group(2)
        return None, None

    def get_repo_images(self):
        """
        Get a list of VM image repos in /var/www/html and the images in each
        repo.

        :returns: Images repos and images contained in each one
        :rtype: dict
        """
        repos = {}
        images_dir = join(self.repo_basepath, 'images')
        for project in listdir(images_dir):
            repos[project] = glob1(join(images_dir, project), '*.qcow2')
        return repos

    def get_modeled_images(self):
        """
        Get a list of images that are in the deployment model.

        :returns: List of image repos and images in each repo
        :rtype: dict
        """
        modeled = {}
        for d_image in self._litp.get_children(PATH_SW_IMAGES):
            o_image = LitpObject(None, d_image['data'], self._litp.path_parser)
            image_path = o_image.get_property('source_uri')
            image_name = basename(image_path)
            image_repo = basename(dirname(image_path))
            if image_repo not in modeled:
                modeled[image_repo] = []
            modeled[image_repo].append(image_name)
        return modeled

    def _order_iso_images(self, iso_images):
        """
        Convert the iso contents map into a map defined as:
        {
            repo_name: {
                image_name: version_list,
                ........
                image_name: version_list,
            },
        }

        :param iso_images: Images on the ISO
        :returns: Map of repos containing a map of images and list of versions
        :rtype: dict
        """
        ordered_versions = {}
        for repo, images in iso_images.items():
            ordered_versions[repo] = {}
            for image in images:
                name, version = self.version_from_filename(image)
                ordered_versions[repo][name] = [version]
        return ordered_versions

    def _merge_modeled_images(self, ordered_versions, modeled_images):
        """
        Add the modeled image versions to the `ordered_versions` map
        :param ordered_versions: Map of image repos (the return result of
        the `_order_iso_images` function)
        :param modeled_images: List of image in the LITP model
        """
        for repo, images in modeled_images.items():
            if repo not in ordered_versions:
                ordered_versions[repo] = {}
            for image in images:
                name, version = self.version_from_filename(image)
                if name not in ordered_versions[repo]:
                    ordered_versions[repo][name] = []
                if version not in ordered_versions[repo][name]:
                    ordered_versions[repo][name].append(version)

    def _merge_fsrepo_images(self, ordered_versions, fs_repo_images):
        """
        Add image versions that are in the filesystem repo to the
        `ordered_versions` map
        :param ordered_versions: Map of image repos (the return result of
        the `_order_iso_images` function)
        :param fs_repo_images: List of image found in /var/www/html
        """
        for repo, images in fs_repo_images.items():
            if repo not in ordered_versions:
                ordered_versions[repo] = {}
            for image in images:
                name, version = self.version_from_filename(image)
                if not name:
                    # Unsupported image name format.
                    continue
                if name not in ordered_versions[repo]:
                    ordered_versions[repo][name] = []
                if version not in ordered_versions[repo][name]:
                    ordered_versions[repo][name].append(version)

    def housekeep_images(self, iso_images, image_history_count=1):
        """
        Remove any images that are no longer needed from /var/www/html

        This keeps the images that are on the ISO (regardless of version) as
        they'll get added to the model. The current modeled versions are
        the N-1 versions and any images in /var/www/html/images/<repos> are
        N-2 ... N-n

        :param iso_images: Images on the ISO being upgraded to.
        :type iso_images: dict
        :param image_history_count: Number of versions of each image to keep.
        :type image_history_count: int

        """
        ordered_versions = self._order_iso_images(iso_images)
        self._merge_modeled_images(ordered_versions, self.get_modeled_images())
        self._merge_fsrepo_images(ordered_versions, self.get_repo_images())

        for repo, images in ordered_versions.items():
            self.info('Checking images repository {0}'.format(repo))
            for name, versions in images.items():
                self.info('Checking image {0}/{1}'.format(repo, name))
                if len(versions) <= image_history_count:
                    non_sort = versions
                    to_sort = []
                else:
                    non_sort = versions[:image_history_count]
                    to_sort = versions[image_history_count:]
                ssorted = sorted(to_sort, reverse=True)
                ordered = non_sort + ssorted
                if len(ordered) > image_history_count:
                    for version in ordered[image_history_count:]:
                        filepath = join(self.repo_basepath, 'images', repo,
                                        '{0}-{1}.qcow2'.format(name, version))
                        if exists(filepath):
                            self.info('Removing {0}'.format(filepath))
                            remove(filepath)
                        md5 = '{0}.md5'.format(filepath)
                        if exists(md5):
                            remove(md5)
                self.info('Completed housekeeping on images repository '
                          '{0}'.format(repo))

    def housekeep_yum(self, iso_yum, rpm_history_count=1):
        """
        Remove any rpms that are no longer needed from /var/www/html
        This removes based on versioning i.e. remove everything except latest
        package, everything except latest & latest-1, etc.

        :param iso_yum: List of YUM repositories contained on the ISO being
        used in the upgrade.
        :param rpm_history_count: Number of versions of RPM's to keep

        """
        for yum_repo in iso_yum.keys():
            self.info('Checking YUM repository {0}'.format(yum_repo))
            repo_path = join(self.repo_basepath, yum_repo)
            command = [REPOMANAGE,
                       '--keep={0}'.format(rpm_history_count),
                       '--old', '--nocheck',
                       repo_path]
            if not exists(repo_path):
                self.warning('Skipping {0}'.format(yum_repo))
                self.warning('{0} does not exist'.format(repo_path))
                continue
            try:
                _out = exec_process(command).split('\n')
            except IOError as error:
                # Handle empty repos and repos with no old versions
                # i.e. (new repos)
                if 'No files to process' in error.args[1]:
                    self.info('No files to process in {0}'.format(yum_repo))
                    continue
                else:
                    raise EnmHouseKeepingException(error)
            delete_rpms = [item for item in _out if item]
            if delete_rpms:
                for rpm in delete_rpms:
                    self.info('Removing {0}'.format(rpm))
                    remove(rpm)
                self.info('Updating repository {0}'.format(repo_path))
                _results = exec_process([
                    CREATEREPO, '--update', repo_path
                ])
                self.debug(_results)
                self.info('Completed housekeeping on YUM repository '
                          '{0}'.format(yum_repo))

            else:
                self.info('No houskeeping needed in YUM repository '
                          '{0}'.format(yum_repo))
