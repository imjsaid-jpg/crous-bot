import json, os, random, re, time
from urllib.parse import urlparse, parse_qs
import requests

SEARCH_URL = "https://trouverunlogement.lescrous.fr/tools/47/search?bounds=-4.5689169_48.4595521_-4.4278311_48.3572972&locationName=Brest+%2829200%29"
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

DUREE = 260      # secondes de surveillance par lancement
INTERVALLE = 25  # secondes entre deux checks
SEEN_FILE = "seen_logements.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json", "Content-Type": "application/json",
    "Origin": "https://trouverunlogement.lescrous.fr", "Referer": SEARCH_URL,
}

m = re.search(r"/tools/(?:flow/)?(\d+)/search", SEARCH_URL)
TOOL_ID = int(m.group(1))
b = parse_qs(urlparse(SEARCH_URL).query)["bounds"][0]
LON1, LAT1, LON2, LAT2 = map(float, b.split("_"))

def fetch():
    payload = {
        "idTool": TOOL_ID, "need_aggregation": False, "page": 1, "pageSize": 100,
        "sector": None, "occupationModes": [],
        "location": [{"lon": LON1, "lat": LAT1}, {"lon": LON2, "lat": LAT2}],
        "residence": None, "precision": 6, "equipment": [],
        "price": {"min": 0, "max": 10000000},
    }
    r = requests.post(f"https://trouverunlogement.lescrous.fr/api/fr/search/{TOOL_ID}",
                      headers=HEADERS, json=payload, timeout=15)
    r.raise_for_status()
    items = r.json().get("results", {}).get("items", [])
    out = {}
    for it in items:
        if it.get("id") is None: continue
        label = it.get("label") or "Logement"
        res = (it.get("residence") or {}).get("label", "")
        out[str(it["id"])] = f"{label} — {res}".strip(" —")
    return out

def telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": msg,
                            "disable_web_page_preview": True}, timeout=10)
    except Exception as e:
        print("Telegram KO:", e)

seen = set()
first = True
if os.path.exists(SEEN_FILE):
    seen = set(json.load(open(SEEN_FILE)))
    first = False

debut = time.time()
while time.time() - debut < DUREE:
    try:
        logs = fetch()
        if first:
            if logs:
                telegram(f"📋 {len(logs)} logement(s) déjà en ligne :\n"
                         + "\n".join(f"• {v}" for v in list(logs.values())[:15])
                         + f"\n👉 {SEARCH_URL}")
            else:
                telegram("🤖 Bot CROUS actif (cloud). Aucun logement pour l'instant, je veille.")
            seen = set(logs); first = False
        else:
            nouveaux = set(logs) - seen
            for _id in nouveaux:
                lien = f"https://trouverunlogement.lescrous.fr/tools/{TOOL_ID}/accommodations/{_id}"
                telegram(f"🚨 NOUVEAU LOGEMENT !\n{logs[_id]}\n👉 FONCE : {lien}")
            if nouveaux: seen |= nouveaux
        print(time.strftime("%H:%M:%S"), "-", len(logs), "en ligne")
    except Exception as e:
        print("Erreur:", e)
    time.sleep(INTERVALLE + random.uniform(0, 5))

json.dump(sorted(seen), open(SEEN_FILE, "w"))
