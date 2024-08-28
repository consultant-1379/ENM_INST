#!/bin/bash
LMS_IP=$(/usr/bin/litp show -p /ms/network_interfaces/eth0 -o ipaddress)
vm_service_update () {
   for vm_name in $(/usr/bin/litp show -p /software/services/ -r | grep -A8 vm-service | grep service_name | awk '{print $NF}'); do
        echo -e "\n"
        echo "litp update -p /software/services/${vm_name}/vm_aliases/ms-1_alias -o address=${LMS_IP}"
        echo -e "\n"
   done
}
vm_image_update() {
    lsb_image=$(/usr/bin/litp show -p /software/images/lsb-image | grep source_uri: | awk '{print $NF}' | awk -F '/' '{print $NF}')
    jboss_image=$(/usr/bin/litp show -p /software/images/jboss-image | grep source_uri: | awk '{print $NF}' | awk -F '/' '{print $NF}')
    echo -e "\n"
    echo "litp update -p /software/images/lsb-image -o source_uri=http://${LMS_IP}/images/ENM/${lsb_image}"
    echo -e "\n"
    echo "litp update -p /software/images/jboss-image -o source_uri=http://${LMS_IP}/images/ENM/${jboss_image}"
}
vm_service_update
vm_image_update
#end
