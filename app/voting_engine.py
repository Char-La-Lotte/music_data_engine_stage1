import re
import time
from datetime import datetime
from .database import get_conn
from .scheduler import ready_videos


class VotingEngine:
    def __init__(self):
        self._last_user_comment_time: dict[str, float] = {}

    def _get_setting(self, key: str, default: str = "") -> str:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def _set_setting(self, key: str, val: str):
        with get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, str(val)))

    def is_enabled(self) -> bool:
        return self._get_setting("voting_enabled", "1") == "1"

    def set_enabled(self, enabled: bool):
        self._set_setting("voting_enabled", "1" if enabled else "0")

    def get_session_id(self) -> str:
        sess = self._get_setting("voting_session", "")
        if not sess:
            sess = "session_1"
            self._set_setting("voting_session", sess)
        return sess

    def set_session_id(self, sess: str):
        self._set_setting("voting_session", sess)

    def _get_votable_videos(self) -> list[dict]:
        """Lấy danh sách các bài hát có thể bình chọn (ưu tiên ready; nếu chưa bài nào ready thì lấy bài enabled để test)."""
        ready = ready_videos()
        if ready:
            return ready

        with get_conn() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM music_videos WHERE enabled=1 ORDER BY id ASC LIMIT 50"
            )]
            for r in rows:
                r["code"] = f"#{r['id']}"
            return rows

    def get_ready_codes(self) -> list[dict]:
        votable = self._get_votable_videos()
        ready_ids = {v["id"] for v in ready_videos()}
        return [
            {
                "code": f"#{v['id']}",
                "video_id": v["id"],
                "title": v["title"],
                "artist": v.get("artist") or v.get("channel", ""),
                "category": v.get("category", ""),
                "is_ready": v["id"] in ready_ids,
            }
            for v in votable
        ]

    def extract_vote_code(self, text: str) -> int | None:
        """Tìm mã #ID trong comment hoặc số độc lập hợp lệ."""
        text = text.strip()
        votable_ids = {v["id"] for v in self._get_votable_videos()}

        # 1. Tìm cú pháp dạng #1, # 12
        matches = re.findall(r"#\s*(\d+)", text)
        for m in matches:
            vid = int(m)
            if vid in votable_ids:
                return vid

        # 2. Tìm số nguyên độc lập (vd user chỉ comment: 1 hoặc 12)
        tokens = re.findall(r"\b(\d+)\b", text)
        for t in tokens:
            vid = int(t)
            if vid in votable_ids:
                return vid

        return None

    def process_comment(self, user_id: str, user_name: str, text: str) -> dict:
        if not self.is_enabled():
            return {"ok": False, "reason": "Bình chọn hiện đang tắt."}

        # Chống spam cho comment
        try:
            anti_spam = float(self._get_setting("voting_antispam_seconds", "10"))
        except ValueError:
            anti_spam = 10.0

        now = time.time()
        last_time = self._last_user_comment_time.get(user_id, 0.0)
        if now - last_time < anti_spam:
            remain = int(anti_spam - (now - last_time)) + 1
            return {"ok": False, "reason": f"Spam: Vui lòng đợi {remain}s trước khi vote tiếp."}

        video_id = self.extract_vote_code(text)
        if not video_id:
            return {"ok": False, "reason": "Không tìm thấy mã bài hát hợp lệ (ví dụ: #1, #2)."}

        session_id = self.get_session_id()
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO votes(session_id, user_id, user_name, video_id, vote_type, points, raw_content)
                   VALUES (?, ?, ?, ?, 'comment', 1, ?)""",
                (session_id, user_id, user_name, video_id, text),
            )

        self._last_user_comment_time[user_id] = now
        self._notify_leaderboard()

        return {"ok": True, "video_id": video_id, "points": 1, "code": f"#{video_id}"}

    def process_gift(
        self,
        user_id: str,
        user_name: str,
        gift_name: str,
        diamonds: int = 1,
        repeat: int = 1,
        video_id: int | None = None,
    ) -> dict:
        if not self.is_enabled():
            return {"ok": False, "reason": "Bình chọn hiện đang tắt."}

        try:
            ratio = float(self._get_setting("gift_points_ratio", "1"))
        except ValueError:
            ratio = 1.0

        points = max(1, int(diamonds * ratio)) * max(1, repeat)
        session_id = self.get_session_id()

        votable = self._get_votable_videos()
        votable_ids = {v["id"] for v in votable}

        # Nếu chưa có video_id chỉ định hoặc không hợp lệ:
        if not video_id or video_id not in votable_ids:
            with get_conn() as conn:
                r = conn.execute(
                    "SELECT video_id FROM votes WHERE session_id=? AND user_id=? ORDER BY id DESC LIMIT 1",
                    (session_id, user_id),
                ).fetchone()
                if r and r[0] in votable_ids:
                    video_id = r[0]
                else:
                    top = self.get_top(1)
                    if top and top[0]["video_id"] in votable_ids:
                        video_id = top[0]["video_id"]
                    elif votable:
                        video_id = votable[0]["id"]

        if not video_id:
            return {"ok": False, "reason": "Chưa có bài hát nào để nhận vote từ quà."}

        raw = f"{gift_name} x{repeat} ({diamonds}💎)"
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO votes(session_id, user_id, user_name, video_id, vote_type, points, raw_content)
                   VALUES (?, ?, ?, ?, 'gift', ?, ?)""",
                (session_id, user_id, user_name, video_id, points, raw),
            )

        self._notify_leaderboard()
        return {"ok": True, "video_id": video_id, "points": points, "gift": gift_name, "code": f"#{video_id}"}

    def get_top(self, limit: int = 5) -> list[dict]:
        session_id = self.get_session_id()
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT v.video_id, m.title, m.artist, m.thumbnail, m.category, SUM(v.points) AS total_points
                   FROM votes v
                   JOIN music_videos m ON v.video_id = m.id
                   WHERE v.session_id = ?
                   GROUP BY v.video_id
                   ORDER BY total_points DESC, MAX(v.id) ASC
                   LIMIT ?""",
                (session_id, limit),
            ).fetchall()

        out = []
        for rank, r in enumerate(rows, 1):
            out.append({
                "rank": rank,
                "video_id": r["video_id"],
                "code": f"#{r['video_id']}",
                "title": r["title"],
                "artist": r["artist"],
                "thumbnail": r["thumbnail"],
                "category": r["category"],
                "points": r["total_points"],
            })
        return out

    def finalize_round(self) -> dict:
        top = self.get_top(1)
        winner = None
        if top:
            winner = top[0]
            with get_conn() as conn:
                conn.execute("INSERT INTO queue(video_id, played) VALUES (?, 0)", (winner["video_id"],))

        new_sess = f"session_{int(datetime.now().timestamp())}"
        self.set_session_id(new_sess)
        self._notify_next_and_leaderboard()

        return {"ok": True, "winner": winner, "new_session": new_sess}

    def reset_round(self) -> dict:
        new_sess = f"session_{int(datetime.now().timestamp())}"
        self.set_session_id(new_sess)
        self._notify_leaderboard()
        return {"ok": True, "new_session": new_sess}

    def get_history(self, limit: int = 50) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT v.*, m.title, m.artist
                   FROM votes v
                   JOIN music_videos m ON v.video_id = m.id
                   ORDER BY v.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def _notify_leaderboard(self):
        try:
            import asyncio
            from .broadcast import bc
            loop = asyncio.get_running_loop()
            loop.create_task(bc.broadcast_leaderboard())
        except Exception:
            pass

    def _notify_next_and_leaderboard(self):
        try:
            import asyncio
            from .broadcast import bc
            loop = asyncio.get_running_loop()
            loop.create_task(bc.notify_next_changed())
            loop.create_task(bc.broadcast_leaderboard())
        except Exception:
            pass


voting_engine = VotingEngine()
