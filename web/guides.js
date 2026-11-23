// Guides page ("Behind the I agree button"): five topic circles on a trail. Clicking a circle, or an
// "I want to" shortcut, shows what the topic means, how it reads in a policy, and how Inkwell helps.
// The "How Inkwell helps" cards use the report card's real check names and verdict wording (inkwell/report.py).
// The chosen topic is kept in the address (#sale, #delete, ...) so it can be linked to.
import { currentUser, startAuth, toggleTheme } from "./auth.js";
import { mountMenus } from "./menu.js";
import { el } from "./shared.js";

const $ = (id) => document.getElementById(id);

const ICON = {
  read: '<path d="M4 5h11a3 3 0 0 1 3 3v11H7a3 3 0 0 1-3-3z"/><path d="M8 9h6M8 13h6"/>',
  partners: '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3.5 19c.6-3 2.8-5 5.5-5s4.9 2 5.5 5M14.5 14.5c2.6-.6 5.3.9 6 4.5"/>',
  sale: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
  rights: '<path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
  delete: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="M4 7l8 6 8-6"/>',
};

const TOPICS = [
  {
    id: "read", icon: "read", title: "Read a policy fast", hint: "The 8 questions",
    kicker: "Read a privacy policy in 5 minutes",
    heading: "Every policy answers the same 8 questions.",
    lede: "They're just hard to find. The parts that matter are spread across long pages written to be skipped.",
    facts: ["Do they sell or share your data, or use it for ads?", "Do they track your location, and how long do they keep things?",
      "Can you delete your data or opt out, and will they tell you about changes?"],
    snippets: [
      { tone: "unknown", label: "Vague", text: "We may use your information for other business purposes.", note: "Says almost nothing. Easy to skim past." },
      { tone: "bad", label: "Watch out", text: "By continuing to use the service, you agree to any changes to this policy.", note: "They can change the rules without asking you." },
    ],
    card: [{ title: "Sells your data", tone: "bad", verdict: "Yes, or it may count as a sale" },
      { title: "Lets you delete your data", tone: "good", verdict: "Yes" },
      { title: "Says how long it keeps your data", tone: "unknown", verdict: "No clear time limit" }],
    points: ["Answers all 8 questions in seconds", "Quotes the exact sentence behind each answer", "Says “Not mentioned” instead of guessing"],
    cta: ["Try it on a sample policy", "app.html?sample=1"],
  },
  {
    id: "partners", icon: "partners", title: "Who are “partners”?", hint: "Sharing",
    kicker: "“We may share with partners”: who is that?",
    heading: "“Partners” can mean almost anyone.",
    lede: "It can be the company that sends their emails, or an advertiser building a profile of you. The policy rarely says which.",
    facts: ["Service providers run parts of the app for them, like payments or hosting.", "Advertisers and data brokers use your data for their own ends.",
      "Affiliates are other companies in the same group."],
    snippets: [
      { tone: "unknown", label: "Vague", text: "We share information with our trusted partners.", note: "Who? For what? It doesn't say." },
      { tone: "bad", label: "They do", text: "We share data with advertising partners to personalize the ads you see.", note: "Your data leaves to build ad profiles." },
    ],
    card: [{ title: "Shares your data with other companies", tone: "bad", verdict: "Yes", quote: "We share data with advertising partners to personalize the ads you see." },
      { title: "Uses your data for targeted ads", tone: "bad", verdict: "Yes" }],
    points: ["Shows who gets your data, in the policy's own words", "Finds their opt-out link when the policy names one", "Writes a request to stop the sharing, ready to send"],
    cta: ["Check who a site shares with", "app.html"],
  },
  {
    id: "sale", icon: "sale", title: "Stop the sale", hint: "Selling your data · US",
    kicker: "Stop the sale of your data",
    heading: "Your data may be for sale. You can say no.",
    lede: "Many apps pass what they know about you to advertisers and data brokers. In several US states, the law lets you opt out.",
    facts: ["“Selling” can include sharing for targeted ads, not just for money.", "Sites often add a “Do Not Sell or Share” link, usually in the footer.",
      "Global Privacy Control is a browser setting that asks every site not to sell."],
    snippets: [
      { tone: "bad", label: "They do", text: "We may sell personal information to advertising partners.", note: "A clear yes, often deep in the policy." },
      { tone: "unknown", label: "Unclear", text: "We share data with partners to show you relevant ads.", note: "Not called a sale, but it may count as one." },
    ],
    card: [{ title: "Sells your data", tone: "bad", verdict: "Yes, or it may count as a sale", quote: "We may sell personal information to advertising partners." },
      { title: "Uses your data for targeted ads", tone: "bad", verdict: "Yes" }],
    points: ["Finds the exact sentence, so you don't have to read it all", "Links their “Do Not Sell” page when the policy names it", "Writes the opt-out email, ready to send"],
    cta: ["See it on a real policy", "app.html"],
  },
  {
    id: "rights", icon: "rights", title: "Your privacy rights", hint: "US · EU & UK",
    // Rights depend on where you live, so this topic has a switch. Each region replaces the fields below it.
    regions: {
      us: {
        label: "US",
        kicker: "Your privacy rights in the US",
        heading: "In many US states, you can ask what they have.",
        lede: "There's no single national law. California and a growing list of states give their residents rights over the data companies hold.",
        facts: ["Know: ask what they collected about you, and who they sold or shared it with.", "Delete and correct: ask them to erase it, or fix what's wrong.",
          "Opt out: say no to the sale of your data and targeted ads. They often have 45 days to answer."],
        snippets: [
          { tone: "good", label: "Clear", text: "California residents may request to know, delete or correct their personal information.", note: "Names the rights and who has them." },
          { tone: "unknown", label: "Vague", text: "Residents of certain states may have additional rights.", note: "Which states? Which rights? It doesn't say." },
        ],
      },
      eu: {
        label: "EU & UK",
        kicker: "Your rights under GDPR, without the legalese",
        heading: "In the EU and UK, the law is on your side.",
        lede: "If a company handles your data there, you can ask what it has, fix it, delete it, or object to how it's used.",
        facts: ["Access: get a copy of your data, and who it went to.", "Correct and delete: fix what's wrong, erase what isn't needed.",
          "Object: say no to uses like direct marketing. They usually have one month to answer."],
        snippets: [
          { tone: "good", label: "Clear", text: "You may request access to, correction or erasure of your personal data.", note: "Tells you what you can ask for." },
          { tone: "unknown", label: "Vague", text: "Requests will be handled in accordance with applicable law.", note: "No contact and no timeline." },
        ],
      },
    },
    card: [{ title: "Lets you delete your data", tone: "good", verdict: "Yes" }, { title: "Lets you opt out", tone: "good", verdict: "Yes" }],
    points: ["Finds their privacy contact in the policy", "Writes access and deletion requests, ready to send", "Keeps the check in your dashboard for later"],
    cta: ["Write a request with Inkwell", "app.html"],
  },
  {
    id: "delete", icon: "delete", title: "Deleting your data", hint: "What they keep",
    kicker: "Deleting your data: what really happens",
    heading: "Deleting your account doesn't always delete your data.",
    lede: "Companies may keep some records for legal reasons, and copies already shared with partners stay with them.",
    facts: ["Ask for deletion in writing, and ask what they keep and why.", "US companies often have 45 days to answer; in the EU, usually one month.",
      "“As long as necessary” means they decide how long."],
    snippets: [
      { tone: "good", label: "Clear", text: "You can delete your account at any time in Settings.", note: "Tells you how. Easy to act on." },
      { tone: "unknown", label: "Vague", text: "We retain information for as long as necessary for our business purposes.", note: "No end date. They decide." },
    ],
    card: [{ title: "Lets you delete your data", tone: "good", verdict: "Yes" },
      { title: "Says how long it keeps your data", tone: "unknown", verdict: "No clear time limit", quote: "We retain information for as long as necessary for our business purposes." }],
    points: ["Checks whether you can delete, and how long they keep data", "Writes a deletion request that asks their partners to delete too", "Adds it to “Your steps” so you can tick it off"],
    cta: ["Check a policy", "app.html"],
  },
];
// "I want to" shortcuts, in the order they're shown.
const GOALS = [["read", "Understand a policy", "read"], ["sale", "Stop them selling my data", "sale"], ["rights", "See what they have on me", "mail"], ["delete", "Delete my data", "delete"]];
// Where each circle sits on the trail (percent across, px down), alternating low and high.
const SPOTS = [[10, 172], [30, 92], [50, 172], [70, 92], [90, 172]];

// Which region "Your privacy rights" shows: the visitor's last choice, else a guess from the browser language.
const REGION_KEY = "inkwell-rights-region";
let region = (() => {
  try { const saved = localStorage.getItem(REGION_KEY); if (saved === "us" || saved === "eu") return saved; } catch { /* storage blocked */ }
  return /-US$/i.test(navigator.language || "") ? "us" : "eu";
})();
function setRegion(next) {
  region = next;
  try { localStorage.setItem(REGION_KEY, next); } catch { /* not remembered */ }
  select("rights", false);
  document.querySelector(`.gd-switch [data-region="${next}"]`)?.focus();
}

const svg = (name) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.setAttribute("viewBox", "0 0 24 24");
  node.setAttribute("aria-hidden", "true");
  node.innerHTML = ICON[name];  // Fixed markup from ICON above, never user input.
  return node;
};

const stops = TOPICS.map((t, i) => {
  const [x, y] = SPOTS[i];
  return el("button", { type: "button", class: `gd-stop${y < 150 ? " up" : ""}`, style: `left:${x}%;top:${y}px`, "aria-pressed": "false",
    "aria-controls": "gd-detail", "data-id": t.id, onclick: () => select(t.id, true), onkeydown: (e) => arrows(e, i) },
  el("span", { class: "gd-pin" }, svg(t.icon)), el("span", { class: "gd-lab" }, el("b", {}, t.title), el("small", {}, t.hint)));
});
const goals = GOALS.map(([id, label, icon]) => el("button", { type: "button", class: "gd-goal", "aria-pressed": "false", "data-id": id,
  onclick: () => select(id, true) }, svg(icon), label));

function arrows(e, i) {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  if (!step) return;
  e.preventDefault();
  const next = stops[(i + step + stops.length) % stops.length];
  next.focus();
  select(next.dataset.id, false);
}

/** Shows topic `id`. `scroll`: bring the details into view. `remember`: put the topic in the address. */
function select(id, scroll, remember = true) {
  const base = TOPICS.find((x) => x.id === id) || TOPICS[0];
  const index = TOPICS.indexOf(base);
  const t = base.regions ? { ...base, ...base.regions[region] } : base;
  const regionSwitch = base.regions ? el("div", { class: "gd-switch", role: "group", "aria-label": "Where you live" },
    Object.entries(base.regions).map(([key, r]) => el("button", { type: "button", "data-region": key, "aria-pressed": String(key === region),
      onclick: () => { if (key !== region) setRegion(key); } }, r.label))) : null;
  for (const s of stops) s.setAttribute("aria-pressed", String(s.dataset.id === t.id));
  for (const g of goals) g.setAttribute("aria-pressed", String(g.dataset.id === t.id));
  const detail = $("gd-detail");
  detail.style.setProperty("--arrow", `${SPOTS[index][0]}%`);
  detail.setAttribute("aria-label", t.kicker);
  detail.replaceChildren(
    el("div", {},
      el("span", { class: "gd-k" }, t.kicker),
      regionSwitch,
      el("h2", {}, t.heading),
      el("p", { class: "gd-lede" }, t.lede),
      el("ul", { class: "gd-facts" }, t.facts.map((f, n) => el("li", {}, el("b", {}, String(n + 1)), el("span", {}, f))))),
    el("div", {},
      el("p", { class: "gd-h" }, "What it looks like in a policy"),
      t.snippets.map((s) => el("div", { class: "gd-snip" }, el("span", { class: `gd-tag ${s.tone}` }, s.label), el("q", {}, s.text), el("small", {}, s.note)))),
    el("div", {},
      el("div", { class: "gd-helps" },
        el("div", { class: "gd-helps-t" }, el("img", { src: "logo.svg", alt: "" }), "How Inkwell helps"),
        el("div", { class: "gd-card", "aria-label": "Example from Inkwell's report card" }, t.card.flatMap((r) => [
          el("div", { class: "gd-row" }, el("b", {}, r.title), el("span", { class: `gd-tag ${r.tone}` }, r.verdict)),
          r.quote ? el("p", { class: "gd-quote" }, `“${r.quote}”`) : null])),
        el("ul", { class: "gd-points" }, t.points.map((p) => el("li", {}, p))),
        el("a", { class: "btn btn-primary", href: t.cta[1] }, t.cta[0]))));
  if (remember && location.hash.slice(1) !== t.id) history.replaceState(null, "", `#${t.id}`);
  if (scroll && detail.getBoundingClientRect().top > innerHeight - 160) detail.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
}

$("gd-stops").replaceChildren(...stops);
$("gd-goals").append(...goals);
const fromHash = () => TOPICS.some((t) => t.id === location.hash.slice(1)) ? location.hash.slice(1) : null;
select(fromHash() || TOPICS[0].id, false, false);
addEventListener("hashchange", () => { const id = fromHash(); if (id) select(id, true); });

/* ---------- The trail: one run of the dot when the trail first comes into view ---------- */

// The whole run is built as keyframes up front and handed to the browser's animation engine (Web Animations),
// which moves the dot on the compositor: it stays smooth even while the page is still busy loading.
const VIEW = { w: 1120, h: 262 };  // The trail SVG's viewBox.
const RUN_MS = 3000;
const KEYS = 150;  // Keyframes along the trail.
// Gentle ease in and out, so the dot never looks stalled at the start or the end.
const ease = (p) => (1 - Math.cos(Math.PI * p)) / 2;

let trailStarted = false;
function runTrail() {
  if (trailStarted) return;
  trailStarted = true;
  const path = $("gd-trail"), dot = $("gd-dot"), map = document.querySelector(".gd-map");
  const reveal = $("gd-reveal"), revealIn = $("gd-reveal-in");
  const showAll = () => { reveal.style.transform = "none"; revealIn.style.transform = "none"; };
  const done = () => { showAll(); dot.classList.remove("on"); };
  // No dot when motion is reduced, on phones where the trail is hidden, or without Web Animations: just colour it.
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || getComputedStyle(path.ownerSVGElement).display === "none" || !dot.animate) return done();

  // One set of keyframes for the dot and for the colour's leading edge, so the two can't drift apart. Everything
  // animated is a transform, which the browser runs on its own, away from the page's other work.
  const total = path.getTotalLength(), W = map.clientWidth, sx = W / VIEW.w, sy = map.clientHeight / VIEW.h;
  const dotFrames = [], outFrames = [], inFrames = [], xs = [];
  for (let k = 0; k <= KEYS; k++) {
    const p = k / KEYS, pt = path.getPointAtLength(ease(p) * total), x = pt.x * sx;
    xs.push(x);
    dotFrames.push({ transform: `translate3d(${x}px, ${pt.y * sy}px, 0)` });
    outFrames.push({ transform: `translate3d(${x - W}px, 0, 0)` });  // The window's right edge sits under the dot.
    inFrames.push({ transform: `translate3d(${W - x}px, 0, 0)` });   // ...while the wave inside stays still.
  }
  // When the dot is over each circle's centre: the keyframe whose x is closest to it.
  const reach = SPOTS.map(([pct]) => {
    const target = (pct / 100) * W;
    const best = xs.reduce((b, x, k) => (Math.abs(x - target) < Math.abs(xs[b] - target) ? k : b), 0);
    return (best / KEYS) * RUN_MS;
  });
  const timing = { duration: RUN_MS, easing: "linear", fill: "forwards" };
  dot.style.transform = dotFrames[0].transform;  // At the start of the trail as it fades in.
  dot.classList.add("on");
  const runs = [dot.animate(dotFrames, timing), reveal.animate(outFrames, timing), revealIn.animate(inFrames, timing)];
  // Each circle's pulse is part of the same run: started together, delayed to the moment the dot arrives, so it
  // can't fall behind the way a timer could. Each pulse peaks exactly as the dot is over the circle's centre.
  const PULSE_MS = 650, PEAK = .35;
  const pulses = stops.flatMap((stop, i) => {
    const pin = stop.querySelector(".gd-pin"), at = { delay: Math.max(0, reach[i] - PULSE_MS * PEAK), easing: "linear" };
    const list = [pin.animate([{ transform: "scale(1)", easing: "ease-out" }, { transform: "scale(1.16)", offset: PEAK, easing: "ease-in-out" }, { transform: "scale(1)" }], { ...at, duration: PULSE_MS })];
    try { list.push(pin.animate([{ opacity: .9, transform: "scale(1)" }, { opacity: 0, transform: "scale(1.75)" }], { ...at, duration: 800, pseudoElement: "::after" })); }
    catch { /* No pseudo-element animations in this browser: the scale alone. */ }
    return list;
  });
  runs[0].ready.then(() => { for (const a of pulses) a.startTime = runs[0].startTime; });  // One shared clock.
  Promise.all(runs.map((a) => a.finished)).then(() => {
    showAll();
    runs[1].cancel(); runs[2].cancel();
    setTimeout(() => { dot.classList.remove("on"); }, 250);
  }).catch(done);
}

// Wait until the fonts are in, so the page has stopped shifting, then start if the trail is on screen (the usual
// case), otherwise when it's scrolled into view.
function startTrailWhenVisible() {
  const box = document.querySelector(".gd-map").getBoundingClientRect();
  if (box.top < innerHeight - box.height / 2 && box.bottom > 0) return runTrail();
  if (!("IntersectionObserver" in window)) return runTrail();
  const watch = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { watch.disconnect(); runTrail(); }
  }, { threshold: .5 });
  watch.observe(document.querySelector(".gd-map"));
  // Never leave the trail grey: if it hasn't started after a few seconds, just colour it.
  setTimeout(() => {
    if (trailStarted) return;
    trailStarted = true; watch.disconnect();
    $("gd-reveal").style.transform = "none"; $("gd-reveal-in").style.transform = "none";
  }, 6000);
}
Promise.race([document.fonts?.ready ?? Promise.resolve(), new Promise((r) => setTimeout(r, 1500))])
  .then(() => setTimeout(startTrailWhenVisible, 150));

/* ---------- The extension pop-up (guides.html#extension) ---------- */

// The Chrome Web Store page. Leave empty until the extension is published; "Add to Chrome" shows once it's set.
const EXTENSION_URL = "";

const extDialog = $("extension");
// Once it's in the store, one "Add to Chrome" button replaces the by-hand install steps.
if (EXTENSION_URL) { $("gd-ext-install").href = EXTENSION_URL; $("gd-ext-install").hidden = false; $("gd-install").hidden = true; }
// Websites can't open chrome://extensions, so step 2 offers to copy the address instead.
$("gd-ext-copy").addEventListener("click", async (e) => {
  const button = e.currentTarget, address = $("gd-ext-addr").textContent;
  try {
    await navigator.clipboard.writeText(address);
    button.textContent = "Copied ✓";
  } catch {
    getSelection().selectAllChildren($("gd-ext-addr"));  // Clipboard blocked: select it so Ctrl+C works.
    button.textContent = "Press Ctrl+C";
  }
  setTimeout(() => { button.textContent = "Copy"; }, 2000);
});
function openExtension() {
  if (!extDialog.open) extDialog.showModal();
}
// Closing clears #extension from the address, so the card and the menu links can open it again.
const forgetHash = () => { if (location.hash === "#extension") history.replaceState(null, "", location.pathname + location.search); };
const closeExtension = () => { extDialog.close(); forgetHash(); };
extDialog.addEventListener("cancel", forgetHash);  // Esc
extDialog.addEventListener("close", forgetHash);
// A click on the backdrop (outside the box) closes it; clicks on the box's own padding don't.
extDialog.addEventListener("click", (e) => {
  if (e.target !== extDialog) return;
  const r = extDialog.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) closeExtension();
});
$("gd-ext-close").addEventListener("click", closeExtension);
$("gd-ext-done").addEventListener("click", closeExtension);
document.querySelector('.gd-short[href="#extension"]').addEventListener("click", (e) => {
  e.preventDefault();
  history.replaceState(null, "", "#extension");
  openExtension();
});
if (location.hash === "#extension") openExtension();
addEventListener("hashchange", () => { if (location.hash === "#extension") openExtension(); });

$("theme").addEventListener("click", toggleTheme);
mountMenus(document.querySelector(".nav-links"));
(async () => {
  try {
    const ctx = await startAuth();
    if (ctx.enabled && (await currentUser(ctx))) { $("nav-signin").hidden = true; $("nav-cta").textContent = "Open Inkwell"; }
  } catch { /* server asleep: the links still work */ }
})();
