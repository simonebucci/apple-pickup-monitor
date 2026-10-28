#!/usr/bin/env python3
"""Apple Store pickup monitor. Original monitoring logic with interactive configuration.
Python 3.10+, standard library only. Run --setup, then start without --once.
"""
import argparse
import http.client
import json
import os
import random
import re
import socket
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from pathlib import Path
import ssl
import configuration

VERSION = "1.1.0"
TZ = None
LOCATIONS, STORE_IDS, STORE_FILTER = [], [], []
PRODUCT_FILTER, EXTRA_PARTS = "", []
NORMAL_MINUTES, FAST_MINUTES = 15, 2
FAST_WINDOWS, HEARTBEAT_HOUR = [], 9
NTFY_TOPIC, NTFY_TOKEN = "", ""
NTFY_SERVER = "https://ntfy.sh"
BASE, BUY_PAGE, APPLE_HOST = "", "", "www.apple.com"
DISCOVERY_PAGES = []
PART_RE = re.compile(r"\b[A-Z0-9]{5,12}/A\b")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": BUY_PAGE,
    "X-Requested-With": "XMLHttpRequest",
    "Cookie": "as_sfa=MnxpdHxpdHx8aXRfSVR8Y29uc3VtZXJ8aW50ZXJuZXR8MHwwfDE",
}
DEFAULT_HEADERS = HEADERS.copy()

MIN_PAUSE = 30
DISCOVERY_EVERY = 6 * 3600
GRACE_CYCLES = 2
MAX_CONSECUTIVE_ERRORS = 5
PENDING_MAX_AGE = 2 * 3600

ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException)


def now_local() -> datetime:
    return datetime.now(TZ) if TZ else datetime.now()


def log(msg: str) -> None:
    print(f"[{now_local():%H:%M:%S}] {msg}", flush=True)


def clean(x) -> str:
    return " ".join(str(x).split())


def short(e: Exception) -> str:
    return f"{type(e).__name__}: {clean(e)}"[:140]


def pause() -> None:
    time.sleep(0.8 + random.random() * 0.7)


def network_ok() -> bool:
    try:
        socket.getaddrinfo(APPLE_HOST, 443)
        return True
    except OSError:
        return False


def next_interval() -> int:
    n = now_local()
    minutes = n.hour * 60 + n.minute
    for h1, m1, h2, m2 in FAST_WINDOWS:
        if h1 * 60 + m1 <= minutes < h2 * 60 + m2:
            return FAST_MINUTES * 60
    return NORMAL_MINUTES * 60



def tls_context():
    """Keep certificate verification enabled, including on macOS Python installs."""
    context = ssl.create_default_context()
    if sys.platform == "darwin" and not any(os.environ.get(key) for key in ("SSL_CERT_FILE", "SSL_CERT_DIR")):
        bundle = Path("/etc/ssl/cert.pem")
        if bundle.is_file():
            context.load_verify_locations(cafile=str(bundle))
    return context


def http_text(url, headers=None, data=None, timeout=15) -> str:
    req = urllib.request.Request(url, headers=headers or HEADERS, data=data)
    with urllib.request.urlopen(req, timeout=timeout, context=tls_context()) as r:
        return r.read().decode("utf-8", "replace")


def get_with_retry(url, attempts=2) -> str:
    last = None
    for i in range(attempts):
        try:
            return http_text(url)
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504, 541):
                break
        except ERRORS as e:
            last = e
        if i + 1 < attempts:
            time.sleep(2 + random.random() * 2)
    raise last


def send_ntfy(text: str, title: str, priority="high", tags="iphone,rotating_light") -> bool:
    if not NTFY_TOPIC:
        return True
    headers = {"Title": title, "Priority": priority, "Tags": tags, "Click": BUY_PAGE}
    if NTFY_TOKEN:
        headers["Authorization"] = "Bearer " + NTFY_TOKEN
    for i in range(3):
        try:
            http_text(f"{NTFY_SERVER}/{NTFY_TOPIC}", headers=headers, data=text.encode("utf-8"), timeout=10)
            return True
        except Exception as e:
            err = e
            time.sleep(2 * (i + 1))
    log(f"ntfy notification not delivered ({short(err)})")
    return False



def build_url(part: str, where) -> str:
    kind, value = where
    q = [("mts.0", "regular"), ("mts.1", "compact")]
    if kind == "location":
        q += [("searchNearby", "true"), ("cppart", "UNLOCKED/WW"), ("product", part),
              ("little", "false"), ("location", value)]
    else:
        q += [("product", part), ("store", value), ("cppart", "UNLOCKED/WW")]
    return BASE + "pickup-message-recommendations?" + urllib.parse.urlencode(q)


def parse_rows(raw: str, part: str) -> list:
    """Return [(part, title, store, available, quote)]. Empty rows mean no availability."""
    body = json.loads(raw).get("body")
    if not isinstance(body, dict):
        raise ValueError("response has no 'body' (error page or block?)")
    pm = (body.get("content") or {}).get("pickupMessage") or body.get("PickupMessage") or {}
    out = []
    for s in pm.get("stores") or []:
        store = clean(s.get("storeName", "?"))
        for p, info in (s.get("partsAvailability") or {}).items():
            title = clean(((info.get("messageTypes") or {}).get("regular") or {})
                          .get("storePickupProductTitle", p))
            out.append((p, title, store, info.get("pickupDisplay") == "available",
                        clean(info.get("storePickupQuote", ""))))

    if not any(r[3] for r in out) and re.search(r'"pickupDisplay"\s*:\s*"available"', raw):
        out.append((part, part, "one or more stores (check Apple)", True, ""))
    return out



class Monitor:
    def __init__(self):
        self.parts, self.parts_time = [], 0.0
        self.seen = {}
        self.fails, self.fail_since = 0, None
        self.pending = []
        self.logged = set()
        self.ok_cycles = 0
        self.heartbeat_day = None


    def notify(self, text, title, priority="high", tags="iphone,rotating_light", queue=True) -> None:
        print(f"\n>>> {title}: {text}\n", flush=True)
        if not send_ntfy(text, title, priority, tags) and queue:
            self.pending.append((text, title, time.time()))

    def flush_pending(self) -> None:
        keep = []
        for text, title, ts in self.pending:
            if time.time() - ts > PENDING_MAX_AGE:
                continue
            if not send_ntfy(text, title + " (delayed)"):
                keep.append((text, title, ts))
        self.pending = keep

    def log_once(self, msg: str) -> None:
        if msg not in self.logged:
            self.logged.add(msg)
            log(msg)


    def register_failure(self) -> None:
        self.fails += 1
        if self.fail_since is None:
            self.fail_since = time.time()
        if self.fails == 3:
            self.notify("Unable to read availability from Apple (3 consecutive checks failed). "
                        "Check the device network connection.", "iPhone monitor error",
                        tags="warning", queue=False)

    def register_ok(self) -> None:
        if self.fail_since is not None and self.fails >= 3:
            mins = int((time.time() - self.fail_since) / 60)
            self.notify(f"Monitoring resumed after about {mins} minutes of errors: during that period "
                        "availability could not be checked.", "iPhone monitoring resumed",
                        priority="default", tags="white_check_mark", queue=False)
        self.fails, self.fail_since = 0, None

    def heartbeat(self) -> None:
        n = now_local()
        if HEARTBEAT_HOUR is None or n.hour < HEARTBEAT_HOUR or self.heartbeat_day == n.date():
            return
        self.heartbeat_day = n.date()
        self.notify(f"Monitor active: {self.ok_cycles} successful checks since the last status message, "
                    f"last at {n:%H:%M}.", "iPhone monitor active",
                    priority="low", tags="white_check_mark", queue=False)
        self.ok_cycles = 0


    def discover(self) -> list:
        if self.parts and time.time() - self.parts_time < DISCOVERY_EVERY:
            return self.parts
        found, any_ok = set(EXTRA_PARTS) | set(self.parts), False
        for page in DISCOVERY_PAGES:
            try:
                found |= set(PART_RE.findall(get_with_retry(page)))
                any_ok = True
            except ERRORS as e:
                self.log_once(f"part-number discovery from {page.split('/')[-1]} failed ({short(e)}); using known parts")
        self.parts = sorted(found)
        if any_ok:
            self.parts_time = time.time()
            self.log_once(f"monitored part numbers: {len(self.parts)}")
        return self.parts


    def cycle(self) -> bool:
        if not network_ok():
            log("Network/DNS unavailable: check skipped (availability NOT checked)")
            self.register_failure()
            return False
        self.flush_pending()
        parts = self.discover()
        targets = [("location", x) for x in LOCATIONS] + [("store", x) for x in STORE_IDS]
        total = errors = consecutive = 0
        error_samples, aborted = [], False
        found = {}
        product = " ".join(PRODUCT_FILTER.split()).lower() if PRODUCT_FILTER else ""

        for part in parts:
            for where in targets:
                total += 1
                try:
                    rows = parse_rows(get_with_retry(build_url(part, where)), part)
                    consecutive = 0
                except ERRORS as e:
                    errors += 1
                    consecutive += 1
                    if len(error_samples) < 3:
                        error_samples.append(f"{part}@{where[1]}: {short(e)}")
                    if consecutive >= MAX_CONSECUTIVE_ERRORS:
                        aborted = True
                        break
                    pause()
                    continue
                for p, title, store, ok, quote in rows:
                    if not ok:
                        continue
                    if product and title != p and product not in title.lower():
                        self.log_once(f"available but different product (ignored): {title} @ {store}")
                        continue
                    if STORE_FILTER and not any(f.lower() in store.lower() for f in STORE_FILTER):
                        self.log_once(f"available but store outside selection (ignored): {store}")
                        continue
                    found[(p, store)] = (title, store, quote)
                pause()
            if aborted:
                break

        if errors == total or aborted:
            log(f"ERROR: {errors}/{total} requests failed, availability NOT checked "
                f"[{'; '.join(error_samples)}]")
            self.register_failure()
            return False

        self.register_ok()
        self.ok_cycles += 1
        new = [k for k in found if k not in self.seen]
        for k in found:
            self.seen[k] = 0
        if errors * 4 <= total:
            for k in list(self.seen):
                if k not in found:
                    self.seen[k] += 1
                    if self.seen[k] >= GRACE_CYCLES:
                        del self.seen[k]

        if new:
            by_title = {}
            for k in new:
                title, store, quote = found[k]
                by_title.setdefault(title, []).append(store + (f" ({quote})" if quote else ""))
            lines = [f"{t}: {', '.join(sorted(set(s)))}" for t, s in by_title.items()]
            self.notify("\n".join(lines[:8]), "iPhone AVAILABLE for pickup!")
        if found:
            log(f"available now: {sorted({v[0] + ' @ ' + v[1] for v in found.values()})}")
        else:
            log(f"No {PRODUCT_FILTER or 'selected iPhone'} available "
                f"({total - errors}/{total} requests successful, {len(parts)} variants)"
                + (f" [errors: {'; '.join(error_samples)}]" if errors else ""))
        self.heartbeat()
        return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Apple Pickup Monitor: original checks with guided configuration")
    ap.add_argument("--setup", action="store_true", help="configure shop, stores, models, interval and your existing ntfy topic")
    ap.add_argument("--config", type=Path, default=Path("config.json"), help="configuration file (default: ./config.json)")
    ap.add_argument("--once", action="store_true", help="run one round; exit 0 = successful, 1 = failed")
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    engine = sys.modules[__name__]
    config = configuration.load_configuration(a.config.expanduser().resolve(), engine, a.setup)
    if config is None:
        return
    profiles = configuration.apply_configuration(engine, config)
    monitors = [Monitor() for _ in profiles]
    print(f"Apple Pickup Monitor {VERSION} · original monitoring engine", flush=True)
    print(f"Nearby searches: {', '.join(LOCATIONS)}; direct stores: {', '.join(STORE_IDS)}", flush=True)
    if not NTFY_TOPIC:
        log("WARNING: ntfy disabled; notifications are shown in this terminal only.")
    else:
        print(f"ntfy destination: {NTFY_SERVER}/{NTFY_TOPIC}", flush=True)
    if a.once:
        results = []
        for profile, monitor in zip(profiles, monitors):
            configuration.apply_profile(engine, profile)
            results.append(monitor.cycle())
        sys.exit(0 if all(results) else 1)
    configuration.apply_profile(engine, profiles[0])
    if NTFY_TOPIC:
        w = FAST_WINDOWS[0] if FAST_WINDOWS else None
        extra = f", every {FAST_MINUTES} min from {w[0]:02d}:{w[1]:02d} to {w[2]:02d}:{w[3]:02d}" if w else ""
        monitors[0].notify(f"Monitoring started: checking every {NORMAL_MINUTES} min{extra}.",
                           "iPhone monitor active", priority="default", tags="white_check_mark", queue=False)
        for monitor in monitors:
            monitor.heartbeat_day = now_local().date()
    while True:
        start = time.time()
        for profile, monitor in zip(profiles, monitors):
            configuration.apply_profile(engine, profile)
            try:
                monitor.cycle()
            except KeyboardInterrupt:
                raise
            except Exception:
                log("Unexpected error, continuing: " + traceback.format_exc().strip().splitlines()[-1])
                monitor.register_failure()
        wait = max(next_interval() - (time.time() - start), MIN_PAUSE)
        log(f"Next check in {round(wait / 60)} min")
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException) as exc:

        print("Error: " + short(exc), file=sys.stderr)
        sys.exit(1)
