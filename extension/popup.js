// The Inkwell popup. Nothing happens until the person clicks the toolbar icon; the policy is read only when
// they press "Check policy". Each red answer says how long it takes to limit, and the button does it:
//   ⚡ Fix now     a switch in the extension (the "don't sell or share" signal, blocking location)
//   ⚙ In settings opens the site's own settings page, found in the policy or on our hand-checked list
//   ✉ Request     a pre-written email; Inkwell tracks the legal deadline and reminds you
//   — Comes with the service   nothing to switch off; the choice is whether to use it
import { DAY, TEMPLATES, apiBase, deadline, el, getSettings, listRequests, mailto, saveRequests, saveSettings, shortDate } from "./common.js";
import { highlightTips, scanPage } from "./scan.js";

const root = document.getElementById("view");
const S = { settings: null, api: "", tab: null, auth: null, config: null, scan: null, result: null };
const TIP_TAGS = { email: "Use a hidden email →", optional: "Not required →", marketing: "Untick this →" };
const INDUSTRY_ADS = "https://optout.aboutads.info/";
const GPC_WORDS = /global\s+privacy\s+control|\bGPC\b|opt-out\s+preference\s+signal/i;
const TIERS = {
  now: { cls: "now", icon: "⚡", text: "Fix now" },
  set: { cls: "set", icon: "⚙", text: "In settings · ~2 min" },
  req: { cls: "req", icon: "✉", text: "Request" },
  none: { cls: "none", icon: "—", text: "Comes with the service" },
};

const show = (...nodes) => { root.replaceChildren(...nodes); root.scrollTop = 0; };
const msg = (type, extra = {}) => chrome.runtime.sendMessage({ type, ...extra });
const link = (text, href) => el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
const openTab = (url) => chrome.tabs.create({ url });
const resultKey = () => `result:${(S.tab?.url || "").split("#")[0]}`;

function setStatus(text, kind = "") {
  const box = document.getElementById("status");
  if (box) { box.textContent = text; box.className = `status ${kind}`; }
}

/** "https://www.pigeonpost.co.uk/signup" -> "Pigeonpost" (the same rule as the Inkwell server). */
function siteName(url = S.tab?.url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (/^[\d.]+$|^\[|^localhost$/.test(host)) return host;
    const labels = host.replace(/^www\./, "").split(".");
    const key = labels.length >= 3 && ["co", "com", "org", "net", "ac", "gov", "edu"].includes(labels.at(-2)) ? labels.at(-3)
      : labels.length >= 2 ? labels.at(-2) : labels[0];
    return key.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  } catch { return "This site"; }
}

async function runInPage(func, args = []) {
  const [first] = await chrome.scripting.executeScript({ target: { tabId: S.tab.id }, func, args });
  return first?.result;
}

async function api(path, body, timeoutMs = 90000) {
  const headers = { "Content-Type": "application/json" };
  if (S.config.enabled) {
    const token = await msg("token");
    if (!token?.ok || !token.value) throw Object.assign(new Error("Please sign in again."), { signedOut: true });
    headers.Authorization = `Bearer ${token.value}`;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(S.api + path, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { await msg("sign-out"); throw Object.assign(new Error("Please sign in again."), { signedOut: true }); }
    if (!response.ok) throw new Error(data.detail || `Inkwell answered ${response.status}.`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Inkwell took too long to answer. If it was asleep, try again in a minute.");
    if (error instanceof TypeError) throw new Error("Can't reach Inkwell. It may be waking up; try again shortly.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- Start ---------- */

async function init() {
  S.settings = await getSettings();
  S.api = apiBase(S.settings);
  // popup.html?tab=<id> opens the popup as a page about another tab (used by the automated test).
  const forced = Number(new URLSearchParams(location.search).get("tab"));
  [S.tab] = forced ? [await chrome.tabs.get(forced)] : await chrome.tabs.query({ active: true, currentWindow: true });
  show(el("p", { class: "pad muted" }, "Opening Inkwell…"));
  try {
    const response = await fetch(`${S.api}/auth-config`);
    if (!response.ok) throw new Error();
    S.config = await response.json();
  } catch {
    return show(el("div", { class: "pad" }, el("p", {}, "Can't reach Inkwell right now. The server may be waking up."),
      el("button", { class: "btn", onclick: init }, "Try again")));
  }
  S.auth = (await chrome.storage.local.get("auth")).auth || null;
  if (S.config.enabled && (!S.auth || S.auth.open)) return signedOutView();
  if (!/^https?:/i.test(S.tab?.url || "")) {
    return show(el("div", { class: "pad" }, el("p", { class: "lead" }, "Open a website first"),
      el("p", {}, "Go to a site you're about to sign up for, then click the Inkwell icon again.")));
  }
  try { S.scan = await runInPage(scanPage); } catch { S.scan = null; }  // Some pages (like the Chrome Web Store) can't be read.
  const cached = (await chrome.storage.session.get(resultKey()))[resultKey()];
  if (cached) { S.result = cached; return cardView(); }
  homeView();
}

/* ---------- Not signed in ---------- */

function signedOutView() {
  show(el("div", { class: "pad" },
    el("p", { class: "lead" }, "Know what you're agreeing to, before you agree."),
    el("p", {}, "Inkwell reads this site's privacy policy and shows what to be aware of, with the quickest way to limit each thing."),
    el("button", { class: "btn", onclick: () => connect("signup") }, "Sign up free"),
    el("button", { class: "btn ghost", onclick: () => connect("signin") }, "I already have an account"),
    el("p", { class: "fine" }, "Takes under a minute. We'll bring you back to this page.")));
}

async function connect(mode) {
  await msg("connect-start", { mode, tabId: S.tab?.id });
  window.close();
}

/* ---------- Before checking: quick wins and the policy link ---------- */

function homeView() {
  const nodes = [];
  const who = S.auth?.name || S.auth?.email;
  if (who) nodes.push(el("p", { class: "who" }, "✓ Signed in as ", who));
  const tips = tipsBlock();
  if (tips) nodes.push(tips);
  const found = S.scan?.policy?.[0];
  const input = el("input", { type: "text", class: "input", placeholder: "https://…/privacy", "aria-label": "Link to the privacy policy", inputmode: "url" });
  const manual = el("form", { class: "manual", onsubmit: (e) => {
    e.preventDefault();
    const value = input.value.trim();
    if (value) check(/^https?:\/\//i.test(value) ? value : `https://${value}`);
  } }, input, el("button", { class: "btn ghost small", type: "submit" }, "Check"));
  if (found) {
    nodes.push(el("p", { class: "tight" }, el("strong", {}, `We found ${siteName()}'s privacy policy:`)),
      link(found.url.replace(/^https?:\/\//, ""), found.url),
      el("button", { class: "btn", id: "check", onclick: () => check(found.url) }, "Check policy"),
      el("details", { class: "fold" }, el("summary", {}, "Wrong page? Paste the right link"), manual));
    nodes.at(-3).className = "found-link";
  } else {
    nodes.push(el("p", { class: "tight" }, el("strong", {}, "No privacy policy link on this page.")),
      el("p", { class: "fine" }, "It's usually at the bottom of the site. Paste its link here:"), manual);
  }
  nodes.push(el("p", { class: "status", id: "status", role: "status" }));
  show(el("div", { class: "pad" }, ...nodes));
}

function tipsBlock() {
  if (!S.settings.tips || !S.scan) return null;
  const site = siteName();
  const tips = S.scan.tips || [];
  const items = [];
  const item = (title, ...text) => el("li", {}, el("b", {}, title), el("span", {}, ...text));
  if (tips.some((t) => t.kind === "email")) {
    items.push(item("Use a hidden email", `Give ${site} a forwarding address instead of your real one: `,
      link("Firefox Relay", "https://relay.firefox.com/"), ", ", link("SimpleLogin", "https://simplelogin.io/"), ", or iCloud+ Hide My Email on Apple devices."));
  }
  const optional = tips.filter((t) => t.kind === "optional");
  if (optional.length) {
    items.push(item(optional.length === 1 ? `Leave “${optional[0].label}” empty` : `Leave ${optional.length} optional fields empty`,
      "They look optional. The less you give, the less there is to share."));
  }
  if (tips.some((t) => t.kind === "marketing")) items.push(item("Untick the marketing box", "It's already ticked. Unticking it keeps you off their marketing lists."));
  if (S.scan.location === "granted") {
    const button = el("button", { class: "mini", onclick: (e) => blockLocation(e.currentTarget) }, "Block location");
    items.push(item("This site can see your location", "You allowed it before. ", button));
  }
  if (!items.length) return null;
  if (tips.length) runInPage(highlightTips, [TIP_TAGS]).catch(() => {});
  return el("section", { class: "tips" },
    el("h3", {}, S.scan.signup ? `${items.length} quick win${items.length > 1 ? "s" : ""} before you sign up` : "Quick win"),
    el("p", { class: "fine" }, tips.length ? "Highlighted on the page. Each takes seconds." : "Takes a second."),
    el("ol", {}, items));
}

/* ---------- Reading the policy ---------- */

async function check(url) {
  const button = document.getElementById("check");
  if (button) button.disabled = true;
  setStatus(`Reading ${url.replace(/^https?:\/\//i, "").slice(0, 46)}…`, "busy");
  try {
    const page = await api("/fetch-policy", { url, confirmed: true }, 60000);
    if (page.status !== "ok") throw new Error("That page doesn't look like a privacy policy. Paste the policy's own link.");
    setStatus("Checking what it says…", "busy");
    const { report } = await api("/report", { text: page.text });
    // Kept for this browser session only, so reopening the popup shows the card again. Not the policy text.
    S.result = { url: page.url, site: page.site || siteName(), fixes: page.fixes || [], report, gpcMentioned: GPC_WORDS.test(page.text), at: Date.now() };
    await chrome.storage.session.set({ [resultKey()]: S.result });
    cardView();
  } catch (error) {
    if (error.signedOut) return signedOutView();
    setStatus(error.message, "error");
    if (button) button.disabled = false;
  }
}

/* ---------- The card ---------- */

function cardView() {
  const { report, site } = S.result;
  const concern = Object.fromEntries((report.concerns || []).map((c) => [c.id, c.title]));
  const red = [], yellow = [], green = [], handled = [];
  for (const c of report.checks) {
    if (c.tone === "bad") (S.settings.gpc && (c.id === "sale" || c.id === "sharing") ? handled : red).push(c);
    else if (c.tone === "good") green.push(c);
    else yellow.push(c);
  }
  const nodes = [
    el("p", { class: "tight" }, el("strong", {}, `${site}'s privacy policy`)),
    el("p", { class: "fine top0" }, "What to be aware of before you agree. Tap a line to see the sentence."),
  ];
  if (handled.length) {
    nodes.push(el("div", { class: "ok" }, el("i", {}, "✓"), el("span", {},
      el("b", {}, handled.length > 1 ? "Selling and sharing your data: " : handled[0].id === "sale" ? "Selling your data: " : "Sharing your data: "),
      `your browser is already telling ${site} not to (Global Privacy Control). Companies must follow it in California and several other US states; elsewhere it may be ignored.`,
      S.result.gpcMentioned ? ` ${site}'s policy mentions this signal.` : "")));
  }
  if (red.length) nodes.push(group("red", "Worth knowing", red.map((c) => redLine(c, concern[c.id] || c.title))));
  if (yellow.length) nodes.push(group("yel", "Not clearly answered", yellow.map((c) => line(c, c.title, el("small", {}, c.label)))));
  if (green.length) nodes.push(group("grn", "In your favour", green.map((c) => line(c, c.title, el("small", {}, c.label)))));
  nodes.push(
    el("p", { class: "status", id: "status", role: "status" }),
    el("button", { class: "btn", onclick: () => openTab(`${S.api}/app.html?url=${encodeURIComponent(S.result.url)}`) }, "See the full report on Inkwell →"),
    rateStrip(site),
    el("p", { class: "fine" }, "Colours describe each answer, not the company. Wording checks, not legal advice. ",
      el("button", { class: "linklike", onclick: async () => { await chrome.storage.session.remove(resultKey()); S.result = null; homeView(); } }, "Check a different link")));
  show(el("div", { class: "pad" }, ...nodes));
}

/* ---------- Rate Inkwell: the stars open the review form on the Inkwell site ---------- */

function rateUrl(stars, site) {
  const q = new URLSearchParams({ write: "1" });
  if (stars) q.set("stars", String(stars));
  if (site) q.set("site", site);
  return `${S.api}/reviews.html?${q}`;
}

function rateStrip(site) {
  const stars = el("span", { class: "rate-stars", role: "group", "aria-label": "Rate Inkwell" },
    [1, 2, 3, 4, 5].map((n) => el("button", { type: "button", class: "rate-star", title: `${n} star${n > 1 ? "s" : ""}`,
      "aria-label": `Rate Inkwell ${n} out of 5`, onclick: () => openTab(rateUrl(n, site)) }, "★")));
  return el("div", { class: "rate" }, el("div", {}, el("b", {}, "Enjoying Inkwell?"), el("small", {}, "Tap a star to rate it on Inkwell.")), stars);
}

const group = (cls, title, lines) => el("section", { class: `grp ${cls}` }, el("h4", {}, el("i", {}), title, el("em", {}, String(lines.length))), lines);

function quote(c) {
  const text = c.evidence?.[0]?.text;
  return text ? el("blockquote", {}, `“${text}”`) : el("p", { class: "fine" }, c.meaning);
}

function line(c, title, extra) {
  return el("details", { class: "line" }, el("summary", {}, el("span", { class: "t" }, title), extra || null), quote(c));
}

function redLine(c, title) {
  const fix = fixFor(c);
  const tier = TIERS[fix.tier];
  const due = deadline(S.settings.region);
  const label = fix.tier === "now" ? `${tier.text} · ${fix.effort}` : fix.tier === "req" ? `${tier.text} · up to ${due.text}` : tier.text;
  const button = fix.button ? el("button", { class: `mini${fix.tier === "req" ? " ghost" : ""}`, onclick: (e) => {
    e.preventDefault(); e.stopPropagation(); fix.run(e.currentTarget);
  } }, fix.button) : null;
  return el("details", { class: "line fixrow" },
    el("summary", {}, el("span", { class: "t" }, title),
      el("span", { class: "meta" }, el("span", { class: `eff ${tier.cls}` }, `${tier.icon} ${label}`), button)),
    fix.note ? el("p", { class: "fine note" }, ...[fix.note].flat()) : null, quote(c));
}

/** The quickest way to limit one red answer, best first. */
function fixFor(c) {
  const { fixes, report, site } = S.result;
  const find = (...kinds) => { for (const k of kinds) { const f = fixes.find((x) => x.kind === k); if (f) return f; } return null; };
  const email = report.steps?.find((s) => s.kind === "request_delete")?.to;
  const where = (f) => (f.source === "known" ? `Opens ${site}'s own ${f.kind === "ads" ? "ad" : "privacy"} settings.`
    : `Opens “${f.text || f.label}”, linked from the policy.`);
  const open = (f) => ({ tier: "set", button: "Fix it", run: () => openTab(f.url), note: where(f) });
  switch (c.id) {
    case "sale":
    case "sharing": {
      const own = find("sale");
      // The button says what the person gets (the selling stops), not what we flip (the signal goes on).
      return { tier: "now", effort: "1 click", button: c.id === "sale" ? "Stop selling" : "Stop sharing", run: turnOnGpc, note: [
        "Tells every site you visit: don't sell or share my data (a browser signal called Global Privacy Control). Companies must follow it in California and several other US states; elsewhere it may be ignored. Chrome will ask to let Inkwell send it on all sites.",
        c.id === "sharing" ? " Companies that run the service for them still get your data." : "",
        own ? [" Or use ", link(own.text || "their own page", own.url), "."] : ""] };
    }
    case "ads": {
      const f = find("ads", "cookies", "settings");
      if (f) return open(f);
      return { tier: "set", button: "Fix it", run: () => openTab(INDUSTRY_ADS),
        note: `The policy links no ad settings. This ad-industry page turns off targeted ads from many ad companies at once, though not from ${site} itself.` };
    }
    case "location":
      return { tier: "now", effort: "1 click", button: "Block", run: (button) => blockLocation(button),
        note: "Stops this site from using your browser's location. Phone apps have their own setting." };
    case "retention":
    case "delete": {
      const f = find("delete", "rights", "settings");
      if (f) return open(f);
      if (email) return { tier: "req", button: "Send request", run: () => requestView("delete", email),
        note: `Asks ${site} to delete your data. Inkwell keeps track of the deadline for their reply.` };
      return { tier: "none", note: "The policy gives no way to change this." };
    }
    default:
      return { tier: "none", note: "This is how the service works; your choice is whether to use it." };
  }
}

/* ---------- One-click fixes ---------- */

async function turnOnGpc() {
  // Chrome may close the popup while it asks; the background worker then finishes the job (see "pending").
  chrome.storage.session.set({ pending: { gpc: true } });
  const allowed = await chrome.permissions.request({ origins: ["<all_urls>"] });
  if (!allowed) { chrome.storage.session.remove("pending"); return setStatus("Nothing changed: Chrome needs that permission to send the signal to every site.", "error"); }
  await msg("gpc-set", { on: true });
  chrome.storage.session.remove("pending");
  S.settings.gpc = true;
  if (S.result) cardView(); else settingsView();
}

async function blockLocation(button) {
  const origin = new URL(S.tab.url).origin;
  chrome.storage.session.set({ pending: { block: origin } });
  const allowed = await chrome.permissions.request({ permissions: ["contentSettings"] });
  chrome.storage.session.remove("pending");
  if (!allowed) return setStatus("Nothing changed: Chrome needs permission to change this site's location setting.", "error");
  await chrome.contentSettings.location.set({ primaryPattern: `${origin}/*`, setting: "block" });
  button.replaceWith(el("span", { class: "done" }, "✓ Blocked"));
}

/* ---------- ✉ Request: written for you, deadline tracked ---------- */

function requestView(kind, to) {
  const site = S.result.site;
  const draft = TEMPLATES[kind].make(site, S.auth?.name || "[your name]", S.auth?.email || "[the email on your account]");
  const text = el("textarea", { class: "mail", rows: "9", "aria-label": "The email" });
  text.value = `Subject: ${draft.subject}\n\n${draft.body}`;
  const parts = () => {
    const m = text.value.match(/^Subject:\s*(.*)\n\n([\s\S]*)$/);
    return m ? { subject: m[1], body: m[2] } : { subject: draft.subject, body: text.value };
  };
  const due = deadline(S.settings.region);
  const after = el("div");
  const send = el("a", { class: "btn", href: "#", onclick: async () => {
    send.href = mailto(to, parts());  // Set before the browser follows the link.
    const now = Date.now();
    const request = { id: crypto.randomUUID(), company: site, policy: S.result.url, kind, title: TEMPLATES[kind].title, to,
      subject: parts().subject, sentAt: now, dueAt: now + due.days * DAY, status: "waiting" };
    await saveRequests([request, ...(await listRequests())]);
    after.replaceChildren(el("div", { class: "ok" }, el("i", {}, "✓"), el("span", {},
      `Inkwell will track it. ${site} has until `, el("b", {}, shortDate(request.dueAt)), ` (${due.text}). We'll remind you on ${shortDate(request.dueAt - 7 * DAY)} if there's no reply. Didn't send it? Remove it in `,
      el("button", { class: "linklike", onclick: () => openTab(chrome.runtime.getURL("requests.html")) }, "My requests"), ".")));
  } }, "Open in my email app and send");
  show(el("div", { class: "pad" },
    el("button", { class: "linklike back", onclick: cardView }, "← Back"),
    el("p", { class: "tight" }, el("strong", {}, `Request: ${TEMPLATES[kind].title.toLowerCase()}`)),
    el("p", { class: "fine top0" }, `To: ${to}. You can edit the text first.`),
    text, send,
    el("button", { class: "btn ghost", onclick: async (e) => {
      try { const p = parts(); await navigator.clipboard.writeText(`${p.subject}\n\n${p.body}`); e.currentTarget.textContent = "Copied"; } catch { text.select(); }
    } }, "Copy the text instead"),
    el("p", { class: "fine" }, "A template, not legal advice. Nothing is sent unless you send it from your own email."), after));
}

/* ---------- Settings ---------- */

function settingsView() {
  const back = () => (S.result ? cardView() : S.config && (!S.config.enabled || (S.auth && !S.auth.open)) && S.tab ? homeView() : init());
  const toggle = (on, onchange) => el("input", { type: "checkbox", class: "switch", checked: on, onchange });
  const gpc = toggle(S.settings.gpc, async (e) => {
    if (e.target.checked) { e.target.checked = false; await turnOnGpc(); return; }
    await msg("gpc-set", { on: false }); S.settings.gpc = false;
  });
  const tips = toggle(S.settings.tips, async (e) => { S.settings.tips = e.target.checked; await saveSettings({ tips: e.target.checked }); });
  const region = el("select", { class: "input", onchange: async (e) => { S.settings.region = e.target.value; await saveSettings({ region: e.target.value }); } },
    el("option", { value: "us", selected: S.settings.region === "us" }, "United States (45 days)"),
    el("option", { value: "eu", selected: S.settings.region === "eu" }, "EU or UK (1 month)"),
    el("option", { value: "other", selected: S.settings.region === "other" }, "Somewhere else (we'll use 45 days)"));
  const server = el("input", { class: "input", type: "url", value: S.settings.api });
  const signedIn = S.auth && !S.auth.open;
  show(el("div", { class: "pad" },
    el("button", { class: "linklike back", onclick: back }, "← Back"),
    el("p", { class: "tight" }, el("strong", {}, "Settings")),
    el("label", { class: "opt" }, gpc, el("span", {}, el("b", {}, "Tell every site: don't sell or share my data"),
      "Sends the Global Privacy Control signal to every website you visit. In California and several other US states, companies must follow it.")),
    el("label", { class: "opt" }, tips, el("span", {}, el("b", {}, "Show sign-up quick wins"),
      "Points out optional fields and pre-ticked boxes on sign-up pages, only when you open Inkwell.")),
    el("label", { class: "field" }, el("b", {}, "Where you live"), el("span", { class: "fine" }, "Sets how long companies have to answer your requests."), region),
    el("button", { class: "btn ghost", onclick: () => openTab(chrome.runtime.getURL("requests.html")) }, "My requests"),
    el("button", { class: "btn ghost rate-btn", onclick: () => openTab(rateUrl(0, S.result?.site)) }, "★ Rate Inkwell"),
    el("button", { class: "linklike small-link", onclick: () => openTab(`${S.api}/reviews.html`) }, "Read what others think"),
    el("p", { class: "fine" }, signedIn ? `Signed in as ${S.auth.name || S.auth.email}. ` : "Not signed in. ",
      signedIn ? el("button", { class: "linklike", onclick: async () => { await msg("sign-out"); S.auth = null; signedOutView(); } }, "Sign out") : null),
    el("details", { class: "fold" }, el("summary", {}, "Advanced: Inkwell server"),
      el("p", { class: "fine" }, "For testing with a local server, use http://127.0.0.1:7860."),
      el("form", { class: "manual", onsubmit: async (e) => {
        e.preventDefault();
        const value = server.value.trim().replace(/\/+$/, "");
        if (!/^https?:\/\/[^/]+$/i.test(value)) return;
        await saveSettings({ api: value }); await msg("sign-out"); init();
      } }, server, el("button", { class: "btn ghost small", type: "submit" }, "Save")))));
}

document.getElementById("open-settings").addEventListener("click", settingsView);
init();
