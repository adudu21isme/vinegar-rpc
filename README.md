> [!WARNING]
> This is pending, do not install yet. Once this is complete, this warning will be removed.

# RPC for [Vinegar](https://github.com/vinegarhq/vinegar)
Since the Rich presence of Vinegar does not work for me, i have made this workaround for myself and decided to make it public if anybody else wishes to use it for now.

If Vinegar fully fixes their RPC and has all the statues in this, then this repo will be archived.

## How to install?
1. In KDE Plasma, right click on the menu button in taskbar and then click "Edit Applications" then search for Vinegar
> [!TIP]
> You may also right click on Vinegar in application menu and click "Edit Application":
> <img width="1008" height="419" alt="image" src="https://github.com/user-attachments/assets/556e6945-cbd2-4068-a0cb-8753aa4983bc" />

2. Download [launch_studio.sh](src/launch_studio.sh) and ideally save it to your `~/Documents` folder
3. Open `launch studio.sh` in a program that permits you to edft .sh files like Kate, then replace:
```bash
/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
with the Command-Line arguments that are visible in KDE Menu Editor (click in the textbox, press CTRL+A then press CTRL+C and replace the mentioned code with the Command-Line args)
<img width="1903" height="527" alt="image" src="https://github.com/user-attachments/assets/44d45368-a26b-4b5b-bb66-b1592543faf0" />
4. After replacing the code, set the Command-line args to simply
```
%u
```
And change Program to the location of the `launch_studio.sh` script
<img width="1334" height="429" alt="image" src="https://github.com/user-attachments/assets/929a74ec-1392-42ca-a08b-eae023c4e2cc" />, which you can find via Dolphin:
<img width="864" height="665" alt="image" src="https://github.com/user-attachments/assets/de07aee1-3027-45e0-a65c-1cb669c762a1" />

5. Download [RPC.py](src/RPC.py) and save it to your `~/Documents` folder
> [!NOTE]
> If it is not in your documents folder then you will have to edit this in `launch.studio.sh`:
> ```bash
> "$HOME/Documents/RPC.py"
> ```
> to the proper location of RPC.py. like how we found "Program" KDE menu application field for vinegar.
6. Find Vinegar in the application menu then right click it and click "Settings"
<img width="743" height="98" alt="image" src="https://github.com/user-attachments/assets/9f7daf10-baaf-44c7-ab45-3fcce6cce6aa" />

> [!TIP]
> You may also open the settings via Terminal by typing
> ```
> flatpak run org.vinegarhq.Vinegar manage
> ```

7. Once you are in the settings of vinegar, toggle on "Web Pages"
<img width="451" height="112" alt="image" src="https://github.com/user-attachments/assets/fa806da0-f84f-4925-a04a-ad57bc03dede" />

> [!NOTE]
> This is so if you have issues with the OAuth login method you can use Quick-Sign in/similar for Studio.
8. Close settings and launch studio, it should ideally work if the python script is running successfully!

## How to uninstall once fully installed?
1. Ensure Vinegar is completely closed/all Roblox Studio instances are closed
2. Open your `launch studio.sh` and copy the Command-Line arguments which is after `/usr/bin/flatpak`, for reference in:
```
exec /usr/bin/flatpak run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
you would copy
```
run --branch=stable --arch=x86_64 --command=vinegar --file-forwarding org.vinegarhq.Vinegar @@u "$@" @@
```
3. Open KDE menu editor (which is shown how to do in [How to Install](#how-to-install), find Vinegar and replace its Command-Line args with the correct copied args
4. Replace "Program" with
```
/usr/bin/flatpak
```
5. Delete `launch_studio.sh` and delete `RPC.py`
