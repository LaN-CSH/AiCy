// AiCy Viewer — Stage 0 Prototype
// Live2D model display + audio lip sync

(function () {
  "use strict";

  const { Live2DModel } = PIXI.live2d;

  // --- Config ---
  const SAMPLE_MODEL =
    "https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/haru/haru_greeter_t03.model3.json";
  const TEST_AUDIO = "../tts-audio.mp3";
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

    setLoading("Loading Live2D model (this may take a moment)...");
    setStatus("state", "loading");

    try {
      model = await Live2DModel.from(SAMPLE_MODEL, {
        autoInteract: false,
      });
    } catch (e) {
      console.error("Model load failed:", e);
      setLoading("Failed to load model. Check console.");
      setStatus("model", "load failed", "err");
      return;
    }

    app.stage.addChild(model);
    positionModel();

    setStatus("model", "Haru (sample)", "ok");
    setStatus("state", "idle", "ok");

    // Resize handling
    window.addEventListener("resize", positionModel);

    // Init audio system
    initAudio();

    // Setup lip sync
    setupLipSync();

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
    });

    // Hide loading overlay
    ui.loadingOverlay.classList.add("hidden");

    console.log("AiCy Viewer initialized.");
    console.log("Shortcuts: [Space] speak, [M] motion, [E] expression");
  }

  // --- Start ---
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
