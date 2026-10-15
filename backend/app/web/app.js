/* Veritas - citizen web app (vanilla JS, no build step).
 * Security: every value coming from the API or from public sources is inserted with
 * textContent / DOM APIs (never parsed as HTML), and only http(s) links are rendered.
 */
"use strict";

const API = "/api/v1/fact-check/text";
const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
const REQUEST_TIMEOUT_MS = 90_000;

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
  translate: "M4 5h9M8.5 3v2m3 0c-.8 4-3.6 7.3-7 9m2-6c1.2 2.4 3.3 4.5 6 5.5M13 21l4.5-10L22 21m-7.5-3h6",
};

const AREAS = {
  gov: { label: "Governo e Congresso", hint: "Câmara, Senado, data.gouv", color: "--a-gov" },
  stats: { label: "Estatísticas oficiais", hint: "IBGE, INSEE", color: "--a-stats" },
  law: { label: "Leis e tribunais", hint: "Planalto, STJ, EUR-Lex", color: "--a-law" },
  science: { label: "Ciência e saúde", hint: "PubMed, OMS", color: "--a-science" },
  world: { label: "Mundo e conflitos", hint: "ONU, GDELT", color: "--a-world" },
  climate: { label: "Clima e ambiente", hint: "Copernicus, NOAA", color: "--a-climate" },
  web: { label: "Memória da web", hint: "Internet Archive", color: "--a-web" },
};

// connector id -> [area, language of its content]
const CONNECTORS = {
  "br.camara": ["gov", "pt"], "br.senado": ["gov", "pt"], "br.transparencia": ["gov", "pt"],
  "br.ibge": ["stats", "pt"], "br.legislacao": ["law", "pt"], "br.stj_precedentes": ["law", "pt"],
  "fr.data_gouv": ["gov", "fr"], "fr.insee": ["stats", "fr"], "fr.legifrance": ["law", "fr"],
  "fr.judilibre": ["law", "fr"], "eu.eurlex": ["law", "en"], "science.pubmed": ["science", "en"],
  "health.who_gho": ["science", "en"], "geo.gdelt": ["world", "en"], "geo.reliefweb": ["world", "en"],
  "web.wayback": ["web", "pt"], "climate.copernicus": ["climate", "pt"],
  "climate.noaa": ["climate", "pt"],
};
const DOMAIN_TO_AREA = {
  politics_legislation: "gov", economy_statistics: "stats", legal_justice: "law",
  health_science: "science", geopolitics: "world", web_history: "web",
  climate_environment: "climate",
};
const LANG_NAMES = { en: "inglês", fr: "francês" };

const VERDICTS = {
  VERDADEIRO: { label: "Verdadeiro", tone: "true", icon: "check", emoji: "✅",
    meaning: "As fontes oficiais confirmam esta afirmação." },
  FALSO: { label: "Falso", tone: "false", icon: "cross", emoji: "❌",
    meaning: "As fontes oficiais contradizem esta afirmação." },
  ENGANOSO: { label: "Enganoso", tone: "warn", icon: "alert", emoji: "⚠️",
    meaning: "Tem parte de verdade, mas está fora de contexto ou exagerado." },
  INCONCLUSIVO: { label: "Inconclusivo", tone: "neutral", icon: "question", emoji: "❔",
    meaning: "As fontes encontradas não permitem uma conclusão segura." },
  SEM_DADOS_SUFICIENTES: { label: "Sem dados suficientes", tone: "neutral", icon: "question", emoji: "❔",
    meaning: "Não encontramos dados oficiais sobre este assunto." },
  SEM_CHAVE_IA_DADOS_BRUTOS: { label: "Veja as fontes oficiais", tone: "info", icon: "book", emoji: "📚",
    meaning: "Reunimos o que as fontes oficiais dizem. Leia e tire sua conclusão." },
};

const EXAMPLES = [
  { area: "science", text: "Vacinas causam autismo em crianças." },
  { area: "stats", text: "A inflação no Brasil passou de 10% nos últimos 12 meses." },
  { area: "law", text: "A Lei 12.965/2014 obriga provedores a guardar registros por 5 anos." },
  { area: "gov", text: "A Câmara aprovou a reforma tributária que cria o IBS e a CBS." },
  { area: "climate", text: "2023 e 2024 foram recordes consecutivos de temperatura média global." },
  { area: "world", text: "A Ucrânia e a Rússia assinaram um cessar-fogo este mês." },
  { area: "stats", text: "Le taux de chômage en France a doublé depuis 2020.", country: "FR" },
];

const FALLBACK_PROVIDERS = [
  { name: "gemini", free_tier: true, requires_api_key: true, get_key_url: "https://aistudio.google.com/apikey",
    steps: ["Entre com sua conta Google em aistudio.google.com/apikey", "Clique em “Create API key” e copie", "Cole a chave abaixo"] },
  { name: "groq", free_tier: true, requires_api_key: true, get_key_url: "https://console.groq.com/keys",
    steps: ["Crie uma conta grátis em console.groq.com", "Em “API Keys”, crie e copie a chave", "Cole a chave abaixo"] },
  { name: "ollama", free_tier: true, requires_api_key: false, get_key_url: null,
    steps: ["Instale o Ollama (ollama.com) e rode: ollama pull llama3.1", "Pronto: não precisa de chave"] },
];
const PROVIDER_NAMES = { gemini: "Google Gemini", groq: "Groq", ollama: "Ollama (no seu PC)", anthropic: "Claude", openai: "OpenAI" };

// ---------------------------------------------------------------- state & helpers
const state = { ai: null, selected: "gemini", providers: [], report: null, filter: null, lastBody: null };
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
  return el("span", { class: "area-icon", style: `--c: var(${AREAS[area].color})` }, icon(area));
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
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
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

// ---------------------------------------------------------------- static UI
function renderAreas() {
  const list = $("areasEmpty");
  const radar = $("radarAreas");
  const keys = Object.keys(AREAS);
  keys.forEach((key, index) => {
    list.append(el("li", { class: "area" }, areaIcon(key), AREAS[key].label, el("small", { text: AREAS[key].hint })));
    radar.append(el("li", { "data-area": key, style: `--angle: ${(360 / keys.length) * index}deg` }, areaIcon(key)));
  });
}

function renderExamples() {
  const box = $("examples");
  for (const example of EXAMPLES) {
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
      }, el("span", { class: "swatch", style: `background: var(${AREAS[example.area].color})` }), example.text),
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
      el("b", { text: PROVIDER_NAMES[provider.name] || provider.name }),
      el("small", { class: "free", text: "Grátis" }),
      el("small", { text: provider.requires_api_key ? "sem cartão" : "sem chave" })),
    );
  }
  if (paid.length) {
    const select = el("select", {
      class: "provider-more", "aria-label": "Outros provedores (pagos)",
      onchange: (event) => event.target.value && selectProvider(event.target.value),
    }, el("option", { value: "", text: "Outros (pagos): escolher…" }),
    paid.map((p) => el("option", { value: p.name, text: PROVIDER_NAMES[p.name] || p.name })));
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
  help.append(
    el("b", { text: provider.free_tier ? "Como pegar sua chave grátis:" : "Como pegar sua chave:" }),
    el("ol", {}, (provider.steps || []).map((step) => el("li", { text: step }))),
    link ? el("a", { href: link, target: "_blank", rel: "noopener noreferrer", text: "Abrir página da chave ↗" }) : null,
  );
  $("keyRow").hidden = provider.requires_api_key === false;
}

function setAiStatus() {
  const pill = $("aiPill");
  pill.classList.toggle("on", Boolean(state.ai));
  $("aiPillText").textContent = state.ai
    ? `IA: ${PROVIDER_NAMES[state.ai.provider] || state.ai.provider}`
    : "Grátis · sem IA";
}

function aiHeaders(ai) {
  const headers = { "X-Provider": ai.provider };
  if (ai.key) headers["X-API-Key"] = ai.key;
  if (ai.model) headers["X-Model"] = ai.model;
  return headers;
}

/** Turns provider error messages into plain Portuguese with a next step. */
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
function keyProblem(providerName, key) {
  const format = KEY_FORMATS[providerName];
  if (!format || !key) return null;
  const name = PROVIDER_NAMES[providerName] || providerName;
  if (/[*•…]|\.\.\./.test(key)) {
    return `Essa chave está mascarada (tem * ou …). É a versão resumida que aparece na lista do painel. No ${name}, a chave completa só aparece uma vez, quando é criada: crie uma chave nova em ${format.console} e copie na hora.`;
  }
  if (!key.startsWith(format.prefix)) {
    return `As chaves do ${name} começam com “${format.prefix}”. Confira se você copiou a chave (e não o nome dela) e se escolheu o provedor certo acima.`;
  }
  if (key.length < format.min) {
    return `A chave parece incompleta: tem ${key.length} caracteres, e as do ${name} costumam ter ${format.typical}. Copie de novo a chave inteira.`;
  }
  return null;
}

/** Turns provider error messages into plain Portuguese with a next step. */
function friendlyAiError(message, providerName) {
  const raw = String(message || "");
  const text = raw.toLowerCase();
  const name = PROVIDER_NAMES[providerName] || "provedor";
  const reason = raw.match(/\(([^()]*)\)\.?$/)?.[1];
  const said = reason ? ` Resposta do ${name}: “${reason}”.` : "";
  if (text.includes("rejected") || text.includes("permission")) {
    const format = KEY_FORMATS[providerName];
    const tip = format
      ? ` Dica: no ${name}, a chave completa só aparece uma vez, no momento em que é criada. Se você copiou da lista de chaves, crie uma nova em ${format.console} e copie na hora.`
      : " Confira se copiou a chave inteira e se escolheu o provedor certo.";
    return `O ${name} não aceitou essa chave.${said}${tip}`;
  }
  if (text.includes("rate limit") || text.includes("quota")) {
    return `A cota gratuita acabou por enquanto. Espere alguns minutos ou use outro provedor gratuito.${said}`;
  }
  if (text.includes("not found")) return `O modelo de IA não está disponível para esta chave.${said}`;
  if (text.includes("timed out") || text.includes("demorou")) return "A IA demorou demais para responder. Tente de novo.";
  if (text.includes("connect")) return "Não foi possível falar com o provedor de IA. Verifique sua internet.";
  if (text.includes("malformed")) return "A chave tem caracteres inválidos. Copie de novo, só a chave.";
  if (text.includes("requires an api key") || text.includes("x-api-key")) return "Cole sua chave no campo acima.";
  return raw;
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
    showAiStatus(false, "Cole sua chave no campo acima.");
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
  showAiStatus(null, "Testando a conexão com a IA…");
  try {
    const response = await fetch("/api/v1/byok/test", { method: "POST", headers: aiHeaders(candidate) });
    const result = await response.json();
    if (!result.ok) {
      showAiStatus(false, `Não funcionou. ${friendlyAiError(result.message, candidate.provider)}`);
      return;
    }
    // Reuse the model that answered (it may differ from the default when the provider's
    // free catalog changed), so later checks skip the model discovery.
    state.ai = { ...candidate, model: result.model };
    setAiStatus();
    remember();
    showAiStatus(true, `Conectado: ${PROVIDER_NAMES[result.provider] || result.provider} (${result.model}). Agora clique em “Verificar agora”.`);
    toast("IA conectada!");
  } catch {
    showAiStatus(false, "Sem conexão com o servidor do Veritas.");
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
  $("privacyText").textContent = $("rememberKey").checked
    ? "Sua chave fica guardada só neste navegador. Desmarque a opção para apagá-la daqui. O servidor do Veritas nunca a guarda."
    : "Sua chave fica só nesta aba e some ao fechá-la. O servidor do Veritas só a usa durante cada verificação e nunca a guarda.";
}

function clearAi() {
  state.ai = null;
  $("apiKey").value = "";
  $("rememberKey").checked = false;
  remember();
  updatePrivacyText();
  $("aiStatus").hidden = true;
  setAiStatus();
  toast("Modo grátis sem IA.");
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

async function readImage(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const preview = $("imagePreview");
  const url = URL.createObjectURL(file);
  $("imageThumb").src = url;
  preview.hidden = false;
  preview.classList.remove("done");
  $("ocrTitle").textContent = "Lendo o texto da imagem…";
  $("ocrHint").textContent = "Na primeira vez pode levar alguns segundos.";
  $("ocrBar").style.width = "5%";
  const country = document.querySelector('input[name="country"]:checked').value;
  try {
    const Tesseract = await loadTesseract();
    const result = await Tesseract.recognize(file, country === "FR" ? "fra" : "por", {
      logger: (m) => {
        if (m.status === "recognizing text") $("ocrBar").style.width = `${Math.round(10 + m.progress * 90)}%`;
      },
    });
    const text = result.data.text.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
    preview.classList.add("done");
    if (!text) {
      $("ocrTitle").textContent = "Não encontramos texto nesta imagem.";
      $("ocrHint").textContent = "Tente uma foto mais nítida ou digite o texto.";
      return;
    }
    const current = $("claim").value.trim();
    $("claim").value = (current ? `${current}\n\n${text}` : text).slice(0, 5000);
    updateCounter();
    $("ocrTitle").textContent = "Texto lido da imagem ✔";
    $("ocrHint").textContent = "Confira o texto acima e corrija se precisar.";
    $("claim").focus();
  } catch {
    preview.classList.add("done");
    $("ocrTitle").textContent = "Não foi possível ler a imagem.";
    $("ocrHint").textContent = "Verifique sua conexão ou digite o texto.";
  }
}

function setupImageInput() {
  $("imageInput").addEventListener("change", (event) => readImage(event.target.files[0]));
  $("removeImage").addEventListener("click", () => {
    $("imagePreview").hidden = true;
    $("imageInput").value = "";
  });
  $("claim").addEventListener("paste", (event) => {
    const item = [...(event.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) {
      event.preventDefault();
      readImage(item.getAsFile());
    }
  });
  const zone = $("dropZone");
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    const file = [...(event.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
    if (file) readImage(file);
  });
}

// ---------------------------------------------------------------- check
let radarTimer = null;
const LOADING_TEXTS = [
  "Consultando fontes oficiais…",
  "Cruzando dados do governo e de estatísticas…",
  "Buscando leis, estudos e arquivos…",
  "Organizando as evidências…",
];

function startLoading() {
  showState("loading");
  const items = [...document.querySelectorAll("#radarAreas li")];
  items.forEach((li) => li.classList.remove("lit"));
  let tick = 0;
  clearInterval(radarTimer);
  radarTimer = setInterval(() => {
    items.forEach((li, index) => li.classList.toggle("lit", (tick + index) % 3 === 0));
    $("loadingText").textContent = LOADING_TEXTS[Math.floor(tick / 3) % LOADING_TEXTS.length];
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
  if (claim.length < 5) {
    error.textContent = "Escreva ou cole a afirmação que você quer verificar.";
    error.hidden = false;
    $("claim").focus();
    return;
  }
  const body = { claim };
  const country = document.querySelector('input[name="country"]:checked').value;
  if (country) body.country = country;
  const sourceUrl = $("sourceUrl").value.trim();
  if (sourceUrl) {
    const normalized = safeUrl(/^https?:\/\//i.test(sourceUrl) ? sourceUrl : `https://${sourceUrl}`);
    if (!normalized) {
      error.textContent = "O link da fonte não parece válido.";
      error.hidden = false;
      return;
    }
    body.source_url = normalized;
  }
  state.lastBody = body;
  await run(body);
}

async function run(body) {
  const headers = { "Content-Type": "application/json" };
  if (state.ai) Object.assign(headers, aiHeaders(state.ai));
  const button = $("submitBtn");
  button.disabled = true;
  button.classList.add("busy");
  startLoading();
  if (window.matchMedia("(max-width: 960px)").matches) {
    $("resultPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(API, {
      method: "POST", headers, body: JSON.stringify(body), signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      const detail = data?.error?.message || (Array.isArray(data?.detail) ? "Texto inválido." : null);
      throw new Error(detail || `Erro ${response.status}`);
    }
    state.report = data;
    state.filter = null;
    renderReport(data);
  } catch (err) {
    stopLoading();
    $("errorText").textContent = err.name === "AbortError"
      ? "As fontes demoraram demais para responder. Tente de novo em instantes."
      : `Algo deu errado: ${err.message}`;
    showState("error");
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    button.classList.remove("busy");
  }
}

// ---------------------------------------------------------------- result
function renderReport(report) {
  stopLoading();
  const verdict = VERDICTS[report.verdict] || VERDICTS.INCONCLUSIVO;
  const card = $("verdictCard");
  card.dataset.tone = verdict.tone;
  $("verdictIcon").replaceChildren(icon(verdict.icon));
  $("verdictLabel").textContent = verdict.label;
  $("verdictMeaning").textContent = verdict.meaning;

  const gauge = $("gauge");
  gauge.hidden = !report.ai_used;
  if (report.ai_used) {
    const pct = Math.round((report.confidence_score || 0) * 100);
    $("gaugeNum").textContent = `${pct}%`;
    const value = $("gaugeValue");
    value.style.strokeDashoffset = "113.1";
    requestAnimationFrame(() => requestAnimationFrame(() => {
      value.style.strokeDashoffset = String(113.1 * (1 - pct / 100));
    }));
  }

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
        type: "button", class: "ref", text: match[1], "aria-label": `Ver fonte ${match[1]}`,
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
  return (CONNECTORS[source.connector] || ["gov", "pt"])[0];
}
function sourceLang(source) {
  return (CONNECTORS[source.connector] || ["gov", "pt"])[1];
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
    filter.append(makeButton(null, "Todas"), ...areas.map((a) => makeButton(a, AREAS[a].label)));
  }

  sources
    .filter((source) => !state.filter || sourceArea(source) === state.filter)
    .forEach((source, index) => list.append(sourceCard(source, index)));
}

function sourceCard(source, index) {
  const area = sourceArea(source);
  const lang = sourceLang(source);
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
      el("span", { class: "source-area", text: AREAS[area].label }),
      lang !== "pt" ? el("span", { class: "lang-tag", text: lang.toUpperCase() }) : null,
      source.cited ? el("span", { class: "cited", text: "Usada no veredito" }) : null),
    el("h4", { text: source.title }),
    el("p", { class: "publisher", text: source.publisher }),
    excerpt,
    longExcerpt ? el("button", {
      type: "button", class: "more", text: "Ler mais",
      onclick: (event) => {
        const clamped = excerpt.classList.toggle("clamped");
        event.target.textContent = clamped ? "Ler mais" : "Ler menos";
      },
    }) : null,
    el("div", { class: "meta" },
      tags,
      lang !== "pt" && (source.excerpt || source.title)
        ? el("button", {
          type: "button", class: "translate-btn",
          onclick: (event) => translateSource(event.currentTarget, source, lang),
        }, icon("translate"), `Traduzir do ${LANG_NAMES[lang] || lang}`)
        : null,
      link ? el("a", { class: "open-link", href: link, target: "_blank", rel: "noopener noreferrer" },
        "Abrir fonte oficial", icon("external")) : null),
  );
  return el("li", {
    class: "source", "data-evidence": source.evidence_id,
    style: `--c: var(${AREAS[area].color}); --i: ${index}`,
  }, areaIcon(area), body);
}

// ---------------------------------------------------------------- translation
async function translateText(text, from) {
  // On-device, free and private when the browser ships a translator (Chrome 138+).
  if ("Translator" in self) {
    const options = { sourceLanguage: from, targetLanguage: "pt" };
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
  button.lastChild.textContent = "Traduzindo…";
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
    ? el("div", { class: "translation" }, el("small", { text: "Tradução automática" }), translated)
    : el("div", { class: "translation" },
      el("small", { text: "Tradução" }),
      "Seu navegador não traduz sozinho. ",
      el("a", {
        href: `https://translate.google.com/?sl=${lang}&tl=pt&op=translate&text=${encodeURIComponent(original.slice(0, 4500))}`,
        target: "_blank", rel: "noopener noreferrer", text: "Traduzir no Google Tradutor ↗",
      }));
  card.querySelector(".excerpt").after(box);
}

// ---------------------------------------------------------------- alerts & notes
const VAGUE_PREFIX = "A afirmação não diz onde";
const AI_FAILURE_PREFIXES = ["IA indisponível", "Configuração de IA"];

function renderAlerts(report) {
  const box = $("alerts");
  box.replaceChildren();
  const notes = report.notes || [];
  const aiFailure = notes.find((n) => AI_FAILURE_PREFIXES.some((p) => n.startsWith(p)));
  if (aiFailure) {
    box.append(el("div", { class: "alert warn" }, icon("warning"),
      el("div", {},
        el("b", { text: "A IA não respondeu, então mostramos só os dados oficiais." }),
        el("p", { text: friendlyAiError(aiFailure, state.ai?.provider) }),
        el("button", {
          type: "button", class: "link-btn", text: "Testar minha chave",
          onclick: () => { $("aiPanel").open = true; $("aiPanel").scrollIntoView({ behavior: "smooth", block: "center" }); },
        }))));
  }
  const vague = notes.find((n) => n.startsWith(VAGUE_PREFIX));
  if (vague) {
    box.append(el("div", { class: "alert tip" }, icon("bulb"),
      el("div", {}, el("b", { text: "Dica para uma verificação melhor" }), el("p", { text: vague }))));
  }
}

function renderNotes(report) {
  const hidden = [VAGUE_PREFIX, ...AI_FAILURE_PREFIXES];
  const notes = (report.notes || []).filter((n) => !hidden.some((p) => n.startsWith(p)));
  for (const failure of report.connector_failures || []) {
    const area = CONNECTORS[failure.connector]?.[0];
    notes.push(`A fonte ${area ? AREAS[area].label.toLowerCase() : failure.connector} (${failure.connector}) não respondeu a tempo.`);
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

function shareText() {
  const report = state.report;
  const verdict = VERDICTS[report.verdict] || VERDICTS.INCONCLUSIVO;
  const lines = [
    `${verdict.emoji} *${verdict.label}*`,
    `“${report.claim.slice(0, 280)}”`,
    "",
    report.ai_used ? stripRefs(report.explanation).slice(0, 600) : verdict.meaning,
    "",
    "*Fontes oficiais:*",
  ];
  for (const source of (report.primary_sources || []).slice(0, 4)) {
    const link = safeUrl(source.url);
    if (link) lines.push(`• ${source.title.slice(0, 90)}\n${link}`);
  }
  lines.push("", "Verificado com o Veritas · verifique antes de compartilhar");
  return lines.join("\n");
}

function shareWhatsApp() {
  window.open(`https://wa.me/?text=${encodeURIComponent(shareText())}`, "_blank", "noopener");
}

async function copySummary() {
  try {
    await navigator.clipboard.writeText(shareText());
    toast("Resumo copiado!");
  } catch {
    toast("Não foi possível copiar.");
  }
}

// Draws a 1080x1350 share card (portrait, ideal for WhatsApp/Instagram) with the verdict.
function drawShareCard() {
  const report = state.report;
  const verdict = VERDICTS[report.verdict] || VERDICTS.INCONCLUSIVO;
  const tones = {
    true: ["#12875a", "#e3f6ec"], false: ["#d33a3a", "#fdeaea"], warn: ["#c97800", "#fff3df"],
    neutral: ["#5f6b80", "#eef0f5"], info: ["#3b5bdb", "#e9eeff"],
  };
  const [tone, soft] = tones[verdict.tone];
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
  ctx.fillStyle = "#6a7488"; ctx.font = font(500, 26); ctx.fillText("Verifique antes de compartilhar", P + 230, P + 43);

  // verdict block
  let y = P + 110;
  ctx.fillStyle = soft; roundRect(ctx, P, y, W - 2 * P, 210, 32); ctx.fill();
  ctx.fillStyle = tone; ctx.font = font(800, 26); ctx.fillText("RESULTADO", P + 40, y + 62);
  ctx.font = font(800, 76); ctx.fillText(fit(ctx, verdict.label, W - 2 * P - 80), P + 40, y + 140);
  ctx.fillStyle = "#3c465c"; ctx.font = font(500, 28);
  ctx.fillText(fit(ctx, verdict.meaning, W - 2 * P - 80), P + 40, y + 185);

  // claim (quote bar grows with the number of lines)
  y += 270;
  ctx.fillStyle = "#3c465c"; ctx.font = `italic ${font(500, 34)}`;
  const claimTop = y;
  const claimBottom = wrap(ctx, `“${report.claim}”`, P + 32, y + 34, W - 2 * P - 40, 46, 3);
  ctx.fillStyle = "#e2e6ef"; ctx.fillRect(P, claimTop, 8, claimBottom - claimTop + 14);
  y = claimBottom + 80;

  // explanation (AI) or hint
  if (report.ai_used && report.explanation) {
    ctx.fillStyle = "#131a2e"; ctx.font = font(500, 30);
    y = wrap(ctx, stripRefs(report.explanation), P, y, W - 2 * P, 42, 5) + 76;
  }

  // sources
  ctx.fillStyle = "#6a7488"; ctx.font = font(800, 24); ctx.fillText("FONTES OFICIAIS", P, y); y += 26;
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
  const day = new Date().toLocaleDateString("pt-BR");
  ctx.fillText(`Verificado em ${day} · dados de fontes públicas oficiais`, P, H - P - 10);
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
  const canvas = drawShareCard();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) return toast("Não foi possível gerar a imagem.");
  const file = new File([blob], "veritas-verificacao.png", { type: "image/png" });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: "Veritas", text: "Verifique antes de compartilhar" });
      return;
    } catch {
      // user cancelled or share failed: fall back to download
    }
  }
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: "veritas-verificacao.png" });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast("Imagem salva!");
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
  $("aiPill").addEventListener("click", () => {
    $("aiPanel").open = true;
    $("aiPanel").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("openAi").addEventListener("click", () => {
    $("aiPanel").open = true;
    $("aiPanel").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("toggleKey").addEventListener("click", () => {
    const input = $("apiKey");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    $("toggleKey").textContent = show ? "Ocultar" : "Mostrar";
  });
  $("useAi").addEventListener("click", useAi);
  $("clearAi").addEventListener("click", clearAi);
  $("shareBtn").addEventListener("click", shareWhatsApp);
  $("copyBtn").addEventListener("click", copySummary);
  $("imageBtn").addEventListener("click", downloadImage);
  $("newBtn").addEventListener("click", () => {
    $("claim").value = "";
    $("sourceUrl").value = "";
    $("imagePreview").hidden = true;
    updateCounter();
    showState("empty");
    $("claim").focus();
  });
  $("retryBtn").addEventListener("click", () => state.lastBody && run(state.lastBody));
}

document.addEventListener("DOMContentLoaded", init);
