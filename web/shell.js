// The app shell for the product pages (checker, dashboard, compare): one left rail with search (⌘K), every page,
// and your recent checks, instead of a different top bar on each page. On phones the rail becomes a drawer behind ☰,
// and the top bar keeps only the logo, the server light and your account, so nothing scrolls sideways.
import { openPalette } from "./palette.js";
import { exposureCells } from "./visuals.js";
import { el } from "./shared.js";

const NAV = [
  ["✎", "Check a policy", "app.html"], ["◫", "Dashboard", "dashboard.html"], ["⇄", "Compare", "compare.html"],
  ["◎", "Data map", "data-map.html"], ["★", "Reviews", "reviews.html"],
];
const COLOR = { red: "#e5534b", fixed: "#8fd3ad", yellow: "#e9b949", green: "#2f9e62" };
let recent = loadRecent();
let recentBox = null;
const DESKTOP = "(min-width: 981px)";

/** Recent checks are kept for this browser tab only, so pages that don't load your saved checks (map, reviews, guides) can still list them. */
function loadRecent() { try { return JSON.parse(sessionStorage.getItem("inkwell-recent") || "[]"); } catch { return []; } }

/** The saved checks the rail and the palette show: [{ id, name, url, checkedAt, cells }], newest first. */
export const getRecent = () => recent;

/** A small red/yellow/green strip for a saved report. */
export function miniBar(cells) {
  return el("span", { class: "mini-bar", "aria-hidden": "true" }, cells.map((c) => el("i", { style: `background:${COLOR[c.kind]}` })));
}

/** Pages call this once their saved checks are loaded (a map of id → saved doc). */
export function setRecent(saved) {
  recent = Object.entries(saved || {}).filter(([, d]) => d?.report?.checks)
    .map(([id, d]) => ({ id, name: d.name, url: d.url || "", checkedAt: d.checkedAt || "", cells: exposureCells(d.report, d.done) }))
    .sort((a, b) => b.checkedAt.localeCompare(a.checkedAt));
  try { sessionStorage.setItem("inkwell-recent", JSON.stringify(recent.slice(0, 6))); } catch { /* not kept */ }
  renderRecent();
}

function renderRecent() {
  if (!recentBox) return;
  const here = new URLSearchParams(location.search).get("open");
  recentBox.replaceChildren(...(recent.length ? [el("h6", {}, "Recent checks"), ...recent.slice(0, 6).map((r) =>
    el("a", { class: `shell-recent${here === r.id ? " on" : ""}`, href: `app.html?open=${encodeURIComponent(r.id)}`, title: `Open ${r.name}` },
      el("span", { class: "shell-recent-name" }, r.name), miniBar(r.cells)))] : []));
}

/** Back goes to the page you came from on Inkwell; if you arrived from outside, it goes to the home page. */
function goBack() {
  let fromHere = false;
  try { fromHere = !!document.referrer && new URL(document.referrer).origin === location.origin && document.referrer !== location.href; } catch { /* treat as outside */ }
  if (fromHere && history.length > 1) history.back(); else location.href = "/";
}

/** Builds the rail and wires ☰, ✕, ← Back and ⌘K. active: the file name of this page. */
export function mountShell(active) {
  document.body.classList.add("has-shell");
  const page = location.pathname.split("/").pop() || "app.html";
  const nav = el("nav", { class: "shell-nav", "aria-label": "Inkwell" }, NAV.map(([icon, label, href]) =>
    el("a", { href, class: (active || page) === href ? "on" : null, "aria-current": (active || page) === href ? "page" : null },
      el("i", { "aria-hidden": "true" }, icon), label)));
  recentBox = el("div", { class: "shell-recents" });
  const closeBtn = el("button", { type: "button", class: "shell-close", "aria-label": "Close the menu", title: "Close the menu", onclick: () => closeRail() }, "✕");
  const rail = el("aside", { class: "shell", id: "shell", "aria-label": "Inkwell navigation" },
    el("div", { class: "shell-top" },
      el("a", { class: "brand shell-brand", href: "/" }, el("img", { class: "brand-mark", src: "logo.svg?v=2", alt: "" }), el("span", { class: "brand-name" }, "Inkwell")),
      closeBtn),
    el("button", { type: "button", class: "shell-search", onclick: () => { closeDrawer(); openPalette(); } },
      el("span", {}, "⌕ Search or paste"), el("kbd", {}, navigator.platform?.startsWith("Mac") ? "⌘K" : "Ctrl K")),
    nav, recentBox,
    el("div", { class: "shell-foot" }, el("a", { href: "guides.html" }, "Guides"), el("span", { "aria-hidden": "true" }, "·"), el("a", { href: "/" }, "Home"),
      el("span", { "aria-hidden": "true" }, "·"),
      el("button", { type: "button", class: "shell-tour", onclick: () => { closeDrawer(); document.querySelector(".tour-launch")?.click(); } }, "Tour")));
  const scrim = el("div", { class: "shell-scrim", hidden: true, onclick: () => closeDrawer() });
  document.body.prepend(rail, scrim);
  const menuBtn = el("button", { type: "button", class: "icon-btn shell-menu", "aria-label": "Open the menu", "aria-controls": "shell", "aria-expanded": "false",
    title: "Open the menu", onclick: () => openRail() }, "☰");
  const backBtn = el("button", { type: "button", class: "btn btn-ghost shell-back", title: "Go back to the previous page", "aria-label": "Back", onclick: goBack },
    el("span", { "aria-hidden": "true" }, "←"), el("span", { class: "shell-back-text" }, " Back"));
  const bar = document.querySelector(".topbar, .nav");
  bar?.prepend(menuBtn, backBtn);
  const desktop = () => matchMedia(DESKTOP).matches;
  let railClosed = false;
  try { railClosed = localStorage.getItem("inkwell-rail") === "closed"; } catch { /* default open */ }
  const sync = () => {
    document.body.classList.toggle("rail-closed", railClosed);
    menuBtn.setAttribute("aria-expanded", String(desktop() ? !railClosed : document.body.classList.contains("drawer-open")));
  };
  function openRail() {
    if (!desktop()) return document.body.classList.contains("drawer-open") ? closeDrawer() : openDrawer();
    railClosed = false; try { localStorage.removeItem("inkwell-rail"); } catch { /* not remembered */ }
    sync(); rail.querySelector(".shell-search")?.focus();
  }
  function closeRail() {
    if (!desktop()) return closeDrawer();
    railClosed = true; try { localStorage.setItem("inkwell-rail", "closed"); } catch { /* not remembered */ }
    sync(); menuBtn.focus();
  }
  function openDrawer() { document.body.classList.add("drawer-open"); scrim.hidden = false; sync(); rail.querySelector("a, button")?.focus(); }
  function closeDrawer() { document.body.classList.remove("drawer-open"); scrim.hidden = true; sync(); }
  matchMedia(DESKTOP).addEventListener?.("change", () => { closeDrawer(); sync(); });
  addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); closeDrawer(); openPalette(); }
    if (e.key === "Escape" && document.body.classList.contains("drawer-open")) closeDrawer();
  });
  sync();
  renderRecent();
}
