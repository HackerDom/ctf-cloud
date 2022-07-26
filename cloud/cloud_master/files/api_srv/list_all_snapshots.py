#!/usr/bin/python3
# Developed by Alexander Bersenev from Hackerdom team, bay@hackerdom.ru

"""Lists all vm snapshots"""

import ya_api

def main():
    snapshots = ya_api.list_snapshots()

    if not snapshots:
        return 0

    if "created_at" in snapshots[0]:
        snapshots.sort(key=lambda v: v.get("created_at", 0))
    if "createdAt" in snapshots[0]:
        snapshots.sort(key=lambda v: v.get("createdAt", 0))

    for snapshot in snapshots:
        print(snapshot["id"], snapshot["name"])

    return 0

    
if __name__ == "__main__":
    main()
