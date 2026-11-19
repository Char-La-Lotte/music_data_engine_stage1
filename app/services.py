import re
import subprocess
from pathlib import Path
from . import youtube
from .config import BASE_DIR
from .database import get_conn

NOISE = re.compile(
    r"[\(\[\{][^\)\]\}]*(official|mv|m/v|lyric|audio|video|4k|hd|visualizer|teaser)[^\)\]\}]*[\)\]\}]",
    re.I,
)
VI_CHARS = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)
HANGUL = re.compile(r"[\uac00-\ud7af]")
KANA = re.compile(r"[\u3040-\u30ff]")
OLDIES = ("nhạc xưa", "nhạc vàng", "bolero", "oldies", "nhạc bất hủ", "trữ tình")
GENRE_KEYS = {
    "Ballad": ("ballad",),
    "EDM": ("edm", "remix", "dj "),
    "Rap": ("rap", "hip hop", "hiphop"),
    "Indie": ("indie",),
    "Dance": ("dance",),
    "Pop": ("pop",),
}

NOISE_WORDS = {"official", "music", "video", "mv", "m/v", "lyrics", "lyric", "audio",
               "visualizer", "teaser", "themesong", "4k", "hd", "full", "ost"}
CHANNEL_WORDS = re.compile(r"(?i)\b(official|vevo|music|channel|topic|records?|entertainment)\b")
SEP = re.compile(r"\s+[-–—|•]\s+")

# Từ khóa định danh video tổng hợp / tuyển tập / album
EXPLICIT_COMPILATION = re.compile(
    r"(?i)\b("
    r"tổng hợp|tuyển tập|tuyển chọn|liên khúc|\blk\b|những bài hát hay nhất|bài hát hay nhất của|"
    r"full album|trọn bộ album|mixtape|nonstop|playlist|greatest hits|best songs of|"
    r"top \d+\s*(bài|ca khúc|bản|hit)|(\d+)\s*(bài hát|ca khúc|bản ballad|hit) hay nhất|"
    r"collection|medley|all songs|full concert|liveshow"
    r")\b",
    re.I,
)

MIN_MV_DURATION = 60    # 1 phút
MAX_MV_DURATION = 600   # 10 phút (chuẩn MV phát sóng đơn lẻ)


def is_compilation_or_invalid(raw_title: str, duration: int) -> tuple[bool, str]:
    """Kiểm tra video có phải là video tổng hợp, liên khúc, quá dài (>10p) hoặc quá ngắn (<1p)."""
    if duration > MAX_MV_DURATION:
        return True, f"Thời lượng quá dài ({duration//60}m{duration%60}s > {MAX_MV_DURATION//60}m - video tổng hợp/show)"
    if duration < MIN_MV_DURATION:
        return True, f"Thời lượng quá ngắn ({duration}s < {MIN_MV_DURATION}s - teaser/short)"
    if EXPLICIT_COMPILATION.search(raw_title):
        return True, "Chứa từ khóa tổng hợp / tuyển tập / liên khúc / playlist"
    return False, ""


def clean_compilations(action: str = "delete") -> dict:
    """Quét và dọn dẹp các video tổng hợp hoặc không hợp lệ đã có trong database."""
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, title, duration FROM music_videos").fetchall()]
        ids_to_process = []
        for r in rows:
            is_comp, reason = is_compilation_or_invalid(r["title"], r["duration"])
            if is_comp:
                ids_to_process.append((r["id"], r["title"], r["duration"], reason))

        if ids_to_process:
            ids = [item[0] for item in ids_to_process]
            placeholders = ",".join("?" * len(ids))
            if action == "delete":
                conn.execute(f"DELETE FROM queue WHERE video_id IN ({placeholders})", ids)
                conn.execute(f"DELETE FROM votes WHERE video_id IN ({placeholders})", ids)
                conn.execute(f"DELETE FROM play_history WHERE video_id IN ({placeholders})", ids)
                conn.execute(f"DELETE FROM music_videos WHERE id IN ({placeholders})", ids)
            else:
                conn.execute(
                    f"UPDATE music_videos SET rights_status='blocked', enabled=0 WHERE id IN ({placeholders})",
                    ids,
                )

        removed = [
            {"id": i[0], "title": i[1], "duration": i[2], "reason": i[3]}
            for i in ids_to_process
        ]
    return {"count": len(removed), "action": action, "items": removed}


def generate_test_video(video_id: int, duration_sec: int = 30) -> dict:
    """Tạo video MP4 Full HD giả lập bằng FFmpeg để kiểm thử toàn diện hệ thống."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM music_videos WHERE id=?", (video_id,)).fetchone()
    if not row:
        raise ValueError(f"Không tìm thấy video #{video_id}")

    out_dir = Path(BASE_DIR) / "data" / "media"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"test_mv_{video_id}.mp4"

    title = (row["title"] or f"Song #{video_id}")[:35]
    artist = (row["artist"] or row["channel"] or "Unknown")[:25]
    safe_title = re.sub(r"[\':\\%]", " ", title).encode("ascii", "ignore").decode("ascii").strip()
    if not safe_title:
        safe_title = f"Song #{video_id}"
    safe_artist = re.sub(r"[\':\\%]", " ", artist).encode("ascii", "ignore").decode("ascii").strip()
    if not safe_artist:
        safe_artist = "Artist"

    dur = max(5, min(120, int(duration_sec)))
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0f172a:s=1920x1080:d={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
        "-vf", f"drawtext=text='TikTok iTV LIVE TEST':fontcolor=0x00f2fe:fontsize=48:x=(w-text_w)/2:y=100,drawtext=text='#{video_id} {safe_title}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-30,drawtext=text='Artist - {safe_artist}':fontcolor=0x94a3b8:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/2+50",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(file_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {res.stderr[:200]}")

    abs_path = str(file_path.resolve())
    with get_conn() as conn:
        conn.execute(
            """UPDATE music_videos
               SET playback_source = ?, rights_status = 'licensed', enabled = 1
               WHERE id = ?""",
            (abs_path, video_id),
        )

    return {"ok": True, "video_id": video_id, "playback_source": abs_path, "duration": dur}


def generate_batch_test_videos(count: int = 5, duration_sec: int = 25) -> list[dict]:
    """Tạo hàng loạt video test cho N bài hát đầu tiên trong DB để test nhanh."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM music_videos WHERE enabled=1 ORDER BY id ASC LIMIT ?", (count,)).fetchall()

    results = []
    for r in rows:
        try:
            res = generate_test_video(r["id"], duration_sec=duration_sec)
            results.append(res)
        except Exception as e:
            results.append({"video_id": r["id"], "ok": False, "error": str(e)})
    return results


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", CHANNEL_WORDS.sub("", s).lower())


def _is_noise(part: str) -> bool:
    words = re.findall(r"[\w/]+", part.lower())
    return bool(words) and all(w in NOISE_WORDS for w in words)


def parse_title(raw: str, channel: str) -> tuple[str, str]:
    clean = NOISE.sub("", raw)
    clean = re.sub(r"\s+", " ", clean).strip(" -|•")
    parts = [p.strip() for p in SEP.split(clean) if p.strip() and not _is_noise(p)]
    channel_clean = re.sub(r"\s+", " ", CHANNEL_WORDS.sub("", channel)).strip(" -|•") or channel
    if not parts:
        return clean, channel_clean
    if len(parts) == 1:
        return parts[0], channel_clean
    ch = _norm(channel)
    def match(p):
        n = _norm(p)
        return bool(n and ch and (n in ch or ch in n))
    if match(parts[-1]):
        return " - ".join(parts[:-1]), parts[-1]
    if match(parts[0]):
        return " - ".join(parts[1:]), parts[0]
    return parts[0], channel_clean


def classify(title: str, artist: str, desc: str, channel: str, keyword: str) -> dict:
    text = f"{title} {artist} {channel} {keyword}".lower()
    full = f"{text} {desc[:300].lower()}"
    if HANGUL.search(full):
        lang, cat = "ko", "K-Pop"
    elif KANA.search(full):
        lang, cat = "ja", "J-Pop"
    elif VI_CHARS.search(f"{title} {artist}") or any(k in text for k in ("nhạc việt", "v-pop", "vpop", "vietnam")):
        lang, cat = "vi", "V-Pop"
    else:
        lang, cat = "en", "International"
    if any(k in full for k in OLDIES):
        cat = "Classic & Oldies"
    genres = [g for g, keys in GENRE_KEYS.items() if any(k in full for k in keys)]
    return {"language": lang, "category": cat, "genres": ",".join(genres)}


def discover(keyword: str, max_results: int = 25) -> dict:
    found = added = skipped = 0
    error = ""
    try:
        ids = youtube.search_video_ids(keyword, max_results)
        found = len(ids)
        with get_conn() as conn:
            existing = {r[0] for r in conn.execute(
                f"SELECT youtube_id FROM music_videos WHERE youtube_id IN ({','.join('?' * len(ids))})", ids
            )} if ids else set()
            new_ids = [i for i in ids if i not in existing]
            for d in youtube.video_details(new_ids):
                if not d["embeddable"]:
                    continue

                # Bỏ qua video tổng hợp, liên khúc, quá dài (>10 phút) hoặc quá ngắn (<1 phút)
                is_comp, _ = is_compilation_or_invalid(d["raw_title"], d["duration"])
                if is_comp:
                    skipped += 1
                    continue

                title, artist = parse_title(d["raw_title"], d["channel"])
                c = classify(title, artist, d["description"], d["channel"], keyword)
                cur = conn.execute(
                    """INSERT OR IGNORE INTO music_videos
                    (youtube_id,title,artist,channel,channel_id,thumbnail,duration,published_at,
                     description,embeddable,language,category,genres,source_keyword)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (d["youtube_id"], title, artist, d["channel"], d["channel_id"], d["thumbnail"],
                     d["duration"], d["published_at"], d["description"], d["embeddable"],
                     c["language"], c["category"], c["genres"], keyword),
                )
                added += cur.rowcount
    except Exception as e:
        error = str(e)
    with get_conn() as conn:
        conn.execute("INSERT INTO discovery_logs(keyword,found,added,error) VALUES (?,?,?,?)",
                     (keyword, found, added, error))
        conn.execute("UPDATE discovery_keywords SET last_run=CURRENT_TIMESTAMP WHERE keyword=?", (keyword,))
    return {"keyword": keyword, "found": found, "added": added, "skipped_compilations": skipped, "error": error}


def stats() -> dict:
    with get_conn() as conn:
        q = lambda sql: [dict(r) for r in conn.execute(sql)]
        total = conn.execute("SELECT COUNT(*) FROM music_videos").fetchone()[0]
        ready = conn.execute(
            "SELECT COUNT(*) FROM music_videos WHERE rights_status='licensed' AND playback_source!='' AND enabled=1"
        ).fetchone()[0]
        return {
            "total": total,
            "ready_to_broadcast": ready,
            "by_rights": q("SELECT rights_status AS k, COUNT(*) AS n FROM music_videos GROUP BY rights_status"),
            "by_category": q("SELECT category AS k, COUNT(*) AS n FROM music_videos GROUP BY category"),
        }
