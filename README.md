# TikTok iTV – Music Data Engine

Hệ thống truyền hình âm nhạc tự động vận hành: Tìm kiếm MV trên YouTube, quản lý thư viện & bản quyền, tự xếp lịch phát, phát sóng qua OBS lên TikTok LIVE, tương tác bình chọn khán giả (Comment/Gift) realtime.

---

## Các giai đoạn hoàn thiện
1. **Giai đoạn 1**: YouTube Discovery, Metadata Cleaning, Classification, SQLite Database, Dashboard quản trị.
2. **Giai đoạn 2**: Scheduler điều phối phát sóng (Rotation, Random, Category slots), Hàng đợi ưu tiên (Queue), Media Streaming (`/media/{id}`), OBS 1080p Overlay (`/overlay`) realtime qua WebSocket (`/ws`).
3. **Giai đoạn 3**: TikTok LIVE Adapter (nhận Comment, Gift, Follow), Voting Engine (tính điểm, mã bình chọn `#ID`, chống spam rate limit, chốt vòng đưa bài thắng vào hàng đợi), Bảng xếp hạng Realtime Top 5 trên OBS Overlay & Dashboard, Bộ giả lập TikTok LIVE Simulation Console.

---

## Nguyên tắc bản quyền (Bắt buộc)
- YouTube **CHỈ** dùng để khám phá và lấy metadata. **KHÔNG** tải lậu, **KHÔNG** trích xuất luồng video từ YouTube.
- Nội dung phát ra là file MP4 local có bản quyền phát (`playback_source`).
- Chỉ phát video có `rights_status='licensed'` + `enabled=1` + file MP4 local tồn tại trên ổ đĩa. Mặc định MV mới thu thập ở trạng thái `pending`.

---

## Cấu trúc thư mục
```text
music_data_engine_stage1/
├── app/
│   ├── config.py         # BASE_DIR, YOUTUBE_API_KEY, DB_PATH, STATIC_DIR
│   ├── database.py       # Khởi tạo schema SQLite, từ khóa và cài đặt mặc định
│   ├── youtube.py        # YouTube Data API v3 (search.list + videos.list)
│   ├── services.py       # Làm sạch tiêu đề, phân loại ngôn ngữ/thể loại, discover, stats
│   ├── scheduler.py      # Lập lịch phát sóng (chống trùng, rotation, slots, queue)
│   ├── broadcast.py      # Quản lý phát sóng, state, WebSocket broadcast
│   ├── voting_engine.py  # Hệ thống bình chọn realtime, tính điểm gift/comment, chống spam
│   ├── tiktok_adapter.py # Adapter sự kiện TikTok LIVE + Console mô phỏng
│   └── main.py           # REST API FastAPI + WebSocket /ws + /media/{id} + /overlay
├── static/
│   ├── index.html        # Dashboard điều khiển trung tâm
│   ├── app.js            # Xử lý logic Dashboard, realtime polling, mô phỏng
│   ├── style.css         # Dark theme hiện đại
│   ├── overlay.html      # Trang Browser Source 1080p cho OBS
│   └── overlay.js        # Logic phát media, hiện thẻ Đang phát, Tiếp theo, Top 5 vote
├── data/
│   └── itv.sqlite3       # Database SQLite
├── .env                  # YOUTUBE_API_KEY
├── requirements.txt      # fastapi, uvicorn, httpx, python-dotenv, websockets
└── run_windows.bat       # Script khởi động tự động trên Windows
```

---

## Hướng dẫn sử dụng

### 1. Khởi chạy
Chạy `run_windows.bat` hoặc:
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
- **Dashboard Studio**: http://127.0.0.1:8000
- **OBS Browser Source**: http://127.0.0.1:8000/overlay (Đặt độ phân giải 1920x1080 trong OBS)

### 2. Sử dụng tính năng Bình chọn TikTok LIVE (GĐ3)
1. Khán giả comment mã bài hát theo cú pháp: `#MÃ` (ví dụ `#1`, `#2`). Hệ thống tự động cộng **+1 phiếu** và cập nhật bảng xếp hạng Realtime Top 5 lên màn hình OBS.
2. Tặng quà (Gift): Số điểm quy đổi theo kim cương của quà (ví dụ 1💎 = 1 phiếu, 17💎 = 17 phiếu...).
3. Chống spam: Mỗi user bị giới hạn tần suất vote comment (mặc định 10 giây/lượt).
4. Chốt vòng: Bấm **"🏆 Chốt vòng & Đưa Top 1 vào Hàng đợi"** để tự động thêm bài hát chiến thắng vào hàng đợi phát sóng tiếp theo và reset phiên vote mới.
5. Kiểm thử nhanh: Sử dụng **Bộ mô phỏng TikTok LIVE** ngay trên Dashboard để bắn comment và tặng quà giả lập.
