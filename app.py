"""Personalized Travel Itinerary Planner - Skill Wallet Capstone Project 4
Streamlit + SQLite. Run: streamlit run app.py  (demo mode works without any API key)
NOTE: itineraries are AREA-BASED optimized (activities grouped by area/day); distances are
straight-line estimates, not verified shortest-route results."""
import io, json, math, random, re, sqlite3, datetime as dt
import requests, pandas as pd, streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

DB, SLOTS = "trips.db", {"M": "Morning Sightseeing", "L": "Lunch", "A": "Afternoon Leisure", "E": "Evening Dining & Entertainment"}
LEVEL = {"Budget": 0.7, "Moderate": 1.0, "Luxury": 2.2}
PARTY = {"Solo": 1, "Couple": 2, "Family": 4, "Friends": 4}
STAY = {"Budget": 1500, "Moderate": 4000, "Luxury": 10000}   # INR per room per night (estimate)
MOVE = {"Budget": 400, "Moderate": 900, "Luxury": 2500}      # INR per day local transport (estimate)
DEFAULT_MODEL = "gemini-3.8-flash"                           # editable in sidebar; Google retires models often

# demo data: dest -> {vibes, months, base, tags, areas{name: (lat, lon, [(name, slot, INR pp, tags)])}}
DEST = {
 "Goa": {"vibes": ["Beach", "Urban"], "months": [11, 12, 1, 2, 3], "base": 3500, "tags": "food nightlife beach adventure", "areas": {
   "North Goa": (15.55, 73.76, [("Fort Aguada", "M", 300, "history outdoor"), ("Britto's Shack Seafood", "L", 900, "seafood food"), ("Baga Beach Time", "A", 500, "beach outdoor"), ("Tito's Lane Nightlife", "E", 1800, "nightlife")]),
   "South Goa": (15.01, 74.02, [("Palolem Kayaking", "M", 900, "adventure outdoor beach"), ("Vegetarian Thali House", "L", 400, "vegetarian food"), ("Cabo de Rama Fort", "A", 200, "history outdoor"), ("Beach Shack Dinner", "E", 1200, "seafood beach food")]),
   "Panjim & Old Goa": (15.50, 73.83, [("Basilica of Bom Jesus", "M", 0, "history culture"), ("Fontainhas Veg Cafe", "L", 500, "vegetarian cafe food"), ("Fontainhas Heritage Walk", "A", 0, "culture history"), ("Mandovi River Cruise", "E", 700, "nightlife entertainment")])}},
 "Jaipur": {"vibes": ["Cultural", "Urban"], "months": [10, 11, 12, 1, 2, 3], "base": 3000, "tags": "history food culture", "areas": {
   "Amer": (26.99, 75.85, [("Amer Fort", "M", 500, "history"), ("Dal Baati Thali", "L", 450, "vegetarian food"), ("Jal Mahal Stroll", "A", 0, "outdoor"), ("Cultural Dinner & Folk Show", "E", 1500, "culture entertainment food")]),
   "Old City": (26.92, 75.82, [("City Palace", "M", 700, "history museum"), ("LMB Restaurant", "L", 600, "vegetarian food"), ("Johri Bazaar Market", "A", 0, "market shopping"), ("Rooftop Dinner, Hawa Mahal View", "E", 1400, "food")]),
   "Nahargarh": (26.94, 75.81, [("Nahargarh Sunrise Trek", "M", 200, "outdoor adventure"), ("Tapri Chai & Cafe", "L", 350, "vegetarian cafe food"), ("Jantar Mantar", "A", 200, "museum history"), ("Rooftop Lounge Night", "E", 2000, "nightlife")])}},
 "Manali": {"vibes": ["Mountains"], "months": [3, 4, 5, 6, 10, 11, 12], "base": 3800, "tags": "adventure outdoor nature", "areas": {
   "Solang Valley": (32.32, 77.15, [("Paragliding", "M", 3000, "adventure outdoor"), ("Mountain Cafe Lunch", "L", 700, "cafe food"), ("Snow Point Visit", "A", 500, "outdoor"), ("Bonfire Dinner", "E", 1000, "food outdoor")]),
   "Old Manali": (32.26, 77.18, [("Hadimba Temple", "M", 50, "culture history"), ("Old Manali Vegetarian Cafe Hop", "L", 600, "vegetarian cafe food"), ("Mall Road Market", "A", 0, "market shopping"), ("Live Music Dinner", "E", 1200, "nightlife entertainment")]),
   "Naggar": (32.12, 77.13, [("Naggar Castle", "M", 100, "history museum"), ("Trout Lunch by the River", "L", 800, "seafood food"), ("Roerich Art Gallery", "A", 50, "museum culture"), ("Riverside Camp Dinner", "E", 900, "outdoor food")])}}}
GENERIC = [("Old town walking tour", "M", 300, "history culture outdoor"), ("Main museum visit", "M", 400, "museum history"), ("Local market lunch", "L", 500, "market food"), ("Vegetarian restaurant lunch", "L", 450, "vegetarian food"),
           ("Park or waterfront stroll", "A", 0, "outdoor"), ("Local craft market", "A", 0, "market shopping"), ("Street-food dinner crawl", "E", 800, "food"), ("Live music evening", "E", 1200, "nightlife entertainment")]

# ---------- logic ----------
def hav(a, b):
    p1, p2, dl = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))

def pick(items, slot, avoid=(), hint=""):
    pool = [i for i in items if i[1] == slot and i[0] not in avoid] or [i for i in items if i[1] == slot]
    if hint:
        words = [w for w in re.findall(r"[a-z]+", hint.lower()) if len(w) > 3]
        pool = [i for i in pool if any(w in (i[0] + " " + i[3]).lower() for w in words)] or pool
    return random.choice(pool) if pool else None

def slot_of(item, mult, ll=None):
    if item is None:
        return {"name": "Free time / explore locally", "cost": 0, "lat": ll[0] if ll else None, "lon": ll[1] if ll else None}
    return {"name": item[0], "cost": round(item[2] * mult), "lat": ll[0] if ll else None, "lon": ll[1] if ll else None}

def pool_for(dest, area=None):
    d = DEST.get(dest)
    if not d:
        return GENERIC, None
    if area and area in d["areas"]:
        return d["areas"][area][2], d["areas"][area][:2]
    return [i for a in d["areas"].values() for i in a[2]], None

def demo_plan(dest, days, pace, mult):
    d, plan = DEST.get(dest), []
    names = list(d["areas"]) if d else ["Central area", "Old town", "Nature outskirts"]
    for n in range(days):
        area = names[n % len(names)]
        items, ll = pool_for(dest, area) if d else (GENERIC, None)
        slots = {k: slot_of(pick(items, k), mult, ll) for k in SLOTS if not (pace == "Relaxed" and k == "A")}
        plan.append({"area": area + (" (revisit)" if n >= len(names) else ""), "slots": slots})
    return plan

def gemini(key, model, prompt):
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, timeout=90,
                      json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}})
    r.raise_for_status()
    return json.loads(re.sub(r"```json|```", "", r.json()["candidates"][0]["content"]["parts"][0]["text"]).strip())

def num(v, lo, hi):
    v = float(v)
    if not lo <= v <= hi: raise ValueError("out of range")
    return v

def check_slot(s):
    if not isinstance(s, dict) or not str(s.get("name", "")).strip(): raise ValueError("slot missing name")
    cost = max(0, int(float(s.get("cost", 0))))
    try: lat, lon = num(s["lat"], -90, 90), num(s["lon"], -180, 180)
    except Exception: lat = lon = None
    return {"name": str(s["name"])[:80], "cost": cost, "lat": lat, "lon": lon}

def validate_plan(data, days, pace):
    ds = data.get("days") if isinstance(data, dict) else None
    if not isinstance(ds, list) or len(ds) < days: raise ValueError("AI returned wrong number of days")
    out = []
    for d in ds[:days]:
        need = [k for k in SLOTS if not (pace == "Relaxed" and k == "A")]
        sl = d.get("slots", {})
        if any(k not in sl for k in need): raise ValueError("AI plan missing slots")
        out.append({"area": str(d.get("area", "Area"))[:50], "slots": {k: check_slot(sl[k]) for k in need}})
    return out

def ai_plan(key, model, dest, days, pace, budget, party, interests):
    p = (f"Plan a {days}-day trip to {dest} for {party} traveller(s), {budget} budget, {pace} pace, interests {interests}. One geographic area per day, "
         "no backtracking. Return JSON only: {\"days\":[{\"area\":str,\"slots\":{\"M\":{\"name\":str,\"cost\":int,\"lat\":num,\"lon\":num},\"L\":{...},\"A\":{...},\"E\":{...}}}]}. "
         "cost = total INR for the whole group; lat/lon real coordinates; M=morning sightseeing, L=lunch, A=afternoon leisure, E=evening dining & entertainment.")
    return validate_plan(gemini(key, model, p), days, pace)

def costs(trip):
    m, n = trip["meta"], len(trip["plan"])
    pax = PARTY[m["party"]]; f = DEST[trip["dest"]]["base"] / 3500 if trip["dest"] in DEST else 1.0
    act = sum(s["cost"] for d in trip["plan"] for s in d["slots"].values())
    stay = round(STAY[m["budget"]] * math.ceil(pax / 2) * max(n - 1, 0) * f)
    move = round(MOVE[m["budget"]] * (1 if pax <= 2 else 2) * n * f)
    return {"Activities & dining": act, "Accommodation": stay, "Local transport": move}

def day_km(day):
    pts = [(s["lat"], s["lon"]) for s in day["slots"].values() if s["lat"] is not None]
    return sum(hav(a, b) for a, b in zip(pts, pts[1:])) if len(pts) > 1 else None

def map_df(trip):
    rows = [{"lat": s["lat"], "lon": s["lon"]} for d in trip["plan"] for s in d["slots"].values() if s["lat"] is not None]
    return pd.DataFrame(rows)

def make_pdf(trip):
    buf, S = io.BytesIO(), getSampleStyleSheet()
    c, rate = costs(trip), trip["meta"]["rate"]
    el = [Paragraph(f"Travel Guide: {trip['dest']}", S["Title"]),
          Paragraph(f"{len(trip['plan'])} days | {trip['meta']['party']} | {trip['meta']['budget']} | Estimated total INR {sum(c.values()):,} (~USD {sum(c.values())/rate:,.0f} at {rate}/USD)", S["Normal"]), Spacer(1, 10)]
    for n, d in enumerate(trip["plan"], 1):
        el.append(Paragraph(f"Day {n} - {d['area']}", S["Heading2"]))
        t = Table([["Time", "Activity", "INR"]] + [[SLOTS[k], s["name"], f"{s['cost']:,}"] for k, s in d["slots"].items()], colWidths=[150, 230, 80])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .4, colors.grey)]))
        el += [t, Spacer(1, 8)]
    el.append(Paragraph("Budget breakdown (estimates)", S["Heading2"]))
    el += [Paragraph(f"{k}: INR {v:,}", S["Normal"]) for k, v in c.items()]
    el.append(Paragraph("Emergency checklist", S["Heading2"]))
    el += [Paragraph("[  ] " + x, S["Normal"]) for x in ["Police 112 | Ambulance 108 | Tourist helpline 1363", "ID/passport copies and hotel bookings", "Travel insurance details", "Offline maps downloaded", "Emergency contact saved offline"]]
    SimpleDocTemplate(buf, pagesize=A4).build(el)
    return buf.getvalue()

# ---------- SQLite ----------
def db():
    c = sqlite3.connect(DB); c.execute("CREATE TABLE IF NOT EXISTS trips(id INTEGER PRIMARY KEY, name TEXT, created TEXT, data TEXT)"); return c

# ---------- UI ----------
st.set_page_config("Travel Itinerary Planner", "🧭", layout="wide")
st.markdown("""<style>.hero{background:linear-gradient(120deg,#0f766e,#f59e0b);padding:1.3rem 2rem;border-radius:16px;color:#fff}.hero h1,.hero p{margin:0;color:#fff}
.card{border-left:5px solid #0f766e;background:#f0fdfa;padding:.6rem 1rem;border-radius:8px;margin:.3rem 0;color:#134e4a}</style>
<div class="hero"><h1>🧭 Personalized Travel Itinerary Planner</h1><p>Area-based itinerary optimization · budget tracking · SQLite trip storage · PDF guides</p></div>""", unsafe_allow_html=True)
ss = st.session_state; ss.setdefault("trip", None)

with st.sidebar:
    key = st.text_input("Gemini API key (optional)", type="password")
    model = st.text_input("Gemini model", DEFAULT_MODEL)
    st.caption("🟢 AI mode" if key else "🟡 Demo mode (Goa, Jaipur, Manali detailed; other cities generic)")
    vibe = st.selectbox("Vibe", ["Beach", "Mountains", "Cultural", "Urban"])
    dest_in = st.text_input("Destination (blank = recommend)", placeholder="e.g. Kerala, Mumbai, Paris")
    days = st.slider("Days", 1, 7, 3); start = st.date_input("Start date", dt.date.today() + dt.timedelta(days=30))
    budget = st.select_slider("Budget", list(LEVEL), "Moderate"); party = st.selectbox("Travel party", list(PARTY))
    pace = st.selectbox("Pace", ["Relaxed", "Moderate", "Fast-Paced"], 1)
    interests = st.multiselect("Interests", ["Food", "Adventure", "History", "Nightlife"], ["Food"])
    rate = st.number_input("INR per USD (estimate, editable)", 50.0, 150.0, 88.0)

t1, t2, t3, t4 = st.tabs(["🌍 Destination Recommender", "🗓️ Day-Wise Itinerary", "🎛️ Customize Activities", "💼 Trips & PDF Export"])

with t1:
    st.subheader("Top matches for your vibe, budget and season")
    recs = []
    if key:
        try:
            r = gemini(key, model, f"Recommend 3 destinations for vibe {vibe}, {budget} budget, month {start.strftime('%B')}, interests {interests}. JSON only: "
                       "{\"recs\":[{\"name\":str,\"why\":str,\"tags\":[str],\"inr_per_day_pp\":int}]}")["recs"][:3]
            recs = [(x["name"], x["why"], x["tags"], int(x["inr_per_day_pp"])) for x in r]
        except Exception as e:
            st.warning(f"AI recommendation failed ({e}); showing built-in matches.")
    if not recs:
        sc = sorted(DEST.items(), key=lambda kv: -((3 if vibe in kv[1]["vibes"] else 0) + (2 if start.month in kv[1]["months"] else 0) + sum(i.lower() in kv[1]["tags"] for i in interests)))
        recs = [(n, f"Fits {vibe} vibe; {'in season' if start.month in d['months'] else 'off-season'} for {start.strftime('%B')}.", d["vibes"], round(d["base"] * LEVEL[budget])) for n, d in sc[:3]]
    for n, why, tags, c in recs:
        st.markdown(f"<div class='card'><b>{n}</b> — ~INR {c:,}/day per person<br>{why}<br>{' '.join('`'+t+'`' for t in tags)}</div>", unsafe_allow_html=True)

with t2:
    dest = (dest_in.strip().title() if dest_in.strip() else recs[0][0]) if recs else "Goa"
    meta = dict(budget=budget, party=party, pace=pace, start=str(start), rate=rate, interests=interests)
    if st.button(f"✨ Generate itinerary for {dest}", type="primary"):
        mult = LEVEL[budget] * PARTY[party]
        try:
            plan, src = (ai_plan(key, model, dest, days, pace, budget, party, interests), "AI") if key else (demo_plan(dest, days, pace, mult), "demo")
        except Exception as e:
            st.warning(f"AI generation/validation failed ({e}); using demo mode."); plan, src = demo_plan(dest, days, pace, mult), "demo"
        meta["source"] = src; ss.trip = dict(dest=dest, plan=plan, meta=meta)
        if src == "demo" and dest not in DEST: st.info("Generic template used: add an API key for destination-specific plans.")
    T = ss.trip
    if T:
        run = 0
        for n, d in enumerate(T["plan"], 1):
            km = day_km(d)
            hdr = f"Day {n} · {d['area']} · {(dt.date.fromisoformat(T['meta']['start']) + dt.timedelta(days=n-1)).strftime('%a %d %b')}"
            with st.expander(hdr + (f" · ~{km:.0f} km straight-line, ~{km/25*60:.0f} min" if km else ""), expanded=True):
                for k, s in d["slots"].items():
                    run += s["cost"]; st.write(f"**{SLOTS[k]}** — {s['name']} · ₹{s['cost']:,} (${s['cost']/rate:,.0f}) · running activities ₹{run:,}")
        c = costs(T); cols = st.columns(4)
        for col, (k, v) in zip(cols, list(c.items()) + [("Estimated total", sum(c.values()))]):
            col.metric(k, f"₹{v:,}", f"${v/rate:,.0f}", delta_color="off")
        st.caption(f"Estimates only. Rate {rate} INR/USD. Plan source: {T['meta'].get('source')}. Distances are straight-line, not routed.")
        df = map_df(T)
        if len(df): st.map(df)
        else: st.caption("Map needs coordinates (available in AI mode).")
    else: st.info("Set preferences in the sidebar, then generate.")

with t3:
    T = ss.trip
    if not T: st.info("Generate an itinerary first.")
    else:
        n = st.selectbox("Day", range(1, len(T["plan"]) + 1)); day = T["plan"][n - 1]
        slot = st.selectbox("Slot", list(day["slots"]), format_func=lambda k: SLOTS[k])
        req = st.text_input("Change request", placeholder="vegetarian lunch / outdoor market instead of museum")
        mult = LEVEL[T["meta"]["budget"]] * PARTY[T["meta"]["party"]]; a, b = st.columns(2)
        if a.button("🔄 Swap this slot"):
            try:
                if key:
                    s = check_slot(gemini(key, model, f"In {T['dest']}, area {day['area']}, replace the {SLOTS[slot]} activity '{day['slots'][slot]['name']}'. Request: {req or 'something different'}. "
                                         "JSON only: {\"name\":str,\"cost\":int total INR for group,\"lat\":num,\"lon\":num}")); day["slots"][slot] = s
                else:
                    items, ll = pool_for(T["dest"], day["area"].replace(" (revisit)", ""))
                    day["slots"][slot] = slot_of(pick(items, slot, [day["slots"][slot]["name"]], req), mult, ll)
                st.success(f"Slot now: {day['slots'][slot]['name']}")
            except Exception as e: st.error(f"Swap failed, plan unchanged: {e}")
        if b.button("🔁 Regenerate whole day"):
            try:
                if key: T["plan"][n - 1] = ai_plan(key, model, T["dest"], 1, T["meta"]["pace"], T["meta"]["budget"], T["meta"]["party"], T["meta"]["interests"])[0]
                else:
                    items, ll = pool_for(T["dest"], day["area"].replace(" (revisit)", ""))
                    T["plan"][n - 1]["slots"] = {k: slot_of(pick(items, k, [s["name"] for s in day["slots"].values()]), mult, ll) for k in day["slots"]}
                st.success("Day regenerated; other days untouched.")
            except Exception as e: st.error(f"Regeneration failed, plan unchanged: {e}")

with t4:
    T = ss.trip
    if T:
        name = st.text_input("Trip name", f"{T['dest']} {T['meta']['start']}")
        c1, c2 = st.columns(2)
        if c1.button("💾 Save trip to SQLite"):
            with db() as c: c.execute("INSERT INTO trips(name,created,data) VALUES(?,?,?)", (name, dt.datetime.now().isoformat(timespec="seconds"), json.dumps(T)))
            st.success("Saved permanently to trips.db")
        c2.download_button("📄 Download PDF guide", make_pdf(T), f"{T['dest']}_itinerary.pdf", "application/pdf")
    st.subheader("Saved trips")
    with db() as c: rows = c.execute("SELECT id,name,created,data FROM trips ORDER BY id DESC").fetchall()
    for i, nm, cr, data in rows:
        t = json.loads(data); a, b, d_ = st.columns([4, 1, 1])
        a.markdown(f"<div class='card'><b>{nm}</b> · {len(t['plan'])} days · ₹{sum(costs(t).values()):,} · saved {cr}</div>", unsafe_allow_html=True)
        if b.button("Load", key=f"l{i}"): ss.trip = t; st.rerun()
        if d_.button("Delete", key=f"d{i}"):
            with db() as c: c.execute("DELETE FROM trips WHERE id=?", (i,))
            st.rerun()
    if not rows: st.caption("No saved trips yet.")
