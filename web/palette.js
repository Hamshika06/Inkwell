// ⌘K / Ctrl K: one box for everything. Type or paste a site to check it, jump to a saved report, or run an
// action (new check, compare, dashboard, theme). Arrow keys move, Enter runs, Esc closes.
import { toggleTheme } from "./auth.js";
import { getRecent, miniBar } from "./shell.js";
import { asLink, el } from "./shared.js";

const ACTIONS = [
  ["✎", "New check", () => go("app.html")],
  ["▸", "Try the Pigeonpost sample", () => go("app.html?sample=1")],
  ["◫", "Open your dashboard", () => go("dashboard.html")],
  ["⇄", "Compare two policies", () => go("compare.html")],
  ["◎", "Where your data goes (data map)", () => go("data-map.html")],
  ["★", "Reviews", () => go("reviews.html")],
  ["◐", "Switch light or dark theme", () => toggleTheme()],
];
const go = (href) => { location.href = href; };

/** Check a link or text. On the checker page it runs in place; elsewhere it opens the checker. */
function check(value) {
  if (typeof window.inkwellCheck === "function") return window.inkwellCheck(value);
  go(`app.html?check=${encodeURIComponent(value)}`);
}

let open = null;

export function openPalette(initial = "") {
  if (open) return open.input.focus();
  const input = el("input", { class: "pal-input", type: "text", value: initial, placeholder: "Check a site, open a report, or type a command…",
    "aria-label": "Search Inkwell or paste a link", role: "combobox", "aria-expanded": "true", "aria-controls": "pal-list", autocomplete: "off", spellcheck: "false" });
  const list = el("div", { class: "pal-list", id: "pal-list", role: "listbox" });
  const box = el("div", { class: "pal", role: "dialog", "aria-modal": "true", "aria-label": "Command palette" },
    input, list,
    el("div", { class: "pal-foot" }, el("span", {}, el("kbd", {}, "↑↓"), " move"), el("span", {}, el("kbd", {}, "↵"), " open"), el("span", {}, el("kbd", {}, "esc"), " close")));
  const back = el("div", { class: "pal-back", onclick: (e) => { if (e.target === back) close(); } }, box);
  const before = document.activeElement;
  let items = [], at = 0;

  function build() {
    const q = input.value.trim(), lq = q.toLowerCase();
    const groups = [];
    const link = q && asLink(q);
    if (link) groups.push(["Check", [{ icon: "✎", label: `Check ${link.replace(/^https?:\/\//i, "").replace(/\/.*$/, "")}'s privacy policy`, run: () => check(link) }]]);
    else if (q.length > 120) groups.push(["Check", [{ icon: "✎", label: "Check this pasted text", run: () => check(q) }]]);
    const reports = getRecent().filter((r) => !lq || r.name.toLowerCase().includes(lq) || r.url.toLowerCase().includes(lq)).slice(0, 5)
      .map((r) => ({ icon: "◫", label: r.name, extra: miniBar(r.cells), run: () => go(`app.html?open=${encodeURIComponent(r.id)}`) }));
    if (reports.length) groups.push(["Your reports", reports]);
    const actions = ACTIONS.filter(([, label]) => !lq || label.toLowerCase().includes(lq)).map(([icon, label, run]) => ({ icon, label, run }));
    if (actions.length) groups.push(["Actions", actions]);
    if (!groups.length) groups.push(["", [{ icon: "✎", label: `Check “${q.slice(0, 40)}”`, run: () => check(q) }]]);
    items = groups.flatMap(([, g]) => g);
    at = Math.min(at, items.length - 1);
    let n = 0;
    list.replaceChildren(...groups.flatMap(([title, g]) => [title ? el("p", { class: "pal-group" }, title) : null,
      ...g.map((it) => { const i = n++; return el("div", { class: `pal-item${i === at ? " on" : ""}`, role: "option", id: `pal-${i}`, "aria-selected": String(i === at),
        onclick: () => runAt(i), onpointermove: () => { if (at !== i) { at = i; mark(); } } },
        el("span", { class: "pal-ico", "aria-hidden": "true" }, it.icon), el("span", { class: "pal-label" }, it.label), it.extra || null,
        i === at ? el("kbd", {}, "↵") : null); })]).filter(Boolean));
    input.setAttribute("aria-activedescendant", `pal-${at}`);
  }
  function mark() { build(); list.querySelector(".pal-item.on")?.scrollIntoView({ block: "nearest" }); }
  function runAt(i) { const it = items[i]; close(); it?.run(); }
  function close() { back.remove(); open = null; before?.focus?.(); }

  input.addEventListener("input", () => { at = 0; build(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); at = (at + 1) % items.length; mark(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); at = (at - 1 + items.length) % items.length; mark(); }
    else if (e.key === "Enter") { e.preventDefault(); runAt(at); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  });
  document.body.append(back);
  open = { input };
  build();
  input.focus();
}
