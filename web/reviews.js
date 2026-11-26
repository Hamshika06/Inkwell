// Reviews of Inkwell: storage, the star picker, the review pop-up and the review card.
// With sign-in on, reviews live in Cloud Firestore (`reviews/{uid}`, one per account), readable by anyone, so
// they stay up after their author signs out. Only the author can change or delete theirs (see firestore.rules).
// A review shows the account's username (never the email address), or "Anonymous" if they choose.
// With sign-in off (local testing) reviews are kept in this browser instead.
import { el } from "./shared.js";

const FIREBASE_SDK = "https://www.gstatic.com/firebasejs/13.0.0";
const TIMEOUT_MS = 8000;
const SNOOZE_KEY = "inkwell-review-later", SNOOZE_DAYS = 30;
export const LIMITS = { headline: 80, body: 1200, name: 40, site: 60 };
export const WORDS = { 0.5: "Not for me", 1: "Not useful", 1.5: "Poor", 2: "Needs work", 2.5: "Fair", 3: "Okay",
  3.5: "Good", 4: "Useful", 4.5: "Really useful", 5: "Loved it" };

const withTimeout = (promise) => Promise.race([promise,
  new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), TIMEOUT_MS))]);

/* ---------- Who is writing ---------- */

/** The name a review shows: the account's username. Never the email address, and never anything with an "@". */
export function accountName(user) {
  const name = (user?.displayName || "").trim().slice(0, LIMITS.name);
  return name && !name.includes("@") ? name : "";
}

/* ---------- Storage ---------- */

let storePromise = null;

/** { mode: "account" | "device", list(), get(id), put(id, data), remove(id), vote(id, voter, on) } */
export function openReviews(ctx) {
  return (storePromise ||= ctx.enabled ? cloudReviews(ctx) : Promise.resolve(localReviews()));
}

async function cloudReviews(ctx) {
  const fs = await import(`${FIREBASE_SDK}/firebase-firestore.js`);
  const db = fs.getFirestore(ctx.auth.app);
  const reviews = fs.collection(db, "reviews");
  const votesOf = (id) => fs.collection(db, "reviews", id, "helpful");
  return {
    mode: "account",
    async list(me) {
      const snap = await withTimeout(fs.getDocs(fs.query(reviews, fs.orderBy("updatedAt", "desc"), fs.limit(300))));
      // Helpful votes: one small read per review (each vote is its own document, so nobody can stuff the count).
      return Promise.all(snap.docs.map(async (d) => {
        let helpful = 0, voted = false;
        try {
          const votes = await withTimeout(fs.getDocs(votesOf(d.id)));
          helpful = votes.size; voted = !!me && votes.docs.some((v) => v.id === me);
        } catch { /* counts are optional */ }
        return { id: d.id, ...d.data(), helpful, voted };
      }));
    },
    async get(id) {
      const snap = await withTimeout(fs.getDoc(fs.doc(reviews, id)));
      return snap.exists() ? { id, ...snap.data() } : null;
    },
    async put(id, data) { await withTimeout(fs.setDoc(fs.doc(reviews, id), data)); },
    async remove(id) { await withTimeout(fs.deleteDoc(fs.doc(reviews, id))); },
    async vote(id, voter, on) {
      const ref = fs.doc(db, "reviews", id, "helpful", voter);
      await withTimeout(on ? fs.setDoc(ref, { at: new Date().toISOString() }) : fs.deleteDoc(ref));
    },
  };
}

function localReviews() {
  const key = "inkwell:reviews";
  const read = () => { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch { return {}; } };
  const write = (data) => { try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* storage blocked */ } };
  return {
    mode: "device",
    async list(me) {
      return Object.entries(read()).map(([id, r]) => {
        const votes = r.votes || [];
        const { votes: _, ...rest } = r;
        return { id, ...rest, helpful: votes.length, voted: votes.includes(me) };
      }).sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
    },
    async get(id) { const r = read()[id]; if (!r) return null; const { votes: _, ...rest } = r; return { id, ...rest }; },
    async put(id, data) { const all = read(); all[id] = { ...data, votes: all[id]?.votes || [] }; write(all); },
    async remove(id) { const all = read(); delete all[id]; write(all); },
    async vote(id, voter, on) {
      const all = read(); if (!all[id]) return;
      const votes = new Set(all[id].votes || []);
      on ? votes.add(voter) : votes.delete(voter);
      all[id].votes = [...votes]; write(all);
    },
  };
}

/* ---------- Stars ---------- */

const STAR = "M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.5l-5.9 3.1 1.2-6.5L2.5 9.5l6.6-.9z";

function starRow(cls) {
  const NS = "http://www.w3.org/2000/svg";
  const row = el("span", { class: cls, "aria-hidden": "true" });
  for (let i = 0; i < 5; i++) {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", STAR);
    svg.append(path);
    row.append(svg);
  }
  return row;
}

/** A read-only rating, halves included (also averages such as 4.3). */
export function starsView(value, size = "") {
  return el("span", { class: `stars ${size}`, style: `--v:${Math.max(0, Math.min(5, value)) / 5}`, role: "img",
    "aria-label": `${fmt(value)} out of 5 stars` }, starRow("stars-base"), starRow("stars-fill"));
}

export const fmt = (n) => (Math.round(n * 10) / 10).toLocaleString(undefined, { maximumFractionDigits: 1 });

/** A big picker: tap the left or right half of a star; arrow keys move by half a star. */
export function starPicker(value, onChange) {
  let current = value || 0;
  const view = starsView(current, "big");
  const word = el("p", { class: "rate-word", "aria-hidden": "true" });
  const box = el("div", { class: "star-picker", role: "slider", tabindex: "0", "aria-label": "Your rating",
    "aria-valuemin": "0.5", "aria-valuemax": "5", "aria-valuestep": "0.5" }, view);
  const show = (v, preview = false) => {
    view.style.setProperty("--v", v / 5);
    word.textContent = v ? `${fmt(v)} · ${WORDS[v]}` : "Tap a star. Halves count.";
    word.classList.toggle("preview", preview);
  };
  const set = (v) => {
    current = Math.max(0.5, Math.min(5, v));
    box.setAttribute("aria-valuenow", String(current));
    box.setAttribute("aria-valuetext", `${fmt(current)} stars, ${WORDS[current]}`);
    show(current);
    onChange(current);
  };
  const at = (e) => {
    const r = view.getBoundingClientRect();
    return Math.max(0.5, Math.min(5, Math.ceil(((e.clientX - r.left) / r.width) * 10) / 2));
  };
  box.addEventListener("pointermove", (e) => show(at(e), true));
  box.addEventListener("pointerleave", () => show(current));
  box.addEventListener("click", (e) => set(at(e)));
  box.addEventListener("keydown", (e) => {
    const step = { ArrowRight: 0.5, ArrowUp: 0.5, ArrowLeft: -0.5, ArrowDown: -0.5 }[e.key];
    if (step) { e.preventDefault(); set((current || 0) + step); }
    else if (e.key === "Home") { e.preventDefault(); set(0.5); }
    else if (e.key === "End") { e.preventDefault(); set(5); }
  });
  if (current) set(current); else show(0);
  return { node: el("div", { class: "star-wrap" }, box, word), get: () => current };
}

/* ---------- The review card ---------- */

const AVATAR = ["#0a0a0a", "#13919a", "#17683b", "#b8622a", "#8a3fb8", "#b8322a", "#4f6b8a"];
const colorFor = (name) => AVATAR[[...name].reduce((h, c) => (h * 31 + c.codePointAt(0)) >>> 0, 7) % AVATAR.length];

export function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (!(s >= 0)) return "";
  if (s < 90) return "just now";
  const units = [[3600, 60, "minute"], [86400, 3600, "hour"], [86400 * 30, 86400, "day"], [86400 * 365, 86400 * 30, "month"]];
  for (const [below, size, word] of units) if (s < below) { const n = Math.round(s / size); return `${n} ${word}${n === 1 ? "" : "s"} ago`; }
  const n = Math.round(s / (86400 * 365)); return `${n} year${n === 1 ? "" : "s"} ago`;
}

export const shownName = (r) => (r.anonymous || !r.name ? "Anonymous" : r.name);

/** opts: { mine, onHelpful(review, on), onEdit() } */
export function reviewCard(r, opts = {}) {
  const name = shownName(r);
  const edited = r.createdAt && r.updatedAt && new Date(r.updatedAt) - new Date(r.createdAt) > 60000;
  return el("article", { class: `rv${opts.mine ? " mine" : ""}` },
    el("div", { class: "rv-top" }, starsView(r.rating), el("span", { class: "rv-score" }, fmt(r.rating)),
      opts.mine ? el("span", { class: "rv-yours" }, "Your review") : null),
    r.headline ? el("h4", {}, r.headline) : null,
    r.body ? el("p", { class: "rv-body" }, r.body) : null,
    el("div", { class: "rv-who" },
      el("span", { class: "rv-av", style: `background:${r.anonymous ? "#808080" : colorFor(name)}` }, name[0].toUpperCase()),
      el("span", { class: "rv-name" }, name), el("span", { class: "rv-when" }, `· ${ago(r.updatedAt || r.createdAt)}${edited ? " (edited)" : ""}`),
      r.site ? el("span", { class: "rv-site" }, `Checked ${r.site}`) : null),
    opts.onHelpful || opts.onEdit ? el("div", { class: "rv-actions" },
      opts.onHelpful && !opts.mine
        ? el("button", { type: "button", class: `rv-help${r.voted ? " on" : ""}`, "aria-pressed": String(!!r.voted),
          onclick: () => opts.onHelpful(r, !r.voted) }, `▲ Helpful${r.helpful ? ` (${r.helpful})` : ""}`)
        : r.helpful ? el("span", { class: "rv-help static" }, `▲ ${r.helpful} found this helpful`) : null,
      opts.mine && opts.onEdit ? el("button", { type: "button", class: "link", onclick: opts.onEdit }, "Edit or delete") : null) : null);
}

/* ---------- When to ask ---------- */

export function snoozed() {
  try { return Date.now() < Number(localStorage.getItem(SNOOZE_KEY) || 0); } catch { return false; }
}
function snooze() {
  try { localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_DAYS * 86400000)); } catch { /* not remembered */ }
}

/** Where to send someone who must sign in before reviewing. */
export const writeLink = ({ site, stars } = {}) => {
  const q = new URLSearchParams({ write: "1" });
  if (stars) q.set("stars", String(stars));
  if (site) q.set("site", site);
  return `/reviews.html?${q}`;
};
export const signInToReview = (opts) => `login.html?next=${encodeURIComponent(writeLink(opts))}`;

/* ---------- The pop-up ---------- */

/**
 * Opens the review pop-up. opts: { ctx, user, site, stars, heading, onPosted(review), onRemoved() }.
 * Without an account (and sign-in on) it goes to sign-in first, then comes back to the form.
 */
export async function openReviewModal(opts) {
  const { ctx, user } = opts;
  if (ctx.enabled && !user) { location.href = signInToReview(opts); return; }
  const id = user ? user.uid : "local";
  let store, existing = null;
  try {
    store = await openReviews(ctx);
    existing = await store.get(id);
  } catch (error) {
    console.warn("Reviews unavailable:", error?.code || error?.message || error);
  }

  const dialog = el("dialog", { class: "rv-modal", "aria-labelledby": "rv-title" });
  document.body.append(dialog);
  const close = () => { dialog.close(); };
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) close(); });

  const account = accountName(user);
  let rating = opts.stars ? Math.round(Number(opts.stars) * 2) / 2 : existing?.rating || 0;
  if (!(rating >= 0.5 && rating <= 5)) rating = existing?.rating || 0;
  const site = (opts.site || existing?.site || "").slice(0, LIMITS.site);
  const error = el("p", { class: "rv-error", role: "alert" });
  const picker = starPicker(rating, (v) => { rating = v; error.textContent = ""; });
  const clear = () => { error.textContent = ""; };
  const headline = el("input", { class: "input", oninput: clear, maxlength: String(LIMITS.headline), placeholder: "Sum it up in a line", value: existing?.headline || "" });
  const body = el("textarea", { class: "input", rows: "4", maxlength: String(LIMITS.body), placeholder: "What helped? What was missing?" });
  body.value = existing?.body || "";
  // The name comes from the account. Only someone without a username (some Google or GitHub accounts) types one.
  const nameInput = account ? null : el("input", { class: "input", oninput: clear, maxlength: String(LIMITS.name), placeholder: "How you'd like to appear",
    value: existing?.name || "", autocomplete: "nickname" });
  const anon = el("input", { type: "checkbox", checked: !!existing?.anonymous });
  const post = el("button", { type: "submit", class: "btn btn-primary" }, existing ? "Update review" : "Post review");

  const form = el("form", { class: "rv-form", method: "dialog", onsubmit: async (e) => {
    e.preventDefault();
    const name = account || (nameInput?.value || "").trim();
    if (!rating) return (error.textContent = "Pick a rating first: tap a star.");
    if (!anon.checked && !name) return (error.textContent = "Add the name to show, or post anonymously.");
    if (name.includes("@")) return (error.textContent = "Use a name, not an email address.");
    if (!store) return (error.textContent = "Reviews can't be reached right now. Try again in a moment.");
    const now = new Date().toISOString();
    const review = { rating, name: anon.checked ? "" : name.slice(0, LIMITS.name), anonymous: anon.checked,
      headline: headline.value.trim().slice(0, LIMITS.headline), body: body.value.trim().slice(0, LIMITS.body),
      site, createdAt: existing?.createdAt || now, updatedAt: now };
    post.disabled = true; post.textContent = "Posting…";
    try {
      await store.put(id, review);
      opts.onPosted?.({ id, ...review });
      thanks({ id, ...review });
    } catch (err) {
      console.warn("Couldn't post the review:", err?.code || err?.message || err);
      error.textContent = err?.code === "permission-denied"
        ? "Reviews aren't switched on yet: the database refused to save it. (Site owner: publish the latest firestore.rules.)"
        : err?.message === "timeout" || err?.code === "unavailable"
          ? "Couldn't reach the database. Check your connection and try again."
          : `Couldn't post your review (${err?.code || "unknown error"}). Try again.`;
      post.disabled = false; post.textContent = existing ? "Update review" : "Post review";
    }
  } },
    opts.heading ? el("p", { class: "rv-done" }, opts.heading) : null,
    el("h3", { id: "rv-title" }, existing ? "Your review of Inkwell" : "How did Inkwell do?"),
    el("p", { class: "rv-sub" }, existing ? "Change anything and update it. Only you can edit or delete it." : "Your rating helps others decide. It takes a minute."),
    picker.node,
    el("label", { class: "field" }, el("span", {}, "Your headline (optional)"), headline),
    el("label", { class: "field" }, el("span", {}, "Your review (optional)"), body),
    nameInput ? el("label", { class: "field" }, el("span", {}, "Name to show"), nameInput) : null,
    el("label", { class: "rv-check" }, anon, el("span", {}, account
      ? ["Post anonymously. Otherwise it shows your username, ", el("strong", {}, account), "."]
      : "Post anonymously")),
    error,
    el("div", { class: "rv-row" }, post,
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => { if (!existing) snooze(); close(); } }, existing ? "Cancel" : "Maybe later"),
      existing ? el("button", { type: "button", class: "link rv-delete", onclick: async (e) => {
        if (e.currentTarget.dataset.sure !== "1") { e.currentTarget.dataset.sure = "1"; e.currentTarget.textContent = "Click again to delete"; return; }
        try { await store.remove(id); opts.onRemoved?.(); close(); }
        catch { error.textContent = "Couldn't delete it. Try again."; }
      } }, "Delete my review") : null),
    el("p", { class: "fine rv-fine" }, `Reviews show your rating, headline, review, ${account || nameInput ? "name" : "the name you choose"} and the site you checked, never your email address. They stay up after you sign out. You can edit or delete yours any time.`));

  function thanks(review) {
    const first = account ? account.split(/\s+/)[0] : "";
    dialog.replaceChildren(el("div", { class: "rv-thanks" },
      el("img", { class: "rv-logo", src: "logo.svg?v=2", alt: "" }),
      el("h3", { id: "rv-title" }, `Thanks${first && !review.anonymous ? `, ${first}` : ""}`),
      el("p", { class: "rv-sub" }, existing ? "Your review is updated." : "Your review is live on the Reviews page."),
      reviewCard(review, { mine: true }),
      el("div", { class: "rv-row center" },
        location.pathname.endsWith("/reviews.html") ? null : el("a", { class: "btn btn-primary", href: "reviews.html" }, "See all reviews"),
        el("button", { type: "button", class: `btn ${location.pathname.endsWith("/reviews.html") ? "btn-primary" : "btn-ghost"}`, onclick: close }, "Close"))));
  }

  dialog.append(form);
  dialog.showModal();
  dialog.querySelector(".star-picker").focus();
}

/**
 * After the last step is ticked: ask once. Skipped for free checks, if they already reviewed,
 * or if they chose "Maybe later" in the last 30 days.
 */
export async function askAfterSteps({ ctx, user, site, total }) {
  if (snoozed() || (ctx.enabled && !user)) return;
  try {
    const store = await openReviews(ctx);
    if (await store.get(user ? user.uid : "local")) return;
  } catch { return; }
  snooze();  // Asked once; "Maybe later" or not, not again for 30 days.
  openReviewModal({ ctx, user, site, heading: `✓ All ${total} step${total === 1 ? "" : "s"} done for ${site}` });
}
