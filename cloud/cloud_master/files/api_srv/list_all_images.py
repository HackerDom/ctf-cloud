#!/usr/bin/python3
# Developed by Alexander Bersenev from Hackerdom team, bay@hackerdom.ru

"""Lists all vm images"""

import ya_api

def main():
    images = ya_api.list_images()

    if not images:
        return 0

    if "created_at" in images[0]:
        images.sort(key=lambda v: v.get("created_at", 0))
    if "createdAt" in images[0]:
        images.sort(key=lambda v: v.get("createdAt", 0))

    for image in images:
        print(image["id"], image["name"])

    return 0

    
if __name__ == "__main__":
    main()
