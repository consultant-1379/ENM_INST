from unittest2 import TestCase

from h_util.h_ssh.cmd import Command


class TestCommand(TestCase):
    def test_simple_sudo_command(self):
        cmd = Command("whoami", sudo=True)
        expected = 'sudo sh -c "whoami"'
        self.assertEqual(expected, str(cmd))

    def test_user_command_with_env_var(self):
        cmd = Command("/opt/rh/postgresql/bin/psql", su_user="postgres", env={"PGPASSWORD": "SECRET"})
        expected = 'su postgres -c "PGPASSWORD=\'SECRET\' /opt/rh/postgresql/bin/psql"'
        self.assertEqual(expected, str(cmd))

    def test_env_sourced_command(self):
        cmd = Command("/ericsson/3pp/neo4j/bin/neo4j-admin version", su_user="neo4j", sh_source_path="/etc/neo4j/neo4j_env")
        expected = 'su neo4j -c ". /etc/neo4j/neo4j_env; /ericsson/3pp/neo4j/bin/neo4j-admin version"'
        self.assertEqual(expected, str(cmd))

    def test_command_with_timeout(self):
        cmd = Command("/ericsson/3pp/neo4j/bin/neo4j-admin version", timeout=10)
        expected = '/usr/bin/timeout 10 sh -c "/ericsson/3pp/neo4j/bin/neo4j-admin version"'
        self.assertEqual(expected, str(cmd))

    def test_masked_command(self):
        cmd = Command("/opt/rh/postgresql/bin/psql", su_user="postgres",
                      env={"PGPASSWORD": "SECRET"}, mask=r"PGPASSWORD=([^\s]+)")
        expected = 'su postgres -c "PGPASSWORD=****** /opt/rh/postgresql/bin/psql"'
        self.assertEqual(expected, cmd.masked)
