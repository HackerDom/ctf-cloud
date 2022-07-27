#!/usr/bin/python3
# Developed by Alexander Bersenev from Hackerdom team, bay@hackerdom.ru

"""Creates vm instance for a team"""

import sys
import json
import time
import os
import traceback

import ya_api
from cloud_common import ( # get_cloud_ip, take_cloud_ip,
                          log_progress,
                          call_unitl_zero_exit,SSH_OPTS, SSH_YA_OPTS, DOMAIN)

TEAM = int(sys.argv[1])
ROUTER_VM_NAME = "team%d-router" % TEAM
IMAGE_VM_NAME = "team%d" % TEAM
DNS_NAME = IMAGE_VM_NAME


ROUTER_YA_IMAGE = "fd8erh9mvch1cs3viqoi"
VULNIMAGE_YA_IMAGE = "fd8io4od9lo2h7a32dk9"

ADMIN_PUBLIC_SSH_KEY = open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "admin_key.pub")).read()
DEPLOY_KEY = open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "cloud_deploy_key.pub")).read()

ROUTER_MEM_GB = 2
ROUTER_CORES = 2
ROUTER_SSD_GB = 20

IMAGE_MEM_GB = 4
IMAGE_CORES = 2
IMAGE_SSD_GB = 30


def log_stderr(*params):
    print("Team %d:" % TEAM, *params, file=sys.stderr)


def main():
    net_state = open("db/team%d/net_deploy_state" % TEAM).read().strip()

    # cloud_ip = get_cloud_ip(TEAM)
    # if not cloud_ip:
    #     cloud_ip = take_cloud_ip(TEAM)
    #     if not cloud_ip:
    #         print("msg: ERR, no free vm slots remaining")
    #         return 1

    log_progress("0%")
    droplet_id = None

    if net_state == "NOT_STARTED":
        vpc_id = ya_api.get_vpc_by_name("team%d" % TEAM)
        print("vpc_id", vpc_id)

        team_network = "%d.%d.%d.%d/25" % (10, 60 + TEAM//256, TEAM%256, 0)

        router_ip = "%d.%d.%d.%d" % (10, 60 + TEAM//256, TEAM%256, 3)
        vulnimage_ip = "%d.%d.%d.%d" % (10, 60 + TEAM//256, TEAM%256, 4)

        if vpc_id is None:
            routes = [
                ["10.60.0.0/14", router_ip],
                ["10.80.0.0/14", router_ip],
                ["10.10.10.0/24", router_ip],
            ]
            vpc_id = ya_api.create_vpc("team%d" % TEAM, team_network, routes)

        if vpc_id is None:
            log_stderr("no vpc id, exiting")
            exit(1)

        print("vpc_id2", vpc_id)

        subnet_id = ya_api.get_subnet_id(vpc_id, team_network)

        if subnet_id is None:
            log_stderr("no subnet_id, exiting")
            exit(1)

        exists = ya_api.check_vm_exists(ROUTER_VM_NAME)
        if exists is None:
            log_stderr("failed to determine if vm exists, exiting")
            return 1

        log_progress("5%")

        if not exists:
            droplet_id = ya_api.create_vm(
                ROUTER_VM_NAME, ssh_keys=[ADMIN_PUBLIC_SSH_KEY, DEPLOY_KEY], image_id=ROUTER_YA_IMAGE,
                subnet_id=subnet_id, ip=router_ip, mem_gb=ROUTER_MEM_GB, cores=ROUTER_CORES,
                ssd_gb=ROUTER_SSD_GB, tag="team-router")
            if droplet_id is None:
                log_stderr("failed to create vm, exiting")
                return 1

        net_state = "DO_LAUNCHED"
        open("db/team%d/net_deploy_state" % TEAM, "w").write(net_state)
        time.sleep(10)  # this allows to make less requests (there is a limit)


    log_progress("10%")
    ip = None
    if net_state == "DO_LAUNCHED":

        for attempt in range(5):
            if not droplet_id:
                ip = ya_api.get_ip_by_vmname(ROUTER_VM_NAME)
            else:
                ip = ya_api.get_ip_by_id(droplet_id)

            if ip:
                break
            time.sleep(10)

        if ip is None:
            log_stderr("no ip, exiting")
            return 1

        log_progress("15%")

        domain_ids = ya_api.get_domain_ids_by_hostname(DNS_NAME, DOMAIN)
        if domain_ids is None:
            log_stderr("failed to check if dns exists, exiting")
            return 1

        if domain_ids:
            for domain_id in domain_ids:
                ya_api.delete_domain_record(domain_id, DOMAIN)

        log_progress("17%")

        if ya_api.create_domain_record(DNS_NAME, ip, DOMAIN):
            net_state = "DNS_REGISTERED"
            open("db/team%d/net_deploy_state" % TEAM, "w").write(net_state)
        else:
            log_stderr("failed to create vm: dns register error")
            return 1

        for i in range(20, 50):
            # just spinning for the sake of smooth progress
            log_progress("%d%%" % i)
            time.sleep(0.5)


    log_progress("50%")

    if net_state == "DNS_REGISTERED":
        if ip is None:
            ip = ya_api.get_ip_by_vmname(ROUTER_VM_NAME)

            if ip is None:
                log_stderr("no ip, exiting")
                return 1

        log_progress("55%")

        file_from = "db/team%d/server_outside.conf" % TEAM
        file_to = "%s:/etc/openvpn/server_outside_team%d.conf" % (ip, TEAM)
        ret = call_unitl_zero_exit(["scp"] + SSH_YA_OPTS +
                                   [file_from, file_to])
        if not ret:
            log_stderr("scp to DO failed")
            return 1

        log_progress("57%")

        file_from = "db/team%d/game_network.conf" % TEAM
        file_to = "%s:/etc/openvpn/game_network_team%d.conf" % (ip, TEAM)
        ret = call_unitl_zero_exit(["scp"] + SSH_YA_OPTS +
                                   [file_from, file_to])
        if not ret:
            log_stderr("scp to YA failed")
            return 1

        log_progress("60%")

        cmd = ["systemctl start openvpn@server_outside_team%d" % TEAM]
        ret = call_unitl_zero_exit(["ssh"] + SSH_YA_OPTS + [ip] + cmd)
        if not ret:
            log_stderr("start internal tun")
            return 1

        # UNCOMMENT BEFORE THE GAME
        host_int_ip = "10.%d.%d.3" % (60 + TEAM//256, TEAM%256)
        dest = "10.%d.%d.4" % (60 + TEAM//256, TEAM%256)
        cmd = ["iptables -t nat -A PREROUTING -d %s -p tcp " % host_int_ip +
               "--dport 22 -j DNAT --to-destination %s:22" % dest]
        ret = call_unitl_zero_exit(["ssh"] + SSH_YA_OPTS + [ip] + cmd)
        if not ret:
           log_stderr("unable to nat port 22")
           return 1

        log_progress("61%")

        cmd = ["iptables -t nat -A POSTROUTING -o eth1 -p tcp " +
               "-m tcp --dport 22 -j MASQUERADE"]
        ret = call_unitl_zero_exit(["ssh"] + SSH_YA_OPTS + [ip] + cmd)
        if not ret:
           log_stderr("unable to masquerade port 22")
           return 1

        log_progress("62%")

        net_state = "READY"
        open("db/team%d/net_deploy_state" % TEAM, "w").write(net_state)


        cmd = ["systemctl start openvpn@game_network_team%d" % TEAM]
        ret = call_unitl_zero_exit(["ssh"] + SSH_YA_OPTS + [ip] + cmd)
        if not ret:
            log_stderr("start main game net tun")
            return 1

        team_state = "CLOUD"
        open("db/team%d/team_state" % TEAM, "w").write(team_state)


    log_progress("65%")


    image_state = open("db/team%d/image_deploy_state" % TEAM).read().strip()

    log_progress("67%")

    if net_state == "READY":
        if image_state == "NOT_STARTED":
            pass_hash = open("db/team%d/root_passwd_hash.txt" % TEAM).read().strip()
            team_network = "%d.%d.%d.%d/25" % (10, 60 + TEAM//256, TEAM%256, 0)

            router_ip = "%d.%d.%d.%d" % (10, 60 + TEAM//256, TEAM%256, 3)
            vulnimage_ip = "%d.%d.%d.%d" % (10, 60 + TEAM//256, TEAM%256, 4)


            vpc_id = ya_api.get_vpc_by_name("team%d" % TEAM)

            if vpc_id is None:
                routes = [
                    ["10.60.0.0/14", router_ip],
                    ["10.80.0.0/14", router_ip],
                    ["10.10.10.0/24", router_ip],
                ]
                vpc_id = ya_api.create_vpc("team%d" % TEAM, team_network, routes)

            if vpc_id is None:
                log_stderr("no vpc id, exiting")
                exit(1)

            subnet_id = ya_api.get_subnet_id(vpc_id, team_network)

            if subnet_id is None:
                log_stderr("no subnet_id, exiting")
                exit(1)

            exists = ya_api.check_vm_exists(IMAGE_VM_NAME)
            if exists is None:
                log_stderr("failed to determine if vm exists, exiting")
                return 1

            log_progress("69%")

            if not exists:
                vulnimage_droplet_id = ya_api.create_vm(
                    IMAGE_VM_NAME, ssh_keys=[ADMIN_PUBLIC_SSH_KEY, DEPLOY_KEY], image_id=VULNIMAGE_YA_IMAGE,
                    root_password_hash=pass_hash, subnet_id=subnet_id, ip=vulnimage_ip,
                    mem_gb=IMAGE_MEM_GB, cores=IMAGE_CORES, ssd_gb=IMAGE_SSD_GB,
                    tag="team-image")
                if vulnimage_droplet_id is None:
                    log_stderr("failed to create vm, exiting")
                    return 1

                for i in range(70, 100):
                    # just spinning for the sake of smooth progress
                    log_progress("%d%%" % i)
                    time.sleep(3)

            image_state = "RUNNING"
            open("db/team%d/image_deploy_state" % TEAM, "w").write(image_state)
    
    log_progress("100%")
    return 0


if __name__ == "__main__":
    sys.stdout = os.fdopen(1, 'w', 1)
    print("started: %d" % time.time())
    exitcode = 1
    try:
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        exitcode = main()

        net_state = open("db/team%d/net_deploy_state" % TEAM).read().strip()
        image_state = open("db/team%d/image_deploy_state" % TEAM).read().strip()

        log_stderr("NET_STATE:", net_state)
        log_stderr("IMAGE_STATE:", image_state)

        if net_state != "READY":
            print("msg: ERR, failed to set up the network")
        elif image_state != "RUNNING":
            print("msg: ERR, failed to start up the vm")
    except:
        traceback.print_exc()
    print("exit_code: %d" % exitcode)
    print("finished: %d" % time.time())
