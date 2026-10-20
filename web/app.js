"use strict";
// Inkwell web client. Talks to the API in config.js; renders only API data, always as text (never HTML).

const API = (new URLSearchParams(location.search).get("api") ?? window.INKWELL_API ?? "").replace(/\/+$/, "");
const MAX_BYTES = 1000000; // Mirrors the API limit.
const COLOR = {
  "First Party Collection/Use": "#2b59c3", "Third Party Sharing/Collection": "#c2362b",
  "User Choice/Control": "#7a3fb0", "Data Security": "#2f6b3a",
  "International and Specific Audiences": "#b5651d", "User Access, Edit and Deletion": "#0f7c80",
  "Policy Change": "#8a6d00", "Data Retention": "#a2346f", "Do Not Track": "#3b3b3b", "Other": "#8b8578",
};
const PERSONA = {
  svm: "The quick clerk. Counts words, answers instantly.",
  distilbert: "The careful reader. A slimmed-down BERT that reads context.",
  roberta: "The fussy scholar. Slowest, but best on our test set.",
};
const FALLBACK_MODELS = [
  { id: "svm", label: "TF-IDF + SVM" }, { id: "distilbert", label: "DistilBERT" }, { id: "roberta", label: "RoBERTa-base" },
];
const SAMPLE = `Pigeonpost Privacy Policy (fictional sample)

We collect the name, email address and phone number you give us when you create an account, and we automatically collect your device type, IP address and approximate location when you use the app.

We use this information to deliver messages, personalize your feed and measure how the service is used.

We share your personal information with advertising partners and analytics providers, and we may disclose it to law enforcement when required by law.

You can opt out of personalized advertising at any time in Settings > Privacy, and you can unsubscribe from marketing emails using the link in each message.

You may access, correct or delete your account information from your profile page, or by emailing privacy@pigeonpost.example.

We retain your messages for as long as your account is active and delete them within 30 days after you close your account.

We protect your data with encryption in transit and at rest, and we restrict access to employees who need it to do their jobs.

Pigeonpost is not directed to children under 13, and we do not knowingly collect information from them. If you live in the European Economic Area, you have additional rights under the GDPR.

We may change this policy from time to time. If we make material changes we will notify you by email before they take effect.`;

const state = { models: [], defaultModel: "svm", choice: "svm", results: {}, order: [], view: null, filter: null, selected: null, onlyDisagree: false, lampTimer: null };
const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  return node;
}
const chip = (cat) => el("span", { class: "chip", style: `--c:${COLOR[cat] || "#555"}`, title: cat }, cat);
const sigmoid = (x) => 1 / (1 + Math.exp(-x));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const modelLabel = (id) => (state.models.find((m) => m.id === id) || FALLBACK_MODELS.find((m) => m.id === id) || { label: id }).label;
const paragraphs = (text) => text.split(/\n[ \t]*\n/).filter((p) => p.trim()).length; // Same rule as inkwell/stage1.segment.

async function api(path, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(API + path, { ...options, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`);
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The API took too long to answer. If it was asleep, try again in a minute.");
    if (error instanceof TypeError) throw new Error(`Can't reach the API at ${API || location.origin}. It may be waking up; try again shortly.`);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- API status lamp and model cards ---------- */

function setLamp(kind, text) { $("lamp").dataset.state = kind; $("lamp-text").textContent = text; }

async function checkApi() {
  clearTimeout(state.lampTimer);
  if (location.protocol === "file:" && !API) {
    return setLamp("down", "Opened as a file. Start the API and open http://127.0.0.1:7860 instead.");
  }
  try {
    const data = await api("/models", {}, 15000);
    state.models = data.models; state.defaultModel = data.default;
    const ready = state.models.filter((m) => m.status === "ready").length;
    const loading = state.models.some((m) => m.status === "loading");
    setLamp(ready === state.models.length ? "ok" : "partial",
      `API awake · ${ready}/${state.models.length} readers ready${loading ? " · loading the rest…" : ""}`);
    if (loading) state.lampTimer = setTimeout(checkApi, 5000);
  } catch {
    state.models = [];
    setLamp("down", "API asleep or unreachable. Free Spaces nap when idle; retrying every 10 s…");
    state.lampTimer = setTimeout(checkApi, 10000);
  }
  renderModels();
}

function readyIds() { return state.models.filter((m) => m.status === "ready").map((m) => m.id); }

function renderModels() {
  const list = state.models.length ? state.models : FALLBACK_MODELS.map((m) => ({ ...m, status: "offline" }));
  const ready = readyIds();
  if (state.choice === "all" ? ready.length < 2 : !ready.includes(state.choice)) state.choice = ready.includes(state.defaultModel) ? state.defaultModel : ready[0];
  const cards = list.map((m) => modelCard(m.id, m.label, PERSONA[m.id] || "", m.status, m));
  cards.push(modelCard("all", "All three", "Run every ready reader on the same text and see where they disagree.", ready.length >= 2 ? "ready" : "needs 2+", null));
  $("models").replaceChildren(...cards);
}

function modelCard(id, label, blurb, status, m) {
  const off = status !== "ready";
  const stats = m && m.test_macro_f1 !== undefined ? el("dl", {},
    el("dt", {}, "test macro-F1"), el("dd", {}, m.test_macro_f1.toFixed(3)),
    el("dt", {}, "test micro-F1"), el("dd", {}, m.test_micro_f1.toFixed(3)),
    el("dt", {}, "speed (CPU)"), el("dd", {}, m.cpu_ms_per_segment < 1 ? "<1 ms / paragraph" : `~${Math.round(m.cpu_ms_per_segment)} ms / paragraph`)) : null;
  return el("label", { class: `model${off ? " off" : ""}`, title: m && m.error ? m.error : null },
    el("input", { type: "radio", name: "model", value: id, disabled: off, checked: !off && state.choice === id, onchange: () => { state.choice = id; } }),
    el("span", { class: `badge ${status}` }, status),
    el("span", { class: "model-name" }, label),
    el("p", { class: "blurb" }, blurb), stats,
    m && m.error ? el("p", { class: "why" }, m.error) : null);
}

/* ---------- Step 1: input ---------- */

function updateCounts() {
  const text = $("policy").value;
  const bytes = new TextEncoder().encode(text).length;
  const n = paragraphs(text);
  const size = el("span", { class: bytes > MAX_BYTES ? "over" : null }, `${(bytes / 1000).toFixed(1)} KB of 1,000 KB`);
  $("counts").replaceChildren(`${text.length.toLocaleString()} characters · ${plural(n, "paragraph")} · `, size);
  const warn = n === 1 && text.length > 1500
    ? "This reads as one giant paragraph, so Inkwell can only quote it back whole. Leave blank lines between paragraphs, or try “Split single line breaks”."
    : bytes > MAX_BYTES ? "That's over the 1 MB limit. Trim the policy before reading it." : "";
  $("warn").textContent = warn; $("warn").hidden = !warn;
}

function setStatus(text, kind = "") { $("status").textContent = text; $("status").className = `status ${kind}`; }

/* ---------- Step 2: run ---------- */

async function run() {
  const text = $("policy").value;
  if (!text.trim()) return setStatus("Paste a policy first (or load the sample).", "error");
  if (new TextEncoder().encode(text).length > MAX_BYTES) return setStatus("That's over the 1 MB limit.", "error");
  const keys = state.choice === "all" ? readyIds() : [state.choice].filter(Boolean);
  if (!keys.length) return setStatus("No reader is ready yet. Wait for the lamp to turn green.", "error");
  $("run").disabled = true;
  const results = {};
  try {
    for (const [i, key] of keys.entries()) {
      setStatus(`${modelLabel(key)} is reading ${plural(paragraphs(text), "paragraph")}${keys.length > 1 ? ` (${i + 1}/${keys.length})` : ""}`, "busy");
      results[key] = await api("/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, model: key }),
      }, 300000);
    }
    setStatus("Done. Click any stamp, question or paragraph to dig in.");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    $("run").disabled = false;
  }
  const done = keys.filter((k) => results[k]);
  if (!done.length) return;
  Object.assign(state, { results, order: done, view: done[done.length - 1], filter: null, selected: null });
  renderResults();
  showTab("stamps");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Step 3: results ---------- */

const current = () => state.results[state.view];
const categories = () => Object.keys(current().coverage);

function renderResults() {
  $("results").hidden = false;
  document.querySelector('[data-tab="compare"]').hidden = state.order.length < 2;
  $("viewing").replaceChildren(...(state.order.length < 2 ? [] : [el("span", {}, "Viewing:"),
    ...state.order.map((key) => el("button", { type: "button", "aria-pressed": String(key === state.view),
      onclick: () => { state.view = key; state.selected = null; renderResults(); } }, modelLabel(key)))]));
  renderSummary(); renderStamps(); renderFaqs(); renderDoc(); renderCompare();
}

function renderSummary() {
  const d = current();
  const silent = categories().filter((c) => !d.coverage[c].length);
  $("summary").replaceChildren(
    `${modelLabel(d.model)} read ${plural(d.segments.length, "paragraph")} in ${d.elapsed_ms ?? "?"} ms and found evidence for ${categories().length - silent.length} of ${categories().length} categories. `,
    silent.length ? el("span", { class: "silent-list" }, `Silent on: ${silent.join(", ")}.`) : "No category is silent.");
}

function renderStamps() {
  const d = current();
  const stamps = categories().map((cat) => {
    const n = d.coverage[cat].length;
    return el("button", { type: "button", class: `stamp ${n ? "found" : "silent"}`, style: `--c:${COLOR[cat]}`,
      title: n ? `Show the ${plural(n, "paragraph")} classified as ${cat}` : `No paragraph was classified as ${cat}`,
      onclick: () => { state.filter = n ? cat : null; renderDoc(); showTab("doc"); } },
      el("span", { class: "stamp-count" }, n || "∅"), el("span", { class: "stamp-name" }, cat),
      el("span", { class: "stamp-ink" }, n ? plural(n, "clause") : "SILENT"));
  });
  $("tab-stamps").replaceChildren(el("div", { class: "stamps" }, stamps),
    el("p", { class: "legend" }, "Click a stamp to see its clauses in the annotated policy. SILENT means no paragraph was classified into that category. That may be a real gap in the policy, or a miss by the model."));
}

function quoteButton(segment, cat) {
  return el("button", { type: "button", class: "quote", style: `--c:${COLOR[cat]}`, title: "Show in the annotated policy",
    onclick: () => select(segment.id) }, segment.text);
}

function renderFaqs() {
  const d = current();
  const cards = Object.entries(d.faqs).map(([question, cat]) => {
    const ids = d.coverage[cat];
    return el("article", { class: "faq" }, el("h3", {}, question),
      el("p", { class: "answered-by" }, "answered by clauses tagged ", chip(cat)),
      ids.length ? ids.map((id) => quoteButton(d.segments[id], cat))
        : el("p", { class: "nothing" }, `${d.empty_message}. The policy may not address this, or the model may have missed it.`));
  });
  $("tab-faqs").replaceChildren(el("div", { class: "faqs" }, cards));
}

function renderDoc() {
  const d = current();
  const filters = [el("button", { type: "button", class: "chip", "aria-pressed": String(!state.filter),
    onclick: () => { state.filter = null; renderDoc(); } }, `all ${d.segments.length}`)];
  for (const cat of categories()) {
    const n = d.coverage[cat].length;
    if (n) filters.push(el("button", { type: "button", class: "chip", style: `--c:${COLOR[cat]}`, "aria-pressed": String(state.filter === cat),
      onclick: () => { state.filter = state.filter === cat ? null : cat; renderDoc(); } }, `${cat} · ${n}`));
  }
  const segs = d.segments.map((s) => el("article", {
    id: `seg-${s.id}`, tabindex: "0",
    class: ["seg", s.labels.length ? "" : "unlabeled", state.filter && !s.labels.includes(state.filter) ? "dim" : "", state.selected === s.id ? "selected" : ""].join(" "),
    style: `--c:${COLOR[s.labels[0]] || "#9a9384"}`,
    onclick: () => select(s.id, false), onkeydown: (e) => { if (e.key === "Enter") select(s.id, false); },
  }, el("div", { class: "seg-meta" }, `¶${s.id + 1}`, s.labels.length ? s.labels.map(chip) : "no category"),
     el("p", { class: "seg-text" }, s.text)));
  $("tab-doc").replaceChildren(el("div", { class: "filters" }, filters),
    el("div", { class: "doc-layout" }, el("div", { class: "doc" }, segs), renderDetails(d)));
}

function renderDetails(d) {
  const s = d.segments[state.selected];
  if (!s) return el("aside", { class: "details" }, el("h3", {}, "How sure was it?"),
    el("p", {}, "Click a paragraph to see how close it came to each category's cutoff."),
    el("p", { class: "note" }, "Paragraphs with a dashed edge matched no category."));
  const enc = (d.score_type || "").startsWith("logit");
  const rows = categories().map((cat, i) => ({ cat, i, delta: s.scores ? s.scores[i] - d.thresholds[i] : 0 }))
    .sort((a, b) => b.delta - a.delta)
    .map(({ cat, i, delta }) => {
      if (!s.scores) return null;
      const score = s.scores[i], cutoff = d.thresholds[i], hit = s.labels.includes(cat);
      const width = Math.min(Math.abs(delta) / 4, 1) * 50;
      return el("div", { class: `meter ${hit ? "hit" : "miss"}`, style: `--c:${COLOR[cat]}` },
        el("span", { class: "meter-name" }, `${hit ? "✔ " : ""}${cat}`),
        el("span", { class: "meter-track" }, el("span", { class: "meter-fill", style: `width:${width}%;${delta >= 0 ? "left" : "right"}:50%` })),
        el("span", { class: "meter-num" }, enc ? `probability ${sigmoid(score).toFixed(2)} · cutoff ${sigmoid(cutoff).toFixed(2)}`
          : `margin ${score.toFixed(2)} · cutoff ${cutoff.toFixed(2)}`));
    });
  return el("aside", { class: "details" }, el("h3", {}, `¶${s.id + 1}`),
    el("div", { class: "seg-meta" }, s.labels.length ? s.labels.map(chip) : "no category"),
    el("p", { class: "note" }, "Centre line = the category's cutoff, tuned on validation data. Bars to the right passed it; bars to the left fell short.",
      enc ? "" : " SVM margins are distances from a decision boundary, not probabilities."),
    s.scores ? rows : el("p", {}, "This API did not return scores."),
    el("p", { class: "note" }, `Characters ${s.start}–${s.end} of the text you pasted.`));
}

function select(id, scroll = true) {
  state.selected = id;
  renderDoc(); showTab("doc");
  const node = $(`seg-${id}`);
  if (!node) return;
  if (scroll) node.scrollIntoView({ behavior: "smooth", block: "center" });
  node.classList.add("flash"); node.focus({ preventScroll: true });
}

function renderCompare() {
  if (state.order.length < 2) return $("tab-compare").replaceChildren();
  const runs = state.order.map((k) => state.results[k]);
  const cats = Object.keys(runs[0].coverage);
  const catRows = cats.map((cat) => {
    const counts = runs.map((r) => r.coverage[cat].length);
    const verdict = counts.every((n) => n > 0) ? "all found" : counts.every((n) => n === 0) ? "all silent" : "split";
    return el("tr", { class: verdict === "split" ? "split" : null }, el("td", {}, chip(cat)),
      counts.map((n) => el("td", { class: `n${n ? "" : " zero"}` }, n || "SILENT")), el("td", {}, verdict));
  });
  const key = (labels) => [...labels].sort().join("|");
  const segRows = runs[0].segments.map((s, i) => {
    const sets = runs.map((r) => r.segments[i].labels);
    return { s, sets, agree: sets.every((l) => key(l) === key(sets[0])) };
  });
  const agreed = segRows.filter((r) => r.agree).length;
  const shown = segRows.filter((r) => !state.onlyDisagree || !r.agree);
  $("tab-compare").replaceChildren(
    el("div", { class: "compare-block" }, el("h3", {}, "Clauses found per category"),
      el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Category"), state.order.map((k) => el("th", {}, modelLabel(k))), el("th", {}, "Verdict"))),
        el("tbody", {}, catRows))),
    el("div", { class: "compare-block" }, el("h3", {}, "Paragraph by paragraph"),
      el("p", {}, `The readers gave identical labels to ${agreed} of ${segRows.length} paragraphs (${Math.round(100 * agreed / Math.max(segRows.length, 1))}%). `,
        el("label", {}, el("input", { type: "checkbox", checked: state.onlyDisagree, onchange: (e) => { state.onlyDisagree = e.target.checked; renderCompare(); } }), " show only disagreements")),
      el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "¶"), el("th", {}, "Paragraph"), state.order.map((k) => el("th", {}, modelLabel(k))))),
        el("tbody", {}, shown.map(({ s, sets, agree }) => el("tr", { class: agree ? null : "disagree" },
          el("td", {}, s.id + 1),
          el("td", {}, el("span", { class: "excerpt", title: "Show in the annotated policy", onclick: () => select(s.id) },
            s.text.length > 160 ? `${s.text.slice(0, 160)}…` : s.text)),
          sets.map((labels) => el("td", {}, labels.length ? labels.map(chip) : "—"))))))));
}

function showTab(name) {
  for (const tab of document.querySelectorAll("[role=tab]")) tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  for (const panel of document.querySelectorAll(".panel")) panel.hidden = panel.id !== `tab-${name}`;
}

/* ---------- Exports ---------- */

function download(name, type, content) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  el("a", { href: url, download: name }).click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function markdownReport() {
  const d = current();
  const quote = (text) => `> ${text.replace(/\n/g, "\n> ")}`;
  const silent = categories().filter((c) => !d.coverage[c].length);
  const lines = [`# Inkwell evidence report`, ``,
    `Reader: ${modelLabel(d.model)} (\`${d.run}\`) · ${plural(d.segments.length, "paragraph")} · ${new Date().toISOString().slice(0, 10)}`, ``,
    `_Research baseline, not legal advice. Quotes are exact paragraphs from the submitted policy. A silent category may be a model miss._`, ``,
    `## Silent categories`, ``, ...(silent.length ? silent.map((c) => `- ${c}`) : ["None."]), ``, `## Common questions`, ``];
  for (const [question, cat] of Object.entries(d.faqs)) {
    lines.push(`### ${question}`, ``);
    const ids = d.coverage[cat];
    if (!ids.length) lines.push(`_${d.empty_message}._`, ``);
    for (const id of ids) lines.push(quote(d.segments[id].text), ``);
  }
  lines.push(`## Evidence by category`, ``);
  for (const cat of categories()) {
    if (!d.coverage[cat].length) continue;
    lines.push(`### ${cat} (${d.coverage[cat].length})`, ``);
    for (const id of d.coverage[cat]) lines.push(quote(d.segments[id].text), ``);
  }
  return lines.join("\n");
}

/* ---------- Wiring ---------- */

$("policy").addEventListener("input", updateCounts);
$("policy").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
$("run").addEventListener("click", run);
$("sample").addEventListener("click", () => { $("policy").value = SAMPLE; updateCounts(); });
$("clear").addEventListener("click", () => { $("policy").value = ""; updateCounts(); $("policy").focus(); });
$("split").addEventListener("click", () => {
  $("policy").value = $("policy").value.replace(/\r\n?/g, "\n").replace(/([^\n])\n(?=[^\n])/g, "$1\n\n");
  updateCounts();
});
$("file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  if (file.size > MAX_BYTES) setStatus("That file is over the 1 MB limit.", "error");
  else { $("policy").value = await file.text(); updateCounts(); setStatus(`Loaded ${file.name}.`); }
  e.target.value = "";
});
for (const tab of document.querySelectorAll("[role=tab]")) tab.addEventListener("click", () => showTab(tab.dataset.tab));
$("dl-json").addEventListener("click", () => download("inkwell-results.json", "application/json",
  JSON.stringify({ generated: new Date().toISOString(), api: API, results: state.results }, null, 2)));
$("dl-md").addEventListener("click", () => download(`inkwell-report-${state.view}.md`, "text/markdown", markdownReport()));

updateCounts();
renderModels();
checkApi();
