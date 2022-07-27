1. Install packer 1.7.0 or higher: https://learn.hashicorp.com/tutorials/packer/get-started-install-cli#
2. Get the OAuth for Yandex Cloud: https://cloud.yandex.ru/docs/iam/concepts/authorization/oauth-token
3. Run `packer build -var "api_token=<YOUR_API_TOKEN>" image.pkr.hcl`
