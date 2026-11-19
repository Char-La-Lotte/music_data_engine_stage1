import re
import httpx
from .config import YOUTUBE_API_KEY

API = "https://www.googleapis.com/youtube/v3"


def _get(endpoint: str, params: dict) -> dict:
    if not YOUTUBE_API_KEY:
        raise RuntimeError("Chưa cấu hình YOUTUBE_API_KEY trong file .env")
    params = {**params, "key": YOUTUBE_API_KEY}
    r = httpx.get(f"{API}/{endpoint}", params=params, timeout=20)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = r.text[:200]
        raise RuntimeError(f"YouTube API {r.status_code}: {msg}")
    return r.json()


def search_video_ids(keyword: str, max_results: int = 25) -> list[str]:
    data = _get("search", {
        "part": "id",
        "q": keyword,
        "type": "video",
        "videoCategoryId": "10",      # Music
        "videoEmbeddable": "true",
        "maxResults": min(max_results, 50),
    })
    return [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]


def parse_duration(iso: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def video_details(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    data = _get("videos", {"part": "snippet,contentDetails,status", "id": ",".join(ids)})
    out = []
    for it in data.get("items", []):
        sn = it["snippet"]
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        out.append({
            "youtube_id": it["id"],
            "raw_title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "channel_id": sn.get("channelId", ""),
            "thumbnail": thumb,
            "published_at": sn.get("publishedAt", ""),
            "description": (sn.get("description", "") or "")[:1000],
            "duration": parse_duration(it["contentDetails"].get("duration", "")),
            "embeddable": 1 if it.get("status", {}).get("embeddable") else 0,
        })
    return out
