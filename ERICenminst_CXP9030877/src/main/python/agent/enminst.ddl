metadata :name        => "enminst",
         :description => "Enminst MCO commands",
         :author      => "Ericsson AB",
         :license     => "Ericsson AB 2015",
         :version     => "1.0",
         :url         => "",
         :timeout     => 3600

action "boot_partition_test", :description => "Test if the /boot partition is writable" do
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

action "boot_partition_test_cleanup", :description => "Cleanup after testing if the /boot partition is writable" do
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

action "boot_partition_mount", :description => "Mount the /boot partition" do
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

action "remove_packages", :description => "Removes packages for removal and dependencies" do
    display :always

    input  :package,
           :prompt      => "Package",
           :description => "Package to remove",
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

action "get_available_package_versions", :description => "Get package versions" do
    display :always

    input  :package,
           :prompt      => "Package",
           :description => "Get available Package versions",
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

action "upgrade_packages", :description => "Upgrade packages" do
    display :always

    input  :package,
           :prompt      => "Package",
           :description => "Package to upgrade",
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

action "downgrade_packages", :description => "Downgrade packages" do
    display :always

    input  :package,
           :prompt      => "Package",
           :description => "Package to downgrade",
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

action "install_packages", :description => "Install packages" do
    display :always

    input  :package,
           :prompt      => "Package",
           :description => "Package to install",
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

action "upgrade_rpm", :description => "Upgrade rpm" do
    display :always

    input  :rpm,
           :prompt      => "rpm",
           :description => "path to rpm to upgrade",
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

action "get_package_info", :description => "get RPM info" do
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

action "consul_service_restart", :description => "restart service" do
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

action "physical_volume_scan", :description => "Run pvscan" do
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

action "lvm_conf_backups_cleanup", :description => "Remove lvm.conf backup files" do
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

action "get_lvm_conf_filter", :description => "Get filter from lvm.conf" do
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

action "get_lvm_conf_global_filter", :description => "Get global_filter from lvm.conf" do
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

action "update_lvm_conf_global_filter", :description => "Update global_filter in lvm.conf" do
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

action "add_lvm_nondb_global_filter", :description => "Update global_filter in lvm.conf" do
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

action "add_lvm_nondb_filter", :description => "Update filter in lvm.conf" do
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

action "backup_lvm_conf", :description => "Backup lvm.conf" do
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

action "get_grub_conf_lvs", :description => "Get LVs present in grub.cfg file" do
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

action "get_active_and_prime_bond_mbr", :description => "Get active and primary member from bond0 file" do
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

action "get_bond_interface_info", :description => "Get info on bond interfaces from bond0 file" do
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

action "get_count_dmsetup_deps_non_dm", :description => "Get dmsetup dependencies for non device-mapper" do
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

action "stop_vcs_and_reboot", :description => "Stop VCS and reboot server" do
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


action "dsreplication_status", :description => "Get the OpenDJ replication status" do
    display :always

    input  :baseDN,
           :prompt      => "baseDN",
           :description => "Base DN",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :password,
           :prompt      => "Password",
           :description => "Admin password",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :host,
           :prompt      => "Hostname",
           :description => "Hostname",
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


action "lltstat_active", :description => "Get the status of LLT interfaces" do
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

action "haclus_list", :description => "Get a list of known clusters" do
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

action "hagrp_list", :description => "Get a list of known groups" do
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

action "hagrp_history", :description => "Get a list start/stop times for a group" do
    display :always

    input  :groups,
           :prompt      => "Group Name",
           :description => "Group to get the history for.",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "hagrp_display", :description => "Get a list of known groups" do
    display :always

    input  :groups,
           :prompt      => "Group Name(s)",
           :description => "Comma separated list of VCS groups to get the attributes from",
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

action "hasys_display", :description => "Get a list of known groups" do
    display :always

    input  :systems,
           :prompt      => "Systems",
           :description => "Comma separated list of VCS systems to get the attributes from",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "hagrp_clear", :description => "access hagrp -clear command" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :system,
           :prompt      => "System to clear the group on",
           :description => "The name of the system to clear the group on",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "hagrp_state", :description => "Lists all VCS groups states" do
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

action "hagrp_add_triggers_enabled", :description => "access hagrp -hagrp_add_triggers_enabled command" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :attribute_val,
           :prompt      => "Attribute Value",
           :description => "The value of the attribute",
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

action "hagrp_delete_triggers_enabled", :description => "access hagrp -hagrp_delete_triggers_enabled command" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :attribute_val,
           :prompt      => "Attribute Value",
           :description => "The value of the attribute",
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

action "hagrp_modify", :description => "access hagrp -modify command" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :attribute,
           :prompt      => "Attribute Name",
           :description => "The name of the attribute",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :attribute_val,
           :prompt      => "Attribute Value",
           :description => "The value of the attribute",
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

action "cluster_app_agent_num_threads", :description => "Set the number of threads the VCS application agent uses to manage application resources" do
    display :always

    input  :app_agent_num_threads,
           :prompt      => "Application NumThreads value",
           :description => "The number of threads the VCS application agent uses to manage application resources.",
           :type        => :integer,
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

action "cluster_seed", :description => "Read the cluster seed" do
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

action "hasys_state", :description => "Lists all VCS systems states" do
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

action "hagrp_switch", :description => "Switches groups" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :system,
           :prompt      => "System to bring the group offline on",
           :description => "System to bring the group offline on",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "hagrp_freeze", :description => "Freeze a group" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :persistent,
           :prompt      => "persistent",
           :description => "If true, the freeze is maintained after a system is rebooted",
           :type        => :boolean,
           :optional    => true,
           :default     => false

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

action "hagrp_unfreeze", :description => "Unfreeze a group" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :persistent,
           :prompt      => "persistent",
           :description => "If true, the unfreeze is maintained after a system is rebooted",
           :type        => :boolean,
           :optional    => true,
           :default     => false

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

# Dont use the LITP freeze/lock agent as that will take groups offline
action "hasys_freeze", :description => "Freeze a system" do
    display :always

    input  :system,
           :prompt      => "system",
           :description => "The name of the system",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :persistent,
           :prompt      => "persistent",
           :description => "If true, the freeze is maintained after a system is rebooted",
           :type        => :boolean,
           :optional    => true,
           :default     => false

    input  :evacuate,
           :prompt      => "evacuate",
           :description => "If true, the system is evacuated",
           :type        => :boolean,
           :optional    => true,
           :default     => false

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


# Dont use the LITP unfreeze/unlock agent as that will take action on the groups also.
action "hasys_unfreeze", :description => "Unfreeze a system" do
    display :always

    input  :system,
           :prompt      => "system",
           :description => "The name of the system",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :persistent,
           :prompt      => "persistent",
           :description => "If true, the unfreeze is maintained after a system is rebooted",
           :type        => :boolean,
           :optional    => true,
           :default     => false

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

action "hagrp_offline", :description => "Offline a VCS group" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :system,
           :prompt      => "System to offline the group on.",
           :description => "The name of the system to offline",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "hagrp_online", :description => "Online a VCS group" do
    display :always

    input  :group_name,
           :prompt      => "Group Name",
           :description => "The name of the group",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :system,
           :prompt      => "System to offline the group on.",
           :description => "The name of the system to offline",
           :type        => :string,
           :validation  => '',
           :optional    => true,
           :maxlength   => 0

    input  :propagate,
           :prompt      => "When onlining a group all of its required child groups are also brought online",
           :description => "When onlining a group all of its required child groups are also brought online",
           :type        => :boolean,
           :optional    => true,
           :default     => false

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

action "vxdisk_scandisks", :description => "Scan devices in the operating system device tree by VxVM" do
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

action "runlevel", :description => "Get current runlevel of the blade" do
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

action "get_mem", :description => "Get provided memory value of the blade" do
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

action "get_cores", :description => "Get number of cores on a blade" do
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

action "set_cluster_seed_control", :description => "Set gabconfig to allow vcs form a cluster" do
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

action "get_fs_usage", :description => "Get local filesystem usage on nodes" do
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

action "get_stale_mounts", :description => "Get all stale mounts on nodes" do
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

action "service_list", :description => "Get a list of services that are marked as ON for a particular chkconfig runlevel" do
    display :always

    input  :run_level,
           :prompt      => "run_level",
           :description => "The system runlevel.",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "check_service", :description => "Check status of service (stopped/started)" do
    display :always

    input  :service,
           :prompt      => "service",
           :description => "The name of the service.",
           :type        => :string,
           :validation  => '',
           :optional    => true,
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

action "lvs_list", :description => "List LVM volumes" do
    display :always

    input  :lv_opts,
           :prompt      => "lv_opts",
           :description => "The LVM options to get",
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

action "create_lv_snapshots" , :description => "Create LVM volume snapshots" do
    display :always

    input  :snap_info,
           :prompt      => "snap_info",
           :description => "Snapshot data, see enminst_snapshots.py for structure",
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


action "delete_lv_snapshots" , :description => "Delete LVM volume snapshots" do
    display :always

    input  :tag_name,
           :prompt      => "tag_name",
           :description => "Delete a snapshot with a specific tag",
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

action "restore_lv_snapshots" , :description => "Restore LVM volume snapshots" do
    display :always

    input  :tag_name,
           :prompt      => "tag_name",
           :description => "Restore snapshots with a specific tag",
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

action "execute_sync_command" , :description => "Execute sync command" do
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

action "vxfenclearpre" , :description => "Remove SCSI3 registrations and reservations from disks." do
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

action "migrate_elasticsearch_indexes" , :description => "Migrate Elasticsearch indexes" do
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

action "get_redundancy_level", :description => "Get multipath redundancy and enabled paths" do
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

action "get_mco_fact_disk_list", :description => "Get mco facts and dev_mapper directory list" do
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

action "get_mp_bind_names_config", :description => "Get multipath friendly names config" do
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

action "safe_shutdown", :description => "Issue the shutdown command" do
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

action "restore_pam_settings", :description => "Restore PAM settings" do
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

action "is_user_password_expired", :description => "Is a User's password expired" do
    display :always

    input  :user,
           :prompt      => "user",
           :description => "Base DN",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    output :retcode,
           :description => "The exit code from running the command",
           :display_as => "Result code"

    output :out,
           :description => "true if expired, else false",
           :display_as => "out"

    output :err,
           :description => "The stderr from running the command",
           :display_as => "err"
end

action "update_initial_credentials", :description => "Updates nodes initial password" do
    display :always

    input  :user,
           :prompt      => "user",
           :description => "Base DN",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :new_pass,
           :prompt      => "new_pass",
           :description => "New password",
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

action "neo4j_cluster_overview", :description => "Fetch Neo4j Cluster data" do
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

action "postgres_mount_perc_used", :description => "Get Postgres mount percentage space used" do
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

action "pre_uplift_space_check", :description => "Check Neo4j Filesystem space" do
    display :always

    input  :lun_size,
           :prompt      => "Neo4j LUN size",
           :description => "Neo4j LUN size in bytes",
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

action "has_file", :description => "Check if a file exist on db node" do
    display :always

    input  :file_path,
           :prompt      => "File path",
           :description => "File location path",
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

action "check_ssh_connectivity", :description => "Check SSH connectivity from one node to another" do
    display :always

    input  :host,
           :prompt      => "Host",
           :description => "Host to SSH",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :user,
           :prompt      => "User",
           :description => "User",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :password,
           :prompt      => "Password",
           :description => "Password for the given user",
           :type        => :string,
           :validation  => '',
           :optional    => true,
           :maxlength   => 0

    input  :key_filename,
           :prompt      => "SSH key filename",
           :description => "SSH key filename location on the origin node",
           :type        => :string,
           :validation  => '',
           :optional    => true,
           :maxlength   => 0

    input  :sudo,
           :prompt      => "Use sudo",
           :description => "Use sudo",
           :type        => :boolean,
           :optional    => true,
           :default     => false

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

action "upgrade_dg_versions", :description => "Upgrade Diskgroup versions" do
    display :always

    input  :dg_target_ver,
           :prompt      => "Diskgroup target version",
           :description => "Diskgroup target version",
           :type        => :string,
           :validation  => '',
           :optional    => false,
           :maxlength   => 0

    input  :dl_target_ver,
           :prompt      => "Disk layout target version",
           :description => "Disk layout target version",
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

action "set_selinux", :description => "Set SELinux" do
    display :always

    input  :mode,
           :prompt      => "SELinux mode",
           :description => "SELinux mode (enforcing, permissive, disabled)",
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

action "hares_display", :description => "Access hares -display command" do
    display :always

    input  :resource,
           :prompt      => "Resource Name",
           :description => "The name of the resource",
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

action "hares_delete_no_offline", :description => "Access hares -delete command" do
    display :always

    input  :resource,
           :prompt      => "Resource Name",
           :description => "The name of the resource",
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
