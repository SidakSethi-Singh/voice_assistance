document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const statusPill = document.getElementById("statusPill");
  const statusText = document.getElementById("statusText");
  const toggleVoiceBtn = document.getElementById("toggleVoiceBtn");
  const toggleVoiceText = document.getElementById("toggleVoiceText");
  const toggleWakeWordBtn = document.getElementById("toggleWakeWordBtn");
  const bargeInBtn = document.getElementById("bargeInBtn");
  const conversationFeed = document.getElementById("conversationFeed");
  const partialTranscriptBar = document.getElementById("partialTranscriptBar");
  const partialTranscriptText = document.getElementById("partialTranscriptText");
  const orbContainer = document.getElementById("orbContainer");
  const waveformCanvas = document.getElementById("waveformCanvas");
  const canvasCtx = waveformCanvas ? waveformCanvas.getContext("2d") : null;

  // Telemetry HUD elements
  const telStt = document.getElementById("telStt");
  const telLlm = document.getElementById("telLlm");
  const telTts = document.getElementById("telTts");
  const telTotal = document.getElementById("telTotal");

  // Text Prompt
  const textPromptInput = document.getElementById("textPromptInput");
  const sendPromptBtn = document.getElementById("sendPromptBtn");

  // Settings Modal Elements
  const openSettingsBtn = document.getElementById("openSettingsBtn");
  const closeSettingsBtn = document.getElementById("closeSettingsBtn");
  const cancelSettingsBtn = document.getElementById("cancelSettingsBtn");
  const saveSettingsBtn = document.getElementById("saveSettingsBtn");
  const settingsModal = document.getElementById("settingsModal");
  const inputDeepgramKey = document.getElementById("inputDeepgramKey");
  const inputGeminiKey = document.getElementById("inputGeminiKey");
  const inputElevenLabsKey = document.getElementById("inputElevenLabsKey");

  // State
  let ws = null;
  let isSessionActive = false;
  let isWakeWordEnabled = true;
  let currentAssistantBubble = null;
  let currentUtteranceText = "";
  let isAssistantSpeaking = false;
  let audioLevel = 0;
  let animationFrameId = null;
  let browserSpeechRecognition = null;
  let isRecognizing = false;
  let lastInterruptionTime = 0;

  // Audio activation chime
  function playActivationChime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.26);
    } catch (e) {}
  }

  const WAKE_WORD_REGEX = /\b(hey aether|aether|hey either|hey ather|wake up)\b/i;

  // Progressive Speech Synthesis Queue for Ultra-Low Latency (<1.5s)
  let ttsQueue = [];
  let isTtsPlaying = false;
  let fullTurnText = "";

  function queueSentenceTTS(sentence) {
    if (!('speechSynthesis' in window) || !sentence.trim()) return;
    
    // Clean sentence of symbols
    const cleanSentence = sentence.replace(/[*_#`~]/g, "").trim();
    if (!cleanSentence) return;

    ttsQueue.push(cleanSentence);
    if (!isTtsPlaying) {
      processNextTTSQueueItem();
    }
  }

  function processNextTTSQueueItem() {
    if (ttsQueue.length === 0) {
      isTtsPlaying = false;
      isAssistantSpeaking = false;
      if (bargeInBtn) bargeInBtn.disabled = true;
      
      // Allow acoustic grace period (300ms) before re-enabling microphone recognition
      setTimeout(() => {
        if (isSessionActive) {
          setAssistantState("LISTENING");
          resumeSpeechRecognition();
        } else {
          setAssistantState("IDLE");
        }
      }, 300);
      return;
    }

    isTtsPlaying = true;
    isAssistantSpeaking = true;
    setAssistantState("SPEAKING");
    if (bargeInBtn) bargeInBtn.disabled = false;

    // Pause mic recognition during speech output to prevent self-echo interruption
    pauseSpeechRecognition();

    const sentence = ttsQueue.shift();
    const utterance = new SpeechSynthesisUtterance(sentence);
    utterance.rate = 1.15; // Natural, fast conversational pace
    utterance.pitch = 1.0;
    utterance.lang = "en-US";

    utterance.onend = () => {
      // Small pause between sentences or play next immediately
      setTimeout(processNextTTSQueueItem, 50);
    };

    utterance.onerror = (err) => {
      console.warn("TTS Utterance error:", err);
      processNextTTSQueueItem();
    };

    window.speechSynthesis.speak(utterance);
  }

  function clearAllTTS() {
    ttsQueue = [];
    isTtsPlaying = false;
    isAssistantSpeaking = false;
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setTimeout(() => {
      if (isSessionActive) {
        setAssistantState("LISTENING");
        resumeSpeechRecognition();
      }
    }, 150);
  }

  // Execute clean and immediate interruption on user request
  function performInstantBargeIn(reason = "user_action") {
    const now = Date.now();
    if (now - lastInterruptionTime < 400) return;
    lastInterruptionTime = now;

    console.log(`Instant Barge-In executed (${reason})`);
    
    // 1. Immediately halt audio output and drain queue
    player.flush();
    clearAllTTS();

    // 2. Notify backend
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "manual_interrupt" }));
    }

    // 3. Update UI state
    setAssistantState("INTERRUPTED");
    if (currentAssistantBubble) {
      const cutTag = document.createElement("span");
      cutTag.style.opacity = "0.6";
      cutTag.style.fontSize = "11px";
      cutTag.textContent = " [interrupted]";
      currentAssistantBubble.appendChild(cutTag);
      currentAssistantBubble = null;
    }
  }

  function pauseSpeechRecognition() {
    if (browserSpeechRecognition && isRecognizing) {
      try {
        browserSpeechRecognition.abort();
        isRecognizing = false;
      } catch (e) {}
    }
  }

  function resumeSpeechRecognition() {
    if (browserSpeechRecognition && !isRecognizing && (isSessionActive || isWakeWordEnabled)) {
      try {
        browserSpeechRecognition.start();
        isRecognizing = true;
      } catch (e) {}
    }
  }

  // Initialize Streaming Audio Player
  const player = new StreamingAudioPlayer(
    () => {
      isAssistantSpeaking = true;
      pauseSpeechRecognition();
      if (bargeInBtn) bargeInBtn.disabled = false;
      setAssistantState("SPEAKING");
    },
    () => {
      isAssistantSpeaking = false;
      if (bargeInBtn) bargeInBtn.disabled = true;
      setTimeout(() => {
        if (isSessionActive) {
          setAssistantState("LISTENING");
          resumeSpeechRecognition();
        } else {
          setAssistantState("IDLE");
        }
      }, 300);
    }
  );

  // Setup Browser Speech Recognition (STT Fallback & Wake-word detection)
  function setupBrowserSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("Web Speech API recognition not supported in this browser.");
      return;
    }

    browserSpeechRecognition = new SpeechRecognition();
    browserSpeechRecognition.continuous = true;
    browserSpeechRecognition.interimResults = true;
    browserSpeechRecognition.lang = "en-US";
    browserSpeechRecognition.maxAlternatives = 1;

    browserSpeechRecognition.onresult = (event) => {
      if (isAssistantSpeaking) return; // Prevent any speaker self-echo capture

      let interim = "";
      let final = "";

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          final += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }

      if (interim) {
        if (partialTranscriptText) partialTranscriptText.textContent = interim;

        // Wake word trigger
        if (isWakeWordEnabled && WAKE_WORD_REGEX.test(interim) && !isSessionActive) {
          playActivationChime();
          isSessionActive = true;
          if (toggleVoiceBtn) toggleVoiceBtn.classList.add("active");
          if (toggleVoiceText) toggleVoiceText.textContent = "Stop Voice Session";
          setAssistantState("LISTENING");
          addSystemMessage("⚡ 'Hey Aether' detected! Listening...");
        }
      }

      if (final.trim()) {
        let cleanText = final.trim();
        if (isWakeWordEnabled && WAKE_WORD_REGEX.test(cleanText)) {
          playActivationChime();
          cleanText = cleanText.replace(WAKE_WORD_REGEX, "").trim();
          if (!cleanText) {
            if (partialTranscriptText) partialTranscriptText.textContent = "I'm listening...";
            addSystemMessage("⚡ Wake-word detected. What can I do for you?");
            return;
          }
        }

        if (partialTranscriptText) partialTranscriptText.textContent = "Listening for speech...";
        addUserMessage(cleanText);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: "text_prompt", text: cleanText }));
        }
      }
    };

    browserSpeechRecognition.onend = () => {
      isRecognizing = false;
      if (!isAssistantSpeaking && (isSessionActive || isWakeWordEnabled)) {
        setTimeout(resumeSpeechRecognition, 150);
      }
    };

    browserSpeechRecognition.onerror = (err) => {
      if (err.error !== "no-speech" && err.error !== "aborted") {
        console.warn("Speech recognition error:", err.error);
      }
    };

    resumeSpeechRecognition();
  }

  setupBrowserSpeechRecognition();

  // Spacebar keyboard shortcut for instant barge-in interruption
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && isAssistantSpeaking && document.activeElement !== textPromptInput) {
      e.preventDefault();
      performInstantBargeIn("spacebar");
    }
  });

  // Initialize Audio Recorder for PCM WebSocket streaming (no false background energy barge-ins)
  const recorder = new AudioRecorder(
    (pcmChunk) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(pcmChunk);
      }
    },
    (level) => {
      audioLevel = level;
    }
  );

  // --- WebSocket Connection ---
  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = window.BACKEND_WS_URL || `${protocol}//${host}/ws/voice`;
    
    console.log("Connecting WebSocket to:", wsUrl);
    ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      console.log("Connected to Voice WebSocket");
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        player.queueAudioChunk(event.data);
      } else {
        try {
          const msg = JSON.parse(event.data);
          handleServerMessage(msg);
        } catch (e) {
          console.error("Error parsing WS message:", e);
        }
      }
    };

    ws.onclose = () => {
      setTimeout(connectWebSocket, 2000);
    };
  }

  // --- Handle Server Messages ---
  function handleServerMessage(msg) {
    switch (msg.type) {
      case "state_change":
        setAssistantState(msg.state);
        break;

      case "stt_transcript":
        if (msg.text) {
          if (partialTranscriptText) partialTranscriptText.textContent = msg.text;
          if (msg.is_final || msg.speech_final) {
            addUserMessage(msg.text);
            if (partialTranscriptText) partialTranscriptText.textContent = "Listening for speech...";
          }
        }
        break;

      case "processing_started":
        currentAssistantBubble = null;
        currentUtteranceText = "";
        accumulatedText = "";
        if (bargeInBtn) bargeInBtn.disabled = false;
        break;

      case "assistant_chunk":
        appendAssistantChunk(msg.text);
        currentUtteranceText += msg.text;
        accumulatedText += msg.text;

        // Progressive sentence-level TTS streaming
        const sentenceEndIndex = currentUtteranceText.search(/[.!?\n]/);
        if (sentenceEndIndex !== -1 && !player.isPlaying) {
          const readySentence = currentUtteranceText.slice(0, sentenceEndIndex + 1);
          currentUtteranceText = currentUtteranceText.slice(sentenceEndIndex + 1);
          queueSentenceTTS(readySentence);
        }
        break;

      case "tool_executed":
        renderToolCard(msg.tool_name, msg.args, msg.result);
        break;

      case "turn_completed":
        // Queue any remaining sentence text
        if (currentUtteranceText.trim() && !player.isPlaying) {
          queueSentenceTTS(currentUtteranceText.trim());
          currentUtteranceText = "";
        }
        currentAssistantBubble = null;
        if (msg.metrics) updateMetricsHUD(msg.metrics);
        break;

      case "metrics_update":
        if (msg.metrics) updateMetricsHUD(msg.metrics);
        break;

      case "barge_in":
        player.flush();
        clearAllTTS();
        if (currentAssistantBubble) {
          const cutTag = document.createElement("span");
          cutTag.style.opacity = "0.6";
          cutTag.style.fontSize = "11px";
          cutTag.textContent = " [interrupted]";
          currentAssistantBubble.appendChild(cutTag);
          currentAssistantBubble = null;
        }
        break;

      case "warning":
        addSystemMessage("⚠️ " + msg.message);
        break;

      case "error":
        addSystemMessage("❌ Error: " + msg.message);
        break;
    }
  }

  // --- UI State Management ---
  function setAssistantState(state) {
    if (!statusPill || !statusText || !orbContainer) return;

    statusPill.className = "status-pill";
    orbContainer.className = "orb-container";

    switch (state) {
      case "IDLE":
        statusPill.classList.add("status-idle");
        statusText.textContent = "IDLE";
        break;
      case "LISTENING":
        statusPill.classList.add("status-listening");
        orbContainer.classList.add("orb-listening");
        statusText.textContent = "LISTENING";
        break;
      case "PROCESSING":
        statusPill.classList.add("status-processing");
        orbContainer.classList.add("orb-processing");
        statusText.textContent = "PROCESSING";
        break;
      case "SPEAKING":
        statusPill.classList.add("status-speaking");
        orbContainer.classList.add("orb-speaking");
        statusText.textContent = "SPEAKING";
        if (bargeInBtn) bargeInBtn.disabled = false;
        break;
      case "INTERRUPTED":
        statusPill.classList.add("status-interrupted");
        statusText.textContent = "INTERRUPTED";
        break;
    }
  }

  function updateMetricsHUD(metrics) {
    if (metrics.stt_final_ms !== undefined && telStt) telStt.textContent = `${metrics.stt_final_ms} ms`;
    if (metrics.llm_ttft_ms !== undefined && telLlm) telLlm.textContent = `${metrics.llm_ttft_ms} ms`;
    if (metrics.tts_ttfb_ms !== undefined && telTts) telTts.textContent = `${metrics.tts_ttfb_ms} ms`;
    if (metrics.total_turn_ms !== undefined && telTotal) telTotal.textContent = `${metrics.total_turn_ms} ms`;
  }

  // --- Chat Bubble Rendering ---
  function addUserMessage(text) {
    if (!conversationFeed) return;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble user-bubble";
    bubble.textContent = text;
    conversationFeed.appendChild(bubble);
    conversationFeed.scrollTop = conversationFeed.scrollHeight;
  }

  function appendAssistantChunk(text) {
    if (!conversationFeed) return;
    if (!currentAssistantBubble) {
      currentAssistantBubble = document.createElement("div");
      currentAssistantBubble.className = "chat-bubble assistant-bubble";
      conversationFeed.appendChild(currentAssistantBubble);
    }
    currentAssistantBubble.textContent += text;
    conversationFeed.scrollTop = conversationFeed.scrollHeight;
  }

  function renderToolCard(toolName, args, result) {
    if (!conversationFeed) return;
    const card = document.createElement("div");
    card.className = "tool-card";

    const header = document.createElement("div");
    header.className = "tool-card-header";
    header.innerHTML = `⚡ TOOL: <strong>${toolName}</strong>`;

    const body = document.createElement("div");
    body.className = "tool-card-body";
    body.textContent = `Args: ${JSON.stringify(args, null, 2)}\nResult: ${JSON.stringify(result, null, 2)}`;

    card.appendChild(header);
    card.appendChild(body);
    conversationFeed.appendChild(card);
    conversationFeed.scrollTop = conversationFeed.scrollHeight;
  }

  function addSystemMessage(text) {
    if (!conversationFeed) return;
    const bubble = document.createElement("div");
    bubble.className = "system-bubble";
    bubble.textContent = text;
    conversationFeed.appendChild(bubble);
    conversationFeed.scrollTop = conversationFeed.scrollHeight;
  }

  // --- Voice Controls ---
  if (toggleVoiceBtn) {
    toggleVoiceBtn.addEventListener("click", async () => {
      if (!isSessionActive) {
        try {
          await recorder.start();
          if (browserSpeechRecognition && !isRecognizing) {
            try {
              browserSpeechRecognition.start();
              isRecognizing = true;
            } catch (e) {}
          }
          isSessionActive = true;
          toggleVoiceBtn.classList.add("active");
          if (toggleVoiceText) toggleVoiceText.textContent = "Stop Voice Session";
          setAssistantState("LISTENING");
          addSystemMessage("🎙️ Microphone stream activated. Start speaking!");
        } catch (err) {
          alert("Microphone access error: " + err.message);
        }
      } else {
        recorder.stop();
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        isSessionActive = false;
        toggleVoiceBtn.classList.remove("active");
        if (toggleVoiceText) toggleVoiceText.textContent = "Start Voice Session";
        setAssistantState("IDLE");
        addSystemMessage("🔇 Voice session stopped.");
      }
    });
  }

  // Wake-word toggle
  if (toggleWakeWordBtn) {
    toggleWakeWordBtn.addEventListener("click", () => {
      isWakeWordEnabled = !isWakeWordEnabled;
      const label = toggleWakeWordBtn.querySelector(".wake-label");
      if (isWakeWordEnabled) {
        toggleWakeWordBtn.classList.add("active");
        if (label) label.textContent = "WAKE WORD: ON";
        addSystemMessage("⚡ Hands-free Wake-word enabled ('Hey Aether').");
        if (browserSpeechRecognition && !isRecognizing) {
          try {
            browserSpeechRecognition.start();
            isRecognizing = true;
          } catch (e) {}
        }
      } else {
        toggleWakeWordBtn.classList.remove("active");
        if (label) label.textContent = "WAKE WORD: OFF";
        addSystemMessage("🔇 Hands-free Wake-word disabled.");
      }
    });
  }

  // Manual Barge-In Button
  if (bargeInBtn) {
    bargeInBtn.addEventListener("click", () => {
      player.flush();
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "manual_interrupt" }));
      }
    });
  }

  // Direct Text Prompt Fallback
  function submitTextPrompt() {
    if (!textPromptInput) return;
    const text = textPromptInput.value.trim();
    if (!text) return;
    textPromptInput.value = "";
    addUserMessage(text);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: "text_prompt", text: text }));
    }
  }

  if (sendPromptBtn) sendPromptBtn.addEventListener("click", submitTextPrompt);
  if (textPromptInput) {
    textPromptInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") submitTextPrompt();
    });
  }

  // Settings Modal Handlers
  if (openSettingsBtn) openSettingsBtn.addEventListener("click", () => settingsModal && settingsModal.classList.remove("hidden"));
  if (closeSettingsBtn) closeSettingsBtn.addEventListener("click", () => settingsModal && settingsModal.classList.add("hidden"));
  if (cancelSettingsBtn) cancelSettingsBtn.addEventListener("click", () => settingsModal && settingsModal.classList.add("hidden"));

  if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener("click", () => {
      const payload = {
        action: "update_config",
        deepgram_api_key: inputDeepgramKey ? inputDeepgramKey.value.trim() : "",
        gemini_api_key: inputGeminiKey ? inputGeminiKey.value.trim() : "",
        elevenlabs_api_key: inputElevenLabsKey ? inputElevenLabsKey.value.trim() : ""
      };
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
      }
      if (settingsModal) settingsModal.classList.add("hidden");
      addSystemMessage("⚙️ Assistant configuration updated.");
    });
  }

  // --- Canvas Waveform Animation ---
  const freqData = new Uint8Array(64);
  function renderWaveform() {
    if (!waveformCanvas || !canvasCtx) return;
    const width = waveformCanvas.width;
    const height = waveformCanvas.height;
    canvasCtx.clearRect(0, 0, width, height);

    if (recorder.isRecording) {
      recorder.getFrequencyData(freqData);
    } else {
      freqData.fill(0);
    }

    const barWidth = (width / freqData.length) * 1.5;
    let x = 0;

    for (let i = 0; i < freqData.length; i++) {
      const v = freqData[i] / 255.0;
      const barHeight = Math.max(4, v * height * 0.85);

      const grad = canvasCtx.createLinearGradient(0, height, 0, 0);
      grad.addColorStop(0, "#00f0ff");
      grad.addColorStop(1, "#9d4edd");

      canvasCtx.fillStyle = grad;
      canvasCtx.fillRect(x, (height - barHeight) / 2, barWidth - 2, barHeight);
      x += barWidth;
    }

    animationFrameId = requestAnimationFrame(renderWaveform);
  }

  // Start animation loop and websocket connection
  renderWaveform();
  connectWebSocket();
});
