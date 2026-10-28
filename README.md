# Apple Pickup Monitor

A small, English-language Python script that checks whether selected iPhone variants are available for pickup at selected Apple Stores and sends notifications to **your own ntfy topic**. Originally written for iPhone Duo, it can discover other iPhone families from the selected regional Apple shop.

**Python 3.10 or later. No pip packages, Apple account, Apple credentials or administrator privileges are required to run it.**

## What it does

- An interactive setup asks for your regional Apple shop and nearby postal code/location.
- Choose one or more iPhone families, then exact storage/color/model variants.
- Choose stores from the nearby stores returned by Apple, including stores currently without stock.
- Set the interval between checks (15 minutes by default; minimum 2).
- Enter the name of the topic you already use in the ntfy app, or use terminal-only output.
- Remember delivered alerts across restarts and retry failed notifications when stock is confirmed again.
- Slow down after incomplete checks and stop the current round if Apple returns HTTP 403, 429 or 541.

This is an unofficial availability checker. It does not reserve or buy anything. Open the Apple link and confirm availability yourself; stock can change before you arrive or complete checkout.

## Regional support and limitations

There is no hard-coded country, store, regional SKU suffix, time zone or list of current iPhone models. Shop codes include `us`, `uk`, `it`, `ca`, `au`, `de`, `fr`, `jp`, `hk-zh` and `cn`. Use Apple's shop code, which is not always an ISO country code (`uk`, for example). China maps to `www.apple.com.cn`. You can instead paste an HTTPS regional shop root, such as `https://www.apple.com/ca/shop/`.

**This does not guarantee support in every country.** The selected Apple shop must sell the product online and expose compatible pickup responses for its own retail stores. Resellers and regions without that service are not supported. SKU catalogs and pickup endpoints are undocumented and may change or be blocked. Product names, store names and pickup quotes can remain in the regional shop's language even though the program and instructions are English.

The setup lists only nearby stores returned by Apple, not every store within a configurable geographic radius. Try another postal code if a store is missing. A configuration covers one regional shop. To monitor multiple countries, create separate configurations with separate state files. Part numbers are regional: do not copy a US SKU into an Italian configuration.

Current variant discovery reads structured iPhone records embedded in Apple's purchase pages and excludes accessory records. If that data is absent, setup asks for exact regional part numbers and display names. It does not promise to discover every carrier-specific or dynamically loaded option. Select only purchase options applicable to you; pickup lookup uses Apple's `UNLOCKED/WW` purchase context.

## Quick start

1. Install Python 3.10 or later using the platform instructions below.
2. Download this repository as a ZIP and extract it, or clone your published repository.
3. Open a terminal in the extracted repository directory.
4. Run:

```sh
python3 check_iphone_duo.py --setup
python3 check_iphone_duo.py
```

On Windows, replace `python3` with `py -3`.

During setup:

1. Enter your regional shop code or shop URL.
2. Enter a nearby postal code or location accepted by that shop.
3. Select iPhone families by number. Use `1,3`, `1-3` or `all`.
4. Select the exact storage and color variants for each family.
5. Select nearby stores by number.
6. Set your check interval.
7. Enable ntfy and enter the server used by your app (`https://ntfy.sh` by default).
8. Enter **only the exact name of the topic you have already added in the ntfy app**, not its URL. Setup requires a name and never generates one.

Running without an existing configuration starts the same setup in an interactive terminal, saves the file, and exits. Run again to monitor. `--setup` replaces the selected configuration; preserve a copy first if you want to keep it. It sends no startup or test notifications. A notification is sent when selected stock is confirmed.

## ntfy: notifications on your phone

[ntfy](https://ntfy.sh/) accepts HTTP messages and delivers them to subscribed devices. You do not need to run an ntfy server yourself.

1. Install the ntfy app for [iOS or Android](https://docs.ntfy.sh/subscribe/phone/), or use its [web app](https://ntfy.sh/app).
2. In the app, add your personal topic/subscription first, or use one you have already added. Allow notifications in the operating system.
3. During monitor setup, accept `https://ntfy.sh` if that is the server used by your app, or enter your own HTTPS ntfy server root URL.
4. Enter **only your existing topic name**, exactly as shown in the app. For example, if your subscription URL is `https://ntfy.sh/my-personal-topic`, enter `my-personal-topic`. Do not paste the URL. There is no default topic; an empty or invalid name is rejected and requested again.
5. Keep the monitor running on your Mac, Pi or other computer. Your phone receives notifications; it does not run the checks.

Setup only saves your chosen server and existing topic name. It does not generate a topic, create a subscription or send a setup/test notification. It cannot verify that you subscribed to that topic in the app: the spelling and server must match your existing subscription. Actual stock notifications are published to that configured topic when availability is confirmed.

On public ntfy servers, anyone who knows an unprotected topic can generally read its messages and publish to it. A random topic reduces guessing but is not access control. Use a protected topic/server for stronger privacy. Do not publish your generated configuration, screenshots of your subscription or your token. See [ntfy topic selection and publishing](https://docs.ntfy.sh/publish/) and [server access control](https://docs.ntfy.sh/config/#access-control).

For a server/topic requiring authentication, create a publishing access token according to that server's rules and set `NTFY_TOKEN` before starting the monitor:

```sh
# macOS, Raspberry Pi, Linux: read without putting the token in shell history
printf 'ntfy access token: '
stty -echo
read -r NTFY_TOKEN
stty echo
printf '\n'
export NTFY_TOKEN
python3 check_iphone_duo.py
```

In Windows PowerShell:

```powershell
$secret = Read-Host 'ntfy access token' -AsSecureString
$env:NTFY_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
py -3 check_iphone_duo.py
```

The token is sent only in the ntfy Authorization header. It is never saved by setup, added to notification links or printed by network errors. The phone subscription may also need credentials for protected topics. Public unprotected topics normally need no token. Public service limits and account features can change; consult the server's current documentation. Notifications can be delayed by phone permissions, battery optimization or server configuration; follow the [phone delivery guidance](https://docs.ntfy.sh/subscribe/phone/) and the [self-hosting documentation](https://docs.ntfy.sh/config/) when applicable.

## macOS

Install Python from [python.org](https://www.python.org/downloads/macos/) or your preferred package manager. Do not rely on macOS having a suitable Python preinstalled. Open Terminal, change to the repository folder and verify:

```sh
cd ~/Downloads/apple-pickup-monitor
python3 --version
python3 check_iphone_duo.py --setup
python3 check_iphone_duo.py --once
python3 check_iphone_duo.py
```

Use your actual extracted folder path. `--once` is a real single check, not a notification test: it can send a stock alert. Exit status 1 can mean unknown availability, not just a network failure.

The computer must stay awake and connected. For an awake monitoring session:

```sh
caffeinate -i python3 check_iphone_duo.py
```

Closing a laptop lid or putting it to sleep can still stop checks. For unattended use at login, copy `examples/com.example.apple-pickup-monitor.plist` to `~/Library/LaunchAgents/`, replace **every** `YOUR_USER` and `PYTHON_PATH` placeholder with your real absolute paths, and verify the folder contains your configured `config.json`. Find Python with `command -v python3`. Use a stable Python executable rather than a temporary shell shim. Then:

```sh
mkdir -p ~/Library/LaunchAgents
# Edit the example and copy it to this path first.
plutil -lint ~/Library/LaunchAgents/com.example.apple-pickup-monitor.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.apple-pickup-monitor.plist
```

Logs are written to `monitor.log` and `monitor-error.log` in the configured repository directory. Stop/unload it with:

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.apple-pickup-monitor.plist
```

A LaunchAgent runs while that user is logged in; it does not prevent sleep. If you need an ntfy token, add an `EnvironmentVariables` dictionary with `NTFY_TOKEN` to your **private installed plist**, protect it with `chmod 600`, and never commit it. Exporting a token in Terminal does not automatically pass it to launchd.

If a python.org installation reports a certificate verification error, run its bundled `Install Certificates.command` in `/Applications/Python 3.x/`. For a managed network, install/configure the trusted corporate certificate through your administrator. Do not disable HTTPS verification.

Version 1.0.1 also loads the macOS CA bundle at `/etc/ssl/cert.pem` when available, in addition to Python's default trusted certificates. Explicit `SSL_CERT_FILE` or `SSL_CERT_DIR` settings take precedence and disable this automatic addition. HTTPS verification always remains enabled. DNS, timeout and certificate failures now have separate messages; setup stops on a connection failure instead of asking for another product URL that would encounter the same problem.

If pasting a product URL manually, use the plain address, such as `https://www.apple.com/it/shop/buy-iphone/iphone-duo`. Markdown links copied from chat (`[label](https://...)`), angle-bracket links and backtick-wrapped addresses are also recognized and normalized before validation.

## Raspberry Pi OS / Debian / Ubuntu

Use a supported OS release with Python 3.10 or later. Both ARM and x86 work; no architecture-specific Python dependencies are used.

```sh
sudo apt update
sudo apt install python3 ca-certificates git
python3 --version
```

If your distribution provides an older Python, upgrade to a supported OS/Python release. Download/extract the repository or clone it, then:

```sh
cd ~/apple-pickup-monitor
python3 check_iphone_duo.py --setup
python3 check_iphone_duo.py --once
python3 check_iphone_duo.py
```

For a Pi running without a screen, connect over SSH and run setup in that terminal. Setup requires interactive input; create the configuration before enabling a background service.

### Run automatically at boot with systemd

Edit `examples/apple-pickup-monitor.service` and replace every `YOUR_USER` placeholder and directory with the actual user/repository path. Raspberry Pi usernames are not necessarily `pi`. The service uses `/usr/bin/python3`; change it if your Python is elsewhere. It runs as your ordinary user and writes alert history beside `config.json`.

```sh
sudo cp examples/apple-pickup-monitor.service /etc/systemd/system/apple-pickup-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now apple-pickup-monitor
systemctl status apple-pickup-monitor
journalctl -u apple-pickup-monitor -f
```

Stop the foreground monitor before starting the service. To stop and disable the service:

```sh
sudo systemctl disable --now apple-pickup-monitor
```

For authenticated ntfy, create `/etc/apple-pickup-monitor.env` with a text editor, containing `NTFY_TOKEN=your_actual_token`, set its permissions to `600` owned by root, and uncomment the example's `EnvironmentFile` line. That file stays outside the repository. Restart the service after changing configuration or credentials:

```sh
sudo systemctl restart apple-pickup-monitor
```

The background service cannot ask setup questions. Check the paths and create its configuration first. Logs use the machine's local time zone; the interval is elapsed time and has no Rome-specific schedule.

## Windows

Install Python 3.10+ from [python.org](https://www.python.org/downloads/windows/), including its launcher. In PowerShell:

```powershell
cd "$HOME\Downloads\apple-pickup-monitor"
py -3 --version
py -3 check_iphone_duo.py --setup
py -3 check_iphone_duo.py --once
py -3 check_iphone_duo.py
```

Keep the terminal open or create a Windows Task Scheduler task at logon with your full Python executable path, the script path and `--config` with an absolute path. Set its working directory to the repository folder and prevent overlapping instances. A scheduled task needs its own token environment/credentials; it does not inherit an arbitrary PowerShell session. Disable any task duration limit that would terminate a continuous monitor. Windows sleep pauses checks.

## Other systems

The script should run on other Linux distributions, a server, a VM or a NAS with Python 3.10+, valid CA certificates, persistent writable storage and outbound HTTPS. These environments have not all been tested. No desktop or browser automation is required. Setup and monitoring do not require root. Mobile operating systems and browser-only environments are not primary targets. A suspended machine or a stopped container cannot check stock.

## Commands and configuration

```sh
python3 check_iphone_duo.py --help
python3 check_iphone_duo.py --setup --config london.json
python3 check_iphone_duo.py --config london.json
python3 check_iphone_duo.py --once --config london.json
python3 check_iphone_duo.py --config london.json --state /absolute/private/path/london-state.json
```

`--once` exits 0 only when **every selected pair** has an explicit supported availability status; 1 means an incomplete/failed check or invalid configuration. Availability itself is not an exit status: both available and unavailable can be successful checks. Ctrl+C exits 130. Failed ntfy delivery is logged and retried on a later positive check; `--once` does not wait for another attempt, and its exit code describes Apple checks, not notification delivery.

The JSON generated by setup contains:

| Field | Meaning |
| --- | --- |
| `version` | Configuration schema version, currently `1` |
| `shop_url` | Regional Apple shop root |
| `interval_minutes` | Minutes to wait **after** a check completes |
| `products` | Selected objects with `part`, `name` and regional purchase-page `url` |
| `stores` | Selected objects with exact `id` and display `name` |
| `ntfy.enabled` | `true` for phone notifications; `false` for terminal-only output |
| `ntfy.server` / `ntfy.topic` | Your HTTPS server root and personal topic, when enabled |

Edit the file while the monitor is stopped, or rerun setup. Settings are loaded at startup. There is no dependency installation, `.env` loader, hard-coded topic, embedded token, fast time window or daily heartbeat. `NTFY_TOKEN` is the only notification setting read from the environment. The old `NTFY_TOPIC` environment variable is no longer used. The old `--test-notify`, `--product` and `--part` test overrides have been removed; select production variants through setup instead.

Each round sends one Apple request per selected variant/store pair, with a 1–2 second pause between requests. Eight variants across five stores means 40 requests per round. Keep selections focused and start with the 15-minute default. Incomplete rounds gradually increase the pause up to at least 32 minutes. A 403/429/541 stops that round and triggers a pause of at least 30 minutes. A longer user-configured interval always wins. Five consecutive connection/response failures also stop a round. There are no proxy rotations or block bypasses.

## Alert history and unknown results

State defaults to `<config stem>.state.json` next to the configuration: `config.json` uses `config.state.json`; `london.json` uses `london.state.json`. Keep that file on persistent storage. Run **one process per configuration/state file**; concurrent runs are unsupported and can duplicate alerts or overwrite history.

- An exact selected SKU/store pair with `pickupDisplay: available` produces an alert.
- Another alert is suppressed after successful delivery, including across restarts.
- Two explicit consecutive unavailable/ineligible observations for that pair rearm the alert. Unknown/error observations do not increment the counter or erase history; a confirmed available observation resets it.
- If ntfy delivery fails, the next confirmed positive observation retries. No old stock alert is blindly replayed after hours of downtime.
- Changing product/store/notification configuration resets the history identity. Removing state also resets history and can generate fresh alerts.

**`UNKNOWN` does not mean out of stock.** Apple sometimes returns a store with an empty `partsAvailability` object (this was observed in a live check). Missing stores, missing exact SKUs and unrecognized status values also remain unknown. The script does not guess from recommendation text, availability of a different SKU or a generic `available` string elsewhere in a response. Unknown observations cannot rearm an already delivered alert, so a disappearance/reappearance reported only through empty records may not produce a second notification. Check Apple's website if a pair stays unknown. Even a successful response may become stale immediately.

After a service interruption, inspect logs: there is no separate heartbeat or failure notification. A small possibility of a duplicate remains if the process crashes after ntfy accepts a message but before state is saved. Local state and notifications are not an atomic transaction.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No nearby stores | Correct regional shop and postal code; verify pickup is offered on Apple's website; try a nearby postal code. |
| No variants | Use the correct purchase page and regional SKUs; Apple may have changed the page format. |
| HTTP 403 / 429 / 541 | Leave the monitor stopped/paused, increase the interval, and try later. Do not repeatedly restart it to bypass backoff. |
| Repeated `UNKNOWN` | Open the selected product on Apple; the response may omit exact stock details. Unknown is not a negative stock result. |
| No phone notification | Same server/topic in the app and config; phone permissions, server limits, topic access and `NTFY_TOKEN`; inspect the delivery error in logs. |
| Duplicate alerts | Check for a foreground process plus a service, missing/unwritable state, or a changed configuration. |
| Service fails immediately | Absolute paths, supported Python, valid JSON, existing setup and writable state directory; inspect service logs. |
| HTTPS certificate error | Install/update trusted CA certificates, correct the system clock and configure legitimate network CA certificates. Never disable TLS verification. |
| Mac/Pi stops checking | Sleep, power loss, disconnected network, closed terminal or disabled service. |

## Development and publishing

The production script contains no notification test command or test-specific product overrides. The separate regression suite uses simulated responses and sends **no network requests or notifications**:

```sh
python3 -m unittest discover -s tests -v
```

A GitHub Actions workflow runs those checks on Linux, macOS and Windows with Python 3.10 and 3.13. Platform startup examples must still be adjusted to the machine; CI does not install launchd/systemd services or prove live stock availability.

Before publishing, keep only the source, README, startup examples, tests and workflow. `.gitignore` excludes local JSON configurations/history, logs, `.env` files, Python caches and private installed startup files. It cannot remove secrets already committed to Git history. Review `git status` and the staged diff before committing. The distributed project contains no personal topic, token, postal code or selected store configuration.

To create your own repository, create an empty GitHub repository, then run from this project directory (replace the URL):

```sh
git init
git add check_iphone_duo.py README.md .gitignore examples tests .github
git diff --cached
git commit -m "Add configurable Apple pickup monitor"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/apple-pickup-monitor.git
git push -u origin main
```

Authenticate to GitHub using your preferred supported method. Choose and add a license before sharing if you want to grant others permission to reuse/modify the code; no license has been imposed on your original script. Apple and ntfy are trademarks of their respective owners; this project is not affiliated with either.
