/* Veritas - citizen web app (vanilla JS, no build step).
 * Security: every value coming from the API or from public sources is inserted with
 * textContent / DOM APIs (never parsed as HTML), and only http(s) links are rendered.
 * Languages: the server renders one page per language (/pt/, /en/, /fr/) and embeds its
 * dictionary in <script id="i18n">; every text below comes from t().
 */
"use strict";

const API = "/api/v1/fact-check/text";
const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
const REQUEST_TIMEOUT_MS = 90_000;
const MEDIA_API = "/api/v1/fact-check/media";
const MEDIA_TIMEOUT_MS = 240_000; // download + transcription + several checks
const MEDIA_MAX_BYTES = 50 * 1024 * 1024;
const VIDEO_LINK = /(youtube\.com|youtu\.be|tiktok\.com|instagram\.com|(\/\/|\.)x\.com|twitter\.com|facebook\.com|fb\.watch|kwai|vimeo\.com|dailymotion\.com|\.(mp4|mov|webm|mkv|mp3|m4a|wav|ogg|opus|jpe?g|png|webp)(\?|$))/i;

// ---------------------------------------------------------------- language
const I18N = (() => {
  try {
    return JSON.parse(document.getElementById("i18n")?.textContent || "{}");
  } catch {
    return {};
  }
})();
const LANG = I18N.meta?.lang || "pt";
const LOCALE = I18N.meta?.locale || "pt-BR";

/** Translated text for `key`, with {placeholders} filled from `vars`. */
function t(key, vars = {}) {
  const text = I18N.strings?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

// ---------------------------------------------------------------- knowledge areas
const ICONS = {
  gov: "M3 21h18M5 21V10m14 11V10M9 21V10m6 11V10M2 10l10-6 10 6",
  stats: "M4 20V11m6 9V5m6 15v-6m6 6H2",
  law: "M12 3v18m-5 0h10M4 7h16M4 7l-2.5 6a3 3 0 0 0 5 0zm16 0-2.5 6a3 3 0 0 0 5 0z",
  science: "M9 3h6m-5 0v6L4.2 18.6A2 2 0 0 0 6 21.5h12a2 2 0 0 0 1.8-2.9L14 9V3M7 15h10",
  world: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.7 3.6 5.7 3.6 9s-1.1 6.3-3.6 9c-2.5-2.7-3.6-5.7-3.6-9S9.5 5.7 12 3z",
  web: "M3 12a9 9 0 1 0 2.6-6.4L3 8m0-5v5h5m4-1v5l3 2",
  climate: "M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0zM12 9v8",
  warning: "M12 9v4m0 3.5v.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  bulb: "M9 18h6m-5 3h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
  check: "m5 12.5 4.5 4.5L19 7.5",
  cross: "M7 7l10 10M17 7 7 17",
  alert: "M12 8v5m0 3.5v.01M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  question: "M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5M12 17.5v.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  book: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zm0 15A2.5 2.5 0 0 0 6.5 23H20v-5",
  external: "M14 4h6v6m0-6-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  video: "M4 6h11a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm12 4 5-3v10l-5-3",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
  translate: "M4 5h9M8.5 3v2m3 0c-.8 4-3.6 7.3-7 9m2-6c1.2 2.4 3.3 4.5 6 5.5M13 21l4.5-10L22 21m-7.5-3h6",
};

const AREA_COLORS = {
  gov: "--a-gov", stats: "--a-stats", law: "--a-law", science: "--a-science",
  world: "--a-world", climate: "--a-climate", web: "--a-web",
};
const areaLabel = (area) => t(`area_${area}`);

// connector id -> [area, language of its content]
const CONNECTORS = {
  "br.camara": ["gov", "pt"], "br.senado": ["gov", "pt"], "br.transparencia": ["gov", "pt"],
  "br.ibge": ["stats", "pt"], "br.legislacao": ["law", "pt"], "br.stj_precedentes": ["law", "pt"],
  "fr.data_gouv": ["gov", "fr"], "fr.insee": ["stats", "fr"], "fr.legifrance": ["law", "fr"],
  "fr.judilibre": ["law", "fr"], "eu.eurlex": ["law", "en"], "science.pubmed": ["science", "en"],
  "health.who_gho": ["science", "en"], "geo.gdelt": ["world", "en"], "geo.reliefweb": ["world", "en"],
  "web.wayback": ["web", null], "climate.copernicus": ["climate", "pt"],
  "climate.noaa": ["climate", "pt"],
};

const VERDICTS = {
  VERDADEIRO: { key: "v_true", tone: "true", icon: "check", emoji: "✅" },
  FALSO: { key: "v_false", tone: "false", icon: "cross", emoji: "❌" },
  ENGANOSO: { key: "v_misleading", tone: "warn", icon: "alert", emoji: "⚠️" },
  INCONCLUSIVO: { key: "v_inconclusive", tone: "neutral", icon: "question", emoji: "❔" },
  SEM_DADOS_SUFICIENTES: { key: "v_no_data", tone: "neutral", icon: "question", emoji: "❔" },
  SEM_CHAVE_IA_DADOS_BRUTOS: { key: "v_raw", tone: "info", icon: "book", emoji: "📚" },
};

function verdictInfo(code) {
  const base = VERDICTS[code] || VERDICTS.INCONCLUSIVO;
  return { ...base, label: t(base.key), meaning: t(`${base.key}_meaning`) };
}

const C2PA_LABELS = {
  AI_GENERATED: { key: "c2pa_label_ai_generated", tone: "false" },
  AI_EDITED: { key: "c2pa_label_ai_edited", tone: "warn" },
  CAMERA_CAPTURE: { key: "c2pa_label_camera", tone: "true" },
  EDITED: { key: "c2pa_label_edited", tone: "warn" },
  SIGNED_UNKNOWN: { key: "c2pa_label_signed_unknown", tone: "neutral" },
  INVALID_SIGNATURE: { key: "c2pa_label_invalid", tone: "false" },
  NO_MANIFEST: { key: "c2pa_label_no_manifest", tone: "neutral" },
  UNAVAILABLE: { key: "c2pa_label_unavailable", tone: "neutral" },
};
const VERDICT_SEVERITY = ["FALSO", "ENGANOSO", "INCONCLUSIVO", "SEM_DADOS_SUFICIENTES", "VERDADEIRO", "SEM_CHAVE_IA_DADOS_BRUTOS"];

const FALLBACK_PROVIDERS = [
  { name: "gemini", free_tier: true, requires_api_key: true, get_key_url: "https://aistudio.google.com/apikey" },
  { name: "groq", free_tier: true, requires_api_key: true, get_key_url: "https://console.groq.com/keys" },
  { name: "ollama", free_tier: true, requires_api_key: false, get_key_url: null },
];
const providerName = (name) => ({
  gemini: "Google Gemini", groq: "Groq", ollama: t("provider_ollama"), anthropic: "Claude", openai: "OpenAI",
}[name] || name);

// ---------------------------------------------------------------- confidence
//: From this confidence on, a True/False verdict is shown as a stamped, full-colour result.
const STRONG_CONFIDENCE = 0.8;
const MEDIUM_CONFIDENCE = 0.55;
const LEANING = { VERDADEIRO: 1, FALSO: -1, ENGANOSO: -0.5 };

/** How sure the AI verdict is, and where it sits on the False ↔ True scale. Null without AI.
 *
 * Only True / False / Misleading carry a truth percentage. For "Inconclusive" and "Not enough
 * data" the model's confidence only says how sure it is that it *cannot* decide: shown as a
 * percentage it reads like "20% reliable", so those verdicts get the centred marker and no %. */
function certainty(report) {
  if (!report?.ai_used) return null;
  const lean = LEANING[report.verdict] ?? 0;
  if (!lean) return { pct: null, tone: null, level: "neutral", text: t("cert_neutral"), position: 50, strong: false };
  const confidence = Math.max(0, Math.min(1, Number(report.confidence_score) || 0));
  const pct = Math.round(confidence * 100);
  const tone = VERDICTS[report.verdict].tone;
  const level = confidence >= STRONG_CONFIDENCE ? "strong" : confidence >= MEDIUM_CONFIDENCE ? "medium" : "weak";
  const text = level === "weak" ? t("cert_weak", { pct }) : t(`cert_${level}_${tone}`, { pct });
  return { pct, tone, level, text, position: 50 + lean * confidence * 50, strong: level === "strong" };
}

// ---------------------------------------------------------------- state & helpers
const state = {
  ai: null, selected: "gemini", providers: [], report: null, filter: null,
  lastRequest: null, mediaFile: null, media: null,
};
const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function icon(name, extraClass = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  if (extraClass) svg.setAttribute("class", extraClass);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICONS[name]);
  svg.append(path);
  return svg;
}

function areaIcon(area) {
  return el("span", { class: "area-icon", style: `--c: var(${AREA_COLORS[area]})` }, icon(area));
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function formatDate(iso) {
  if (!iso) return null;
  const date = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(LOCALE, { day: "2-digit", month: "short", year: "numeric" });
}

function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 2600);
}

function showState(name) {
  for (const id of ["emptyState", "loadingState", "resultState", "errorState"]) {
    $(id).hidden = id !== `${name}State`;
  }
  $("resultPanel").setAttribute("aria-busy", name === "loading" ? "true" : "false");
}

function openAiPanel() {
  $("aiPanel").open = true;
  $("aiPanel").scrollIntoView({ behavior: "smooth", block: "center" });
}

// ---------------------------------------------------------------- static UI
function renderAreas() {
  const list = $("areasEmpty");
  const radar = $("radarAreas");
  const keys = Object.keys(AREA_COLORS);
  keys.forEach((key, index) => {
    list.append(el("li", { class: "area" }, areaIcon(key), areaLabel(key), el("small", { text: t(`area_${key}_hint`) })));
    radar.append(el("li", { "data-area": key, style: `--angle: ${(360 / keys.length) * index}deg` }, areaIcon(key)));
  });
}

function renderExamples() {
  const box = $("examples");
  for (const example of I18N.examples || []) {
    box.append(
      el("button", {
        type: "button", class: "chip",
        onclick: () => {
          $("claim").value = example.text;
          updateCounter();
          const radio = document.querySelector(`input[name="country"][value="${example.country || ""}"]`);
          if (radio) radio.checked = true;
          submit();
        },
      }, el("span", { class: "swatch", style: `background: var(${AREA_COLORS[example.area] || "--a-gov"})` }), example.text),
    );
  }
}

function updateCounter() {
  $("counter").textContent = `${$("claim").value.length} / 5000`;
}

// ---------------------------------------------------------------- AI (BYOK) panel
async function loadProviders() {
  try {
    const response = await fetch("/api/v1/byok/providers");
    const body = await response.json();
    state.providers = body.providers || FALLBACK_PROVIDERS;
  } catch {
    state.providers = FALLBACK_PROVIDERS;
  }
  renderProviders();
}

function renderProviders() {
  const grid = $("providerGrid");
  grid.replaceChildren();
  const free = state.providers.filter((p) => p.free_tier);
  const paid = state.providers.filter((p) => !p.free_tier);
  for (const provider of free) {
    grid.append(
      el("button", {
        type: "button", class: "provider", role: "radio",
        "aria-checked": String(provider.name === state.selected),
        onclick: () => selectProvider(provider.name),
      },
      el("b", { text: providerName(provider.name) }),
      el("small", { class: "free", text: t("free") }),
      el("small", { text: provider.requires_api_key ? t("no_card") : t("no_key") })),
    );
  }
  if (paid.length) {
    const select = el("select", {
      class: "provider-more", "aria-label": t("paid_aria"),
      onchange: (event) => event.target.value && selectProvider(event.target.value),
    }, el("option", { value: "", text: t("paid_choose") }),
    paid.map((p) => el("option", { value: p.name, text: providerName(p.name) })));
    if (paid.some((p) => p.name === state.selected)) select.value = state.selected;
    grid.append(select);
  }
  renderProviderHelp();
}

function selectProvider(name) {
  state.selected = name;
  renderProviders();
}

function renderProviderHelp() {
  const provider = state.providers.find((p) => p.name === state.selected) || {};
  const help = $("providerHelp");
  help.replaceChildren();
  const link = safeUrl(provider.get_key_url);
  // The server lists the steps in Portuguese; the page's own language wins when it has them.
  const steps = I18N.provider_steps?.[provider.name] || provider.steps || [];
  help.append(
    el("b", { text: provider.free_tier ? t("how_get_free_key") : t("how_get_key") }),
    el("ol", {}, steps.map((step) => el("li", { text: step }))),
    link ? el("a", { href: link, target: "_blank", rel: "noopener noreferrer", text: t("open_key_page") }) : null,
  );
  $("keyRow").hidden = provider.requires_api_key === false;
}

function setAiStatus() {
  const pill = $("aiPill");
  pill.classList.toggle("on", Boolean(state.ai));
  $("aiPillText").textContent = state.ai
    ? t("ai_pill_on", { name: providerName(state.ai.provider) })
    : t("ai_pill_off");
}

function aiHeaders(ai) {
  const headers = { "X-Provider": ai.provider };
  if (ai.key) headers["X-API-Key"] = ai.key;
  if (ai.model) headers["X-Model"] = ai.model;
  return headers;
}

/** Key formats of each provider, used to catch copy/paste mistakes before calling it. */
const KEY_FORMATS = {
  gemini: { prefix: "AIza", min: 35, typical: 39, console: "aistudio.google.com/apikey" },
  groq: { prefix: "gsk_", min: 40, typical: 56, console: "console.groq.com/keys" },
  openai: { prefix: "sk-", min: 30, typical: 100, console: "platform.openai.com/api-keys" },
  anthropic: { prefix: "sk-ant-", min: 40, typical: 108, console: "console.anthropic.com" },
};

/** Removes spaces, line breaks, invisible characters and quotes that come along when copying. */
function cleanKey(raw) {
  return String(raw || "")
    .replace(/[\s\u00A0\u200B-\u200D\u2060\uFEFF]/g, "")
    .replace(/^["'“”‘’`]+|["'“”‘’`]+$/g, "");
}

/** Returns a plain-language problem with the pasted key, or null if it looks right. */
function keyProblem(provider, key) {
  const format = KEY_FORMATS[provider];
  if (!format || !key) return null;
  const name = providerName(provider);
  if (/[*•…]|\.\.\./.test(key)) return t("key_masked", { name, console: format.console });
  if (!key.startsWith(format.prefix)) return t("key_prefix", { name, prefix: format.prefix });
  if (key.length < format.min) {
    return t("key_short", { name, length: key.length, typical: format.typical });
  }
  return null;
}

/** Turns provider error messages into plain language with a next step (null if unknown). */
function friendlyAiError(message, provider) {
  const raw = String(message || "");
  const text = raw.toLowerCase();
  const name = provider ? providerName(provider) : t("provider_generic");
  const reason = raw.match(/\(([^()]*)\)\.?$/)?.[1];
  const said = reason ? t("ai_said", { name, reason }) : "";
  if (text.includes("rejected") || text.includes("permission")) {
    const format = KEY_FORMATS[provider];
    const tip = format ? t("ai_tip_console", { name, console: format.console }) : t("ai_tip_generic");
    return t("ai_rejected", { name, said, tip });
  }
  if (text.includes("rate limit") || text.includes("quota")) return t("ai_quota", { said });
  if (text.includes("not found")) return t("ai_model_missing", { said });
  if (text.includes("timed out") || text.includes("demorou")) return t("ai_timeout");
  if (text.includes("connect")) return t("ai_connect");
  if (text.includes("malformed")) return t("ai_malformed");
  if (text.includes("requires an api key") || text.includes("x-api-key")) return t("ai_paste_key");
  return null;
}

function showAiStatus(ok, message) {
  const box = $("aiStatus");
  box.hidden = false;
  box.className = `ai-status ${ok === null ? "" : ok ? "ok" : "fail"}`;
  box.textContent = message;
}

async function useAi() {
  const provider = state.providers.find((p) => p.name === state.selected);
  const key = cleanKey($("apiKey").value);
  $("apiKey").value = key;
  if (provider?.requires_api_key !== false && !key) {
    showAiStatus(false, t("ai_paste_key"));
    $("apiKey").focus();
    return;
  }
  const problem = keyProblem(state.selected, key);
  if (problem) {
    showAiStatus(false, problem);
    $("apiKey").focus();
    return;
  }
  const candidate = { provider: state.selected, key };
  const button = $("useAi");
  button.disabled = true;
  showAiStatus(null, t("ai_testing"));
  try {
    const response = await fetch("/api/v1/byok/test", { method: "POST", headers: aiHeaders(candidate) });
    const result = await response.json();
    if (!result.ok) {
      const reason = friendlyAiError(result.message, candidate.provider) ?? result.message;
      showAiStatus(false, t("ai_failed", { reason }));
      return;
    }
    // Reuse the model that answered (it may differ from the default when the provider's
    // free catalog changed), so later checks skip the model discovery.
    state.ai = { ...candidate, model: result.model };
    setAiStatus();
    remember();
    showAiStatus(true, t("ai_connected", { name: providerName(result.provider), model: result.model, button: t("submit") }));
    toast(t("ai_connected_toast"));
  } catch {
    showAiStatus(false, t("ai_no_server"));
  } finally {
    button.disabled = false;
  }
}

function remember() {
  try {
    if ($("rememberKey").checked && state.ai) localStorage.setItem("veritas.ai", JSON.stringify(state.ai));
    else localStorage.removeItem("veritas.ai");
  } catch {
    // storage blocked (private mode): the key simply stays in memory
  }
}

function restoreAi() {
  try {
    const saved = JSON.parse(localStorage.getItem("veritas.ai") || "null");
    if (saved?.provider) {
      state.ai = saved;
      state.selected = saved.provider;
      $("apiKey").value = saved.key || "";
      $("rememberKey").checked = true;
      updatePrivacyText();
    }
  } catch {
    // ignore unreadable storage
  }
}

function updatePrivacyText() {
  $("privacyText").textContent = $("rememberKey").checked ? t("privacy_saved") : t("privacy_session");
}

function clearAi() {
  state.ai = null;
  $("apiKey").value = "";
  $("rememberKey").checked = false;
  remember();
  updatePrivacyText();
  $("aiStatus").hidden = true;
  setAiStatus();
  toast(t("ai_cleared_toast"));
}

// ---------------------------------------------------------------- image -> text (OCR)
let tesseractPromise = null;
function loadTesseract() {
  if (window.Tesseract) return Promise.resolve(window.Tesseract);
  tesseractPromise ??= new Promise((resolve, reject) => {
    const script = el("script", { src: TESSERACT_URL, async: true });
    script.onload = () => resolve(window.Tesseract);
    script.onerror = () => { tesseractPromise = null; reject(new Error("ocr-load")); };
    document.head.append(script);
  });
  return tesseractPromise;
}

function ocrLanguage() {
  const country = document.querySelector('input[name="country"]:checked').value;
  if (country === "FR") return "fra";
  if (country === "BR") return "por";
  return I18N.meta?.ocr || "por";
}

async function readImage(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const preview = $("imagePreview");
  const url = URL.createObjectURL(file);
  $("imageThumb").src = url;
  preview.hidden = false;
  preview.classList.remove("done");
  $("ocrTitle").textContent = t("ocr_reading");
  $("ocrHint").textContent = t("ocr_first_time");
  $("ocrBar").style.width = "5%";
  try {
    const Tesseract = await loadTesseract();
    const result = await Tesseract.recognize(file, ocrLanguage(), {
      logger: (m) => {
        if (m.status === "recognizing text") $("ocrBar").style.width = `${Math.round(10 + m.progress * 90)}%`;
      },
    });
    const text = result.data.text.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    preview.classList.add("done");
    if (!text) {
      $("ocrTitle").textContent = t("ocr_none");
      $("ocrHint").textContent = t("ocr_none_hint");
      return;
    }
    const current = $("claim").value.trim();
    $("claim").value = (current ? `${current}\n\n${text}` : text).slice(0, 5000);
    updateCounter();
    $("ocrTitle").textContent = t("ocr_done");
    $("ocrHint").textContent = t("ocr_done_hint");
    $("claim").focus();
  } catch {
    preview.classList.add("done");
    $("ocrTitle").textContent = t("ocr_fail");
    $("ocrHint").textContent = t("ocr_fail_hint");
  }
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function clearMedia() {
  state.mediaFile = null;
  $("imagePreview").hidden = true;
  $("imageInput").value = "";
  $("mediaIcon").hidden = true;
  $("imageThumb").hidden = false;
}

/** Any media file: images also get OCR; video/audio are sent for forensics and transcription. */
function handleFile(file) {
  if (!file) return;
  const kind = file.type.split("/")[0];
  if (!["image", "video", "audio"].includes(kind)) {
    toast(t("media_wrong_type"));
    return;
  }
  if (file.size > MEDIA_MAX_BYTES) {
    toast(t("media_too_big", { size: formatBytes(file.size) }));
    return;
  }
  state.mediaFile = file;
  if (kind === "image") {
    $("mediaIcon").hidden = true;
    $("imageThumb").hidden = false;
    readImage(file);
    return;
  }
  const preview = $("imagePreview");
  preview.hidden = false;
  preview.classList.add("done");
  $("imageThumb").hidden = true;
  const iconBox = $("mediaIcon");
  iconBox.hidden = false;
  iconBox.replaceChildren(icon(kind === "video" ? "video" : "mic"));
  $("ocrTitle").textContent = `${file.name} · ${formatBytes(file.size)}`;
  $("ocrHint").textContent = kind === "video" ? t("media_video_hint") : t("media_audio_hint");
}

function setupImageInput() {
  $("imageInput").addEventListener("change", (event) => handleFile(event.target.files[0]));
  $("removeImage").addEventListener("click", clearMedia);
  $("claim").addEventListener("paste", (event) => {
    const item = [...(event.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) {
      event.preventDefault();
      handleFile(item.getAsFile());
    }
  });
  const zone = $("dropZone");
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    const file = [...(event.dataTransfer?.files || [])].find((f) => /^(image|video|audio)\//.test(f.type));
    if (file) handleFile(file);
  });
}

// ---------------------------------------------------------------- check
let radarTimer = null;
const LOADING_KEYS = ["loading_1", "loading_2", "loading_3", "loading_4"];
const MEDIA_LOADING_KEYS = ["media_loading_1", "media_loading_2", "media_loading_3", "media_loading_4", "media_loading_5"];

function startLoading(keys = LOADING_KEYS) {
  showState("loading");
  const items = [...document.querySelectorAll("#radarAreas li")];
  items.forEach((li) => li.classList.remove("lit"));
  let tick = 0;
  clearInterval(radarTimer);
  radarTimer = setInterval(() => {
    items.forEach((li, index) => li.classList.toggle("lit", (tick + index) % 3 === 0));
    $("loadingText").textContent = t(keys[Math.floor(tick / 3) % keys.length]);
    tick += 1;
  }, 700);
}

function stopLoading() {
  clearInterval(radarTimer);
}

async function submit(event) {
  event?.preventDefault();
  const claim = $("claim").value.trim();
  const error = $("formError");
  error.hidden = true;
  const linkRaw = $("sourceUrl").value.trim();
  const link = linkRaw ? safeUrl(/^https?:\/\//i.test(linkRaw) ? linkRaw : `https://${linkRaw}`) : null;
  if (linkRaw && !link) {
    error.textContent = t("bad_link");
    error.hidden = false;
    return;
  }
  const country = document.querySelector('input[name="country"]:checked').value;
  if (state.mediaFile || (link && VIDEO_LINK.test(link))) {
    const form = new FormData();
    if (state.mediaFile) form.append("file", state.mediaFile, state.mediaFile.name);
    else form.append("url", link);
    if (claim) form.append("claim", claim);
    if (country) form.append("country", country);
    form.append("language", LANG);
    state.lastRequest = () => runMedia(form);
    await runMedia(form);
    return;
  }
  if (claim.length < 5) {
    error.textContent = t("need_claim");
    error.hidden = false;
    $("claim").focus();
    return;
  }
  const body = { claim, language: LANG };
  if (country) body.country = country;
  if (link) body.source_url = link;
  state.lastRequest = () => run(body);
  await run(body);
}

function beginRequest(keys) {
  const button = $("submitBtn");
  button.disabled = true;
  button.classList.add("busy");
  startLoading(keys);
  if (window.matchMedia("(max-width: 960px)").matches) {
    $("resultPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function endRequest() {
  const button = $("submitBtn");
  button.disabled = false;
  button.classList.remove("busy");
}

async function runMedia(form) {
  const headers = state.ai ? aiHeaders(state.ai) : {};
  beginRequest(MEDIA_LOADING_KEYS);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), MEDIA_TIMEOUT_MS);
  try {
    const response = await fetch(MEDIA_API, { method: "POST", headers, body: form, signal: controller.signal });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      throw new Error(data?.error?.message || t("http_error", { status: response.status }));
    }
    state.media = data;
    state.report = data.checks?.[0]?.report || null;
    state.filter = null;
    renderMediaReport(data);
  } catch (err) {
    stopLoading();
    $("errorText").textContent = err.name === "AbortError" ? t("media_timeout") : localizeNote(err.message);
    showState("error");
  } finally {
    clearTimeout(timeout);
    endRequest();
  }
}

async function run(body) {
  const headers = { "Content-Type": "application/json" };
  if (state.ai) Object.assign(headers, aiHeaders(state.ai));
  beginRequest(LOADING_KEYS);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(API, {
      method: "POST", headers, body: JSON.stringify(body), signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      const detail = data?.error?.message || (Array.isArray(data?.detail) ? t("invalid_text") : null);
      throw new Error(detail || t("http_error", { status: response.status }));
    }
    state.report = data;
    state.media = null;
    state.filter = null;
    renderReport(data);
  } catch (err) {
    stopLoading();
    $("errorText").textContent = err.name === "AbortError"
      ? t("sources_timeout")
      : t("something_wrong", { message: localizeNote(err.message) });
    showState("error");
  } finally {
    clearTimeout(timeout);
    endRequest();
  }
}

// ---------------------------------------------------------------- result
/** Fills the verdict card: colour, label, stamp for near-certain results and the truth scale. */
function renderVerdictCard(head, cert, stamp = null) {
  const card = $("verdictCard");
  card.dataset.tone = head.tone;
  const strong = Boolean(stamp) || Boolean(cert?.strong);
  card.dataset.strength = strong ? "strong" : cert?.level || "none";
  $("verdictIcon").replaceChildren(icon(head.icon));
  $("verdictLabel").textContent = head.label;
  $("verdictMeaning").textContent = head.meaning;
  $("verdictKicker").textContent = cert?.strong ? t(`kicker_strong_${cert.tone}`) : t("result_kicker");

  const stampBox = $("verdictStamp");
  const stampText = stamp || (cert?.strong ? t(`stamp_${cert.tone}`) : null);
  stampBox.hidden = !stampText;
  stampBox.textContent = stampText || "";

  const gauge = $("gauge");
  gauge.hidden = !cert || cert.pct === null;
  const scale = $("truthScale");
  scale.hidden = !cert;
  if (!cert) return;
  $("gaugeNum").textContent = cert.pct === null ? "" : `${cert.pct}%`;
  const value = $("gaugeValue");
  value.style.strokeDashoffset = "113.1";
  const marker = $("scaleMarker");
  marker.dataset.tone = cert.tone || "neutral";
  marker.style.left = "50%";
  $("scaleBar").setAttribute("aria-label", `${t("scale_aria")}: ${cert.text}`);
  $("certaintyText").textContent = cert.text;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    value.style.strokeDashoffset = String(113.1 * (1 - (cert.pct ?? 0) / 100));
    marker.style.left = `${cert.position}%`;
  }));
}

function renderReport(report) {
  stopLoading();
  $("forensicsBox").hidden = true;
  $("timelineBox").hidden = true;
  $("sourcesBox").hidden = false;
  const head = verdictInfo(report.verdict);
  if (report.verdict === "SEM_DADOS_SUFICIENTES" && report.primary_sources?.length) {
    head.meaning = t("v_no_data_meaning_sources"); // sources were found, they just don't answer
  }
  renderVerdictCard(head, certainty(report));
  renderAlerts(report);
  $("claimQuote").textContent = `“${report.claim}”`;
  renderExplanation(report.explanation || "");
  // The free-AI invitation only makes sense when no AI was configured at all.
  $("ctaAi").hidden = report.ai_used || Boolean(state.ai);
  renderSources();
  renderNotes(report);
  showState("result");
  $("resultState").scrollTop = 0;
}

function renderExplanation(text) {
  const target = $("explanation");
  target.replaceChildren();
  const parts = text.split(/(\[E\d+\])/g);
  for (const part of parts) {
    const match = part.match(/^\[(E\d+)\]$/);
    if (match) {
      target.append(el("button", {
        type: "button", class: "ref", text: match[1], "aria-label": t("see_source", { id: match[1] }),
        onclick: () => focusSource(match[1]),
      }));
    } else if (part) {
      target.append(part);
    }
  }
}

function focusSource(evidenceId) {
  state.filter = null;
  renderSources();
  const item = document.querySelector(`[data-evidence="${evidenceId}"]`);
  if (!item) return;
  item.scrollIntoView({ behavior: "smooth", block: "center" });
  item.classList.remove("flash");
  void item.offsetWidth;
  item.classList.add("flash");
  setTimeout(() => item.classList.remove("flash"), 1800);
}

function sourceArea(source) {
  return (CONNECTORS[source.connector] || ["gov", null])[0];
}
function sourceLang(source) {
  return (CONNECTORS[source.connector] || ["gov", null])[1];
}

function renderSources() {
  const sources = state.report?.primary_sources || [];
  const list = $("sourceList");
  list.replaceChildren();
  $("sourceCount").textContent = String(sources.length);
  $("noSources").hidden = sources.length > 0;

  const areas = [...new Set(sources.map(sourceArea))];
  const filter = $("areaFilter");
  filter.replaceChildren();
  if (areas.length > 1) {
    const makeButton = (key, label) => el("button", {
      type: "button", "aria-pressed": String(state.filter === key), text: label,
      onclick: () => { state.filter = key; renderSources(); },
    });
    filter.append(makeButton(null, t("filter_all")), ...areas.map((a) => makeButton(a, areaLabel(a))));
  }

  sources
    .filter((source) => !state.filter || sourceArea(source) === state.filter)
    .forEach((source, index) => list.append(sourceCard(source, index)));
}

function sourceCard(source, index) {
  const area = sourceArea(source);
  const lang = sourceLang(source);
  const foreign = lang && lang !== LANG;
  const link = safeUrl(source.url);
  const excerpt = el("p", { class: "excerpt", text: source.excerpt || "" });
  const longExcerpt = (source.excerpt || "").length > 220;
  if (longExcerpt) excerpt.classList.add("clamped");

  const tags = [];
  const date = formatDate(source.published_at);
  if (date) tags.push(el("span", { class: "tag", text: date }));
  if (source.venue) tags.push(el("span", { class: "tag", text: source.venue }));
  for (const [key, value] of Object.entries(source.identifiers || {}).slice(0, 3)) {
    tags.push(el("span", { class: "tag", text: `${key.toUpperCase()} ${value}` }));
  }
  if (source.authors?.length) {
    const authors = source.authors.slice(0, 2).join(", ") + (source.authors.length > 2 ? " et al." : "");
    tags.push(el("span", { class: "tag", text: authors }));
  }

  const body = el("div", { class: "source-body" },
    el("div", { class: "source-top" },
      el("span", { class: "source-id", text: source.evidence_id }),
      el("span", { class: "source-area", text: areaLabel(area) }),
      foreign ? el("span", { class: "lang-tag", text: lang.toUpperCase() }) : null,
      source.cited ? el("span", { class: "cited", text: t("cited") }) : null),
    el("h4", { text: source.title }),
    el("p", { class: "publisher", text: source.publisher }),
    excerpt,
    longExcerpt ? el("button", {
      type: "button", class: "more", text: t("read_more"),
      onclick: (event) => {
        const clamped = excerpt.classList.toggle("clamped");
        event.target.textContent = clamped ? t("read_more") : t("read_less");
      },
    }) : null,
    el("div", { class: "meta" },
      tags,
      foreign && (source.excerpt || source.title)
        ? el("button", {
          type: "button", class: "translate-btn",
          onclick: (event) => translateSource(event.currentTarget, source, lang),
        }, icon("translate"), t(`lang_from_${lang}`))
        : null,
      link ? el("a", { class: "open-link", href: link, target: "_blank", rel: "noopener noreferrer" },
        t("open_source"), icon("external")) : null),
  );
  return el("li", {
    class: "source", "data-evidence": source.evidence_id,
    style: `--c: var(${AREA_COLORS[area]}); --i: ${index}`,
  }, areaIcon(area), body);
}

// ---------------------------------------------------------------- media report
/** The checks behind the media headline: the worst verdict, and the surest check with it. */
function worstCheck(checks) {
  const verdicts = checks.map((c) => c.report.verdict);
  const worst = VERDICT_SEVERITY.find((v) => verdicts.includes(v));
  const matching = checks.filter((c) => c.report.verdict === worst);
  matching.sort((a, b) => (b.report.confidence_score || 0) - (a.report.confidence_score || 0));
  return { worst, check: matching[0] || null, count: verdicts.length };
}

function mediaHeadline(data) {
  const c2pa = data.forensics?.c2pa;
  if (c2pa && ["AI_GENERATED", "AI_EDITED", "INVALID_SIGNATURE"].includes(c2pa.verdict)) {
    const info = C2PA_LABELS[c2pa.verdict];
    const label = t(info.key);
    // Signed credentials are a strong signal on their own: stamped like a near-certain result.
    return { label, tone: info.tone, icon: "alert", meaning: c2paText(c2pa), stamp: c2pa.verdict === "AI_EDITED" ? null : label, cert: null };
  }
  const { worst, check, count } = worstCheck(data.checks || []);
  if (worst && worst !== "SEM_CHAVE_IA_DADOS_BRUTOS") {
    const base = verdictInfo(worst);
    const headlines = {
      FALSO: t("media_h_false"),
      ENGANOSO: t("media_h_misleading"),
      INCONCLUSIVO: t("media_h_inconclusive"),
      SEM_DADOS_SUFICIENTES: t("media_h_no_data"),
      VERDADEIRO: count === 1 ? t("media_h_true_one") : t("media_h_true_many"),
    };
    let meaning;
    if (worst === "VERDADEIRO") meaning = count === 1 ? t("media_m_true_one") : t("media_m_true_many", { count });
    else meaning = count === 1 ? t("media_m_worst_one", { label: base.label }) : t("media_m_worst_many", { count, label: base.label });
    return { label: headlines[worst], tone: base.tone, icon: base.icon, meaning, cert: certainty(check?.report) };
  }
  return {
    label: t("media_done"), tone: "info", icon: "book", cert: null,
    meaning: count ? t("media_done_checks") : t("media_done_none"),
  };
}

function renderMediaReport(data) {
  stopLoading();
  const head = mediaHeadline(data);
  renderVerdictCard(head, head.cert, head.stamp);

  const f = data.forensics;
  renderAlerts({ notes: data.notes || [] });
  $("claimQuote").textContent = f.source_url || f.filename || t("media_sent");
  $("explanation").replaceChildren(mediaSummary(data));
  const transcriptTip = (data.notes || []).some((n) => TRANSCRIPT_PREFIXES.some((p) => n.startsWith(p)));
  $("ctaAi").hidden = data.ai_used || Boolean(state.ai) || transcriptTip;

  renderForensics(f);
  renderTimeline(data.checks || []);
  $("sourcesBox").hidden = true;
  renderNotes({ notes: [...(data.notes || []), ...(f.warnings || [])], connector_failures: [] });
  showState("result");
}

function mediaSummary(data) {
  const f = data.forensics;
  const kind = t(`kind_${["image", "video", "audio"].includes(f.kind) ? f.kind : "unknown"}`);
  const parts = [t("media_size", { kind, size: formatBytes(f.size_bytes) })];
  if (f.exif?.duration_seconds) parts.push(t("media_with_duration", { seconds: Math.round(f.exif.duration_seconds) }));
  let text = `${parts.join(" ")}. `;
  if (f.transcript?.segments?.length) {
    const count = f.transcript.segments.length;
    const timed = data.checks.filter((c) => c.start_time !== null).length;
    text += t("transcribed", { count, segments: count === 1 ? t("segment_one") : t("segment_many") });
    if (timed === 0) text += t("no_checkable");
    else text += timed === 1 ? t("checked_one") : t("checked_many", { count: timed });
  } else if (f.kind === "video" || f.kind === "audio") {
    text += t("not_transcribed");
  }
  // The C2PA finding is in the headline (when decisive) and in the forensics table.
  if (f.c2pa && ["CAMERA_CAPTURE", "EDITED", "SIGNED_UNKNOWN"].includes(f.c2pa.verdict)) {
    text += c2paText(f.c2pa);
  }
  return text.trim();
}

/** C2PA finding in the page language (the server writes it in Portuguese). */
function c2paText(c2pa) {
  if (LANG === "pt") return c2pa.summary;
  const tool = c2pa.ai_tool || t("c2pa_tool_unknown");
  const actions = c2pa.summary.match(/editada \(([^)]*)\)/)?.[1] || (c2pa.actions || []).join(", ");
  const texts = {
    AI_GENERATED: t("c2pa_ai_generated", { tool }),
    AI_EDITED: t("c2pa_ai_edited", { tool }),
    EDITED: t("c2pa_edited", { actions }),
    CAMERA_CAPTURE: t("c2pa_camera"),
    SIGNED_UNKNOWN: t("c2pa_signed_unknown"),
    INVALID_SIGNATURE: t("c2pa_invalid"),
    NO_MANIFEST: t("c2pa_no_manifest"),
    UNAVAILABLE: t("c2pa_unavailable"),
  };
  let text = texts[c2pa.verdict] || c2pa.summary;
  if (!["INVALID_SIGNATURE", "NO_MANIFEST", "UNAVAILABLE"].includes(c2pa.verdict)) {
    if (c2pa.signed_by) text += ` ${t("c2pa_signed_by", { who: c2pa.signed_by })}`;
    if (c2pa.summary.includes("lista de confiança")) text += ` ${t("c2pa_untrusted")}`;
  }
  return text;
}

function forensicRow(label, value, tone) {
  return el("div", { class: "frow" },
    el("span", { class: "flabel", text: label }),
    el("span", { class: `fvalue${tone ? ` tone-${tone}` : ""}` }, value));
}

function clock(seconds) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function renderForensics(f) {
  const grid = $("forensicGrid");
  grid.replaceChildren();
  if (f.c2pa) {
    const info = C2PA_LABELS[f.c2pa.verdict] || C2PA_LABELS.NO_MANIFEST;
    grid.append(forensicRow(t("f_c2pa"),
      el("span", {}, el("span", { class: `pill tone-${info.tone}`, text: t(info.key) }), " ", c2paText(f.c2pa))));
  }
  const exif = f.exif;
  if (exif?.camera) grid.append(forensicRow(t("f_camera"), exif.camera));
  if (exif?.captured_at) grid.append(forensicRow(t("f_captured"), exif.captured_at));
  if (exif?.software) grid.append(forensicRow(t("f_software"), exif.software, "warn"));
  if (exif?.gps) {
    const { latitude: lat, longitude: lon } = exif.gps;
    grid.append(forensicRow(t("f_gps"),
      el("a", { href: `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=15/${lat}/${lon}`, target: "_blank", rel: "noopener noreferrer", text: `${lat}, ${lon} ↗` })));
  }
  if (exif?.duration_seconds) {
    const total = Math.round(exif.duration_seconds);
    grid.append(forensicRow(t("f_duration"), t("f_duration_value", { min: Math.floor(total / 60), sec: String(total % 60).padStart(2, "0") })));
  }
  if (exif?.width && exif?.height) grid.append(forensicRow(t("f_dimensions"), `${exif.width} × ${exif.height} px`));
  for (const warning of exif?.warnings || []) grid.append(forensicRow(t("f_warning"), localizeNote(warning), "warn"));
  if (f.transcript?.engine && f.transcript.engine !== "none") {
    const engines = { groq_whisper: "Whisper (Groq)", openai_whisper: "Whisper (OpenAI)", gemini: "Gemini", whisper_local: t("f_whisper_local") };
    grid.append(forensicRow(t("f_transcript"), engines[f.transcript.engine] || f.transcript.engine));
  }
  grid.append(forensicRow(t("f_hash"), el("code", { class: "hash", title: f.sha256, text: `${f.sha256.slice(0, 16)}…` })));
  for (const missing of f.capabilities_missing || []) grid.append(forensicRow(t("f_not_checked"), localizeNote(missing), "neutral"));

  const frames = $("keyframes");
  frames.replaceChildren();
  for (const frame of f.keyframes || []) {
    if (!String(frame.data_url).startsWith("data:image/jpeg;base64,")) continue;
    const time = clock(frame.time_seconds);
    frames.append(el("figure", {},
      el("img", { src: frame.data_url, alt: t("frame_alt", { time }), loading: "lazy" }),
      el("figcaption", { text: time })));
  }
  $("forensicsBox").hidden = false;
}

function renderTimeline(checks) {
  const list = $("timelineList");
  list.replaceChildren();
  $("timelineBox").hidden = checks.length === 0;
  checks.forEach((check, index) => {
    const verdict = verdictInfo(check.report.verdict);
    const cert = certainty(check.report);
    const detail = el("div", { class: "tl-detail", hidden: true });
    const button = el("button", {
      type: "button", class: "tl-head", "aria-expanded": "false",
      onclick: () => {
        const open = detail.hidden;
        detail.hidden = !open;
        button.setAttribute("aria-expanded", String(open));
        if (open && !detail.childElementCount) detail.append(...timelineDetail(check.report));
      },
    },
    el("span", { class: "tl-time", text: check.start_time === null ? t("context_text") : check.label }),
    el("span", { class: "tl-quote", text: `“${check.quote}”` }),
    el("span", {
      class: `pill tone-${verdict.tone}${cert?.strong ? " strong" : ""}`,
      text: cert?.pct != null ? `${verdict.label} · ${cert.pct}%` : verdict.label,
    }));
    list.append(el("li", { class: "tl-item", style: `--i: ${index}` }, button, detail));
  });
}

function timelineDetail(report) {
  const nodes = [];
  if (report.claim) nodes.push(el("p", { class: "tl-claim" }, el("b", { text: t("claim_checked") }), report.claim));
  const cert = certainty(report);
  if (cert) nodes.push(el("p", { class: `tl-certainty tone-${cert.tone || "neutral"}`, text: cert.text }));
  nodes.push(el("p", { class: "tl-explanation", text: stripRefs(report.explanation) }));
  const sources = (report.primary_sources || []).slice(0, 3);
  if (sources.length) {
    nodes.push(el("ol", { class: "source-list" }, sources.map((s, i) => sourceCard(s, i))));
  }
  return nodes;
}

// ---------------------------------------------------------------- translation
async function translateText(text, from) {
  // On-device, free and private when the browser ships a translator (Chrome 138+).
  if ("Translator" in self) {
    const options = { sourceLanguage: from, targetLanguage: LANG };
    // Some browsers expose the API but never settle (model unavailable): never hang the UI.
    const availability = await withTimeout(self.Translator.availability(options), 2500);
    if (availability && availability !== "unavailable") {
      const translator = await withTimeout(self.Translator.create(options), 20_000);
      if (translator) return withTimeout(translator.translate(text), 15_000);
    }
  }
  return null;
}

function withTimeout(promise, ms) {
  return Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(null), ms))]);
}

async function translateSource(button, source, lang) {
  const card = button.closest(".source-body");
  const existing = card.querySelector(".translation");
  if (existing) {
    existing.remove();
    return;
  }
  const original = `${source.title}. ${source.excerpt || ""}`.trim();
  const label = button.lastChild.textContent;
  button.disabled = true;
  button.lastChild.textContent = t("translating");
  let translated = null;
  try {
    translated = await translateText(original, lang);
  } catch {
    translated = null;
  } finally {
    button.disabled = false;
    button.lastChild.textContent = label;
  }
  const box = translated
    ? el("div", { class: "translation" }, el("small", { text: t("auto_translation") }), translated)
    : el("div", { class: "translation" },
      el("small", { text: t("translation") }),
      t("no_browser_translate"),
      el("a", {
        href: `https://translate.google.com/?sl=${lang}&tl=${LANG}&op=translate&text=${encodeURIComponent(original.slice(0, 4500))}`,
        target: "_blank", rel: "noopener noreferrer", text: t("google_translate"),
      }));
  card.querySelector(".excerpt").after(box);
}

// ---------------------------------------------------------------- alerts & notes
// The server writes notes in Portuguese; these prefixes identify them whatever the page language.
const VAGUE_PREFIX = "A afirmação não diz onde";
const TRANSCRIPT_PREFIXES = ["Sem transcrição", "A transcrição falhou", "Whisper local falhou"];
const AI_FAILURE_PREFIXES = ["IA indisponível", "Configuração de IA"];

/** Known server messages -> dictionary key (+ names of the captured values). */
const NOTE_RULES = [
  [/^Para receber um veredito explicado por IA/, "note_free_keys"],
  [/^A afirmação não diz onde/, "note_vague"],
  [/^IA indisponível \((.*)\)\. Exibindo/s, "note_ai_unavailable", ["reason"]],
  [/^Configuração de IA não utilizada: (.*)$/s, "note_ai_config", ["reason"]],
  [/^Citações descartadas \(não correspondem a evidências\): (.*)$/s, "note_citations_dropped", ["ids"]],
  [/^Veredito (\w+) rebaixado para (\w+):/, "note_downgraded", ["from", "to"]],
  [/^Triagem por IA falhou/, "note_triage_failed"],
  [/^Sem transcrição:/, "note_no_transcript"],
  [/^A transcrição falhou: (.*)$/s, "note_transcript_failed", ["reason"]],
  [/^Whisper local falhou \((.*)\)\.?$/, "note_whisper_failed", ["reason"]],
  [/^Nenhuma afirmação verificável foi encontrada na fala/, "note_no_claims"],
  [/^Tipo de arquivo não reconhecido/, "warn_unknown_type"],
  [/^Mídia com (\d+) s: só os primeiros (\d+) s/, "warn_truncated", ["seconds", "max"]],
  [/^A mídia não tem faixa de áudio/, "warn_no_audio"],
  [/^Arquivo processado por software de edição\/geração: (.*)\.$/s, "warn_software", ["name"]],
  [/^Sem data de captura nem câmera/, "warn_no_exif"],
  [/^ffmpeg: duração/, "missing_ffmpeg"],
  [/^c2pa: detecção/, "missing_c2pa"],
  [/^Nenhuma chave de IA informada/, "note_no_key"],
  // errors of the media route (shown on the error screen)
  [/^Envie um arquivo ou cole o link/, "err_need_media"],
  [/^Esse link aponta para uma rede interna/, "err_internal_link"],
  [/^O link precisa começar com http/, "err_link_scheme"],
  [/^Não foi possível encontrar esse endereço/, "err_address"],
  [/^Não foi possível baixar o link \((.*)\)\.$/, "err_download", ["reason"]],
  [/^Não foi possível baixar o vídeo: (.*)$/s, "err_download_video", ["reason"]],
  [/^O link respondeu HTTP (\d+)/, "err_http", ["status"]],
  [/^O link redireciona vezes demais/, "err_redirects"],
  [/^O link mudou de endereço/, "err_moved"],
  [/^O arquivo está vazio/, "err_empty"],
  [/^O arquivo (do link )?passa do limite/, "err_too_big"],
  [/^O vídeo passa do limite/, "err_video_limit"],
  [/^Baixar vídeos de links exige o yt-dlp/, "err_needs_ytdlp"],
  [/^FFmpeg indisponível/, "err_no_ffmpeg"],
];

function localizeNote(note) {
  if (LANG === "pt") return note;
  for (const [pattern, key, names = []] of NOTE_RULES) {
    const match = note.match(pattern);
    if (!match) continue;
    const vars = Object.fromEntries(names.map((name, i) => [name, match[i + 1]]));
    if (key === "note_downgraded") {
      vars.from = verdictInfo(vars.from).label;
      vars.to = verdictInfo(vars.to).label;
    }
    return t(key, vars);
  }
  return note;
}

function renderAlerts(report) {
  const box = $("alerts");
  box.replaceChildren();
  const notes = report.notes || [];
  const aiFailure = notes.find((n) => AI_FAILURE_PREFIXES.some((p) => n.startsWith(p)));
  if (aiFailure) {
    box.append(el("div", { class: "alert warn" }, icon("warning"),
      el("div", {},
        el("b", { text: t("alert_ai_title") }),
        el("p", { text: friendlyAiError(aiFailure, state.ai?.provider) ?? localizeNote(aiFailure) }),
        el("button", { type: "button", class: "link-btn", text: t("alert_test_key"), onclick: openAiPanel }))));
  }
  const transcriptNote = notes.find((n) => TRANSCRIPT_PREFIXES.some((p) => n.startsWith(p)));
  if (transcriptNote) {
    box.append(el("div", { class: "alert tip" }, icon("mic"),
      el("div", {}, el("b", { text: t("alert_transcript_title") }),
        el("p", { text: friendlyAiError(transcriptNote, state.ai?.provider) ?? localizeNote(transcriptNote) }),
        el("button", { type: "button", class: "link-btn", text: t("cta_button"), onclick: openAiPanel }))));
  }
  const vague = notes.find((n) => n.startsWith(VAGUE_PREFIX));
  if (vague) {
    box.append(el("div", { class: "alert tip" }, icon("bulb"),
      el("div", {}, el("b", { text: t("alert_tip_title") }), el("p", { text: localizeNote(vague) }))));
  }
}

function renderNotes(report) {
  const hidden = [VAGUE_PREFIX, ...AI_FAILURE_PREFIXES, ...TRANSCRIPT_PREFIXES];
  const notes = (report.notes || []).filter((n) => !hidden.some((p) => n.startsWith(p))).map(localizeNote);
  for (const failure of report.connector_failures || []) {
    const area = CONNECTORS[failure.connector]?.[0];
    notes.push(t("connector_failed", { area: area ? areaLabel(area).toLowerCase() : failure.connector, id: failure.connector }));
  }
  const box = $("notesBox");
  box.hidden = notes.length === 0;
  $("notesList").replaceChildren(...notes.map((n) => el("li", { text: n })));
}

// ---------------------------------------------------------------- sharing
/** Removes "[E1]" citation markers (and the space before them) for plain-text sharing. */
function stripRefs(text) {
  return (text || "").replace(/\s*\[E\d+\]/g, "").replace(/\s{2,}/g, " ").trim();
}

/** "(high confidence, 92%)" next to a verdict, or "" without AI. */
function confidenceSuffix(report) {
  const cert = certainty(report);
  return cert?.pct != null ? ` (${t(`level_${cert.level}`)}, ${cert.pct}%)` : "";
}

function mediaShareText() {
  const data = state.media;
  const head = mediaHeadline(data);
  const lines = [`🔎 *${head.label}*`, head.meaning, ""];
  for (const check of data.checks || []) {
    const verdict = verdictInfo(check.report.verdict);
    const label = check.start_time === null ? t("context_text") : check.label;
    lines.push(`${verdict.emoji} ${label}: “${check.quote.slice(0, 140)}” → ${verdict.label}${confidenceSuffix(check.report)}`);
  }
  if (data.forensics?.c2pa) lines.push("", t("share_c2pa", { summary: c2paText(data.forensics.c2pa) }));
  lines.push("", t("share_footer"));
  return lines.join("\n");
}

function shareText() {
  if (state.media) return mediaShareText();
  const report = state.report;
  const verdict = verdictInfo(report.verdict);
  const lines = [
    `${verdict.emoji} *${verdict.label}*${confidenceSuffix(report)}`,
    `“${report.claim.slice(0, 280)}”`,
    "",
    report.ai_used ? stripRefs(report.explanation).slice(0, 600) : verdict.meaning,
    "",
    t("share_sources"),
  ];
  for (const source of (report.primary_sources || []).slice(0, 4)) {
    const link = safeUrl(source.url);
    if (link) lines.push(`• ${source.title.slice(0, 90)}\n${link}`);
  }
  lines.push("", t("share_footer"));
  return lines.join("\n");
}

function shareWhatsApp() {
  window.open(`https://wa.me/?text=${encodeURIComponent(shareText())}`, "_blank", "noopener");
}

async function copySummary() {
  try {
    await navigator.clipboard.writeText(shareText());
    toast(t("copied"));
  } catch {
    toast(t("copy_fail"));
  }
}

// Draws a 1080x1350 share card (portrait, ideal for WhatsApp/Instagram) with the verdict.
function drawShareCard() {
  const report = state.report;
  const verdict = verdictInfo(report.verdict);
  const cert = certainty(report);
  const tones = {
    true: ["#12875a", "#e3f6ec"], false: ["#d33a3a", "#fdeaea"], warn: ["#c97800", "#fff3df"],
    neutral: ["#5f6b80", "#eef0f5"], info: ["#3b5bdb", "#e9eeff"],
  };
  const [tone, soft] = tones[verdict.tone];
  const strong = Boolean(cert?.strong);
  const W = 1080, H = 1350, P = 80;
  const canvas = el("canvas", { width: W, height: H });
  const ctx = canvas.getContext("2d");
  const font = (weight, size) => `${weight} ${size}px system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif`;

  ctx.fillStyle = "#f4f6fb"; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "#ffffff"; roundRect(ctx, 40, 40, W - 80, H - 80, 40); ctx.fill();

  // brand
  ctx.fillStyle = "#3b5bdb";
  ctx.beginPath(); ctx.moveTo(P + 24, P); ctx.lineTo(P, P + 10); ctx.lineTo(P, P + 28);
  ctx.quadraticCurveTo(P + 2, P + 52, P + 24, P + 60); ctx.quadraticCurveTo(P + 46, P + 52, P + 48, P + 28);
  ctx.lineTo(P + 48, P + 10); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = "#fff"; ctx.lineWidth = 5; ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.beginPath(); ctx.moveTo(P + 14, P + 30); ctx.lineTo(P + 21, P + 37); ctx.lineTo(P + 34, P + 22); ctx.stroke();
  ctx.fillStyle = "#131a2e"; ctx.font = font(800, 40); ctx.fillText("Veritas", P + 66, P + 44);
  ctx.fillStyle = "#6a7488"; ctx.font = font(500, 26); ctx.fillText(t("tagline"), P + 230, P + 43);

  // verdict block: solid colour when the AI is near certain, soft tint otherwise
  let y = P + 110;
  const blockHeight = cert ? 250 : 210;
  ctx.fillStyle = strong ? tone : soft; roundRect(ctx, P, y, W - 2 * P, blockHeight, 32); ctx.fill();
  const ink = strong ? "#ffffff" : tone;
  ctx.fillStyle = ink; ctx.font = font(800, 26);
  ctx.fillText(strong ? t(`kicker_strong_${cert.tone}`).toUpperCase() : t("card_result"), P + 40, y + 62);
  ctx.font = font(800, 76); ctx.fillText(fit(ctx, verdict.label, W - 2 * P - 80), P + 40, y + 140);
  ctx.fillStyle = strong ? "#ffffff" : "#3c465c"; ctx.font = font(500, 28);
  ctx.fillText(fit(ctx, verdict.meaning, W - 2 * P - 80), P + 40, y + 185);
  if (cert) {
    ctx.font = font(700, 28);
    ctx.fillText(fit(ctx, cert.text, W - 2 * P - 80), P + 40, y + 228);
  }
  y += blockHeight;

  // truth scale (False ↔ True) with the verdict's position
  if (cert) {
    y += 44;
    const barX = P, barW = W - 2 * P, barH = 18;
    const gradient = ctx.createLinearGradient(barX, 0, barX + barW, 0);
    gradient.addColorStop(0, "#d33a3a"); gradient.addColorStop(0.5, "#c9ced9"); gradient.addColorStop(1, "#12875a");
    ctx.fillStyle = gradient; roundRect(ctx, barX, y, barW, barH, 9); ctx.fill();
    const markerX = barX + (barW * cert.position) / 100;
    ctx.fillStyle = "#ffffff"; ctx.beginPath(); ctx.arc(markerX, y + barH / 2, 20, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = cert.tone ? tones[cert.tone][0] : "#5f6b80";
    ctx.beginPath(); ctx.arc(markerX, y + barH / 2, 13, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#6a7488"; ctx.font = font(700, 22);
    ctx.fillText(t("scale_false"), barX, y + 56);
    ctx.textAlign = "right"; ctx.fillText(t("scale_true"), barX + barW, y + 56); ctx.textAlign = "left";
    y += 40;
  }

  // claim (quote bar grows with the number of lines)
  y += 60;
  ctx.fillStyle = "#3c465c"; ctx.font = `italic ${font(500, 34)}`;
  const claimTop = y;
  const claimBottom = wrap(ctx, `“${report.claim}”`, P + 32, y + 34, W - 2 * P - 40, 46, 3);
  ctx.fillStyle = "#e2e6ef"; ctx.fillRect(P, claimTop, 8, claimBottom - claimTop + 14);
  y = claimBottom + 80;

  // explanation (AI) or hint
  if (report.ai_used && report.explanation) {
    ctx.fillStyle = "#131a2e"; ctx.font = font(500, 30);
    y = wrap(ctx, stripRefs(report.explanation), P, y, W - 2 * P, 42, cert ? 4 : 5) + 76;
  }

  // sources
  ctx.fillStyle = "#6a7488"; ctx.font = font(800, 24); ctx.fillText(t("card_sources"), P, y); y += 26;
  for (const source of (report.primary_sources || []).slice(0, 4)) {
    if (y > H - 220) break;
    ctx.fillStyle = "#f7f8fc"; roundRect(ctx, P, y, W - 2 * P, 104, 20); ctx.fill();
    ctx.fillStyle = "#131a2e"; ctx.font = font(700, 28);
    ctx.fillText(fit(ctx, source.title, W - 2 * P - 48), P + 24, y + 44);
    ctx.fillStyle = "#6a7488"; ctx.font = font(500, 22);
    let host = "";
    try { host = new URL(source.url).hostname.replace(/^www\./, ""); } catch { /* ignore */ }
    ctx.fillText(fit(ctx, `${source.publisher}${host ? ` · ${host}` : ""}`, W - 2 * P - 48), P + 24, y + 80);
    y += 120;
  }

  ctx.fillStyle = "#6a7488"; ctx.font = font(500, 24);
  const day = new Date().toLocaleDateString(LOCALE);
  ctx.fillText(t("card_checked_on", { day }), P, H - P - 10);
  return canvas;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

function fit(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let cut = text;
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > maxWidth) cut = cut.slice(0, -1);
  return `${cut.trimEnd()}…`;
}

function wrap(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
  const words = text.split(/\s+/);
  let line = "";
  let lines = 0;
  for (let i = 0; i < words.length; i += 1) {
    const test = line ? `${line} ${words[i]}` : words[i];
    if (ctx.measureText(test).width > maxWidth && line) {
      lines += 1;
      if (lines === maxLines) { ctx.fillText(fit(ctx, `${line} ${words.slice(i).join(" ")}`, maxWidth), x, y); return y; }
      ctx.fillText(line, x, y);
      y += lineHeight;
      line = words[i];
    } else {
      line = test;
    }
  }
  if (line) ctx.fillText(line, x, y);
  return y;
}

async function downloadImage() {
  if (!state.report) return toast(t("card_no_claim"));
  const canvas = drawShareCard();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) return toast(t("card_fail"));
  const name = t("card_file");
  const file = new File([blob], name, { type: "image/png" });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: "Veritas", text: t("tagline") });
      return;
    } catch {
      // user cancelled or share failed: fall back to download
    }
  }
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast(t("card_saved"));
}

// ---------------------------------------------------------------- wiring
function init() {
  renderAreas();
  renderExamples();
  restoreAi();
  loadProviders();
  setAiStatus();
  $("rememberKey").addEventListener("change", () => { updatePrivacyText(); remember(); });
  $("checkForm").addEventListener("submit", submit);
  $("claim").addEventListener("input", updateCounter);
  $("claim").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit(event);
  });
  setupImageInput();
  $("aiPill").addEventListener("click", openAiPanel);
  $("openAi").addEventListener("click", openAiPanel);
  $("toggleKey").addEventListener("click", () => {
    const input = $("apiKey");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    $("toggleKey").textContent = show ? t("key_hide") : t("key_show");
  });
  $("useAi").addEventListener("click", useAi);
  $("clearAi").addEventListener("click", clearAi);
  $("shareBtn").addEventListener("click", shareWhatsApp);
  $("copyBtn").addEventListener("click", copySummary);
  $("imageBtn").addEventListener("click", downloadImage);
  $("newBtn").addEventListener("click", () => {
    $("claim").value = "";
    $("sourceUrl").value = "";
    clearMedia();
    state.media = null;
    updateCounter();
    showState("empty");
    $("claim").focus();
  });
  $("retryBtn").addEventListener("click", () => state.lastRequest && state.lastRequest());
}

document.addEventListener("DOMContentLoaded", init);
