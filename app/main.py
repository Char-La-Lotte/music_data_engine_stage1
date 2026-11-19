import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import scheduler, services
from .broadcast import bc
from .config import STATIC_DIR, YOUTUBE_API_KEY, BASE_DIR
from .database import get_conn, init_db
from .tiktok_adapter import tiktok_adapter
from .voting_engine import voting_engine

app = FastAPI(title="TikTok iTV – Music Data Engine")
RIGHTS = {"pending", "licensed", "blocked"}


@app.on_event("startup")
def _startup():
    init_db()


# ----------------- PYDANTIC SCHEMAS -----------------
class VideoUpdate(BaseModel):
    rights_status: str | None = None
    playback_source: str | None = None
    enabled: bool | None = None
    title: str | None = None
    artist: str | None = None
    category: str | None = None


class CleanIn(BaseModel):
    action: str = "delete"


class KeywordIn(BaseModel):
    keyword: str


class DiscoverIn(BaseModel):
    keyword: str | None = None
    max_results: int = 25


class QueueIn(BaseModel):
    video_id: int


class BroadcastSettingsIn(BaseModel):
    mode: str | None = None
    slots: list | None = None


class TickerSpeedIn(BaseModel):
    speed: int


class VotingToggleIn(BaseModel):
    enabled: bool


class SimCommentIn(BaseModel):
    user_id: str | None = "viewer_1"
    user_name: str | None = "Khán giả"
    text: str


class SimGiftIn(BaseModel):
    user_id: str | None = "vip_viewer"
    user_name: str | None = "Fan Cứng"
    gift_name: str = "Hoa hồng"
    diamonds: int = 1
    repeat: int = 1
    video_id: int | None = None


# ----------------- MEDIA & OBS OVERLAY -----------------
@app.get("/media/{vid}")
def stream_media(vid: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT playback_source, rights_status, enabled FROM music_videos WHERE id=?", (vid,)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Không tìm thấy video")
    if row["rights_status"] != "licensed" or not row["enabled"]:
        raise HTTPException(403, "Video chưa được cấp quyền phát sóng hoặc đang bị vô hiệu hóa")

    file_path = (row["playback_source"] or "").strip()
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(404, f"File MP4 local không tồn tại: {file_path}")

    return FileResponse(file_path, media_type="video/mp4")


@app.get("/overlay")
def get_overlay():
    overlay_path = STATIC_DIR / "overlay.html"
    if not overlay_path.is_file():
        raise HTTPException(404, "Chưa tìm thấy static/overlay.html")
    return FileResponse(overlay_path)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await bc.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            mtype = data.get("type")
            if mtype in ("ended", "error"):
                seq = data.get("seq", 0)
                await bc.advance(seq)
            elif mtype == "ping":
                await ws.send_json({"type": "pong"})
    except (WebSocketDisconnect, Exception):
        bc.disconnect(ws)


# ----------------- STATS & VIDEOS -----------------
@app.get("/api/stats")
def api_stats():
    st = services.stats()
    # Kiểm tra số lượng video thực sự ready (licensed + file tồn tại + enabled)
    ready_count = len(scheduler.ready_videos())
    with get_conn() as conn:
        q_cnt = conn.execute("SELECT COUNT(*) FROM queue WHERE played=0").fetchone()[0]
        v_cnt = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE session_id=?", (voting_engine.get_session_id(),)
        ).fetchone()[0]

    return {
        **st,
        "ready_to_broadcast": ready_count,
        "queue_count": q_cnt,
        "votes_count": v_cnt,
        "api_key_configured": bool(YOUTUBE_API_KEY),
        "broadcast": bc.get_state(),
        "voting_session": voting_engine.get_session_id(),
        "voting_enabled": voting_engine.is_enabled(),
    }


@app.get("/api/videos")
def api_videos(q: str = "", rights: str = "", category: str = "", limit: int = 500):
    sql, args = "SELECT * FROM music_videos WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR artist LIKE ? OR channel LIKE ?)"
        args += [f"%{q}%"] * 3
    if rights:
        sql += " AND rights_status=?"; args.append(rights)
    if category:
        sql += " AND category=?"; args.append(category)
    sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)

    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, args)]

    for r in rows:
        path = (r.get("playback_source") or "").strip()
        f_exists = bool(path and os.path.isfile(path))
        r["file_exists"] = f_exists
        r["ready"] = r["rights_status"] == "licensed" and f_exists and bool(r["enabled"])
        r["code"] = f"#{r['id']}"
    return rows


@app.put("/api/videos/{vid}")
async def api_update_video(vid: int, body: VideoUpdate):
    data = body.model_dump(exclude_none=True)
    if "rights_status" in data and data["rights_status"] not in RIGHTS:
        raise HTTPException(400, "rights_status không hợp lệ")
    if "enabled" in data:
        data["enabled"] = int(data["enabled"])
    if not data:
        raise HTTPException(400, "Không có dữ liệu cập nhật")

    sets = ", ".join(f"{k}=?" for k in data)
    with get_conn() as conn:
        conn.execute(f"UPDATE music_videos SET {sets} WHERE id=?", [*data.values(), vid])

    await bc.notify_next_changed()
    return {"ok": True}


@app.delete("/api/videos/{vid}")
async def api_delete_video(vid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM music_videos WHERE id=?", (vid,))
        conn.execute("DELETE FROM queue WHERE video_id=?", (vid,))
        conn.execute("DELETE FROM votes WHERE video_id=?", (vid,))
    await bc.notify_next_changed()
    return {"ok": True}


@app.post("/api/videos/clean-compilations")
async def api_clean_compilations(body: CleanIn | None = None):
    action = body.action if body else "delete"
    res = services.clean_compilations(action=action)
    await bc.notify_next_changed()
    return res


@app.post("/api/videos/{vid}/generate-test")
async def api_generate_test_video(vid: int, duration: int = 25):
    try:
        res = services.generate_test_video(vid, duration_sec=duration)
        await bc.notify_next_changed()
        return res
    except Exception as e:
        raise HTTPException(400, f"Lỗi tạo video test: {str(e)}")


@app.post("/api/videos/generate-batch-test")
async def api_generate_batch_test(count: int = 5, duration: int = 25):
    try:
        res = services.generate_batch_test_videos(count=count, duration_sec=duration)
        await bc.notify_next_changed()
        return res
    except Exception as e:
        raise HTTPException(400, f"Lỗi tạo hàng loạt video test: {str(e)}")


@app.post("/api/videos/{vid}/upload")
async def api_upload_video(vid: int, file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".mkv", ".mov", ".webm")):
        raise HTTPException(400, "Chỉ hỗ trợ file định dạng video (.mp4, .mkv, .mov, .webm)")

    out_dir = Path(BASE_DIR) / "data" / "media"
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix or ".mp4"
    dest = out_dir / f"uploaded_mv_{vid}{ext}"

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    abs_path = str(dest.resolve())
    with get_conn() as conn:
        conn.execute(
            """UPDATE music_videos
               SET playback_source = ?, rights_status = 'licensed', enabled = 1
               WHERE id = ?""",
            (abs_path, vid),
        )

    await bc.notify_next_changed()
    return {"ok": True, "video_id": vid, "playback_source": abs_path}


# ----------------- KEYWORDS & DISCOVERY -----------------
@app.get("/api/keywords")
def api_keywords():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM discovery_keywords ORDER BY id")]


@app.post("/api/keywords")
def api_add_keyword(body: KeywordIn):
    kw = body.keyword.strip()
    if not kw:
        raise HTTPException(400, "Từ khóa trống")
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO discovery_keywords(keyword) VALUES (?)", (kw,))
    return {"ok": True}


@app.delete("/api/keywords/{kid}")
def api_delete_keyword(kid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM discovery_keywords WHERE id=?", (kid,))
    return {"ok": True}


@app.post("/api/discover")
def api_discover(body: DiscoverIn):
    if body.keyword:
        return [services.discover(body.keyword, body.max_results)]
    with get_conn() as conn:
        kws = [r[0] for r in conn.execute("SELECT keyword FROM discovery_keywords WHERE enabled=1")]
    return [services.discover(k, body.max_results) for k in kws]


@app.get("/api/logs")
def api_logs():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM discovery_logs ORDER BY id DESC LIMIT 50")]


# ----------------- BROADCAST CONTROL -----------------
@app.get("/api/broadcast/state")
def api_broadcast_state():
    return bc.get_state()


@app.post("/api/broadcast/start")
async def api_broadcast_start():
    return await bc.start()


@app.post("/api/broadcast/stop")
async def api_broadcast_stop():
    return await bc.stop()


@app.post("/api/broadcast/skip")
async def api_broadcast_skip():
    return await bc.skip()


@app.get("/api/broadcast/settings")
def api_get_broadcast_settings():
    return scheduler.get_settings()


@app.put("/api/broadcast/settings")
async def api_save_broadcast_settings(body: BroadcastSettingsIn):
    data = body.model_dump(exclude_none=True)
    res = scheduler.save_settings(data)
    await bc.notify_next_changed()
    return res


@app.get("/api/broadcast/ticker-speed")
def api_get_ticker_speed():
    with get_conn() as conn:
        r = conn.execute("SELECT value FROM settings WHERE key='ticker_speed'").fetchone()
        speed = int(r[0]) if r and r[0].isdigit() else 180
    return {"speed": speed}


@app.put("/api/broadcast/ticker-speed")
async def api_set_ticker_speed(body: TickerSpeedIn):
    speed = max(40, min(600, int(body.speed)))
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('ticker_speed', ?)", (str(speed),))
    await bc.broadcast_ticker_speed(speed)
    return {"ok": True, "speed": speed}


# ----------------- QUEUE & PLAY HISTORY -----------------
@app.get("/api/queue")
def api_get_queue():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT q.id as queue_id, q.video_id, q.played, q.created_at,
                      m.title, m.artist, m.thumbnail, m.duration, m.category, m.playback_source, m.rights_status, m.enabled
               FROM queue q
               JOIN music_videos m ON q.video_id = m.id
               WHERE q.played = 0
               ORDER BY q.id ASC"""
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/queue")
async def api_add_queue(body: QueueIn):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM music_videos WHERE id=? AND rights_status='licensed' AND enabled=1 AND playback_source!=''",
            (body.video_id,)
        ).fetchone()

    if not row:
        raise HTTPException(400, "Bài hát không tồn tại hoặc chưa được cấp quyền phát")

    file_path = row["playback_source"].strip()
    if not os.path.isfile(file_path):
        raise HTTPException(400, f"File MP4 local không tồn tại: {file_path}")

    with get_conn() as conn:
        conn.execute("INSERT INTO queue(video_id, played) VALUES (?, 0)", (body.video_id,))

    await bc.notify_next_changed()
    return {"ok": True}


@app.delete("/api/queue/{qid}")
async def api_delete_queue(qid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM queue WHERE id=?", (qid,))
    await bc.notify_next_changed()
    return {"ok": True}


@app.get("/api/history")
def api_get_history():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.id, p.video_id, p.started_at, m.title, m.artist, m.thumbnail, m.category, m.duration
               FROM play_history p
               JOIN music_videos m ON p.video_id = m.id
               ORDER BY p.id DESC LIMIT 50"""
        ).fetchall()
        return [dict(r) for r in rows]


# ----------------- TIKTOK & VOTING -----------------
@app.get("/api/voting/state")
def api_voting_state():
    return {
        "enabled": voting_engine.is_enabled(),
        "session_id": voting_engine.get_session_id(),
        "leaderboard": voting_engine.get_top(10),
        "ready_codes": voting_engine.get_ready_codes(),
    }


@app.post("/api/voting/toggle")
def api_voting_toggle(body: VotingToggleIn):
    voting_engine.set_enabled(body.enabled)
    return {"ok": True, "enabled": voting_engine.is_enabled()}


@app.post("/api/voting/finalize")
def api_voting_finalize():
    return voting_engine.finalize_round()


@app.post("/api/voting/reset")
def api_voting_reset():
    return voting_engine.reset_round()


@app.get("/api/voting/leaderboard")
def api_voting_leaderboard(limit: int = 10):
    return voting_engine.get_top(limit)


@app.get("/api/voting/history")
def api_voting_history():
    return voting_engine.get_history(50)


@app.post("/api/tiktok/simulate/comment")
def api_sim_comment(body: SimCommentIn):
    return tiktok_adapter.simulate_comment(body.user_id, body.user_name, body.text)


@app.post("/api/tiktok/simulate/gift")
def api_sim_gift(body: SimGiftIn):
    return tiktok_adapter.simulate_gift(
        body.user_id, body.user_name, body.gift_name, body.diamonds, body.repeat, body.video_id
    )


@app.get("/api/tiktok/events")
def api_tiktok_events(limit: int = 30):
    return tiktok_adapter.get_recent_events(limit)


# ----------------- PAGE ROUTES -----------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
