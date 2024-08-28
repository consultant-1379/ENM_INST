metadata :name        => "dbsnapshots",
         :description => "Snapshot MCO commands",
         :author      => "Ericsson AB",
         :license     => "Ericsson AB 2015",
         :version     => "1.0",
         :url         => "",
         :timeout     => 300


action "create_snapshot", :description => "Get a list of known groups" do
    display :always

    input  :dbtype,
           :prompt      => "mysql, versant or neo4j",
           :description => "db node type",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :array_type,
           :prompt      => "array_type",
           :description => "Type of Array",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :spa_ip,
           :prompt      => "spa_ip",
           :description => "IP of SPA",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :spb_ip,
           :prompt      => "spb_ip",
           :description => "IP of SPA",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :spa_username,
           :prompt      => "spa_username",
           :description => "spa username",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :Password,
           :prompt      => "Password",
           :description => "Password of SAN",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :Scope,
           :prompt      => "Scope",
           :description => "Scope",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :dblun_id,
           :prompt      => "dblun_id",
           :description => "lun ID of DB",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :snap_name,
           :prompt      => "snap_name",
           :description => "name of snapshot",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :descr,
           :prompt      => "descr",
           :description => "snapshot descr",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

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

action "opendj_backup", :description => "Take opendj_backup on both DB nodes" do
    display :always

    input  :opendj_backup_cmd,
           :prompt      => "opendj_backup_cmd",
           :description => "opendj_backup.sh including path",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :opendj_backup_dir,
           :prompt      => "opendj_backup_dir",
           :description => "backup_dir",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :opendj_log_dir,
           :prompt      => "opendj_log_dir",
           :description => "log_dir",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

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

action "ensure_installed", :description => "Install a package." do
    display :always

    input  :package,
           :prompt      => "Package to ensure is installed",
           :description => "Package to ensure is installed",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

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

action "opendj_cleanup", :description => "Cleanup opendj backup dirs" do
    display :always

    input  :opendj_backup_dir,
           :prompt      => "opendj_backup_dir",
           :description => "backup_dir",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :opendj_log_dir,
           :prompt      => "opendj_log_dir",
           :description => "log_dir",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

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
