variable "api_token" {
  type = string
}

source "yandex" "vuln_image" {
  folder_id = "b1g3omd7tqchq59cd8np"
  zone        = "ru-central1-a"
  token     = var.api_token
  image_family = "ctf-images"
  image_name = "ctf-image-test-{{timestamp}}"
  source_image_family = "ubuntu-2004-lts"
  ssh_username  = "root"
  use_ipv4_nat = true
  instance_cores = 2
  instance_mem_gb = 2
  platform_id = "standard-v3"
  disk_type = "network-ssd"
  metadata = {
    user-data = "#cloud-config\ndisable_root: false\n"
  }
}

build {
  sources = ["source.yandex.vuln_image"]

  provisioner "shell" {
    inline_shebang = "/bin/sh -ex"
    environment_vars = [
      "DEBIAN_FRONTEND=noninteractive",
    ]
    inline = [
      # Wait apt-get lock
      "while ps -opid= -C apt-get > /dev/null; do sleep 1; done",
      "apt-get clean",
      # apt-get update sometime may fail
      "for i in `seq 1 3`; do apt-get update && break; sleep 10; done",

      # Wait apt-get lock
      "while ps -opid= -C apt-get > /dev/null; do sleep 1; done",

      "apt-get dist-upgrade -y -o Dpkg::Options::='--force-confdef' -o Dpkg::Options::='--force-confold'",
      "for i in `seq 1 3`; do apt-get update && break; sleep 10; done",
      "apt-get upgrade -y -q -o Dpkg::Options::='--force-confdef' -o Dpkg::Options::='--force-confold'",

      # Install docker and docker-compose
      "apt-get install -y -q apt-transport-https ca-certificates nfs-common",
      "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -",
      "add-apt-repository \"deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable\"",
      "for i in `seq 1 3`; do apt-get update && break; sleep 10; done",
      "apt-get install -y -q docker-ce",
      "curl -L \"https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)\" -o /usr/local/bin/docker-compose",
      "chmod +x /usr/local/bin/docker-compose",
      
      # Install haveged, otherwise docker-compose may hang: https://stackoverflow.com/a/68172225/1494610
      "apt-get install -y -q haveged",

      # Add users for services
      "useradd -m -s /bin/bash ambulance",
    ]
  }

  ## Onboot docker-compose run service
  provisioner "file" {
    source = "service-boot/ctf-service@.service"
    destination = "/etc/systemd/system/ctf-service@.service"
  }

  # Copy services
  provisioner "file" {
    source = "services/ambulance/"
    destination = "/home/ambulance/"
  }

  # Build and run services for the first time
  provisioner "shell" {
    inline = [
      "cd ~ambulance",
      "docker-compose build",

      "systemctl daemon-reload",
      "systemctl enable ctf-service@ambulance",
    ]
  }

  # Fix some internal digitalocean+cloud-init scripts to be compatible with our cloud infrastructure
  provisioner "shell" {
    script = "yandex_cloud_specific_setup.sh"
  }
}
