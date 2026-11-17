// Compare two privacy policies: the same 8 answers side by side, differences first. It states what each policy
// says and never picks a winner. Each side takes a link or the policy text.
import { renderAccountMenu } from "./account.js";
import { API, authHeaders, currentUser, isVerified, startAuth, toggleTheme } from "./auth.js";
import { asLink, el } from "./shared.js";

const $ = (id) => document.getElementById(id);
const sides = [{ key: "a", label: "Company A" }, { key: "b", label: "Company B" }];
const page = { ctx: { enabled: false }, results: null, open: {}, sameOpen: false };

function toLogin() { location.replace("login.html?next=%2Fcompare.html"); }
function setStatus(text, kind = "") { $("status").textContent = text; $("status").className = `status ${kind}`; }
function setSide(side, text, kind = "") { const box = $(`status-${side.key}`); box.textContent = text; box.className = `status ${kind}`; }

async function api(path, body, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { "Content-Type": "application/json", ...(await authHeaders(page.ctx)) };
    const response = await fetch(API + path, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if ((response.status === 401 || response.status === 403) && page.ctx.enabled) { toLogin(); throw new Error("Please sign in again."); }
    if (!response.ok) throw new Error(data.detail || `${response.status} ${response.statusText}`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The server took too long to answer. If it was asleep, try again in a minute.");
    if (error instanceof TypeError) throw new Error("Can't reach the Inkwell server. It may be waking up; try again shortly.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- Reading each side ---------- */

function askAboutLink(side, found) {
  const box = $(`confirm-${side.key}`);
  side.waiting = true;
  box.replaceChildren(
    el("p", {}, el("strong", {}, `We found this policy for ${found.site}:`), " ",
      el("a", { href: found.url, target: "_blank", rel: "noopener noreferrer nofollow" }, found.url)),
    el("p", { class: "fine" }, "Is this the right page?"),
    el("div", { class: "request-actions" },
      el("button", { type: "button", class: "btn btn-primary", onclick: async () => {
        box.hidden = true; side.waiting = false;
        if (await readLink(side, found.url, true) && !sides.some((s) => s.waiting)) compare();
      } }, "Yes, use it"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => {
        box.hidden = true; side.waiting = false;
        setSide(side, "Paste the link to the policy itself, or its text.");
        $(`box-${side.key}`).focus(); $(`box-${side.key}`).select();
      } }, "No, I'll paste it")));
  box.hidden = false;
}

/** Fills the box with the page's text. False when it needs an answer from the reader, or couldn't be read. */
async function readLink(side, url, confirmed) {
  setSide(side, `Reading ${url.replace(/^https?:\/\//i, "").slice(0, 50)}…`, "busy");
  try {
    const found = await api("/fetch-policy", { url, confirmed }, 60000);
    if (found.status === "confirm") {
      setSide(side, "");
      askAboutLink(side, found);
      return false;
    }
    $(`box-${side.key}`).value = found.text;
    side.source = { site: found.site, text: found.text };
    setSide(side, "Policy read. The text is in the box.");
    return true;
  } catch (error) {
    setSide(side, error.message, "error");
    return false;
  }
}

function nameOf(side, report, text) {
  const source = side.source?.text === text ? side.source : null;
  if (!source) return report.company || side.label;
  return (report.company || "").split(/\s+/).find((w) => w.toLowerCase() === source.site.toLowerCase()) || source.site;
}

async function compare() {
  setStatus("");
  for (const side of sides) { side.waiting = false; $(`confirm-${side.key}`).hidden = true; setSide(side, ""); }
  const empty = sides.filter((s) => !$(`box-${s.key}`).value.trim());
  if (empty.length) { for (const s of empty) setSide(s, "Paste a link or the policy text here.", "error"); return; }
  $("compare").disabled = true;
  try {
    const ready = await Promise.all(sides.map((s) => {
      const link = asLink($(`box-${s.key}`).value);
      return link ? readLink(s, link, false) : true;
    }));
    if (!ready.every(Boolean)) return;
    setStatus("Comparing…", "busy");
    const texts = sides.map((s) => $(`box-${s.key}`).value);
    const reports = await Promise.all(texts.map((text) => api("/report", { text })));
    const results = sides.map((s, i) => ({ name: nameOf(s, reports[i].report, texts[i]), report: reports[i].report }));
    if (results[0].name === results[1].name) results.forEach((r, i) => { r.name += ` (${sides[i].label.slice(-1)})`; });
    Object.assign(page, { results, open: {}, sameOpen: false });
    setStatus("Done. The comparison is below.");
    render();
    $("compare-results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    $("compare").disabled = false;
  }
}

/* ---------- The comparison ---------- */

const answer = (check) => (check.state === "missing" ? "Not found" : check.label);
const quote = (e) => el("blockquote", { class: "receipt plain-receipt" }, el("span", { class: "receipt-mark", "aria-hidden": "true" }, "“"), e.text);

function detail(check) {
  const more = check.evidence_count - 1;
  return el("div", { class: "cmp-side" }, el("p", { class: "check-meaning" }, check.meaning),
    check.evidence.length ? quote(check.evidence[0]) : null,
    more > 0 ? el("p", { class: "fine" }, `${more} more ${more === 1 ? "sentence" : "sentences"} like this in the policy.`) : null,
    check.counter?.length ? el("div", { class: "counter" }, el("span", {}, "But the policy also says:"), quote(check.counter[0])) : null);
}

function row(item, [a, b]) {
  const open = !!page.open[item.id];
  return el("li", { class: `cmp-row${open ? " open" : ""}` },
    el("button", { type: "button", class: "cmp-toggle", "aria-expanded": String(open), "data-row": item.id,
      onclick: () => { page.open[item.id] = !open; render(); document.querySelector(`[data-row="${item.id}"]`)?.focus(); } },
      el("span", { class: "cmp-title" }, el("span", { class: "concern-chev", "aria-hidden": "true" }, "▸"), item.title),
      el("span", { class: "cmp-answer" }, el("small", {}, a.name), answer(item.a)),
      el("span", { class: "cmp-answer" }, el("small", {}, b.name), answer(item.b))),
    open ? el("div", { class: "cmp-detail" }, el("span", {}), detail(item.a), detail(item.b)) : null);
}

function render() {
  const [a, b] = page.results;
  const items = a.report.checks.map((check) => {
    const other = b.report.checks.find((c) => c.id === check.id);
    return { id: check.id, title: check.title, a: check, b: other, differs: check.state !== other.state };
  });
  const differ = items.filter((i) => i.differs), same = items.filter((i) => !i.differs);
  const headers = el("div", { class: "cmp-header", "aria-hidden": "true" }, el("span", {}), el("strong", {}, a.name), el("strong", {}, b.name));
  $("compare-results").hidden = false;
  $("compare-results").replaceChildren(el("article", { class: "card compare-card" },
    el("h2", {}, differ.length ? `${a.name} and ${b.name} differ on ${differ.length} of ${items.length} answers` : `${a.name} and ${b.name} give the same ${items.length} answers`),
    el("p", { class: "fine" }, "“Not found” means our wording checks didn't find it in this policy. It isn't proof of what the company does, so read the sentences before deciding."),
    differ.length ? [headers, el("ul", { class: "cmp-list" }, differ.map((i) => row(i, page.results)))] : null,
    same.length ? el("details", { class: "all-answers", open: page.sameOpen || !differ.length, ontoggle: (e) => { page.sameOpen = e.target.open; } },
      el("summary", {}, `They say the same on ${same.length}`), el("ul", { class: "cmp-list" }, same.map((i) => row(i, page.results)))) : null,
    el("div", { class: "request-actions compare-again" }, el("button", { type: "button", class: "btn", onclick: reset }, "Start another comparison"))));
}

function reset() {
  page.results = null;
  $("compare-results").hidden = true;
  for (const side of sides) { $(`box-${side.key}`).value = ""; $(`confirm-${side.key}`).hidden = true; setSide(side, ""); side.source = null; side.waiting = false; }
  setStatus("");
  scrollTo({ top: 0, behavior: "smooth" });
  $("box-a").focus();
}

async function connect() {
  $("theme").addEventListener("click", toggleTheme);
  try {
    page.ctx = await startAuth();
  } catch {
    document.body.dataset.auth = "ready";
    setStatus("The server is waking up. Reload in a minute.", "error");
    return;
  }
  const user = await currentUser(page.ctx);
  document.body.dataset.auth = "ready";
  if (page.ctx.enabled && !user) {  // Compare is an account feature.
    $("compare-form").hidden = true; $("app-nav").hidden = true; $("compare-locked").hidden = false;
    return;
  }
  if (user && !(await isVerified(user).catch(() => true))) return toLogin();
  if (page.ctx.enabled && user) renderAccountMenu($("user"), page.ctx, user);
  $("compare").addEventListener("click", compare);
  for (const side of sides) $(`box-${side.key}`).addEventListener("input", () => { $(`confirm-${side.key}`).hidden = true; side.waiting = false; setSide(side, ""); });
}

connect();
