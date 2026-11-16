// What to do about a policy: the reader's own priorities, a neutral decision bar, a checklist of steps the
// policy itself offers (opt-out links, pre-written emails to its privacy address), and saving it all to an
// account (every check, automatically) so the next check shows what changed. Inkwell states facts; the reader decides what matters.
import { fingerprint, policyId } from "./store.js";

// The things a reader can say matter to them, one per report-card check (same ids).
export const PRIORITIES = [
  ["sale", "Selling my data"], ["ads", "Targeted ads"], ["sharing", "Sharing with other companies"],
  ["location", "My location"], ["retention", "How long they keep my data"], ["delete", "Being able to delete my data"],
  ["optout", "Being able to opt out"], ["changes", "Hearing about policy changes"],
];
const PRIORITY_LABEL = Object.fromEntries(PRIORITIES);

let ui;  // { state, el, plural, select, refresh, showResults, setStatus }
export function initDecide(context) { ui = context; }

const report = () => ui.state.result?.report;
const company = () => ui.state.current?.name || report()?.company || "the company";
const dateText = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");

/* ---------- What you care about: a filter on the list, applied as you tap ---------- */

export async function loadPriorities() {
  try { ui.state.priorities = await ui.state.store.getPriorities(); } catch { ui.state.priorities = null; }
}

let saveTimer;

async function storePriorities() {
  const { state } = ui;
  try {
    await state.storeReady;
    await state.store.setPriorities(state.priorities || []);
    return true;
  } catch {
    ui.setStatus("Couldn't save your picks. They'll apply until you leave this page.", "error");
    return false;
  }
}

function togglePriority(id, scope) {
  const { state } = ui;
  const picked = new Set(state.priorities || []);
  picked.has(id) ? picked.delete(id) : picked.add(id);
  state.priorities = PRIORITIES.map(([key]) => key).filter((key) => picked.has(key));
  state.focusSaved = false;
  ui.refresh();
  renderPasteFocus();
  document.querySelector(`${scope} [data-prio="${id}"]`)?.focus();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(storePriorities, 500);
}

async function finishFocus() {
  const { state } = ui;
  clearTimeout(saveTimer);
  state.editingFocus = false;
  ui.refresh();
  state.focusSaved = await storePriorities();
  ui.refresh();
}

function chips(scope) {
  const { el, state } = ui;
  const mine = state.priorities || [];
  return el("div", { class: "prio-chips", role: "group", "aria-label": "What you care about" }, PRIORITIES.map(([id, label]) => el("button", {
    type: "button", class: "prio-chip", "data-prio": id, "aria-pressed": String(mine.includes(id)), onclick: () => togglePriority(id, scope),
  }, label)));
}

/** The priority chips, for other places that ask (the extension arrival card). */
export const priorityChips = (scope) => chips(scope);

/** On the paste page: once there's a policy in the box, ask what to focus on before checking it. Accounts only. */
export function renderPasteFocus() {
  const { el, state, plural } = ui;
  const box = document.getElementById("paste-focus"), list = document.getElementById("you-get");
  if (!box) return;
  const ask = !!state.store && !state.guest && !!document.getElementById("policy").value.trim();
  box.hidden = !ask; list.hidden = ask;
  if (!ask) return box.replaceChildren();
  const mine = state.priorities || [];
  box.replaceChildren(
    el("p", { class: "focus-q" }, "What do you care about most?"),
    el("p", { class: "fine" }, "Pick any, then check the policy. Your report will focus on these, and we'll remember them."),
    chips("#paste-focus"),
    el("p", { class: "paste-picked", role: "status" }, mine.length ? `✓ We'll focus on the ${plural(mine.length, "thing")} you picked.` : "Nothing picked: we'll show everything."));
}

function renderFocus() {
  const { el, state } = ui;
  const mine = state.priorities || [];
  if (state.editingFocus) {
    return el("div", { class: "focus editing" },
      el("p", { class: "focus-q" }, "What do you care about most?"),
      el("p", { class: "fine" }, "Tap any that matter to you. The list below changes as you tap, and your picks apply to every policy you check."),
      chips(".focus"),
      el("button", { type: "button", class: "btn btn-primary focus-done", onclick: finishFocus }, "Done"));
  }
  const open = () => { state.editingFocus = true; state.focusSaved = false; ui.refresh(); };
  if (!mine.length) {
    return el("div", { class: "focus" }, el("span", {}, "Showing everything we check."),
      el("button", { type: "button", class: "link", onclick: open }, "Show only what I care about"));
  }
  const where = state.store?.mode === "account" ? "your account" : "this browser";
  return el("div", { class: "focus" },
    el("span", {}, "Showing only what you care about: ", el("strong", {}, mine.map((id) => PRIORITY_LABEL[id]).join(", ")), "."),
    el("button", { type: "button", class: "link", onclick: open }, "Change"),
    state.focusSaved ? el("p", { class: "focus-saved", role: "status" }, `✓ Saved to ${where}. We'll use these picks for every policy you check.`) : null);
}

/* ---------- The decision: what agreeing means, then the reader's choice ---------- */

export function renderDecision() {
  const { el, state, plural } = ui;
  const r = report();
  if (!r?.concerns) return null;
  const mine = state.priorities?.length ? state.priorities : null;
  const shown = mine ? r.concerns.filter((c) => mine.includes(c.id)) : r.concerns;
  const others = mine ? r.concerns.filter((c) => !mine.includes(c.id)) : [];
  const unclear = r.checks.filter((c) => c.applies == null && (!mine || mine.includes(c.id)));
  const who = state.current?.name || r.company || "this company";
  const headline = shown.length ? `If you agree, ${who}:`
    : mine ? "None of the things you picked came up in this policy." : "We didn't find any of the things we check for in this policy.";
  const summary = [others.length ? `${others.length} you didn't pick` : null,
    unclear.length ? `${unclear.length} the policy doesn't clearly answer` : null].filter(Boolean).join(" · ");
  return el("section", { class: "decision", "aria-label": "Your decision" },
    renderChanges(),
    renderFocus(),
    el("h3", { class: "decision-title" }, headline),
    shown.length ? el("ul", { class: "concerns" }, shown.map(concernRow)) : null,
    shown.length ? el("p", { class: "fine" }, "Tap a line to see the exact sentence from the policy.") : null,
    summary ? el("details", { class: "more-info", open: state.moreOpen, ontoggle: (e) => { state.moreOpen = e.target.open; } }, el("summary", {}, `Also: ${summary}`),
      others.length ? el("p", { class: "fine" }, el("strong", {}, "You didn't pick: "), others.map((c) => c.title.toLowerCase()).join(", "), ".") : null,
      unclear.length ? el("p", { class: "fine" }, el("strong", {}, "Not clearly answered: "), unclear.map((c) => (PRIORITY_LABEL[c.id] || c.title).toLowerCase()).join(", "), ".") : null) : null,
    state.decision ? renderDecided(state.decision) : renderChoices(shown),
    renderSaveRow());
}

function concernRow(c) {
  const { el, state } = ui;
  const open = !!state.openConcerns?.[c.id];
  const check = report().checks.find((k) => k.id === c.id);
  return el("li", { class: `concern ${c.fixable ? "fixable" : "stays"}${open ? " open" : ""}` },
    el("button", { type: "button", class: "concern-toggle", "aria-expanded": String(open),
      onclick: () => { state.openConcerns = { ...(state.openConcerns || {}), [c.id]: !open }; ui.refresh(); document.querySelector(`[data-concern="${c.id}"]`)?.focus(); }, "data-concern": c.id },
      el("span", { class: "concern-chev", "aria-hidden": "true" }, "▸"),
      el("span", { class: "concern-name" }, c.title),
      el("span", { class: "concern-tag" }, c.fixable ? "You can limit this" : "No way to limit this found")),
    open ? el("div", { class: "concern-detail" }, el("p", { class: "check-meaning" }, check.meaning),
      c.note ? el("p", { class: "fine" }, c.note) : null, ui.proof(check)) : null);
}

function renderChoices(shown) {
  const { el } = ui;
  const r = report();
  const fixable = shown.filter((c) => c.fixable).length;
  const limit = fixable === 1 ? "Show me how to limit this" : fixable > 1 ? "Show me how to limit these" : r.steps.length ? "See what I can do" : null;
  return el("div", { class: "decision-ask" },
    el("p", { class: "decision-q" }, "What do you want to do?"),
    el("div", { class: "decision-actions", role: "group", "aria-label": "What do you want to do?" },
      limit ? choice("steps", limit) : null, choice("agree", "Accept it as is"), choice("leave", "Don't accept")),
    el("p", { class: "fine" }, "This is only for your own records. Inkwell never contacts the company."));
}

function choice(id, label) {
  return ui.el("button", { type: "button", class: "btn btn-lg decision-btn", onclick: () => decide(id) }, label);
}

function decide(id) {
  const { state } = ui;
  state.decision = id;
  ui.refresh();
  autosave({ decision: id });
  if (id === "steps") document.getElementById("steps")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function changeAnswer() {
  const { state } = ui;
  state.decision = null; state.showSteps = false;
  ui.refresh();
  autosave({ decision: null });
}

// Closure: replaces the buttons with what was chosen and what happens next.
function renderDecided(decision) {
  const { el, state } = ui;
  const del = report().steps.find((s) => s.id === "request_delete");
  const goToSteps = el("button", { type: "button", class: "btn", onclick: () => document.getElementById("steps")?.scrollIntoView({ behavior: "smooth", block: "start" }) }, "Go to my steps");
  const writeRequest = () => { state.showSteps = true; state.stepAt = report().steps.indexOf(del); state.openRequest = "request_delete"; ui.refresh(); document.getElementById("step-request_delete")?.scrollIntoView({ behavior: "smooth", block: "center" }); };
  const content = {
    steps: ["You chose to limit this.", "Your steps are below, one at a time.", goToSteps],
    agree: ["You chose to accept this policy as it is.", "Nothing else to do.", null],
    leave: ["You chose not to accept this policy.",
      del ? `Already have an account with ${company()}? You can ask them to delete your data.` : "If you already have an account, look for a privacy or account-deletion page on their website.",
      del ? el("button", { type: "button", class: "btn", onclick: writeRequest }, "Write the deletion request") : null],
  }[decision];
  return el("div", { class: "decided", role: "status" },
    el("p", { class: "decided-title" }, `✓ ${content[0]}`),
    el("p", { class: "decided-next" }, content[1]),
    el("div", { class: "decided-actions" }, content[2], el("button", { type: "button", class: "link", onclick: changeAnswer }, "Change my answer")));
}

/* ---------- Steps ---------- */

/** One step at a time, shown once the reader asks to limit what the policy allows. */
export function renderSteps() {
  const { el, state } = ui;
  const r = report();
  if (!r?.steps || !(state.decision === "steps" || state.showSteps)) return null;
  const list = r.steps, done = state.done || {}, total = list.length;
  const doneCount = list.filter((st) => done[st.id]).length;
  const head = el("div", { class: "steps-head" }, el("h3", {}, "Your steps"),
    total ? el("span", { class: "steps-progress" }, `${doneCount} of ${total} done`) : null);
  if (!total) {
    return el("section", { class: "steps", id: "steps" }, head,
      el("p", { class: "note" }, "This policy doesn't give opt-out links or a privacy email in the text you pasted. Look for “Your Privacy Choices” or “Do Not Sell” in the footer of their website."));
  }
  const firstOpen = list.findIndex((st) => !done[st.id]);
  const at = Math.min(state.stepAt ?? (firstOpen < 0 ? total : firstOpen), total);
  return el("section", { class: "steps", id: "steps" }, head,
    el("ol", { class: "step-pills", "aria-label": "Steps" }, list.map((st, i) => el("li", {},
      el("button", { type: "button", class: `step-pill${i === at ? " current" : ""}${done[st.id] ? " done" : ""}`, "aria-current": i === at ? "step" : null,
        "aria-label": `Step ${i + 1}: ${st.title}${done[st.id] ? " (done)" : ""}`, onclick: () => goToStep(i) }, done[st.id] ? "✓" : String(i + 1))))),
    at === total ? finishedSteps(firstOpen, total, doneCount) : stepCard(list[at], at, total, !!done[list[at].id]));
}

function goToStep(i) {
  const { state } = ui;
  state.stepAt = i; state.openRequest = null;
  ui.refresh();
  document.getElementById("guided")?.focus({ preventScroll: true });
}

function finishedSteps(firstOpen, total, doneCount) {
  const { el } = ui;
  const left = total - doneCount;
  return el("div", { class: "step guided finished", id: "guided", tabindex: "-1", role: "status" },
    el("strong", {}, left ? "You've been through every step." : `✓ All ${total} steps done.`),
    el("p", { class: "step-detail" }, left ? `${left} still to do whenever you're ready.` : "Your progress is saved."),
    left ? el("div", { class: "step-nav" }, el("button", { type: "button", class: "btn", onclick: () => goToStep(firstOpen) }, "Go to the first one left")) : null);
}

function stepCard(step, i, total, checked) {
  const { el, state } = ui;
  const r = report();
  const helps = r.concerns.filter((c) => c.steps.includes(step.id)).map((c) => c.title.toLowerCase());
  const body = [];
  if (step.target?.kind === "url") {
    body.push(el("a", { class: "btn step-go", href: step.target.value, target: "_blank", rel: "noopener noreferrer nofollow" },
      `Open ${step.target.value.replace(/^https?:\/\//i, "").replace(/\/$/, "")} ↗`));
  } else if (step.target?.kind === "named_link") {
    body.push(el("p", { class: "step-detail" }, "Usually in the footer of their website or app."));
  }
  if (step.detail) body.push(el("p", { class: "step-detail" }, step.detail));
  if (step.to) {
    const open = state.openRequest === step.id;
    body.push(el("p", { class: "step-detail" }, "To: ", el("span", { class: "mono" }, step.to)));
    body.push(open ? requestEditor(step) : el("button", { type: "button", class: "btn step-go", onclick: () => { state.openRequest = step.id; ui.refresh(); } }, "Write the email"));
    body.push(el("p", { class: "fine" }, "This is a template, not legal advice. Nothing is sent unless you send it from your own email."));
  }
  const nextOpen = () => {
    for (let j = i + 1; j < total; j++) if (!state.done?.[r.steps[j].id]) return j;
    return total;
  };
  return el("div", { class: "step guided", id: `step-${step.id}` },
    el("div", { id: "guided", tabindex: "-1" },
      el("p", { class: "step-count" }, `Step ${i + 1} of ${total}`),
      el("div", { class: "step-top" }, el("strong", {}, step.title),
        step.source === "general" ? el("span", { class: "step-src" }, "General advice") : null,
        step.segment_id != null && !state.savedView ? el("button", { type: "button", class: "found-in", onclick: () => ui.select(step.segment_id) }, "Where the policy says this") : null),
      helps.length ? el("p", { class: "step-helps" }, `Helps with: ${helps.join(", ")}`) : null,
      body),
    el("div", { class: "step-nav" },
      checked
        ? [el("span", { class: "step-done-note" }, "✓ You've done this."), el("button", { type: "button", class: "btn btn-primary", onclick: () => goToStep(i + 1) }, i + 1 < total ? "Next step" : "Finish"),
           el("button", { type: "button", class: "link", onclick: () => tick(step.id, false) }, "Mark as not done")]
        : [el("button", { type: "button", class: "btn btn-primary", onclick: () => { state.stepAt = nextOpen(); state.openRequest = null; tick(step.id, true); document.getElementById("guided")?.focus({ preventScroll: true }); } }, nextOpen() < total ? "Done, next step" : "Done"),
           el("button", { type: "button", class: "btn btn-ghost", onclick: () => goToStep(i + 1) }, "Skip for now")],
      i > 0 ? el("button", { type: "button", class: "link", onclick: () => goToStep(i - 1) }, "Back") : null));
}

function tick(id, on) {
  const { state } = ui;
  state.done = { ...(state.done || {}), [id]: on };
  if (!on) delete state.done[id];
  ui.refresh();
  autosave({ done: state.done });
}

/* ---------- Pre-written requests ---------- */

const LAW = "Where they apply to me, I'm making this request under privacy laws such as the California Consumer Privacy Act (CCPA, as amended by the CPRA) and the EU/UK General Data Protection Regulation (GDPR).";
const TEMPLATES = {
  delete: (c, name, email) => ({
    subject: "Request to delete my personal information",
    body: `Hello ${c} privacy team,\n\nI'm asking you to delete the personal information you hold about me, and to tell any companies you have shared it with to delete it too.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nPlease confirm when this is done. If you keep any of my information, please tell me what you keep and why, and let me know if you need anything else to verify my identity.\n\n${LAW}\n\nThank you,\n${name}`,
  }),
  optout: (c, name, email) => ({
    subject: "Please do not sell or share my personal information",
    body: `Hello ${c} privacy team,\n\nPlease stop selling or sharing my personal information, including for targeted (cross-context behavioral) advertising, and opt me out of any such use from now on.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nPlease confirm once this is in place.\n\n${LAW}\n\nThank you,\n${name}`,
  }),
  access: (c, name, email) => ({
    subject: "Request for a copy of my personal information",
    body: `Hello ${c} privacy team,\n\nPlease send me a copy of the personal information you hold about me, including where you got it, what you use it for, and which companies you have shared or sold it to.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nLet me know if you need anything else to verify my identity.\n\n${LAW}\n\nThank you,\n${name}`,
  }),
};

function requestEditor(step) {
  const { el, state } = ui;
  const user = state.user;
  const f = state.requestFields ||= { name: user?.displayName || "", email: user?.email || "" };
  const draft = () => TEMPLATES[step.template](company(), f.name || "[your name]", f.email || "[the email on your account]");
  const preview = el("textarea", { class: "request-text", rows: "11", "aria-label": "Email text", spellcheck: "false" });
  const sync = () => { const d = draft(); preview.value = `Subject: ${d.subject}\n\n${d.body}`; };
  const field = (key, label, type) => el("label", { class: "request-field" }, label,
    el("input", { type, class: "input", value: f[key], oninput: (e) => { f[key] = e.target.value; sync(); } }));
  sync();
  const parts = () => {
    const text = preview.value;
    const m = text.match(/^Subject: (.*)\n\n([\s\S]*)$/);
    return m ? { subject: m[1], body: m[2] } : { subject: draft().subject, body: text };
  };
  return el("div", { class: "request" },
    el("div", { class: "request-fields" }, field("name", "Your name", "text"), field("email", "Email on your account with them", "email")),
    preview,
    el("div", { class: "request-actions" },
      el("button", { type: "button", class: "btn btn-primary", onclick: () => {
        const { subject, body } = parts();
        location.href = `mailto:${encodeURIComponent(step.to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
      } }, "Open in my email app"),
      el("button", { type: "button", class: "btn", onclick: async (e) => {
        const { subject, body } = parts();
        try { await navigator.clipboard.writeText(`${subject}\n\n${body}`); e.target.textContent = "Copied"; } catch { preview.select(); }
      } }, "Copy text"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.openRequest = null; ui.refresh(); } }, "Close")),
    el("p", { class: "fine" }, "Some companies ask you to use a web form instead; you can paste this text there."));
}

/* ---------- Saved work: every check is kept automatically; the dashboard lists it ---------- */

const verdictsOf = (r) => Object.fromEntries(r.checks.map((c) => [c.id, { state: c.state, label: c.label }]));
const HISTORY_LIMIT = 24;  // Earlier results kept per policy.

/** After each check: find this policy's saved work (if any), work out what changed, and save. */
export async function afterAnalysis(text) {
  const { state } = ui;
  await state.storeReady?.catch(() => {});  // Saved work may still be loading.
  const r = report();
  if (!r) return;  // Free checks have no report card and aren't saved.
  const fp = await fingerprint(text).catch(() => null);
  const source = state.source?.text === text ? state.source : null;  // Read from a link: name it after the site if needed.
  if (source) {  // Headings like "Privacy & Terms" make poor names, so use the site; keep its spelling if the title has it.
    r.company = (r.company || "").split(/\s+/).find((w) => w.toLowerCase() === source.site.toLowerCase()) || source.site;
  }
  const saved = state.saved || {};
  const named = r.company && saved[policyId(r.company)] ? policyId(r.company) : null;
  const same = fp ? Object.keys(saved).find((k) => saved[k].fingerprint === fp) : null;
  const id = state.recheck || named || same || null;
  const prior = id ? saved[id] : null;
  state.current = { id: prior ? id : null, name: prior?.name || r.company || "", url: source?.url || prior?.url || "", fingerprint: fp, saved: false };
  state.decision = null; state.done = {}; state.openRequest = null; state.focusSaved = false; state.editingFocus = false;
  state.changes = null; state.openConcerns = {}; state.moreOpen = false; state.stepAt = null; state.showSteps = false;
  if (prior) {
    state.changes = { since: prior.checkedAt, textChanged: prior.fingerprint !== fp, verdicts: diff(prior.verdicts || {}, verdictsOf(r)) };
    // Steps you already took stay ticked; a changed policy needs a fresh decision.
    const stillThere = new Set(r.steps.map((st) => st.id));
    state.done = Object.fromEntries(Object.entries(prior.done || {}).filter(([k, v]) => v && stillThere.has(k)));
    state.decision = prior.fingerprint === fp ? prior.decision || null : null;
  }
  state.recheck = null;
  await save();
  if (location.search) history.replaceState(null, "", "app.html");  // A reload now starts fresh.
  ui.refresh();
}

function diff(before, after) {
  const titles = Object.fromEntries(report().checks.map((c) => [c.id, c.title]));
  return Object.keys(after).filter((k) => before[k] && before[k].state !== after[k].state)
    .map((k) => ({ id: k, title: titles[k], from: before[k].label, to: after[k].label }));
}

function renderChanges() {
  const { el, state } = ui;
  const ch = state.changes;
  if (!ch) return null;
  const name = state.current?.name || "this policy";
  if (!ch.textChanged) return el("div", { class: "changes same" }, el("strong", {}, `No changes since you checked ${name} on ${dateText(ch.since)}.`));
  return el("div", { class: "changes" },
    el("strong", {}, `${name} changed since you checked it on ${dateText(ch.since)}.`),
    ch.verdicts.length
      ? el("ul", {}, ch.verdicts.map((v) => el("li", {}, `${v.title}: `, el("s", {}, v.from), " → ", el("b", {}, v.to))))
      : el("p", {}, "The wording changed, but all 8 answers are the same."));
}

function renderSaveRow() {
  const { el, state } = ui;
  const cur = state.current;
  if (!cur) return null;  // Still saving.
  if (!cur.saved) return el("p", { class: "save-row fine save-failed", role: "status" }, "This check couldn't be saved to your dashboard. Your earlier work is safe; check this policy again to retry.");
  return el("p", { class: "save-row fine" }, `✓ Saved to your dashboard${state.store.mode === "account" ? "" : " in this browser"}. Your choice and ticked steps save as you go. `,
    el("a", { href: "dashboard.html" }, "Open dashboard"));
}

async function save() {
  const { state } = ui;
  const cur = state.current;
  const r = report();
  if (!cur || !r || !state.store || state.store.mode === "guest") return;
  // If saved work couldn't be loaded, writing now could replace it. Leave it alone.
  if (state.savedLoadFailed) return;
  const now = new Date().toISOString();
  cur.name = (cur.name || "").trim() || r.company || `Untitled policy, ${dateText(now)}`;
  const id = cur.id || (r.company ? policyId(r.company) : `untitled-${Date.now()}`);
  const old = state.saved?.[id];
  const changed = old && old.fingerprint !== cur.fingerprint;
  const doc = {
    name: cur.name, url: (cur.url || "").trim(), checkedAt: now, savedAt: old?.savedAt || now, fingerprint: cur.fingerprint,
    verdicts: verdictsOf(r), decision: state.decision || null, done: state.done || {}, stepsTotal: r.steps.length, report: r,
    history: changed ? [{ checkedAt: old.checkedAt, fingerprint: old.fingerprint, verdicts: old.verdicts }, ...(old.history || [])].slice(0, HISTORY_LIMIT) : old?.history || [],
  };
  try {
    await state.store.putPolicy(id, doc);
    state.saved = { ...(state.saved || {}), [id]: doc };
    Object.assign(cur, { id, saved: true });
  } catch (error) {
    console.warn("Couldn't save this check:", error?.code || error?.message || error);
  }
}

function autosave(patch) {
  const { state } = ui;
  const cur = state.current;
  if (!cur?.saved || !cur.id) return;
  state.saved[cur.id] = { ...state.saved[cur.id], ...patch };
  state.store.putPolicy(cur.id, patch).catch(() => ui.setStatus("Couldn't save that change.", "error"));
}

export async function loadSaved() {
  const { state } = ui;
  state.saved = {};
  if (!state.store || state.store.mode === "guest") return;
  try {
    const list = await state.store.listPolicies();
    state.saved = Object.fromEntries(list.map(({ id, ...doc }) => [id, doc]));
  } catch { state.savedLoadFailed = true; }
}

/** dashboard.html -> app.html?recheck=id: paste the current text and see what changed. */
export function startRecheck(id) {
  const { state } = ui;
  const doc = state.saved?.[id];
  if (!doc) return ui.setStatus("That saved check isn't in your dashboard any more. You can start a new one here.", "error");
  state.recheck = id;
  const box = document.getElementById("policy");
  if (doc.url) { box.value = doc.url; box.dispatchEvent(new Event("input")); }
  box.focus();
  ui.setStatus(doc.url ? `Press “Check this policy” to read the current ${doc.name} policy. We'll show what changed since ${dateText(doc.checkedAt)}.`
    : `Paste the current ${doc.name} policy and press “Check this policy”. We'll show what changed since ${dateText(doc.checkedAt)}.`);
}

/** dashboard.html -> app.html?open=id: the saved report card and checklist, ready to carry on. */
export function openSaved(id) {
  const { el, state } = ui;
  const doc = state.saved?.[id];
  if (!doc) return ui.setStatus("That saved check isn't in your dashboard any more. You can start a new one here.", "error");
  if (!doc.report) return startRecheck(id);  // Saved before reports were kept.
  state.savedView = { id };
  state.result = { report: doc.report, coverage: {}, segments: [], faqs: {} };
  state.current = { id, name: doc.name, url: doc.url || "", fingerprint: doc.fingerprint, saved: true };
  state.decision = doc.decision || null; state.done = { ...(doc.done || {}) }; state.changes = null;
  document.getElementById("workspace").hidden = true;
  document.getElementById("intro").hidden = true;
  const banner = document.getElementById("saved-banner");
  banner.hidden = false;
  banner.replaceChildren(
    el("div", {}, el("strong", {}, doc.name), el("p", { class: "fine" }, `Saved work, last checked ${dateText(doc.checkedAt)}. Your changes here save automatically.`)),
    el("div", { class: "saved-actions" },
      el("a", { class: "btn", href: `app.html?recheck=${encodeURIComponent(id)}` }, "Check the latest version"),
      el("a", { class: "btn btn-primary", href: "app.html" }, "Start a new check")));
  ui.showResults();
}
