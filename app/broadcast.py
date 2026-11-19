from fastapi import WebSocket
from .database import get_conn
from .scheduler import pick_next


class Broadcast:
    def __init__(self):
        self.is_playing: bool = False
        self.current: dict | None = None
        self.next: dict | None = None
        self.seq: int = 0
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)
        # Gửi trạng thái hiện tại
        if self.is_playing and self.current:
            await ws.send_json({
                "type": "play",
                "seq": self.seq,
                "current": self.current,
                "next": self.next,
            })
        else:
            await ws.send_json({"type": "idle"})

        # Gửi bảng xếp hạng realtime
        from .voting_engine import voting_engine
        await ws.send_json({
            "type": "leaderboard",
            "data": voting_engine.get_top(5),
            "session": voting_engine.get_session_id(),
        })

        # Gửi tốc độ chạy chữ ticker
        with get_conn() as conn:
            r = conn.execute("SELECT value FROM settings WHERE key='ticker_speed'").fetchone()
            speed = int(r[0]) if r and r[0].isdigit() else 180
        await ws.send_json({"type": "ticker_speed", "speed": speed})

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, msg: dict):
        dead = set()
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.clients.difference_update(dead)

    def _record_history(self, video_id: int):
        with get_conn() as conn:
            conn.execute("INSERT INTO play_history(video_id) VALUES (?)", (video_id,))

    def _mark_queue_played(self, queue_id: int):
        with get_conn() as conn:
            conn.execute("UPDATE queue SET played=1 WHERE id=?", (queue_id,))

    async def start(self) -> dict:
        if self.is_playing and self.current:
            return {"ok": True, "status": "already_playing", "current": self.current}

        first = pick_next()
        if not first:
            self.is_playing = False
            self.current = None
            self.next = None
            await self.broadcast({"type": "idle"})
            return {"ok": False, "message": "Không có bài hát nào sẵn sàng để phát (cần licensed + file MP4 local tồn tại)."}

        self.is_playing = True
        self.current = first
        self.seq += 1
        self._record_history(first["id"])
        self.next = pick_next(exclude=[first["id"]])

        await self.broadcast({
            "type": "play",
            "seq": self.seq,
            "current": self.current,
            "next": self.next,
        })
        return {"ok": True, "current": self.current, "next": self.next}

    async def stop(self) -> dict:
        self.is_playing = False
        self.current = None
        self.next = None
        self.seq += 1
        await self.broadcast({"type": "idle"})
        return {"ok": True}

    async def skip(self) -> dict:
        if not self.is_playing:
            return await self.start()
        return await self.advance(self.seq)

    async def advance(self, seq: int) -> dict:
        if seq != self.seq:
            return {"ignored": True, "reason": "outdated_seq", "expected": self.seq, "received": seq}

        if self.current and "queue_id" in self.current:
            self._mark_queue_played(self.current["queue_id"])

        candidate = self.next
        if not candidate:
            candidate = pick_next(exclude=[self.current["id"]] if self.current else None)

        if not candidate:
            self.is_playing = False
            self.current = None
            self.next = None
            self.seq += 1
            await self.broadcast({"type": "idle"})
            return {"ok": True, "status": "idle"}

        self.current = candidate
        self.seq += 1
        self._record_history(self.current["id"])
        self.next = pick_next(exclude=[self.current["id"]])

        await self.broadcast({
            "type": "play",
            "seq": self.seq,
            "current": self.current,
            "next": self.next,
        })
        return {"ok": True, "seq": self.seq, "current": self.current}

    async def notify_next_changed(self):
        if self.is_playing and self.current:
            self.next = pick_next(exclude=[self.current["id"]])
            await self.broadcast({"type": "next", "next": self.next})

    async def broadcast_leaderboard(self):
        from .voting_engine import voting_engine
        await self.broadcast({
            "type": "leaderboard",
            "data": voting_engine.get_top(5),
            "session": voting_engine.get_session_id(),
        })

    async def broadcast_ticker_speed(self, speed: int):
        await self.broadcast({"type": "ticker_speed", "speed": speed})

    def get_state(self) -> dict:
        return {
            "is_playing": self.is_playing,
            "current": self.current,
            "next": self.next,
            "seq": self.seq,
            "clients_count": len(self.clients),
        }


bc = Broadcast()
