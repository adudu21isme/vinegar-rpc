> [!CAUTION]
> Don't install this yet; it is being fixed.

# RPC for [Vinegar](https://github.com/vinegarhq/vinegar)
Since Vinegars rich presence does not currently work for me (i use [Vesktop](https://vesktop.dev/)), this workaround has been created and decided to publish it in case it helps others.

If Vinegar fixes its rich presence feature and supports all of the statuses provided by this repository then this repo will be archived.

### States supported:
- Not in a place (aka studio home screen)
- Opening a place
- In workspace of a place
- Returning to workspace after finished playtesting/similar
- Editing a script
- Playtesting
- Running place
- Team testing
- Server & Clients playtest

Example video of this script (click to watch):

[![Video showcase](https://img.youtube.com/vi/cdGw7Uqi9r0/hqdefault.jpg)](https://www.youtube.com/watch?v=cdGw7Uqi9r0)

## How to install?
> [!NOTE]
> This assumes you have Python 3+ installed and are using KDE Plasma and that vinegar is intalled via Flatpak
1. In KDE Plasma, right-click the application menu button on the taskbar, select **Edit Applications**, then search for **Vinegar**.
> [!TIP]
> You can also right-click **Vinegar** in the application menu and select **Edit Application**.
> <img width="1008" height="419" alt="image" src="https://github.com/user-attachments/assets/556e6945-cbd2-4068-a0cb-8753aa4983bc" />

> [!WARNING]
> You must install the [required packages](requirements.txt), otherwise the script will not work.
>
> On ArchLinux-based systems, you can attempt running:
> ```
> sudo pacman -S python-pypresence python-psutil
> ```
> which works for me (i use [CachyOS](https://cachyos.org/))

2. Download [launch_studio.sh](src/launch_studio.sh) and save it somewhere convenient (this guide assumes `~/Documents`).
3. Open `launch_studio.sh` in a text editor such as Kate, then replace the following line:
```bash
run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
with the contents of the **Command-line arguments** field in **KDE Menu Editor**. Click inside the field, press Ctrl+A, then Ctrl+C, and paste the copied text over the command above.
<img width="1330" height="419" alt="image" src="https://github.com/user-attachments/assets/06e21b29-0155-4e89-8033-dbee5354d52c" />

> [!WARNING]
> **Check the end of the line you just pasted.** It must finish with `@@u "$@" @@`
>
> - If it says `%u` instead of `"$@"`, change it to `"$@"`.
> - Keep the double quotes (`"`). Single quotes (`'`) won't work.
>
> ```bash
> # ❌ Wrong
> ... org.vinegarhq.Vinegar @@u %u @@
> ... org.vinegarhq.Vinegar @@u '$@' @@
>
> # ✅ Right
> ... org.vinegarhq.Vinegar @@u "$@" @@
> ```
>
> **Why:** this part passes the ROBLOX link to Studio. If it's wrong, Studio will have problems, such as not being able to login via Browser Login.

4. After editing `launch_studio.sh`, set **Command-line arguments** to:
```
%u
```
and set **Program** to the location of `launch_studio.sh`.
<img width="1334" height="429" alt="image" src="https://github.com/user-attachments/assets/929a74ec-1392-42ca-a08b-eae023c4e2cc" />, which you can find via Dolphin:
<img width="864" height="665" alt="image" src="https://github.com/user-attachments/assets/de07aee1-3027-45e0-a65c-1cb669c762a1" />

5. Download [RPC.py](src/RPC.py) and, ideally, save it in the same directory as `launch_studio.sh`. Afterwards, should be ready.
> [!WARNING]
> If you saved `RPC.py` somewhere else, edit this line in `launch_studio.sh`:
> ```bash
> "$HOME/Documents/RPC.py"
> ```
> with the full path to `RPC.py`, similar to how you found the **Program** path for `launch_studio.sh`.

> [!NOTE]
> This script supports optional flags/args:
> - `--hide-placeid` replaces the fallback when it cannot get the name of a Place, so instead of falling back to the PlaceID, it will display "Private Place".
> - `--internal` makes the RPC title Roblox Studio [Internal], i don't suggest using this arg if you are not actually using internal studio, yes im aware it does not have the channel prefix.
> - `--no-update-check` turns off the update check (see [Updating](#updating)).
>
> Example on how to add flag(s) you want after the path in `launch_studio.sh`:
> ```bash
> python "$HOME/Documents/RPC.py" --hide-placeid &
> ```
> Flags can be combined:
> ```bash
> python "$HOME/Documents/RPC.py" --hide-placeid --internal --no-update-check &
> ```

## Updating
When you start Studio, the script checks GitHub for a newer release. If there is one, a desktop notification shows up, clicking it brings you here.

> [!NOTE]
> The popup needs `notify-send` (`libnotify` package), without it nothing is shown and the script only logs it. You can turn the check off with `--no-update-check`.

1. Ensure all Roblox Studio instances are completely closed (this also stops the old script).
2. Download the new [RPC.py](src/RPC.py) and replace your old one, same location (`~/Documents/RPC.py` if you followed this guide).
3. Check the [latest release notes](https://github.com/adudu21isme/vinegar-rpc/releases/latest). If it says `launch_studio.sh` changed too, copy the changes into your file by hand instead of replacing it, since yours has your own Vinegar command and flags in it.
4. Launch Studio as usual.

> [!TIP]
> Not sure which version you have? Run this (change the path if you saved `RPC.py` elsewhere):
> ```bash
> grep '^VERSION' "$HOME/Documents/RPC.py"
> ```

## How to uninstall once installed?
> [!NOTE]
> This assumes you are using KDE Plasma
1. Ensure Vinegar and all Roblox Studio instances are completely closed.
2. Open `launch_studio.sh` and copy everything after `/usr/bin/flatpak`. For example in:
```
exec /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
you would copy
```
run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
3. Open KDE Menu Editor (see [How to install](#how-to-install)), locate **Vinegar**, and restore the original command-line arguments.
4. Set **Program** to:
```
/usr/bin/flatpak
```
> [!WARNING]
> Once you have modified the above, if using KDE Plasma, you may need to Log Out of the current active session and then Relogin for it to apply immediately.
5. Delete `launch_studio.sh` and `RPC.py`
