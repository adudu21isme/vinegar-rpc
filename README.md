> [!WARNING]
> This is pending, do not install yet. Once this is complete, this warning will be removed.

# RPC for [Vinegar](https://github.com/vinegarhq/vinegar)
Since the Rich presence of Vinegar does not work for me, i have made this workaround for myself and decided to make it public if anybody else wishes to use it for now.

If Vinegar fully fixes their RPC and has all the statues in this, then this repo will be archived.

## How to install?
1. In KDE Plasma, right click on the menu button in taskbar and click "Edit Applications" then search for Vinegar, or you may right click on Vinegar in application menu and click "Edit Application":
<img width="1008" height="419" alt="image" src="https://github.com/user-attachments/assets/556e6945-cbd2-4068-a0cb-8753aa4983bc" />

2. Download [launch_studio.sh](https://github.com/adudu21isme/vinegar-rpc-for-kde-plasma/blob/main/src/launch_studio.sh)
3. Open launch studio.sh in a program that permits you to edft .sh files like Kate, then replace:
```bash
/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
with the Command-Line arguments that are visible in KDE Menu Editor (click in the textbox, press CTRL+A then press CTRL+C and replace the mentioned code)
<img width="1903" height="527" alt="image" src="https://github.com/user-attachments/assets/44d45368-a26b-4b5b-bb66-b1592543faf0" />
4. After replacing the code, set the Command-line args to simply
```
%u
```
And change Program to the location of the launch_studio.sh script
<img width="1334" height="429" alt="image" src="https://github.com/user-attachments/assets/929a74ec-1392-42ca-a08b-eae023c4e2cc" />, which you can find via Dolphin:
<img width="864" height="665" alt="image" src="https://github.com/user-attachments/assets/de07aee1-3027-45e0-a65c-1cb669c762a1" />

## How to uninstall once fully installed?
