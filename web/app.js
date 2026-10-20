// Inkwell product page. Talks to the API in config.js; renders API data only as text (never as HTML).
import { API, authHeaders, currentUser, startAuth, toggleTheme } from "./auth.js";

const MAX_BYTES = 1000000; // Mirrors the API limit.
const COLOR = {
  "First Party Collection/Use": "#3b6fd8", "Third Party Sharing/Collection": "#d0453a",
  "User Choice/Control": "#8a4fd1", "Data Security": "#2f8f5b",
  "International and Specific Audiences": "#c97a1e", "User Access, Edit and Deletion": "#13919a",
  "Policy Change": "#a88a12", "Data Retention": "#c04b86", "Do Not Track": "#6b7280", "Other": "#9a948a",
};
const DESCRIBE = {
  "First Party Collection/Use": "What the company itself collects about you, and how it uses it.",
  "Third Party Sharing/Collection": "When your data is shared with, sold to, or collected by other companies.",
  "User Choice/Control": "Opt-outs, consent and settings you control.",
  "Data Security": "How your data is protected.",
  "International and Specific Audiences": "Rules for children, or for people in particular countries or regions.",
  "User Access, Edit and Deletion": "Whether you can see, correct or delete your data.",
  "Policy Change": "How you'll be told when the policy changes.",
  "Data Retention": "How long your data is kept.",
  "Do Not Track": "Whether browser Do-Not-Track signals are honored.",
  "Other": "Introductions, contact details and other general text.",
};
const PERSONA = {
  svm: "Word-pattern classifier. Instant, a solid baseline.",
  distilbert: "Compact transformer that reads context.",
  roberta: "Larger transformer, also trained on modern (C3PA) policies. The slowest.",
};
const FALLBACK_MODELS = [
  { id: "svm", label: "TF-IDF + SVM" }, { id: "distilbert", label: "DistilBERT" }, { id: "roberta", label: "RoBERTa (C3PA + OPP-115)" },
];
const PROVIDER = { "google.com": "Google", "github.com": "GitHub", "password": "Email and password" };
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

const state = { ctx: { enabled: false }, models: [], defaultModel: "svm", choice: "svm", results: {}, order: [], view: null,
  filter: null, selected: null, onlyDisagree: false, lampTimer: null };
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
const chip = (cat) => el("span", { class: "chip", style: `--c:${COLOR[cat] || "#888"}`, title: DESCRIBE[cat] || cat }, cat);
const sigmoid = (x) => 1 / (1 + Math.exp(-x));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const modelLabel = (id) => (state.models.find((m) => m.id === id) || FALLBACK_MODELS.find((m) => m.id === id) || { label: id }).label;
const paragraphs = (text) => text.split(/\n[ \t]*\n/).filter((p) => p.trim()).length; // Same rule as inkwell/stage1.segment.
const seconds = (ms) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);

function toLogin() { location.replace(`login.html?next=${encodeURIComponent(location.pathname)}`); }

async function api(path, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { ...(options.headers || {}), ...(await authHeaders(state.ctx)) };
    const response = await fetch(API + path, { ...options, headers, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401 && state.ctx.enabled) { toLogin(); throw new Error("Please sign in again."); }
    if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`);
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The server took too long to answer. If it was asleep, try again in a minute.");
    if (error instanceof TypeError) throw new Error("Can't reach the Inkwell server. It may be waking up; try again shortly.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- Account ---------- */

function renderUser(user) {
  const box = $("user");
  if (!state.ctx.enabled) {
    box.replaceChildren(el("span", { class: "guest", title: "Sign-in isn't configured on this server" }, "Open access"));
    return;
  }
  const name = user.displayName || (user.email || "").split("@")[0] || "Account";
  const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const avatar = el("span", { class: "avatar" }, user.photoURL ? el("img", { src: user.photoURL, alt: "", referrerpolicy: "no-referrer" }) : initials);
  const menu = el("div", { class: "menu", role: "menu", hidden: true },
    el("div", { class: "menu-head" }, el("strong", {}, name), el("span", {}, user.email || ""),
      el("small", {}, `Signed in with ${PROVIDER[user.providerData[0]?.providerId] || "your account"}`)),
    el("button", { type: "button", role: "menuitem", onclick: async () => { await state.ctx.fb.signOut(state.ctx.auth); toLogin(); } }, "Sign out"));
  const button = el("button", { type: "button", class: "user-btn", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; button.setAttribute("aria-expanded", String(!menu.hidden)); } },
    avatar, el("span", { class: "user-name" }, name));
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) { menu.hidden = true; button.setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.hidden = true; });
  box.replaceChildren(button, menu);
}

/* ---------- Server status and model picker ---------- */

function setLamp(kind, text) { $("lamp").dataset.state = kind; $("lamp-text").textContent = text; $("lamp").title = text; }

async function checkApi() {
  clearTimeout(state.lampTimer);
  try {
    const data = await api("/models", {}, 15000);
    state.models = data.models; state.defaultModel = data.default;
    const ready = state.models.filter((m) => m.status === "ready").length;
    const loading = state.models.some((m) => m.status === "loading");
    setLamp(ready === state.models.length ? "ok" : "partial",
      loading ? `Loading models · ${ready}/${state.models.length} ready` : `Online · ${ready}/${state.models.length} models ready`);
    if (loading) state.lampTimer = setTimeout(checkApi, 5000);
  } catch {
    state.models = [];
    setLamp("down", "Server asleep or unreachable · retrying");
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
  cards.push(modelCard("all", "Compare all models", "Run every ready model on the same text and see where they disagree.",
    ready.length >= 2 ? "ready" : "needs 2+", null));
  $("models").replaceChildren(...cards);
}

function modelCard(id, label, blurb, status, m) {
  const off = status !== "ready";
  const speed = m && m.cpu_ms_per_segment !== undefined
    ? (m.cpu_ms_per_segment < 1 ? "<1 ms per paragraph" : `~${Math.round(m.cpu_ms_per_segment)} ms per paragraph`) : null;
  return el("label", { class: `model${off ? " off" : ""}`, title: m && m.error ? m.error : null },
    el("input", { type: "radio", name: "model", value: id, disabled: off, checked: !off && state.choice === id, onchange: () => { state.choice = id; } }),
    el("span", { class: "model-top" }, el("span", { class: "model-name" }, label),
      status === "ready" ? null : el("span", { class: `badge ${status === "needs 2+" ? "muted" : status}` }, status)),
    el("span", { class: "model-blurb" }, blurb),
    speed ? el("span", { class: "model-meta" }, speed) : null,
    m && m.error ? el("p", { class: "model-why" }, m.error) : null);
}

/* ---------- Input ---------- */

function updateCounts() {
  const text = $("policy").value;
  const bytes = new TextEncoder().encode(text).length;
  const n = paragraphs(text);
  $("counts").replaceChildren(
    el("span", {}, `${text.length.toLocaleString()} characters`), el("span", {}, plural(n, "paragraph")),
    el("span", { class: bytes > MAX_BYTES ? "over" : null }, `${(bytes / 1000).toFixed(1)} KB of 1,000 KB`));
  const warn = n === 1 && text.length > 1500
    ? "This reads as one long paragraph, so Inkwell can only quote it back whole. Leave blank lines between paragraphs, or use “Fix line breaks”."
    : bytes > MAX_BYTES ? "That's over the 1 MB limit. Trim the policy before analyzing it." : "";
  $("warn").textContent = warn; $("warn").hidden = !warn;
}

function setStatus(text, kind = "") { $("status").textContent = text; $("status").className = `status ${kind}`; }

async function run() {
  const text = $("policy").value;
  if (!text.trim()) return setStatus("Paste a policy first, or load the sample.", "error");
  if (new TextEncoder().encode(text).length > MAX_BYTES) return setStatus("That's over the 1 MB limit.", "error");
  const keys = state.choice === "all" ? readyIds() : [state.choice].filter(Boolean);
  if (!keys.length) return setStatus("No model is ready yet. Wait for the status light to turn green.", "error");
  $("run").disabled = true;
  const results = {};
  try {
    for (const [i, key] of keys.entries()) {
      setStatus(`${modelLabel(key)} is reading ${plural(paragraphs(text), "paragraph")}${keys.length > 1 ? ` (${i + 1} of ${keys.length})` : ""}`, "busy");
      results[key] = await api("/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, model: key }),
      }, 300000);
    }
    setStatus("Done. Select a topic, question or paragraph to explore.");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    $("run").disabled = false;
  }
  const done = keys.filter((k) => results[k]);
  if (!done.length) return;
  Object.assign(state, { results, order: done, view: done[done.length - 1], filter: null, selected: null });
  renderResults();
  showTab("overview");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Results ---------- */

const current = () => state.results[state.view];
const categories = () => Object.keys(current().coverage);

function renderResults() {
  $("results").hidden = false;
  $("tab-btn-compare").hidden = state.order.length < 2;
  $("viewing").hidden = state.order.length < 2;
  $("viewing").replaceChildren(...state.order.map((key) => el("button", { type: "button", "aria-pressed": String(key === state.view),
    onclick: () => { state.view = key; state.selected = null; renderResults(); } }, modelLabel(key))));
  renderKpis(); renderOverview(); renderFaqs(); renderDoc(); renderCompare();
}

function renderKpis() {
  const d = current();
  const cats = categories();
  const silent = cats.filter((c) => !d.coverage[c].length);
  const kpi = (label, value, note, alert = false) => el("div", { class: `card kpi${alert ? " alert" : ""}` },
    el("div", { class: "kpi-label" }, label), el("div", { class: "kpi-value" }, value), note ? el("div", { class: "kpi-note", title: note }, note) : null);
  $("kpis").replaceChildren(
    kpi("Paragraphs read", String(d.segments.length), modelLabel(d.model)),
    kpi("Topics covered", el("span", {}, String(cats.length - silent.length), el("small", {}, ` / ${cats.length}`)), "Topics with at least one clause"),
    kpi("Not mentioned", String(silent.length), silent.length ? silent.join(", ") : "Every topic has a clause", silent.length > 0),
    kpi("Analysis time", seconds(d.elapsed_ms ?? 0), "On the server's CPU"));
}

function renderOverview() {
  const d = current();
  const cards = categories().map((cat) => {
    const n = d.coverage[cat].length;
    return el("button", { type: "button", class: `cov${n ? "" : " silent"}`, style: `--c:${COLOR[cat]}`,
      title: n ? `Show the ${plural(n, "clause")} about ${cat}` : `No paragraph was classified as ${cat}`,
      onclick: () => { state.filter = n ? cat : null; renderDoc(); showTab("doc"); } },
      el("span", { class: "cov-top" }, cat), el("span", { class: "cov-desc" }, DESCRIBE[cat] || ""),
      el("span", { class: "cov-foot" }, n ? [el("span", { class: "cov-count" }, String(n)), el("span", { class: "cov-unit" }, n === 1 ? "clause" : "clauses")]
        : el("span", { class: "missing" }, "Not mentioned")));
  });
  $("tab-overview").replaceChildren(el("div", { class: "coverage" }, cards),
    el("p", { class: "panel-note" }, "Select a topic to read its clauses in the document. “Not mentioned” can be a real gap in the policy, or a miss by the model."));
}

function quoteButton(segment, cat) {
  return el("button", { type: "button", class: "quote", style: `--c:${COLOR[cat]}`, title: "Show in the document", onclick: () => select(segment.id) }, segment.text);
}

function renderFaqs() {
  const d = current();
  const cards = Object.entries(d.faqs).map(([question, cat]) => {
    const ids = d.coverage[cat];
    return el("article", { class: "card faq" }, el("h3", {}, question),
      el("p", { class: "answered-by" }, "Answered by clauses about", chip(cat)),
      ids.length ? ids.map((id) => quoteButton(d.segments[id], cat))
        : el("p", { class: "nothing" }, "No matching clause found. The policy may not address this, or the model may have missed it."));
  });
  $("tab-faqs").replaceChildren(el("div", { class: "faqs" }, cards));
}

function renderDoc() {
  const d = current();
  const filters = [el("button", { type: "button", class: "chip plain", "aria-pressed": String(!state.filter),
    onclick: () => { state.filter = null; renderDoc(); } }, `All paragraphs · ${d.segments.length}`)];
  for (const cat of categories()) {
    const n = d.coverage[cat].length;
    if (n) filters.push(el("button", { type: "button", class: "chip", style: `--c:${COLOR[cat]}`, "aria-pressed": String(state.filter === cat),
      onclick: () => { state.filter = state.filter === cat ? null : cat; renderDoc(); } }, `${cat} · ${n}`));
  }
  const segs = d.segments.map((s) => el("article", {
    id: `seg-${s.id}`, tabindex: "0",
    class: ["seg", s.labels.length ? "" : "unlabeled", state.filter && !s.labels.includes(state.filter) ? "dim" : "", state.selected === s.id ? "selected" : ""].join(" "),
    style: `--c:${COLOR[s.labels[0]] || "transparent"}`,
    onclick: () => select(s.id, false), onkeydown: (e) => { if (e.key === "Enter") select(s.id, false); },
  }, el("div", { class: "seg-meta" }, el("span", { class: "seg-num" }, `¶${s.id + 1}`), s.labels.length ? s.labels.map(chip) : "No topic"),
     el("p", { class: "seg-text" }, s.text)));
  $("tab-doc").replaceChildren(el("div", { class: "filters" }, filters),
    el("div", { class: "doc-layout" }, el("div", { class: "doc" }, segs), renderDetails(d)));
}

function renderDetails(d) {
  const s = d.segments[state.selected];
  if (!s) return el("aside", { class: "card details" }, el("h3", {}, "Model confidence"),
    el("p", { class: "note" }, "Select a paragraph to see how close it came to each topic's cutoff."),
    el("p", { class: "note" }, "Paragraphs with a dashed edge matched no topic."));
  const enc = (d.score_type || "").startsWith("logit");
  const rows = s.scores ? categories().map((cat, i) => ({ cat, i, delta: s.scores[i] - d.thresholds[i] }))
    .sort((a, b) => b.delta - a.delta)
    .map(({ cat, i, delta }) => {
      const score = s.scores[i], cutoff = d.thresholds[i], hit = s.labels.includes(cat);
      const width = Math.min(Math.abs(delta) / 4, 1) * 50;
      return el("div", { class: `meter ${hit ? "hit" : "miss"}`, style: `--c:${COLOR[cat]}` },
        el("span", { class: "meter-name" }, el("span", {}, cat), hit ? el("span", {}, "Matched") : null),
        el("span", { class: "meter-track" }, el("span", { class: "meter-fill", style: `width:${width}%;${delta >= 0 ? "left" : "right"}:50%` })),
        el("span", { class: "meter-num" }, enc ? `score ${sigmoid(score).toFixed(2)} · cutoff ${sigmoid(cutoff).toFixed(2)}`
          : `margin ${score.toFixed(2)} · cutoff ${cutoff.toFixed(2)}`));
    }) : el("p", {}, "This server did not return scores.");
  return el("aside", { class: "card details" }, el("h3", {}, `Paragraph ${s.id + 1}`),
    el("div", { class: "seg-meta" }, s.labels.length ? s.labels.map(chip) : "No topic"),
    el("p", { class: "note" }, "The centre line is each topic's cutoff, tuned on validation data. Bars to the right passed it; bars to the left fell short.",
      enc ? " Scores are model outputs, not calibrated probabilities." : " SVM margins are distances from a decision boundary, not probabilities."),
    rows,
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
    const verdict = counts.every((n) => n > 0) ? "All found" : counts.every((n) => n === 0) ? "None found" : "Models disagree";
    return el("tr", { class: verdict === "Models disagree" ? "split" : null }, el("td", {}, chip(cat)),
      counts.map((n) => el("td", { class: `n${n ? "" : " zero"}` }, n ? String(n) : "–")), el("td", { class: "verdict" }, verdict));
  });
  const key = (labels) => [...labels].sort().join("|");
  const segRows = runs[0].segments.map((s, i) => {
    const sets = runs.map((r) => r.segments[i].labels);
    return { s, sets, agree: sets.every((l) => key(l) === key(sets[0])) };
  });
  const agreed = segRows.filter((r) => r.agree).length;
  const shown = segRows.filter((r) => !state.onlyDisagree || !r.agree);
  $("tab-compare").replaceChildren(
    el("div", { class: "compare-block" }, el("h3", {}, "Clauses found per topic"),
      el("p", {}, "How many paragraphs each model assigned to each topic."),
      el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Topic"), state.order.map((k) => el("th", {}, modelLabel(k))), el("th", {}, "Verdict"))),
        el("tbody", {}, catRows))),
    el("div", { class: "compare-block" }, el("h3", {}, "Paragraph by paragraph"),
      el("p", {}, `The models gave identical topics to ${agreed} of ${segRows.length} paragraphs (${Math.round(100 * agreed / Math.max(segRows.length, 1))}%).`,
        el("label", {}, el("input", { type: "checkbox", checked: state.onlyDisagree, onchange: (e) => { state.onlyDisagree = e.target.checked; renderCompare(); } }), " Show only disagreements")),
      el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "¶"), el("th", {}, "Paragraph"), state.order.map((k) => el("th", {}, modelLabel(k))))),
        el("tbody", {}, shown.map(({ s, sets, agree }) => el("tr", { class: agree ? null : "disagree" },
          el("td", {}, String(s.id + 1)),
          el("td", {}, el("span", { class: "excerpt", title: "Show in the document", onclick: () => select(s.id) },
            s.text.length > 160 ? `${s.text.slice(0, 160)}…` : s.text)),
          sets.map((labels) => el("td", {}, labels.length ? el("div", { class: "chips" }, labels.map(chip)) : "–"))))))));
}

function showTab(name) {
  for (const tab of document.querySelectorAll("[role=tab]")) {
    const on = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
  }
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
  const lines = ["# Inkwell evidence report", "",
    `Model: ${modelLabel(d.model)} (\`${d.run}\`) · ${plural(d.segments.length, "paragraph")} · ${new Date().toISOString().slice(0, 10)}`, "",
    "_Research tool, not legal advice. Quotes are exact paragraphs from the submitted policy. A topic marked not mentioned may be a model miss._", "",
    "## Topics not mentioned", "", ...(silent.length ? silent.map((c) => `- ${c}`) : ["None."]), "", "## Common questions", ""];
  for (const [question, cat] of Object.entries(d.faqs)) {
    lines.push(`### ${question}`, "");
    const ids = d.coverage[cat];
    if (!ids.length) lines.push(`_${d.empty_message}._`, "");
    for (const id of ids) lines.push(quote(d.segments[id].text), "");
  }
  lines.push("## Evidence by topic", "");
  for (const cat of categories()) {
    if (!d.coverage[cat].length) continue;
    lines.push(`### ${cat} (${d.coverage[cat].length})`, "");
    for (const id of d.coverage[cat]) lines.push(quote(d.segments[id].text), "");
  }
  return lines.join("\n");
}

/* ---------- Wiring ---------- */

function wire() {
  $("policy").addEventListener("input", updateCounts);
  $("policy").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
  $("run").addEventListener("click", run);
  $("theme").addEventListener("click", toggleTheme);
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
  const tabs = [...document.querySelectorAll("[role=tab]")];
  for (const tab of tabs) {
    tab.addEventListener("click", () => showTab(tab.dataset.tab));
    tab.addEventListener("keydown", (e) => {  // Arrow keys move between visible tabs.
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      const visible = tabs.filter((t) => !t.hidden);
      let i = visible.indexOf(tab);
      i = e.key === "Home" ? 0 : e.key === "End" ? visible.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + visible.length) % visible.length;
      showTab(visible[i].dataset.tab); visible[i].focus(); e.preventDefault();
    });
  }
  $("dl-json").addEventListener("click", () => download("inkwell-results.json", "application/json",
    JSON.stringify({ generated: new Date().toISOString(), results: state.results }, null, 2)));
  $("dl-md").addEventListener("click", () => download(`inkwell-report-${state.view}.md`, "text/markdown", markdownReport()));
}

async function connect() {
  try {
    state.ctx = await startAuth();
  } catch {
    document.body.dataset.auth = "ready";
    setLamp("down", "Server asleep or unreachable · retrying");
    state.lampTimer = setTimeout(connect, 10000);
    return;
  }
  const user = await currentUser(state.ctx);
  if (state.ctx.enabled && !user) return toLogin();
  renderUser(user);
  if (state.ctx.enabled) state.ctx.fb.onAuthStateChanged(state.ctx.auth, (u) => { if (!u) toLogin(); });
  document.body.dataset.auth = "ready";
  checkApi();
}

wire();
updateCounts();
renderModels();
connect();
