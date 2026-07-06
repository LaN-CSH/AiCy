// AiCy Viewer — Stage 0 Prototype
// Live2D model display + audio lip sync

(function () {
  "use strict";

  const { Live2DModel } = PIXI.live2d;

  // --- Config ---
  // Swappable models. Override at runtime with ?model=<key|url>.
  //   ?model=haru  → official Live2D sample (CDN, license-clean fallback)
  //   ?model=<url> → any model3.json path/URL
  // Default 'xl' is self-hosted under frontend/models/ (gitignored).
  const MODELS = {
    xl: { url: "models/xl/xl.model3.json", name: "xl (VTS)" },
    haru: {
      url: "https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/haru/haru_greeter_t03.model3.json",
      name: "Haru (sample)",
    },
  };
  const DEFAULT_MODEL_KEY = "xl";

  function resolveModel() {
    var q = new URLSearchParams(window.location.search).get("model");
    if (q && MODELS[q]) return MODELS[q];
    if (q) return { url: q, name: q };
    return MODELS[DEFAULT_MODEL_KEY];
  }

  // ?broadcast=1 → OBS 브라우저 소스용 클린 뷰 (아바타+자막만, H키로 복원 가능)
  // ?bg=transparent → 배경 투명 (OBS에서 다른 배경 위에 아바타 합성용)
  const _params = new URLSearchParams(window.location.search);
  const BROADCAST_MODE = _params.get("broadcast") === "1";
  const TRANSPARENT_BG = _params.get("bg") === "transparent";

  const TEST_AUDIO = "../audio/tts-audio.mp3";
  const WS_URL = "ws://localhost:8765";
  const BG_COLOR = 0x0d0d1a;
  const LIP_SYNC_SMOOTHING = 0.4;
  const LIP_SYNC_GAIN = 4.0;

  // --- DOM refs ---
  const ui = {
    canvas: document.getElementById("canvas"),
    loadingOverlay: document.getElementById("loading-overlay"),
    loadingText: document.getElementById("loading-text"),
    stModel: document.getElementById("st-model"),
    stState: document.getElementById("st-state"),
    stLipsync: document.getElementById("st-lipsync"),
    stWs: document.getElementById("st-ws"),
    stTts: document.getElementById("st-tts"),
    btnSpeak: document.getElementById("btn-speak"),
    btnMotion: document.getElementById("btn-motion"),
    btnExpression: document.getElementById("btn-expression"),
    chatInput: document.getElementById("chat-input"),
    chatSend: document.getElementById("chat-send"),
    chatMessages: document.getElementById("chat-messages"),
    liveMessages: document.getElementById("live-messages"),
    caption: document.getElementById("caption"),
  };

  // --- State ---
  let app = null;
  let model = null;
  let audioContext = null;
  let analyser = null;
  let audioElement = null;
  let audioSource = null;
  let lipSyncActive = false;
  let smoothedVolume = 0;
  let mouthParamIndex = -1;
  let expressionIndex = 0;
  let ws = null;
  let pendingSpeak = null;
  let currentObjectUrl = null;
  let userAdjusted = false; // user zoomed/panned → don't auto-recenter on resize
  let dragging = false;
  const dragStart = { x: 0, y: 0 };
  const modelStart = { x: 0, y: 0 };

  // --- Status helpers ---
  function setStatus(key, text, cls) {
    const el = ui["st" + key.charAt(0).toUpperCase() + key.slice(1)];
    if (!el) return;
    el.textContent = text;
    el.className = "value" + (cls ? " " + cls : "");
  }

  function setLoading(text) {
    ui.loadingText.textContent = text;
  }

  // --- Audio volume analysis ---
  function initAudio() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;

    audioElement = new Audio();
    audioElement.crossOrigin = "anonymous";
    audioSource = audioContext.createMediaElementSource(audioElement);
    audioSource.connect(analyser);
    analyser.connect(audioContext.destination);

    audioElement.addEventListener("ended", onAudioEnd);
    audioElement.addEventListener("pause", onAudioEnd);
    audioElement.addEventListener("error", function (e) {
      console.error("Audio error:", e);
      setStatus("lipsync", "audio error", "err");
      onAudioEnd();
    });
  }

  function getRawVolume() {
    if (!analyser) return 0;
    var data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);
    var sum = 0;
    for (var i = 0; i < data.length; i++) {
      var v = (data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(Math.sqrt(sum / data.length) * LIP_SYNC_GAIN, 1.0);
  }

  function onAudioEnd() {
    lipSyncActive = false;
    smoothedVolume = 0;
    // 큐에 다음 문장이 있으면 끊김 없이 이어 재생
    if (audioQueue.length > 0) {
      playNextInQueue();
      return;
    }
    queuePlaying = false;
    setStatus("state", "idle", "ok");
    setStatus("lipsync", "off");
    ui.btnSpeak.disabled = false;
    // Free blob URL from WebSocket-delivered audio
    if (currentObjectUrl) {
      URL.revokeObjectURL(currentObjectUrl);
      currentObjectUrl = null;
    }
  }

  // --- Lip sync injection ---
  // Monkey-patch coreModel.update so lip sync is applied
  // right before Cubism finalizes drawables.
  function setupLipSync() {
    var coreModel = model.internalModel.coreModel;

    // Find ParamMouthOpenY index
    var internalModel = coreModel._model;
    if (internalModel && internalModel.parameters) {
      var params = internalModel.parameters;
      for (var i = 0; i < params.count; i++) {
        if (params.ids[i] === "ParamMouthOpenY") {
          mouthParamIndex = i;
          break;
        }
      }
    }

    if (mouthParamIndex < 0) {
      console.warn("ParamMouthOpenY not found — lip sync disabled");
      setStatus("lipsync", "no param", "warn");
      return;
    }

    var origUpdate = coreModel.update.bind(coreModel);
    coreModel.update = function () {
      if (lipSyncActive && mouthParamIndex >= 0) {
        var raw = getRawVolume();
        smoothedVolume =
          smoothedVolume * LIP_SYNC_SMOOTHING +
          raw * (1 - LIP_SYNC_SMOOTHING);
        coreModel.setParameterValueByIndex(mouthParamIndex, smoothedVolume);
      }
      origUpdate();
    };

    console.log(
      "Lip sync ready (ParamMouthOpenY at index " + mouthParamIndex + ")"
    );
  }

  // --- Speak ---
  function speak(audioUrl) {
    if (!audioContext || !audioElement) return;

    audioContext.resume().then(function () {
      audioElement.src = audioUrl;
      lipSyncActive = true;
      smoothedVolume = 0;
      audioElement.play().catch(function (e) {
        console.error("Play failed:", e);
        setStatus("lipsync", "play failed", "err");
        lipSyncActive = false;
      });

      setStatus("state", "speaking", "ok");
      setStatus("lipsync", "active", "ok");
      ui.btnSpeak.disabled = true;
    });
  }

  // --- Chat: messenger-style panel (user right / AiCy left) ---
  let pendingBubble = null; // "생각 중..." 말풍선, 답변 도착 시 교체

  function showCaption(text) {
    ui.caption.textContent = text;
    ui.caption.style.display = text ? "block" : "none";
  }

  function addMsg(role, text, pending) {
    var el = document.createElement("div");
    el.className = "msg " + role + (pending ? " pending" : "");
    el.textContent = text;
    ui.chatMessages.appendChild(el);
    ui.chatMessages.scrollTop = ui.chatMessages.scrollHeight;
    return el;
  }

  function resolveAicyMsg(text) {
    if (pendingBubble) {
      pendingBubble.textContent = text;
      pendingBubble.classList.remove("pending");
      pendingBubble = null;
    } else {
      addMsg("aicy", text); // 콘솔 입력 등 패널 밖 경로로 온 답변
    }
    ui.chatMessages.scrollTop = ui.chatMessages.scrollHeight;
  }

  // --- Live Chat panel (오른쪽 아래): 방송 시청자 채팅 + AiCy 답변 ---
  function addLiveMsg(nick, text, isAicy) {
    var el = document.createElement("div");
    el.className = "live-msg" + (isAicy ? " aicy-reply" : "");
    var nickEl = document.createElement("span");
    nickEl.className = "nick";
    nickEl.textContent = nick;
    el.appendChild(nickEl);
    el.appendChild(document.createTextNode(text));
    ui.liveMessages.appendChild(el);
    // 오래된 메시지 정리 (200개 유지)
    while (ui.liveMessages.childNodes.length > 200) {
      ui.liveMessages.removeChild(ui.liveMessages.firstChild);
    }
    ui.liveMessages.scrollTop = ui.liveMessages.scrollHeight;
  }

  function sendChat() {
    var text = ui.chatInput.value.trim();
    if (!text) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setStatus("ws", "not connected", "err");
      return;
    }
    ws.send(JSON.stringify({ type: "chat", text: text }));
    ui.chatInput.value = "";
    addMsg("user", text);
    pendingBubble = addMsg("aicy", "생각 중...", true);
    setStatus("state", "thinking...", "warn");
  }

  // --- WebSocket: receive AiCy audio from Python backend ---
  // Protocol: a JSON text frame {type:"speak", text, emotion, seq, last, full?}
  // followed by a binary mp3 frame. 백엔드가 문장 단위로 쪼개 보내므로
  // 오디오 큐에 쌓아 끊김 없이 순차 재생한다 (자막은 재생 시점에 동기화).
  let audioQueue = []; // {url, text}
  let queuePlaying = false;

  function enqueueAudio(arrayBuffer, meta) {
    var blob = new Blob([arrayBuffer], { type: "audio/mpeg" });
    audioQueue.push({
      url: URL.createObjectURL(blob),
      text: (meta && meta.text) || "",
    });
    if (!queuePlaying) playNextInQueue();
  }

  function playNextInQueue() {
    var item = audioQueue.shift();
    if (!item) {
      queuePlaying = false;
      return;
    }
    queuePlaying = true;
    if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
    currentObjectUrl = item.url;
    if (item.text) {
      showCaption(item.text);
      setStatus("state", "speaking: " + item.text.slice(0, 24), "ok");
    }
    speak(item.url);
  }

  function connectWS() {
    setStatus("ws", "connecting...", "warn");
    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";

    ws.onopen = function () {
      setStatus("ws", "connected", "ok");
      console.log("Backend connected:", WS_URL);
    };

    ws.onmessage = function (ev) {
      if (typeof ev.data === "string") {
        try {
          var msg = JSON.parse(ev.data);
          if (msg.type === "speak") pendingSpeak = msg;
          if (msg.type === "config") {
            // 백엔드가 알려주는 실제 구성 (TTS 백엔드 · 언어)
            setStatus("tts", msg.tts + " · " + msg.lang, "ok");
            console.log("Backend config:", msg);
          }
          if (msg.type === "live_chat") {
            // 방송 시청자 채팅 → 아래 라이브 패널
            addLiveMsg(msg.author, msg.text, false);
          }
          if (msg.type === "view") {
            // 다른 클라이언트(브라우저)에서 조절한 아바타 뷰를 그대로 반영
            applyNormView(msg);
          }
        } catch (e) {
          console.warn("Bad control message:", ev.data);
        }
        return;
      }
      // Binary frame = audio (문장 1개 분량)
      var meta = pendingSpeak;
      pendingSpeak = null;
      // 말풍선은 전체 답변으로 1회만 (첫 조각에 full 이 실려 옴)
      if (meta && meta.full) {
        if (meta.source === "youtube") {
          // 방송 채팅에 대한 답변 → 라이브 패널에 AiCy 답변으로
          addLiveMsg("AiCy", meta.full, true);
        } else {
          resolveAicyMsg(meta.full);
        }
      }
      enqueueAudio(ev.data, meta);
    };

    ws.onclose = function () {
      setStatus("ws", "disconnected", "warn");
      setStatus("tts", "-");
      ws = null;
      if (pendingBubble) {
        pendingBubble.textContent = "(연결이 끊겨 답을 받지 못했어요)";
        pendingBubble.classList.remove("pending");
        pendingBubble = null;
      }
      setTimeout(connectWS, 2000); // auto-reconnect
    };

    ws.onerror = function () {
      setStatus("ws", "error", "err");
    };
  }

  // Browsers suspend AudioContext until a user gesture. WebSocket audio can
  // arrive without one, so resume on the first click anywhere on the page.
  function enableAudioOnGesture() {
    function resume() {
      if (audioContext && audioContext.state === "suspended") {
        audioContext.resume();
      }
    }
    document.addEventListener("click", resume);
    document.addEventListener("keydown", resume);
  }

  // --- Zoom (mouse wheel) + pan (drag) ---
  const MIN_SCALE = 0.02;
  const MAX_SCALE = 5.0;
  const VIEW_KEY = "aicy-view"; // 로컬 백업 (백엔드 꺼져 있을 때용)
  let viewSendTimer = null;

  // 뷰는 창 크기와 무관한 정규화 좌표로 다룬다:
  //   nx, ny = 화면 대비 위치 비율, s = 자동맞춤 배율 대비 상대 배율
  // → 브라우저 창과 OBS(1920x1080)가 달라도 같은 프레이밍이 된다.
  function baseScale() {
    var nw = model.width / model.scale.x;
    var nh = model.height / model.scale.y;
    return Math.min(
      (app.screen.width / nw) * 0.5,
      (app.screen.height / nh) * 0.75
    );
  }

  function currentNormView() {
    return {
      nx: model.x / app.screen.width,
      ny: model.y / app.screen.height,
      s: model.scale.x / baseScale(),
    };
  }

  function applyNormView(v) {
    if (!model || !v || typeof v.s !== "number") return;
    model.anchor.set(0.5, 0.5);
    model.x = v.nx * app.screen.width;
    model.y = v.ny * app.screen.height;
    model.scale.set(v.s * baseScale());
    userAdjusted = true;
  }

  function saveView() {
    if (!model) return;
    var v = currentNormView();
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify(v));
    } catch (e) { /* storage 불가 환경 무시 */ }
    // 백엔드로 전송 → 다른 클라이언트(OBS 소스)에 실시간 반영 (150ms 디바운스)
    if (viewSendTimer) clearTimeout(viewSendTimer);
    viewSendTimer = setTimeout(function () {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "view", nx: v.nx, ny: v.ny, s: v.s }));
      }
    }, 150);
  }

  function restoreView() {
    try {
      var v = JSON.parse(localStorage.getItem(VIEW_KEY));
      if (!v || typeof v.nx !== "number") return false; // 구형식/없음
      applyNormView(v);
      return true;
    } catch (e) {
      return false;
    }
  }

  function setupZoomPan() {
    const canvas = ui.canvas;
    canvas.style.cursor = "grab";

    // Wheel = zoom toward the cursor position
    canvas.addEventListener(
      "wheel",
      function (e) {
        if (!model) return;
        e.preventDefault();
        userAdjusted = true;

        var factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
        var oldScale = model.scale.x;
        var newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, oldScale * factor));
        if (newScale === oldScale) return;

        var rect = canvas.getBoundingClientRect();
        var mx = e.clientX - rect.left;
        var my = e.clientY - rect.top;
        // keep the point under the cursor fixed while scaling
        var ds = newScale / oldScale;
        model.x = mx - (mx - model.x) * ds;
        model.y = my - (my - model.y) * ds;
        model.scale.set(newScale);
        saveView();
      },
      { passive: false }
    );

    // Drag = move the model
    canvas.addEventListener("pointerdown", function (e) {
      if (!model) return;
      dragging = true;
      userAdjusted = true;
      dragStart.x = e.clientX;
      dragStart.y = e.clientY;
      modelStart.x = model.x;
      modelStart.y = model.y;
      canvas.style.cursor = "grabbing";
    });
    window.addEventListener("pointermove", function (e) {
      if (!dragging || !model) return;
      model.x = modelStart.x + (e.clientX - dragStart.x);
      model.y = modelStart.y + (e.clientY - dragStart.y);
    });
    window.addEventListener("pointerup", function () {
      if (!dragging) return;
      dragging = false;
      canvas.style.cursor = "grab";
      saveView();
    });
  }

  // --- Model setup ---
  function positionModel() {
    if (!model || !app) return;
    var sw = app.screen.width;
    var sh = app.screen.height;

    model.anchor.set(0.5, 0.5);
    model.x = sw / 2;
    model.y = sh / 2;

    var scaleX = (sw / model.width) * 0.5;
    var scaleY = (sh / model.height) * 0.75;
    var s = Math.min(scaleX, scaleY);
    model.scale.set(s);
  }

  // --- Init ---
  async function init() {
    setLoading("Initializing PixiJS...");

    app = new PIXI.Application({
      view: ui.canvas,
      resizeTo: window,
      backgroundColor: BG_COLOR,
      backgroundAlpha: TRANSPARENT_BG ? 0 : 1,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });
    if (TRANSPARENT_BG) {
      document.body.style.background = "transparent";
    }

    var selected = resolveModel();
    setLoading("Loading Live2D model: " + selected.name + " ...");
    setStatus("state", "loading");

    try {
      model = await Live2DModel.from(selected.url, {
        autoInteract: false,
      });
    } catch (e) {
      console.error("Model load failed:", e);
      setLoading("Failed to load model (" + selected.name + "). Check console.");
      setStatus("model", "load failed", "err");
      return;
    }

    app.stage.addChild(model);
    positionModel();
    restoreView(); // 저장된 줌/위치가 있으면 복원 (OBS 리로드 대응)

    setStatus("model", selected.name, "ok");
    setStatus("state", "idle", "ok");

    // Resize handling — keep user's zoom/pan once they've adjusted
    window.addEventListener("resize", function () {
      if (!userAdjusted) positionModel();
    });

    // Mouse wheel zoom + drag to move
    setupZoomPan();

    // Init audio system
    initAudio();
    enableAudioOnGesture();

    // Setup lip sync
    setupLipSync();

    // Connect to Python backend (audio over WebSocket)
    connectWS();

    // Enable buttons
    ui.btnSpeak.disabled = false;
    ui.btnMotion.disabled = false;
    ui.btnExpression.disabled = false;

    // Wire up buttons
    ui.btnSpeak.addEventListener("click", function () {
      speak(TEST_AUDIO);
    });

    ui.btnMotion.addEventListener("click", function () {
      if (!model) return;
      var manager = model.internalModel.motionManager;
      var groups = Object.keys(manager.definitions);
      if (groups.length === 0) return;
      var group = groups[Math.floor(Math.random() * groups.length)];
      model.motion(group);
      setStatus("state", "motion: " + group, "ok");
    });

    ui.btnExpression.addEventListener("click", function () {
      if (!model) return;
      var defs = model.internalModel.motionManager.expressionManager;
      if (!defs || !defs.definitions || defs.definitions.length === 0) {
        setStatus("state", "no expressions", "warn");
        return;
      }
      expressionIndex = (expressionIndex + 1) % defs.definitions.length;
      model.expression(expressionIndex);
      setStatus("state", "expr #" + expressionIndex, "ok");
    });

    // Click on model
    model.on("hit", function (hitAreas) {
      if (hitAreas.length > 0) {
        model.motion("tap_body");
        setStatus("state", "hit: " + hitAreas.join(", "), "ok");
      }
    });

    // Chat input
    ui.chatSend.addEventListener("click", sendChat);
    ui.chatInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        sendChat();
      }
      e.stopPropagation(); // 입력 중 전역 단축키 방지
    });

    // Keyboard shortcuts
    document.addEventListener("keydown", function (e) {
      if (e.target === ui.chatInput) return; // 채팅 입력 중엔 단축키 무시
      if (e.code === "Space" && !ui.btnSpeak.disabled) {
        e.preventDefault();
        speak(TEST_AUDIO);
      }
      if (e.code === "KeyM") {
        ui.btnMotion.click();
      }
      if (e.code === "KeyE") {
        ui.btnExpression.click();
      }
      if (e.code === "KeyR") {
        userAdjusted = false;
        try { localStorage.removeItem(VIEW_KEY); } catch (err) {}
        positionModel();
        setStatus("state", "view reset", "ok");
      }
      if (e.code === "KeyH") {
        // 방송(OBS 캡처)용: 컨트롤 UI 숨김/표시 (자막은 유지)
        document.body.classList.toggle("ui-hidden");
      }
    });

    // OBS 방송 모드: 컨트롤 UI 없이 시작 (자막은 유지)
    if (BROADCAST_MODE) {
      document.body.classList.add("ui-hidden");
    }

    // Hide loading overlay
    ui.loadingOverlay.classList.add("hidden");

    console.log("AiCy Viewer initialized.");
    console.log("Shortcuts: [Space] speak, [M] motion, [E] expression, [R] reset view, [H] hide UI");
    console.log("Mouse: wheel = zoom, drag = move");
  }

  // --- Start ---
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
