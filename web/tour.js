// The guided tour: short, catchy tips that walk a new visitor through Inkwell, page by page, from the home page
// to a finished report, their dashboard and the reviews. Each tip has Next, Skip step and ✕ (✕ or Esc closes the
// whole tour). A small "Tour" button on every page starts it again; first-time visitors are offered it once.
// Progress is kept in this browser, so the tour carries on across pages. Tips whose target isn't on screen
// (for example the dashboard for someone without an account) are skipped without a flash.

const KEY = "inkwell-tour", SEEN = "inkwell-tour-seen";
const PAGES = { home: "/", app: "/app.html", dashboard: "/dashboard.html", reviews: "/reviews.html" };
const $ = (s) => document.querySelector(s);
const visible = (n) => !!n && n.getClientRects().length > 0 && getComputedStyle(n).visibility !== "hidden";
const click = (s) => $(s)?.click();

/** The tour, in order. page: where it shows; target: what it points at; account: only for signed-in people. */
const STEPS = [
  { page: "home", target: ".hero h1", icon: "✒", title: "Fine print, decoded.",
    text: "Paste any privacy policy. See what it really lets them do, with the exact sentence as proof." },
  { page: "home", target: ".nav-links", icon: "☰", title: "Everything, one menu away.",
    text: "Features shows what Inkwell does. Resources has guides, reviews and Rate Inkwell." },
  { page: "home", target: "#nav-signin", icon: "★", title: "Free account, full report.", signedOut: true,
    text: "Sign up free for the 8-question report card, your fixes and a dashboard. About 20 seconds." },
  { page: "home", target: ".hero-ctas [data-cta]", icon: "→", title: "Let's try one.", next: "Take me there",
    text: "Next opens the checker. Bring a policy, or borrow ours." },

  { page: "app", target: "#policy", icon: "⎘", title: "Drop it here.",
    text: "Paste a link to their privacy page, or the whole policy. Links are quickest." },
  { page: "app", target: "#sample", icon: "✦", title: "No policy handy?", next: "Use the sample",
    text: "Borrow ours: Pigeonpost, a made-up app with a very real-looking policy.",
    action: () => { if (!$("#policy")?.value.trim()) click("#sample"); } },
  { page: "app", target: "#paste-focus:not([hidden]) .prio-chips", icon: "♥", title: "What matters to you?", account: true,
    text: "Tap what you care about. Your report puts those first, every time." },
  { page: "app", target: "#run", icon: "▶", title: "One click. Under a minute.", next: "Check it for me",
    text: "We read every paragraph, sort it into 5 topics and answer 8 key questions.",
    action: () => { if (!$("#policy")?.value.trim()) click("#sample"); setTimeout(() => click("#run"), 120); } },
  { page: "app", target: ".exposure", wait: "report", icon: "◔", title: "Your exposure score.",
    text: "How many answers are worth knowing. Fix one and watch it drop. Lower is better." },
  { page: "app", target: ".exp-cells", report: true, icon: "●", title: "Red. Yellow. Green.",
    text: "Red: worth knowing. Yellow: the policy doesn't say clearly. Green: in your favour." },
  { page: "app", target: ".fix-btn", report: true, icon: "⚡", title: "Fix it, fast.",
    text: "Each line says how long its fix takes: ⚙ settings take minutes; ✉ requests take up to 45 days, and we write them for you." },
  { page: "app", target: ".concern-detail .for-you", report: true, icon: "❝", title: "Proof, in plain words.",
    before: () => { if (!$(".concern.open")) click(".concern-toggle"); },
    text: "Tap any line: what it means for you, then the exact sentence it came from. No guesses." },
  { page: "app", target: ".concern-detail .term", report: true, icon: "?", title: "Jargon? Hover it.",
    text: "Dotted words come with a one-line explanation. “Third parties”, decoded." },
  { page: "app", target: ".decision-ask, .decided", report: true, icon: "⚖", title: "Your call.",
    text: "Fix it, accept it, or walk away. Inkwell never decides for you." },
  { page: "app", target: "#guest-banner:not([hidden])", icon: "★", title: "Want the full report?", signedOut: true,
    text: "Free checks show the breakdown. A free account adds the report card, fixes and your dashboard." },
  { page: "app", target: "#app-nav:not([hidden]) a[href='dashboard.html']", icon: "◫", title: "It's all saved.", account: true, next: "Show me",
    text: "Every check lands on your dashboard, with the steps you've ticked." },

  { page: "dashboard", target: "#dash-list", icon: "◫", title: "Your privacy history.", account: true,
    text: "Open any check to pick up where you left off. Check again later to see what changed." },
  { page: "dashboard", target: ".app-nav a[href='compare.html']", icon: "⇄", title: "Two apps, side by side.", account: true, next: "Last stop",
    text: "Compare puts two policies next to each other, differences first. It never picks a winner." },

  { page: "reviews", target: ".rvp-score", icon: "☆", title: "Hear it from others.",
    text: "Real ratings from people who checked a policy. We don't edit them or hide low scores." },
  { page: "reviews", target: ".rvp-score .btn", icon: "✍", title: "Your turn.", final: true,
    text: "That's the tour! Rate Inkwell in a minute (halves count), or close the tour and explore." },
];

let ctx = { signedIn: false }, current = -1, ui = null, raf = 0, waitTimer = 0;

const pageNow = () => {
  const p = location.pathname;
  return p === "/" || p.endsWith("/index.html") ? "home" : p.endsWith("/app.html") ? "app" : p.endsWith("/dashboard.html") ? "dashboard"
    : p.endsWith("/reviews.html") ? "reviews" : null;
};
const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch { return null; } };
const save = (v) => { try { v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); } catch { /* not remembered */ } };
const seen = () => { try { return !!localStorage.getItem(SEEN); } catch { return true; } };
const markSeen = () => { try { localStorage.setItem(SEEN, "1"); } catch { /* fine */ } };
const allowed = (s) => !(s.account && !ctx.signedIn) && !(s.signedOut && ctx.signedIn);

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
  cancelAnimationFrame(raf); clearTimeout(waitTimer);
  ui?.spot.remove(); ui?.pop.remove();
  ui = null;
  removeEventListener("keydown", onKey, true);
}

function onKey(e) {
  if (e.key === "Escape") { e.preventDefault(); closeTour(); }
}

function frame(content, { counter, onSkip, nextLabel, onNext, final } = {}) {
  teardown();
  const spot = el("div", { class: "tour-spot", "aria-hidden": "true" });
  const total = STEPS.filter(allowed).length, at = STEPS.slice(0, Math.max(0, current + 1)).filter(allowed).length;
  const pop = el("div", { class: "tour-pop", role: "dialog", "aria-modal": "false", "aria-labelledby": "tour-title" },
    el("div", { class: "tour-top" },
      counter ? el("span", { class: "tour-count" }, `${at} / ${total}`) : el("span", { class: "tour-count" }, "Inkwell tour"),
      counter ? el("span", { class: "tour-track", "aria-hidden": "true" }, el("i", { style: `width:${(at / total) * 100}%` })) : null,
      el("button", { type: "button", class: "tour-x", "aria-label": "Close the tour", title: "Close the tour", onclick: closeTour }, "✕")),
    content,
    el("div", { class: "tour-actions" },
      onSkip ? el("button", { type: "button", class: "tour-skip", onclick: onSkip }, "Skip step") : el("span"),
      final ? el("button", { type: "button", class: "tour-skip", onclick: closeTour }, "Close tour") : null,
      onNext ? el("button", { type: "button", class: "tour-next", onclick: onNext }, nextLabel || "Next →") : null));
  document.body.append(spot, pop);
  ui = { spot, pop };
  updateLauncher();
  addEventListener("keydown", onKey, true);
  pop.querySelector(".tour-next, .tour-x")?.focus({ preventScroll: true });
  return ui;
}

function place(target) {
  if (!ui) return;
  const { spot, pop } = ui;
  const pad = 8, gap = 14, vw = innerWidth, vh = innerHeight;
  if (!target || !visible(target)) {
    spot.style.cssText = "opacity:0";
    pop.style.cssText = `left:${Math.max(12, (vw - pop.offsetWidth) / 2)}px; top:${Math.max(12, (vh - pop.offsetHeight) / 2)}px`;
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

async function find(step) {
  // Tips about the report skip straight away when there's no report on screen.
  if (step.report && !document.querySelector("#results:not([hidden])")) return null;
  const limit = step.wait === "report" ? 150000 : 900, t0 = performance.now();
  for (;;) {
    const n = [...document.querySelectorAll(step.target)].find(visible);
    if (n) return n;
    if (performance.now() - t0 > limit) return null;
    if (step.wait === "report" && performance.now() - t0 > 300 && !ui?.waiting) waitingCard();
    await new Promise((r) => (waitTimer = setTimeout(r, 150)));
    if (current < 0) return null;  // Closed while waiting.
  }
}

function waitingCard() {
  frame(el("div", { class: "tour-body" }, el("p", { class: "tour-icon", "aria-hidden": "true" }, "⏳"),
    el("h3", { id: "tour-title" }, "Reading the policy…"),
    el("p", {}, "Press “Check this policy” if you haven't. The tour picks up the moment your report is ready.")),
    { onSkip: () => go(current + 1) });
  ui.waiting = true;
  place(null);
}

async function show(i) {
  current = i;
  if (i >= STEPS.length) return closeTour();
  const step = STEPS[i];
  if (!allowed(step)) return show(i + 1);
  if (step.page !== pageNow()) {
    save({ i });
    location.href = PAGES[step.page];
    return;
  }
  save({ i });
  step.before?.();
  const target = await find(step);
  if (current !== i) return;  // Moved on (closed or skipped) while looking.
  if (!target) return show(i + 1);
  target.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  const last = step.final;
  frame(el("div", { class: "tour-body" },
    el("p", { class: "tour-icon", "aria-hidden": "true" }, step.icon),
    el("h3", { id: "tour-title" }, step.title),
    el("p", {}, step.text)),
  { counter: true, onSkip: last ? null : () => go(i + 1), nextLabel: last ? "★ Rate Inkwell" : step.next ? `${step.next} →` : "Next →", final: last,
    onNext: () => {
      if (last) { closeTour(); click(".rvp-score .btn"); return; }
      step.action?.();
      go(i + 1);
    } });
  follow(target);
}

function go(i) { teardown(); show(i); }

/** Closes the tour completely, from any step. */
export function closeTour() {
  current = -1;
  teardown();
  save(null);
  markSeen();
  updateLauncher();
}

/** Starts the tour: from the first tip on this page, or from the very beginning. */
export function startTour(fromStart = false) {
  markSeen();
  document.querySelector(".tour-offer")?.remove();
  const here = STEPS.findIndex((s) => s.page === pageNow() && allowed(s));
  show(fromStart || here < 0 ? 0 : here);
}

/* ---------- The launcher and the first-visit offer ---------- */

function updateLauncher() {
  const b = document.querySelector(".tour-launch");
  if (b) b.hidden = current >= 0;
}

function launcher() {
  if (document.querySelector(".tour-launch")) return;
  document.body.append(el("button", { type: "button", class: "tour-launch", "aria-label": "Start the guided tour", title: "Take the guided tour",
    onclick: () => startTour(pageNow() === "home") }, el("span", { "aria-hidden": "true" }, "✦"), " Tour"));
}

function offer() {
  const dismiss = () => { markSeen(); card.remove(); updateLauncher(); };
  const card = el("div", { class: "tour-offer", role: "dialog", "aria-labelledby": "tour-offer-title" },
    el("button", { type: "button", class: "tour-x", "aria-label": "Close", onclick: dismiss }, "✕"),
    el("p", { class: "tour-icon", "aria-hidden": "true" }, "👋"),
    el("h3", { id: "tour-offer-title" }, "New here? Take the 60-second tour."),
    el("p", {}, "Paste → check → fix → done. We'll show you each part as you go."),
    el("div", { class: "tour-actions" },
      el("button", { type: "button", class: "tour-skip", onclick: dismiss }, "Skip tour"),
      el("button", { type: "button", class: "tour-next", onclick: () => { card.remove(); startTour(pageNow() === "home"); } }, "Start tour →")));
  document.body.append(card);
  const b = document.querySelector(".tour-launch");
  if (b) b.hidden = true;  // One invitation at a time.
}

const busy = () => !!document.querySelector("dialog[open], #welcome:not([hidden]), #arrive:not([hidden]), .tour-pop");

/**
 * Call once the page knows who's here. { signedIn }: whether account-only tips apply.
 * Resumes a tour in progress, or offers it to a first-time visitor on the home page or the checker.
 */
export function initTour(context = {}) {
  ctx = { ...ctx, ...context };
  launcher();
  const saved = load(), page = pageNow();
  if (saved && Number.isInteger(saved.i)) {
    const step = STEPS[saved.i];
    if (step && step.page === page) { show(saved.i); updateLauncher(); return; }
    // Mid-tour on another page (say, signing in): keep the place; the launcher picks it up from here.
    if (step && page) { const here = STEPS.findIndex((s, k) => k >= saved.i && s.page === page && allowed(s)); if (here >= 0) { show(here); return; } }
  }
  if (!seen() && (page === "home" || page === "app")) {
    const tryOffer = (n = 0) => (busy() ? n < 20 && setTimeout(() => tryOffer(n + 1), 500) : offer());
    setTimeout(tryOffer, 1400);
  }
}
