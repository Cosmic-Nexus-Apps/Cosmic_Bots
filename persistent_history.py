import os
import json
import re
import hashlib
from datetime import datetime, timezone

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "published_history.json")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[PERSISTENT HISTORY SAVE ERROR] {e}")

def normalize_title(title_str):
    if not title_str:
        return ""
    clean = re.sub(r'\W+', '', title_str.lower())
    if clean:
        return hashlib.md5(clean.encode('utf-8')).hexdigest()
    return ""

def is_published(item_id, title_str=""):
    history = load_history()
    now_ts = datetime.now(timezone.utc).timestamp()

    # 1. Check ID match
    if item_id in history:
        exp = history[item_id].get("expire_ts")
        if exp is None or exp > now_ts:
            return True

    # 2. Check normalized title MD5 hash match
    t_hash = normalize_title(title_str)
    if t_hash:
        key = f"title_{t_hash}"
        if key in history:
            exp = history[key].get("expire_ts")
            if exp is None or exp > now_ts:
                return True

    return False

def record_published(item_id, title_str="", ttl_hours=720):
    history = load_history()
    now_ts = datetime.now(timezone.utc).timestamp()
    expire_ts = now_ts + (ttl_hours * 3600) if ttl_hours else None

    entry = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "expire_ts": expire_ts
    }

    history[item_id] = entry

    t_hash = normalize_title(title_str)
    if t_hash:
        history[f"title_{t_hash}"] = entry

    # Cleanup expired entries from history dictionary
    keys_to_del = [k for k, v in history.items() if v.get("expire_ts") and v["expire_ts"] <= now_ts]
    for k in keys_to_del:
        del history[k]

    save_history(history)
