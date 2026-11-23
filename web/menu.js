// The Features and Resources menus in the top bar of the home, Reviews and Guides pages.
// Each item says in one line what it does. "Rate Inkwell" opens the review pop-up on the page you're on.
import { currentUser, startAuth } from "./auth.js";
import { openReviewModal, openReviews, reviewCard, writeLink } from "./reviews.js";
import { el } from "./shared.js";

const onHome = () => location.pathname === "/" || location.pathname.endsWith("/index.html");
const home = (hash) => (onHome() ? hash : `/${hash}`);

const item = (icon, title, text, href, extra = {}) => el(href ? "a" : "button", {
  class: `mm-item${extra.hl ? " hl" : ""}`, href, type: href ? null : "button", role: "menuitem", onclick: extra.onclick },
  el("span", { class: "mm-ico", "aria-hidden": "true" }, icon),
  el("span", {}, el("b", {}, title, extra.pill ? el("span", { class: `mm-pill ${extra.pill[0]}` }, extra.pill[1]) : null), el("small", {}, text)));

async function rate() {
  try {
    const ctx = await startAuth();
    openReviewModal({ ctx, user: await currentUser(ctx), onPosted: () => document.dispatchEvent(new CustomEvent("inkwell:review-changed")) });
  } catch {
    location.href = writeLink();  // Server asleep: the Reviews page retries.
  }
}

function featuresPanel() {
  return el("div", { class: "mm-panel", id: "mm-features", role: "menu", "aria-label": "Features", hidden: true },
    el("div", {}, el("h5", {}, "Check"),
      item("✎", "Check a policy", "Paste a link or text. See what it allows, with the exact sentences.", "app.html", { pill: ["free", "Free"] }),
      item("▦", "Privacy report card", "8 key questions, what you can limit, and ready-to-send requests.", "app.html?sample=1")),
    el("div", {}, el("h5", {}, "Go further"),
      item("⇄", "Compare two policies", "Side by side, differences first. Never picks a winner.", "compare.html"),
      item("◫", "Your dashboard", "Every check saved. Check again later to see what changed.", "dashboard.html"),
      item("⬡", "Chrome extension", "Check a site's policy before you sign up. Fix things in one click.", "guides.html#extension", { hl: true, pill: ["new", "New"] })),
    el("div", {}, el("h5", {}, "Featured"),
      el("a", { class: "mm-feature", href: "guides.html#extension" }, el("span", { class: "mm-pill new" }, "New"),
        el("p", {}, "Fix it, don't just read it: one switch tells every site not to sell your data."),
        el("span", { class: "mm-go" }, "About the extension →"))));
}

function resourcesPanel() {
  const featured = el("div", { class: "mm-feature quiet" }, el("p", { class: "mm-muted" }, "Loading the latest review…"));
  const panel = el("div", { class: "mm-panel", id: "mm-resources", role: "menu", "aria-label": "Resources", hidden: true },
    el("div", {}, el("h5", {}, "Learn"),
      item("❖", "Guides", "What really happens to your data when you click “I agree”.", "guides.html"),
      item("?", "What we check", "The 8 key questions, and how we find the answers.", home("#checks"))),
    el("div", {}, el("h5", {}, "Community"),
      item("★", "Reviews", "Read what people think of Inkwell, and how they rated it.", "reviews.html", { hl: true }),
      item("✍", "Rate Inkwell", "Tell us how it went. Takes a minute.", null, { onclick: rate })),
    el("div", {}, el("h5", {}, "Featured review"), featured));
  panel.loadFeatured = async () => {
    if (panel.loaded) return;
    panel.loaded = true;
    try {
      const store = await openReviews(await startAuth());
      const list = (await store.list()).filter((r) => r.headline || r.body);
      const best = list.sort((a, b) => b.helpful - a.helpful || b.rating - a.rating)[0];
      featured.replaceChildren(...(best
        ? [reviewCard(best), el("a", { class: "mm-go", href: "reviews.html" }, "Read all reviews →")]
        : [el("p", {}, "No reviews yet."), el("button", { type: "button", class: "mm-go", onclick: rate }, "Be the first to rate Inkwell →")]));
    } catch {
      featured.replaceChildren(el("a", { class: "mm-go", href: "reviews.html" }, "Read reviews →"));
    }
  };
  return panel;
}

/** Replaces the links in `nav` with Features ▾ · Compare · Resources ▾ · FAQ. */
export function mountMenus(nav) {
  const panels = { features: featuresPanel(), resources: resourcesPanel() };
  const buttons = {};
  let open = null, hoverTimer, hoveredAt = 0;
  const setOpen = (name) => {
    open = name;
    for (const [key, panel] of Object.entries(panels)) {
      panel.hidden = key !== name;
      buttons[key].setAttribute("aria-expanded", String(key === name));
      buttons[key].classList.toggle("open", key === name);
    }
    if (name === "resources") panels.resources.loadFeatured();
  };
  const trigger = (name, label) => (buttons[name] = el("button", { type: "button", class: "mm-trigger", "aria-haspopup": "true", "aria-expanded": "false",
    // A click right after hovering open keeps it open, rather than closing what the pointer just opened.
    "aria-controls": `mm-${name}`, onclick: () => setOpen(open === name && performance.now() - hoveredAt > 600 ? null : name),
    onpointerenter: (e) => { if (e.pointerType === "mouse") { clearTimeout(hoverTimer); if (open !== name) hoveredAt = performance.now(); setOpen(name); } } },
    label, el("span", { class: "mm-caret", "aria-hidden": "true" }, "▾")));
  nav.replaceChildren(trigger("features", "Features"), el("a", { href: "compare.html" }, "Compare"),
    trigger("resources", "Resources"), el("a", { href: home("#faq") }, "FAQ"));
  const holder = el("div", { class: "mm-holder" }, panels.features, panels.resources);
  nav.closest("header").append(holder);
  const leave = (e) => { if (e.pointerType === "mouse") hoverTimer = setTimeout(() => setOpen(null), 220); };
  const stay = () => clearTimeout(hoverTimer);
  for (const node of [nav, holder]) { node.addEventListener("pointerleave", leave); node.addEventListener("pointerenter", stay); }
  document.addEventListener("click", (e) => { if (open && !nav.contains(e.target) && !holder.contains(e.target)) setOpen(null); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open) { const b = buttons[open]; setOpen(null); b.focus(); } });
  holder.addEventListener("click", (e) => { if (e.target.closest("a, button.mm-item")) setOpen(null); });
}
