#!/usr/bin/python3
# Developed by Alexander Bersenev from Hackerdom team, bay@hackerdom.ru

"""Lists all vm snapshots"""

import do_api

def main():
    snapshots = do_api.list_snapshots()
    snapshots.sort(key=lambda v: v.get("created_at", 0))

    for snapshot in snapshots:
        print(snapshot["id"], snapshot["name"])

    return 0

    
if __name__ == "__main__":
    main()
