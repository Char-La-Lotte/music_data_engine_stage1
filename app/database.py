import sqlite3
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS music_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    artist TEXT DEFAULT '',
    channel TEXT DEFAULT '',
    channel_id TEXT DEFAULT '',
    thumbnail TEXT DEFAULT '',
    duration INTEGER DEFAULT 0,
    published_at TEXT DEFAULT '',
    description TEXT DEFAULT '',
    embeddable INTEGER DEFAULT 0,
    language TEXT DEFAULT '',
    category TEXT DEFAULT '',
    genres TEXT DEFAULT '',
    rights_status TEXT DEFAULT 'pending',
    playback_source TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    source_keyword TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS discovery_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run TEXT
);

CREATE TABLE IF NOT EXISTS discovery_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT,
    found INTEGER DEFAULT 0,
    added INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS play_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES music_videos(id)
);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    played INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES music_videos(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    video_id INTEGER NOT NULL,
    vote_type TEXT NOT NULL,
    points INTEGER DEFAULT 1,
    raw_content TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES music_videos(id)
);

CREATE TABLE IF NOT EXISTS tiktok_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

DEFAULT_KEYWORDS = [
    "MV nhạc Việt chính thức",
    "Vietnamese Ballad MV",
    "V-Pop Official MV",
    "Official Music Video",
    "EDM Official Music Video",
    "K-Pop Official MV",
    "Vietnamese oldies music video",
]

DEFAULT_SETTINGS = {
    "mode": "rotation",
    "slots": "[]",
    "voting_enabled": "1",
    "voting_session": "session_1",
    "voting_antispam_seconds": "10",
    "gift_points_ratio": "1",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM discovery_keywords").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO discovery_keywords(keyword) VALUES (?)",
                [(k,) for k in DEFAULT_KEYWORDS],
            )
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
