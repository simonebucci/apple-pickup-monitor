"""Interactive configuration only. Inventory decisions remain in check_iphone_duo.py."""
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.parse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PART = re.compile(r"[A-Z0-9]{5,12}/A")
STORE = re.compile(r"R\d{3,6}")
_engine = None

class MonitorError(ValueError):
    pass

def get_with_retry(url):
    return _engine.get_with_retry(url)

def configure_shop(engine, base):
    engine.HEADERS = engine.DEFAULT_HEADERS.copy()
    engine.BASE = base
    engine.APPLE_HOST = urllib.parse.urlsplit(base).hostname
    engine.HEADERS["Referer"] = base + "buy-iphone"
    if base != "https://www.apple.com/it/shop/":
        engine.HEADERS.pop("Cookie", None)
        engine.HEADERS["Accept-Language"] = "en-US,en;q=0.9"

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
    raw = get_with_retry(base + "pickup-message-recommendations?" + urllib.parse.urlencode(query))
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
    heartbeat_hour = config.get("heartbeat_hour", 9)
    if heartbeat_hour is not None and (type(heartbeat_hour) is not int or not 0 <= heartbeat_hour <= 23):
        raise MonitorError("heartbeat_hour must be an hour from 0 to 23, or null to disable it.")
    fast = config.get("fast_schedule")
    if fast is not None:
        if (not isinstance(fast, dict) or type(fast.get("minutes")) not in (int, float)
                or not math.isfinite(fast["minutes"]) or fast["minutes"] < 2
                or not isinstance(fast.get("windows"), list)):
            raise MonitorError("fast_schedule needs minutes >= 2 and a list of [start_hour, start_minute, end_hour, end_minute] windows.")
        for window in fast["windows"]:
            if (not isinstance(window, list) or len(window) != 4 or any(type(n) is not int for n in window)
                    or not 0 <= window[0] <= 23 or not 0 <= window[2] <= 23
                    or not 0 <= window[1] <= 59 or not 0 <= window[3] <= 59
                    or window[0] * 60 + window[1] >= window[2] * 60 + window[3]):
                raise MonitorError("Invalid fast_schedule window; use a same-day start time before its end time.")
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
    configure_shop(_engine, base)
    location = input("Nearby postal codes/locations (comma-separated if more than one): ").strip()
    locations = list(dict.fromkeys(x.strip() for x in location.split(",") if x.strip()))
    if not locations:
        raise MonitorError("A location is required to find nearby stores.")
    print("Loading current iPhone families...")
    try:
        page = PageData()
        page.feed(get_with_retry(base + "buy-iphone"))
        urls = sorted({urllib.parse.urljoin(base, link).split("?")[0].rstrip("/") for link in page.links
                       if re.fullmatch(re.escape(urllib.parse.urlsplit(base).path) + r"buy-iphone/iphone-[a-z0-9-]+/?",
                                       urllib.parse.urlsplit(urllib.parse.urljoin(base, link)).path)
                       and urllib.parse.urljoin(base, link).startswith(base)})
    except OSError:
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
        variants = variants_from_page(get_with_retry(url))
        print("As in the original monitor, Apple may also return available alternatives from the same family.")
        if variants:
            parts = select(sorted(variants.items(), key=lambda pair: pair[1]), "variants to query (model, storage and color)")
        else:
            print("Apple did not expose a variant catalog. Copy exact regional part numbers from the purchase page.")
            parts = [p.strip().upper() for p in input("Part numbers, separated by commas (including /A): ").split(",")]
            variants = {part: input(f"Display name for {part}: ").strip() for part in parts}
        for part in parts:
            if not PART.fullmatch(part):
                raise MonitorError("Invalid part number; use the complete regional Apple SKU including /A.")
            products[part] = {"part": part, "name": variants[part], "url": url}
    print("Finding nearby Apple Stores...")
    stores, store_postcodes, store_timezones = {}, {}, {}
    for location_value in locations:
        for row in pickup(base, next(iter(products)), location=location_value):
            sid = row.get("storeNumber")
            if isinstance(sid, str) and STORE.fullmatch(sid):
                name = row.get("storeName", sid)
                details = " · ".join(str(x) for x in [name, row.get("city"), row.get("storeDistanceWithUnit")] if x)
                stores[sid] = (name, details)
                store_postcodes[sid] = (row.get("address") or {}).get("postalCode")
                store_timezones[sid] = (row.get("retailStore") or {}).get("timezone")
    ids = select([(sid, row[1]) for sid, row in stores.items()], "stores")
    while True:
        try:
            interval = float(input("Minutes between checks [15, minimum 2]: ").strip() or "15")
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
    locations = list(dict.fromkeys(locations + [str(store_postcodes[sid]) for sid in ids if store_postcodes[sid]]))
    config = validate({"version": 1, "shop_url": base, "interval_minutes": interval,
                       "locations": locations, "timezone": store_timezones.get(ids[0]),
                       "products": list(products.values()),
                       "stores": [{"id": sid, "name": stores[sid][0]} for sid in ids], "ntfy": ntfy})
    atomic_json(path, config)
    print(f"Configuration saved to {path}. Run the script again to start monitoring.")

def load_configuration(path, engine, setup_requested=False):
    global _engine
    _engine = engine
    if setup_requested or not path.exists():
        if not sys.stdin.isatty():
            raise MonitorError("Run --setup in an interactive terminal before starting the background monitor.")
        setup(path)
        return None
    config = validate(read_json(path))
    if not config.get("locations"):
        if not sys.stdin.isatty():
            raise MonitorError("The previous configuration omitted postal-code searches. Run --setup in a terminal to restore them.")
        answer = input("Restore original nearby searches: enter your postal code/location (comma-separated for several): ")
        config["locations"] = list(dict.fromkeys(x.strip() for x in answer.split(",") if x.strip()))
        if not config["locations"]:
            raise MonitorError("At least one postal code/location is required for the original monitoring logic.")
        atomic_json(path, config)
    if not isinstance(config["locations"], list) or any(not isinstance(x, str) or not x.strip() for x in config["locations"]):
        raise MonitorError("locations must be a non-empty list of postal-code/location strings.")
    return config


def apply_configuration(engine, config):
    configure_shop(engine, config["shop_url"])
    engine.LOCATIONS = list(config["locations"])
    engine.STORE_IDS = [store["id"] for store in config["stores"]]
    engine.STORE_FILTER = [store["name"] for store in config["stores"]]
    engine.NORMAL_MINUTES = config["interval_minutes"]
    fast = config.get("fast_schedule") or {}
    engine.FAST_MINUTES = fast.get("minutes", 2)
    engine.FAST_WINDOWS = fast.get("windows", [])
    engine.HEARTBEAT_HOUR = config.get("heartbeat_hour", 9)
    engine.TZ = None
    if config.get("timezone"):
        try:
            engine.TZ = ZoneInfo(config["timezone"])
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            engine.log("Configured time zone unavailable; using this computer's local time.")
    ntfy = config["ntfy"]
    engine.NTFY_SERVER = ntfy.get("server", "https://ntfy.sh").rstrip("/")
    engine.NTFY_TOPIC = ntfy.get("topic", "") if ntfy["enabled"] else ""
    engine.NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "").strip()
    profiles = {}
    for product in config["products"]:
        suffix = product["url"].split("buy-iphone/", 1)[1]
        family = suffix.split("/", 1)[0]
        url = config["shop_url"] + "buy-iphone/" + family
        profile = profiles.setdefault(url, {"url": url, "parts": [], "pages": [],
                                           "filter": family.removeprefix("iphone-").replace("-", " "),
                                           "models": []})
        model = re.split(r"\s+\d+(?:[.,]\d+)?\s*(?:GB|TB)\b", product["name"], maxsplit=1, flags=re.IGNORECASE)[0]
        if model.lower().startswith("iphone ") and model != product["name"]:
            profile["models"].append(model[7:].lower().strip())
        profile["parts"].append(product["part"])
        if product["url"] not in profile["pages"]:
            profile["pages"].append(product["url"])
    for profile in profiles.values():
        if len(profile["models"]) == len(profile["parts"]):
            common = os.path.commonprefix(profile["models"]).strip()
            if common:
                profile["filter"] = common
    return list(profiles.values())


def apply_profile(engine, profile):
    engine.BUY_PAGE = profile["url"]
    engine.HEADERS["Referer"] = engine.BUY_PAGE
    engine.PRODUCT_FILTER = profile["filter"]
    engine.EXTRA_PARTS = profile["parts"]
    engine.DISCOVERY_PAGES = list(dict.fromkeys([profile["url"]] + profile["pages"]))
    engine.PART_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in profile["parts"]) + r")\b")
