# Browser Tool (POS Dual-Screen)

Two small Python apps for multi-monitor POS screens:

1. **Config** (`browser-tool-config`) — add any number of named screens (name, URL, monitor, window mode, open as window or tab, on/off), choose Edge / Chrome / Brave, and whether to open when the computer starts.
2. **Launcher** (`browser-tool`) — opens every enabled screen from config. No settings UI.

They share `config.json` in the install folder (next to the binaries). Saves write an **encrypted** envelope; the decryption key lives in the OS credential store (Windows Credential Manager, or Linux Secret Service such as gnome-keyring / libsecret). If no secret service is available on Linux, the key is stored as a `0600` file at `~/.local/share/POSBrowserLauncher/profiles/config.key`. `config.example.json` stays plaintext for documentation. Plaintext `config.json` from older versions still loads; the next Save from Config upgrades it to encrypted.

Works on **Linux** (Arch, Omarchy/Hyprland, and typical X11/Wayland desktops) and **Windows**. Develop and test on Linux; build `.exe` files on a Windows PC (or GitLab’s Windows runner).

Packaged Config shows **Version** and an **Update** button: it checks Cloudflare R2 (`latest/version.json`) and replaces the binaries in the install folder (keeps `config.json` and `log/`), then restarts Config. No uninstall needed.

## Releases (GitHub → GitLab → R2)

Source stays **private** on GitHub/GitLab. Public downloads and in-app updates use **Cloudflare R2** at `https://download-hengkakada.thecapy.org` (bucket `browser-tool-releases`).

1. Sync + CI setup as before (`GITLAB_TOKEN`, Windows runner tagged `windows`).
2. On GitLab CI/CD variables (masked), set:
   - `R2_ACCOUNT_ID`
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
3. R2 bucket `browser-tool-releases` with custom domain `download-hengkakada.thecapy.org` (public).
4. Publish a version:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
   CI builds Linux + Windows, then uploads to R2:
   - `https://download-hengkakada.thecapy.org/v1.0.0/browser-tool-setup.exe`
   - `https://download-hengkakada.thecapy.org/v1.0.0/browser-tool-linux.tar.gz`
   - `…/v1.0.0/browser-tool-windows.zip` (in-app Update)
   - `…/latest/` copies of the same + `version.json` (Update + evergreen blog links)

Blog: paste the `v1.0.0/…` or `latest/…` R2 URLs. Keep the GitLab project **private** so source is not public.

Manual sync: GitHub → Actions → **Sync to GitLab** → Run workflow.

## Install layout

After setup, both platforms use the same folder shape:

```
browser-tool/
  browser-tool-config(.exe)   # Config UI
  browser-tool(.exe)          # Launcher
  config.json                 # created on first Save
  log/                        # daily YYYYDDMM.log files
```

### Windows

1. Download `browser-tool-setup.exe` from R2 (e.g. `…/latest/browser-tool-setup.exe`) or build with `build_windows.bat`.
2. Double-click setup → pick a drive (e.g. `D:`) → installs to `D:\browser-tool\` with both exes, an empty `log\` folder, and icons on the binaries.
3. Later updates: open Config → **Update** (downloads `browser-tool-windows.zip` from R2).

### Linux

1. Download `browser-tool-linux.tar.gz` from R2 (e.g. `…/latest/browser-tool-linux.tar.gz`) or build with `./build_linux.sh`.
2. Then:

```bash
tar xf browser-tool-linux.tar.gz
cd browser-tool-linux
./install.sh                 # installs to ~/browser-tool
./install.sh /opt/browser-tool   # optional custom path
```

3. Later updates: open Config → **Update**.

## Requirements

- Python 3.12
- Microsoft Edge, Google Chrome, Chromium, or Brave (Arch/Omarchy: `sudo pacman -S chromium`; Brave is usually `brave-bin` from the AUR)
- Linux: Tk (`sudo pacman -S tk` on Arch/Omarchy, `sudo apt install python3-tk` on Debian/Ubuntu)
- Two monitors for the real POS layout (one monitor is enough to test the UI)

On **Omarchy / Hyprland**, the launcher reads monitor layout from `hyprctl` and moves each kiosk window onto the chosen output. Chromium is treated as Chrome.

## Setup (development)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x config.sh open.sh
```

## Run (development)

| Action | Linux | Windows |
|--------|--------|---------|
| Config | `./config.sh` | `config.bat` |
| Open POS | `./open.sh` | `open.bat` |

On Windows, create a venv the same way (`py -3.12 -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`) or rely on `py -3.12` if packages are installed for that interpreter.

## How it behaves

- **Save** writes encrypted `config.json` (key in the OS keyring, or the fallback `config.key` file). Copying only `config.json` to another user/machine will not decrypt. If you chose *When computer starts*, it creates an autostart entry for the launcher; *Manual* removes that entry.
  - Linux (XDG): `~/.config/autostart/browser-tool.desktop`
  - Omarchy / Hyprland: also a managed block in `~/.config/hypr/autostart.lua` (runs at compositor start)
  - Windows: a `.lnk` in the user Startup folder
- **Save & Test Open** saves, then opens every screen that is turned **On**.
- **Screens** in `config.json` are a list of `{ "name", "url", "monitor", "window_mode", "open_as", "enabled" }`. Use **Add screen** in Config to grow the list; each screen needs a unique name. Uncheck **On** to keep a screen saved but skip it when opening (missing `enabled` in older configs is treated as on). List order is the open queue (top opens first); use **↑** / **↓** in Config to change when each screen opens.
- **Delay between screens** (`open_delay_seconds` in config) waits that many seconds after each screen before opening the next (default `0.4`). Set to `0` for no extra wait.
- **Window** is per screen (dropdown in Config). *Fullscreen* is kiosk (no title bar). *Maximized* fills the screen but keeps close and minimize. New screens default to fullscreen. Ignored when **Open as** is *tab* (the parent window already has its mode).
- **Open as** is per screen: *window* (default) opens a new browser window on the chosen monitor — you can put several windows on the same monitor. *tab* opens the URL as a new tab in the latest prior *window* on that same monitor (by list order). A *tab* row needs an **On** *window* on the same monitor above it; otherwise Save / launch reports an error. Missing `open_as` in older configs is treated as *window*.
- All screens share one browser profile (`…/POSBrowserLauncher/profiles/shared` on Linux under `~/.local/share`, or under `%LOCALAPPDATA%` on Windows) so login and localStorage for the same site are available on every window. Older per-screen profile folders are migrated into `shared` on first launch.
- **Logs** (startup, launch by screen name, save/decrypt failures) go to one file per day named `YYYYDDMM.log` (year, day, month — e.g. `20262210.log` for 2026-10-22) under `log/` next to the binaries (install folder or project root in development). Secrets (decryption keys, ciphertext) and URLs/monitor details are not written. Error dialogs point at today’s log when something fails at login.
- **Update** (Config, packaged installs only) reads `https://download-hengkakada.thecapy.org/latest/version.json`, downloads the platform archive from R2, replaces only the binaries (and Linux `icon.png` if present), and restarts Config. `config.json`, `log/`, and browser profiles are left alone.

If `config.json` is missing, the launcher asks you to run Config first.

## Packaged apps

PyInstaller is not a cross-compiler. Build Linux binaries on Linux and Windows `.exe` files on Windows.

**Linux**

```bash
./build_linux.sh
```

Outputs `dist/browser-tool-config`, `dist/browser-tool`, and the ship archive `dist/browser-tool-linux.tar.gz` (binaries + `install.sh` + icon).

**Windows**

```bat
build_windows.bat
```

Outputs `dist\browser-tool-setup.exe` (first install) and `dist\browser-tool-windows.zip` (in-app update). Intermediate `browser-tool-config.exe` and `browser-tool.exe` are built and embedded into setup.
