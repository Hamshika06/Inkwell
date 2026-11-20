// The dashboard: all saved work, with "start a new check" always available. Opening old work never replaces
// anything, and if saved work can't be loaded the page says so instead of looking empty.
import { renderAccountMenu } from "./account.js";
import { currentUser, isVerified, startAuth, toggleTheme } from "./auth.js";
import { initTour } from "./tour.js";
import { openStore } from "./store.js";
import { el } from "./shared.js";

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
  box.replaceChildren(el("ul", { class: "card saved-list" }, items.map(row)));
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
