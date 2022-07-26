# Developed by Alexander Bersenev from Hackerdom team, bay@hackerdom.ru

"""Common functions that make requests to digital ocean api"""

import requests
import time
import json
import sys
import os

import jwt
import yaml

from ya_token import SERVICE_ACCOUNT_ID, KEY_ID, PRIVATE_KEY, FOLDER_ID, ZONE_ID


VERBOSE = True



def log(*params):
    if VERBOSE:
        print(*params, file=sys.stderr)


def refresh_iam_token():
    now = int(time.time())
    payload = {
        "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
        "iss": SERVICE_ACCOUNT_ID,
        "iat": now - 600,
        "exp": now + 3000
    }

    encoded_token = jwt.encode(payload, PRIVATE_KEY[:], algorithm='PS256', headers={'kid': KEY_ID})

    resp = requests.post("https://iam.api.cloud.yandex.net/iam/v1/tokens", json={"jwt": encoded_token})

    if resp.status_code != 200:
        log("failed to get iamToken", resp.text)
        return None

    token = resp.json()["iamToken"]
    with open(os.open("ya_token.txt", os.O_CREAT | os.O_WRONLY, 0o600), "w") as f:
        f.write(token)


def get_iam_token():
    try:
        token = open("ya_token.txt", "r").read().strip()
    except OSError as E:
        log("faled to reuse the old token, getting new", E)
        refresh_iam_token()
        token = open("ya_token.txt", "r").read().strip()

    return token



def call_api(method, url, json={}, ret_field=None, folder_id=FOLDER_ID, page_size=None, attempts=5, timeout=10):
    for attempt in range(1, attempts+1):
        try:
            token = get_iam_token()
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer %s" % token,
            }

            resp = requests.request(method, url, headers=headers, json=json,
                params={"folder_id": folder_id, "page_size": page_size})

            print(resp.status_code, resp.text)

            if resp.status_code == 404:
                log("call api %s %s returned 404: %s %s" % (method, url, resp.reason, repr(resp.text)))
                time.sleep(timeout)
                continue

            if resp.status_code == 401:
                refresh_iam_token()
                if attempt > 1:
                    time.sleep(timeout)
                continue

            if resp.status_code != 200:
                log("bad ans code", resp.status_code, resp.text)
                time.sleep(timeout)
                continue

            ans = resp.json()
            if "nextPageToken" in ans:
                log("call_api %s %s: too many values warning, paging is no supported" % (method, url))
            if ret_field:
                if ret_field not in ans:
                    return []
                ans = ans[ret_field]
            return ans

        except Exception as e:
            log("call_api %s %s trying again %s" % (method, url, e,))
            time.sleep(timeout)

    return None



def get_all_vms(attempts=5, timeout=10):
    vms = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/instances", ret_field="instances",
                   page_size=1000, attempts=attempts, timeout=timeout)
    return vms



def get_ids_by_vmname(vm_name):
    ids = set()

    droplets = get_all_vms()
    if droplets is None:
        return None

    for droplet in droplets:
        if droplet["name"] == vm_name:
            ids.add(droplet['id'])
    return ids


def check_vm_exists(vm_name):
    droplets = get_all_vms()
    if droplets is None:
        return None

    for droplet in droplets:
        if droplet["name"] == vm_name:
            return True
    return False


def create_vm(vm_name, ssh_keys, vpc_uuid=None,
              mem_gb=2, cores=2, image_id=None,
              snapshot_id=None, tag="vm",
              user_data="#!/bin/bash\n\n", attempts=10, timeout=20):

    if not image_id and not snapshot_id:
        log("create_vm, image_id or snapshot_id is needed")
        return None


    cloud_config = {
        "users": [
            {
                "name": "root",
                "ssh_authorized_keys": ssh_keys
            }
        ],

        "disable_root": False,
    }

    config = "#cloud-config\n" + yaml.dump(cloud_config)

    data = {
        "name": vm_name,
        "hostname": vm_name,
        "zoneId": ZONE_ID,
        "platformId": "standard-v3",
        "resourcesSpec": {
            "memory": mem_gb*1024*1024*1024,
            "cores": cores,
            "coreFraction": 100,
        },
        "metadataOptions": {
            "gceHttpEndpoint": "ENABLED",
            "awsV1HttpEndpoint": "ENABLED",
        },
        "bootDiskSpec": {
            "mode": "READ_WRITE",
            "autoDelete": True,
            "diskSpec": {
                "name": "delmedisk",
                "description": "desc",
                "typeId": "network-ssd",
                "size": 15*1024*1024*1024,
                "imageId": image_id,
                "snapshot_id": snapshot_id
            },
        },
        "networkInterfaceSpecs": {
            "subnetId": "e9btb1ae8ap9mgosijis",
            "primaryV4AddressSpec": {
                "oneToOneNatSpec": {
                    "ipVersion": "IPV4"
                }
            }
        },
        "metadata": {
            "user-data": config
        },
    }
    vm = call_api("POST", "https://compute.api.cloud.yandex.net/compute/v1/instances", data, ret_field="metadata", attempts=attempts, timeout=timeout)

    return vm["instanceId"]


def delete_vm_by_id(droplet_id, attempts=10, timeout=20):
    vm = call_api("DELETE", "https://compute.api.cloud.yandex.net/compute/v1/instances/"+droplet_id, ret_field=None, folder_id=None, attempts=attempts, timeout=timeout)

    return bool(vm)


def get_ip_by_id(droplet_id, attempts=5, timeout=20):
    interfaces = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/instances/"+droplet_id,
        ret_field="networkInterfaces", folder_id=None, attempts=attempts, timeout=timeout)

    for interface in interfaces:
        ip = interface.get("primaryV4Address", {}).get("oneToOneNat", {}).get("address")
        if ip:
            return ip

    return None


def get_ip_by_vmname(vm_name):
    ids = set()

    droplets = get_all_vms()
    if droplets is None:
        return None

    for droplet in droplets:
        if droplet["name"] == vm_name:
            ids.add(droplet['id'])

    if len(ids) > 1:
        log("warning: there are more than one droplet with name " + vm_name +
            ", using random :)")

    if not ids:
        return None

    return get_ip_by_id(list(ids)[0])


def reboot_vm_by_id(droplet_id, attempts=5, timeout=20):
    reboot_op = call_api("POST", "https://compute.api.cloud.yandex.net/compute/v1/instances/"+droplet_id+":restart",
        ret_field=None, folder_id=None, attempts=attempts, timeout=timeout)

    return bool(reboot_op)


def reboot_vm_by_vmname(vm_name):
    ids = set()

    droplets = get_all_vms()
    if droplets is None:
        return None

    for droplet in droplets:
        if droplet["name"] == vm_name:
            ids.add(droplet['id'])

    if len(ids) > 1:
        log("warning: there are more than one droplet with name " + vm_name +
            ", using random :)")

    if not ids:
        return None

    return reboot_vm_by_id(list(ids)[0])


def take_vm_snapshot(droplet_id, snapshot_name, attempts=5, timeout=20):
    disk = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/instances/"+droplet_id,
        ret_field="bootDisk", folder_id=None, attempts=attempts, timeout=timeout)

    if not disk:
        return False

    disk_id = disk["diskId"]


    snapshot = call_api("POST", "https://compute.api.cloud.yandex.net/compute/v1/snapshots",
        {"diskId": disk_id, "name": snapshot_name, "description": "desc"},
        ret_field=None, folder_id=FOLDER_ID, attempts=attempts, timeout=timeout)

    return bool(snapshot)



def restore_vm_from_snapshot_by_id(droplet_id, snapshot_id, attempts=5, timeout=20):
    vm = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/instances/"+droplet_id,
        {"view": "FULL"}, ret_field=None, folder_id=None, attempts=attempts, timeout=timeout)

    if not vm:
        log("restore_vm_from_snapshot_by_id faled, failed to get vm")
        return False

    snapshot = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/snapshots/"+snapshot_id,
        ret_field=None, folder_id=None, attempts=attempts, timeout=timeout)

    if not snapshot:
        log("restore_vm_from_snapshot_by_id faled, failed to get snapshot")
        return False

    vm_name = vm["name"]
    zone_id = vm["zoneId"]
    mem_gb = int(vm["resources"]["memory"]) // 1024 // 1024 // 1024
    cores = vm["resources"]["cores"]
    disk_id = vm["bootDisk"]["diskId"]

    if not disk_id:
        log("restore_vm_from_snapshot_by_id failed, no disk_id")
        return False

    disk = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/disks/"+disk_id,
        {"view": "FULL"}, ret_field=None, folder_id=None, attempts=attempts, timeout=timeout)

    disk_type = disk["typeId"]
    disk_size = int(disk["size"])

    ok = delete_vm_by_id(droplet_id)
    if not ok:
        log("restore_vm_from_snapshot_by_id, delete vm by id failed")
        return False

    # save one api call by sleeping 15 seconds
    time.sleep(15)

    new_vm = create_vm(vm_name, ssh_keys=None, mem_gb=mem_gb, cores=cores, image_id=None, snapshot_id=snapshot_id)

    return True


def list_snapshots(attempts=4, timeout=5):
    vms = call_api("GET", "https://compute.api.cloud.yandex.net/compute/v1/snapshots", ret_field="snapshots",
                   page_size=1000, attempts=attempts, timeout=timeout)
    return vms


def delete_snapshot(snapshot_id, attempts=10, timeout=20):
    operation = call_api("DELETE", "https://compute.api.cloud.yandex.net/compute/v1/snapshots/"+snapshot_id, ret_field=None, folder_id=None, attempts=attempts, timeout=timeout)

    return bool(operation)


def get_all_vpcs(attempts=5, timeout=20):
    vpcs = call_api("GET", "https://vpc.api.cloud.yandex.net/vpc/v1/networks", ret_field="networks",
                   page_size=1000, attempts=attempts, timeout=timeout)
    return vpcs



def get_vpc_by_name(name, print_warning_on_fail=False):
    vpcs = get_all_vpcs()
    if vpcs is None:
        return None

    for vpc in vpcs:
        if vpc["name"] == name:
            return vpc['id']

    if print_warning_on_fail:
        log("failed to get vpc ids by name", name)

    return None


def create_vpc(name, ip_range, attempts=5, timeout=20):
    vpc_id = get_vpc_by_name(name)

    if not vpc_id:
        data = {
            "folderId": FOLDER_ID,
            "name": name
        }
        vpc = call_api("POST", "https://vpc.api.cloud.yandex.net/vpc/v1/networks", data, ret_field=None, attempts=attempts, timeout=timeout)
        if not vpc:
            log("create_vpc failed")
            return None

        vpc_id = vpc["metadata"]["networkId"]

    if not vpc_id:
        return None

    subnets = call_api("GET", "https://vpc.api.cloud.yandex.net/vpc/v1/subnets", ret_field="subnets", attempts=attempts, timeout=timeout)

    for subnet in subnets:
        if ip_range in subnet.get("v4CidrBlocks", []):
            # already created
            if subnet.get("networkId") == vpc_id:
                return True
            log("create_vpc: the network addr is already attached to network", subnet.get("networkId"))
            return False


    subnet_data = {
        "folderId": FOLDER_ID,
        "name": name + "-subnet",
        "networkId": vpc_id,
        "zoneId": ZONE_ID,
        "v4CidrBlocks": [
            ip_range
        ]
    }

    subnet = call_api("POST", "https://vpc.api.cloud.yandex.net/vpc/v1/subnets", subnet_data, ret_field=None, attempts=attempts, timeout=timeout)

    return bool(subnet)


def get_domain_zone_id(domain, attempts=5, timeout=10):
    zones = call_api("GET", "https://dns.api.cloud.yandex.net/dns/v1/zones", ret_field="dnsZones",
                   page_size=1000, attempts=attempts, timeout=timeout)

    if not domain.endswith("."):
        domain += "."

    zone_id = None

    for zone in zones:
        if zone["zone"] == domain:
            zone_id = zone["id"]
            break

    if zone_id is None:
        log("get_domain_zone_id zone not found", domain)
        return None

    return zone_id

def get_all_domain_records(domain, zone_id=None, attempts=5, timeout=20):
    if not domain.endswith("."):
        domain += "."

    if not zone_id:
        zone_id = get_domain_zone_id(domain)

    if not zone_id:
        return []

    records = call_api("GET", "https://dns.api.cloud.yandex.net/dns/v1/zones/"+zone_id+":listRecordSets",
        {"filter": 'type = "A"'} , ret_field="recordSets", folder_id=None, page_size=1000, attempts=attempts, timeout=timeout)

    return records



def get_domain_ids_by_hostname(host_name, domain, print_warning_on_fail=False):
    ids = set()

    records = get_all_domain_records(domain)
    if records is None:
        return None

    for record in records:
        if record["type"] == "A" and record["name"] == host_name + "." + domain:
            ids.add(record['name'])

    if not ids:
        if print_warning_on_fail:
            log("failed to get domain ids by hostname", host_name)

    return ids



def create_domain_record(name, ip, domain, attempts=10, timeout=20):
    if not domain.endswith("."):
        domain += "."

    zone_id = get_domain_zone_id(domain)

    if not zone_id:
        log("create_domain_record failed, no such domain")
        return False

    records = call_api("POST", "https://dns.api.cloud.yandex.net/dns/v1/zones/"+zone_id+":updateRecordSets",
        json={
            "additions": [{
                "name": name,
                "type": "A",
                "ttl": 10,
                "data": [ip]
            }]
        }, ret_field=None, folder_id=None, page_size=None, attempts=attempts, timeout=timeout)

    return bool(records)



def delete_domain_record(name, domain, attempts=10, timeout=20):
    if not domain.endswith("."):
        domain += "."

    zone_id = get_domain_zone_id(domain)

    if not zone_id:
        log("delete_domain_record failed, no such domain")
        return False

    records = get_all_domain_records(domain, zone_id)

    records_to_delete = []
    for record in records:
        if record["name"] == name + "." + domain:
            records_to_delete.append(record)

    if len(records_to_delete) > 1:
        log("delete_domain_record, more 1 records to delete:", len(records_to_delete))

    if not(records_to_delete):
        return True

    records = call_api("POST", "https://dns.api.cloud.yandex.net/dns/v1/zones/"+zone_id+":updateRecordSets",
        json={
            "deletions": records_to_delete
        }, ret_field=None, folder_id=None, page_size=None, attempts=attempts, timeout=timeout)

    return bool(records)
