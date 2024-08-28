authconfig --enableshadow --passalgo=sha512
text
firewall --enabled --port=123:udp
firstboot --disable
keyboard uk
lang en_US
url --url=$tree
repo --name=3PP --baseurl=http://$http_server/3pp
repo --name=UPDATES --baseurl=http://$http_server/6/updates/x86_64/Packages
# Network information
$SNIPPET('network_config')
reboot

rootpw --iscrypted @@ROOT_PASSWD@@
selinux --enforcing
skipx
timezone --utc Europe/Dublin
install
zerombr

# System bootloader configuration
%include /tmp/bootloader.info

# Use partition information generated
%include /tmp/partitioninfo

%pre --erroronfail
$SNIPPET('log_ks_pre')
$SNIPPET($hostname + '.ks.bootloader.snippet')
$SNIPPET($hostname + '.ks.partition.snippet')
$SNIPPET('pre_install_network_config')
# Enable installation monitoring
$SNIPPET('pre_anamon')
%end

%packages --nobase
@Core
-rsyslog
rsyslog7
@server-policy
wget
ntp
lsof
man
screen
strace
tcpdump
pexpect
policycoreutils-python
nfs-utils
openssh-clients
tmpwatch
device-mapper-multipath
device-mapper-multipath-libs
kpartx
pciutils
libaio
libvirt
libvirt-python
ltrace
traceroute
bind-utils
sysstat
vim-common
vim-enhanced
qemu-kvm
python-virtinst
procmail
bridge-utils
kexec-tools
tcl-8.5.7-6.el6.x86_64
yum-utils
yum-plugin-versionlock


%post --log=/var/log/ks-post.log --erroronfail

# Setup the root user key
mkdir -m0700 /root/.ssh/
echo "@@ROOT_PUB_KEY@@" > /root/.ssh/authorized_keys
chmod 0600 /root/.ssh/authorized_keys
restorecon -R /root/.ssh

# add OS yum repo config
echo "[OS]" > /etc/yum.repos.d/OS.repo
echo "name = RHEL OS" >> /etc/yum.repos.d/OS.repo
echo "baseurl = http://$http_server/6/os/x86_64/Packages" >> /etc/yum.repos.d/OS.repo
echo "enabled = 1" >> /etc/yum.repos.d/OS.repo
echo "gpgcheck = 0" >> /etc/yum.repos.d/OS.repo

# add UPDATES yum repo config
echo "[UPDATES]" > /etc/yum.repos.d/UPDATES.repo
echo "name = RHEL Updates" >> /etc/yum.repos.d/UPDATES.repo
echo "baseurl = http://$http_server/6/updates/x86_64/Packages" >> /etc/yum.repos.d/UPDATES.repo
echo "enabled = 1" >> /etc/yum.repos.d/UPDATES.repo
echo "gpgcheck = 0" >> /etc/yum.repos.d/UPDATES.repo

# add 3PP yum repo config
echo "[3PP]" > /etc/yum.repos.d/3PP.repo
echo "name = Third-Party Packages for LITP" >> /etc/yum.repos.d/3PP.repo
echo "baseurl = http://$http_server/3pp" >> /etc/yum.repos.d/3PP.repo
echo "enabled = 1" >> /etc/yum.repos.d/3PP.repo
echo "gpgcheck = 0" >> /etc/yum.repos.d/3PP.repo

# add LITP yum repo config
echo "[LITP]" > /etc/yum.repos.d/LITP.repo
echo "name = LITP Packages" >> /etc/yum.repos.d/LITP.repo
echo "baseurl = http://$http_server/litp" >> /etc/yum.repos.d/LITP.repo
echo "enabled = 1" >> /etc/yum.repos.d/LITP.repo
echo "gpgcheck = 0" >> /etc/yum.repos.d/LITP.repo

rm -f /etc/yum.repos.d/rhel-source.repo

yum clean all
yum install -y ERIClitpmnlibvirt_CXP9031529

# Configuration for COM
cd /usr/lib64/
echo  "/usr/lib64/perl5/CORE" > /etc/ld.so.conf.d/perl.conf
ldconfig

#### Create directory for coredumps ####
mkdir -p /var/coredumps
chmod 1777 /var/coredumps

#### Tune kernel parameters ####
cat << 'EOF' >> /etc/sysctl.conf

kernel.core_pattern = /var/coredumps/core.%e.pid%p.usr%u.sig%s.tim%t
fs.suid_dumpable = 2

EOF

#### Add filter to lvm.conf
if [ -f /etc/lvm/lvm.conf ] ; then
    grep -q '    filter = \[ "a\/.*\/" \]' /etc/lvm/lvm.conf
    if (( $? == 0 )) ; then
        cp -f /etc/lvm/lvm.conf /etc/lvm/lvm.conf.orig
        sed -i 's/    filter = \[ "a\/.*\/" \]/    filter = \[ "r\/block\/", "r\/disk\/by-path\/", "r\/disk\/by-uuid\/", "r\/disk\/by-id\/", "a\/.\/" \]/g' /etc/lvm/lvm.conf
    fi
fi

echo ''                                                   >> /etc/security/limits.conf
echo '*               soft    core            unlimited'  >> /etc/security/limits.conf
echo ''                                                   >> /etc/sysconfig/init
echo 'DAEMON_COREFILE_LIMIT=unlimited'                    >> /etc/sysconfig/init
echo ''                                                   >> /etc/profile
echo '# ulimit -c unlimited'                              >> /etc/profile

### Add path for nascli
cat << 'EOF' >> /etc/profile.d/nascli.sh

PATH=$PATH:/opt/ericsson/storage/bin/
export PATH

EOF

# force change password at first login
# chage -d 0 litp-admin
# chage -d 0 root

# set minimum password len 9
perl -npe 's/PASS_MIN_LEN\s+5/PASS_MIN_LEN  9/' -i /etc/login.defs

/bin/echo "server $http_server" >> /etc/ntp.conf
ntpdate -u $http_server
chkconfig ntpd on
chkconfig iptables off
chkconfig ip6tables off
hwclock --systohc

$SNIPPET('log_ks_post')

rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-*
# End yum configuration
$SNIPPET('post_install_kernel_options')
$SNIPPET('post_install_network_config')
$SNIPPET('download_config_files')
$SNIPPET('koan_environment')

# Dump GRUB's device mapping for debugging purposes
if [[ -f /boot/grub/device.map ]]; then
	dmap="/boot/grub/device.map"
else
	echo '' | grub --batch --device-map=/tmp/test_devmap --no-floppy
	dmap="/tmp/test_devmap"
fi
cat \${dmap}

grub_info=\$(mktemp)
while read grub_dev kernel_dev; do
	header="GRUB disk ID \${grub_dev} maps to the following device"
	padding_length=\$(( 4 + \${#header} ))
	separator=\$(printf -- '-%.0s' \$(eval echo {1..\${padding_length}}) )
	echo \${separator} > \${grub_info}
	echo "| \${header} |" >> \${grub_info}
	echo \${separator} >> \${grub_info}
	udevadm info --query=all --name=\${kernel_dev} >> \${grub_info}
	echo \${separator} >> \${grub_info}
done < \${dmap}

cat \${grub_info}
rm \${grub_info}

$SNIPPET('cobbler_register')
$SNIPPET('version.snippet')
$SNIPPET($hostname + '.ks.udev_network.snippet')
# Enable post-install boot notification
$SNIPPET('post_anamon')
# Start final steps
$SNIPPET('kickstart_done')
# End final steps
rm -rf /tmp/ks-script-*
rm -f /tmp/bootloader.info
%end
