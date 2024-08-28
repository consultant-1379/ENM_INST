import os
import runpy
import sys
import traceback

from unittest2 import TestCase

from workarounds.sed_update import LOG_DIR, LOG_FILENAME_FORMAT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCES_DIR = os.path.abspath(os.path.join(BASE_DIR,
                                             '../Resources/sed_update'))


def get_traceback_str():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb = '\n'.join(traceback.format_tb(exc_traceback))
    name = getattr(exc_type, "__name__", None)
    return "%s: %s\nTraceback (most recent call last):\n\n%s\n%s: %s" % \
           (name, exc_value, tb, name, exc_value)


class TestSedAliasesRemapper(TestCase):

    def _run_sed_update_script(self, sed, old_dd, new_dd, new_sed,
                               expected_exit_code, tester):
        d = os.path.dirname
        base_dir = d(d(BASE_DIR))
        new_path = os.path.join(base_dir, "src/main/python/workarounds/")
        sys.path.append(new_path)
        original_sys_argv = sys.argv
        sys.argv = ["sed_update.py", "--sed", sed, "--old-dd",
                    old_dd, "--new-dd", new_dd]
        try:
            try:
                runpy._run_module_as_main("sed_update")
            except BaseException as e:
                self.assertTrue(isinstance(e, SystemExit),
                                get_traceback_str())
                self.assertTrue(e.code in expected_exit_code)
            finally:
                sys.argv = original_sys_argv
                sys.path.remove(new_path)

            tester()
        finally:
            if os.path.exists(new_sed):
                os.remove(new_sed)
            key = "__DATETIME__"
            log_prefix = (LOG_FILENAME_FORMAT % key).split(key)[0]
            for filename in os.listdir(LOG_DIR):
                extension = os.path.splitext(filename)[-1]
                if extension == '.log' and filename.startswith(log_prefix):
                    os.remove(os.path.join(LOG_DIR, filename))

    def _get_dds_and_seds_for_testing(self):
        """ List all directories in Resources/sed_update and look for 4 files
        inside each directory with the following pattern:
            1. *.from.xml            -> representing the from state DD
            2. *.to.xml              -> representing the to state DD
            3. *.cfg                 -> representing the SED file
            4. *.cfg.expected        -> representing a expected SED updated
        :return generator: list of tuples (from_dd, to_dd, sed, new_sed, expected)
        """
        for item in os.listdir(RESOURCES_DIR):
            path = os.path.join(RESOURCES_DIR, item)
            if not os.path.isdir(path):
                continue
            files = os.listdir(path)

            get_file = lambda x: next((os.path.join(path, f)
                                      for f in files if f.endswith(x)), None)
            from_dd = get_file('.from.xml')
            to_dd = get_file('.to.xml')
            sed = get_file('.cfg')
            new_sed = "%s.updated" % sed
            expected = get_file('.cfg.expected')
            self.assertTrue(sed is not None,
                            "SED .cfg file missing on %s" % path)
            self.assertTrue(from_dd is not None,
                            ".from.xml file missing on %s" % path)
            self.assertTrue(to_dd is not None,
                            ".to.xml file missing on %s" % path)
            self.assertTrue(expected is not None,
                            "SED .cfg.expected file missing on %s" % path)
            yield from_dd, to_dd, sed, new_sed, expected

    def test_successful_sed_update_script(self):

        def _tester():
            with open(new_sed) as new_sed_file:
                with open(expected) as expected_sed_file:
                    self.assertEquals(new_sed_file.read(),
                                      expected_sed_file.read())
        data = self._get_dds_and_seds_for_testing()
        for from_dd, to_dd, sed, new_sed, expected in data:
            self._run_sed_update_script(sed, from_dd, to_dd, new_sed,
                                        [0, None], _tester)

    def test_invalid_file_provided_to_sed_update_script(self):
        data = self._get_dds_and_seds_for_testing()
        first = next(data, None)
        self.assertTrue(first is not None)
        from_dd, to_dd, sed, new_sed, expected = first
        self._run_sed_update_script("invalid sed path", from_dd,
                                    to_dd, new_sed, [2], lambda: None)
        self._run_sed_update_script(sed, "invalid old DD path",
                                    to_dd, new_sed, [2], lambda: None)
        self._run_sed_update_script(sed, from_dd, "invalid new DD path",
                                    new_sed, [2], lambda: None)
