const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const video = $("#videoPlayer");
const nowCard = $("#nowCard");
const nowThumb = $("#nowThumb");
const nowCode = $("#nowCode");
const nowCat = $("#nowCat");
const nowTitle = $("#nowTitle");
const nowArtist = $("#nowArtist");

const nextCard = $("#nextCard");
const nextThumb = $("#nextThumb");
const nextTitle = $("#nextTitle");
const nextArtist = $("#nextArtist");
const tickerNextText = $("#tickerNextText");
const tickerTrack = $("#tickerTrack");

const idleScreen = $("#idleScreen");
const idleText = $("#idleText");
const unmuteBtn = $("#unmuteBtn");
const lbList = $("#lbList");

let currentSeq = 0;
let currentTrack = null;
let nextTrack = null;
let hideNowTimer = null;
let ws = null;

function showIdle(show, msg = "Đang chờ tín hiệu phát sóng từ Studio...") {
  if (show) {
    idleScreen.classList.add("active");
    idleText.textContent = msg;
    nowCard.classList.add("hidden");
    nextCard.classList.remove("show");
  } else {
    idleScreen.classList.remove("active");
  }
}

function renderLeaderboard(items) {
  if (!items || items.length === 0) {
    lbList.innerHTML = '<div class="lb-empty">Đang chờ lượt bình chọn đầu tiên...</div>';
    return;
  }
  lbList.innerHTML = items.map((it) => `
    <div class="lb-item rank-${it.rank}">
      <div class="lb-item-left">
        <div class="lb-rank">${it.rank}</div>
        <div class="lb-code">${esc(it.code)}</div>
        <div class="lb-song">
          <div class="lb-song-title">${esc(it.title)}</div>
          <div class="lb-song-artist">${esc(it.artist)}</div>
        </div>
      </div>
      <div class="lb-votes"><span>${it.points}</span><small style="font-size:12px;opacity:0.8">🗳️</small></div>
    </div>
  `).join("");
}

function showNowPlaying(track) {
  if (!track) return;
  nowThumb.src = track.thumbnail || "";
  nowCode.textContent = track.code || `#${track.id}`;
  nowCat.textContent = track.category || "V-Pop";
  nowTitle.textContent = track.title || "Không rõ tên bài hát";
  nowArtist.textContent = track.artist || track.channel || "Không rõ nghệ sĩ";

  nowCard.classList.remove("hidden");
  if (hideNowTimer) clearTimeout(hideNowTimer);
  // Hiện 10 giây đầu bài hát rồi ẩn
  hideNowTimer = setTimeout(() => {
    nowCard.classList.add("hidden");
  }, 10000);
}

function setTickerSpeed(sec) {
  if (tickerTrack && sec) {
    tickerTrack.style.setProperty("--ticker-speed", `${sec}s`);
    tickerTrack.style.animationDuration = `${sec}s`;
  }
}

function updateNextTrack(track) {
  nextTrack = track;
  if (!track) {
    nextCard.classList.remove("show");
    if (tickerNextText) tickerNextText.textContent = "Đang chọn bài...";
    return;
  }
  nextThumb.src = track.thumbnail || "";
  nextTitle.textContent = `${track.code || '#' + track.id} ${track.title}`;
  nextArtist.textContent = track.artist || track.channel || "";
  if (tickerNextText) {
    tickerNextText.textContent = `${track.code || '#' + track.id} ${track.title} - ${track.artist || track.channel || ""}`;
  }
}

async function loadTickerSongs() {
  try {
    const res = await fetch("/api/videos?limit=80");
    if (!res.ok) return;
    const songs = await res.json();
    if (!songs || !songs.length || !tickerTrack) return;

    const itemsHtml = songs.map((s) => `
      <span class="ticker-item">
        <span class="t-code">${esc(s.code)}</span>
        <span class="t-title">${esc(s.title)}</span>
        <span class="t-artist">(${esc(s.artist || s.channel)})</span>
      </span>
      <span class="ticker-sep">✦</span>
    `).join("");

    const guideHtml = `<span class="ticker-item" style="color:#00f2fe;font-weight:800">🗳️ Comment #MÃ để bình chọn bài tiếp theo!</span><span class="ticker-sep">✦</span>`;
    const fullHtml = guideHtml + itemsHtml;

    // Nhân đôi nội dung để animation translateX(-50%) lặp vô tận mượt mà
    tickerTrack.innerHTML = fullHtml + fullHtml;
  } catch (e) {
    console.error("loadTickerSongs error:", e);
  }
}

function playTrack(track) {
  if (!track || !track.url) {
    showIdle(true, "Không tìm thấy đường dẫn phát sóng.");
    return;
  }
  currentTrack = track;
  showIdle(false);
  showNowPlaying(track);

  video.src = track.url;
  video.currentTime = 0;
  video.play().then(() => {
    unmuteBtn.style.display = "none";
  }).catch((err) => {
    console.warn("Autoplay bị chặn, cần tương tác người dùng:", err);
    unmuteBtn.style.display = "block";
  });
}

function stopPlayback() {
  currentTrack = null;
  nextTrack = null;
  video.pause();
  video.removeAttribute("src");
  video.load();
  showIdle(true);
}

// Theo dõi thời gian phát để hiện thẻ "Tiếp theo" 15s cuối
video.ontimeupdate = () => {
  if (!video.duration || isNaN(video.duration)) return;
  const remaining = video.duration - video.currentTime;
  if (remaining <= 15 && nextTrack) {
    nextCard.classList.add("show");
  } else {
    nextCard.classList.remove("show");
  }
};

// Khi phát xong video
video.onended = () => {
  console.log("Video ended, seq:", currentSeq);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ended", seq: currentSeq }));
  }
};

// Khi lỗi file / media
video.onerror = (e) => {
  console.error("Video playback error:", e);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "error", seq: currentSeq }));
  }
};

unmuteBtn.onclick = () => {
  video.muted = false;
  video.play();
  unmuteBtn.style.display = "none";
};

// Kết nối WebSocket tới server
function connectWS() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${location.host}/ws`;
  console.log("Connecting WebSocket to", wsUrl);

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("WebSocket connected");
  };

  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      console.log("WS Message:", msg);

      if (msg.type === "play") {
        currentSeq = msg.seq;
        updateNextTrack(msg.next);
        playTrack(msg.current);
      } else if (msg.type === "next") {
        updateNextTrack(msg.next);
      } else if (msg.type === "leaderboard") {
        renderLeaderboard(msg.data);
      } else if (msg.type === "ticker_speed") {
        setTickerSpeed(msg.speed);
      } else if (msg.type === "idle") {
        stopPlayback();
      }
    } catch (err) {
      console.error("Lỗi parse WS message:", err);
    }
  };

  ws.onclose = () => {
    console.warn("WebSocket closed. Đang kết nối lại sau 3s...");
    setTimeout(connectWS, 3000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    ws.close();
  };
}

// Khởi động
connectWS();
loadTickerSongs();
setInterval(loadTickerSongs, 60000);
