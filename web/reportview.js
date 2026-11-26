// The report, one job per tab: Overview (the whole picture and one next step), Fix (a queue, one fix at a time),
// Proof (every answer with its sentence, shown in its paragraph), Map (where your data goes) and Full policy.
// On phones the tabs scroll, a translucent bar always offers the next fix, and proof opens in a bottom sheet.
// The logic (steps, ticking, requests, saving, the exposure count) stays in decide.js; this file only lays it out.
import { el } from "./shared.js";
import { forYou, glossify } from "./words.js";
import { exposureCells } from "./visuals.js";
import { classify, orbitSvg, readDataFlows } from "./orbit.js";
import { bestStep, changeAnswer, company, dateText, decide, isLimited, minutesLeft, renderChanges, renderFocus, renderMap,
  report, requestEditor, speedOf, tick } from "./decide.js";

let v;  // { state, select(segmentId), rerender(), exportTxt(), exportJson(), signupUrl() }
export function initReportView(context) { v = context; }

const TONE = { bad: "red", unknown: "yellow", good: "green" };
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const mobile = () => matchMedia("(max-width: 760px)").matches;

/* ---------- Helpers ---------- */

/** Fixable concerns, the reader's priorities first, then the quickest. */
function fixables() {
  const mine = v.state.priorities || [];
  return (report()?.concerns || []).filter((c) => c.fixable)
    .sort((a, b) => Number(mine.includes(b.id)) - Number(mine.includes(a.id)) || (speedOf(bestStep(a) || {})[3] || 9) - (speedOf(bestStep(b) || {})[3] || 9));
}

/** The next thing to fix: { concern, step }, or null. */
export function nextFix() {
  const c = fixables().find((k) => !isLimited(k));
  return c ? { concern: c, step: bestStep(c) } : null;
}

/** The fix queue: concerns grouped by the step that limits them, then the other steps the policy offers. */
function queue() {
  const r = report(), done = v.state.done || {};
  const byStep = new Map();
  for (const c of fixables()) {
    const st = bestStep(c);
    if (!st) continue;
    if (!byStep.has(st.id)) byStep.set(st.id, { key: st.id, step: st, concerns: [] });
    byStep.get(st.id).concerns.push(c);
  }
  const main = [...byStep.values()].map((q) => ({ ...q, label: q.concerns.map((c) => c.title).join(" · "), done: q.concerns.every(isLimited) }));
  const extras = (r.steps || []).filter((st) => !byStep.has(st.id)).map((st) => ({ key: st.id, step: st, concerns: [], label: st.title, done: !!done[st.id], extra: true }));
  return { main, extras };
}

const speedPill = (st) => {
  const sp = speedOf(st);
  return el("span", { class: `fix-speed ${sp[0]}` }, `${sp[1]} · ${sp[2]}`);
};

function citeButton(segmentId, on, onclick) {
  return el("button", { type: "button", class: `cite${on ? " on" : ""}`, title: `Paragraph ${segmentId + 1}`, onclick }, `¶${segmentId + 1}`);
}

/* ---------- Header and tabs ---------- */

export function tabsFor() {
  const { state } = v;
  if (state.guest) return [["policy", "Full policy"]];
  const r = report();
  if (!r) return [["policy", "Full policy"]];
  const open = (r.concerns || []).filter((c) => c.fixable && !isLimited(c)).length;
  const flows = r.dataFlows || (state.result?.segments?.length ? readDataFlows(state.result.segments) : null);
  return [["overview", "Overview"], ["fix", open ? `Fix · ${open}` : "Fix"], ["proof", "Proof"],
    flows?.recipients?.length ? ["map", "Map"] : null, state.savedView ? null : ["policy", "Full policy"]].filter(Boolean);
}

export function renderHead() {
  const { state } = v;
  const r = report();
  const name = state.current?.name || r?.company || r?.title || "Your policy";
  const url = state.current?.url || state.source?.url || "";
  const when = state.savedView ? `last checked ${dateText(state.savedView.checkedAt)}` : "checked just now";
  const tabs = tabsFor();
  const saved = state.current && !state.guest
    ? (state.current.saved ? el("span", { class: "pill p-ok" }, `✓ Saved to your dashboard${state.store?.mode === "account" ? "" : " in this browser"}`)
      : el("span", { class: "pill p-warn" }, "Not saved: check again to retry")) : null;
  const exportMenu = el("details", { class: "rv-export" }, el("summary", { class: "btn btn-ghost" }, "⇩ Export"),
    el("div", { class: "rv-export-menu", role: "menu" },
      el("button", { type: "button", role: "menuitem", id: "dl-txt", onclick: (e) => { e.target.closest("details").open = false; v.exportTxt(); } }, "Report (.txt)"),
      state.savedView ? null : el("button", { type: "button", role: "menuitem", id: "dl-json", onclick: (e) => { e.target.closest("details").open = false; v.exportJson(); } }, "Raw data (.json)")));
  const tablist = el("div", { class: "rv-tabs", role: "tablist", "aria-label": "Report sections" }, tabs.map(([id, label]) =>
    el("button", { type: "button", role: "tab", "data-rtab": id, id: `rtab-${id}`, "aria-selected": String(state.rtab === id), "aria-controls": "rv-panel",
      tabindex: state.rtab === id ? "0" : "-1", onclick: () => setTab(id), onkeydown: tabKeys }, label)));
  return el("header", { class: "rv-head" },
    el("div", { class: "rv-top" }, el("span", { class: "rv-eyebrow" }, state.guest ? "Free check" : "Report"), saved),
    el("div", { class: "rv-title" },
      el("h1", {}, name),
      el("span", { class: "rv-meta" }, [url.replace(/^https?:\/\//i, "").replace(/\/$/, ""), when].filter(Boolean).join(" · ")),
      el("div", { class: "rv-actions" },
        state.guest ? null : el("a", { class: "btn btn-ghost", href: "compare.html" }, "⇄ Compare"),
        state.guest ? null : exportMenu,
        state.savedView ? el("a", { class: "btn btn-ghost", href: `app.html?recheck=${encodeURIComponent(state.savedView.id)}` }, "↻ Check latest") : null,
        el("a", { class: "btn btn-primary", href: "app.html" }, "＋ New check"))),
    tabs.length > 1 ? tablist : null);
}

function tabKeys(e) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  const ids = tabsFor().map(([id]) => id);
  let i = ids.indexOf(v.state.rtab);
  i = e.key === "Home" ? 0 : e.key === "End" ? ids.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length;
  setTab(ids[i]);
  document.getElementById(`rtab-${ids[i]}`)?.focus();
  e.preventDefault();
}

export function setTab(id, opts = {}) {
  const { state } = v;
  state.rtab = id;
  state.sheet = false;
  Object.assign(state, opts);
  v.rerender();
  const head = document.querySelector(".rv-head");
  if (head && head.getBoundingClientRect().top < 0) head.scrollIntoView({ block: "start" });
}

/** Opens the Fix tab, optionally on one step. */
export function openFix(stepId) { setTab("fix", stepId ? { fixPick: stepId } : {}); }

/* ---------- Overview ---------- */

function overview() {
  const { state } = v;
  const r = report();
  const cells = exposureCells(r, state.done);
  const count = (k) => cells.filter((c) => c.kind === k).length;
  const left = count("red"), fixed = count("fixed"), total = left + fixed;
  const fx = fixables(), next = nextFix(), mins = minutesLeft(r.concerns || []);
  const word = { red: "Worth knowing", fixed: "You limited it", yellow: "Not clearly answered", green: "In your favour" };
  const byId = Object.fromEntries(r.checks.map((c) => [c.id, c]));
  const proofRow = (check, cls, extra) => el("button", { type: "button", class: `ov-row ${cls}`, onclick: () => setTab("proof", { proofPick: check.id, proofCite: 0 }) },
    el("span", { class: `dot d-${cls}`, "aria-hidden": "true" }), el("span", { class: "ov-row-t" }, check.title), extra || null);

  const exposure = el("section", { class: "card tile tile-exposure", "aria-label": `Your exposure: ${left} of ${cells.length}` },
    el("h4", {}, "Your exposure"),
    el("div", { class: "tile-big" }, el("b", {}, String(left)), el("span", {}, `of ${cells.length} answers worth knowing`)),
    el("div", { class: "exp-cells", "aria-hidden": "true" }, cells.map((c) => el("i", { class: c.kind, title: `${c.title}: ${word[c.kind].toLowerCase()}` }))),
    el("p", { class: "tile-legend" }, ["red", "fixed", "yellow", "green"].filter((k) => count(k)).map((k) => el("span", {}, el("b", { class: `dot d-${k}` }), `${count(k)} ${word[k].toLowerCase()}`))),
    el("p", { class: "tile-fine" }, fixed ? el("span", { class: "win" }, `Down from ${total} to ${left}. `) : null,
      `It counts what the policy allows and what you've changed; it isn't a rating of ${company()}.`));

  let nextTile;
  if (next) {
    const sp = speedOf(next.step);
    nextTile = el("section", { class: "card tile tile-next" },
      el("h4", {}, fx.length > 1 ? `Fix next · about ${mins} min for all ${fx.filter((c) => !isLimited(c)).length}` : "Fix next"),
      el("p", { class: "tile-next-t" }, next.concern.title),
      el("p", { class: "tile-next-s" }, `${next.step.title}. ${sp[1]}, ${sp[2].replace("~", "about ")}.`),
      el("button", { type: "button", class: "btn btn-light", onclick: () => openFix(next.step.id) }, fixed ? "Fix the next one →" : "Fix the first one →"));
  } else if (fx.length) {
    nextTile = el("section", { class: "card tile tile-next done" },
      el("h4", {}, "All limited"), el("p", { class: "tile-next-t" }, `✓ You limited ${plural(fx.length, "thing")}`),
      el("p", { class: "tile-next-s" }, `Your exposure went from ${total} to ${left}.${left ? " What's left comes with the service." : ""}`),
      el("button", { type: "button", class: "btn btn-light", onclick: () => openFix() }, "See your fixes"));
  } else {
    const steps = r.steps?.length;
    nextTile = el("section", { class: "card tile tile-next quiet" },
      el("h4", {}, "What you can do"),
      el("p", { class: "tile-next-t" }, total ? "Nothing here you can switch off" : "Nothing worth flagging"),
      el("p", { class: "tile-next-s" }, total ? "The policy gives no setting or link for what's worth knowing." + (steps ? " You can still send them a request." : "")
        : "None of the 8 key questions has an answer worth knowing."),
      steps ? el("button", { type: "button", class: "btn btn-light", onclick: () => openFix() }, "See what you can do") : null);
  }

  const red = r.checks.filter((c) => c.tone === "bad");
  const worth = el("section", { class: "card tile" }, el("h4", {}, "Worth knowing"),
    red.length ? red.map((c) => {
      const con = (r.concerns || []).find((k) => k.id === c.id);
      const lim = con && isLimited(con);
      return proofRow(c, lim ? "fixed" : "red", lim ? el("span", { class: "ov-tag ok" }, "✓ limited") : null);
    }) : el("p", { class: "tile-fine" }, "Nothing worth flagging."));

  const flows = r.dataFlows || (state.result?.segments?.length ? readDataFlows(state.result.segments) : null);
  let mapTile = null;
  if (flows?.recipients?.length) {
    const placed = classify(flows.recipients, r.concerns, isLimited);
    const art = el("div", { class: "tile-orbit", "aria-hidden": "true" });
    art.innerHTML = orbitSvg(placed, { company: company(), compact: true, id: "orb-tile" });  // Escaped inside orbitSvg.
    art.querySelectorAll("animateMotion").forEach((a) => a.parentElement.remove());
    const cut = placed.filter((f) => f.kind === "limit").length;
    mapTile = el("button", { type: "button", class: "card tile tile-map", onclick: () => setTab("map") },
      el("h4", {}, "Where your data goes"), art,
      el("span", { class: "tile-fine" }, `${placed.length} ${placed.length === 1 ? "kind of company gets" : "kinds of company get"} your data${cut ? ` · ${cut} you can cut` : ""} →`));
  }
  const yellow = r.checks.filter((c) => c.tone === "unknown"), green = r.checks.filter((c) => c.tone === "good");
  const also = el("section", { class: "card tile" },
    el("h4", {}, "Not clearly answered"),
    yellow.length ? yellow.map((c) => proofRow(c, "yellow")) : el("p", { class: "tile-fine" }, "Every question is answered."),
    green.length ? [el("h4", { class: "tile-h-gap" }, "In your favour"), ...green.map((c) => proofRow(c, "green", el("span", { class: "ov-tag" }, c.label)))] : null);

  return el("div", { class: "ov" },
    renderChanges(), renderFocus(),
    el("div", { class: `bento${mapTile ? "" : " no-map"}` }, exposure, nextTile, worth, mapTile, also),
    decideRow(),
    glossNote());
}

function glossNote() {
  return el("p", { class: "rv-note" }, report().limitation || "");
}

function decideRow() {
  const { state } = v;
  if (state.decision) {
    const text = { steps: "You chose to limit this.", agree: "You chose to accept this policy as it is.", leave: "You chose not to accept this policy." }[state.decision];
    const del = state.decision === "leave" && report().steps.find((s) => s.id === "request_delete");
    return el("div", { class: "decide-row decided", role: "status" }, el("span", {}, `✓ ${text}`),
      del ? el("button", { type: "button", class: "btn btn-ghost", onclick: () => openFix("request_delete") }, "Ask them to delete your data") : null,
      el("button", { type: "button", class: "link", onclick: changeAnswer }, "Change my answer"));
  }
  return el("div", { class: "decide-row" },
    el("span", {}, "Made up your mind? ", el("span", { class: "fine" }, "Only for your own records; Inkwell never contacts the company.")),
    el("span", { class: "decide-btns" },
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => decide("agree") }, "Accept it as is"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => decide("leave") }, "Don't accept")));
}

/* ---------- Fix ---------- */

function fixTab() {
  const { state } = v;
  const r = report();
  const { main, extras } = queue();
  const all = [...main, ...extras];
  if (!all.length) {
    return el("div", { class: "card fix-empty" }, el("h3", {}, "Nothing to switch off here"),
      el("p", {}, "This policy doesn't give opt-out links, settings or a privacy email in the text we read. Look for “Your Privacy Choices” or “Do Not Sell” in the footer of their website."));
  }
  const pick = all.find((q) => q.key === state.fixPick) || main.find((q) => !q.done) || extras.find((q) => !q.done) || main[0] || extras[0];
  const fx = fixables(), limited = fx.filter(isLimited).length;
  const mins = minutesLeft(r.concerns || []);
  const C = 2 * Math.PI * 15, frac = fx.length ? limited / fx.length : 1;
  const ring = el("span", { class: "fix-ring", "aria-hidden": "true" });
  ring.innerHTML = `<svg viewBox="0 0 36 36" width="40" height="40"><circle cx="18" cy="18" r="15" fill="none" stroke="var(--surface-3)" stroke-width="5"/><circle cx="18" cy="18" r="15" fill="none" stroke="var(--success)" stroke-width="5" stroke-linecap="round" stroke-dasharray="${(C * frac).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 18 18)"/></svg>`;
  const item = (q, i) => el("li", {}, el("button", { type: "button", class: `fq-item${q === pick ? " on" : ""}${q.done ? " done" : ""}`, "aria-current": q === pick ? "true" : null,
    onclick: () => { state.fixPick = q.key; v.rerender(); if (mobile()) document.querySelector(".fix-card")?.scrollIntoView({ behavior: "smooth", block: "start" }); } },
    el("span", { class: "fq-num" }, q.done ? "✓" : String(i + 1)), el("span", { class: "fq-label" }, q.label),
    el("span", { class: "fq-time" }, q.done ? "done" : speedOf(q.step)[2])));
  const stays = (r.concerns || []).filter((c) => !c.fixable);
  const list = el("aside", { class: "card fix-queue", "aria-label": "Your fixes" },
    fx.length ? el("div", { class: "fq-head" }, ring, el("div", {}, el("b", {}, `${limited} of ${fx.length} limited`),
      el("small", {}, limited === fx.length ? "Nothing left to switch off" : `about ${mins} min left`))) : null,
    main.length ? el("ol", { class: "fq" }, main.map(item)) : null,
    extras.length ? [el("p", { class: "fq-group" }, main.length ? "More you can do" : "What you can do"), el("ol", { class: "fq" }, extras.map((q, i) => item(q, main.length + i)))] : null,
    stays.length ? el("p", { class: "fq-stays" }, el("b", {}, "Comes with the service: "), stays.map((c) => c.title.toLowerCase()).join(", "),
      ". No setting or request in the policy limits these.") : null);
  return el("div", { class: "fix-layout" }, list, fixCard(pick, main, extras));
}

function fixCard(q, main, extras) {
  const { state } = v;
  const st = q.step, r = report(), segments = state.result?.segments || [];
  const body = [];
  if (st.target?.kind === "url") body.push(el("a", { class: "btn step-go", href: st.target.value, target: "_blank", rel: "noopener noreferrer nofollow" }, `Open ${st.target.value.replace(/^https?:\/\//i, "").replace(/\/$/, "")} ↗`));
  else if (st.target?.kind === "settings") body.push(el("ol", { class: "fix-steps" }, el("li", {}, `Open the ${company()} app or website.`), el("li", {}, "Go to ", el("b", {}, st.target.value), " and switch it off.")));
  else if (st.target?.kind === "named_link") body.push(el("p", {}, "Look for ", el("b", {}, `“${st.target.value}”`), ", usually in the footer of their website or app."));
  if (st.detail) body.push(el("p", {}, st.detail));
  if (st.to) body.push(el("p", { class: "fine" }, "To: ", el("span", { class: "mono" }, st.to)), requestEditor(st),
    el("p", { class: "fine" }, "A template, not legal advice. Nothing is sent unless you send it from your own email."));
  const others = q.concerns.flatMap((c) => c.steps).filter((id, i, a) => id !== st.id && a.indexOf(id) === i).map((id) => r.steps.find((s) => s.id === id)).filter(Boolean);
  const order = [...main, ...extras];
  const nextKey = () => (order.slice(order.indexOf(q) + 1).find((x) => !x.done) || order.find((x) => !x.done && x !== q))?.key || q.key;
  const allDone = main.length && main.every((x) => x.done);
  return el("section", { class: "card fix-card", "aria-live": "polite" },
    allDone ? el("p", { class: "fix-all" }, `✓ Everything you can switch off is limited. ${extras.some((x) => !x.done) ? "There's more you can do in the list, if you want." : ""}`) : null,
    el("div", { class: "fix-pills" }, speedPill(st), st.source === "general" ? el("span", { class: "pill" }, "General advice") : null),
    q.concerns.length ? el("p", { class: "fix-for" }, "Limits: ", q.concerns.map((c) => c.title.toLowerCase()).join(" · ")) : el("p", { class: "fix-for" }, "Optional"),
    el("h2", {}, st.title),
    q.concerns.length ? el("p", { class: "fix-why" }, forYou(q.concerns[0].id, company())) : null,
    body,
    others.length ? el("p", { class: "fix-others" }, "Other ways: ", others.map((o) => el("button", { type: "button", class: "link", onclick: () => { state.fixPick = o.id; v.rerender(); } }, o.title))) : null,
    el("div", { class: "fix-actions" },
      q.done
        ? [el("span", { class: "fix-done" }, "✓ Done"), el("button", { type: "button", class: "btn btn-primary", onclick: () => { state.fixPick = nextKey(); v.rerender(); } }, "Next"),
           el("button", { type: "button", class: "link", onclick: () => { state.fixPick = q.key; tick(st.id, false); } }, "Mark as not done")]
        : [el("button", { type: "button", class: "btn btn-primary btn-lg", onclick: () => { state.fixPick = nextKey(); tick(st.id, true); } }, "✓ Done, show the next one"),
           el("button", { type: "button", class: "btn btn-lg", onclick: () => { state.fixPick = nextKey(); v.rerender(); } }, "Skip for now")],
      st.segment_id != null && segments[st.segment_id] ? el("button", { type: "button", class: "fix-cite", onclick: () => setTab("proof", { proofSegment: st.segment_id }) },
        "From the policy ", el("span", { class: "cite" }, `¶${st.segment_id + 1}`)) : null));
}

/* ---------- Proof ---------- */

function citations(check) {
  const seen = new Set();
  return (check.evidence || []).filter((e) => { const k = `${e.segment_id}|${e.text}`; if (seen.has(k)) return false; seen.add(k); return true; });
}

function proofTab() {
  const { state } = v;
  const r = report();
  const checks = r.checks;
  let pick = checks.find((c) => c.id === state.proofPick);
  if (!pick && state.proofSegment != null) {
    pick = checks.find((c) => c.evidence.some((e) => e.segment_id === state.proofSegment));
    if (pick) { state.proofPick = pick.id; state.proofCite = Math.max(0, citations(pick).findIndex((e) => e.segment_id === state.proofSegment)); }
    state.proofSegment = null;
  }
  pick ||= checks.find((c) => c.tone === "bad") || checks[0];
  const choose = (c, i = 0) => { state.proofPick = c.id; state.proofCite = i; state.sheet = mobile(); v.rerender(); };
  const rows = checks.map((c) => el("li", { class: `pf-row${c === pick ? " on" : ""}` },
    el("button", { type: "button", class: "pf-main", "aria-pressed": String(c === pick), onclick: () => choose(c) },
      el("span", { class: `dot d-${TONE[c.tone]}`, "aria-hidden": "true" }), el("span", { class: "pf-title" }, c.title),
      el("span", { class: `verdict v-${TONE[c.tone]}` }, c.label)),
    el("span", { class: "pf-cites" }, citations(c).map((e, i) => citeButton(e.segment_id, c === pick && (state.proofCite || 0) === i, () => choose(c, i))))));
  const pane = proofPane(pick);
  const sheet = state.sheet && mobile()
    ? el("div", { class: "sheet-back", onclick: (e) => { if (e.target.classList.contains("sheet-back")) { state.sheet = false; v.rerender(); } } },
      el("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": pick.title },
        el("span", { class: "sheet-grip", "aria-hidden": "true" }), proofPane(pick, true),
        el("button", { type: "button", class: "btn btn-block", onclick: () => { state.sheet = false; v.rerender(); } }, "Close")))
    : null;
  return el("div", { class: "proof-layout" }, el("ul", { class: "card pf-list", "aria-label": "The 8 answers" }, rows), pane, sheet);
}

function proofPane(check, inSheet = false) {
  const { state } = v;
  const segments = state.result?.segments || [];
  const cites = citations(check);
  const at = Math.min(state.proofCite || 0, Math.max(0, cites.length - 1));
  const e = cites[at];
  const concern = (report().concerns || []).find((c) => c.id === check.id);
  const fix = concern?.fixable && !isLimited(concern) ? bestStep(concern) : null;
  const all = report().checks.flatMap((c) => citations(c).map((_, i) => [c.id, i]));
  const pos = all.findIndex(([id, i]) => id === check.id && i === at);
  const move = (d) => { const [id, i] = all[(pos + d + all.length) % all.length]; state.proofPick = id; state.proofCite = i; v.rerender(); };
  let context = null;
  if (e && segments[e.segment_id]) {
    const seg = segments[e.segment_id];
    const para = (s, dim) => s ? el("p", { class: `pf-para${dim ? " dim" : ""}` }, el("span", { class: "pf-num" }, `¶${s.id + 1}`), " ", s.text) : null;
    let ls = e.start - seg.start, le = e.end - seg.start;
    if (!(ls >= 0 && le <= seg.text.length && seg.text.slice(ls, le) === e.text)) { ls = seg.text.indexOf(e.text); le = ls + e.text.length; }
    const cited = ls >= 0
      ? el("p", { class: "pf-para cited" }, el("span", { class: "cite on" }, `¶${seg.id + 1}`), " ", seg.text.slice(0, ls), el("mark", {}, seg.text.slice(ls, le)), seg.text.slice(le))
      : para(seg, false);
    context = [para(segments[seg.id - 1], true), cited, para(segments[seg.id + 1], true)];
  } else if (e) {
    context = el("blockquote", { class: "receipt plain-receipt" }, el("span", { class: "receipt-mark", "aria-hidden": "true" }, "“"), e.text);
  }
  const node = el("section", { class: `card proof-pane${inSheet ? " in-sheet" : ""}`, "aria-live": "polite" },
    el("p", { class: "pf-where" }, e && segments.length ? `${company()} privacy policy · paragraph ${e.segment_id + 1} of ${segments.length}` : `${company()} privacy policy`),
    el("div", { class: "pf-head" }, el("h3", {}, check.title), el("span", { class: `verdict v-${TONE[check.tone]}` }, check.label)),
    el("p", { class: "check-meaning" }, check.meaning),
    check.tone === "bad" && forYou(check.id, company()) ? el("div", { class: "for-you" }, el("b", {}, "For you, this means"), forYou(check.id, company())) : null,
    e ? el("div", { class: "pf-context" }, context)
      : el("p", { class: "pf-none" }, "We found no sentence about this. “Not mentioned” means our wording checks found nothing; it isn't proof either way."),
    check.counter?.length ? el("div", { class: "counter" }, el("span", {}, "But the policy also says:"), el("blockquote", { class: "receipt plain-receipt" }, check.counter[0].text)) : null,
    el("div", { class: "pf-nav" },
      all.length > 1 ? [el("button", { type: "button", class: "btn btn-ghost", onclick: () => move(-1) }, "↑ Previous citation"),
        el("button", { type: "button", class: "btn btn-ghost", onclick: () => move(1) }, "Next citation ↓")] : null,
      fix ? el("button", { type: "button", class: "btn btn-primary", onclick: () => openFix(fix.id) }, "✂ Fix it") : null,
      e && segments[e.segment_id] && !inSheet ? el("button", { type: "button", class: "link", onclick: () => v.select(e.segment_id) }, "Open in the full policy") : null));
  return node;
}

/* ---------- Map ---------- */

function mapTab() {
  return el("div", { class: "map-tab" }, renderMap());
}

/* ---------- The panel and the phone's sticky next step ---------- */

export function renderPanel() {
  const { state } = v;
  const r = report();
  if (!r || state.guest) return null;
  const node = { overview, fix: fixTab, proof: proofTab, map: mapTab }[state.rtab]?.() || null;
  return node;
}

export function renderFixbar() {
  const { state } = v;
  const next = !state.guest && report() ? nextFix() : null;
  if (!next || state.rtab === "fix") return null;
  const sp = speedOf(next.step);
  return el("div", { class: "fixbar", role: "region", "aria-label": "Your next fix" },
    el("div", {}, el("b", {}, `Fix next: ${next.concern.title}`), el("small", {}, `${sp[1]} · ${sp[2]}`)),
    el("button", { type: "button", class: "btn btn-primary", onclick: () => openFix(next.step.id) }, "Fix →"));
}

export function gloss(root) {
  glossify(root, ".check-meaning, .for-you, .pf-para.cited, .fix-why", company());
}
