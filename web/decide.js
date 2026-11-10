// What to do about a policy: the reader's own priorities, a neutral decision bar, a checklist of steps the
// policy itself offers (opt-out links, pre-written emails to its privacy address), and saving it all to an
// account so the next check shows what changed. Inkwell states facts; the reader decides what matters.
import { fingerprint, policyId } from "./store.js";

// The things a reader can say matter to them, one per report-card check (same ids).
export const PRIORITIES = [
  ["sale", "Selling my data"], ["ads", "Targeted ads"], ["sharing", "Sharing with other companies"],
  ["location", "My location"], ["retention", "How long they keep my data"], ["delete", "Being able to delete my data"],
  ["optout", "Being able to opt out"], ["changes", "Hearing about policy changes"],
];
const PRIORITY_LABEL = Object.fromEntries(PRIORITIES);
const DECISIONS = { steps: "Taking the steps", agree: "Agreed", leave: "Not for me" };

let ui;  // { state, el, plural, select, signupUrl, refresh, setStatus }
export function initDecide(context) { ui = context; }

const report = () => ui.state.result?.report;
const company = () => ui.state.current?.name || report()?.company || "the company";
const dateText = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");

/* ---------- Priorities ---------- */

export async function loadPriorities() {
  try { ui.state.priorities = await ui.state.store.getPriorities(); } catch { ui.state.priorities = null; }
}

function prioritiesEditor(inline) {
  const { el, state } = ui;
  const picked = new Set(state.draftPriorities ?? state.priorities ?? []);
  const chips = PRIORITIES.map(([id, label]) => el("button", {
    type: "button", class: "prio-chip", "aria-pressed": String(picked.has(id)),
    onclick: (e) => {
      picked.has(id) ? picked.delete(id) : picked.add(id);
      state.draftPriorities = [...picked];
      e.currentTarget.setAttribute("aria-pressed", String(picked.has(id)));
    },
  }, label));
  return el("div", { class: `prio-editor${inline ? " inline" : ""}` },
    el("p", { class: "prio-q" }, inline ? "What matters to you? Pick any. We'll point these out in every policy you check." : "What matters to you?"),
    el("div", { class: "prio-chips", role: "group", "aria-label": "Your priorities" }, chips),
    el("div", { class: "prio-actions" },
      el("button", { type: "button", class: "btn btn-primary", onclick: savePriorities }, "Save my priorities"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.editingPriorities = false; state.skipPriorities = true; state.draftPriorities = null; ui.refresh(); } },
        inline ? "Not now" : "Cancel")),
    el("p", { class: "fine" }, state.store?.mode === "account" ? "Saved to your account." : "Saved in this browser."));
}

async function savePriorities() {
  const { state } = ui;
  state.priorities = state.draftPriorities ?? state.priorities ?? [];
  state.draftPriorities = null; state.editingPriorities = false;
  ui.refresh();
  try { await state.store.setPriorities(state.priorities); } catch { ui.setStatus("Couldn't save your priorities. They'll apply until you leave this page.", "error"); }
}

/* ---------- Decision bar ---------- */

export function renderDecision() {
  const { el, state, plural } = ui;
  const r = report();
  if (!r?.concerns) return null;
  const mine = state.priorities;
  const relevant = mine?.length ? r.concerns.filter((c) => mine.includes(c.id)) : r.concerns;
  const fixable = relevant.filter((c) => c.fixable).length;
  const unclear = r.checks.filter((c) => c.applies == null && (!mine?.length || mine.includes(c.id)));
  const stepCount = r.steps.length;

  const headline = mine?.length
    ? relevant.length
      ? `This policy allows ${relevant.length} of the ${plural(mine.length, "thing")} you said matter to you.`
      : `None of the ${plural(mine.length, "thing")} you said matter to you came up as allowed in this policy.`
    : relevant.length
      ? `This policy allows ${relevant.length} of the 8 practices we check.`
      : "This policy doesn't allow any of the 8 practices we check, as far as the text says.";
  const split = relevant.length
    ? [fixable ? `${fixable} you can switch off with steps from the policy` : "None can be switched off with steps from the policy",
       relevant.length - fixable ? `${relevant.length - fixable} come${relevant.length - fixable === 1 ? "s" : ""} with using the service` : null].filter(Boolean).join(" · ")
    : null;

  const others = mine?.length ? r.concerns.filter((c) => !mine.includes(c.id)) : [];
  const decision = state.decision;
  return el("section", { class: "decision", "aria-label": "Your decision" },
    renderChanges(),
    el("div", { class: "decision-head" },
      el("p", { class: "eyebrow" }, "Before you agree"),
      el("button", { type: "button", class: "link edit-prio", onclick: () => { state.editingPriorities = !state.editingPriorities; ui.refresh(); } },
        mine?.length ? "Edit what matters to me" : "Choose what matters to me")),
    state.editingPriorities ? prioritiesEditor(false) : null,
    el("h3", { class: "decision-title" }, headline),
    split ? el("p", { class: "decision-split" }, split) : null,
    relevant.length ? el("ul", { class: "concerns" }, relevant.map((c) => el("li", { class: `concern ${c.fixable ? "fixable" : "stays"}` },
      el("button", { type: "button", class: "concern-name", onclick: () => focusCheck(c.id) }, c.title),
      el("span", { class: "concern-tag" }, c.fixable ? "You can switch this off" : "Comes with the service")))) : null,
    unclear.length ? el("p", { class: "fine" }, `${plural(unclear.length, "practice")} ${unclear.length === 1 ? "isn't" : "aren't"} settled by the text: ${unclear.map((c) => (PRIORITY_LABEL[c.id] || c.title).toLowerCase()).join(", ")}.`) : null,
    others.length ? el("p", { class: "fine" }, `Also allowed, not on your list: ${others.map((c) => c.title.toLowerCase()).join(", ")}.`) : null,
    mine == null && !state.skipPriorities && !state.editingPriorities ? prioritiesEditor(true) : null,
    el("div", { class: "decision-actions", role: "group", "aria-label": "What do you want to do?" },
      stepCount ? choice("steps", fixable ? `Take the ${plural(fixable, "step")}` : `See ${plural(stepCount, "step")} you can take`) : null,
      choice("agree", "Agree anyway"),
      choice("leave", "Not for me")),
    decision ? decisionNote(decision) : null,
    renderSaveRow());
}

function choice(id, label) {
  const { el, state } = ui;
  return el("button", { type: "button", class: "btn btn-lg decision-btn", "aria-pressed": String(state.decision === id),
    onclick: () => decide(id) }, label);
}

function decide(id) {
  const { state } = ui;
  state.decision = state.decision === id ? null : id;
  ui.refresh();
  autosave({ decision: state.decision });
  if (state.decision === "steps") document.getElementById("steps")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function decisionNote(decision) {
  const { el, state } = ui;
  const del = report().steps.find((s) => s.id === "request_delete");
  if (decision === "agree") return el("p", { class: "decision-note" }, "Noted. The steps below stay here if you change your mind.");
  if (decision === "steps") return el("p", { class: "decision-note" }, "Your steps are below. Tick them off as you go.");
  return el("div", { class: "decision-note" },
    el("p", {}, `Already have an account with ${company()}? You can ask them to delete your data.`),
    del ? el("button", { type: "button", class: "btn", onclick: () => { state.openRequest = "request_delete"; ui.refresh(); document.getElementById("step-request_delete")?.scrollIntoView({ behavior: "smooth", block: "center" }); } },
      "Write the deletion request") : el("p", { class: "fine" }, "The policy doesn't give a privacy email address. Look for a privacy or account-deletion page on their website."));
}

function focusCheck(id) {
  const node = document.getElementById(`check-${id}`);
  if (!node) return;
  node.scrollIntoView({ behavior: "smooth", block: "center" });
  node.classList.remove("flash"); void node.offsetWidth; node.classList.add("flash");
}

/* ---------- Steps ---------- */

export function renderSteps() {
  const { el, state, plural } = ui;
  const r = report();
  if (!r?.steps) return null;
  const helps = (stepId) => r.concerns.filter((c) => c.steps.includes(stepId)).map((c) => c.title.toLowerCase());
  const done = state.done || {};
  const doneCount = r.steps.filter((s) => done[s.id]).length;
  const head = el("div", { class: "steps-head" }, el("h3", {}, "Your steps"),
    r.steps.length ? el("span", { class: "steps-progress" }, `${doneCount} of ${r.steps.length} done`) : null);
  if (!r.steps.length) {
    return el("section", { class: "steps", id: "steps" }, head,
      el("p", { class: "note" }, "This policy doesn't give opt-out links or a privacy email in the text you pasted. Look for “Your Privacy Choices” or “Do Not Sell” in the footer of their website."));
  }
  if (state.guest) {
    return el("section", { class: "steps", id: "steps" }, head,
      el("ul", { class: "step-list" }, r.steps.map((s) => el("li", { class: "step locked" },
        el("span", { class: "step-box", "aria-hidden": "true" }, "🔒"),
        el("div", {}, el("strong", {}, s.title), helps(s.id).length ? el("p", { class: "step-helps" }, `Helps with: ${helps(s.id).join(", ")}`) : null)))),
      ui.lockCta(`Create a free account to get the ${plural(r.steps.length, "link")} and ready-to-send emails, and to save your checklist.`, "Get my steps"));
  }
  return el("section", { class: "steps", id: "steps" }, head,
    el("ul", { class: "step-list" }, r.steps.map((s) => stepItem(s, helps(s.id), !!done[s.id]))),
    el("p", { class: "fine" }, "Requests are templates, not legal advice. Nothing is sent unless you send it from your own email."));
}

function stepItem(step, helps, checked) {
  const { el, state } = ui;
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
  }
  return el("li", { class: `step${checked ? " done" : ""}`, id: `step-${step.id}` },
    el("input", { type: "checkbox", class: "step-box", checked, "aria-label": `Done: ${step.title}`, onchange: (e) => tick(step.id, e.target.checked) }),
    el("div", { class: "step-body" },
      el("div", { class: "step-top" }, el("strong", {}, step.title),
        step.source === "general" ? el("span", { class: "step-src" }, "General advice") : null,
        step.segment_id != null ? el("button", { type: "button", class: "found-in", onclick: () => ui.select(step.segment_id) }, "Where the policy says this") : null),
      helps.length ? el("p", { class: "step-helps" }, `Helps with: ${helps.join(", ")}`) : null,
      body));
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

/* ---------- Saving, My policies and what changed ---------- */

const verdictsOf = (r) => Object.fromEntries(r.checks.map((c) => [c.id, { state: c.state, label: c.label }]));

/** After each check: fingerprint the text, find a saved copy of this policy and work out what changed. */
export async function afterAnalysis(text) {
  const { state } = ui;
  const r = report();
  const fp = await fingerprint(text).catch(() => null);
  const saved = state.saved || {};
  const id = state.recheck || (r.company && saved[policyId(r.company)] ? policyId(r.company) : null);
  const prior = id ? saved[id] : null;
  state.current = { id: prior ? id : null, name: prior?.name || r.company || "", url: prior?.url || "", fingerprint: fp, saved: false, prior };
  state.decision = null; state.done = {}; state.openRequest = null;
  if (prior) {
    state.changes = { since: prior.checkedAt, textChanged: prior.fingerprint !== fp, verdicts: diff(prior.verdicts || {}, verdictsOf(r)) };
    // Steps you already took stay ticked; a changed policy needs a fresh decision.
    const stillThere = new Set(r.steps.map((st) => st.id));
    state.done = Object.fromEntries(Object.entries(prior.done || {}).filter(([k, v]) => v && stillThere.has(k)));
    state.decision = prior.fingerprint === fp ? prior.decision || null : null;
    if (state.recheck) await save();  // Re-checking a saved policy updates it, keeping the previous result.
  } else {
    state.changes = null;
  }
  state.recheck = null;
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
      : el("p", {}, "The wording changed, but all 8 answers are the same."),
    !state.current.saved && state.store?.mode !== "guest"
      ? el("button", { type: "button", class: "btn", onclick: save }, "Update my saved copy") : null);
}

function renderSaveRow() {
  const { el, state } = ui;
  if (state.guest || state.store?.mode === "guest") {
    return el("p", { class: "save-row fine" }, el("a", { href: ui.signupUrl() }, "Create a free account"), " to save your checklist and see what changes the next time you check this policy.");
  }
  const cur = state.current || {};
  const where = state.store.mode === "account" ? "your account" : "this browser";
  if (cur.saved) {
    return el("p", { class: "save-row fine" }, `✓ Saved to ${where} as “${cur.name}”. Your choice and ticked steps save automatically.`,
      state.store.fallback ? " (Your account storage isn't set up yet, so this stays on this device.)" : null);
  }
  if (state.saving) {
    return el("form", { class: "save-form", onsubmit: (e) => { e.preventDefault(); save(); } },
      el("label", { class: "request-field" }, "Name", el("input", { class: "input", required: true, maxlength: "80", value: cur.name || "",
        oninput: (e) => { cur.name = e.target.value; } })),
      el("label", { class: "request-field" }, "Link to the policy (optional)", el("input", { class: "input", type: "url", placeholder: "https://…", value: cur.url || "",
        oninput: (e) => { cur.url = e.target.value; } })),
      el("div", { class: "request-actions" }, el("button", { class: "btn btn-primary", type: "submit" }, "Save"),
        el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.saving = false; ui.refresh(); } }, "Cancel")),
      el("p", { class: "fine" }, "We save the name, the 8 answers, your choice, your ticked steps and a fingerprint of the text to spot changes. Never the policy text."));
  }
  return el("div", { class: "save-row" }, el("button", { type: "button", class: "btn", onclick: () => { state.saving = true; ui.refresh(); } }, "Save to My policies"),
    el("span", { class: "fine" }, "See what changed next time you check it."));
}

async function save() {
  const { state } = ui;
  const cur = state.current;
  const r = report();
  if (!cur || !r) return;
  cur.name = (cur.name || "").trim() || r.company || "Untitled policy";
  const id = cur.id || policyId(cur.name);
  const old = state.saved?.[id];
  const now = new Date().toISOString();
  const doc = {
    name: cur.name, url: (cur.url || "").trim(), checkedAt: now, savedAt: old?.savedAt || now, fingerprint: cur.fingerprint,
    verdicts: verdictsOf(r), decision: state.decision || null, done: state.done || {}, stepsTotal: r.steps.length,
    previous: old && old.fingerprint !== cur.fingerprint ? { checkedAt: old.checkedAt, fingerprint: old.fingerprint, verdicts: old.verdicts } : old?.previous || null,
  };
  try {
    await state.store.putPolicy(id, doc);
    state.saved = { ...(state.saved || {}), [id]: doc };
    Object.assign(cur, { id, saved: true });
    state.saving = false;
  } catch {
    ui.setStatus("Couldn't save. Check your connection and try again.", "error");
  }
  ui.refresh(); renderMyPolicies();
}

function autosave(patch) {
  const { state } = ui;
  const cur = state.current;
  if (!cur?.saved || !cur.id) return;
  state.saved[cur.id] = { ...state.saved[cur.id], ...patch };
  state.store.putPolicy(cur.id, patch).then(renderMyPolicies).catch(() => ui.setStatus("Couldn't save that change.", "error"));
}

export async function loadSaved() {
  const { state } = ui;
  if (!state.store || state.store.mode === "guest") { state.saved = {}; return renderMyPolicies(); }
  try {
    const list = await state.store.listPolicies();
    state.saved = Object.fromEntries(list.map(({ id, ...doc }) => [id, doc]));
  } catch { state.saved = {}; }
  renderMyPolicies();
}

export function renderMyPolicies() {
  const { el, state } = ui;
  const box = document.getElementById("my-policies");
  if (!box) return;
  const items = Object.entries(state.saved || {}).sort((a, b) => (b[1].checkedAt || "").localeCompare(a[1].checkedAt || ""));
  box.hidden = !items.length;
  if (!items.length) return box.replaceChildren();
  box.replaceChildren(el("div", { class: "card-head" }, el("h2", {}, "My policies"),
    el("span", { class: "fine" }, state.store.mode === "account" ? "Saved to your account" : "Saved in this browser")),
  el("ul", { class: "saved-list" }, items.map(([id, doc]) => {
    const done = Object.values(doc.done || {}).filter(Boolean).length;
    return el("li", { class: "saved" },
      el("div", { class: "saved-main" }, el("strong", {}, doc.name),
        el("span", { class: "fine" }, [`Checked ${dateText(doc.checkedAt)}`, doc.decision ? DECISIONS[doc.decision] : null,
          doc.stepsTotal ? `${done} of ${doc.stepsTotal} steps done` : null].filter(Boolean).join(" · "))),
      el("div", { class: "saved-actions" },
        doc.url && /^https?:\/\//i.test(doc.url) ? el("a", { class: "btn btn-ghost", href: doc.url, target: "_blank", rel: "noopener noreferrer nofollow" }, "Open policy ↗") : null,
        el("button", { type: "button", class: "btn", onclick: () => startRecheck(id, doc) }, "Check again"),
        el("button", { type: "button", class: "btn btn-ghost", "aria-label": `Remove ${doc.name}`, onclick: () => remove(id, doc) }, "Remove")));
  })));
}

function startRecheck(id, doc) {
  ui.state.recheck = id;
  const box = document.getElementById("policy");
  box.value = ""; box.dispatchEvent(new Event("input"));
  box.focus(); box.scrollIntoView({ behavior: "smooth", block: "center" });
  ui.setStatus(`Paste the current ${doc.name} policy and press “Check this policy”. We'll show what changed since ${dateText(doc.checkedAt)}.`);
}

async function remove(id, doc) {
  if (!confirm(`Remove ${doc.name} from My policies?`)) return;
  try {
    await ui.state.store.deletePolicy(id);
    delete ui.state.saved[id];
    if (ui.state.current?.id === id) Object.assign(ui.state.current, { saved: false, id: null });
  } catch { ui.setStatus("Couldn't remove it. Try again.", "error"); }
  renderMyPolicies();
  if (ui.state.result) ui.refresh();
}
