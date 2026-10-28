# Apple Pickup Monitor

Monitor iPhone pickup availability at nearby Apple Stores and receive notifications on your phone through **your own ntfy topic**.

Choose your regional Apple shop, nearby locations, stores, iPhone variants and check frequency through an interactive setup. The monitor runs in a terminal or as a background service on macOS, Raspberry Pi, Linux and Windows.

## Features

- Guided selection of regional shop, nearby stores, iPhone families, storage capacities and colors.
- Nearby searches using postal codes or locations, plus direct checks of selected stores.
- Configurable check frequency and optional faster checking windows.
- Notifications when monitoring starts, when stock is found, after repeated errors and when checking resumes.
- A daily status notification, with a configurable hour.
- Your existing ntfy topic on ntfy.sh or your own HTTPS ntfy server; optional access-token authentication.
- Network retries, duplicate-alert suppression during a session and retries for undelivered stock notifications.
- Python standard library only: no pip packages or Apple login required.

## Requirements

- **Python 3.10 or later.**
- An internet connection and trusted HTTPS certificates.
- Both `check_iphone_duo.py` and `configuration.py` in the same directory.
- For phone notifications, an ntfy app subscription to your personal topic.

The computer must remain running, awake and connected for checks to continue. Your phone receives notifications; it does not need to run the script.

## Quick start

Download the repository using **Code → Download ZIP** on GitHub and extract it, or clone it. Open a terminal in the project directory, then run:

```sh
python3 check_iphone_duo.py --setup
python3 check_iphone_duo.py
```

On Windows, replace `python3` with `py -3`.

**Setup saves your configuration and exits. Run the second command to start monitoring and send the startup notification.** Press Ctrl+C to stop.

### Configure the monitor

The setup asks for:

1. **Regional Apple shop:** enter a shop code such as `us`, `uk`, `it`, `ca`, `au`, `de`, `fr`, `jp`, `hk-zh` or `cn`, or paste its shop URL.
2. **Nearby locations:** enter a postal code or location accepted by that Apple shop. You can enter several, separated by commas. Leading zeros, letters, spaces and hyphens are preserved.
3. **iPhone families and variants:** select models, capacities and colors from Apple's purchase-page data. Enter numbers such as `1,3`, a range such as `1-3`, or `all`.
4. **Apple Stores:** select from the nearby stores returned by Apple.
5. **Check interval:** choose the normal interval in minutes; the default is 15 and the minimum is 2.
6. **Notifications:** enable ntfy, select the server used by your app and enter only your existing topic name.

Settings are saved in `config.json`. Starting without an existing configuration opens setup and exits. Run `--setup` again to replace the configuration, or edit the JSON file while the monitor is stopped. Restart after changing settings.

When Apple provides postal codes for your selected stores, setup includes them in nearby searches alongside the locations you entered. It also uses the first selected store's time zone when available.

## Understanding availability alerts

Selected variants are the products used to query Apple. Apple's responses can include **available alternatives with another capacity or color in the selected iPhone family**. These alternatives can also trigger notifications. Product and store filtering uses name matching, so the selection is not a strict exact-variant alert filter.

For example, a lookup for a black 512GB phone may return a silver 512GB or black 1TB phone. Read the **actual product title and store in the alert** to identify which variant is offered. An available alternative does not establish that the requested color/capacity is available.

A completed check without matching pickup availability is logged as no availability. Failed requests are included in the error count; they do not establish that a phone is out of stock. The parser accepts the pickup information exposed by Apple's service, which can omit details or change over time.

This tool checks online pickup availability. It does not reserve or purchase products. Confirm the exact variant and pickup option on Apple before ordering or travelling; availability can change immediately.

### Regional support

Support depends on the selected Apple shop offering a compatible online pickup service. Not every country, reseller or product is supported. Shop codes are Apple's codes, which may differ from ISO country codes (`uk`, for example). China uses `www.apple.com.cn`.

CAP, ZIP code and postcode are all entered as text; Apple interprets them for the selected region. If the regional service accepts a city or another location instead, you can enter that value. Product/store names and pickup quotes may remain in the regional shop's language. The program does not guarantee that a particular location format or every international shop will work.

## Set up ntfy notifications

1. Install/open the [ntfy app for iOS or Android](https://docs.ntfy.sh/subscribe/phone/), or use the [web app](https://ntfy.sh/app).
2. Add your personal topic in the app first, or use a subscription you already have. Allow phone notifications.
3. During script setup, choose the **same server** as the app. For an ntfy.sh subscription, press Enter to accept `https://ntfy.sh`.
4. Enter **only the exact topic name**, not a URL. If your subscription URL is `https://ntfy.sh/my-personal-topic`, enter `my-personal-topic`. Empty names and URLs are rejected.
5. Start monitoring without `--setup` or `--once`:

```sh
python3 check_iphone_duo.py
```

The monitor prints the configured destination and sends an `iPhone monitor active` notification with a “Monitoring started” message before checking stock. It sends subsequent stock, error, recovery and daily status messages to that same topic.

The script does not generate topics, create app subscriptions or send notifications during setup. Your server and topic spelling must match the app. A terminal message alone does not confirm phone delivery: check for `ntfy notification not delivered (...)` after any failed publication attempts. Phone permissions, Do Not Disturb, battery settings and server delivery configuration can affect arrival; see the [ntfy phone guide](https://docs.ntfy.sh/subscribe/phone/).

### Topic privacy

Anyone who knows an unprotected public topic name can generally read its messages and publish to it. Use a hard-to-guess personal topic or a protected server/topic, and keep `config.json` private. See [topic selection](https://docs.ntfy.sh/publish/) and [access control](https://docs.ntfy.sh/config/#access-control).

### Optional access token

Public unprotected topics normally need no token. For protected topics, create a publishing access token according to your server's rules and set `NTFY_TOKEN` before launching. The token is sent in the Authorization header and is not written to JSON by setup.

macOS/Linux (read without putting the token in shell history):

```sh
printf 'ntfy access token: '
stty -echo
read -r NTFY_TOKEN
stty echo
printf '\n'
export NTFY_TOKEN
python3 check_iphone_duo.py
```

Windows PowerShell:

```powershell
$secret = Read-Host 'ntfy access token' -AsSecureString
$env:NTFY_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
py -3 check_iphone_duo.py
```

The phone subscription may also require credentials. Background services need their own token environment, as described below. Features and limits depend on your server; consult the [ntfy documentation](https://docs.ntfy.sh/).

## macOS

Install Python from [python.org](https://www.python.org/downloads/macos/) or your preferred package manager. Do not rely on macOS having a suitable Python preinstalled. Open Terminal, change to the repository folder and verify:

```sh
cd ~/Downloads/apple-pickup-monitor
python3 --version
python3 check_iphone_duo.py --setup
python3 check_iphone_duo.py --once
python3 check_iphone_duo.py
```

Use your actual extracted folder path. `--once` is a real single check, not a notification test: it can send a stock alert. A valid response without pickup availability is a successful negative check. A failed round returns exit status 1; see the exit-status details below.

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

The HTTPS helper also loads the macOS CA bundle at `/etc/ssl/cert.pem` when available, in addition to Python's default trusted certificates. Explicit `SSL_CERT_FILE` or `SSL_CERT_DIR` settings take precedence and disable this automatic addition. HTTPS verification always remains enabled. Network exception details are shown in the log. Setup stops on connection failures instead of treating them as product selection problems.

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

Edit `examples/apple-pickup-monitor.service` and replace every `YOUR_USER` placeholder and directory with the actual user/repository path. Raspberry Pi usernames are not necessarily `pi`. The service uses `/usr/bin/python3`; change it if your Python is elsewhere. It runs as your ordinary user and loads your private `config.json`. Monitoring history stays in memory and resets when the process restarts.

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

The background service cannot ask setup questions. Check the paths and create its configuration first. Logs, daily notifications and optional fast windows use the configured time zone, falling back to the computer's local time.

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

The script should run on other Linux distributions, a server, a VM or a NAS with Python 3.10+, valid CA certificates, storage for your private configuration and outbound HTTPS. These environments have not all been tested. No desktop or browser automation is required. Setup and monitoring do not require root. Mobile operating systems and browser-only environments are not primary targets. A suspended machine or a stopped container cannot check stock.

## Commands

| Command | Action |
| --- | --- |
| `python3 check_iphone_duo.py --setup` | Create or replace the configuration interactively, then exit |
| `python3 check_iphone_duo.py` | Start continuous monitoring and send the startup notification when ntfy is enabled |
| `python3 check_iphone_duo.py --once` | Perform one real checking round, without the startup notification |
| `python3 check_iphone_duo.py --config london.json` | Use a specific configuration file |
| `python3 check_iphone_duo.py --help` | Show command-line help |
| `python3 check_iphone_duo.py --version` | Show the program version |

To keep independent configurations:

```sh
python3 check_iphone_duo.py --setup --config london.json
python3 check_iphone_duo.py --config london.json
```

Use an absolute `--config` path for background services. Only run one instance per configuration unless you deliberately want duplicate requests and notifications.

### Single checks and exit codes

`--once` performs real checks and can send stock or daily-status notifications. It skips the startup notification.

- Exit **0**: each selected family's round completed with at least one successful request and was not aborted. A round with some failed requests can therefore still return 0; inspect the log's error count.
- Exit **1**: a family's round failed, was aborted, or a configuration/startup error occurred.

Availability itself is not an exit code: both available and unavailable products can be successful checks.

## Configuration reference

| JSON field | Meaning |
| --- | --- |
| `version` | Configuration schema, currently `1` |
| `shop_url` | Regional Apple shop root |
| `locations` | Postal-code/location strings used for nearby searches |
| `products` | Query variants with regional `part`, display `name` and purchase-page `url` |
| `stores` | Selected store `id` and `name` values |
| `interval_minutes` | Normal target minutes between the starts of checking rounds |
| `ntfy.enabled` | Whether to publish notifications |
| `ntfy.server`, `ntfy.topic` | Your HTTPS server root and existing personal topic name |
| `timezone` | Optional IANA time zone; falls back to the computer's local time if unavailable |
| `heartbeat_hour` | Daily status hour, default `9`; use `null` to disable |
| `fast_schedule` | Optional faster checking windows; omitted/`null` uses the normal interval all day |

Topic names are entered in setup, not through an `NTFY_TOPIC` environment variable. `NTFY_TOKEN` is the optional environment variable for authentication.

### Faster checking windows

To check every two minutes from 06:00 to 10:00, add this field to your configuration object, with the appropriate comma between JSON fields:

```json
"fast_schedule": {"minutes": 2, "windows": [[6, 0, 10, 0]]}
```

Times use the configured time zone. Windows must start and end on the same day, with the start before the end. The normal interval applies outside those windows. The time spent checking is subtracted from the interval, with at least 30 seconds of rest before the next round.

### Daily status

The daily message is sent after `heartbeat_hour` following a successful round. Starting continuous monitoring marks the current day as reported, so the first daily status message is normally on the following day. Set `"heartbeat_hour": null` to disable it.

## Monitoring and error handling

The monitor checks the configured locations and direct stores for each query variant. For each family, the approximate request count per round is:

```text
query variants × (locations + selected stores)
```

Transient retries and periodic part-number discovery can add requests. Keep selections focused and start with the 15-minute default.

- Apple requests have a 15-second timeout and up to two attempts. Network errors and transient HTTP statuses can be retried after 2–4 seconds.
- Inventory requests are separated by a 0.8–1.5 second pause. Five consecutive request failures abort that family's round.
- Three consecutive failed rounds trigger an error notification. A later successful round triggers a recovery notification. Partial rounds count as successful.
- Stock alerts are grouped by product, with up to eight product lines in one alert. Repeated availability is suppressed during the session until the product/store pair has been absent for two eligible rounds. Absences count only when at least 75% of the round's requests succeeded.
- ntfy publications have a 10-second timeout and up to three attempts. Undelivered stock alerts are queued for retry for up to two hours. A delayed alert is labelled `(delayed)` and may describe stock that has since changed.
- Startup, error, recovery and daily messages get immediate publication attempts but are not queued for later delivery.
- Monitoring history and pending alerts are held in memory. They are lost when the process exits, so restarting can produce fresh stock alerts.
- Unexpected errors during continuous checking are logged and the monitor continues.

Part-number discovery uses a six-hour cache and falls back to configured/known query parts if a page cannot be read. Multiple iPhone families have separate availability histories and error counters and are checked sequentially.

If Apple repeatedly rejects requests, stop monitoring, increase the interval and try later.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Setup finished but no startup notification | Run again without `--setup` or `--once`; setup only saves configuration. |
| `ntfy disabled` in the terminal | Enable ntfy in setup, or set `ntfy.enabled` to `true` with your correct existing server/topic. |
| Startup notification not received | Match the printed destination with the app. Look for `ntfy notification not delivered` and its error; check permissions, topic authorization and phone notification settings. |
| Other colors/capacities appear | Apple can return available alternatives. Read the actual title in the alert. |
| No availability | Check selected models, store names, regional shop and nearby locations against Apple's website. |
| `available but ... ignored` | The returned product name or store name does not match the configured filters. |
| Network, HTTP or JSON errors | Check the failed request count. Failed requests do not establish that a product is out of stock. |
| HTTPS certificate error | Update trusted CA certificates or run the python.org `Install Certificates.command`; keep HTTPS verification enabled. |
| Background service asks for configuration/location | Run setup interactively first and verify the service's absolute `--config` path. |
| Duplicate notifications | Check for a service plus a terminal process, repeated restarts or another monitor using the same topic. |
| Checking pauses | Check sleep, power, network connectivity, terminal closure and service status. |

## Development

Run the offline checks from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

The suite checks request routing, response parsing, alternative variants, notification requests, configuration and failure handling. It sends no Apple requests or ntfy notifications. GitHub Actions runs the suite on Linux, macOS and Windows with Python 3.10 and 3.13.

Keep personal configuration, topics, tokens, logs and local environment files out of commits. The included `.gitignore` excludes these local file types; review staged changes before pushing.

This project is not affiliated with Apple or ntfy.
