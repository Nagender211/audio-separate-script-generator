const ramuAudio = document.getElementById("ramuAudio");
const riyaAudio = document.getElementById("riyaAudio");
const ramuDownload = document.getElementById("ramuDownload");
const riyaDownload = document.getElementById("riyaDownload");
const durationDisplay = document.getElementById("durationDisplay");
const scriptBox = document.getElementById("scriptBox");
const generateAudio = document.getElementById("generateAudio");
const normalizeScript = document.getElementById("normalizeScript");
const maxConcurrentInput = document.getElementById("maxConcurrent");
const copyScript = document.getElementById("copyScript");
const copyStatus = document.getElementById("copyStatus");
const generateStatus = document.getElementById("generateStatus");
const scriptSection = document.getElementById("scriptSection");
const transcribeSection = document.getElementById("transcribeSection");
const generateOverlayText = document.getElementById("generateOverlayText");
const transcribeOverlayText = document.getElementById("transcribeOverlayText");
const audioFileInput = document.getElementById("audioFile");
const transcribeAudio = document.getElementById("transcribeAudio");
const useTranscription = document.getElementById("useTranscription");
const copyTranscription = document.getElementById("copyTranscription");
const transcribeStatus = document.getElementById("transcribeStatus");
const transcriptBox = document.getElementById("transcriptBox");
const speakerMapDisplay = document.getElementById("speakerMapDisplay");

const playBoth = document.getElementById("playBoth");
const pauseBoth = document.getElementById("pauseBoth");
const stopBoth = document.getElementById("stopBoth");
const syncBoth = document.getElementById("syncBoth");

let syncTimer = null;
const MAX_UPLOAD_MB = 800;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const CHUNK_THRESHOLD_BYTES = 20 * 1024 * 1024;
const CHUNK_SIZE_BYTES = 8 * 1024 * 1024;
const MAX_CHUNK_RETRIES = 3;

const SPEAKER_REGEX = /^([A-Za-z][A-Za-z0-9 ._-]{0,40})\s*[:\-]\s*(.*)$/;

function setSectionLoading(section, overlayText, isLoading, message) {
  if (!section) {
    return;
  }
  if (isLoading) {
    section.classList.add("is-loading");
    if (overlayText && message) {
      overlayText.textContent = message;
    }
  } else {
    section.classList.remove("is-loading");
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeLine(line) {
  return line
    .trim()
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .replace(/^[\s>*-]+/, "")
    .replace(/^\[?\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?\]?\s*(?:min|minutes)?\s*/i, "")
    .trim();
}

function cleanDialogueText(text) {
  return text
    .trim()
    .replace(/\*\*/g, "")
    .replace(/[#*]/g, "")
    .replace(/\.{3,}/g, "")
    .replace(/\u2026/g, "")
    .replace(/^\d{1,2}:\d{2}(?:\s*-\s*\d{1,2}:\d{2})?\s*(?:min|minutes)?\s*/i, "")
    .replace(/^\([^)]*\)\s*/, "")
    .replace(/^\[[^\]]*\]\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isNoiseLine(line) {
  const lower = line.toLowerCase();
  if (/^\d{1,2}:\d{2}(\s*-\s*\d{1,2}:\d{2})?$/.test(line)) {
    return true;
  }
  if (["min", "minute", "minutes"].includes(lower)) {
    return true;
  }
  if (/^(part|segment|chapter|section)\b/.test(lower)) {
    return true;
  }
  if (
    lower.startsWith("---") ||
    lower.startsWith("###") ||
    lower.startsWith("##") ||
    lower.startsWith("#") ||
    lower.startsWith("topic:") ||
    lower.startsWith("characters:") ||
    lower.startsWith("setting:") ||
    lower.startsWith("estimated") ||
    lower.startsWith("end of script")
  ) {
    return true;
  }
  if (line.startsWith("(") && line.endsWith(")")) {
    return true;
  }
  if (line.startsWith("[") && line.endsWith("]")) {
    return true;
  }
  if (lower.includes("sound fx")) {
    return true;
  }
  return false;
}

function isNoiseSpeakerName(name) {
  const lower = name.toLowerCase();
  if (/^(part|segment|chapter|section|intro|outro|topic)\b/.test(lower)) {
    return true;
  }
  if (/^\d+$/.test(lower)) {
    return true;
  }
  return false;
}

function mapSpeaker(raw, speakerMap) {
  const key = raw.trim().toLowerCase();
  if (key === "ramu") {
    return "Ramu";
  }
  if (key === "riya" || key === "raju") {
    return "Riya";
  }
  if (!speakerMap.has(key)) {
    if (speakerMap.size >= 2) {
      return null;
    }
    speakerMap.set(key, speakerMap.size === 0 ? "Ramu" : "Riya");
  }
  return speakerMap.get(key);
}

function extractTurns(text) {
  const turns = [];
  let current = null;
  let skipSection = false;
  const speakerMap = new Map();
  text.split(/\r?\n/).forEach((rawLine) => {
    const stripped = rawLine.trim();
    if (!stripped) {
      skipSection = false;
      return;
    }
    const line = normalizeLine(rawLine);
    if (!line) {
      return;
    }
    if (/^characters\b/i.test(line)) {
      skipSection = true;
      return;
    }
    if (skipSection) {
      if (!SPEAKER_REGEX.test(line)) {
        return;
      }
      skipSection = false;
    }
    if (isNoiseLine(line)) {
      return;
    }
    const match = line.match(SPEAKER_REGEX);
    if (match) {
      const rawSpeaker = match[1].trim();
      if (isNoiseSpeakerName(rawSpeaker)) {
        return;
      }
      const speaker = mapSpeaker(rawSpeaker, speakerMap);
      if (!speaker) {
        current = null;
        return;
      }
      const content = cleanDialogueText(match[2] || "");
      if (content) {
        current = { speaker, text: content };
        turns.push(current);
      } else {
        current = { speaker, text: "", pending: true };
      }
      return;
    }
    if (current && !isNoiseLine(line)) {
      const content = cleanDialogueText(line);
      if (content) {
        if (current.pending) {
          current.text = content;
          current.pending = false;
          turns.push(current);
        } else {
          current.text = `${current.text} ${content}`.trim();
        }
      }
    }
  });
  return turns;
}

function splitIntoSentences(text) {
  const cleaned = cleanDialogueText(text);
  if (!cleaned) {
    return [];
  }
  const matches = cleaned.match(/[^.!?]+[.!?]*/g);
  if (!matches) {
    return [cleaned];
  }
  return matches.map((part) => part.trim()).filter(Boolean);
}

function buildTurnsFromPlainText(text) {
  const paragraphs = [];
  let current = [];
  text.split(/\r?\n/).forEach((rawLine) => {
    const stripped = rawLine.trim();
    if (!stripped) {
      if (current.length) {
        paragraphs.push(current.join(" "));
        current = [];
      }
      return;
    }
    const line = normalizeLine(rawLine);
    if (!line || isNoiseLine(line)) {
      return;
    }
    const content = cleanDialogueText(line);
    if (content) {
      current.push(content);
    }
  });
  if (current.length) {
    paragraphs.push(current.join(" "));
  }

  if (!paragraphs.length) {
    return [];
  }

  const sentences = [];
  paragraphs.forEach((paragraph) => {
    splitIntoSentences(paragraph).forEach((sentence) => sentences.push(sentence));
  });

  if (!sentences.length) {
    return [];
  }

  const minWords = 12;
  const maxWords = 38;
  const chunks = [];
  let buffer = [];
  let wordTotal = 0;

  const flush = () => {
    if (!buffer.length) {
      return;
    }
    const chunk = buffer.join(" ").trim();
    if (chunk) {
      chunks.push(chunk);
    }
    buffer = [];
    wordTotal = 0;
  };

  sentences.forEach((sentence) => {
    const cleaned = cleanDialogueText(sentence);
    if (!cleaned) {
      return;
    }
    const words = cleaned.split(/\s+/).filter(Boolean);
    if (!words.length) {
      return;
    }
    if (words.length > maxWords) {
      flush();
      for (let i = 0; i < words.length; i += maxWords) {
        const slice = words.slice(i, i + maxWords).join(" ");
        if (slice) {
          chunks.push(slice);
        }
      }
      return;
    }
    if (wordTotal + words.length > maxWords && buffer.length) {
      flush();
    }
    buffer.push(cleaned);
    wordTotal += words.length;
    if (wordTotal >= minWords) {
      flush();
    }
  });
  flush();

  if (!chunks.length) {
    return [];
  }

  const turns = [];
  let speaker = "Ramu";
  chunks.forEach((chunk) => {
    turns.push({ speaker, text: chunk });
    speaker = speaker === "Ramu" ? "Riya" : "Ramu";
  });
  return turns;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return "--:--";
  }
  const totalMinutes = Math.floor(seconds / 60);
  const mins = String(totalMinutes).padStart(2, "0");
  const secs = String(Math.floor(seconds % 60)).padStart(2, "0");
  return `${mins}:${secs}`;
}

function updateDuration() {
  if (Number.isFinite(ramuAudio.duration) && Number.isFinite(riyaAudio.duration)) {
    const minDuration = Math.min(ramuAudio.duration, riyaAudio.duration);
    const maxDuration = Math.max(ramuAudio.duration, riyaAudio.duration);
    const label = `Ramu ${formatDuration(ramuAudio.duration)} | Riya ${formatDuration(
      riyaAudio.duration
    )} | Diff ${Math.abs(maxDuration - minDuration).toFixed(2)}s`;
    durationDisplay.textContent = label;
  }
}

function syncTimes() {
  const target = Math.min(ramuAudio.currentTime || 0, riyaAudio.currentTime || 0);
  ramuAudio.currentTime = target;
  riyaAudio.currentTime = target;
}

function startSyncLoop() {
  if (syncTimer) {
    return;
  }
  syncTimer = setInterval(() => {
    const diff = ramuAudio.currentTime - riyaAudio.currentTime;
    if (Math.abs(diff) > 0.2) {
      const target = Math.min(ramuAudio.currentTime, riyaAudio.currentTime);
      ramuAudio.currentTime = target;
      riyaAudio.currentTime = target;
    }
  }, 1000);
}

function stopSyncLoop() {
  if (syncTimer) {
    clearInterval(syncTimer);
    syncTimer = null;
  }
}

function setDownloadLink(link, url) {
  if (!link) {
    return;
  }
  if (!url) {
    link.removeAttribute("href");
    link.setAttribute("aria-disabled", "true");
    return;
  }
  link.href = url;
  link.removeAttribute("aria-disabled");
}

function refreshAudioSources(basePath) {
  if (!basePath) {
    return;
  }
  const cacheBust = `?t=${Date.now()}`;
  const ramuUrl = `${basePath}/Ramu_Audio.wav`;
  const riyaUrl = `${basePath}/Riya_Audio.wav`;
  ramuAudio.src = `${ramuUrl}${cacheBust}`;
  riyaAudio.src = `${riyaUrl}${cacheBust}`;
  ramuAudio.load();
  riyaAudio.load();
  setDownloadLink(ramuDownload, ramuUrl);
  setDownloadLink(riyaDownload, riyaUrl);
  durationDisplay.textContent = "Loading audio metadata...";
}

function getMaxConcurrent() {
  const rawValue = Number.parseInt(maxConcurrentInput?.value || "2", 10);
  if (Number.isNaN(rawValue)) {
    return 2;
  }
  return Math.max(1, Math.min(rawValue, 4));
}

async function uploadChunk(uploadId, index, chunk) {
  for (let attempt = 1; attempt <= MAX_CHUNK_RETRIES; attempt += 1) {
    try {
      const response = await fetch(
        `/transcribe/chunk?upload_id=${encodeURIComponent(uploadId)}&index=${index}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/octet-stream",
          },
          body: chunk,
        }
      );
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Chunk upload failed.");
      }
      return;
    } catch (err) {
      if (attempt >= MAX_CHUNK_RETRIES) {
        throw err;
      }
      await sleep(400 * attempt);
    }
  }
}

async function transcribeChunked(file) {
  const initResponse = await fetch("/transcribe/init", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      filename: file.name,
      size: file.size,
      content_type: file.type || "application/octet-stream",
    }),
  });
  if (!initResponse.ok) {
    const message = await initResponse.text();
    throw new Error(message || "Upload init failed.");
  }
  const initData = await initResponse.json();
  if (!initData.upload_id) {
    throw new Error("Upload init failed.");
  }

  const totalChunks = Math.ceil(file.size / CHUNK_SIZE_BYTES);
  for (let index = 0; index < totalChunks; index += 1) {
    const start = index * CHUNK_SIZE_BYTES;
    const end = Math.min(file.size, start + CHUNK_SIZE_BYTES);
    const chunk = file.slice(start, end);
    const progress = Math.round(((index + 1) / totalChunks) * 100);
    transcribeStatus.textContent = `Uploading ${progress}% (${index + 1}/${totalChunks}).`;
    setSectionLoading(transcribeSection, transcribeOverlayText, true, `Uploading ${progress}%...`);
    await uploadChunk(initData.upload_id, index, chunk);
  }

  transcribeStatus.textContent = "Transcribing audio...";
  setSectionLoading(transcribeSection, transcribeOverlayText, true, "Transcribing audio...");

  return fetch("/transcribe/complete", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ upload_id: initData.upload_id }),
  });
}

async function requestTranscription(file) {
  if (file.size > CHUNK_THRESHOLD_BYTES) {
    return transcribeChunked(file);
  }
  return fetch("/transcribe", {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-Filename": file.name,
    },
    body: file,
  });
}

playBoth.addEventListener("click", async () => {
  syncTimes();
  try {
    await Promise.all([ramuAudio.play(), riyaAudio.play()]);
  } catch (err) {
    console.error("Playback failed", err);
  }
});

pauseBoth.addEventListener("click", () => {
  ramuAudio.pause();
  riyaAudio.pause();
});

stopBoth.addEventListener("click", () => {
  ramuAudio.pause();
  riyaAudio.pause();
  ramuAudio.currentTime = 0;
  riyaAudio.currentTime = 0;
});

syncBoth.addEventListener("click", () => {
  syncTimes();
});

ramuAudio.addEventListener("loadedmetadata", updateDuration);
riyaAudio.addEventListener("loadedmetadata", updateDuration);

ramuAudio.addEventListener("play", startSyncLoop);
riyaAudio.addEventListener("play", startSyncLoop);
ramuAudio.addEventListener("pause", stopSyncLoop);
riyaAudio.addEventListener("pause", stopSyncLoop);

generateAudio.addEventListener("click", async () => {
  const scriptText = scriptBox.value.trim();
  if (!scriptText) {
    generateStatus.textContent = "Script is empty.";
    return;
  }
  const maxConcurrent = getMaxConcurrent();
  generateStatus.textContent = `Generating audio (speed ${maxConcurrent}). This can take several minutes.`;
  generateAudio.classList.add("is-loading");
  setSectionLoading(
    scriptSection,
    generateOverlayText,
    true,
    `Generating audio (speed ${maxConcurrent})...`
  );
  generateAudio.disabled = true;
  try {
    const response = await fetch("/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ scriptText, maxConcurrent }),
    });
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const rawText = await response.text();
      throw new Error(
        `Server did not return JSON. Start with 'python server.py'. Response: ${rawText.slice(
          0,
          120
        )}`
      );
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Generation failed.");
    }
    let durationLabel = "";
    if (typeof data.duration_seconds === "number") {
      durationLabel = ` ${formatDuration(data.duration_seconds)}.`;
    } else if (data.minutes) {
      durationLabel = ` ${data.minutes} minutes.`;
    }
    generateStatus.textContent = `Generation complete.${durationLabel}`;
    refreshAudioSources(data.output_dir);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Generation failed.";
    generateStatus.textContent = message;
    console.error(err);
  } finally {
    generateAudio.disabled = false;
    generateAudio.classList.remove("is-loading");
    setSectionLoading(scriptSection, generateOverlayText, false);
  }
});

normalizeScript.addEventListener("click", () => {
  let turns = extractTurns(scriptBox.value);
  let usedFallback = false;
  if (!turns.length) {
    turns = buildTurnsFromPlainText(scriptBox.value);
    usedFallback = true;
  }
  if (!turns.length) {
    generateStatus.textContent = "No usable text found to format.";
    return;
  }
  scriptBox.value = turns.map((turn) => `${turn.speaker}: ${turn.text}`).join("\n");
  generateStatus.textContent = usedFallback
    ? `Auto-split into ${turns.length} lines.`
    : `Formatted ${turns.length} lines.`;
});

copyScript.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(scriptBox.value);
    copyStatus.textContent = "Copied.";
    setTimeout(() => {
      copyStatus.textContent = "";
    }, 2000);
  } catch (err) {
    copyStatus.textContent = "Copy failed.";
  }
});

if (transcribeAudio) {
  transcribeAudio.addEventListener("click", async () => {
    const file = audioFileInput?.files?.[0];
    if (!file) {
      transcribeStatus.textContent = "Select an audio file first.";
      if (speakerMapDisplay) {
        speakerMapDisplay.textContent = "";
      }
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      transcribeStatus.textContent = "File is too large. Max 800 MB.";
      if (speakerMapDisplay) {
        speakerMapDisplay.textContent = "";
      }
      return;
    }
    transcribeStatus.textContent = "Uploading and transcribing. This can take a while.";
    if (speakerMapDisplay) {
      speakerMapDisplay.textContent = "";
    }
    transcribeAudio.classList.add("is-loading");
    setSectionLoading(transcribeSection, transcribeOverlayText, true, "Transcribing audio...");
    transcribeAudio.disabled = true;
    try {
      const response = await requestTranscription(file);
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        const rawText = await response.text();
        throw new Error(`Server error: ${rawText.slice(0, 140)}`);
      }
      const data = await response.json();
      if (!response.ok || data.status !== "ok") {
        throw new Error(data.error || "Transcription failed.");
      }
      transcriptBox.value = data.text || "";
      const durationLabel = data.duration_seconds
        ? ` ${formatDuration(data.duration_seconds)}.`
        : "";
      if (data.diarization === "fallback") {
        const reason = data.diarization_error ? ` (${data.diarization_error})` : "";
        transcribeStatus.textContent = `Transcription complete${durationLabel} Using fallback speakers${reason}.`;
      } else {
        transcribeStatus.textContent = `Transcription complete.${durationLabel}`;
      }
      if (speakerMapDisplay) {
        if (data.speaker_map) {
          const entries = Object.entries(data.speaker_map);
          if (entries.length) {
            const mapText = entries.map(([key, value]) => `${key} -> ${value}`).join(", ");
            speakerMapDisplay.textContent = `Mapping: ${mapText}`;
          } else {
            speakerMapDisplay.textContent = "";
          }
        } else {
          speakerMapDisplay.textContent = "";
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Transcription failed.";
      transcribeStatus.textContent = message;
      if (speakerMapDisplay) {
        speakerMapDisplay.textContent = "";
      }
      console.error(err);
    } finally {
      transcribeAudio.disabled = false;
      transcribeAudio.classList.remove("is-loading");
      setSectionLoading(transcribeSection, transcribeOverlayText, false);
    }
  });
}

if (copyTranscription) {
  copyTranscription.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(transcriptBox.value);
      transcribeStatus.textContent = "Copied transcription.";
    } catch (err) {
      transcribeStatus.textContent = "Copy failed.";
    }
  });
}

if (useTranscription) {
  useTranscription.addEventListener("click", () => {
    if (!transcriptBox.value.trim()) {
      transcribeStatus.textContent = "No transcription to use.";
      return;
    }
    scriptBox.value = transcriptBox.value.trim();
    transcribeStatus.textContent = "Loaded transcription into editor.";
  });
}
