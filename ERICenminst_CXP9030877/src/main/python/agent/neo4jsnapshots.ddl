metadata :name        => "neo4jsnapshots",
         :description => "Neo4j Snapshot MCO commands",
         :author      => "Ericsson AB",
         :license     => "Ericsson AB 2015",
         :version     => "1.0",
         :url         => "",
         :timeout     => 3600


action "force_neo4j_checkpoint", :description => "Force neo4j checkpoint" do
    display :always

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "The stdout from running the command",
           :display_as => "out"

    output :err,
           :description => "The stderr  from running the command",
           :display_as => "err"
end

action "freeze_neo4j_db_filesystem", :description => "Freeze neo4j fs" do
    display :always

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "The stdout from running the command",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end

action "unfreeze_neo4j_db_filesystem", :description => "Freeze neo4j fs" do
    display :always

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "The stdout from running the command",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end
