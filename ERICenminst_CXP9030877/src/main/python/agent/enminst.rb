require 'fileutils'
require 'syslog'
require 'facter'

module MCollective
  module Agent
    class Enminst<RPC::Agent
      begin
        PluginManager.loadclass("MCollective::Util::VxvmUtils")
        vx_utils = Util::VxvmUtils
      rescue LoadError => e
        raise "Cannot load utils: %s" % [e.to_s]
      end

      def log(log_name, *args)
        begin
          logname = 'Enminst.' + log_name
          Syslog.open(logname)
          Syslog.log(Syslog::LOG_INFO, *args)
        ensure
          Syslog.close
        end
      end

      action 'hagrp_display' do
        implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
      end

      action 'hasys_display' do
        implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
      end

      action 'hagrp_history' do
        implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
      end

      action 'hagrp_modify' do
        implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
      end

      action 'hagrp_add_triggers_enabled' do
        implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
      end

      action 'hagrp_delete_triggers_enabled' do
        implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
      end

      action "cluster_app_agent_num_threads" do
        implemented_by "/opt/mcollective/mcollective/agent/enminst.py"
      end

      action 'check_service' do
        if File.exist?('/opt/mcollective/mcollective/agent/enminst.py')
          implemented_by '/opt/mcollective/mcollective/agent/enminst.py'
        else
          implemented_by '/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents/files/enminst.py'
        end
      end

      action 'cluster_seed' do
        cmd = %{/sbin/gabconfig -l | /bin/grep 'Node count' | /bin/awk '{print $NF}'}
        self.log('cluster_seed', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_grub_conf_lvs' do
        cmd = '/bin/grep "rd.lvm.lv=" /boot/grub2/grub.cfg | /bin/head -1 | /bin/perl -nle"print $& while m{rd.lvm.lv=\S+\K(?<=/)\S+(?=\s)}g"'
        self.log('get_grub_conf_lvs', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'haclus_list' do
        cmd = '/opt/VRTSvcs/bin/haclus -list '
        self.log('haclus_list', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'lltstat_active' do
        cmd = '/sbin/lltstat -nvv active '
        self.log('lltstat', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_list' do
        cmd = '/opt/VRTSvcs/bin/hagrp -list '
        self.log('hagrp_list', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_state' do
        self.log('hagrp_state', '%s', 'Getting group states')
        cmd = '/opt/VRTS/bin/hagrp -state '
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_clear' do
        group_name = request[:group_name]
        cmd = %{/opt/VRTS/bin/hagrp -clear #{group_name} }
        if request[:system]
          cmd += ' -sys ' + request[:system]
        end
        self.log('hagrp_clear', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hasys_state' do
        cmd = '/opt/VRTS/bin/hasys -state '
        self.log('hasys_state', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_switch' do
        group = request[:group_name]
        cmd = %{/opt/VRTS/bin/hagrp -switch #{group}}
        if request[:system]
          cmd += ' -to ' + request[:system]
        else
          cmd += ' -any'
        end
        self.log('hagrp_switch', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_freeze' do
        group = request[:group_name]
        cmd = %{/opt/VRTS/bin/hagrp -freeze #{group}}
        if request[:persistent]
          cmd += ' -persistent'
        end
        self.log('hagrp_freeze' '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_unfreeze' do
        group = request[:group_name]
        cmd = %{/opt/VRTS/bin/hagrp -unfreeze #{group}}
        if request[:persistent]
          cmd += ' -persistent'
        end
        self.log('hagrp_unfreeze', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hasys_freeze' do
        cmd = '/opt/VRTS/bin/hasys -freeze'
        if request[:persistent]
          cmd += ' -persistent'
        end
        if request[:evacuate]
          cmd += ' -evacuate'
        end

        system_name = request[:system]
        cmd += %{ #{system_name}}
        self.log('hasys_freeze', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hasys_unfreeze' do
        cmd = '/opt/VRTS/bin/hasys -unfreeze'
        if request[:persistent]
          cmd += ' -persistent'
        end
        system_name = request[:system]
        cmd += %{ #{system_name}}
        self.log('hasys_unfreeze', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_offline' do
        group = request[:group_name]
        cmd = '/opt/VRTS/bin/hagrp -offline ' + group
        if request[:system]
          cmd += ' -sys ' + request[:system]
        else
          cmd += ' -any '
        end
        self.log('hagrp_offline', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'hagrp_online' do
        cmd = '/opt/VRTS/bin/hagrp -online '
        if request[:propagate]
          cmd += '-propagate '
        end

        cmd += request[:group_name]

        if request[:system]
          cmd += ' -sys ' + request[:system]
        else
          cmd += ' -any'
        end

        self.log('hagrp_online', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'vxdisk_scandisks' do
        cmd = %{/sbin/vxdisk scandisks}
        self.log('vxdisk_scandisks', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'runlevel' do
        cmd = %{runlevel | awk '{print $2}'}
        self.log('runlevel', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_mem' do
        cmd = %{/bin/grep MemTotal /proc/meminfo | /bin/awk '{print $2}'}
        self.log('get_mem', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_cores' do
        cmd = %{/bin/grep -c ^processor /proc/cpuinfo}
        self.log('get_cores', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'set_cluster_seed_control' do
        cmd = %{/sbin/gabconfig -x}
        self.log('set_cluster_seed_control', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_fs_usage' do
        cmd = %{/bin/df -hPTl -x tmpfs -x devtmpfs}
        self.log('get_fs_usage', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_stale_mounts' do
        cmd = %{/bin/df 2>&1 |grep 'Stale file handle' |awk -F: '{print $2 }'}
        self.log('get_stale_mounts', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'restore_pam_settings' do
        os_ver = Facter.value("operatingsystemmajrelease").to_i
        pam_dir = '/etc/pam.d'
        if os_ver == 7
            auth_file = "#{pam_dir}/system-auth"
        else
            auth_file = "#{pam_dir}/password-auth"
        end
        bkup_file = "#{auth_file}.bak"

        if !File.exist?(auth_file)
          reply[:retcode] = 1
          reply[:err] = "File #{auth_file} not found"
          return reply
        end

        if File.exist?(bkup_file)
          begin
            FileUtils.move(bkup_file, auth_file)
            reply[:retcode] = 0
          rescue Exception => e
            reply[:retcode] = 1
            reply[:err] = "Failed to restore #{bkup_file} to #{auth_file}: #{e}"
          end
        else
          lines = ['account\s\+required\s\+pam_access.so',
                   'account\s\+\[success=1 default=ignore\] pam_succeed_if.so service in crond quiet use_uid']

          reply[:retcode] = 0
          lines.each do |line|
            cmd = "sed -i '/^#{line}/d' #{auth_file}"
            reply[:retcode] += run("#{cmd}",
                                   :stdout => :out,
                                   :stderr => :err,
                                   :chomp => true)
          end
        end
      end

      action 'is_user_password_expired' do
        reply[:retcode] = 1
        reply[:out] = 'unknown'
        reply[:err] = ''

        user = request[:user]
        expires_str = ""
        cmd = "chage -l #{user} | grep '^Password expires' | awk -F': ' '{print $2}'"
        reply[:retcode] = run("#{cmd}",
                              :stdout => expires_str,
                              :stderr => :err,
                              :chomp => true)

        if 0 == reply[:retcode]
          if expires_str == 'never'
              reply[:out] = false
          elsif expires_str == 'password must be changed'
              reply[:out] = true
          end
        end
      end

      action 'update_initial_credentials' do
        user = request[:user]
        new_pass = request[:new_pass]
        cmd = %{if chage -l #{user} | grep "Password expires" | grep -q "password must be changed" ; then echo #{new_pass} | passwd #{user} --stdin ; else false ; fi}
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'service_list' do
        run_level = request[:run_level]
        cmd = %{chkconfig --list | grep #{run_level}:on | awk '{print $1}'}
        self.log('service_list', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'lvs_list' do
        lvopts = request[:lv_opts]
        cmd = %{echo #{lvopts};}
        cmd += %{lvs -o #{lvopts} --separator , --unquoted --noheadings}
        self.log('lvs_list', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'vxfenclearpre' do
        implemented_by '/opt/mcollective/mcollective/agent/vxfenclearpre_nocheck'
      end

      action 'create_lv_snapshots' do
        if File.exist?('/opt/mcollective/mcollective/agent/enminst_snapshots.py')
          implemented_by '/opt/mcollective/mcollective/agent/enminst_snapshots.py'
        else
          implemented_by '/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents/files/enminst_snapshots.py'
        end
      end

      action 'delete_lv_snapshots' do
        if File.exist?('/opt/mcollective/mcollective/agent/enminst_snapshots.py')
          implemented_by '/opt/mcollective/mcollective/agent/enminst_snapshots.py'
        else
          implemented_by '/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents/files/enminst_snapshots.py'
        end
      end

      action 'restore_lv_snapshots' do
        if File.exist?('/opt/mcollective/mcollective/agent/enminst_snapshots.py')
          implemented_by '/opt/mcollective/mcollective/agent/enminst_snapshots.py'
        else
          implemented_by '/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents/files/enminst_snapshots.py'
        end
      end

      action 'execute_sync_command' do
        if File.exist?('/opt/mcollective/mcollective/agent/enminst_snapshots.py')
          implemented_by '/opt/mcollective/mcollective/agent/enminst_snapshots.py'
        else
          implemented_by '/opt/ericsson/nms/litp/etc/puppet/modules/mcollective_agents/files/enminst_snapshots.py'
        end
      end

      action 'dsreplication_status' do
          base_dn = request[:baseDN]
          password = request[:password]
          host = request[:host]
        if File.exist?('/opt/ericsson/com.ericsson.oss.security/idenmgmt/opendj/bin/monitor_replication.sh')
          cmd = %{sh /opt/ericsson/com.ericsson.oss.security/idenmgmt/opendj/bin/monitor_replication.sh}
          cmd_for_log = "sh /opt/ericsson/com.ericsson.oss.security/idenmgmt/opendj/bin/monitor_replication.sh"
          self.log('dsreplication status', '%s', "#{cmd_for_log}")
          reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        else
          cmd = "/opt/opendj/bin/dsreplication status --baseDN #{base_dn} --adminUID repadmin --adminPassword #{password} --hostname #{host} --port 4444 -X -n"
          cmd_for_log = "/opt/opendj/bin/dsreplication status --baseDN #{base_dn} --adminUID repadmin --adminPassword xxxx --hostname #{host} --port 4444 -X -n"
          self.log('dsreplication status', '%s', "#{cmd_for_log}")
          reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        end
      end

      action 'boot_partition_test' do
        cmd = 'dd if=/dev/urandom of=/boot/.enm_prechecks_test bs=1K count=1 conv=fsync'
        self.log('boot_partition_test', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'boot_partition_test_cleanup' do
        cmd = 'rm -f /boot/.enm_prechecks_test'
        self.log('boot_partition_test_cleanup', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'boot_partition_mount' do
        cmd1 = 'cd /root && umount -f /boot'
        self.log('boot_partition_mount', '%s', "#{cmd1}")
        run("#{cmd1}")

        cmd2 = 'cd /root && /bin/mount /boot'
        self.log('boot_partition_mount', '%s', "#{cmd2}")
        reply[:retcode] = run("#{cmd2}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'remove_packages' do
        package = request[:package]
        cmd = %{yum remove -y #{package}}
        self.log('remove_packages', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'upgrade_packages' do
        package = request[:package]
        cmd = %{yum upgrade -y #{package}}
        self.log('upgrade_packages', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'get_package_info' do
        package = request[:package]
        cmd = %{rpm -q --queryformat name=%{NAME},version=%{VERSION},release=%{RELEASE} #{package}}
        self.log('get_package_info', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'consul_service_restart' do
        if (Facter.value(:operatingsystemmajrelease).to_i < 7)
            cmd = %{/sbin/service consul restart}
        else
            cmd = %{/usr/bin/systemctl restart consul.service}
        end
        self.log('Consul service restart', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'get_available_package_versions' do
        package = request[:package]
        cmd = %{yum list | grep #{package}}
        self.log('get_available_package_versions', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'downgrade_packages' do
        package = request[:package]
        cmd = %{yum downgrade -y #{package}}
        self.log('downgrade_packages', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'install_packages' do
        package = request[:package]
        cmd = %{yum install -y #{package}}
        self.log('install_packages', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                               :stdout => :out,
                               :stderr => :err,
                               :chomp => true)
      end

      action 'physical_volume_scan' do
        cmd = 'pvscan | egrep \'^ *PV\' | awk \'{printf("%s %s\n", $2, $4)}\' | sort'
        self.log('physical_volume_scan', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'lvm_conf_backups_cleanup' do
        cmd = 'rm -f /etc/lvm/lvm.conf.backup*'
        self.log('lvm_conf_backups_cleanup', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_lvm_conf_filter' do
        cmd = "grep filter /etc/lvm/lvm.conf | egrep -v '^[[:space:]]*#' | egrep -v global | awk -F= '{print $2}'"
        self.log('get_lvm_conf_filter', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_lvm_conf_global_filter' do
        cmd = "grep global_filter /etc/lvm/lvm.conf | egrep -v '^[[:space:]]*#' | awk -F= '{print $2}'"
        self.log('get_lvm_conf_global_filter', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'backup_lvm_conf' do
        cmd = "cp /etc/lvm/lvm.conf /etc/lvm/lvm.conf.backup-$(date +%F_%R)"
        self.log('backup_lvm_conf', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "update_lvm_conf_global_filter" do
        cmd = "sed -i -e '/global_filter = \\[/s/]$/\"r\\|\\^\\/dev\\/sd\\.\\*\\|\", ]/g' /etc/lvm/lvm.conf"
        self.log('update_lvm_conf_global_filter', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'add_lvm_nondb_global_filter' do
        cmd = "sed -i -e '/# global_filter = /c\global_filter = \\[ \"a\\|\\/dev\\/mapper\\/mpath\\.\\*\\|\", \"r\\|\\.\\*\\|\" ]' /etc/lvm/lvm.conf"
        self.log('add_lvm_conf_non_db_global_filters', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'add_lvm_nondb_filter' do
        cmd = "sed -i -e '/# global_filter = /a filter = \\[ \"a\\|\\/dev\\/mapper\\/mpath\\.\\*\\|\", \"r\\|\\.\\*\\|\" ]' /etc/lvm/lvm.conf"
        self.log('add_lvm_conf_non_db_filter', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_active_and_prime_bond_mbr' do
        cmd = "grep -A 1 'Primary Slave:' /proc/net/bonding/bond0"
        self.log('get_active_and_prime_bond_mbr', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'get_bond_interface_info' do
        cmd = "grep -A 2 'Slave Interface:' /proc/net/bonding/bond0"
        self.log('get_bond_interface_info', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "get_count_dmsetup_deps_non_dm" do
        cmd = "dmsetup deps -o devname"
        self.log('get_count_dmsetup_deps_non_dm', '%s', "#{cmd}")

        lines = ""
        retcode = run("#{cmd}",
                      :stdout => lines,
                      :stderr => :err,
                      :chomp => true)
        if retcode != 0
            reply[:retcode] = retcode
            reply[:err] = "Error running '#{cmd}'"
        else
            match_count = 0
            lines.each_line do |line|
                line = line.strip()
                if line.include?('(sd')
                    match_count += 1
                end
            end
            reply[:retcode] = 0
            reply[:out] = "#{match_count}"
        end
      end

      action "stop_vcs_and_reboot" do
        cmd1 = '/opt/VRTSvcs/bin/hastop -local -evacuate'
        self.log('stop_vcs_and_reboot', '%s', "#{cmd1}")

        retcode1 = run("#{cmd1}")
        if retcode1 != 0
            reply[:retcode] = retcode1
            reply[:err] = "Error running '#{cmd1}'"
        else
            cmd2 = '(/sbin/shutdown -r now)&'
            self.log('stop_vcs_and_reboot', '%s', "#{cmd2}")
            reply[:status] = run("#{cmd2}",
                                  :stdout => :out,
                                  :stderr => :err,
                                  :chomp => true)
        end
      end

      action 'migrate_elasticsearch_indexes' do
        if File.exist?('/usr/share/elasticsearch/migrate_indexes.sh')
            cmd = %{/usr/share/elasticsearch/migrate_indexes.sh}
            self.log('migrate_indexes', '%s', "#{cmd}")
            reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        else
            self.log('migrate_elasticsearch_indexes', '%s', 'index migration script not present')
            reply[:retcode] = 0
        end
      end

      action "get_redundancy_level" do
        retcode = run("/usr/bin/which vxdmpadm")
        if retcode != 0
            cmd = "/sbin/multipath -ll"
        else
            cmd = "/sbin/vxdmpadm getsubpaths"
        end
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "get_mco_fact_disk_list" do
        retcode = run("/usr/bin/which vxdmpadm")
        if retcode != 0
            cmd = "grep 'disk_' /etc/mcollective/facts.yaml; echo -e 'dev_mapper_list:'; ls -l /dev/mapper"
            reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        else
          reply[:retcode] = 0
        end
      end

      action "get_mp_bind_names_config" do
        retcode = run("/usr/bin/which vxdmpadm")
        if retcode != 0
            cmd = "awk '/^mpath/ {print $1}' /etc/multipath/bindings | grep ."
            reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        else
          reply[:retcode] = 0
        end
      end

      action "safe_shutdown" do
        cmd = "shutdown -h now"
        self.log('shutdown', '%s', "#{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action 'neo4j_cluster_overview' do
        if File.exist?('/opt/ericsson/neo4j/scripts/cluster_overview.py')
            cmd = %{/opt/ericsson/neo4j/scripts/cluster_overview.py json}
            self.log('neo4j_cluster_overview', '%s', "#{cmd}")
            reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        else
            self.log('neo4j_cluster_overview', '%s', 'cluster_overview.py script not present')
            reply[:retcode] = 77
            reply[:err] = 'cluster_overview.py script not present'
        end
      end

      action 'postgres_mount_perc_used' do
        if File.exist?('/ericsson/postgres/data/base')
            cmd = %{df -k | grep postgres | awk 'FNR == 1 {print}' | awk '{print $5}'}
            self.log('postgres_mount_perc_used', '%s', "#{cmd}")
            reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        else
            self.log('postgres_mount_perc_used', '%s', '/ericsson/postgres/data/ is not mounted')
            reply[:retcode] = 77
            reply[:err] = '/ericsson/postgres/data/ is not mounted'
        end
      end

      action 'pre_uplift_space_check' do
        implemented_by '/opt/mcollective/mcollective/agent/neo4jfilesystem.py'
      end

      action 'has_file' do
        implemented_by '/opt/mcollective/mcollective/agent/neo4jfilesystem.py'
      end

      action 'check_ssh_connectivity' do
        implemented_by '/opt/mcollective/mcollective/agent/neo4jfilesystem.py'
      end

      action 'upgrade_dg_versions' do
        reply[:retcode] = 0
        reply[:err] = ''
        reply[:out] = ''

        dgs = vx_utils.disk_groups_in_node()
        dgs.each do |dg|
            list_cmd = "/sbin/vxdg list #{dg} | grep version | awk '{print $2}'"
            dg_ver = ""
            retcode = run("#{list_cmd}",
                          :stdout => dg_ver,
                          :stderr => :err,
                          :chomp => true)
            if 0 == retcode
                if dg_ver != request[:dg_target_ver]
                    upgrd_cmd = "/sbin/vxdg upgrade #{dg}"
                    retcode = run("#{upgrd_cmd}",
                                  :stdout => :out,
                                  :stderr => :err,
                                  :chomp => true)
                    if 0 != retcode
                        reply[:retcode] = retcode
                        reply[:err] = "Error running #{upgrd_cmd}"
                        break
                    end
                end
            else
                reply[:retcode] = retcode
                reply[:err] = "Error running #{list_cmd}"
                break
            end
        end

        if 0 != reply[:retcode] or dgs.to_s.empty?
            return reply
        end

        mount_cmd = "mount | grep 'type vxfs'"
        mounts = ""
        retcode = run("#{mount_cmd}",
                      :stdout => mounts,
                      :stderr => :err,
                      :chomp => true)

        mounts.each_line do |fs_line|
            line_parts = fs_line.split(' ')
            fs = line_parts[0]
            mount = line_parts[2]

            fs_ver = ""
            ver_cmd = "/opt/VRTS/bin/fstyp -v #{fs} | grep version | awk '{print $4}'"
            retcode = run("#{ver_cmd}",
                          :stdout => fs_ver,
                          :stderr => :err,
                          :chomp => true)
            if 0 == retcode
                if fs_ver != request[:dl_target_ver]
                    startver = Integer(fs_ver) + 1
                    endver = Integer(request[:dl_target_ver])
                    (startver..endver).each do |ver|
                        vxupdg_cmd = "/opt/VRTS/bin/vxupgrade -n #{ver} #{mount}"
                        retcode = run("#{vxupdg_cmd}",
                                      :stdout => :out,
                                      :stderr => :err,
                                      :chomp => true)
                        if 0 != retcode
                            reply[:retcode] = retcode
                            reply[:err] = "Error running #{vxupdg_cmd}"
                            break
                        end
                    end
                    if 0 != reply[:retcode]
                        break
                    end
                end
            else
                reply[:retcode] = retcode
                reply[:err] = "Error running #{ver_cmd}"
                break
            end
        end
      end

      action 'set_selinux' do
        mode = request[:mode]
        cmd = "sed -i -e 's/^\\(SELINUX=\\).*$/\\1#{mode}/' /etc/selinux/config"
        self.log('set_selinux', "Set SELinux to #{mode} using #{cmd}")
        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "hares_display" do
        resource = request[:resource]
        cmd = "/opt/VRTS/bin/hares -display #{resource}"
        self.log('hares_display', "Res display using: #{cmd}")

        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
      end

      action "hares_delete_no_offline" do
        resource = request[:resource]
        cmd = "/opt/VRTS/bin/hares -delete #{resource}"
        self.log('hares_delete', "Res delete using: #{cmd}")

        reply[:retcode] = run("#{cmd}",
                              :stdout => :out,
                              :stderr => :err,
                              :chomp => true)
        if reply[:err].include?('VCS WARNING V-16-1-10260') then
            reply[:retcode] = 0
            reply[:err] = ''
        end
      end

    end
  end
end
