#!/bin/bash

/usr/bin/python3 /home/main/Documents/RPC.py &

exec /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
