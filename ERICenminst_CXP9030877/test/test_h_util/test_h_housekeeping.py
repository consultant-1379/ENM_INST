import httplib
import sys
from glob import glob1
from json import dumps
from os import makedirs
from os.path import exists, join
from shutil import rmtree
from tempfile import gettempdir

from mock import patch, call, MagicMock
from unittest2 import TestCase

try:
    import yum
except ImportError:
    sys.modules['yum'] = MagicMock()

from h_util.h_housekeeping import EnmLmsHouseKeeping, EnmHouseKeepingException
from h_util.h_utils import touch
from test_h_litp.test_h_litp_rest_client import setup_mock as setup_litp_mocks


class TestEnmLmsHouseKeeping(TestCase):
    def setUp(self):
        super(TestEnmLmsHouseKeeping, self).setUp()
        self.tmpdir = join(gettempdir(), 'doyler')
        if exists(self.tmpdir):
            rmtree(self.tmpdir)
        makedirs(self.tmpdir)
        self.doyler = EnmLmsHouseKeeping()
        self.doyler.repo_basepath = self.tmpdir

    def tearDown(self):
        super(TestEnmLmsHouseKeeping, self).tearDown()
        if exists(self.tmpdir):
            rmtree(self.tmpdir)

    def assert_nameversion(self, filename, expected_name, expected_version):
        name, version = EnmLmsHouseKeeping.version_from_filename(filename)
        self.assertEqual(expected_name, name)
        self.assertEqual(expected_version, version)

    def test_version_from_filename(self):
        self.assert_nameversion('ERICsample_CXP12345-1.1.1.rpm',
                                'ERICsample_CXP12345', '1.1.1')
        self.assert_nameversion('ERICsample_CXP12345-1.1.1-SNAPSHOT.rpm',
                                'ERICsample_CXP12345', '1.1.1-SNAPSHOT')
        self.assert_nameversion('ERICsample_CXP12345-1.1.1-SNAPSHOT.qcow2',
                                'ERICsample_CXP12345', '1.1.1-SNAPSHOT')
        self.assert_nameversion('some_random_file.rpm',
                                None, None)

    def mock_modeled_images(self, *images):
        items = []
        for image_info in images:
            _project = image_info[0]
            for _image in image_info[1]:
                image_name = _image.split('-')[0]
                items.append({
                    'id': image_name,
                    'item-type-name': 'vm-image',
                    'state': 'Applied',
                    '_links': {
                        'self': {
                            'href': 'https://localhost:9999/litp/rest'
                                    '/v1/software/images/' + image_name
                        }
                    },
                    'properties': {
                        'source_uri':
                            'http://localhost/images/' +
                            _project + '/' + _image,
                    }
                })
        return dumps({
            '_embedded': {'item': items}, 'id': 'images'
        })

    def mock_fs_repos(self, *images):
        image_dir = join(self.doyler.repo_basepath, 'images')
        for image_info in images:
            _project = image_info[0]
            imgdir = join(image_dir, _project)
            if not exists(imgdir):
                makedirs(imgdir)
            for _image in image_info[1]:
                touch(join(imgdir, _image))
                touch(join(imgdir, _image + '.md5'))

    def test_get_repo_images(self):
        repo1 = join(self.doyler.repo_basepath, 'images/repo1')
        makedirs(repo1)
        touch(join(repo1, 'image.qcow2'))
        touch(join(repo1, 'somefile.txt'))
        repos = self.doyler.get_repo_images()
        self.assertIn('repo1', repos)
        self.assertEqual(1, len(repos['repo1']))
        self.assertEqual('image.qcow2', repos['repo1'][0])

    def test_get_modeled_images(self):
        image_name = 'ERICimage'
        file_name = image_name + '-CXP123-1.2.3.qcow2'
        repo_name = 'testrepo'
        setup_litp_mocks(
                self.doyler._litp, [
                    [
                        'GET',
                        self.mock_modeled_images((repo_name, [file_name])),
                        httplib.OK]
                ]
        )
        modeled = self.doyler.get_modeled_images()
        self.assertIn(repo_name, modeled)
        self.assertIn(file_name, modeled[repo_name])

    def test_housekeep_images_nochanges(self):
        project = 'ENM'
        iso_images = [
            'ERICimg1-CXP111111-1.2.3.qcow2',
            'ERICimg2-CXP111111-4.1.7.qcow2',
            'ERICimg3-CXP111111-6.99.0.qcow2']

        modeled_images = list(iso_images)
        fs_images = list(iso_images)

        setup_litp_mocks(
                self.doyler._litp, [
                    [
                        'GET',
                        self.mock_modeled_images((project, modeled_images)),
                        httplib.OK]
                ]
        )
        self.mock_fs_repos((project, fs_images))

        self.doyler.housekeep_images({project: iso_images})

        _dir = join(self.doyler.repo_basepath, 'images', project)
        self.assertEqual(3, len(glob1(_dir, '*.qcow2')))
        for img in iso_images:
            self.assertTrue(exists(join(_dir, img)))

    def test_housekeep_images_remove_old(self):
        # ERICimg1: version 1.2.9 should get deleted
        # ERICimg2: version 4.1.7-SNAPSHOT should get deleted
        # ERICimg3: Nothing deleted, iso/model/fs versions are the same

        project = 'ENM'
        iso_images = [
            'ERICimg1-CXP111111-1.3.1.qcow2',
            'ERICimg2-CXP111111-4.1.7.qcow2',
            'ERICimg3-CXP111111-6.99.0.qcow2']

        modeled_images = list(iso_images)
        modeled_images[0] = 'ERICimg1-CXP111111-1.2.9.qcow2'
        fs_images = list(modeled_images)
        fs_images.append('ERICimg2-CXP111111-4.1.7-SNAPSHOT.qcow2')

        setup_litp_mocks(
                self.doyler._litp, [
                    [
                        'GET',
                        self.mock_modeled_images((project, modeled_images)),
                        httplib.OK]
                ]
        )
        self.mock_fs_repos((project, fs_images))

        self.doyler.housekeep_images({project: iso_images})

        _dir = join(self.doyler.repo_basepath, 'images', project)
        self.assertFalse(exists(join(_dir, 'ERICimg1-CXP111111-1.2.9.qcow2')))

        self.assertTrue(exists(join(_dir, 'ERICimg2-CXP111111-4.1.7.qcow2')))
        self.assertFalse(exists(
                join(_dir, 'ERICimg2-CXP111111-4.1.7-SNAPSHOT.qcow2')))

        self.assertTrue(exists(join(_dir, 'ERICimg3-CXP111111-6.99.0.qcow2')))

        self.assertEqual(2, len(glob1(_dir, '*.qcow2')))

    def test_housekeep_images_remove_repos(self):
        iso_project = 'ENIQ'
        iso_images = ['ERICimg1-CXP111111-1.3.1.qcow2']

        mdl_project = 'ENM'
        mdl_images = ['ERICimg2-CXP111111-1.3.1.qcow2']

        fs_images = list(mdl_images)

        self.mock_fs_repos(('obsolete_repo',
                            ['ERICobsolete-CXP111111-1.3.1.qcow2',
                             'aaaaaaaaa.qcow2']))

        setup_litp_mocks(
                self.doyler._litp, [
                    [
                        'GET',
                        self.mock_modeled_images((mdl_project,
                                                  mdl_images)),
                        httplib.OK]
                ]
        )
        self.mock_fs_repos((mdl_project, fs_images))

        self.doyler.housekeep_images({iso_project: iso_images})

        _dir = join(self.doyler.repo_basepath, 'images', mdl_project)
        self.assertEqual(1, len(glob1(_dir, '*.qcow2')))
        self.assertTrue(exists(join(_dir, mdl_images[0])))

    @patch('h_util.h_housekeeping.remove')
    @patch('h_util.h_housekeeping.exec_process')
    def test_housekeep_yum(self, m_exec_process, m_remove):

        makedirs(join(self.doyler.repo_basepath, 'r1'))
        makedirs(join(self.doyler.repo_basepath, 'r2'))
        iso_repos = {
            'r1': [],
            'r2': [],
            'r3': []
        }
        m_exec_process.side_effect = [
            'rpm1.rpm\nrpm2.rpm',
            'updated repo',
            ''
        ]

        self.doyler.housekeep_yum(iso_repos)
        self.assertEqual(2, m_remove.call_count)
        m_remove.assert_has_calls([
            call('rpm1.rpm'), call('rpm2.rpm')
        ])
        m_exec_process.assert_has_call(
                call(['/usr/bin/createrepo', '--update',
                      join(self.doyler.repo_basepath, 'r1')])
        )

    @patch('h_util.h_housekeeping.remove')
    @patch('h_util.h_housekeeping.exec_process')
    def test_housekeep_yum_empty_repo(self, m_exec_process, m_remove):
        makedirs(join(self.doyler.repo_basepath, 'r1'))
        makedirs(join(self.doyler.repo_basepath, 'r2'))
        iso_repos = {
            'r1': [],
            'r2': []
        }
        m_exec_process.side_effect = [
            IOError(1, 'No files to process'),
            'rpm1.rpm',
            'exit_zero_createrepo'
        ]
        self.doyler.housekeep_yum(iso_repos)
        self.assertEqual(1, m_remove.call_count)
        m_remove.assert_has_calls([
            call('rpm1.rpm')
        ])
        m_exec_process.assert_has_call(
                call(['/usr/bin/createrepo', '--update',
                      join(self.doyler.repo_basepath, 'r1')])
        )

    @patch('h_util.h_housekeeping.exec_process')
    def test_housekeep_yum_error(self, m_exec_process):
        makedirs(join(self.doyler.repo_basepath, 'r1'))
        iso_repos = {
            'r1': []
        }
        m_exec_process.side_effect = [
            IOError(1, 'fatal!')
        ]
        self.assertRaises(EnmHouseKeepingException,
                          self.doyler.housekeep_yum, iso_repos)
