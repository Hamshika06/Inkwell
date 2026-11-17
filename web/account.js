// The account menu in the top bar (avatar, name, Sign out, Delete account) and the delete-account pop-up.
// Shared by the product, dashboard and compare pages.
//
// Deleting an account removes, in this order:
//   1. everything Inkwell keeps for the person in Cloud Firestore: saved policies (users/{uid}/policies),
//      priorities (users/{uid}), their review (reviews/{uid}) and the "helpful" votes they gave other reviews;
//   2. anything saved for them in this browser;
//   3. their Firebase sign-in account.
// Firebase only deletes an account that signed in recently, so the person confirms who they are first (a
// Google/GitHub pop-up, or their password). Firestore rules already let each person delete their own documents.
import { describeAuthError } from "./auth.js";
import { el } from "./shared.js";

const FIREBASE_SDK = "https://www.gstatic.com/firebasejs/13.0.0";
const TIMEOUT_MS = 15000;
const BATCH_LIMIT = 450;  // Firestore allows 500 writes per batch.
export const PROVIDER = { "google.com": "Google", "github.com": "GitHub", "password": "Email and password" };

let leaving = false;
/** True while an account is being deleted, so pages don't redirect on the sign-out that deletion causes. */
export const isLeaving = () => leaving;

const withTimeout = (promise) => Promise.race([promise,
  new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), TIMEOUT_MS))]);

/* ---------- The menu ---------- */

/**
 * Fills `box` with the avatar button and its menu for a signed-in user.
 * `items` are extra menu entries (links or buttons) placed above Sign out.
 */
export function renderAccountMenu(box, ctx, user, items = []) {
  const name = user.displayName || (user.email || "").split("@")[0] || "Account";
  const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const avatar = el("span", { class: "avatar" }, user.photoURL ? el("img", { src: user.photoURL, alt: "", referrerpolicy: "no-referrer" }) : initials);
  const close = () => { menu.hidden = true; button.setAttribute("aria-expanded", "false"); };
  const menu = el("div", { class: "menu", role: "menu", hidden: true },
    el("div", { class: "menu-head" }, el("strong", {}, name), el("span", {}, user.email || ""),
      el("small", {}, `Signed in with ${PROVIDER[user.providerData[0]?.providerId] || "your account"}`)),
    ...items,
    el("button", { type: "button", role: "menuitem", onclick: async () => { await ctx.fb.signOut(ctx.auth); location.replace("/"); } }, "Sign out"),
    el("div", { class: "menu-sep", role: "separator" }),
    el("button", { type: "button", role: "menuitem", class: "menu-danger", onclick: () => openDeleteAccount(ctx, user) }, "Delete account…"));
  const button = el("button", { type: "button", class: "user-btn", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; button.setAttribute("aria-expanded", String(!menu.hidden)); } },
    avatar, el("span", { class: "user-name" }, name));
  menu.addEventListener("click", (e) => { if (e.target.closest("a, button")) close(); });
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  box.replaceChildren(button, menu);
}

/* ---------- The pop-up ---------- */

export function openDeleteAccount(ctx, user) {
  const provider = user.providerData[0]?.providerId || "password";
  const usesPassword = provider === "password";
  const dialog = el("dialog", { class: "acct-modal", "aria-labelledby": "acct-title" });
  document.body.append(dialog);
  let busy = false;
  const close = () => { if (!busy) dialog.close(); };
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("cancel", (e) => { if (busy) e.preventDefault(); });
  dialog.addEventListener("click", (e) => { if (e.target === dialog) close(); });

  const error = el("p", { class: "acct-error", role: "alert" });
  const confirmText = el("input", { class: "input", autocomplete: "off", spellcheck: "false", "aria-describedby": "acct-type-hint",
    oninput: () => { error.textContent = ""; update(); } });
  const password = usesPassword
    ? el("input", { class: "input", type: "password", autocomplete: "current-password", oninput: () => { error.textContent = ""; update(); } })
    : null;
  const submit = el("button", { type: "submit", class: "btn btn-danger", disabled: true }, "Delete my account");
  const cancel = el("button", { type: "button", class: "btn btn-ghost", onclick: close }, "Cancel");
  const update = () => { submit.disabled = busy || confirmText.value.trim() !== "DELETE" || (usesPassword && !password.value); };

  const form = el("form", { class: "acct-form", onsubmit: async (e) => {
    e.preventDefault();
    if (submit.disabled) return;
    busy = true; update(); cancel.disabled = true;
    try {
      // 1. Confirm who they are. A pop-up must open straight from the click, so nothing is awaited before it.
      submit.textContent = "Confirming it's you…";
      await reauthenticate(ctx, user, provider, password?.value);
      // 2. Delete their saved data while they can still prove who they are to Firestore.
      submit.textContent = "Deleting your saved data…";
      await deleteSavedData(ctx, user);
      forgetThisBrowser(user.uid);
      // 3. Delete the sign-in account itself. This also signs them out.
      submit.textContent = "Deleting your account…";
      leaving = true;
      await ctx.fb.deleteUser(user);
      done();
    } catch (err) {
      leaving = false;
      busy = false; cancel.disabled = false; submit.textContent = "Delete my account"; update();
      console.warn("Account not deleted:", err?.code || err?.message || err);
      error.textContent = explain(err);
    }
  } },
    el("h3", { id: "acct-title" }, "Delete your account?"),
    el("p", { class: "acct-sub" }, "This permanently deletes:"),
    el("ul", { class: "acct-list" },
      el("li", {}, "Every policy saved to your dashboard, with its report, choice, ticked steps and history"),
      el("li", {}, "Your priorities"),
      el("li", {}, "Your review of Inkwell and the \"helpful\" votes you gave"),
      el("li", {}, `Your sign-in (${user.email || PROVIDER[provider] || "this account"})`)),
    el("p", { class: "acct-warn" }, el("strong", {}, "This can't be undone."), " You can sign up again later, but nothing above comes back."),
    el("label", { class: "field" }, el("span", { id: "acct-type-hint" }, "Type DELETE to confirm"), confirmText),
    usesPassword
      ? el("label", { class: "field" }, el("span", {}, "Your password"), password)
      : el("p", { class: "acct-fine" }, `To confirm it's you, a ${PROVIDER[provider] || "sign-in"} window opens when you click Delete.`),
    error,
    el("div", { class: "acct-row" }, cancel, submit));

  function done() {
    busy = false;
    dialog.replaceChildren(el("div", { class: "acct-form acct-done" },
      el("h3", { id: "acct-title" }, "Your account is deleted"),
      el("p", { class: "acct-sub" }, "Your saved work, review and sign-in are gone. Thanks for trying Inkwell."),
      el("div", { class: "acct-row center" }, el("a", { class: "btn btn-primary", href: "/" }, "Go to the home page"))));
    dialog.addEventListener("close", () => location.replace("/"));
  }

  dialog.append(form);
  dialog.showModal();
  confirmText.focus();
}

async function reauthenticate(ctx, user, provider, password) {
  const fb = ctx.fb;
  if (provider === "password") {
    return fb.reauthenticateWithCredential(user, fb.EmailAuthProvider.credential(user.email, password));
  }
  const auth = provider === "github.com" ? new fb.GithubAuthProvider() : new fb.GoogleAuthProvider();
  return fb.reauthenticateWithPopup(user, auth);
}

async function deleteSavedData(ctx, user) {
  // Unconfirmed email accounts can't save anything (see firestore.rules), so there is nothing to delete.
  if (user.providerData.some((p) => p.providerId === "password") && !user.emailVerified) return;
  const fs = await import(`${FIREBASE_SDK}/firebase-firestore.js`);
  const db = fs.getFirestore(ctx.auth.app);
  const uid = user.uid;
  const [policies, reviews] = await withTimeout(Promise.all([
    fs.getDocs(fs.collection(db, "users", uid, "policies")),
    fs.getDocs(fs.collection(db, "reviews")),
  ]));
  // Children before parents, the profile last: if something fails part-way, trying again finishes the job.
  const refs = [
    ...policies.docs.map((d) => d.ref),
    ...reviews.docs.filter((d) => d.id !== uid).map((d) => fs.doc(db, "reviews", d.id, "helpful", uid)),
    fs.doc(db, "reviews", uid),
    fs.doc(db, "users", uid),
  ];
  for (let i = 0; i < refs.length; i += BATCH_LIMIT) {
    const batch = fs.writeBatch(db);
    for (const ref of refs.slice(i, i + BATCH_LIMIT)) batch.delete(ref);
    await withTimeout(batch.commit());
  }
}

function forgetThisBrowser(uid) {
  try { localStorage.removeItem(`inkwell:${uid}`); } catch { /* storage blocked: nothing saved here */ }
}

function explain(err) {
  const code = err?.code || "";
  if (code === "auth/wrong-password" || code === "auth/invalid-credential") return "That password isn't right. Your account was not deleted.";
  if (code === "auth/user-mismatch") return "That's a different account. Confirm with the account you're deleting.";
  if (code === "auth/popup-blocked") return "Your browser blocked the sign-in window. Allow pop-ups for this site and try again.";
  if (code === "auth/requires-recent-login") return "For your security, sign out, sign in again, then delete your account.";
  if (code === "permission-denied") return "The database refused to delete your saved data, so your account was not deleted. Try again, or contact us.";
  if (code === "unavailable" || err?.message === "timeout") return "Couldn't reach the database, so your account was not deleted. Check your connection and try again.";
  if (code.startsWith("auth/")) return describeAuthError(err) || "Confirmation was cancelled. Your account was not deleted.";
  return `Your account was not deleted (${code || err?.message || "unknown error"}). Try again.`;
}
