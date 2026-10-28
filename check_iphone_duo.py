#!/usr/bin/env python3
"""Configurable Apple Store iPhone pickup monitor. Python 3.10+, standard library only."""

import argparse
import hashlib
import http.client
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import random
import re
import socket
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

VERSION = "1.0.2"
PART = re.compile(r"[A-Z0-9]{5,12}/A")
STORE = re.compile(r"R\d{3,6}")


def log(message):
    print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}] {message}", flush=True)


class MonitorError(Exception):
    """A safe, actionable error that can be printed without leaking credentials."""


class AppleBlocked(MonitorError):
    pass


class ConnectionFailure(MonitorError):
    pass


def tls_context():
    """Verify HTTPS using Python trust plus the macOS CA bundle when available."""
    context = ssl.create_default_context()
    if sys.platform == "darwin" and not any(os.environ.get(key) for key in ("SSL_CERT_FILE", "SSL_CERT_DIR")):
        bundle = Path("/etc/ssl/cert.pem")
        if bundle.is_file():
            context.load_verify_locations(cafile=str(bundle))
    return context


def connection_failure(reason):
    if isinstance(reason, ssl.SSLCertVerificationError):
        return ConnectionFailure(
            "HTTPS certificate verification failed. On macOS with Python from python.org, "
            "run /Applications/Python 3.x/Install Certificates.command for your Python version. "
            "On Linux, install/update ca-certificates. On managed networks, configure the trusted "
            "network CA. Do not disable HTTPS verification.")
    if isinstance(reason, socket.gaierror):
        return ConnectionFailure("DNS lookup failed. Check your internet connection, DNS settings or VPN.")
    if isinstance(reason, TimeoutError):
        return ConnectionFailure("The connection timed out. Check connectivity and try again later.")
    if isinstance(reason, ssl.SSLError):
        return ConnectionFailure("The HTTPS connection failed. Check the system clock, Python TLS support and network certificates.")
    return ConnectionFailure("Connection failed. Check internet access, proxy/VPN settings and service availability.")


def request(url, *, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {
        "User-Agent": "Mozilla/5.0 ApplePickupMonitor/" + VERSION,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=25, context=tls_context()) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if urllib.parse.urlsplit(url).hostname in ("www.apple.com", "www.apple.com.cn") and exc.code in (403, 429, 541):
            raise AppleBlocked(f"Apple returned HTTP {exc.code}; pausing requests. Try again later.") from None
        raise MonitorError(f"HTTP {exc.code}. Check the service, region and configuration.") from None
    except urllib.error.URLError as exc:
        raise connection_failure(exc.reason) from None
    except OSError as exc:
        raise connection_failure(exc) from None
    except (UnicodeError, ValueError, http.client.HTTPException):
        raise MonitorError("Invalid URL, request settings or incomplete server response.") from None


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        raise MonitorError(f"Cannot read valid JSON from {path}.") from None


def pasted_url(value):
    value = value.strip().strip("`")
    markdown = re.fullmatch(r"\[[^\]\r\n]*\]\((https://[^\s()]+)\)", value)
    if markdown:
        return markdown.group(1)
    if value.startswith("<https://") and value.endswith(">"):
        return value[1:-1]
    return value


def shop_url(value):
    value = pasted_url(value).lower()
    if re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", value):
        value = ("https://www.apple.com/shop/" if value == "us" else
                 "https://www.apple.com.cn/shop/" if value == "cn" else
                 f"https://www.apple.com/{value}/shop/")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc not in ("www.apple.com", "www.apple.com.cn")
            or parsed.query or parsed.fragment or not re.fullmatch(r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?shop/?", parsed.path)):
        raise MonitorError("Enter a regional Apple shop URL or shop code, such as us, uk, it, ca or hk-zh.")
    return value.rstrip("/") + "/"


def product_url(value, base):
    url = urllib.parse.urljoin(base, pasted_url(value))
    if (not url.startswith(base) or not re.fullmatch(r"buy-iphone/iphone-[a-z0-9-]+(?:/[^\s?#\[\]()<>]*)?/?", url[len(base):])):
        raise MonitorError("Use an iPhone purchase-page URL from the selected regional shop.")
    return url


class PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.blocks, self.buffer = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "script" and attrs.get("type") == "application/json":
            self.buffer = []

    def handle_data(self, data):
        if self.buffer is not None:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.buffer is not None:
            try:
                self.blocks.append(json.loads("".join(self.buffer)))
            except ValueError:
                pass
            self.buffer = None


def variants_from_page(raw):
    """Read structured iPhone records; never mistake accessory SKUs for phones."""
    page = PageData()
    page.feed(raw)
    found = {}

    def walk(node):
        if isinstance(node, dict):
            part, name = node.get("partNumber"), node.get("name")
            if (isinstance(part, str) and PART.fullmatch(part) and isinstance(name, str)
                    and node.get("category") == "iphone"):
                found[part] = " ".join(html.unescape(name).split())
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for block in page.blocks:
        walk(block)
    return found


def pickup(base, part, *, location=None, store=None):
    query = {"mts.0": "regular", "mts.1": "compact", "product": part, "cppart": "UNLOCKED/WW"}
    if location is not None:
        query.update(searchNearby="true", little="false", location=location)
    else:
        query["store"] = store
    raw = request(base + "pickup-message-recommendations?" + urllib.parse.urlencode(query))
    try:
        payload = json.loads(raw)
        if str(payload.get("head", {}).get("status", "200")) != "200":
            raise ValueError()
        body = payload["body"]
        message = (body.get("content") or {}).get("pickupMessage") or body.get("PickupMessage")
        if (not isinstance(message, dict) or not isinstance(message.get("stores"), list)
                or any(not isinstance(row, dict) for row in message["stores"])):
            raise ValueError()
        return message["stores"]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise MonitorError("Unrecognized Apple response; availability could not be verified.") from None


def select(items, label):
    if not items:
        raise MonitorError(f"No {label} found.")
    for index, (_, name) in enumerate(items, 1):
        print(f"  {index:2}. {name}")
    while True:
        answer = input(f"Select {label} (numbers separated by commas, ranges such as 1-3, or all): ").strip().lower()
        if answer == "all":
            return [key for key, _ in items]
        try:
            numbers = set()
            for token in answer.split(","):
                bounds = token.strip().split("-")
                if len(bounds) == 1:
                    numbers.add(int(bounds[0]))
                elif len(bounds) == 2:
                    first, last = map(int, bounds)
                    if not 1 <= first <= last <= len(items):
                        raise ValueError()
                    numbers.update(range(first, last + 1))
                else:
                    raise ValueError()
            if not numbers or min(numbers) < 1 or max(numbers) > len(items):
                raise ValueError()
            return [key for index, (key, _) in enumerate(items, 1) if index in numbers]
        except ValueError:
            print("Enter valid item numbers, ranges or all.")


def validate(config):
    if not isinstance(config, dict) or config.get("version") != 1:
        raise MonitorError("Unsupported configuration version. Run --setup.")
    config["shop_url"] = shop_url(config.get("shop_url", ""))
    interval = config.get("interval_minutes")
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval < 2:
        raise MonitorError("interval_minutes must be a finite number of at least 2.")
    for field, pattern in (("products", PART), ("stores", STORE)):
        records = config.get(field)
        if not isinstance(records, list) or not records:
            raise MonitorError(f"Configure at least one entry in {field}.")
        ids = set()
        for record in records:
            key = "part" if field == "products" else "id"
            if (not isinstance(record, dict) or not isinstance(record.get(key), str)
                    or not pattern.fullmatch(record[key]) or record[key] in ids
                    or not isinstance(record.get("name"), str) or not record["name"].strip()):
                raise MonitorError(f"Invalid or duplicate entry in {field}.")
            ids.add(record[key])
            if field == "products":
                record["url"] = product_url(record.get("url", ""), config["shop_url"])
    ntfy = config.get("ntfy")
    if not isinstance(ntfy, dict) or not isinstance(ntfy.get("enabled"), bool):
        raise MonitorError("ntfy.enabled must be true or false.")
    if ntfy["enabled"]:
        parsed = urllib.parse.urlsplit(ntfy.get("server", ""))
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise MonitorError("Use an HTTPS ntfy server root URL, without credentials or a path.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ntfy.get("topic", "")):
            raise MonitorError("Use a 1-64 character ntfy topic containing only letters, digits, _ and -.")
    return config


def setup(path):
    print("Apple Pickup Monitor setup\nSelect one regional shop per configuration. Apple product/store names may be localized.")
    base = shop_url(input("Apple shop code or URL (e.g. us, uk, it, ca, au, hk-zh, cn): "))
    location = input("Nearby postal code or location accepted by that Apple shop: ").strip()
    if not location:
        raise MonitorError("A location is required to find nearby stores.")
    print("Loading current iPhone families...")
    try:
        page = PageData()
        page.feed(request(base + "buy-iphone"))
        urls = sorted({urllib.parse.urljoin(base, link).split("?")[0].rstrip("/") for link in page.links
                       if re.fullmatch(re.escape(urllib.parse.urlsplit(base).path) + r"buy-iphone/iphone-[a-z0-9-]+/?",
                                       urllib.parse.urlsplit(urllib.parse.urljoin(base, link)).path)
                       and urllib.parse.urljoin(base, link).startswith(base)})
    except (AppleBlocked, ConnectionFailure):
        raise
    except MonitorError as exc:
        print(str(exc))
        urls = []
    chosen = select([(u, u.rsplit("/", 1)[-1]) for u in urls], "iPhone families") if urls else []
    if not chosen:
        chosen = [product_url(input("Paste the regional iPhone purchase-page URL: ").strip(), base)]
    products = {}
    for url in chosen:
        print(f"Loading variants from {url} ...")
        variants = variants_from_page(request(url))
        if variants:
            parts = select(sorted(variants.items(), key=lambda pair: pair[1]), "variants (model, storage and color)")
        else:
            print("Apple did not expose a variant catalog. Copy exact regional part numbers from the purchase page.")
            parts = [p.strip().upper() for p in input("Part numbers, separated by commas (including /A): ").split(",")]
            variants = {part: input(f"Display name for {part}: ").strip() for part in parts}
        for part in parts:
            if not PART.fullmatch(part):
                raise MonitorError("Invalid part number; use the complete regional Apple SKU including /A.")
            products[part] = {"part": part, "name": variants[part], "url": url}
    print("Finding nearby Apple Stores...")
    stores = {}
    for row in pickup(base, next(iter(products)), location=location):
        sid = row.get("storeNumber")
        if isinstance(sid, str) and STORE.fullmatch(sid):
            name = row.get("storeName", sid)
            details = " · ".join(str(x) for x in [name, row.get("city"), row.get("storeDistanceWithUnit")] if x)
            stores[sid] = (name, details)
    ids = select([(sid, row[1]) for sid, row in stores.items()], "stores")
    while True:
        try:
            interval = float(input("Minutes between completed checks [15, minimum 2]: ").strip() or "15")
            if math.isfinite(interval) and interval >= 2:
                break
        except ValueError:
            pass
        print("Enter a finite number of at least 2 minutes.")
    enabled = input("Enable notifications using your own ntfy topic? [Y/n]: ").strip().lower() not in ("n", "no")
    ntfy = {"enabled": enabled}
    if enabled:
        print("Use the topic you have already added in the ntfy app. Setup does not generate a topic or send a message.")
        server = input("ntfy HTTPS server [https://ntfy.sh]: ").strip() or "https://ntfy.sh"
        while True:
            topic = input("Existing topic name from your ntfy app (name only, not a URL): ").strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
                break
            print("Enter your existing topic name: 1-64 letters, digits, _ or -. It cannot be empty or a URL.")
        ntfy.update(server=server.rstrip("/"), topic=topic)
        print(f"Notifications will use your existing subscription: server {server}, topic {topic}.")
        print("For protected topics, set NTFY_TOKEN in your environment. It is never written to this configuration.")
    config = validate({"version": 1, "shop_url": base, "interval_minutes": interval,
                       "products": list(products.values()),
                       "stores": [{"id": sid, "name": stores[sid][0]} for sid in ids], "ntfy": ntfy})
    atomic_json(path, config)
    print(f"Configuration saved to {path}. Run the script again to start monitoring.")


def notify(config, product, store, quote):
    message = f"{product['name']}\n{store['name']} ({store['id']})\n{quote}\n{product['url']}"
    log("AVAILABLE: " + message.replace("\n", " | "))
    ntfy = config["ntfy"]
    if not ntfy["enabled"]:
        return True
    headers = {"Content-Type": "application/json; charset=utf-8"}
    token = os.environ.get("NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = {"topic": ntfy["topic"], "title": "iPhone available for pickup", "message": message,
               "priority": 4, "tags": ["iphone"], "click": product["url"]}
    try:
        request(ntfy["server"].rstrip("/"), data=json.dumps(payload).encode("utf-8"), headers=headers)
        return True
    except MonitorError as exc:
        log(f"ntfy delivery failed: {exc} Will retry only after availability is confirmed again.")
        return False


def status_for(rows, part, store_id):
    for row in rows:
        if row.get("storeNumber") != store_id:
            continue
        info = (row.get("partsAvailability") or {}).get(part)
        if not isinstance(info, dict):
            return None, ""
        status = info.get("pickupDisplay")
        quote = " ".join(html.unescape(str(info.get("storePickupQuote", ""))).split())
        if status == "available":
            return True, quote
        if status in ("unavailable", "ineligible"):
            return False, quote
        return None, ""
    return None, ""


class Monitor:
    def __init__(self, config, state_path):
        self.config, self.state_path = config, state_path
        identity = {key: config[key] for key in ("shop_url", "products", "stores", "ntfy")}
        self.identity = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.entries = {}
        if state_path.exists():
            state = read_json(state_path)
            if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("entries"), dict):
                raise MonitorError("Invalid state file. Restore it or remove it to reset alert history.")
            if state.get("identity") == self.identity:
                for key, value in state["entries"].items():
                    if (not isinstance(value, dict) or not isinstance(value.get("delivered"), bool)
                            or type(value.get("misses")) is not int or value["misses"] < 0):
                        raise MonitorError("Invalid alert history. Restore or remove the state file.")
                    self.entries[key] = value

    def save(self):
        atomic_json(self.state_path, {"version": 1, "identity": self.identity, "entries": self.entries})

    def cycle(self):
        successful = unknown = failed = available = 0
        blocked = False
        consecutive_errors = 0
        for product in self.config["products"]:
            for store in self.config["stores"]:
                key = product["part"] + "@" + store["id"]
                try:
                    rows = pickup(self.config["shop_url"], product["part"], store=store["id"])
                    status, quote = status_for(rows, product["part"], store["id"])
                    consecutive_errors = 0
                    if status is None:
                        unknown += 1
                        log(f"UNKNOWN: {product['name']} @ {store['name']}; Apple returned no explicit status.")
                    else:
                        successful += 1
                        if status:
                            available += 1
                            entry = self.entries.setdefault(key, {"misses": 0, "delivered": False})
                            entry["misses"] = 0
                            if not entry["delivered"]:
                                entry["delivered"] = notify(self.config, product, store, quote)
                                # Save immediately after delivery to limit duplicates after a restart.
                                self.save()
                        elif key in self.entries:
                            self.entries[key]["misses"] += 1
                            if self.entries[key]["misses"] >= 2:
                                del self.entries[key]
                except AppleBlocked as exc:
                    log(str(exc))
                    failed += 1
                    blocked = True
                    break
                except MonitorError as exc:
                    failed += 1
                    consecutive_errors += 1
                    log(f"CHECK FAILED: {product['part']} @ {store['id']}: {exc}")
                if consecutive_errors >= 5:
                    log("Five consecutive requests failed; stopping this round.")
                    break
                time.sleep(random.uniform(1.0, 2.0))
            if blocked or consecutive_errors >= 5:
                break
        self.save()
        log(f"Check complete: {available} available, {successful} verified, {unknown} unknown, {failed} failed requests.")
        return not (unknown or failed or blocked), blocked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true", help="create or replace configuration interactively, then exit")
    parser.add_argument("--config", type=Path, default=Path("config.json"), help="configuration file (default: ./config.json)")
    parser.add_argument("--state", type=Path, help="alert history file (default: <config stem>.state.json beside configuration)")
    parser.add_argument("--once", action="store_true", help="run one check; exit 0 if fully verified, 1 if incomplete")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    args.config = args.config.expanduser().resolve()
    if args.setup or not args.config.exists():
        if not sys.stdin.isatty():
            raise MonitorError("No interactive terminal. Run --setup in a terminal first, or supply an existing --config file.")
        setup(args.config)
        return 0
    config = validate(read_json(args.config))
    state_path = args.state.expanduser().resolve() if args.state else args.config.with_name(args.config.stem + ".state.json")
    if state_path == args.config:
        raise MonitorError("Configuration and state paths must be different.")
    monitor = Monitor(config, state_path)
    print(f"Apple Pickup Monitor {VERSION} · {len(config['products'])} variants · {len(config['stores'])} stores")
    print("Notifications: " + ("ntfy enabled" if config["ntfy"]["enabled"] else "terminal only"))
    print("One instance per configuration/state file. Press Ctrl+C to stop.")
    backoff = 0
    while True:
        ok, blocked = monitor.cycle()
        if args.once:
            return 0 if ok else 1
        backoff = 0 if ok else min(backoff + 1, 5)
        minutes = max(config["interval_minutes"], min(120, 2 ** backoff) if backoff else 0,
                      30 if blocked else 0)
        log(f"Next check in {minutes:g} minutes.")
        time.sleep(minutes * 60)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (MonitorError, OSError, ValueError, TypeError, AttributeError, EOFError, RecursionError) as exc:
        # Unexpected configuration shapes must not print ntfy credentials in a traceback.
        message = str(exc) if isinstance(exc, MonitorError) else "Cannot continue. Check configuration, file permissions and terminal input."
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
