#!/bin/bash

# RPC.py optional flags (add after the path which is before the trailing &):
#   --internal       Make it appear as you are using Internal Studio instead for the RPC, i dont suggest larping this unless you actually are running Internal Studio.
#   --hide-placeid   If PlaceName cannot be gotten, then instead of falling back to showing the PlaceID it will display "Private Place" instead.
# Example enabling both: python "$HOME/Documents/RPC.py" --internal --hide-placeid &
python "$HOME/Documents/RPC.py" &

exec /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
