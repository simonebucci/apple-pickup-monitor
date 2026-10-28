# Apple Pickup Monitor

An English-language version of the original iPhone pickup checker, with a separate guided configuration for your Apple shop, nearby stores, iPhone models, check frequency and **existing personal ntfy topic**.

**Python 3.10+. Standard library only: no pip packages, Apple login or browser automation.** Keep `check_iphone_duo.py` and `configuration.py` in the same directory.

## What is preserved from the original

The monitoring engine was rebuilt directly from the original script. The original URL builder, Apple response parser, request retry logic, store/product name filters and cycle control flow are retained. Automated structural checks compare these functions against fingerprints of the original, ignoring translated message text.

- Both postal-code nearby searches **and** direct store requests are performed.
- The parser reads all variants returned by Apple's response, including alternatives recommended by Apple. It does not demand that the returned part number equal the requested part number.
- Available entries are filtered by the selected store names and iPhone family, as in the original.
- Requests get the original retry rules, pauses and timeouts; errors, recovery, daily status and the two-hour pending notification queue follow the original behavior.
- Startup notifications use the original **POST to `https://your-ntfy-server/your-topic`**, with a UTF-8 text body and Title/Priority/Tags/Click headers. There is no JSON publication to the server root.
- Alert history and pending messages stay **in memory**, as in the original. Restarting begins fresh; files from earlier versions do not suppress alerts.

Changes around that engine are limited to guided configuration, English messages, regional URL/header settings, optional ntfy token authentication, the verified macOS certificate helper, and removal of test-only command-line overrides. Multiple selected families each use an instance of the original monitor with their own family configuration.

## Important: selected query variants and Apple alternatives

Setup lets you select model, capacity and color variants **to query**. To preserve the original logic, a response may also produce an alert for another capacity/color in the same iPhone family that Apple recommends. The alert reports the **actual returned product title** and store, never renames it to the requested variant. The family filter is the original name-substring filter; it is not an exact variant filter.

For example, a lookup for a black 512GB phone may return a silver 512GB or black 1TB phone. The original checker reports those alternatives, and so does this version. If a black 512GB SKU is absent from that response, the tool cannot claim that exact phone is available merely because a different variant is available.

This is an unofficial checker. It does not reserve or buy phones; confirm the exact model and pickup option on Apple before ordering or travelling.

## Quick start

Download the full repository/ZIP and extract it. From its directory:

```sh
python3 check_iphone_duo.py --setup
python3 check_iphone_duo.py
```

On Windows use `py -3` instead of `python3`.

Setup asks for:

1. Regional Apple shop code/URL, such as `us`, `uk`, `it`, `ca`, `au`, `de`, `fr`, `jp`, `hk-zh` or `cn`.
2. Nearby postal code/location. You may enter several, separated by commas. Leading zeros, letters, spaces and hyphens are preserved. Apple interprets the value for the selected shop.
3. One or more current iPhone families, then capacity/color variants to query. Enter `1,3`, `1-3` or `all` to choose list items.
4. Nearby stores returned by Apple. Selected stores' postal codes are also included in subsequent nearby searches when Apple supplies them, alongside direct requests to those stores.
5. Normal check interval: 15 minutes by default, minimum 2.
6. Whether to enable ntfy, your server (`https://ntfy.sh` by default), and **only the name of your topic already added in the app**.

Setup saves `config.json` and exits; **run the second command to start monitoring and receive the startup notification**. Setup itself sends no notification and generates no topic. Starting without an existing config opens the same setup and exits. `--setup` replaces the selected config.

Regional support depends on Apple's online shop exposing the same pickup service. Not every country, reseller or Apple product is supported. Shop codes are Apple's codes (`uk`, for example), not always ISO country codes. China uses `www.apple.com.cn`. Product/store names and quotes may remain localized by Apple. On shops where a location is not accepted or pickup is not offered, setup cannot invent a compatible alternative.

## ntfy: use the subscription you already have

1. Install/open the [ntfy app for iOS or Android](https://docs.ntfy.sh/subscribe/phone/) or the [web app](https://ntfy.sh/app).
2. Add your own topic in that app first, or use a subscription you already have. Enable phone notification permissions.
3. In script setup, choose the **same server** as the app. For a normal ntfy.sh subscription, press Enter at the server prompt.
4. Enter **only the topic name**, exactly as shown in the app. If its URL is `https://ntfy.sh/my-personal-topic`, enter `my-personal-topic`, not the full URL. Empty names and URLs are rejected and requested again.
5. Start the script without `--setup` or `--once`. It prints the configured destination and sends `iPhone monitor active` with a “Monitoring started” message before checking stock.

The script never creates or randomly generates a topic. It cannot check whether your phone is subscribed: topic spelling and server must match your existing app subscription. If publication fails, the original three attempts run and the log shows `ntfy notification not delivered (...)` with the network/HTTP error. A message printed in the terminal is not proof of phone delivery. Phone permissions, Do Not Disturb, battery settings and server delivery configuration can also affect arrival; see the [ntfy phone guide](https://docs.ntfy.sh/subscribe/phone/).

Unprotected public ntfy topics can generally be read and published to by anyone who knows their name. Use a hard-to-guess personal topic or a protected server/topic, and keep your configuration private. See [topic selection](https://docs.ntfy.sh/publish/) and [access control](https://docs.ntfy.sh/config/#access-control).

For protected topics, create a publishing access token according to your server's rules and set `NTFY_TOKEN` before launching. Public unprotected topics normally need no token. The token is optional and sent only in the Authorization header; setup never writes it to JSON.

macOS/Linux (read without entering the token in shell history):

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

The phone subscription may also require credentials. Background services need their own token environment, as described below. Limits and features depend on the server; consult the [current ntfy documentation](https://docs.ntfy.sh/).

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

The HTTPS helper also loads the macOS CA bundle at `/etc/ssl/cert.pem` when available, in addition to Python's default trusted certificates. Explicit `SSL_CERT_FILE` or `SSL_CERT_DIR` settings take precedence and disable this automatic addition. HTTPS verification always remains enabled. The original network exception details remain visible in the log. Setup stops on connection failures instead of treating them as product selection problems.

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

Edit `examples/apple-pickup-monitor.service` and replace every `YOUR_USER` placeholder and directory with the actual user/repository path. Raspberry Pi usernames are not necessarily `pi`. The service uses `/usr/bin/python3`; change it if your Python is elsewhere. It runs as your ordinary user and loads your private `config.json`. Monitoring history stays in memory, as in the original script.

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

The background service cannot ask setup questions. Check the paths and create its configuration first. Logs and optional fast windows use the machine's local time zone; there is no fixed Rome time zone.

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

## Commands and configuration

```sh
python3 check_iphone_duo.py --help
python3 check_iphone_duo.py --setup --config london.json
python3 check_iphone_duo.py --config london.json
python3 check_iphone_duo.py --once --config london.json
```

`--once` performs real stock checks and can send stock/daily-status messages, but skips the startup message. Exit 0 means that the original cycle logic considers the round successful: at least one request succeeded and the round was not aborted. A partial round can therefore exit 0; inspect the request error count. Exit 1 means a failed round or configuration/startup error. With multiple families, `--once` returns 1 if any family's round fails. Availability itself is not an exit status.

| JSON field | Meaning |
| --- | --- |
| `version` | Configuration schema, currently `1` |
| `shop_url` | Regional Apple shop root |
| `locations` | Postal-code/location strings used for nearby searches |
| `products` | Query variants: objects with regional `part`, display `name` and purchase-page `url` |
| `stores` | Selected objects with `id` and `name`, used for direct requests and original name filtering |
| `interval_minutes` | Normal target minutes between starts of checking rounds |
| `ntfy.enabled` | Whether to publish notifications |
| `ntfy.server`, `ntfy.topic` | Your HTTPS server root and existing topic name |
| `timezone` | Optional IANA zone; setup uses the first selected store's zone if provided, otherwise the computer's local time |
| `heartbeat_hour` | Optional local hour for the daily message; default `9`, `null` disables it |
| `fast_schedule` | Optional faster local-time schedule; omitted/`null` uses the selected normal interval all day |

The original faster schedule can be configured by adding:

```json
"fast_schedule": {"minutes": 2, "windows": [[6, 0, 10, 0]]}
```

There is no fixed Rome schedule or Italian SKU suffix for other regions. The normal/fast interval calculation remains the original function: subtract checking time and leave at least 30 seconds of rest. The daily heartbeat is normally sent after 09:00 on subsequent days because startup marks the current day as reported. Settings are loaded at launch; stop and restart after edits.

Part-number discovery retains the original six-hour cache and fallback to known parts. Its inputs are configured purchase pages and selected query SKUs, so discovery does not silently expand your query selection to every phone on the page. The Apple response parser still reads recommended alternatives in the same family. Multiple families are checked sequentially with separate original monitor instances and deduplication/failure counters.

## Error handling: original behavior

- A DNS check precedes the cycle. A disconnected device records a failed round rather than claiming no stock.
- Apple requests use a 15-second timeout and up to two attempts. HTTP 429, 500, 502, 503, 504 and 541 and network errors can be retried after 2–4 seconds. Non-transient HTTP errors are not retried immediately.
- The original 0.8–1.5 second request pause remains. Five consecutive failed requests abort that family's cycle.
- After three failed cycles, an error notification is sent; a later successful cycle sends a recovery message. Partial cycles count as successful, as in the original.
- Availability that disappears is forgotten after two eligible cycles; absence counters are updated only when at least 75% of requests succeeded. Failed/aborted cycles preserve availability history.
- Newly seen availability produces grouped alerts, using the original first-eight-product-lines limit. Successful repeats are suppressed until the pair is forgotten. A restart clears this in-memory history and can alert again.
- ntfy sends have a 10-second timeout and up to three attempts, with 2, 4 and 6 second waits after failures. Undelivered stock notifications remain in the original two-hour queue, retried before later connected checks. The queue is in memory and is lost on exit. Delayed messages are labelled `(delayed)` and may describe stock that has since changed. Startup/error/recovery/heartbeat messages use immediate attempts and are not queued.
- Unexpected errors in continuous checking are logged and the monitor continues. There is no added exponential backoff, persistent-state suppression or exact-SKU response filter.

Empty pickup availability is logged as no availability, as in the original. Malformed JSON or a missing `body` is a reading error. The original parser also retains its permissive empty-body/pickup handling and broad fallback for an `available` string elsewhere in the response; the original product/store filters still apply afterward. These are the original semantics, not a new interpretation of Apple's undocumented data format. A physical store may have units not offered through online pickup; a web response can also change immediately.

The target count per family is `query variants × (postal locations + selected direct stores)`, before retries and occasional discovery requests. Keep selections focused and use a sensible interval. If Apple repeatedly rejects requests, stop, increase the interval and try later. There are no proxy rotations or block bypasses.

## Updating from the earlier rewritten versions

Replace the project files with this ZIP, **including `configuration.py` beside the main script**. You may keep your private `config.json`. If it lacks `locations`, the next terminal run asks only for the postal code/location needed to restore the original nearby searches and saves it. A background service cannot answer that prompt: run once interactively first, or rerun setup. No personal location is hard-coded in the distribution.

The previous `--state` option and state-file mechanism have been removed. Existing state files are ignored and do not block startup/stock notifications. No state or personal configuration is included in the release. Old test-only flags (`--test-notify`, `--part`, `--product`) remain removed. The `NTFY_TOPIC` environment variable does not override configuration; enter the topic through setup. `NTFY_TOKEN` remains the optional authentication environment variable.

Only run one foreground/background instance per configuration unless you deliberately want duplicate checks and notifications. Stop the foreground process before enabling a service.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Setup finished but no startup notification | Run the script again without `--setup` or `--once`; setup only saves configuration. |
| `ntfy disabled` in the terminal | Enable ntfy in setup or set `ntfy.enabled` to `true` with your correct existing server/topic. |
| Startup notification not received | Check the printed destination against the app, then look for `ntfy notification not delivered` and its error after the attempts finish. Check phone permissions and topic authorization. |
| A requested variant is absent but other phones are listed | Apple's recommendations can contain different colors/capacities. Read the actual returned title. This is the original parser behavior. |
| No availability | Confirm selected model/store names and regional shop, try another nearby postal code and check Apple's website. No stock is guaranteed. |
| `available but ... ignored` | The returned product family or store name does not match your configured original filters. |
| HTTP errors, DNS failure or invalid JSON | The cycle may be failed/partial, not a trustworthy negative stock result. Inspect the log; repeated failures trigger an error notification if ntfy itself works. |
| HTTPS certificate error | Update/install trusted CA certificates or run the python.org `Install Certificates.command`; keep TLS verification enabled. |
| Service exits asking for setup/location | Run interactively first and verify the service's absolute `--config` path. |
| Duplicate startup/stock alerts | Check for a service plus a terminal process, service restarts or another monitor using the same topic. Restarting resets original in-memory history. |
| Checking pauses | Sleep, power/network loss, a closed terminal or a stopped service. |

## Development and publishing

The offline regression suite sends no Apple requests or ntfy notifications:

```sh
python3 -m unittest discover -s tests -v
```

It checks the original core's structure against `tests/original_core.sha256`, request routing through both nearby and direct-store queries, alternative variants, original error/grace/retry handling, and startup's POST URL/body/headers. Translated messages are normalized for the structure comparison. Separate validation also compared original/rebuilt parsing and full-cycle results using real Apple responses; such a comparison verifies response handling, not future stock or phone delivery.

GitHub Actions runs the offline suite on Linux, macOS and Windows with Python 3.10 and 3.13. Startup services and every international shop have not been tested on real machines. `.gitignore` excludes personal JSON configurations, previous state files, logs, `.env` files and Python caches. It cannot remove secrets already committed. Review staged files before publishing.

Create an empty GitHub repository, then from this folder (replace the URL):

```sh
git init
git add check_iphone_duo.py configuration.py README.md .gitignore examples tests .github
git diff --cached
git commit -m "Add guided configuration to original Apple pickup monitor"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/apple-pickup-monitor.git
git push -u origin main
```

Choose a license before publication if you want to grant reuse/modification rights; no license has been imposed on the original script. This project is not affiliated with Apple or ntfy.
