#!/bin/bash

# Set PasswordAuthentication yes
#sed -i '/^[^#]*PasswordAuthentication[[:space:]]no/c\PasswordAuthentication yes' /etc/ssh/sshd_config

# Prohibit to set PasswordAuthentication no
#sed -i 's/updated = update_ssh_config/\    updated = False/' /usr/lib/python3/dist-packages/cloudinit/config/cc_set_passwords.py
 
