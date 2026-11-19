const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const api = async (url, opt = {}) => {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opt });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || err.message || r.statusText);
  }
  return r.json();
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[c]));

const fmt = (s) => `${Math.floor((s || 0) / 60)}:${String((s || 0) % 60).padStart(2, "0")}`;

// ----------------- 1. STATS -----------------
async function loadStats() {
  try {
    const s = await api("/api/stats");
    $("#warn").hidden = s.api_key_configured;

    const rights = Object.fromEntries(s.by_rights.map((x) => [x.k, x.n]));
    const isPlaying = s.broadcast && s.broadcast.is_playing;
    const currentTitle = isPlaying && s.broadcast.current ? s.broadcast.current.title : "Đang dừng";

    $("#stats").innerHTML = [
      ["Tổng MV", s.total],
      ["Sẵn sàng phát", s.ready_to_broadcast],
      ["Chờ xác minh", rights.pending || 0],
      ["Đã cấp quyền", rights.licensed || 0],
      ["Hàng đợi", s.queue_count || 0],
      ["Phiếu vòng này", s.votes_count || 0],
      ["Phát sóng", isPlaying ? "🟢 ĐANG PHÁT" : "⚪ ĐANG DỪNG"],
    ].map(([l, n]) => `<div class="card"><b>${n}</b><small>${l}</small></div>`).join("");

    const sel = $("#fCat");
    const cur = sel.value;
    sel.innerHTML = '<option value="">Mọi danh mục</option>' + s.by_category.map((c) => `<option>${esc(c.k)}</option>`).join("");
    sel.value = cur;

    // Cập nhật tag broadcast
    const bcTag = $("#bcStatusTag");
    if (isPlaying) {
      bcTag.textContent = `🟢 Đang phát: ${currentTitle}`;
      bcTag.classList.add("playing");
    } else {
      bcTag.textContent = "⚪ Đang dừng";
      bcTag.classList.remove("playing");
    }
  } catch (e) {
    console.error("loadStats error:", e);
  }
}

// ----------------- 2. BROADCAST & SCHEDULER -----------------
async function loadBroadcastState() {
  try {
    const st = await api("/api/broadcast/state");
    const curBox = $("#currentTrackContent");
    const nextBox = $("#nextTrackContent");

    if (st.is_playing && st.current) {
      curBox.innerHTML = `
        <div class="track-inline">
          <img src="${esc(st.current.thumbnail)}">
          <div class="track-meta">
            <b>${esc(st.current.code || '#' + st.current.id)} ${esc(st.current.title)}</b>
            <span>${esc(st.current.artist || st.current.channel)} · ${fmt(st.current.duration)} · ${esc(st.current.category)}</span>
          </div>
        </div>`;
    } else {
      curBox.innerHTML = `<em>Chưa có bài hát nào đang phát</em>`;
    }

    const dashNext = $("#dashNextSong");
    if (st.next) {
      if (dashNext) dashNext.textContent = `${st.next.code || '#' + st.next.id} ${st.next.title} - ${st.next.artist || st.next.channel || ''}`;
      nextBox.innerHTML = `
        <div class="track-inline">
          <img src="${esc(st.next.thumbnail)}">
          <div class="track-meta">
            <b>${esc(st.next.code || '#' + st.next.id)} ${esc(st.next.title)}</b>
            <span>${esc(st.next.artist || st.next.channel)} · ${fmt(st.next.duration)} · ${esc(st.next.category)}</span>
          </div>
        </div>`;
    } else {
      if (dashNext) dashNext.textContent = "Chưa chọn bài tiếp theo (sẽ chọn tự động)";
      nextBox.innerHTML = `<em>Chưa chọn bài tiếp theo (sẽ chọn tự động)</em>`;
    }
  } catch (e) {
    console.error("loadBroadcastState error:", e);
  }
}

async function loadBroadcastSettings() {
  try {
    const s = await api("/api/broadcast/settings");
    $("#bcMode").value = s.mode || "rotation";
    $("#bcSlots").value = JSON.stringify(s.slots || [], null, 2);
  } catch (e) {
    console.error("loadBroadcastSettings error:", e);
  }
}

$("#btnSaveBcSettings").onclick = async () => {
  try {
    const mode = $("#bcMode").value;
    let slots = [];
    try {
      slots = JSON.parse($("#bcSlots").value || "[]");
    } catch (e) {
      alert("JSON khung giờ slots không hợp lệ!");
      return;
    }
    await api("/api/broadcast/settings", {
      method: "PUT",
      body: JSON.stringify({ mode, slots }),
    });
    alert("Đã lưu cài đặt điều phối lịch!");
    loadBroadcastState();
  } catch (e) {
    alert("Lỗi lưu cài đặt: " + e.message);
  }
};

$("#btnStart").onclick = async () => {
  try {
    const r = await api("/api/broadcast/start", { method: "POST" });
    if (!r.ok && r.message) alert(r.message);
    loadStats();
    loadBroadcastState();
  } catch (e) { alert("Lỗi bắt đầu phát: " + e.message); }
};

$("#btnSkip").onclick = async () => {
  try {
    await api("/api/broadcast/skip", { method: "POST" });
    loadStats();
    loadBroadcastState();
  } catch (e) { alert("Lỗi chuyển bài: " + e.message); }
};

$("#btnStop").onclick = async () => {
  try {
    await api("/api/broadcast/stop", { method: "POST" });
    loadStats();
    loadBroadcastState();
  } catch (e) { alert("Lỗi dừng phát: " + e.message); }
};

// ----------------- 3. QUEUE -----------------
async function loadQueue() {
  try {
    const qs = await api("/api/queue");
    $("#queueCountBadge").textContent = `${qs.length} bài`;
    $("#queueRows").innerHTML = qs.map((q, idx) => `
      <tr>
        <td><b>${idx + 1}</b></td>
        <td><img src="${esc(q.thumbnail)}"></td>
        <td><b>#${q.video_id} ${esc(q.title)}</b><br><small style="color:#94a3b8">${esc(q.artist)}</small></td>
        <td>${fmt(q.duration)}</td>
        <td>${esc(q.category)}</td>
        <td><button class="btn-danger" data-delq="${q.queue_id}" style="padding:3px 8px;font-size:11px">Xóa</button></td>
      </tr>
    `).join("") || '<tr><td colspan="6" style="text-align:center;color:#64748b">Hàng đợi đang trống. Bấm "+ Hàng đợi" ở bảng MV để thêm.</td></tr>';
  } catch (e) {
    console.error("loadQueue error:", e);
  }
}

$("#queueRows").onclick = async (e) => {
  if (e.target.dataset.delq) {
    await api("/api/queue/" + e.target.dataset.delq, { method: "DELETE" });
    loadQueue();
    loadBroadcastState();
  }
};

// ----------------- 4. TIKTOK LIVE & VOTING (GĐ3) -----------------
async function loadVotingState() {
  try {
    const v = await api("/api/voting/state");
    $("#currentSessionId").textContent = v.session_id;

    const b = $("#votingStatusBadge");
    if (v.enabled) {
      b.textContent = "Bình chọn: ĐANG BẬT";
      b.className = "badge-active";
    } else {
      b.textContent = "Bình chọn: ĐÃ TẮT";
      b.className = "warn";
    }

    // Leaderboard
    $("#leaderboardRows").innerHTML = v.leaderboard.map((it) => `
      <tr>
        <td><b>${it.rank}</b></td>
        <td><span class="badge-code">${esc(it.code)}</span></td>
        <td><b>${esc(it.title)}</b><br><small style="color:#94a3b8">${esc(it.artist)}</small></td>
        <td>${esc(it.category || "")}</td>
        <td><b style="color:#38ef7d;font-size:14px">${it.points}</b></td>
      </tr>
    `).join("") || '<tr><td colspan="5" style="text-align:center;color:#64748b">Chưa có lượt bình chọn nào trong vòng này.</td></tr>';

    // Ready codes chips
    $("#readyCodesChips").innerHTML = v.ready_codes.map((c) => `
      <div class="code-chip" data-code="${esc(c.code)}" title="${esc(c.title)} - ${esc(c.artist)}">
        ${esc(c.code)}: ${esc(c.title.slice(0, 18))}...
      </div>
    `).join("") || '<span style="color:#64748b;font-size:12px">Chưa có bài nào ready để vote. Hãy cấp quyền và gán file MP4 cho bài hát.</span>';
  } catch (e) {
    console.error("loadVotingState error:", e);
  }
}

$("#readyCodesChips").onclick = (e) => {
  const chip = e.target.closest(".code-chip");
  if (!chip) return;
  const code = chip.dataset.code;
  $("#simCText").value = code;
  $("#simGCode").value = code;
};

$("#btnToggleVoting").onclick = async () => {
  try {
    const cur = $("#votingStatusBadge").textContent.includes("BẬT");
    await api("/api/voting/toggle", { method: "POST", body: JSON.stringify({ enabled: !cur }) });
    loadVotingState();
  } catch (e) { alert("Lỗi bật/tắt: " + e.message); }
};

$("#btnFinalizeVoting").onclick = async () => {
  if (!confirm("Chốt vòng bình chọn này? Bài hát Top 1 sẽ được tự động thêm vào Hàng đợi (Queue) và phiên mới sẽ bắt đầu.")) return;
  try {
    const res = await api("/api/voting/finalize", { method: "POST" });
    if (res.winner) {
      alert(`🎉 Bài thắng cuộc: ${res.winner.title} (${res.winner.code}) với ${res.winner.points} phiếu đã được đưa vào hàng đợi!`);
    } else {
      alert("Chưa có bài nào có phiếu bầu trong vòng này. Đã đặt lại phiên mới.");
    }
    loadStats();
    loadQueue();
    loadVotingState();
    loadBroadcastState();
  } catch (e) { alert("Lỗi chốt vòng: " + e.message); }
};

$("#btnResetVoting").onclick = async () => {
  if (!confirm("Đặt lại điểm phiên mới?")) return;
  try {
    await api("/api/voting/reset", { method: "POST" });
    loadVotingState();
  } catch (e) { alert("Lỗi đặt lại: " + e.message); }
};

// Simulation Console
$("#btnSimComment").onclick = async () => {
  const user_name = $("#simCUser").value.trim() || "Khán giả";
  const text = $("#simCText").value.trim();
  if (!text) return;
  try {
    const res = await api("/api/tiktok/simulate/comment", {
      method: "POST",
      body: JSON.stringify({ user_id: "usr_" + user_name, user_name, text }),
    });
    if (!res.vote_result.ok) {
      alert("Kết quả vote: " + (res.vote_result.reason || "Không thành công"));
    }
    loadVotingState();
    loadTikTokEvents();
    loadStats();
  } catch (e) { alert("Lỗi giả lập comment: " + e.message); }
};

$("#btnSimGift").onclick = async () => {
  const user_name = $("#simGUser").value.trim() || "Fan VIP";
  const [gift_name, diamonds] = $("#simGGift").value.split("|");
  const codeRaw = $("#simGCode").value.trim();
  let video_id = null;
  if (codeRaw) {
    const m = codeRaw.match(/\d+/);
    if (m) video_id = parseInt(m[0], 10);
  }
  try {
    const res = await api("/api/tiktok/simulate/gift", {
      method: "POST",
      body: JSON.stringify({
        user_id: "vip_" + user_name,
        user_name,
        gift_name,
        diamonds: parseInt(diamonds, 10),
        repeat: 1,
        video_id,
      }),
    });
    if (!res.vote_result.ok) {
      alert("Kết quả vote quà: " + (res.vote_result.reason || "Không thành công"));
    }
    loadVotingState();
    loadTikTokEvents();
    loadStats();
  } catch (e) { alert("Lỗi tặng quà: " + e.message); }
};

async function loadTikTokEvents() {
  try {
    const evs = await api("/api/tiktok/events?limit=20");
    $("#simEventsStream").innerHTML = evs.map((e) => `
      <div class="event-item">
        <span class="time">[${esc(e.created_at.slice(11, 19))}]</span>
        <span class="user">${esc(e.user_name)}</span>:
        <span class="${e.event_type === 'gift' ? 'gift' : ''}">${esc(e.detail)}</span>
      </div>
    `).join("") || '<div style="color:#64748b;padding:8px">Chưa có sự kiện TikTok LIVE nào...</div>';
  } catch (e) {
    console.error("loadTikTokEvents error:", e);
  }
}

// ----------------- 5. THƯ VIỆN MV -----------------
async function loadVideos() {
  const p = new URLSearchParams({
    q: $("#q").value,
    rights: $("#fRights").value,
    category: $("#fCat").value,
  });
  const vs = await api("/api/videos?" + p);
  $("#rows").innerHTML = vs.map((v) => `
    <tr data-id="${v.id}">
      <td><span class="badge-code">#${v.id}</span></td>
      <td><img src="${esc(v.thumbnail)}" loading="lazy"></td>
      <td>
        <a href="https://www.youtube.com/watch?v=${esc(v.youtube_id)}" target="_blank" rel="noopener" style="color:#fff;font-weight:700">${esc(v.title)}</a>
        <br><small style="color:#94a3b8">${esc(v.artist)} · ${esc(v.channel)}</small>
      </td>
      <td><b>${esc(v.category)}</b><br><small style="color:#94a3b8">${esc(v.genres)}</small></td>
      <td>${fmt(v.duration)}</td>
      <td>
        <select data-f="rights_status">
          ${["pending", "licensed", "blocked"].map((x) => `<option ${x === v.rights_status ? "selected" : ""}>${x}</option>`).join("")}
        </select>
        <br>${v.ready ? '<span class="ready-pill">ready_to_broadcast</span>' : ''}
      </td>
      <td>
        <input data-f="playback_source" value="${esc(v.playback_source)}" placeholder="D:\\media\\bai-hat.mp4" style="width:100%">
        ${v.playback_source && !v.file_exists ? '<span class="file-missing">⚠️ File không tồn tại trên ổ đĩa</span>' : ''}
      </td>
      <td>
        <div style="display:flex;flex-direction:column;gap:3px">
          <button class="btn-primary-sm" data-addq="${v.id}" ${v.ready ? "" : "disabled"} title="${v.ready ? 'Thêm vào hàng đợi' : 'Chỉ thêm được khi bài đã licensed và có file MP4'}">+ Đợi</button>
          <button class="btn-secondary-sm" data-gentest="${v.id}" title="Tạo video MP4 test 25s bằng FFmpeg" style="padding:2px 5px;font-size:10px">🎬 Test MP4</button>
          <button class="btn-secondary-sm" data-upload="${v.id}" title="Upload file video từ máy" style="padding:2px 5px;font-size:10px">📁 Upload</button>
        </div>
      </td>
      <td><input type="checkbox" data-f="enabled" ${v.enabled ? "checked" : ""}></td>
      <td><button class="btn-danger" data-delv="${v.id}" style="padding:4px 8px;font-size:11px">Xóa</button></td>
    </tr>
  `).join("") || '<tr><td colspan="10" style="text-align:center;padding:20px;color:#64748b">Không tìm thấy MV nào phù hợp.</td></tr>';
}

let uploadTargetVid = null;
const fileInput = $("#fileUploadInput");
fileInput.onchange = async () => {
  if (!fileInput.files.length || !uploadTargetVid) return;
  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch(`/api/videos/${uploadTargetVid}/upload`, { method: "POST", body: formData });
    if (!res.ok) throw new Error((await res.json()).detail || "Upload thất bại");
    alert("Đã upload và gắn file MP4 thành công cho bài hát!");
    refresh();
  } catch (err) {
    alert("Lỗi upload: " + err.message);
  } finally {
    fileInput.value = "";
    uploadTargetVid = null;
  }
};

$("#btnGenBatchTest").onclick = async () => {
  if (!confirm("Tạo hàng loạt 5 video test MP4 Full HD (25s) bằng FFmpeg cho các bài hát đầu tiên để kiểm thử?")) return;
  try {
    const res = await api("/api/videos/generate-batch-test?count=5&duration=25", { method: "POST" });
    alert(`Đã tạo thành công ${res.filter(r => r.ok).length} video test MP4! Bây giờ bạn có thể bấm 'Bắt đầu phát' và mở OBS Overlay để xem phát sóng.`);
    refresh();
  } catch (err) {
    alert("Lỗi tạo batch test: " + err.message);
  }
};

$("#rows").onchange = async (e) => {
  const f = e.target.dataset.f;
  if (!f) return;
  const id = e.target.closest("tr").dataset.id;
  const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;
  await api("/api/videos/" + id, { method: "PUT", body: JSON.stringify({ [f]: val }) });
  loadStats();
  loadVotingState();
  if (f !== "enabled") loadVideos();
};

$("#rows").onclick = async (e) => {
  if (e.target.dataset.delv) {
    if (!confirm("Xóa bài hát này khỏi thư viện?")) return;
    await api("/api/videos/" + e.target.dataset.delv, { method: "DELETE" });
    refresh();
  } else if (e.target.dataset.addq) {
    try {
      await api("/api/queue", { method: "POST", body: JSON.stringify({ video_id: parseInt(e.target.dataset.addq, 10) }) });
      alert("Đã thêm vào hàng đợi!");
      loadQueue();
      loadBroadcastState();
      loadStats();
    } catch (err) { alert("Lỗi thêm hàng đợi: " + err.message); }
  } else if (e.target.dataset.gentest) {
    const vid = e.target.dataset.gentest;
    e.target.disabled = true;
    e.target.textContent = "⏳...";
    try {
      await api(`/api/videos/${vid}/generate-test?duration=25`, { method: "POST" });
      alert("Đã tạo video MP4 test 25s thành công và cấp quyền phát!");
      refresh();
    } catch (err) {
      alert("Lỗi tạo video test: " + err.message);
      e.target.disabled = false;
      e.target.textContent = "🎬 Test MP4";
    }
  } else if (e.target.dataset.upload) {
    uploadTargetVid = e.target.dataset.upload;
    fileInput.click();
  }
};

$("#btnCleanCompilations").onclick = async () => {
  if (!confirm("Hệ thống sẽ tự động quét và xóa các video tổng hợp, liên khúc, album, playlist hoặc video quá dài (> 10 phút) khỏi thư viện. Bạn có muốn dọn dẹp?")) return;
  try {
    const res = await api("/api/videos/clean-compilations", { method: "POST", body: JSON.stringify({ action: "delete" }) });
    alert(`Đã dọn dẹp thành công ${res.count} video tổng hợp / không hợp lệ khỏi thư viện!`);
    refresh();
  } catch (e) {
    alert("Lỗi dọn dẹp: " + e.message);
  }
};

let searchTimer;
$("#q").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadVideos, 300); };
$("#fRights").onchange = $("#fCat").onchange = loadVideos;

// ----------------- 6. YOUTUBE DISCOVERY -----------------
async function loadKeywords() {
  const ks = await api("/api/keywords");
  $("#keywords").innerHTML = ks.map((k) =>
    `<div class="chip"><span>${esc(k.keyword)}</span>
     <button class="btn-primary" data-run="${esc(k.keyword)}">Quét</button>
     <button class="btn-danger" data-del="${k.id}">✕</button></div>`).join("");
}

$("#addKw").onclick = async () => {
  const keyword = $("#kw").value.trim();
  if (!keyword) return;
  await api("/api/keywords", { method: "POST", body: JSON.stringify({ keyword }) });
  $("#kw").value = "";
  loadKeywords();
};

async function discover(body, btn) {
  btn.disabled = true;
  $("#discoverResult").textContent = "Đang thu thập dữ liệu từ YouTube...";
  try {
    const res = await api("/api/discover", { method: "POST", body: JSON.stringify(body) });
    $("#discoverResult").textContent = res.map((r) => `${r.keyword}: tìm thấy ${r.found}, thêm mới ${r.added}${r.error ? " – LỖI: " + r.error : ""}`).join("\n");
  } catch (e) {
    $("#discoverResult").textContent = "Lỗi: " + e.message;
  }
  btn.disabled = false;
  refresh();
}

$("#runAll").onclick = (e) => discover({}, e.target);
$("#keywords").onclick = async (e) => {
  if (e.target.dataset.run) discover({ keyword: e.target.dataset.run }, e.target);
  if (e.target.dataset.del) {
    await api("/api/keywords/" + e.target.dataset.del, { method: "DELETE" });
    loadKeywords();
  }
};

// ----------------- 7. TABS: HISTORY, VOTES, LOGS -----------------
async function loadHistory() {
  try {
    const hs = await api("/api/history");
    $("#historyRows").innerHTML = hs.map((h) => `
      <tr>
        <td>${esc(h.started_at)}</td>
        <td><b>${esc(h.title)}</b></td>
        <td>${esc(h.artist)}</td>
        <td>${esc(h.category)}</td>
        <td>${fmt(h.duration)}</td>
      </tr>
    `).join("") || '<tr><td colspan="5" style="text-align:center;color:#64748b">Chưa có lịch sử phát.</td></tr>';
  } catch (e) { console.error("loadHistory error:", e); }
}

async function loadVotesHistory() {
  try {
    const vs = await api("/api/voting/history");
    $("#votesRows").innerHTML = vs.map((v) => `
      <tr>
        <td>${esc(v.created_at)}</td>
        <td><code>${esc(v.session_id)}</code></td>
        <td><b>${esc(v.user_name)}</b></td>
        <td>#${v.video_id} ${esc(v.title)}</td>
        <td><span class="badge-${v.vote_type === 'gift' ? 'sim' : 'code'}">${esc(v.vote_type)}</span></td>
        <td><b>+${v.points}</b></td>
        <td><small>${esc(v.raw_content)}</small></td>
      </tr>
    `).join("") || '<tr><td colspan="7" style="text-align:center;color:#64748b">Chưa có lượt vote nào được ghi nhận.</td></tr>';
  } catch (e) { console.error("loadVotesHistory error:", e); }
}

async function loadLogs() {
  const ls = await api("/api/logs");
  $("#logs").innerHTML = ls.map((l) =>
    `<tr><td>${esc(l.created_at)}</td><td>${esc(l.keyword)}</td><td>${l.found}</td><td>${l.added}</td><td>${esc(l.error)}</td></tr>`).join("") ||
    '<tr><td colspan="5" style="text-align:center;color:#64748b">Chưa có nhật ký thu thập.</td></tr>';
}

$$(".tab-btn").forEach((btn) => {
  btn.onclick = () => {
    $$(".tab-btn").forEach((b) => b.classList.remove("active"));
    $$(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
  };
});

async function loadDashTicker() {
  try {
    const vs = await api("/api/videos?limit=100");
    if (!vs || !vs.length) return;
    const items = vs.map((v) => `
      <span class="dash-t-item">
        <code>${esc(v.code)}</code>
        <b>${esc(v.title)}</b>
        <span style="color:#94a3b8">(${esc(v.artist || v.channel)})</span>
      </span>
      <span class="dash-t-sep">✦</span>
    `).join("");
    const guide = `<span class="dash-t-item" style="color:var(--cyan);font-weight:700">🗳️ Cú pháp bình chọn: Comment #MÃ trên livestream</span><span class="dash-t-sep">✦</span>`;
    const full = guide + items;
    const track = $("#dashTickerTrack");
    if (track) track.innerHTML = full + full;
  } catch (e) {
    console.error("loadDashTicker error:", e);
  }
}

const speedRange = $("#tickerSpeedRange");
const speedVal = $("#tickerSpeedVal");
const dashTrack = $("#dashTickerTrack");

function applyTickerSpeed(sec) {
  if (dashTrack) {
    dashTrack.style.setProperty("--dash-ticker-speed", `${sec}s`);
    dashTrack.style.animationDuration = `${sec}s`;
  }
  if (speedRange) speedRange.value = sec;
  if (speedVal) speedVal.textContent = `${sec}s`;
}

async function loadTickerSpeed() {
  try {
    const res = await api("/api/broadcast/ticker-speed");
    applyTickerSpeed(res.speed || 180);
  } catch (e) {}
}

let speedDebounceTimer;
if (speedRange) {
  speedRange.oninput = () => {
    const sec = parseInt(speedRange.value, 10);
    applyTickerSpeed(sec);
    clearTimeout(speedDebounceTimer);
    speedDebounceTimer = setTimeout(async () => {
      try {
        await api("/api/broadcast/ticker-speed", { method: "PUT", body: JSON.stringify({ speed: sec }) });
      } catch (e) {
        console.error("Failed to save ticker speed:", e);
      }
    }, 400);
  };
}

// ----------------- REFRESH & INTERVAL -----------------
const refresh = () => Promise.all([
  loadStats(),
  loadBroadcastState(),
  loadQueue(),
  loadVotingState(),
  loadTikTokEvents(),
  loadVideos(),
  loadKeywords(),
  loadHistory(),
  loadVotesHistory(),
  loadLogs(),
  loadDashTicker(),
  loadTickerSpeed(),
]);

// Initial load
loadBroadcastSettings();
refresh();

// Polling định kỳ mỗi 3 giây cho trạng thái Broadcast và TikTok LIVE
setInterval(() => {
  loadStats();
  loadBroadcastState();
  loadVotingState();
  loadTikTokEvents();
}, 3000);
