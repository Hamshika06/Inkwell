// Inkwell product page. Talks to the API in config.js; renders API data only as text (never as HTML).
import { isLeaving, renderAccountMenu } from "./account.js";
import { API, authHeaders, currentUser, isVerified, startAuth, toggleTheme } from "./auth.js";
import { afterAnalysis, initDecide, loadPriorities, loadSaved, openSaved, priorityChips, renderDecision, renderPasteFocus, renderSteps, startRecheck } from "./decide.js";
import { inkLine } from "./progress.js";
import { glossify } from "./words.js";
import { initTour } from "./tour.js";
import { askAfterSteps, openReviewModal } from "./reviews.js";
import { openStore } from "./store.js";
import { asLink, el } from "./shared.js";

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
const $ = (id) => document.getElementById(id);

const chip = (cat) => el("span", { class: "chip", style: `--c:${COLOR[cat] || "#888"}`, title: DESCRIBE[cat] || cat }, cat);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const paragraphs = (text) => text.split(/\n[ \t]*\n/).filter((p) => p.trim()).length; // Same rule as inkwell/stage1.segment.
const kb = (bytes) => `${Math.round(bytes / 1000).toLocaleString()} KB`;

function toLogin() { location.replace(`login.html?next=${encodeURIComponent(location.pathname + location.search)}`); }
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
  renderAccountMenu(box, state.ctx, user, [
    el("a", { role: "menuitem", href: "reviews.html" }, "Reviews"),
    el("button", { type: "button", role: "menuitem", onclick: () => openReviewModal({ ctx: state.ctx, user }) }, "★ Rate Inkwell")]);
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

/* ---------- Tidying pasted text, and checking it is a privacy policy ---------- */

// The same words the server's link reader looks for, plus a rough English test.
const POLICY_WORDS = /personal (?:information|data)|your (?:information|data)|third[- ]part|cookies|we collect|privacy/gi;
const ENGLISH = /\b(?:the|and|of|to|we|you|your|is|in|for|with|that|our|or|this|may|are)\b/gi;
const TERMS = /terms of (?:service|use)|arbitration|governing law|you agree to (?:these|the) terms/i;

/** Web page code pasted by mistake (view-source): keep only the readable text, a paragraph per block. Null if it isn't code. */
function stripHtml(text) {
  if ((text.match(/<\/?(?:p|div|br|li|h[1-6]|html|body|span|a|section|table|tr|td|ul|ol)\b[^>]*>/gi) || []).length < 3) return null;
  const doc = new DOMParser().parseFromString(text, "text/html");  // Parsing only: scripts in it never run.
  doc.querySelectorAll("script, style, noscript, template, svg, head").forEach((n) => n.remove());
  doc.querySelectorAll("p, div, li, h1, h2, h3, h4, h5, h6, section, article, tr, br, table, ul, ol").forEach((n) => n.after("\n\n"));
  return (doc.body?.textContent || "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

/**
 * Text copied from a web page often has no blank lines, so a whole policy reads as one paragraph and the model only
 * sees its start. Long blocks are split at line breaks (or, with none, between sentences) into paragraphs of a few
 * hundred characters; short lines such as headings stay with the text after them. The words are unchanged.
 */
function tidyParagraphs(text) {
  const blocks = text.replace(/\r\n?/g, "\n").split(/\n[ \t]*\n/);
  if (!blocks.some((block) => block.trim().length > 1500)) return text;  // Nothing to split: leave it exactly as pasted.
  return blocks.map((block) => {
    if (block.trim().length <= 1500) return block;
    const lines = block.includes("\n");
    const pieces = lines ? block.split("\n") : block.match(/[^.!?]+(?:[.!?]+["')\]]*\s*|$)/g) || [block];
    const out = [];
    let cur = "";
    for (const piece of pieces) {
      cur += lines && cur ? `\n${piece}` : piece;
      if (cur.trim().length >= 400) { out.push(cur.trim()); cur = ""; }
    }
    if (cur.trim()) out.length && cur.trim().length < 150 ? (out[out.length - 1] += `${lines ? "\n" : " "}${cur.trim()}`) : out.push(cur.trim());
    return out.join("\n\n");
  }).join("\n\n");
}

/** Why this text may not be a privacy policy Inkwell can read, or null. */
function doubtAbout(text) {
  const words = text.split(/\s+/).filter(Boolean).length;
  const hits = (text.match(POLICY_WORDS) || []).length;
  if (words >= 25 && (text.match(ENGLISH) || []).length / words < 0.05) {
    return "This doesn't look like English. Inkwell reads English privacy policies only, so most answers would come back as “Not mentioned”. Many sites have an English version: look for a language switch at the bottom of their page.";
  }
  if (hits >= 2) return null;
  if (TERMS.test(text)) return "This looks like terms of service, not a privacy policy. Terms cover the rules for using a service; what happens to your data is usually in a separate privacy policy, often linked at the bottom of the same page.";
  return "This doesn't look like a privacy policy: we found almost none of the words policies use, like “personal information”, “cookies” or “third parties”. The answers would probably all say “Not mentioned”.";
}

/** Asks before checking text that may not be a policy. Resolves true to go ahead. */
function askFirst(message) {
  $("status").className = "status ask";
  $("status").replaceChildren(el("span", {}, message), el("span", { class: "ask-actions" },
    el("button", { type: "button", class: "btn btn-primary", onclick: () => { state.checkAnyway = true; setStatus(""); run(); } }, "Check it anyway"),
    el("button", { type: "button", class: "btn btn-ghost", onclick: () => { setStatus(""); $("policy").focus(); } }, "Paste something else")));
  $("status").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------- Input ---------- */

function updateCounts() {
  const text = $("policy").value;
  $("link-confirm").hidden = true;
  renderPasteFocus();
  if (asLink(text)) {
    $("counts").replaceChildren(el("span", {}, "Link: press “Check this policy” and we'll read this page."));
    $("warn").hidden = true;
    return;
  }
  const bytes = new TextEncoder().encode(text).length;
  const n = paragraphs(text);
  $("counts").replaceChildren(
    el("span", {}, `${text.length.toLocaleString()} characters`), el("span", {}, plural(n, "paragraph")),
    el("span", { class: bytes > maxBytes() || n > MAX_PARAGRAPHS ? "over" : null }, `${(bytes / 1000).toFixed(1)} KB of ${kb(maxBytes())}`));
  const warn = n === 1 && text.length > 1500
    ? "This reads as one long block. When you check it, Inkwell splits it into paragraphs so each part is read and quoted on its own."
    : bytes > maxBytes() ? `That's over the ${kb(maxBytes())} limit${state.guest ? " for a free check. Create a free account for up to 1,000 KB, or trim the policy" : ". Trim the policy before checking it"}.`
    : n > MAX_PARAGRAPHS ? `Inkwell reads up to ${MAX_PARAGRAPHS} paragraphs at a time. Split the policy in two and check each half.` : "";
  $("warn").textContent = warn; $("warn").hidden = !warn;
}

function setStatus(text, kind = "") { $("status").textContent = text; $("status").className = `status ${kind}`; }

function askAboutLink(page) {
  const box = $("link-confirm");
  box.replaceChildren(
    el("p", {}, el("strong", {}, `We found this policy for ${page.site}:`), " ",
      el("a", { href: page.url, target: "_blank", rel: "noopener noreferrer nofollow" }, page.url)),
    el("p", { class: "fine" }, "Is this the right page?"),
    el("div", { class: "request-actions" },
      el("button", { type: "button", class: "btn btn-primary", onclick: () => run(page.url, true) }, "Yes, check it"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => {
        box.hidden = true; setStatus("Paste the link to the policy itself, or its text."); $("policy").focus(); $("policy").select();
      } }, "No, I'll paste it")));
  box.hidden = false;
}

/** Reads the link and fills the box with what it found. False when there's nothing to check yet. */
async function readLink(url, confirmed, quiet = false) {
  if (!quiet) setStatus(`Reading ${url.replace(/^https?:\/\//i, "").slice(0, 60)}…`, "busy");
  $("run").disabled = true;
  try {
    const page = await api("/fetch-policy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, confirmed }) }, 60000);
    if (page.status === "confirm") {
      setStatus("");
      askAboutLink(page);
      return false;
    }
    $("policy").value = page.text;
    updateCounts();
    state.source = { url: page.url, site: page.site, text: page.text };
    return true;
  } catch (error) {
    setStatus(error.message, "error");
    return false;
  } finally {
    $("run").disabled = false;
  }
}

// The stages the ink line walks through. "Questions" because the report card asks 8 of them ("Does it sell your
// data?"); a free check answers 5 common ones instead.
const stageNames = () => ["Reading", "Sorting into 5 topics", state.guest ? "Answering 5 common questions" : "Checking 8 key questions", "Done"];

async function run(linkUrl = null, confirmed = false) {
  $("link-confirm").hidden = true;
  if (!$("policy").value.trim() && !linkUrl) return setStatus("Paste a link or a policy first, or load the sample.", "error");
  if (!ready()) return setStatus("Inkwell is still warming up. Try again when the status light turns green.", "error");
  const link = linkUrl || asLink($("policy").value);
  let note = "";
  if (!link) {
    // Pasted text: clean it up first (the words are unchanged), then make sure it's something Inkwell can read.
    const original = $("policy").value;
    const plain = stripHtml(original);
    const tidy = tidyParagraphs(plain ?? original);
    if (tidy !== original) {
      $("policy").value = tidy; updateCounts();
      note = plain !== null ? "We removed the web page code you pasted and kept its text. "
        : `We split the long block into ${plural(paragraphs(tidy), "paragraph")}, so each part is checked and quoted on its own. `;
    }
    const doubt = state.checkAnyway ? null : doubtAbout(tidy);
    state.checkAnyway = false;
    if (doubt) return askFirst(note + doubt);
  }
  setStatus("");
  $("run").disabled = true;
  $("ink").hidden = false;
  const ink = inkLine($("ink"), stageNames());
  const stop = (message = "", kind = "") => { ink.fail(); $("ink").hidden = true; $("run").disabled = false; setStatus(message, kind); };
  if (link) {
    ink.stage(0, `Step 1 of 3 · Reading ${link.replace(/^https?:\/\//i, "").slice(0, 48)}…`, 4000);
    if (!(await readLink(link, confirmed, true))) { const message = $("status").textContent; return stop(message, $("status").className.includes("error") ? "error" : ""); }
    $("run").disabled = true;  // readLink re-enables it.
  }
  const text = $("policy").value;
  if (new TextEncoder().encode(text).length > maxBytes()) return stop(`That's over the ${kb(maxBytes())} limit.`, "error");
  const n = paragraphs(text);
  if (n > MAX_PARAGRAPHS) return stop(`That's ${n} paragraphs; Inkwell reads up to ${MAX_PARAGRAPHS} at a time.`, "error");
  let result = null;
  try {
    if (!link) { ink.stage(0, `Step 1 of 3 · Reading ${plural(n, "paragraph")}…`, 500); await ink.wait(450); }
    ink.stage(1, `Step 2 of 3 · Sorting each paragraph into 5 topics…${n > 40 ? " Long policies take up to a minute." : ""}`, 1500 + n * 150);
    result = await api("/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    }, 300000);
    ink.stage(2, state.guest ? "Step 3 of 3 · Answering 5 common questions…" : "Step 3 of 3 · Checking 8 key questions, like “Does it sell your data?”…", 500);
    await ink.wait(550);
    await ink.finish(state.guest ? "The breakdown is below." : "Your report card is below.");
  } catch (error) {
    return stop(error.message, "error");
  }
  $("run").disabled = false;
  const short = state.source?.text === text && text.length < 3000;
  if (short) setStatus("That page was short, so it may be only part of the policy. If so, paste the full text.");
  else if (note) setStatus(note.trim());
  Object.assign(state, { result, filter: null, selected: null, expanded: {}, animated: false, allOpen: false, lastExposure: null });
  showBreakdown(state.guest);  // Free checks open on the breakdown; accounts open on the report card.
  renderResults();
  $("results").classList.remove("reveal"); void $("results").offsetWidth; $("results").classList.add("reveal");
  await afterAnalysis(text);
  showTab("overview");
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ---------- Results ---------- */

const current = () => state.result;
const categories = () => Object.keys(current().coverage);

function renderResults() {
  $("results").hidden = false;
  for (const id of ["dl-txt", "dl-json"]) $(id).hidden = state.guest;
  $("breakdown-bar").hidden = state.guest || !!state.savedView;  // Saved work keeps the report, not the full text.
  renderReport();
  if (state.savedView) return showBreakdown(false);
  renderKpis(); renderOverview(); renderFaqs(); renderDoc();
}

function showBreakdown(open) {
  $("breakdown").hidden = !open;
  $("toggle-breakdown").setAttribute("aria-expanded", String(open));
  $("toggle-breakdown").textContent = open ? "Hide full breakdown" : "Show full breakdown";
}

/* ---------- Report card ---------- */

// Neutral marks: whether the practice applies, not whether it's good or bad. The reader's priorities add emphasis.
const MARK = { true: { icon: "●", word: "Applies" }, false: { icon: "○", word: "Doesn't apply" }, null: { icon: "?", word: "Not settled by the text" } };

function receipt(evidence) {
  if (state.savedView) return el("blockquote", { class: "receipt plain-receipt" }, el("span", { class: "receipt-mark", "aria-hidden": "true" }, "“"), evidence.text);
  return el("button", { type: "button", class: "receipt", title: "Show this sentence in the full policy",
    onclick: () => select(evidence.segment_id) },
    el("span", { class: "receipt-mark", "aria-hidden": "true" }, "“"), evidence.text);
}

function proofFor(check) {
  if (!check.evidence.length) return null;
  const more = check.evidence_count - 1;
  return [receipt(check.evidence[0]),
    more > 0 ? el("details", { class: "more-receipts" },
      el("summary", {}, `${more} more ${more === 1 ? "sentence" : "sentences"} like this`),
      check.evidence.slice(1).map(receipt),
      more > check.evidence.length - 1 ? el("p", { class: "note" }, "Open the full breakdown to read the rest.") : null) : null,
    check.counter.length ? el("div", { class: "counter" }, el("span", {}, "But the policy also says:"), receipt(check.counter[0])) : null];
}

function renderCheck(check, i, concern) {
  const mine = state.priorities?.includes(check.id);
  const mark = MARK[check.applies ?? null];
  return el("li", { class: `check applies-${check.applies ?? "unknown"}${mine ? " mine" : ""}`, id: `check-${check.id}`, style: `--i:${i}` },
    el("span", { class: "check-icon", role: "img", "aria-label": mark.word, title: mark.word }, mark.icon),
    el("div", { class: "check-body" },
      el("div", { class: "check-top" }, el("h3", {}, check.title), el("span", { class: "verdict-pill" }, check.label),
        mine ? el("span", { class: "tag mine-tag" }, "Matters to you") : null,
        concern ? el("span", { class: `tag ${concern.fixable ? "fix-tag" : "stay-tag"}` }, concern.fixable ? "You can limit this" : "No way to limit this found") : null),
      el("p", { class: "check-meaning" }, check.meaning),
      concern?.note ? el("p", { class: "fine" }, concern.note) : null,
      proofFor(check)));
}

function guestOffer() {
  return el("aside", { class: "card guest-offer", "aria-label": "Privacy report card" },
    el("div", {}, el("h2", {}, "Want your privacy report card?"),
      el("p", {}, "This free check shows what the policy covers, topic by topic. A free account adds:"),
      el("ul", { class: "you-get" }, ["What you'd be agreeing to, in plain words", "How to limit it, with ready-to-send opt-out and deletion emails", "A dashboard that keeps every check you run"].map((t) => el("li", {}, t)))),
    el("a", { class: "btn btn-primary btn-lg", href: signupUrl() }, "Get my report card, free"));
}

function renderReport() {
  if (state.guest) return $("report").replaceChildren(guestOffer());
  const r = current().report;
  if (!r) return $("report").replaceChildren();
  const concerns = Object.fromEntries((r.concerns || []).map((c) => [c.id, c]));
  // Mine first, in the order the reader sees them in the decision bar; then the rest.
  const mine = state.priorities || [];
  const ordered = [...r.checks].sort((a, b) => Number(mine.includes(b.id)) - Number(mine.includes(a.id)));
  $("report").replaceChildren(el("article", { class: `card report-card${state.animated ? " static" : ""}`, "aria-label": "Privacy report card" },
    el("header", { class: "rc-head" },
      el("div", {}, r.title ? el("p", { class: "eyebrow" }, "Privacy report card") : null, el("h2", {}, r.title || "Your privacy report card"))),
    renderDecision(),
    renderSteps(),
    el("details", { class: "all-answers", open: state.allOpen, ontoggle: (e) => { state.allOpen = e.target.open; } },
      el("summary", {}, `See all ${r.checks.length} answers`),
      el("ul", { class: "checks" }, ordered.map((c, i) => renderCheck(c, i, concerns[c.id])))),
    el("p", { class: "rc-note" }, r.limitation)));
  glossify($("report"), ".receipt, .check-meaning, .for-you", state.current?.name || r.company);
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
  const checks = Object.fromEntries((d.report?.checks || []).map((c) => [c.id, c]));
  const margin = (id, i) => (d.segments[id].scores?.[i] ?? 0) - (d.thresholds?.[i] ?? 0);
  const cards = Object.entries(d.faqs).map(([question, cat]) => {
    const i = categories().indexOf(cat);
    const ids = [...d.coverage[cat]].sort((a, b) => margin(b, i) - margin(a, i));  // Most confident first.
    const check = checks[FAQ_CHECK[question]];
    const answer = check ? `${check.label}. ${check.meaning}`
      : ids.length === 1 ? "1 paragraph covers this." : ids.length ? `${ids.length} paragraphs cover this. The strongest are below.` : "";
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

function textReport() {
  const d = current();
  const quote = (text) => `    "${text.replace(/\s*\n\s*/g, " ")}"`;
  const heading = (text) => [text.toUpperCase(), "=".repeat(text.length), ""];
  const silent = categories().filter((c) => !d.coverage[c].length);
  const lines = ["INKWELL PRIVACY REPORT", "",
    `Policy: ${state.current?.name || d.report?.title || "Pasted policy"}`,
    `Checked: ${new Date().toISOString().slice(0, 10)}, ${plural(d.segments.length, "paragraph")}`,
    "Not legal advice. Quotes are exact text from the policy. A topic marked not mentioned may be a model miss.", ""];
  if (d.report) {
    lines.push(...heading("Privacy report card"));
    for (const c of d.report.checks) lines.push(`${c.title}: ${c.label}`, `  ${c.meaning}`, ...c.evidence.map((e) => quote(e.text)), "");
    if (d.report.steps?.length) {
      lines.push(...heading("Your steps"));
      for (const st of d.report.steps) lines.push(`[${state.done?.[st.id] ? "x" : " "}] ${st.title}${st.target?.kind === "url" ? `: ${st.target.value}` : st.to ? `: ${st.to}` : ""}`);
      lines.push("");
    }
  }
  lines.push(...heading("Topics not mentioned"), ...(silent.length ? silent : ["None."]), "");
  lines.push(...heading("Common questions"));
  for (const [question, cat] of Object.entries(d.faqs)) {
    const ids = d.coverage[cat];
    lines.push(question, ...(ids.length ? ids.map((id) => quote(d.segments[id].text)) : [`  ${d.empty_message}.`]), "");
  }
  lines.push(...heading("Text by topic"));
  for (const cat of categories()) {
    if (d.coverage[cat].length) lines.push(`${cat} (${d.coverage[cat].length})`, ...d.coverage[cat].map((id) => quote(d.segments[id].text)), "");
  }
  return lines.join("\n");
}

/* ---------- Wiring ---------- */

function wire() {
  $("policy").addEventListener("input", updateCounts);
  $("policy").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
  $("run").addEventListener("click", () => run());
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
  $("dl-txt").addEventListener("click", () => download("inkwell-report.txt", "text/plain;charset=utf-8", textReport()));
  $("toggle-breakdown").addEventListener("click", () => {
    const open = $("breakdown").hidden;
    showBreakdown(open);
    if (open) $("breakdown").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

/* ---------- Welcome moments ---------- */

const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/** "n. aniruddhan" -> "Aniruddhan"; "ada.lovelace@x.com" -> "Ada". */
function firstName(user) {
  const raw = user?.displayName || (user?.email || "").split("@")[0] || "";
  const word = raw.split(/[\s._-]+/).find((w) => w.length > 2 && /^\p{L}+$/u.test(w)) || "";
  return word ? word[0].toUpperCase() + word.slice(1).toLowerCase() : "";
}

/** "https://www.pigeonpost.co.uk/privacy" -> "Pigeonpost" (the same rule as the server). */
function siteOf(url) {
  try {
    const labels = new URL(/^https?:\/\//i.test(url) ? url : `https://${url}`).hostname.toLowerCase().replace(/^www\./, "").split(".");
    const key = labels.length >= 3 && ["co", "com", "org", "net", "ac", "gov", "edu"].includes(labels.at(-2)) ? labels.at(-3) : labels.at(-2) || labels[0];
    return key.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  } catch { return "this site"; }
}

/** After signing in: "Welcome back, Aniruddhan" for a moment, then the paste page. Returns { done(savedCount) }. */
function showWelcome(kind) {
  const box = $("welcome"), name = firstName(state.user), started = performance.now();
  const line = el("i"), sub = el("p", {}, kind === "new" ? "Let's check your first privacy policy." : "Setting up a new check…");
  box.replaceChildren(el("div", { class: "welcome-inner" }, el("img", { class: "welcome-mark", src: "logo.svg", alt: "" }),
    el("h1", {}, kind === "new" ? `Welcome to Inkwell${name ? `, ${name}` : ""}` : `Welcome back${name ? `, ${name}` : ""}`), sub,
    el("div", { class: "welcome-line", "aria-hidden": "true" }, line)));
  box.hidden = false;
  requestAnimationFrame(() => requestAnimationFrame(() => { line.style.width = "70%"; }));
  let closing = null;
  const done = (saved = 0) => closing || (closing = (async () => {
    if (kind !== "new" && saved) sub.textContent = `Setting up a new check. You have ${saved === 1 ? "1 saved policy" : `${saved} saved policies`} on your dashboard.`;
    line.style.width = "100%";
    await new Promise((resolve) => setTimeout(resolve, calm() ? 0 : Math.max(700, 1500 - (performance.now() - started))));
    box.classList.add("leaving");
    setTimeout(() => { box.hidden = true; box.classList.remove("leaving"); }, calm() ? 0 : 400);
  })());
  setTimeout(() => done(), 5000);  // Never hold the page longer than this, even if saved work is slow to load.
  return { done };
}

/** From the extension's "See the full report": say where you came from, and check only when asked. */
function showArrival(url) {
  state.arriving = url;
  $("intro").hidden = true; $("workspace").hidden = true;
  renderArrival();
  $("arrive").hidden = false;
}

function renderArrival() {
  const url = state.arriving;
  if (!url) return;
  const site = siteOf(url);
  const focus = !state.guest && state.store
    ? [el("p", { class: "fine" }, "What do you care about most? We'll put these first."), priorityChips("#arrive")] : [];
  const enter = !state.arriveShown;
  state.arriveShown = true;
  $("arrive").replaceChildren(el("div", { class: `card arrive-card${enter ? " enter" : ""}` },
    el("img", { class: "welcome-mark", src: "logo.svg", alt: "" }),
    el("h1", {}, "Welcome to Inkwell"),
    el("p", {}, "You opened this from the Inkwell extension. Here's the policy you were looking at:"),
    el("div", { class: "arrive-from" }, el("strong", {}, site), "·", el("span", {}, url.replace(/^https?:\/\//i, ""))),
    ...focus,
    el("button", { type: "button", class: "btn btn-primary btn-lg btn-block", onclick: () => leaveArrival(true) }, `Check ${site}'s policy`),
    el("button", { type: "button", class: "arrive-other", onclick: () => leaveArrival(false) }, "Not this one? Paste a different link or text")));
}

function leaveArrival(check) {
  const url = state.arriving;
  state.arriving = null;
  $("arrive").hidden = true; $("intro").hidden = false; $("workspace").hidden = false;
  history.replaceState(null, "", location.pathname);
  $("policy").value = check ? url : "";
  updateCounts();
  if (!check) return $("policy").focus();
  if (ready()) run();
  else { state.autoRun = true; setStatus("Starting as soon as Inkwell is ready…", "busy"); }
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
  const params = new URLSearchParams(location.search);
  const welcome = (user || !state.ctx.enabled) && params.get("welcome") ? showWelcome(params.get("welcome")) : null;
  if (params.has("welcome")) { params.delete("welcome"); history.replaceState(null, "", location.pathname + (params.size ? `?${params}` : "")); }
  const arriving = params.get("url");
  if (arriving && asLink(arriving)) showArrival(asLink(arriving));
  $("guest-banner").hidden = !state.guest;
  $("app-nav").hidden = state.guest;
  if (state.guest) {
    $("run-label").textContent = "Your free check";
    $("you-get").replaceChildren(...["Every paragraph sorted into 5 topics", "Straight answers to common questions", "The whole policy, readable by topic"].map((t) => el("li", {}, t)));
  }
  updateCounts();  // Free checks have a lower size limit.
  if (state.ctx.enabled && user) state.ctx.fb.onAuthStateChanged(state.ctx.auth, (u) => { if (!u && !isLeaving()) location.replace("/"); });
  document.body.dataset.auth = "ready";
  initTour({ signedIn: !state.guest });
  checkApi();
  // Priorities and saved policies load after the page shows: account storage can take a few seconds,
  // or time out when Firestore isn't set up. afterAnalysis waits for this before matching saved policies.
  state.storeReady = (async () => {
    state.store = await openStore(state.ctx, user);
    await loadPriorities();
    await loadSaved();
    welcome?.done(Object.keys(state.saved || {}).length);
    renderPasteFocus();
    renderArrival();
    const query = new URLSearchParams(location.search);
    if (query.get("open")) openSaved(query.get("open"));
    else if (query.get("recheck")) startRecheck(query.get("recheck"));
    else if (state.result) renderReport();
  })();
}

initDecide({ state, el, plural, select, setStatus, proof: proofFor, showResults: renderResults, refresh: () => { if (state.result) renderReport(); renderArrival(); } });
document.addEventListener("inkwell:steps-done", (e) => { if (!state.guest) askAfterSteps({ ctx: state.ctx, user: state.user, ...e.detail }); });
wire();
updateCounts();
connect();
