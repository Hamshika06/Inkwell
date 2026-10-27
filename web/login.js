import { applySavedTheme, currentUser, describeAuthError, safeNext, startAuth } from "./auth.js";

applySavedTheme();
const $ = (id) => document.getElementById(id);
const next = safeNext(new URLSearchParams(location.search).get("next"));
let ctx = null;
let mode = "signin";

const TAGLINES = [
  "Read the fine print, without reading all of it.",
  "Every answer comes with its receipt: the exact clause.",
  "Silence is an answer too. We show what a policy never says.",
  "No summaries. No guesses. Just the clauses.",
  "Privacy policies are long. Your evenings aren't.",
];

function rotateTaglines() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let i = 0;
  setInterval(() => {
    const el = $("tagline");
    el.classList.add("fade");
    setTimeout(() => { i = (i + 1) % TAGLINES.length; el.textContent = TAGLINES[i]; el.classList.remove("fade"); }, 450);
  }, 4200);
}

function message(text, ok = false) {
  $("auth-msg").textContent = text;
  $("auth-msg").classList.toggle("ok", ok);
  $("auth-msg").hidden = !text;
}

function busy(on) {
  for (const id of ["google", "github", "submit", "forgot"]) $(id).disabled = on;
}

function setMode(next) {
  mode = next;
  const signup = mode === "signup";
  $("mode-signin").setAttribute("aria-selected", String(!signup));
  $("mode-signup").setAttribute("aria-selected", String(signup));
  $("name-field").hidden = !signup;
  $("password-hint").hidden = !signup;
  $("forgot-row").hidden = signup;
  $("password").autocomplete = signup ? "new-password" : "current-password";
  $("submit").textContent = signup ? "Create account" : "Sign in";
  $("auth-title").textContent = signup ? "Create your account" : "Welcome back";
  $("auth-sub").textContent = signup ? "Start checking what privacy policies really say." : "Sign in to analyze privacy policies.";
  message("");
}

function done() { location.replace(next); }

async function withProvider(provider) {
  const { fb, auth } = ctx;
  message(""); busy(true);
  try {
    await fb.signInWithPopup(auth, provider);
    done();
  } catch (error) {
    if (error.code === "auth/popup-blocked") return fb.signInWithRedirect(auth, provider);
    message(describeAuthError(error));
  } finally {
    busy(false);
  }
}

async function submitEmail(event) {
  event.preventDefault();
  const { fb, auth } = ctx;
  const email = $("email").value.trim(), password = $("password").value, name = $("name").value.trim();
  if (!email) return message("Enter your email address.");
  if (!password) return message("Enter your password.");
  if (mode === "signup") {
    if (!name) return message("Choose a username.");
    if (password.length < 8) return message("Choose a password with at least 8 characters.");
  }
  message(""); busy(true);
  try {
    if (mode === "signup") {
      const { user } = await fb.createUserWithEmailAndPassword(auth, email, password);
      await fb.updateProfile(user, { displayName: name });
      fb.sendEmailVerification(user).catch(() => {});  // Nice to have; sign-up works without it.
    } else {
      await fb.signInWithEmailAndPassword(auth, email, password);
    }
    done();
  } catch (error) {
    message(describeAuthError(error));
  } finally {
    busy(false);
  }
}

async function forgotPassword() {
  const email = $("email").value.trim();
  if (!email) { $("email").focus(); return message("Enter your email above, then choose “Forgot password?” again."); }
  busy(true);
  try {
    await ctx.fb.sendPasswordResetEmail(ctx.auth, email);
    message(`If an account exists for ${email}, a reset link is on its way.`, true);
  } catch (error) {
    // Same answer whether or not the account exists, so this page can't be used to probe emails.
    if (error.code === "auth/user-not-found") message(`If an account exists for ${email}, a reset link is on its way.`, true);
    else message(describeAuthError(error));
  } finally {
    busy(false);
  }
}

async function main() {
  rotateTaglines();
  try {
    ctx = await startAuth();
  } catch (error) {
    $("auth-loading").hidden = true;
    return message(`${error.message}. Is the server running?`);
  }
  $("auth-loading").hidden = true;
  if (!ctx.enabled) { $("auth-off").hidden = false; return; }
  if (await currentUser(ctx)) return done();  // Already signed in.
  try { if (await ctx.fb.getRedirectResult(ctx.auth)) return done(); } catch (error) { message(describeAuthError(error)); }

  $("auth-ui").hidden = false;
  $("google").addEventListener("click", () => withProvider(new ctx.fb.GoogleAuthProvider()));
  $("github").addEventListener("click", () => withProvider(new ctx.fb.GithubAuthProvider()));
  $("mode-signin").addEventListener("click", () => setMode("signin"));
  $("mode-signup").addEventListener("click", () => setMode("signup"));
  $("email-form").addEventListener("submit", submitEmail);
  $("forgot").addEventListener("click", forgotPassword);
  $("reveal").addEventListener("click", () => {
    const show = $("password").type === "password";
    $("password").type = show ? "text" : "password";
    $("reveal").textContent = show ? "Hide" : "Show";
    $("reveal").setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
  if (new URLSearchParams(location.search).get("mode") === "signup") setMode("signup");
}

main();
