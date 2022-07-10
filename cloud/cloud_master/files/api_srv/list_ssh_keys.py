import do_api

keys = sorted(do_api.get_ssh_keys().items())

for key_id, key_name in keys:
    print(key_id, key_name)
