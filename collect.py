import json, re, time, urllib.parse, datetime as dt, os
from concurrent.futures import ThreadPoolExecutor
import requests

# --- DoH-fallback ---
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _doh(host):
    for url in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
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

def load_prev_data(path="data.js"):
    if not os.path.exists(path):
        return {}
    try:
        raw = open(path, encoding="utf-8").read().strip()
        if raw.startswith("window.DATA="):
            raw = raw[len("window.DATA="):]
        if raw.endswith(";"):
            raw = raw[:-1]
        return json.loads(raw)
    except Exception as e:
        print(f"Не удалось прочитать прошлый {path}: {e}")
        return {}

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
        r = S.get(url, params=params, timeout=30)
        r.raise_for_status()
        for ev in r.json().get("items", []):
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
        r = S.get(url, timeout=60)
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.text)
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

def collect_gcal(st, d0, d1, prev_halls, prev_gen, now_str):
    tz = dt.timezone(dt.timedelta(hours=st.get("utc_offset", 0)))
    work = st.get("work", {"from": 9, "to": 21})
    halls = []
    for c in st["calendars"]:
        time.sleep(CFG.get("pause_sec", 0.3))
        prev_h = prev_halls.get(c["name"], {})
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
            halls.append({"name": c["name"], "days": days, "updated": now_str})
        except Exception as e:
            print(f"  ! ошибка: {c['name']}: {e}")
            old_days = prev_h.get("days", {})
            old_upd = (prev_h.get("updated") or prev_gen) if old_days else ""
            halls.append({"name": c["name"], "days": old_days, "updated": old_upd, "error": str(e)})
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

def collect_appevent(st, d0, d1, prev_halls, prev_gen, now_str):
    S = requests.Session()
    S.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    html_r = S.get(st["url"], timeout=30)
    html_r.raise_for_status()
    key = re.search(r"widget_key=([0-9a-f]{32})", html_r.text).group(1)
    cfg = ae_api(S, "/widget/api/widget", CFG.get("appevent_pause", 0.5), widget_key=key)["item"]
    cid = cfg["company_id"]
    halls_src = [h for h in cfg["halls"]
                 if not (h.get("is_dressing_room") and not st.get("include_dressing", True))]
    halls, pause = [], CFG.get("appevent_pause", 0.5)
    all_days = [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]

    for h in halls_src:
        prev_h = prev_halls.get(h["name"], {})
        prev_days = prev_h.get("days", {})
        has_cached = any("error" not in v for v in prev_days.values()) if prev_days else False
        step = h.get("calendar_step") or 30
        args = [(requests.Session(), key, cid, h["id"], day, pause) for day in all_days]

        days_data = {}
        first_err = None
        errors = 0
        print(f"  зал: {h['name']} (собираю {len(all_days)} дней, {WORKERS} параллельно)...", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(fetch_day, args))
        for day_iso, slots, err in results:
            if err:
                print(f"    ! {day_iso}: {err}")
                errors += 1
                if not first_err: first_err = str(err)
                if day_iso in prev_days and "error" not in prev_days[day_iso]:
                    days_data[day_iso] = prev_days[day_iso]
                else:
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
        print(f"  ✓ зал: {h['name']} ({busy_count} занятостей, {free_count} свободных окон"
              + (f", {errors} ошибок)" if errors else ")"))

        hall_obj = {"name": h["name"], "days": days_data}
        if errors == len(all_days):
            hall_obj["days"] = prev_days if has_cached else days_data
            hall_obj["updated"] = (prev_h.get("updated") or prev_gen) if has_cached else ""
            hall_obj["error"] = first_err
        elif errors > 0:
            hall_obj["updated"] = (prev_h.get("updated") or prev_gen) if has_cached else now_str
            hall_obj["error"] = f"не загружено дней: {errors} ({first_err})"
        else:
            hall_obj["updated"] = now_str
        halls.append(hall_obj)
    return halls

# ---------- сборка ----------
if __name__ == "__main__":
    t0 = time.time()
    today = dt.date.today()
    now_str = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    d0 = month_start(today, -CFG.get("months_back", 1))
    d1_full = month_start(today, CFG.get("months_forward", 2) + 1) - dt.timedelta(days=1)
    ae_days = CFG.get("appevent_days")
    d1_ae = min(d1_full, today + dt.timedelta(days=ae_days)) if ae_days else d1_full

    prev_data = load_prev_data("data.js")
    prev_gen = prev_data.get("generated", "")
    prev_studios = {s["name"]: s for s in prev_data.get("studios", []) if "name" in s}

    studios = []
    for i, st in enumerate(CFG["studios"]):
        if not st.get("enabled", True):
            print(f"[{i+1}/{len(CFG['studios'])}] Отключена: {st['name']}"); continue
        print(f"\n[{i+1}/{len(CFG['studios'])}] {st['name']} ({st.get('platform')})")
        d0_s, d1_s = (d0, d1_ae) if st.get("platform") == "appevent" else (d0, d1_full)
        prev_st = prev_studios.get(st["name"], {})
        prev_halls = {h["name"]: h for h in prev_st.get("halls", []) if "name" in h}
        try:
            halls = (collect_gcal(st, d0_s, d1_s, prev_halls, prev_gen, now_str)
                     if st.get("platform") == "gcal"
                     else collect_appevent(st, d0_s, d1_s, prev_halls, prev_gen, now_str))
            all_failed = bool(halls) and all("error" in h for h in halls)
            st_obj = {
                "id": i, "name": st["name"], "address": st.get("address", ""),
                "url": st.get("url", ""), "platform": st.get("platform"),
                "color": PAL[i % len(PAL)], "halls": halls,
                "updated": (prev_st.get("updated") or prev_gen) if all_failed else now_str
            }
            if all_failed:
                st_obj["error"] = halls[0]["error"]
            studios.append(st_obj)
            print(f"OK: {st['name']}")
        except Exception as e:
            print(f"ERR: {st['name']} - {e}")
            fallback_halls = []
            for h in prev_st.get("halls", []):
                hc = dict(h)
                if hc.get("days") and not hc.get("updated"):
                    hc["updated"] = prev_st.get("updated") or prev_gen
                hc["error"] = str(e)
                fallback_halls.append(hc)
            st_upd = prev_st.get("updated") or (prev_gen if fallback_halls else "")
            studios.append({
                "id": i, "name": st["name"], "address": st.get("address", ""),
                "url": st.get("url", ""), "platform": st.get("platform"),
                "color": PAL[i % len(PAL)], "halls": fallback_halls,
                "updated": st_upd, "error": str(e)
            })

    print(f"\nСборка за {time.time()-t0:.1f} с")
    data = {"generated": now_str, "today": today.isoformat(),
            "range": {"from": d0.isoformat(), "to": d1_full.isoformat()}, "studios": studios}
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(data, ensure_ascii=False) + ";")
    print("Сохранено: data.js")
