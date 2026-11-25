import json, re, time, urllib.parse, datetime as dt, os
from concurrent.futures import ThreadPoolExecutor
import requests

# --- DoH-fallback ---
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _doh(host):
    for url in ("https://cloudflare-dns.com/dns-query","https://dns.google/resolve"):
        try:
            r = requests.get(url, params={"name": host, "type": "A"},
                             headers={"Accept": "application/dns-json"}, timeout=5)
            for a in r.json().get("Answer", []):
                if a.get("type") == 1 and a.get("data"): return a["data"]
        except Exception: pass
    return None
def _gai(host, port, family=0, type=0, proto=0, flags=0):
    try: return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except _socket.gaierror:
        ip = _doh(host)
        if ip: return _orig_getaddrinfo(ip, port, family, type, proto, flags)
        raise
_socket.getaddrinfo = _gai

CFG = json.load(open("config.json", encoding="utf-8"))
PAL = ["#dd2590", "#2e90fa", "#12b76a", "#7a5af8", "#f79009", "#06aed4", "#ee46bc", "#4e5ba6"]
WORKERS = int(CFG.get("workers", 10))

def month_start(d, shift):
    y, m = divmod(d.year * 12 + d.month - 1 + shift, 12)
    return dt.date(y, m + 1, 1)

def to_min(t): return int(t[:2]) * 60 + int(t[3:])

def complement(busy, w0, w1):
    res, cur = [], w0
    for a, b in sorted(busy):
        if b <= cur: continue
        if a > cur and cur < w1: res.append([cur, min(a, w1)])
        cur = max(cur, b)
        if cur >= w1: break
    if cur < w1: res.append([cur, w1])
    return [{"s": a, "e": b} for a, b in res if b > a]

def merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]: out[-1][1] = max(out[-1][1], b)
        else: out.append([a, b])
    return out

# ---------- Google Calendar ----------
def gcal_events(src, d0, d1, tz):
    S = requests.Session()
    S.headers.update({"User-Agent": "Mozilla/5.0"})
    key, out = (CFG.get("gcal_api_key", "") or os.environ.get("GCAL_API_KEY", "")), []
    if key:
        url = "https://www.googleapis.com/calendar/v3/calendars/" + urllib.parse.quote(src, safe="") + "/events"
        params = {"key": key, "singleEvents": "true", "orderBy": "startTime", "maxResults": 2500,
                  "timeMin": dt.datetime.combine(d0, dt.time(), tz).isoformat(),
                  "timeMax": dt.datetime.combine(d1 + dt.timedelta(days=1), dt.time(), tz).isoformat()}
        for ev in S.get(url, params=params, timeout=30).json().get("items", []):
            if ev.get("status") == "cancelled" or ev.get("transparency") == "transparent": continue
            a, b = ev["start"], ev.get("end", {})
            if "dateTime" in a:
                a = dt.datetime.fromisoformat(a["dateTime"].replace("Z", "+00:00")).astimezone(tz)
                b = dt.datetime.fromisoformat(b["dateTime"].replace("Z", "+00:00")).astimezone(tz)
            else:
                a = dt.datetime.combine(dt.date.fromisoformat(a["date"]), dt.time(), tz)
                b = dt.datetime.combine(dt.date.fromisoformat(b["date"]), dt.time(), tz)
            out.append((a, b, ev.get("summary", "занято")))
    else:
        import icalendar, recurring_ical_events
        url = "https://calendar.google.com/calendar/ical/" + urllib.parse.quote(src, safe="") + "/public/basic.ics"
        cal = icalendar.Calendar.from_ical(S.get(url, timeout=60).text)
        for ev in recurring_ical_events.of(cal).between(d0, d1 + dt.timedelta(days=1)):
            if str(ev.get("STATUS")) == "CANCELLED" or str(ev.get("TRANSP")) == "TRANSPARENT": continue
            a = ev["DTSTART"].dt
            b = ev["DTEND"].dt if ev.get("DTEND") else None
            if not isinstance(a, dt.datetime):
                a = dt.datetime.combine(a, dt.time(), tz)
                b = dt.datetime.combine(b, dt.time(), tz) if b else a + dt.timedelta(days=1)
            else:
                a, b = a.astimezone(tz), (b.astimezone(tz) if b else a + dt.timedelta(hours=1))
            out.append((a, b, str(ev.get("SUMMARY", "занято"))))
    return out

def split_days(a, b, title):
    if b <= a: b = a + dt.timedelta(minutes=30)
    out, d, last = [], a.date(), (b - dt.timedelta(seconds=1)).date()
    while d <= last:
        day0 = dt.datetime.combine(d, dt.time(), a.tzinfo)
        day1 = day0 + dt.timedelta(days=1)
        s, e = max(a, day0), min(b, day1)
        out.append({"d": d.isoformat(), "s": s.hour * 60 + s.minute,
                    "e": 1440 if e >= day1 else e.hour * 60 + e.minute, "t": title})
        d += dt.timedelta(days=1)
    return out

def collect_gcal(st, d0, d1):
    tz = dt.timezone(dt.timedelta(hours=st.get("utc_offset", 0)))
    work = st.get("work", {"from": 9, "to": 21})
    halls = []
    for c in st["calendars"]:
        time.sleep(CFG.get("pause_sec", 0.3))
        try:
            evs = gcal_events(c["src"], d0, d1, tz)
            segs = []
            for a, b, t in evs: segs += split_days(a, b, t)
            days, busy_count, free_count = {}, 0, 0
            for i in range((d1 - d0).days + 1):
                day = (d0 + dt.timedelta(days=i)).isoformat()
                ev = sorted([e for e in segs if e["d"] == day], key=lambda e: e["s"])
                busy = [{"s": e["s"], "e": e["e"], "t": e["t"]} for e in ev]
                free = complement([[e["s"], e["e"]] for e in ev], work["from"] * 60, work["to"] * 60)
                days[day] = {"busy": busy, "free": free}
                busy_count += len(busy); free_count += len(free)
            print(f"  ✓ календарь: {c['name']} ({busy_count} занятостей, {free_count} свободных окон)")
            halls.append({"name": c["name"], "days": days})
        except Exception as e:
            print(f"  ! ошибка: {c['name']}: {e}")
            halls.append({"name": c["name"], "days": {}, "error": str(e)})
    return halls

# ---------- AppEvent (freetimes с параллелизмом) ----------
def ae_api(S, path, pause, **p):
    time.sleep(pause / WORKERS)
    r = S.get("https://appevent.ru" + path, params=p, timeout=45)
    r.raise_for_status()
    return r.json()

def fetch_day(args):
    S, key, cid, hall_id, day_iso, pause = args
    try:
        ft = ae_api(S, "/widget/api/event/freetimes", pause, widget_key=key, date=day_iso,
                    time="", duration=60, order_type="", photosession_id="", guest_count=0,
                    hall_id=hall_id, client_id="", company_id=cid)
        return day_iso, ft.get("free_times", []), None
    except Exception as e:
        return day_iso, [], e

def collect_appevent(st, d0, d1):
    S = requests.Session()
    S.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    html = S.get(st["url"], timeout=30).text
    key = re.search(r"widget_key=([0-9a-f]{32})", html).group(1)
    cfg = ae_api(S, "/widget/api/widget", CFG.get("appevent_pause", 0.5), widget_key=key)["item"]
    cid = cfg["company_id"]
    halls_src = [h for h in cfg["halls"]
                 if not (h.get("is_dressing_room") and not st.get("include_dressing", True))]
    halls, pause = [], CFG.get("appevent_pause", 0.5)
    all_days = [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]

    for h in halls_src:
        step = h.get("calendar_step") or 30
        args = [(requests.Session(), key, cid, h["id"], day, pause) for day in all_days]

        days_data = {}
        print(f"  зал: {h['name']} (собираю {len(all_days)} дней, {WORKERS} параллельно)…", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(fetch_day, args))
        for day_iso, slots, err in results:
            if err:
                print(f"    ! {day_iso}: {err}")
                days_data[day_iso] = {"busy": [], "free": [], "error": str(err)}
                continue
            if not slots:
                days_data[day_iso] = {"busy": [], "free": []}
                continue
            base = to_min(slots[0]["value"])
            busy, free, cur = [], [], None
            for j, s in enumerate(slots):
                m = base + j * step
                ok = s["status"] == "free" and not s["blocked"] and not s["error"]
                kind = "free" if ok else "busy"
                if cur and cur[0] == kind:
                    cur[2] = m + step; cur[3].add(s["status"])
                else:
                    if cur: (free if cur[0] == "free" else busy).append(cur)
                    cur = [kind, m, m + step, {s["status"]}]
            if cur: (free if cur[0] == "free" else busy).append(cur)
            days_data[day_iso] = {
                "busy": [{"s": a, "e": b,
                          "t": "бронь" if "booked" in st_ else ("заявка" if st_ & {"request", "finished"} else "занято")}
                         for k, a, b, st_ in busy],
                "free": [{"s": a, "e": b} for k, a, b, _ in free]}

        busy_count = sum(len(d.get("busy", [])) for d in days_data.values())
        free_count = sum(len(d.get("free", [])) for d in days_data.values())
        errors = sum(1 for d in days_data.values() if "error" in d)
        print(f"  ✓ зал: {h['name']} ({busy_count} занятостей, {free_count} свободных окон"
              + (f", {errors} ошибок)" if errors else ")"))
        halls.append({"name": h["name"], "days": days_data})
    return halls

# ---------- сборка ----------
if __name__ == "__main__":
    t0 = time.time()
    today = dt.date.today()
    d0 = month_start(today, -CFG.get("months_back", 1))
    d1_full = month_start(today, CFG.get("months_forward", 2) + 1) - dt.timedelta(days=1)
    ae_days = CFG.get("appevent_days")
    d1_ae = min(d1_full, today + dt.timedelta(days=ae_days)) if ae_days else d1_full

    studios = []
    for i, st in enumerate(CFG["studios"]):
        if not st.get("enabled", True):
            print(f"[{i+1}/{len(CFG['studios'])}] Отключена: {st['name']}"); continue
        print(f"\n[{i+1}/{len(CFG['studios'])}] {st['name']} ({st.get('platform')})")
        d0_s, d1_s = (d0, d1_ae) if st.get("platform") == "appevent" else (d0, d1_full)
        try:
            halls = collect_gcal(st, d0_s, d1_s) if st.get("platform") == "gcal" else collect_appevent(st, d0_s, d1_s)
            studios.append({"id": i, "name": st["name"], "address": st.get("address", ""),
                            "url": st.get("url", ""), "platform": st.get("platform"),
                            "color": PAL[i % len(PAL)], "halls": halls})
            print(f"OK: {st['name']}")
        except Exception as e:
            print(f"ERR: {st['name']} — {e}")
            studios.append({"id": i, "name": st["name"], "address": st.get("address", ""),
                            "url": st.get("url", ""), "color": PAL[i % len(PAL)], "halls": [], "error": str(e)})

    print(f"\nСборка за {time.time()-t0:.1f} с")
    data = {"generated": dt.datetime.now().strftime("%d.%m.%Y %H:%M"), "today": today.isoformat(),
            "range": {"from": d0.isoformat(), "to": d1_full.isoformat()}, "studios": studios}
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(data, ensure_ascii=False) + ";")
    print("Сохранено: data.js")
