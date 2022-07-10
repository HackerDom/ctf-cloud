The Cloud-server provides participants the console where they can do various actions with their vulnerable images: create, reboot, checkpoint and so on. The images are run in Digital Ocean. In addition to vulnerable image, for every team the special vm called team router is set up. This router contains the OpenVPN server allowing participants to enter the game network. Also the trafic between vulnerable image and game network flows through this router. Participants don't have SSH access to their router, but can connect or disconnect it from the game network using the cloud console.

Participants authenticate in the console by tokens, so they should be sent to them somehow, for example, using email or telegram bots.

### Pre-requirements ###

To deploy Cloud server you should set up the VPN server first (see ../vpn). The client VPN configs should already be generated for connecting team routers to main VPN server.

The Cloud server can be deployed to some Ubuntu 20.04 box. The server can be a dedicated server or virtual private server on some hosting like Digital Ocean.

The server should have at least 8GB RAM and 4 CPU cores. For big competitions server with 32GB RAM and 8 CPU cores
is recommended.

The server must have SSH up configured to accept the root user by key. The server must have network connectivity to Digital Ocean API.

The account on Digital Ocean should be created and paid. The droplet limit should be not less than 2\*N + 10, where N is a maximum number of teams. For every team the vulnerable vm and the router vm are created.

### Prepare ###

To set up the VPN server you should have it created on some hosting.

The Digital Ocean account must be set up to delegate some zone, like cloud.ructf.org. The A record should point on the Cloud box, other records will be created in this zone during the proccess of team image creation. The domain names are used in VPN configs that console gives to the participants to connect to their team router. The team router, in its turn, connects to the central VPN server using the configs that are were created previously.

To communicate with Digital Ocean API, you need the key, which can be created on Digital Ocean control panel (https://cloud.digitalocean.com/account/api/tokens). This key should be stored secretly and never be commited in git.

After obtaining the token, the command ```echo 'TOKEN = "dop_v1_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"' > cloud_master/files/api_srv/do_token.py``` should be executed with your token.

To communicate with team routers, the SSH key pair is needed. it can be created with the following command: ```ssh-keygen -N "" -f cloud_master/files/api_srv/do_deploy_key```. The public key and the private key will be created, the public key should be added to Digital Ocean using this page: https://cloud.digitalocean.com/account/security.


#### Generate Configs ####

To generate configs, execute: ```./init_cloud.sh <vpn_ip> <vpn_domain>```

For example: ```./init_cloud.sh 188.166.118.28 cloud.ructf.org```

The script patches ip in 'inventory.cfg' file and domain name in 'cloud_master/files/api_srv/cloud_common.py', in gen/gen_conf_client_entergame_prod.py, in cloud_master/files/wsgi/cloudapi.wsgi, in cloud_master/files/apache2/000-default.conf and cloud_master/files/nginx/cloud files.

This can take about 30 minutes.

After that, it generates a directory with init cloud state and copies it in cloud_master/files/api_srv/db_init_state_prod. Every subdirectory in this directory contains cloud state for single team. The states of cloud, VPN configs, root password and its hash, hash of the team token.

This directory should be renamed to "db" after the deploy.

The team tokens are in "gen/tokens_prod" directory. They should be sent to participants before the game.


#### Obtain the SSL Certificates ####

The cloud is accessed by the browser with https protocol, so it need a valid certificates. The easiest way to obtain them is to log in on the cloud host with ssh, make sure that its domain name resolves to its IP address, and execute these commands, replacing cloud.ructf.org with your domain:

```apt update && apt install certbot
certbot -d cloud.ructf.org certonly```

Now copy the contents of file /etc/letsencrypt/archive/<your_domain>/fullchain1.pem from remote host to cloud_master/files/nginx/cert_cloud.pem on your local machine and file /etc/letsencrypt/archive/<your_domain>/privkey1.pem to cloud_master/files/nginx/key_cloud.pem.

Also the file dhparams_cloud.pem should be generated. This can be done with a ```openssl dhparam -out cloud_master/files/nginx/dhparams_cloud.pem 4096``` command. This takes about 10 minutes.

The last thing to do for the webserver is to set up the password for cloud console to protect it from team access before the competition starts:
```htpasswd -c cloud cloud_master/files/apache2/htpasswd```


#### Deploy Cloud Master Role ####

To deploy Cloud master role, run ```ansible-playbook cloud_master.yaml```

This command will set up the remote server.

#### Preparing the Cloud for Game

Before the game, the init state directory should be renamed or copied to db directory on the cloud master host. This was made to prevent db corruption on ansible runs: ```rsync -a /cloud/backend/db_init_state_prod/ /cloud/backend/db```

```

#### Administering the Cloud on the Game ####

Most scripts are in /cloud/backend directory on the cloud master server.

To
