// The guided tour. Each page has its own short tour (3 to 7 stops) that explains what the parts of that page do.
// It never clicks anything for you and never jumps to another page on its own.
// Back / Next move between stops (the arrow keys work too). ✕ or Esc closes the tour; your place is kept, so the Tour button
// offers to carry on from that stop or start again. The checker has two tours: one for the paste screen and one for a report.

const KEY = "inkwell-tour-v2", SEEN = "inkwell-tour-seen";
const $ = (s) => document.querySelector(s);
const visible = (n) => !!n && n.getClientRects().length > 0 && getComputedStyle(n).visibility !== "hidden";
const click = (s) => $(s)?.click();

/** Stops for each page. target: what the stop points at. before: shows the right tab first. account / signedOut: who sees it. */
const TOURS = {
  home: { name: "the home page", stops: [
    { target: ".hero h1", title: "What Inkwell does",
      text: "Inkwell reads a privacy policy and tells you what it lets the company do with your data. Each answer quotes the sentence it comes from." },
    { target: ".hero-ctas [data-cta]", title: "Start a check",
      text: "This opens the checker. Paste a link to any privacy policy, or try the sample policy we provide." },
    { target: "#checks .check-grid", title: "The 8 questions",
      text: "Every check answers the same 8 questions, such as “Do they sell my data?” and “Can I delete it?”." },
    { target: ".nav-links", title: "Learn more",
      text: "Features explains each part of Inkwell. Resources has short guides on selling, sharing and deleting your data." },
    { target: "#nav-signin", title: "A free account", signedOut: true,
      text: "An account is free. It saves your checks and writes opt-out emails for you. You can try a check without one." },
  ], next: { label: "Open the checker", href: "app.html" } },

  app: { name: "the checker", stops: [
    { target: ".shell-nav", title: "Getting around",
      text: "This menu goes to every part of Inkwell. Close it with ✕ for more room, and bring it back with ☰." },
    { target: "#policy", title: "Paste the policy here",
      text: "Paste a link to a company's privacy policy, or the policy text itself. A link usually works best." },
    { target: "#sample", title: "No policy to hand?",
      text: "This fills the box with Pigeonpost, a made-up app, so you can see what a report looks like." },
    { target: "#run", title: "Run the check",
      text: "Inkwell reads every paragraph and answers 8 questions, in under a minute. Once the report appears, press Tour again to learn how to read it." },
    { target: ".shell-search", title: "Search from anywhere",
      text: "Press Ctrl K (⌘K on a Mac) to check a site or reopen an earlier report from any page." },
  ] },

  report: { name: "your report", stops: [
    { target: ".rv-tabs", title: "Five tabs",
      text: "Overview is the summary. Fix lists what you can change. Proof shows the sentences. Map shows who gets your data. Full policy is the whole text." },
    { target: ".tile-exposure", before: () => click("#rtab-overview"), title: "Your exposure",
      text: "How many of the 8 answers are worth knowing about. Red is worth knowing, yellow means the policy isn't clear, green is in your favour. It goes down as you fix things." },
    { target: ".tile-next", before: () => click("#rtab-overview"), title: "What to do first",
      text: "The quickest change you can make, and roughly how long it takes. The button opens its steps." },
    { target: ".fix-layout", before: () => click("#rtab-fix"), title: "The Fix tab",
      text: "Each fix has short steps. When you've done one, mark it as done and the next one opens. Requests to the company are written for you." },
    { target: ".proof-layout", before: () => click("#rtab-proof"), title: "The Proof tab",
      text: "Each answer shows the paragraph it comes from, with the exact sentence highlighted. Words with a dotted underline have a short explanation." },
    { target: ".map-tab .dmap", before: () => click("#rtab-map"), title: "The Map tab",
      text: "Everyone the policy says gets your data. Red lines are ones you can limit. Tap a name to read the sentence." },
    { target: ".decide-row", before: () => click("#rtab-overview"), title: "Your decision",
      text: "When you've made up your mind, note it here for your own records. Inkwell never contacts the company." },
    { target: ".guest-offer", title: "The full report", signedOut: true,
      text: "A free check shows the topics and the full text. A free account adds the answers, the fixes and a dashboard." },
  ] },

  dashboard: { name: "your dashboard", stops: [
    { target: ".deck", title: "Your saved checks",
      text: "Each card is a policy you've checked. Flip through them with the arrows, a swipe, or two fingers on a trackpad." },
    { target: ".dash-filters", title: "Filters",
      text: "Needs action shows checks with fixes left. Policy changed lists companies whose policy is different since you checked." },
    { target: "#dash-list", title: "Pick up where you left off",
      text: "Fix next opens a report on its next fix. The ⋯ menu lets you check a policy again, rename it or remove it." },
  ] },

  compare: { name: "Compare", stops: [
    { target: "#box-a", title: "First company",
      text: "Paste a link to the first company's privacy policy, or its text." },
    { target: "#box-b", title: "Second company",
      text: "Do the same for the company you want to compare it with." },
    { target: "#compare", title: "See the differences",
      text: "Inkwell lists where the two policies differ first, with the sentences side by side. It doesn't pick a winner." },
  ] },

  map: { name: "the data map", stops: [
    { target: ".dmap", title: "The map",
      text: "The company sits in the middle. Everyone the policy says gets your data is placed around it." },
    { target: ".dmap-list, .dmap-side, .dmap-body > :last-child", title: "Tap a name",
      text: "Pick any name to read the sentence that mentions it. If you can limit it, Fix it shows you how." },
    { target: ".dmp-legend, .dmp-grid", title: "Reading the lines",
      text: "Red lines you can limit, grey lines come with the service, and dashed lines only happen in some cases." },
  ] },

  reviews: { name: "Reviews", stops: [
    { target: ".rvp-score", title: "Ratings",
      text: "Ratings from people who checked a policy with Inkwell. We don't edit them or hide low scores." },
    { target: ".rvp-score .btn", title: "Leave a review",
      text: "Checked a policy? Tell others how it went. Half stars count." },
  ] },

  guides: { name: "Guides", stops: [
    { target: "#gd-goals", title: "Choose what you want",
      text: "Pick a goal, such as deleting your data, and the guide shows the topics that matter for it." },
    { target: ".gd-map", title: "Topics",
      text: "Each circle is a topic. Open one to see what policies usually say about it, and how Inkwell helps." },
  ] },
};

let ctx = { signedIn: false }, run = null, ui = null, raf = 0;

/** Which tour fits what's on screen now. The checker has one tour before a check and another once a report is showing. */
function tourKey() {
  const p = location.pathname;
  if (p === "/" || p.endsWith("/index.html")) return "home";
  if (p.endsWith("/app.html")) return $("#results:not([hidden]) .rv-head") || $("#results:not([hidden]) .guest-offer") ? "report" : "app";
  for (const k of ["dashboard", "compare", "reviews", "guides"]) if (p.endsWith(`/${k}.html`)) return k;
  if (p.endsWith("/data-map.html")) return "map";
  return null;
}
const allowed = (s) => !(s.account && !ctx.signedIn) && !(s.signedOut && ctx.signedIn);
// Only stops that are on this screen count, so "Stop 1 of 3" is always true. Stops behind a tab (before) are kept.
const onScreen = (s) => !!s.before || [...document.querySelectorAll(s.target)].some(visible);
const stopsFor = (key) => (TOURS[key]?.stops || []).filter((s) => allowed(s) && onScreen(s));

const loadPlaces = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
const savePlace = (key, i) => { const all = loadPlaces(); if (i == null) delete all[key]; else all[key] = i; try { localStorage.setItem(KEY, JSON.stringify(all)); } catch { /* not kept */ } };
const markSeen = () => { try { localStorage.setItem(SEEN, "1"); } catch { /* fine */ } };
const seen = () => { try { return !!localStorage.getItem(SEEN); } catch { return true; } };

function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
  }
  n.append(...kids.flat().filter((k) => k != null && k !== false));
  return n;
}

/* ---------- Drawing ---------- */

function teardown() {
  cancelAnimationFrame(raf);
  ui?.spot.remove(); ui?.pop.remove();
  ui = null;
  removeEventListener("keydown", onKey, true);
}

function onKey(e) {
  if (!run) return;
  if (e.key === "Escape") { e.preventDefault(); closeTour(); }
  else if (e.key === "ArrowRight" && !e.target.closest?.("input, textarea")) { e.preventDefault(); step(1); }
  else if (e.key === "ArrowLeft" && !e.target.closest?.("input, textarea")) { e.preventDefault(); step(-1); }
}

function card(content, actions, counter) {
  teardown();
  const spot = el("div", { class: "tour-spot", "aria-hidden": "true" });
  const pop = el("div", { class: "tour-pop", role: "dialog", "aria-modal": "false", "aria-labelledby": "tour-title" },
    el("div", { class: "tour-top" },
      el("span", { class: "tour-count" }, counter ? `Stop ${counter[0]} of ${counter[1]}` : "Tour"),
      counter ? el("span", { class: "tour-track", "aria-hidden": "true" }, el("i", { style: `width:${(counter[0] / counter[1]) * 100}%` })) : null,
      el("button", { type: "button", class: "tour-x", "aria-label": "Close the tour (you can carry on later)", title: "Close (you can carry on later)", onclick: closeTour }, "✕")),
    content, el("div", { class: "tour-actions" }, actions));
  document.body.append(spot, pop);
  ui = { spot, pop };
  updateLauncher();
  addEventListener("keydown", onKey, true);
  pop.querySelector(".tour-next")?.focus({ preventScroll: true });
}

function place(target) {
  if (!ui) return;
  const { spot, pop } = ui;
  const pad = 8, gap = 14, vw = innerWidth, vh = innerHeight;
  if (!target || !visible(target)) {
    spot.style.cssText = "opacity:0";
    pop.style.cssText = `left:${Math.max(12, (vw - pop.offsetWidth) / 2)}px; top:${Math.max(12, (vh - pop.offsetHeight) / 2)}px`;
    delete pop.dataset.side;
    return;
  }
  const r = target.getBoundingClientRect();
  const box = { x: r.left - pad, y: r.top - pad, w: r.width + pad * 2, h: Math.min(r.height + pad * 2, vh - 24) };
  spot.style.cssText = `left:${box.x}px; top:${box.y}px; width:${box.w}px; height:${box.h}px`;
  const pw = pop.offsetWidth, ph = pop.offsetHeight;
  let top = box.y + box.h + gap, side = "below";
  if (top + ph > vh - 12) { top = box.y - ph - gap; side = "above"; }
  if (top < 12) { top = Math.min(vh - ph - 12, Math.max(12, box.y + 12)); side = "inside"; }
  const left = Math.min(vw - pw - 12, Math.max(12, box.x + Math.min(24, box.w / 2 - 20)));
  pop.style.cssText = `left:${left}px; top:${top}px`;
  pop.dataset.side = side;
  pop.style.setProperty("--arrow", `${Math.min(pw - 28, Math.max(18, box.x + Math.min(box.w / 2, 60) - left))}px`);
}

function follow(target) {
  const tick = () => { place(target); raf = requestAnimationFrame(tick); };
  cancelAnimationFrame(raf); raf = requestAnimationFrame(tick);
}

/* ---------- Running ---------- */

async function findTarget(stop) {
  stop.before?.();
  const t0 = performance.now();
  for (;;) {
    const n = [...document.querySelectorAll(stop.target)].find(visible);
    if (n) return n;
    if (performance.now() - t0 > 700 || !run) return null;
    await new Promise((r) => setTimeout(r, 80));
  }
}

/** Shows stop i, moving in direction dir past any stop whose target isn't on this screen. */
async function show(i, dir = 1) {
  if (!run) return;
  const { stops, key } = run;
  if (i < 0) i = 0;
  if (i >= stops.length) return finish();
  run.i = i;
  const target = await findTarget(stops[i]);
  if (!run || run.i !== i) return;
  if (!target) {
    const nextI = i + dir;
    if (nextI < 0) return show(i + 1, 1);
    return show(nextI, dir);
  }
  savePlace(key, i);
  target.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  const s = stops[i], last = i === stops.length - 1;
  card(el("div", { class: "tour-body tour-body-plain" }, el("h3", { id: "tour-title" }, s.title), el("p", {}, s.text)),
    [i > 0 ? el("button", { type: "button", class: "tour-skip tour-back", onclick: () => step(-1) }, "← Back") : el("span"),
      el("button", { type: "button", class: "tour-next", onclick: () => step(1) }, last ? "Finish" : "Next →")],
    [i + 1, stops.length]);
  follow(target);
}

function step(d) { if (run) show(run.i + d, d); }

function finish() {
  const key = run?.key, after = TOURS[key]?.next;
  savePlace(key, null);
  run = { key, stops: [], i: 0, done: true };
  card(el("div", { class: "tour-body tour-body-plain" }, el("h3", { id: "tour-title" }, "That's the tour"),
    el("p", {}, after ? `You've seen ${TOURS[key].name}. You can open the Tour button on any page to learn that page.`
      : key === "app" ? "Run a check, then press Tour again to learn how to read the report."
      : "Press Tour on any other page to learn that page.")),
  [el("button", { type: "button", class: "tour-skip", onclick: closeTour }, "Close"),
    after ? el("a", { class: "tour-next", href: after.href, onclick: () => closeTour() }, `${after.label} →`) : null]);
  place(null);
}

/** Closes the tour. Your place on this page is kept, so the Tour button can carry on from it. */
export function closeTour() {
  run = null;
  teardown();
  markSeen();
  updateLauncher();
}

/** Starts this page's tour at a stop (default: the first). */
export function startTour(at = 0) {
  markSeen();
  document.querySelector(".tour-offer")?.remove();
  const key = tourKey(), stops = stopsFor(key);
  if (!stops.length) return;
  run = { key, stops, i: at };
  show(at);
}

/** The Tour button: carry on from where you stopped, or start this page's tour. */
function launch() {
  document.querySelector(".tour-offer")?.remove();
  const key = tourKey(), stops = stopsFor(key), at = loadPlaces()[key];
  if (!stops.length) return;
  if (!Number.isInteger(at) || at <= 0 || at >= stops.length) return startTour(0);
  run = { key, stops, i: at };
  card(el("div", { class: "tour-body tour-body-plain" }, el("h3", { id: "tour-title" }, "Carry on?"),
    el("p", {}, `You stopped at stop ${at + 1} of ${stops.length} in the tour of ${TOURS[key].name}.`)),
  [el("button", { type: "button", class: "tour-skip", onclick: () => { savePlace(key, null); startTour(0); } }, "Start again"),
    el("button", { type: "button", class: "tour-next", onclick: () => show(at) }, `Carry on from stop ${at + 1} →`)]);
  place(null);
}

/* ---------- The Tour button and the first-visit offer ---------- */

function updateLauncher() {
  const b = document.querySelector(".tour-launch");
  if (b) b.hidden = !!run || !!document.querySelector(".tour-offer");
}

function launcher() {
  if (document.querySelector(".tour-launch")) return;
  document.body.append(el("button", { type: "button", class: "tour-launch", "aria-label": "Take a short tour of this page", title: "A short tour of this page",
    onclick: launch }, el("span", { "aria-hidden": "true" }, "?"), " Tour"));
}

function offer() {
  const key = tourKey(), n = stopsFor(key).length;
  if (!n) return;
  const dismiss = () => { markSeen(); box.remove(); updateLauncher(); };
  const box = el("div", { class: "tour-offer", role: "dialog", "aria-labelledby": "tour-offer-title" },
    el("button", { type: "button", class: "tour-x", "aria-label": "Close", onclick: dismiss }, "✕"),
    el("h3", { id: "tour-offer-title" }, "New to Inkwell?"),
    el("p", {}, `A short tour shows what each part of ${TOURS[key].name} does. ${n} stops, at your own pace.`),
    el("div", { class: "tour-actions" },
      el("button", { type: "button", class: "tour-skip", onclick: dismiss }, "No thanks"),
      el("button", { type: "button", class: "tour-next", onclick: () => { box.remove(); startTour(0); } }, "Show me")));
  document.body.append(box);
  updateLauncher();
}

const busy = () => !!document.querySelector("dialog[open], #welcome:not([hidden]), #arrive:not([hidden]), .tour-pop, .check-screen");

/** Call once the page knows who's here. { signedIn }: whether account-only stops apply. */
export function initTour(context = {}) {
  ctx = { ...ctx, ...context };
  launcher();
  const key = tourKey();
  if (!seen() && (key === "home" || key === "app")) {
    const tryOffer = (n = 0) => (busy() ? n < 20 && setTimeout(() => tryOffer(n + 1), 500) : offer());
    setTimeout(tryOffer, 1400);
  }
}
