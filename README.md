# RPC for [Vinegar](https://github.com/vinegarhq/vinegar)
Since Vinegars rich presence does not currently work for me (i use Vesktop), i created this workaround and decided to publish it in case it helps others.

If Vinegar fixes its rich presence feature and supports all of the statuses provided by this repository then this repo will be archived.

## How to install?
> [!NOTE]
> This assumes you have Python 3+ installed
1. In KDE Plasma, right-click the application menu button on the taskbar, select **Edit Applications**, then search for **Vinegar**.
> [!TIP]
> You can also right-click **Vinegar** in the application menu and select **Edit Application**.
> <img width="1008" height="419" alt="image" src="https://github.com/user-attachments/assets/556e6945-cbd2-4068-a0cb-8753aa4983bc" />

> [!WARNING]
> You must install the required packages, otherwise the script will not work.
>
> Run this command in your terminal to install them:
> ```bash
> pip install psutil pypresence
> ```

2. Download [launch_studio.sh](src/launch_studio.sh) and save it somewhere convenient (this guide assumes `~/Documents`).
3. Open `launch_studio.sh` in a text editor such as Kate, then replace the following line:
```bash
run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
with with the contents of the **Command-line arguments** field in **KDE Menu Editor**. Click inside the field, press Ctrl+A, then Ctrl+C, and paste the copied text over the command above.
<img width="1330" height="419" alt="image" src="https://github.com/user-attachments/assets/06e21b29-0155-4e89-8033-dbee5354d52c" />
4. After editing `launch_studio.sh`, set **Command-line arguments** to:
```
%u
```
and set **Program** to the location of `launch_studio.sh`.
<img width="1334" height="429" alt="image" src="https://github.com/user-attachments/assets/929a74ec-1392-42ca-a08b-eae023c4e2cc" />, which you can find via Dolphin:
<img width="864" height="665" alt="image" src="https://github.com/user-attachments/assets/de07aee1-3027-45e0-a65c-1cb669c762a1" />

5. Download [RPC.py](src/RPC.py) and, ideally, save it in the same directory as `launch_studio.sh`.
> [!NOTE]
> If you saved `RPC.py` somewhere else, edit this line in `launch_studio.sh`:
> ```bash
> "$HOME/Documents/RPC.py"
> ```
> with the full path to `RPC.py`, similar to how you found the **Program** path for `launch_studio.sh`.
6. Find **Vinegar** in the application menu, right-click it, and select **Settings**.
<img width="743" height="98" alt="image" src="https://github.com/user-attachments/assets/9f7daf10-baaf-44c7-ab45-3fcce6cce6aa" />

> [!TIP]
> You can also open the settings from a terminal by running:
> ```
> flatpak run org.vinegarhq.Vinegar manage
> ```

7. In the Vinegar settings, enable **Web Pages**.
<img width="451" height="112" alt="image" src="https://github.com/user-attachments/assets/fa806da0-f84f-4925-a04a-ad57bc03dede" />

> [!NOTE]
> This allows you to use Quick Sign-In (or another browser-based login method) if OAuth login does not work in Studio.
8. Close the settings and launch Studio. RPC should now ideally work if the Python script is running successfully!

## How to uninstall once installed?
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
5. Delete `launch_studio.sh` and `RPC.py`
