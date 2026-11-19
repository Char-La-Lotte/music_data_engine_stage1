import json
from abc import ABC, abstractmethod
from typing import Callable
from .database import get_conn
from .voting_engine import voting_engine


class BaseTikTokAdapter(ABC):
    @abstractmethod
    def start(self, room_id_or_username: str = ""):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass


class SimulationTikTokAdapter(BaseTikTokAdapter):
    def __init__(self):
        self._connected = True
        self._comment_callbacks: list[Callable] = []
        self._gift_callbacks: list[Callable] = []
        self._follow_callbacks: list[Callable] = []

    def start(self, room_id_or_username: str = ""):
        self._connected = True

    def stop(self):
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def on_comment(self, cb: Callable):
        self._comment_callbacks.append(cb)

    def on_gift(self, cb: Callable):
        self._gift_callbacks.append(cb)

    def on_follow(self, cb: Callable):
        self._follow_callbacks.append(cb)

    def simulate_comment(self, user_id: str, user_name: str, text: str) -> dict:
        user_id = str(user_id or "user_sim").strip()
        user_name = str(user_name or "Khán giả").strip()
        text = str(text or "").strip()

        # 1. Log event vào DB
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO tiktok_events(event_type, user_id, user_name, detail) VALUES ('comment', ?, ?, ?)",
                (user_id, user_name, text),
            )

        # 2. Xử lý vote
        vote_res = voting_engine.process_comment(user_id, user_name, text)

        # 3. Call external listeners if any
        for cb in self._comment_callbacks:
            try:
                cb(user_id, user_name, text, vote_res)
            except Exception:
                pass

        return {
            "event": "comment",
            "user_id": user_id,
            "user_name": user_name,
            "text": text,
            "vote_result": vote_res,
        }

    def simulate_gift(
        self,
        user_id: str,
        user_name: str,
        gift_name: str,
        diamonds: int = 1,
        repeat: int = 1,
        video_id: int | None = None,
    ) -> dict:
        user_id = str(user_id or "user_sim").strip()
        user_name = str(user_name or "Khán giả VIP").strip()
        gift_name = str(gift_name or "Hoa hồng").strip()
        diamonds = max(1, int(diamonds))
        repeat = max(1, int(repeat))

        detail = f"{gift_name} x{repeat} ({diamonds}💎) -> #{video_id}" if video_id else f"{gift_name} x{repeat} ({diamonds}💎)"

        # 1. Log event
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO tiktok_events(event_type, user_id, user_name, detail) VALUES ('gift', ?, ?, ?)",
                (user_id, user_name, detail),
            )

        # 2. Xử lý vote
        vote_res = voting_engine.process_gift(user_id, user_name, gift_name, diamonds, repeat, video_id)

        # 3. Call external listeners if any
        for cb in self._gift_callbacks:
            try:
                cb(user_id, user_name, gift_name, diamonds, repeat, vote_res)
            except Exception:
                pass

        return {
            "event": "gift",
            "user_id": user_id,
            "user_name": user_name,
            "gift_name": gift_name,
            "diamonds": diamonds,
            "repeat": repeat,
            "vote_result": vote_res,
        }

    def simulate_follow(self, user_id: str, user_name: str) -> dict:
        user_id = str(user_id or "user_sim").strip()
        user_name = str(user_name or "Khán giả mới").strip()

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO tiktok_events(event_type, user_id, user_name, detail) VALUES ('follow', ?, ?, 'followed')",
                (user_id, user_name),
            )

        for cb in self._follow_callbacks:
            try:
                cb(user_id, user_name)
            except Exception:
                pass

        return {"event": "follow", "user_id": user_id, "user_name": user_name}

    def get_recent_events(self, limit: int = 30) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tiktok_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]


tiktok_adapter = SimulationTikTokAdapter()
