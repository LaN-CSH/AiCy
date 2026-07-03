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

  const TEST_AUDIO = "../tts-audio.mp3";
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
    btnSpeak: document.getElementById("btn-speak"),
    btnMotion: document.getElementById("btn-motion"),
    btnExpression: document.getElementById("btn-expression"),
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

  // --- WebSocket: receive AiCy audio from Python backend ---
  // Protocol: a JSON text frame {type:"speak", text, emotion} followed by a
  // binary frame with the mp3 bytes. We play it through the same lip-sync path.
  function playAudioBytes(arrayBuffer) {
    var blob = new Blob([arrayBuffer], { type: "audio/mpeg" });
    if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
    currentObjectUrl = URL.createObjectURL(blob);
    speak(currentObjectUrl);
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
        } catch (e) {
          console.warn("Bad control message:", ev.data);
        }
        return;
      }
      // Binary frame = audio
      if (pendingSpeak && pendingSpeak.text) {
        setStatus("state", "speaking: " + pendingSpeak.text.slice(0, 24), "ok");
      }
      pendingSpeak = null;
      playAudioBytes(ev.data);
    };

    ws.onclose = function () {
      setStatus("ws", "disconnected", "warn");
      ws = null;
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
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });

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

    // Keyboard shortcuts
    document.addEventListener("keydown", function (e) {
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
        positionModel();
        setStatus("state", "view reset", "ok");
      }
    });

    // Hide loading overlay
    ui.loadingOverlay.classList.add("hidden");

    console.log("AiCy Viewer initialized.");
    console.log("Shortcuts: [Space] speak, [M] motion, [E] expression, [R] reset view");
    console.log("Mouse: wheel = zoom, drag = move");
  }

  // --- Start ---
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
