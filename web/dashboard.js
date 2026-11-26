// The dashboard: all saved work, with "start a new check" always available. Opening old work never replaces
// anything, and if saved work can't be loaded the page says so instead of looking empty.
import { renderAccountMenu } from "./account.js";
import { currentUser, isVerified, startAuth, toggleTheme } from "./auth.js";
import { initTour } from "./tour.js";
import { openStore } from "./store.js";
import { el } from "./shared.js";
import { blocksSvg, exposureCells, limitedBy } from "./visuals.js";
import { miniBar, mountShell, setRecent } from "./shell.js";

const DECISIONS = { steps: "Limiting it", agree: "Accepted as is", leave: "Not accepted" };
const $ = (id) => document.getElementById(id);
let store;

const dateText = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");

/** Where a saved check stands: what's left to fix, whether the policy changed, or done. */
function statusOf(item) {
  const concerns = item.report?.concerns || [];
  const isLimited = limitedBy(item.done || {});
  const fixable = concerns.filter((c) => c.fixable), left = fixable.filter((c) => !isLimited(c));
  const changed = (item.history || []).length > 0;
  const decided = item.decision === "agree" || item.decision === "leave";
  const kind = left.length && !decided ? "action" : "done";
  return { kind, changed, left: left.length, fixable: fixable.length, decided };
}

const FILTERS = [["action", "Needs action"], ["changed", "Policy changed"], ["done", "Done"], ["all", "All"]];
let filter = null;

function row(item) {
  const st = statusOf(item);
  const open = `app.html?open=${encodeURIComponent(item.id)}`;
  const cells = item.report?.checks ? exposureCells(item.report, item.done) : null;
  const pill = st.kind === "action" ? el("span", { class: "dpill red" }, `${st.left} to fix`)
    : st.decided ? el("span", { class: "dpill" }, DECISIONS[item.decision])
    : st.fixable ? el("span", { class: "dpill green" }, "✓ All limited") : el("span", { class: "dpill" }, "Nothing to fix");
  const primary = st.kind === "action" ? el("a", { class: "btn btn-primary", href: `${open}&tab=fix` }, "Fix next")
    : st.changed ? el("a", { class: "btn", href: open }, "See changes") : el("a", { class: "btn", href: open }, "Open");
  return el("li", { class: "saved" },
    el("div", { class: "saved-main" },
      el("a", { class: "saved-name", href: open }, item.name),
      el("span", { class: "saved-status" }, cells ? miniBar(cells) : null, pill,
        st.changed ? el("span", { class: "dpill amber" }, `⚑ Policy changed since ${dateText(item.history[0].checkedAt)}`) : null),
      el("span", { class: "fine" }, `Last checked ${dateText(item.checkedAt)}`)),
    el("div", { class: "saved-actions" }, primary,
      el("details", { class: "row-more" }, el("summary", { class: "btn btn-ghost", "aria-label": `More for ${item.name}` }, "⋯"),
        el("div", { class: "row-menu", role: "menu" },
          el("a", { role: "menuitem", href: `app.html?recheck=${encodeURIComponent(item.id)}` }, "Check again"),
          el("button", { type: "button", role: "menuitem", onclick: () => rename(item) }, "Rename"),
          el("button", { type: "button", role: "menuitem", class: "menu-danger", onclick: () => remove(item) }, "Remove")))));
}

function listFor(items) {
  const counts = { action: 0, changed: 0, done: 0, all: items.length };
  for (const it of items) { const st = statusOf(it); counts[st.kind] += 1; if (st.changed) counts.changed += 1; }
  if (!filter || (filter !== "all" && !counts[filter])) filter = counts.action ? "action" : "all";
  const shown = items.filter((it) => { const st = statusOf(it); return filter === "all" || (filter === "changed" ? st.changed : st.kind === filter); });
  const tabs = el("div", { class: "dash-filters", role: "group", "aria-label": "Show" }, FILTERS.filter(([k]) => k === "all" || counts[k]).map(([k, label]) =>
    el("button", { type: "button", class: filter === k ? "on" : null, "aria-pressed": String(filter === k), onclick: () => { filter = k; load(); } }, `${label} · ${counts[k]}`)));
  return [tabs, el("ul", { class: "card saved-list" }, shown.map(row))];
}

async function load() {
  const box = $("dash-list");
  let items;
  try {
    items = await store.listPolicies();
  } catch {
    box.replaceChildren(el("div", { class: "card dash-note" }, el("h2", {}, "We couldn't load your saved work"),
      el("p", {}, "It hasn't been lost. Check your connection and try again."),
      el("button", { type: "button", class: "btn", onclick: load }, "Try again")));
    return;
  }
  if (!items.length) {
    box.replaceChildren(el("div", { class: "card dash-note" }, el("h2", {}, "Nothing saved yet"),
      el("p", {}, "Check your first policy and it will appear here."),
      el("a", { class: "btn btn-primary", href: "app.html" }, "Start a new check")));
    return;
  }
  items.sort((a, b) => (b.checkedAt || "").localeCompare(a.checkedAt || ""));
  setRecent(Object.fromEntries(items.map((it) => [it.id, it])));
  box.replaceChildren(deck(items), ...listFor(items));
}

/* ---------- The deck: saved checks as 3D cards, each showing its exposure blocks ---------- */

let at = 0;
function deck(items) {
  const withReport = items.filter((i) => i.report?.checks);
  if (withReport.length < 2) return el("span");  // A deck of one adds nothing; the list says it all.
  at = Math.min(at, withReport.length - 1);
  const stage = el("div", { class: "deck-stage", role: "group", "aria-roledescription": "carousel", "aria-label": "Your saved checks" });
  const draw = () => {
    stage.replaceChildren(...withReport.map((item, i) => {
      const off = i - at, cells = exposureCells(item.report, item.done);
      const left = cells.filter((c) => c.kind === "red").length;
      const open = `app.html?open=${encodeURIComponent(item.id)}`;
      return el("a", { class: `deck-card${off === 0 ? " front" : ""}`, href: open, style: `--off:${off};--abs:${Math.abs(off)}`,
        tabindex: off === 0 ? "0" : "-1", "aria-hidden": Math.abs(off) > 2 ? "true" : null,
        "aria-label": `${item.name}: exposure ${left} of ${cells.length}. Open`,
        onclick: (e) => { if (off !== 0) { e.preventDefault(); at = i; draw(); } } },
        el("p", { class: "deck-date" }, `Checked ${dateText(item.checkedAt)}`),
        el("h3", {}, item.name),
        blocksSvg(cells, { labels: false, small: true }),
        el("p", { class: "deck-num" }, el("b", {}, String(left)), ` of ${cells.length} exposure`));
    }));
    nav.querySelector(".deck-open").href = `app.html?open=${encodeURIComponent(withReport[at].id)}`;
    nav.querySelector(".deck-open").textContent = `Open ${withReport[at].name}`;
    nav.querySelector(".deck-prev").disabled = at === 0;
    nav.querySelector(".deck-next").disabled = at === withReport.length - 1;
  };
  const go = (d) => { at = Math.max(0, Math.min(withReport.length - 1, at + d)); draw(); };
  const nav = el("div", { class: "deck-nav" },
    el("button", { type: "button", class: "btn deck-prev", "aria-label": "Previous check", onclick: () => go(-1) }, "←"),
    el("a", { class: "btn btn-primary deck-open", href: "#" }, "Open"),
    el("button", { type: "button", class: "btn deck-next", "aria-label": "Next check", onclick: () => go(1) }, "→"));
  stage.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft") go(-1); if (e.key === "ArrowRight") go(1); });
  let x0 = null;
  stage.addEventListener("pointerdown", (e) => { x0 = e.clientX; });
  stage.addEventListener("pointerup", (e) => { if (x0 != null && Math.abs(e.clientX - x0) > 40) go(e.clientX < x0 ? 1 : -1); x0 = null; });
  // Two-finger swipe on a trackpad (or Shift + mouse wheel): sideways scrolling flips through the cards.
  // Up/down scrolling is left alone so the page still scrolls.
  let pull = 0, quietUntil = 0, settle = 0;
  stage.addEventListener("wheel", (e) => {
    const dx = e.shiftKey && !e.deltaX ? e.deltaY : e.deltaX;
    if (Math.abs(dx) <= Math.abs(e.deltaY) && !e.shiftKey) return;
    e.preventDefault();
    clearTimeout(settle); settle = setTimeout(() => { pull = 0; }, 180);
    if (performance.now() < quietUntil) return;  // one flick moves one card, not five
    pull += dx;
    if (Math.abs(pull) > 45) { const before = at; go(pull > 0 ? 1 : -1); pull = 0; if (at !== before) quietUntil = performance.now() + 420; }
  }, { passive: false });
  draw();
  return el("section", { class: "deck", "aria-label": "Your checks at a glance" }, stage, nav);
}

async function rename(item) {
  const name = prompt("Rename this check", item.name)?.trim().slice(0, 80);
  if (!name || name === item.name) return;
  try { await store.putPolicy(item.id, { name }); } catch { alert("Couldn't rename it. Try again."); }
  load();
}

async function remove(item) {
  if (!confirm(`Remove “${item.name}” from your dashboard? This can't be undone.`)) return;
  try { await store.deletePolicy(item.id); } catch { alert("Couldn't remove it. Try again."); }
  load();
}

async function connect() {
  mountShell("dashboard.html");
  $("theme").addEventListener("click", toggleTheme);
  let ctx;
  try {
    ctx = await startAuth();
  } catch {
    document.body.dataset.auth = "ready";
    $("dash-list").replaceChildren(el("div", { class: "card dash-note" }, el("h2", {}, "The server is waking up"), el("p", {}, "Your saved work is safe. Reload in a minute.")));
    return;
  }
  const user = await currentUser(ctx);
  const login = () => location.replace("login.html?next=%2Fdashboard.html");
  if (ctx.enabled && !user) return login();
  if (user && !(await isVerified(user).catch(() => true))) return login();
  if (ctx.enabled && user) renderAccountMenu($("user"), ctx, user);
  document.body.dataset.auth = "ready";
  $("dash-list").replaceChildren(el("p", { class: "fine" }, "Loading your saved work…"));
  store = await openStore(ctx, user);
  if (store.mode !== "account") { $("dash-where").hidden = false; $("dash-where").textContent = "Saved in this browser only."; }
  await load();
  initTour({ signedIn: true });
}

connect();
