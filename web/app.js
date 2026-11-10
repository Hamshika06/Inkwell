// Inkwell product page. Talks to the API in config.js; renders API data only as text (never as HTML).
import { API, authHeaders, currentUser, isVerified, startAuth, toggleTheme } from "./auth.js";
import { afterAnalysis, initDecide, loadPriorities, loadSaved, renderDecision, renderSteps } from "./decide.js";
import { openStore } from "./store.js";

// Mirror the API limits: 1 MB (300 KB for a free check) and at most 200 paragraphs per check.
const MAX_BYTES = 1000000, GUEST_MAX_BYTES = 300000, MAX_PARAGRAPHS = 200;
const maxBytes = () => (state.guest ? GUEST_MAX_BYTES : MAX_BYTES);
// The five topics of the Inkwell model (configs/five_class_mapping.json).
const COLOR = {
  "Data Collection & Use": "#3b6fd8", "Data Sharing": "#d0453a", "User Rights & Choices": "#13919a",
  "Data Security & Retention": "#2f8f5b", "Policy Scope & Changes": "#a88a12",
};
const DESCRIBE = {
  "Data Collection & Use": "What they collect about you, and what they use it for.",
  "Data Sharing": "Who else gets your data: partners, advertisers, buyers, or the authorities.",
  "User Rights & Choices": "What you can do: opt out, access, correct or delete your data, and Do Not Track.",
  "Data Security & Retention": "How your data is protected, and how long they keep it.",
  "Policy Scope & Changes": "Who the policy covers (children, regions) and how you're told when it changes.",
};
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

const state = { ctx: { enabled: false }, guest: false, user: null, store: null, model: null, result: null,
  filter: null, selected: null, lampTimer: null, expanded: {},
  // Decision layer (decide.js): the reader's priorities, choice, ticked steps and saved policies.
  priorities: null, decision: null, done: {}, saved: {}, current: null, changes: null };
// Free checks (no account) show this many report-card checks with their quotes; the rest are previews.
const FREE_RECEIPTS = 2;
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
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const paragraphs = (text) => text.split(/\n[ \t]*\n/).filter((p) => p.trim()).length; // Same rule as inkwell/stage1.segment.
const kb = (bytes) => `${Math.round(bytes / 1000).toLocaleString()} KB`;

function toLogin() { location.replace(`login.html?next=${encodeURIComponent(location.pathname)}`); }
const signupUrl = () => `login.html?mode=signup&next=${encodeURIComponent(location.pathname)}`;

async function api(path, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { ...(options.headers || {}), ...(await authHeaders(state.ctx)) };
    const response = await fetch(API + path, { ...options, headers, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401 && state.ctx.enabled && state.guest) throw new Error(body.detail || "Create a free account to do that.");
    if (response.status === 401 && state.ctx.enabled) { toLogin(); throw new Error("Please sign in again."); }
    if (response.status === 403 && state.ctx.enabled) { toLogin(); throw new Error(body.detail); }  // Email not confirmed.
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
  if (!user) {
    box.replaceChildren(el("div", { class: "guest-actions" },
      el("a", { class: "btn btn-ghost", href: `login.html?next=${encodeURIComponent(location.pathname)}` }, "Sign in"),
      el("a", { class: "btn btn-primary", href: signupUrl() }, "Sign up free")));
    return;
  }
  const name = user.displayName || (user.email || "").split("@")[0] || "Account";
  const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const avatar = el("span", { class: "avatar" }, user.photoURL ? el("img", { src: user.photoURL, alt: "", referrerpolicy: "no-referrer" }) : initials);
  const menu = el("div", { class: "menu", role: "menu", hidden: true },
    el("div", { class: "menu-head" }, el("strong", {}, name), el("span", {}, user.email || ""),
      el("small", {}, `Signed in with ${PROVIDER[user.providerData[0]?.providerId] || "your account"}`)),
    el("button", { type: "button", role: "menuitem", onclick: async () => { await state.ctx.fb.signOut(state.ctx.auth); location.replace("/"); } }, "Sign out"));
  const button = el("button", { type: "button", class: "user-btn", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; button.setAttribute("aria-expanded", String(!menu.hidden)); } },
    avatar, el("span", { class: "user-name" }, name));
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) { menu.hidden = true; button.setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.hidden = true; });
  box.replaceChildren(button, menu);
}

/* ---------- Server status ---------- */

function setLamp(kind, text) { $("lamp").dataset.state = kind; $("lamp-text").textContent = text; $("lamp").title = text; }

async function checkApi() {
  clearTimeout(state.lampTimer);
  try {
    const data = await api("/models", {}, 15000);
    state.model = data.models.find((m) => m.id === data.default) || data.models[0] || null;
    const status = state.model?.status;
    setLamp(status === "ready" ? "ok" : status === "loading" ? "partial" : "down",
      status === "ready" ? "Ready" : status === "loading" ? "Warming up…" : "Unavailable");
    if (status === "loading") state.lampTimer = setTimeout(checkApi, 5000);
  } catch {
    state.model = null;
    setLamp("down", "Waking up the server…");
    state.lampTimer = setTimeout(checkApi, 10000);
  }
  renderModelMeta();
  if (state.autoRun && ready()) { state.autoRun = false; run(); }
}

const ready = () => state.model?.status === "ready";

function renderModelMeta() {
  const m = state.model;
  $("model-meta").textContent = !m ? ""
    : m.status === "unavailable" ? `The model couldn't load on this server: ${m.error || "unknown error"}`
    : m.test_macro_f1 ? `Macro-F1 ${m.test_macro_f1.toFixed(2)} on held-out test paragraphs.` : "";
}

/* ---------- Input ---------- */

function updateCounts() {
  const text = $("policy").value;
  const bytes = new TextEncoder().encode(text).length;
  const n = paragraphs(text);
  $("counts").replaceChildren(
    el("span", {}, `${text.length.toLocaleString()} characters`), el("span", {}, plural(n, "paragraph")),
    el("span", { class: bytes > maxBytes() || n > MAX_PARAGRAPHS ? "over" : null }, `${(bytes / 1000).toFixed(1)} KB of ${kb(maxBytes())}`));
  const warn = n === 1 && text.length > 1500
    ? "This reads as one long paragraph, so Inkwell can only quote it back whole. Leave blank lines between paragraphs, or use “Fix line breaks”."
    : bytes > maxBytes() ? `That's over the ${kb(maxBytes())} limit${state.guest ? " for a free check. Create a free account for up to 1,000 KB, or trim the policy" : ". Trim the policy before checking it"}.`
    : n > MAX_PARAGRAPHS ? `Inkwell reads up to ${MAX_PARAGRAPHS} paragraphs at a time. Split the policy in two and check each half.` : "";
  $("warn").textContent = warn; $("warn").hidden = !warn;
}

function setStatus(text, kind = "") { $("status").textContent = text; $("status").className = `status ${kind}`; }

async function run() {
  const text = $("policy").value;
  if (!text.trim()) return setStatus("Paste a policy first, or load the sample.", "error");
  if (new TextEncoder().encode(text).length > maxBytes()) return setStatus(`That's over the ${kb(maxBytes())} limit.`, "error");
  const n = paragraphs(text);
  if (n > MAX_PARAGRAPHS) return setStatus(`That's ${n} paragraphs; Inkwell reads up to ${MAX_PARAGRAPHS} at a time.`, "error");
  if (!ready()) return setStatus("Inkwell is still warming up. Try again when the status light turns green.", "error");
  $("run").disabled = true;
  let result = null;
  try {
    setStatus(`Reading ${plural(n, "paragraph")}…${n > 40 ? " Long policies take up to a minute." : ""}`, "busy");
    result = await api("/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    }, 300000);
    setStatus("Done. Your report card is below.");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    $("run").disabled = false;
  }
  if (!result) return;
  Object.assign(state, { result, filter: null, selected: null, expanded: {}, animated: false, saving: false });
  showBreakdown(false);
  renderResults();
  await afterAnalysis(text);
  showTab("overview");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Results ---------- */

const current = () => state.result;
const categories = () => Object.keys(current().coverage);

function renderResults() {
  $("results").hidden = false;
  for (const id of ["dl-md", "dl-json"]) $(id).hidden = state.guest;
  renderReport(); renderKpis(); renderOverview(); renderFaqs(); renderDoc();
}

function showBreakdown(open) {
  $("breakdown").hidden = !open;
  $("toggle-breakdown").setAttribute("aria-expanded", String(open));
  $("toggle-breakdown").textContent = open ? "Hide full breakdown" : "Show full breakdown";
}

/* ---------- Report card ---------- */

// Neutral marks: whether the practice applies, not whether it's good or bad. The reader's priorities add emphasis.
const MARK = { true: { icon: "●", word: "Applies" }, false: { icon: "○", word: "Doesn't apply" }, null: { icon: "?", word: "Not settled by the text" } };

function lockCta(text, button = "Sign up free") {
  return el("div", { class: "lock-cta" }, el("span", { class: "lock-icon", "aria-hidden": "true" }, "🔒"),
    el("p", {}, text), el("a", { class: "btn btn-primary", href: signupUrl() }, button));
}

function receipt(evidence) {
  return el("button", { type: "button", class: "receipt", title: "Show this sentence in the full policy",
    onclick: () => select(evidence.segment_id) },
    el("span", { class: "receipt-mark", "aria-hidden": "true" }, "“"), evidence.text);
}

function renderCheck(check, i, free, concern) {
  const locked = state.guest && !free.has(check.id);
  const mine = state.priorities?.includes(check.id);
  let proof = null;
  if (check.evidence.length && locked) {
    proof = el("div", { class: "receipt-locked" },
      el("p", { class: "blurred", "aria-hidden": "true" }, check.evidence[0].text),
      el("a", { class: "unlock-link", href: signupUrl() }, "🔒 Sign up free to read the sentence that proves it"));
  } else if (check.evidence.length) {
    const more = check.evidence_count - 1;
    proof = [receipt(check.evidence[0]),
      more > 0 ? el("details", { class: "more-receipts" },
        el("summary", {}, `${more} more ${more === 1 ? "sentence" : "sentences"} like this`),
        check.evidence.slice(1).map(receipt),
        more > check.evidence.length - 1 ? el("p", { class: "note" }, "Open the full breakdown to read the rest.") : null) : null,
      check.counter.length ? el("div", { class: "counter" }, el("span", {}, "But the policy also says:"), receipt(check.counter[0])) : null];
  }
  const mark = MARK[check.applies ?? null];
  return el("li", { class: `check applies-${check.applies ?? "unknown"}${mine ? " mine" : ""}`, id: `check-${check.id}`, style: `--i:${i}` },
    el("span", { class: "check-icon", role: "img", "aria-label": mark.word, title: mark.word }, mark.icon),
    el("div", { class: "check-body" },
      el("div", { class: "check-top" }, el("h3", {}, check.title), el("span", { class: "verdict-pill" }, check.label),
        mine ? el("span", { class: "tag mine-tag" }, "Matters to you") : null,
        concern ? el("span", { class: `tag ${concern.fixable ? "fix-tag" : "stay-tag"}` }, concern.fixable ? "You can switch this off" : "Comes with the service") : null),
      el("p", { class: "check-meaning" }, check.meaning),
      concern?.note ? el("p", { class: "fine" }, concern.note) : null,
      proof));
}

function renderReport() {
  const r = current().report;
  if (!r) return $("report").replaceChildren();
  // Free checks show the quotes for the first checks that have one.
  const free = new Set(r.checks.filter((c) => c.evidence.length).slice(0, FREE_RECEIPTS).map((c) => c.id));
  const concerns = Object.fromEntries((r.concerns || []).map((c) => [c.id, c]));
  // Mine first, in the order the reader sees them in the decision bar; then the rest.
  const mine = state.priorities || [];
  const ordered = [...r.checks].sort((a, b) => Number(mine.includes(b.id)) - Number(mine.includes(a.id)));
  $("report").replaceChildren(el("article", { class: `card report-card${state.animated ? " static" : ""}`, "aria-label": "Privacy report card" },
    el("header", { class: "rc-head" },
      el("div", {}, el("p", { class: "eyebrow" }, "Privacy report card"), el("h2", {}, r.title || "This privacy policy"))),
    renderDecision(),
    el("h3", { class: "checks-title" }, "What the policy says"),
    el("ul", { class: "checks" }, ordered.map((c, i) => renderCheck(c, i, free, concerns[c.id]))),
    state.guest ? lockCta(`You're seeing ${FREE_RECEIPTS} of ${r.checks.length} receipts. Create a free account to read every sentence behind these answers.`,
      "Unlock the full report") : null,
    renderSteps(),
    el("p", { class: "rc-note" }, r.limitation)));
  state.animated = true;
}

/* ---------- Breakdown ---------- */

function renderKpis() {
  const d = current();
  const cats = categories();
  const silent = cats.filter((c) => !d.coverage[c].length);
  const unlabeled = d.segments.filter((s) => !s.labels.length).length;
  const kpi = (label, value, note, alert = false) => el("div", { class: `card kpi${alert ? " alert" : ""}` },
    el("div", { class: "kpi-label" }, label), el("div", { class: "kpi-value" }, value), note ? el("div", { class: "kpi-note", title: note }, note) : null);
  $("kpis").replaceChildren(
    kpi("Paragraphs read", String(d.segments.length), "Each sorted into the 5 topics"),
    kpi("Topics covered", el("span", {}, String(cats.length - silent.length), el("small", {}, ` / ${cats.length}`)), "Topics with at least one clause"),
    kpi("Not mentioned", String(silent.length), silent.length ? silent.join(", ") : "Every topic has a clause", silent.length > 0),
    kpi("No topic found", String(unlabeled), "Paragraphs the model couldn't place"));
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
    el("p", { class: "panel-note" }, "Select a topic to read its clauses in the document. A paragraph can belong to more than one topic. “Not mentioned” can be a real gap in the policy, or a miss by the model."));
}

function quoteButton(segment, cat) {
  return el("button", { type: "button", class: "quote", style: `--c:${COLOR[cat]}`, title: "Show in the document", onclick: () => select(segment.id) }, segment.text);
}

// Each common question takes its one-line answer from a report-card check.
const FAQ_CHECK = {
  "Do they share or sell my data?": "sharing", "Can I delete my data or opt out?": "delete",
  "How long do they keep it, and how is it protected?": "retention", "Will they tell me when the policy changes?": "changes",
};
const TOP_CLAUSES = 3;

function renderFaqs() {
  const d = current();
  if (state.guest) {
    $("tab-faqs").replaceChildren(lockCta("Get a straight answer to “Do they share my data?”, “Can I delete it?” and more, each with the strongest clauses as proof. Free with an account."));
    return;
  }
  const checks = Object.fromEntries((d.report?.checks || []).map((c) => [c.id, c]));
  const margin = (id, i) => (d.segments[id].scores?.[i] ?? 0) - (d.thresholds?.[i] ?? 0);
  const cards = Object.entries(d.faqs).map(([question, cat]) => {
    const i = categories().indexOf(cat);
    const ids = [...d.coverage[cat]].sort((a, b) => margin(b, i) - margin(a, i));  // Most confident first.
    const check = checks[FAQ_CHECK[question]];
    const answer = check ? `${check.label}. ${check.meaning}`
      : ids.length ? `${plural(ids.length, "paragraph")} cover this. The strongest are below.` : "";
    const open = state.expanded[question];
    return el("article", { class: "card faq" }, el("h3", {}, question),
      answer ? el("p", { class: "faq-answer" }, answer) : null,
      el("p", { class: "answered-by" }, "Best matching clauses about", chip(cat)),
      ids.length ? (open ? ids : ids.slice(0, TOP_CLAUSES)).map((id) => quoteButton(d.segments[id], cat))
        : el("p", { class: "nothing" }, "No matching clause found. The policy may not address this, or the model may have missed it."),
      ids.length > TOP_CLAUSES ? el("button", { type: "button", class: "link show-all",
        onclick: () => { state.expanded[question] = !open; renderFaqs(); } }, open ? "Show fewer" : `Show all ${ids.length}`) : null);
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
  // Scores and cutoffs are probabilities (0 to 1); a bar's length is the distance from the cutoff.
  const rows = s.scores ? categories().map((cat, i) => ({ cat, i, delta: s.scores[i] - d.thresholds[i] }))
    .sort((a, b) => b.delta - a.delta)
    .map(({ cat, i, delta }) => {
      const score = s.scores[i], cutoff = d.thresholds[i], hit = s.labels.includes(cat);
      const room = delta >= 0 ? 1 - cutoff : cutoff;
      const width = Math.min(Math.abs(delta) / Math.max(room, 0.01), 1) * 50;
      return el("div", { class: `meter ${hit ? "hit" : "miss"}`, style: `--c:${COLOR[cat]}` },
        el("span", { class: "meter-name" }, el("span", {}, cat), hit ? el("span", {}, "Matched") : null),
        el("span", { class: "meter-track" }, el("span", { class: "meter-fill", style: `width:${width}%;${delta >= 0 ? "left" : "right"}:50%` })),
        el("span", { class: "meter-num" }, `score ${score.toFixed(2)} · cutoff ${cutoff.toFixed(2)}`));
    }) : el("p", {}, "This server did not return scores.");
  return el("aside", { class: "card details" }, el("h3", {}, `Paragraph ${s.id + 1}`),
    el("div", { class: "seg-meta" }, s.labels.length ? s.labels.map(chip) : "No topic"),
    el("p", { class: "note" }, "The centre line is each topic's cutoff, tuned on validation data. Bars to the right passed it; bars to the left fell short. Scores are model outputs, not calibrated probabilities."),
    rows,
    el("p", { class: "note" }, `Characters ${s.start}–${s.end} of the text you pasted.`));
}

function select(id, scroll = true) {
  state.selected = id;
  showBreakdown(true);
  renderDoc(); showTab("doc");
  const node = $(`seg-${id}`);
  if (!node) return;
  if (scroll) node.scrollIntoView({ behavior: "smooth", block: "center" });
  node.classList.add("flash"); node.focus({ preventScroll: true });
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
    `Model: Inkwell RoBERTa, 5 topics (\`${d.run}\`) · ${plural(d.segments.length, "paragraph")} · ${new Date().toISOString().slice(0, 10)}`, "",
    "_Not legal advice. Quotes are exact text from the submitted policy. A topic marked not mentioned may be a model miss._", "",
    "## Topics not mentioned", "", ...(silent.length ? silent.map((c) => `- ${c}`) : ["None."]), ""];
  if (d.report) {
    lines.splice(6, 0, "## Privacy report card", "", ...d.report.checks.flatMap((c) => [
      `### ${c.title}: ${c.label}`, "", c.meaning, "", ...c.evidence.flatMap((e) => [quote(e.text), ""])]),
      ...(d.report.steps?.length ? ["## Your steps", "", ...d.report.steps.map((st) => `- [${state.done?.[st.id] ? "x" : " "}] ${st.title}${st.target ? `: ${st.target.value}` : st.to ? `: ${st.to}` : ""}`), ""] : []));
  }
  lines.push("## Common questions", "");
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
  // "See a sample report" on the home page: fill in the sample and run it once a model is ready.
  if (new URLSearchParams(location.search).has("sample")) { $("policy").value = SAMPLE; state.autoRun = true; }
  $("clear").addEventListener("click", () => { $("policy").value = ""; updateCounts(); $("policy").focus(); });
  $("split").addEventListener("click", () => {
    $("policy").value = $("policy").value.replace(/\r\n?/g, "\n").replace(/([^\n])\n(?=[^\n])/g, "$1\n\n");
    updateCounts();
  });
  $("file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > maxBytes()) setStatus(`That file is over the ${kb(maxBytes())} limit.`, "error");
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
    JSON.stringify({ generated: new Date().toISOString(), result: state.result }, null, 2)));
  $("dl-md").addEventListener("click", () => download("inkwell-report.md", "text/markdown", markdownReport()));
  $("toggle-breakdown").addEventListener("click", () => {
    const open = $("breakdown").hidden;
    showBreakdown(open);
    if (open) $("breakdown").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

async function connect() {
  try {
    state.ctx = await startAuth();
  } catch {
    document.body.dataset.auth = "ready";
    setLamp("down", "Waking up the server…");
    state.lampTimer = setTimeout(connect, 10000);
    return;
  }
  const user = await currentUser(state.ctx);
  // No account: a free check when the server allows guests, otherwise the login page.
  state.guest = state.ctx.enabled && !user;
  if (state.guest && !state.ctx.guest) return toLogin();
  // If this check can't reach Firebase, carry on: the API still refuses unconfirmed accounts.
  if (user && !(await isVerified(user).catch(() => true))) return toLogin();
  renderUser(user);
  state.user = user;
  $("guest-banner").hidden = !state.guest;
  updateCounts();  // Free checks have a lower size limit.
  if (state.ctx.enabled && user) state.ctx.fb.onAuthStateChanged(state.ctx.auth, (u) => { if (!u) location.replace("/"); });
  document.body.dataset.auth = "ready";
  checkApi();
  // Priorities and saved policies load after the page shows: account storage can take a few seconds,
  // or time out when Firestore isn't set up. afterAnalysis waits for this before matching saved policies.
  state.storeReady = (async () => {
    state.store = await openStore(state.ctx, user);
    await loadPriorities();
    await loadSaved();
    if (state.result) renderReport();
  })();
}

initDecide({ state, el, plural, select, signupUrl, lockCta, setStatus, refresh: () => { if (state.result) renderReport(); } });
wire();
updateCounts();
connect();
