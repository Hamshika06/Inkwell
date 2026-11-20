// The Reviews page: the average and its spread, the most helpful quote, filters, and every review.
// Anyone can read; posting and "Helpful" need an account. Opened with ?write=1 (from the extension's stars,
// or after signing in to review), it opens the review form straight away.
import { currentUser, startAuth, toggleTheme } from "./auth.js";
import { mountMenus } from "./menu.js";
import { initTour } from "./tour.js";
import { fmt, openReviewModal, openReviews, reviewCard, signInToReview, starsView } from "./reviews.js";
import { el } from "./shared.js";

const $ = (id) => document.getElementById(id);
const page = { ctx: { enabled: false }, user: null, store: null, list: [], filter: "all", sort: "helpful" };
const me = () => (page.user ? page.user.uid : page.ctx.enabled ? null : "local");

const FILTERS = [["all", "All"], ["5", "5 ★"], ["4", "4 ★"], ["3", "3 ★ and below"], ["text", "With written reviews"]];
const SORTS = [["helpful", "Most helpful"], ["new", "Newest"], ["high", "Highest rated"], ["low", "Lowest rated"]];
const bucket = (rating) => Math.max(1, Math.floor(rating));  // 4.5 counts as a 4, 0.5 as a 1.

function write(extra = {}) {
  openReviewModal({ ctx: page.ctx, user: page.user, ...extra, onPosted: load, onRemoved: load });
}

function summary() {
  const list = page.list, n = list.length;
  const mine = list.find((r) => r.id === me());
  const writeBtn = el("button", { type: "button", class: "btn btn-primary btn-block", onclick: () => write() }, mine ? "✎ Edit your review" : "✍ Write a review");
  if (page.failed) return el("div", { class: "rvp-score empty" }, el("p", { class: "rvp-num" }, "Reviews"), el("p", { class: "fine" }, "Ratings will show here once they load."), writeBtn);
  if (!n) {
    return el("div", { class: "rvp-score empty" }, el("p", { class: "rvp-num" }, "No reviews yet"),
      el("p", { class: "fine" }, "Checked a policy with Inkwell? Be the first to say how it went."), writeBtn);
  }
  const avg = list.reduce((s, r) => s + r.rating, 0) / n;
  const counts = [5, 4, 3, 2, 1].map((b) => [b, list.filter((r) => bucket(r.rating) === b).length]);
  return el("div", { class: "rvp-score" },
    el("p", { class: "rvp-num" }, fmt(avg), el("small", {}, " / 5")), starsView(avg, "mid"),
    el("p", { class: "fine" }, `From ${n} review${n === 1 ? "" : "s"}`),
    el("div", { class: "rvp-dist" }, counts.flatMap(([b, c]) => [
      el("span", {}, `${b} ★`),
      el("span", { class: "rvp-track", role: "img", "aria-label": `${c} with ${b} stars` }, el("i", { style: `width:${n ? (c / n) * 100 : 0}%` })),
      el("span", {}, String(c))])),
    writeBtn);
}

function pull() {
  const best = [...page.list].filter((r) => r.headline).sort((a, b) => b.helpful - a.helpful || b.rating - a.rating)[0];
  if (!best) return null;
  return el("figure", { class: "rvp-pull" }, el("blockquote", {}, `“${best.headline}”`),
    el("figcaption", {}, `${best.anonymous || !best.name ? "Anonymous" : best.name}${best.helpful ? ` · most helpful` : " · latest"}`));
}

function shown() {
  const f = page.filter;
  const list = page.list.filter((r) => f === "all" || (f === "text" ? r.headline || r.body : f === "3" ? bucket(r.rating) <= 3 : bucket(r.rating) === Number(f)));
  const by = { helpful: (a, b) => b.helpful - a.helpful || (b.updatedAt || "").localeCompare(a.updatedAt || ""),
    new: (a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""),
    high: (a, b) => b.rating - a.rating, low: (a, b) => a.rating - b.rating }[page.sort];
  // Your own review is always first, so you can find it to edit.
  return list.sort((a, b) => (b.id === me()) - (a.id === me()) || by(a, b));
}

async function helpful(review, on) {
  if (!page.user && page.ctx.enabled) { location.href = `login.html?next=${encodeURIComponent("/reviews.html")}`; return; }
  review.voted = on; review.helpful += on ? 1 : -1;
  render();
  try { await page.store.vote(review.id, me(), on); }
  catch { review.voted = !on; review.helpful += on ? -1 : 1; render(); $("rvp-note").textContent = "Couldn't save that. Try again."; }
}

function render() {
  $("rvp-summary").replaceChildren(summary());
  $("rvp-pull").replaceChildren(pull() || "");
  const n = page.list.length;
  $("rvp-tools").hidden = !n;
  $("rvp-filters").replaceChildren(...FILTERS.map(([key, label]) => el("button", { type: "button", class: `rvp-chip${page.filter === key ? " on" : ""}`,
    "aria-pressed": String(page.filter === key), onclick: () => { page.filter = key; render(); } }, label)));
  const items = shown();
  $("rvp-grid").replaceChildren(...(items.length
    ? items.map((r) => reviewCard(r, { mine: r.id === me(), onHelpful: helpful, onEdit: () => write() }))
    : n ? [el("p", { class: "rvp-empty" }, "No reviews match this filter.")] : []));
}

async function load() {
  try {
    page.store = await openReviews(page.ctx);
    page.list = await page.store.list(me());
    page.failed = false;
    $("rvp-note").textContent = page.store.mode === "device" ? "Sign-in is off on this server, so reviews here are kept in this browser only (for testing)." : "";
  } catch (error) {
    console.warn("Reviews unavailable:", error?.code || error?.message || error);
    page.list = []; page.failed = true;
    $("rvp-note").textContent = "Reviews can't be loaded right now. Try again in a moment.";
  }
  render();
}

async function start() {
  $("theme").addEventListener("click", toggleTheme);
  mountMenus(document.querySelector(".nav-links"));
  $("rvp-sort").replaceChildren(...SORTS.map(([key, label]) => el("option", { value: key }, label)));
  $("rvp-sort").addEventListener("change", (e) => { page.sort = e.target.value; render(); });
  try {
    page.ctx = await startAuth();
    page.user = await currentUser(page.ctx);
  } catch {
    $("rvp-note").textContent = "The Inkwell server is waking up. Reload in a moment to see reviews.";
    return;
  }
  if (page.ctx.enabled && page.user) { $("nav-signin").hidden = true; $("nav-cta").textContent = "Open Inkwell"; }
  $("rvp-signin").hidden = !(page.ctx.enabled && !page.user);
  $("rvp-signin-link").href = signInToReview();
  document.addEventListener("inkwell:review-changed", load);
  await load();
  initTour({ signedIn: !page.ctx.enabled || !!page.user });
  const q = new URLSearchParams(location.search);
  if (q.get("write")) {
    history.replaceState(null, "", location.pathname);
    write({ stars: q.get("stars"), site: q.get("site") || "" });
  }
}

start();
