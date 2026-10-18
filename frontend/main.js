let ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/chat`);
let mediaRecorder;
let audioQueue = [];
let videoQueue = [];
let isPlaying = false;
let audioCtx = new (window.AudioContext || window.webkitAudioContext)();

const statusDiv   = document.getElementById("status");
const chatBox     = document.getElementById("chat-box");
const textInput   = document.getElementById("text-input");
const sendBtn     = document.getElementById("send-btn");
const micBtn      = document.getElementById("mic-btn");
const avatar      = document.getElementById("avatar-container");
const avatarToggle= document.getElementById("avatar-toggle");
const avatarImage = document.getElementById("avatar-image");
const avatarVideo = document.getElementById("avatar-video");
const engineSelect= document.getElementById("engine-select");
const ttsSelect   = document.getElementById("tts-select");
const modelSelect = document.getElementById("model-select");
const modelBadge  = document.getElementById("model-badge");
const timingPanel    = document.getElementById("timing-panel");
const historyCount   = document.getElementById("history-count");
const clearBtn       = document.getElementById("clear-btn");
const savedVideoWrap = document.getElementById("saved-video-wrap");
const savedVideoEl   = document.getElementById("saved-video");

let avatarMode   = false;
let exchangeCount = 0;

// ── Load available LLM models ────────────────────────────────────
async function loadModels() {
    try {
        const resp = await fetch("/api/models");
        const data = await resp.json();
        modelSelect.innerHTML = "";
        data.models.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m.startsWith("cloud:") ? "☁ " + m.replace("cloud:", "") : m;
            if (m === data.default) opt.selected = true;
            modelSelect.appendChild(opt);
        });
        updateModelBadge(modelSelect.value);
    } catch (e) {
        console.warn("Could not load models:", e);
    }
}

function updateModelBadge(name) {
    modelBadge.textContent = name.startsWith("cloud:") ? "☁ Cloud" : name.split(":")[0];
}

loadModels();

// ── Load available lipsync engines (only those installed on this host) ──
async function loadEngines() {
    try {
        const resp = await fetch("/api/engines");
        const data = await resp.json();
        engineSelect.innerHTML = "";
        if (!data.engines || data.engines.length === 0) {
            engineSelect.innerHTML = '<option value="">(no engines)</option>';
            return;
        }
        data.engines.forEach(name => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name.charAt(0).toUpperCase() + name.slice(1);
            if (name === data.default) opt.selected = true;
            engineSelect.appendChild(opt);
        });
    } catch (e) {
        console.warn("Could not load engines:", e);
    }
}
const enginesReady = loadEngines();

// ── Chat helpers ────────────────────────────────────────────────
let currentTeacherBubble = null;

function addUserBubble(text) {
    const msg = document.createElement("div");
    msg.className = "msg msg-you";
    msg.innerHTML = `<span class="msg-label">YOU</span><span class="msg-bubble">${text}</span>`;
    chatBox.appendChild(msg);
    scrollChat();
}

function startTeacherBubble() {
    const msg = document.createElement("div");
    msg.className = "msg msg-teacher";
    msg.innerHTML = `<span class="msg-label">TEACHER</span><span class="msg-bubble"></span>`;
    chatBox.appendChild(msg);
    currentTeacherBubble = msg.querySelector(".msg-bubble");
    scrollChat();
}

function appendToTeacherBubble(text) {
    if (!currentTeacherBubble) startTeacherBubble();
    currentTeacherBubble.textContent += text;
    scrollChat();
}

function addErrorNote(text) {
    const note = document.createElement("div");
    note.className = "lipsync-error";
    note.textContent = "⚠ Lipsync error: " + text;
    chatBox.appendChild(note);
    scrollChat();
}

function scrollChat() {
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ── WebSocket ────────────────────────────────────────────────────
ws.onopen = async () => {
    await enginesReady;
    statusDiv.innerText = "Connected";
    statusDiv.className = "connected";
    ws.send(JSON.stringify({ type: "set_mode", avatar: avatarToggle.checked }));
    ws.send(JSON.stringify({ type: "set_engine", engine: engineSelect.value }));
    ws.send(JSON.stringify({ type: "set_tts", tts: ttsSelect.value }));
    ws.send(JSON.stringify({ type: "set_model", model: modelSelect.value }));
    ttsSelect.disabled = false;
};
ws.onclose = () => {
    statusDiv.innerText = "Disconnected";
    statusDiv.className = "disconnected";
};

ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === "transcript") {
        addUserBubble(msg.data);
        startTeacherBubble();
    }
    else if (msg.type === "text_chunk") {
        appendToTeacherBubble(msg.data);
    }
    else if (msg.type === "audio_chunk") {
        if (avatarMode) {
            avatarVideo.style.display = "none";
            avatarImage.style.display = "block";
        }
        audioQueue.push(msg.data);
        if (!isPlaying) playNextAudio();
    }
    else if (msg.type === "video_chunk") {
        avatarImage.style.display = "none";
        avatarVideo.style.display = "block";
        videoQueue.push(msg.data);
        console.log(`[video_chunk] queue=${videoQueue.length} isPlaying=${isPlaying}`);
        if (!isPlaying) playNextVideo();
    }
    else if (msg.type === "lipsync_error") {
        addErrorNote(`${msg.engine} — ${msg.detail}`);
    }
    else if (msg.type === "mode_ack") {
        avatarMode = msg.avatar;
    }
    else if (msg.type === "engine_ack") {
        console.log("Engine confirmed:", msg.engine);
    }
    else if (msg.type === "tts_ack") {
        console.log("TTS confirmed:", msg.tts);
    }
    else if (msg.type === "model_ack") {
        updateModelBadge(msg.model);
        console.log("LLM model confirmed:", msg.model);
    }
    else if (msg.type === "history_cleared") {
        exchangeCount = 0;
        historyCount.textContent = "No history yet";
        chatBox.innerHTML = "";
        const note = document.createElement("div");
        note.className = "msg msg-teacher";
        note.innerHTML = `<span class="msg-label">TEACHER</span><span class="msg-bubble">History cleared. Start a new conversation!</span>`;
        chatBox.appendChild(note);
        currentTeacherBubble = null;
    }
    else if (msg.type === "timing") {
        document.getElementById("timing-engine").textContent =
            msg.engine.toUpperCase() +
            (msg.tts ? " · " + msg.tts.toUpperCase() : "") +
            (msg.model ? " · " + msg.model.split(":")[0] : "");
        document.getElementById("t-total").textContent     = msg.total + "s";
        document.getElementById("t-llm").textContent       = msg.llm + "s";
        document.getElementById("t-tts-avg").textContent   = msg.tts_avg + "s";
        document.getElementById("t-tts-total").textContent = msg.tts_total + "s";
        document.getElementById("t-ls-avg").textContent    = msg.lipsync_avg + "s";
        document.getElementById("t-ls-total").textContent  = msg.lipsync_total + "s";
        document.getElementById("t-sentences").textContent = msg.sentences;
        timingPanel.classList.add("visible");
    }
    else if (msg.type === "video_saved") {
        const ts = Date.now();
        const url = msg.url + "?t=" + ts;

        // Show in dedicated saved-video panel with controls, no autoplay
        // (avoids replaying the answer a second time after the live stream).
        savedVideoEl.src = url;
        savedVideoWrap.style.display = "block";
        savedVideoEl.load();

        // Download link in chat
        const note = document.createElement("div");
        note.style.cssText = "font-size:11px; color:#6b7280; margin:4px 0;";
        note.innerHTML = `<a href="${url}" download="response.mp4" style="color:#38bdf8;">⬇ Download video</a>`;
        chatBox.appendChild(note);
        scrollChat();
    }
    else if (msg.type === "end_of_response") {
        currentTeacherBubble = null;
        exchangeCount++;
        historyCount.textContent = `${exchangeCount} exchange${exchangeCount !== 1 ? "s" : ""} in memory`;
    }
};

// ── Controls ─────────────────────────────────────────────────────
avatarToggle.addEventListener("change", () => {
    avatarMode = avatarToggle.checked;
    ws.send(JSON.stringify({ type: "set_mode", avatar: avatarMode }));
    avatarVideo.style.display = avatarMode ? "block" : "none";
    avatarImage.style.display = avatarMode ? "none" : "block";
    engineSelect.disabled = !avatarMode;
});

engineSelect.addEventListener("change", () => {
    ws.send(JSON.stringify({ type: "set_engine", engine: engineSelect.value }));
});

ttsSelect.addEventListener("change", () => {
    ws.send(JSON.stringify({ type: "set_tts", tts: ttsSelect.value }));
    ttsSelect.disabled = false;
});

modelSelect.addEventListener("change", () => {
    ws.send(JSON.stringify({ type: "set_model", model: modelSelect.value }));
    updateModelBadge(modelSelect.value);
});

clearBtn.addEventListener("click", () => {
    ws.send(JSON.stringify({ type: "clear_history" }));
});

// ── Send text ─────────────────────────────────────────────────────
sendBtn.onclick = () => {
    const text = textInput.value.trim();
    if (!text) return;
    addUserBubble(text);
    startTeacherBubble();
    ws.send(JSON.stringify({ type: "text", data: text }));
    textInput.value = "";
};

textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendBtn.onclick();
});

// ── Mic (hold to speak) ───────────────────────────────────────────
micBtn.onmousedown = async () => {
    audioQueue = [];
    videoQueue = [];
    micBtn.classList.add("recording");
    micBtn.innerText = "Listening...";
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
            const reader = new FileReader();
            reader.onloadend = () => {
                ws.send(JSON.stringify({ type: "audio_chunk", data: reader.result.split(",")[1] }));
            };
            reader.readAsDataURL(e.data);
        }
    };
    mediaRecorder.start();
};

micBtn.onmouseup = () => {
    micBtn.classList.remove("recording");
    micBtn.innerText = "🎙 Hold";
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        ws.send(JSON.stringify({ type: "audio_end" }));
    }
};

// ── Audio playback ────────────────────────────────────────────────
const PAUSE_MS = 300;   // breathing pause between sentence chunks (D-017)
async function playNextAudio() {
    if (audioQueue.length === 0) { isPlaying = false; avatar.classList.remove("talking"); return; }
    isPlaying = true;
    avatar.classList.add("talking");
    const b64 = audioQueue.shift();
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    try {
        const buf = await audioCtx.decodeAudioData(bytes.buffer.slice(0));
        const src = audioCtx.createBufferSource();
        src.buffer = buf;
        src.connect(audioCtx.destination);
        src.onended = () => setTimeout(playNextAudio, PAUSE_MS);
        src.start(0);
    } catch (e) { console.error("Audio decode error", e); playNextAudio(); }
}

// ── Video playback ────────────────────────────────────────────────
function playNextVideo() {
    if (videoQueue.length === 0) { isPlaying = false; avatar.classList.remove("talking"); return; }
    isPlaying = true;
    avatar.classList.add("talking");
    const b64 = videoQueue.shift();
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: "video/mp4" });
    console.log(`[playNextVideo] blob size=${blob.size} remaining=${videoQueue.length}`);
    const url = URL.createObjectURL(blob);
    avatarVideo.src = url;
    avatarVideo.onended = () => { URL.revokeObjectURL(url); playNextVideo(); };
    avatarVideo.onerror = (e) => { console.error("Video error", avatarVideo.error); URL.revokeObjectURL(url); playNextVideo(); };
    avatarVideo.play().catch((e) => { console.error("Video play error", e); playNextVideo(); });
}
