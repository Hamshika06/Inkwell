// The dashboard: all saved work, with "start a new check" always available. Opening old work never replaces
// anything, and if saved work can't be loaded the page says so instead of looking empty.
import { renderAccountMenu } from "./account.js";
import { currentUser, isVerified, startAuth, toggleTheme } from "./auth.js";
import { initTour } from "./tour.js";
import { openStore } from "./store.js";
import { el } from "./shared.js";
import { blocksSvg, exposureCells } from "./visuals.js";

const DECISIONS = { steps: "Limiting it", agree: "Accepted as is", leave: "Not accepted" };
const $ = (id) => document.getElementById(id);
let store;

const dateText = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");

function row(item) {
  const done = Object.values(item.done || {}).filter(Boolean).length;
  const meta = [`Last checked ${dateText(item.checkedAt)}`, item.decision ? DECISIONS[item.decision] : "No decision yet",
    item.stepsTotal ? `${done} of ${item.stepsTotal} steps done` : null].filter(Boolean).join(" · ");
  const open = `app.html?open=${encodeURIComponent(item.id)}`;
  return el("li", { class: "saved" },
    el("div", { class: "saved-main" }, el("a", { class: "saved-name", href: open }, item.name), el("span", { class: "fine" }, meta)),
    el("div", { class: "saved-actions" },
      el("a", { class: "btn btn-primary", href: open }, "Open"),
      el("a", { class: "btn", href: `app.html?recheck=${encodeURIComponent(item.id)}` }, "Check again"),
      el("button", { type: "button", class: "btn btn-ghost", "aria-label": `Rename ${item.name}`, onclick: () => rename(item) }, "Rename"),
      el("button", { type: "button", class: "btn btn-ghost", "aria-label": `Remove ${item.name}`, onclick: () => remove(item) }, "Remove")));
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
  box.replaceChildren(deck(items), el("ul", { class: "card saved-list" }, items.map(row)));
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
