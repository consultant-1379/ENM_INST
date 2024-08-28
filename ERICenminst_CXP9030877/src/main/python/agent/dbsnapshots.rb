require 'syslog'

def log(message)
  Syslog.open($0, Syslog::LOG_PID | Syslog::LOG_CONS) { |s| s.info message }
end

module MCollective
  module Agent
    class Dbsnapshots<RPC::Agent

      action "create_snapshot" do
        implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
      end

      action "opendj_backup" do
        implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
      end

      action "opendj_cleanup" do
        implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
      end

      action "ensure_installed" do
        implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
      end
    end
  end
end
