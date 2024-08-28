require 'syslog'

def log(message)
  Syslog.open($0, Syslog::LOG_PID | Syslog::LOG_CONS) { |s| s.info message }
end

module MCollective
  module Agent
    class Neo4jsnapshots<RPC::Agent

        action "force_neo4j_checkpoint" do
            implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
        end

        action "freeze_neo4j_db_filesystem" do
            implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
        end

        action "unfreeze_neo4j_db_filesystem" do
            implemented_by "/opt/mcollective/mcollective/agent/dbsnapshots.py"
        end

    end
  end
end
