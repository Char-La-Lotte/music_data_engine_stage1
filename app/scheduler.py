import json
import os
import random
from datetime import datetime
from .database import get_conn


def get_settings() -> dict:
    with get_conn() as conn:
        rows = dict(conn.execute("SELECT key, value FROM settings WHERE key IN ('mode', 'slots')").fetchall())
    mode = rows.get("mode", "rotation")
    try:
        slots = json.loads(rows.get("slots", "[]"))
    except Exception:
        slots = []
    return {"mode": mode, "slots": slots}


def save_settings(data: dict) -> dict:
    with get_conn() as conn:
        if "mode" in data and data["mode"] in ("rotation", "random", "category"):
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('mode', ?)", (data["mode"],))
        if "slots" in data:
            slots_val = data["slots"]
            if not isinstance(slots_val, str):
                slots_val = json.dumps(slots_val, ensure_ascii=False)
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('slots', ?)", (slots_val,))
    return get_settings()


def ready_videos() -> list[dict]:
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM music_videos WHERE rights_status='licensed' AND enabled=1 AND playback_source!=''"
        )]
    ready = []
    for r in rows:
        path = r["playback_source"].strip()
        if path and os.path.isfile(path):
            r["code"] = f"#{r['id']}"
            r["url"] = f"/media/{r['id']}"
            ready.append(r)
    return ready


def _is_vi(v: dict) -> bool:
    return v.get("language") == "vi" or v.get("category") == "V-Pop"


def pick_next(exclude: list[int] | None = None) -> dict | None:
    if exclude is None:
        exclude = []

    # 1. Hàng đợi (queue.played=0) luôn ưu tiên nếu video còn ready
    with get_conn() as conn:
        q_rows = [dict(r) for r in conn.execute(
            "SELECT id AS queue_id, video_id FROM queue WHERE played=0 ORDER BY id ASC"
        )]
        for q in q_rows:
            vid = q["video_id"]
            row = conn.execute(
                "SELECT * FROM music_videos WHERE id=? AND rights_status='licensed' AND enabled=1 AND playback_source!=''",
                (vid,)
            ).fetchone()
            if row:
                d = dict(row)
                if os.path.isfile(d["playback_source"]):
                    d["queue_id"] = q["queue_id"]
                    d["code"] = f"#{d['id']}"
                    d["url"] = f"/media/{d['id']}"
                    return d
                else:
                    conn.execute("UPDATE queue SET played=1 WHERE id=?", (q["queue_id"],))
            else:
                conn.execute("UPDATE queue SET played=1 WHERE id=?", (q["queue_id"],))

    # 2. Lấy toàn bộ video ready
    pool = ready_videos()
    if not pool:
        return None

    # Chống trùng: loại min(10, số_ready - 1) bài gần nhất trong play_history và các id trong exclude
    limit = min(10, max(0, len(pool) - 1))
    with get_conn() as conn:
        recent_ids = [r[0] for r in conn.execute(
            "SELECT video_id FROM play_history ORDER BY id DESC LIMIT ?", (limit,)
        )]

    excluded_set = set(exclude) | set(recent_ids)
    candidates = [v for v in pool if v["id"] not in excluded_set]

    # Nới lỏng nếu rỗng
    if not candidates:
        candidates = [v for v in pool if v["id"] not in set(exclude)]
    if not candidates:
        candidates = list(pool)

    # 3. Áp dụng chế độ phát (mode)
    settings = get_settings()
    mode = settings.get("mode", "rotation")

    if mode == "rotation":
        with get_conn() as conn:
            last = conn.execute(
                "SELECT m.language, m.category FROM play_history p JOIN music_videos m ON p.video_id=m.id ORDER BY p.id DESC LIMIT 1"
            ).fetchone()
        if last:
            last_was_vi = _is_vi(dict(last))
            matched = [v for v in candidates if _is_vi(v) != last_was_vi]
            if matched:
                candidates = matched

    elif mode == "category":
        slots = settings.get("slots", [])
        now_hm = datetime.now().strftime("%H:%M")
        target_cat = None
        for s in slots:
            st = s.get("start", "")
            en = s.get("end", "")
            cat = s.get("category", "")
            if not st or not en or not cat:
                continue
            if st <= en:
                if st <= now_hm <= en:
                    target_cat = cat
                    break
            else:  # qua nửa đêm
                if now_hm >= st or now_hm <= en:
                    target_cat = cat
                    break
        if target_cat:
            matched = [v for v in candidates if v.get("category") == target_cat]
            if matched:
                candidates = matched

    # 4. Chọn ngẫu nhiên trong pool còn lại
    chosen = dict(random.choice(candidates))
    chosen["code"] = f"#{chosen['id']}"
    chosen["url"] = f"/media/{chosen['id']}"
    return chosen
