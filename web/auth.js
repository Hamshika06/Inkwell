// Sign-in shared by the login and product pages. The API's /auth-config says whether sign-in is on and
// gives the public Firebase settings; the Firebase SDK is only loaded when it is on.
const FIREBASE_SDK = "https://www.gstatic.com/firebasejs/13.0.0";

export const API = (window.INKWELL_API ?? "").replace(/\/+$/, "");

let context = null;

/** Returns { enabled, auth, fb } once; fb holds the Firebase Auth functions when sign-in is on. */
export async function startAuth() {
  if (context) return context;
  const response = await fetch(`${API}/auth-config`);
  if (!response.ok) throw new Error(`Can't reach the Inkwell API (${response.status})`);
  const config = await response.json();
  if (!config.enabled) return (context = { enabled: false });
  const [{ initializeApp }, fb] = await Promise.all([
    import(`${FIREBASE_SDK}/firebase-app.js`), import(`${FIREBASE_SDK}/firebase-auth.js`)]);
  const auth = fb.getAuth(initializeApp(config.firebase));
  await fb.setPersistence(auth, fb.browserLocalPersistence);
  return (context = { enabled: true, auth, fb });
}

/** Resolves with the signed-in user (or null) once Firebase has restored any saved session. */
export function currentUser(ctx) {
  if (!ctx.enabled) return Promise.resolve(null);
  return new Promise((resolve) => {
    const stop = ctx.fb.onAuthStateChanged(ctx.auth, (user) => { stop(); resolve(user); });
  });
}

/** Authorization header for API calls; empty when sign-in is off. */
export async function authHeaders(ctx) {
  const user = ctx.enabled && ctx.auth.currentUser;
  return user ? { Authorization: `Bearer ${await user.getIdToken()}` } : {};
}

/** Only same-site paths are allowed as a post-login destination. */
export function safeNext(value) {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") ? value : "/";
}

/** Friendly text for Firebase Auth error codes. Returns "" for errors that need no message. */
export function describeAuthError(error) {
  const messages = {
    "auth/invalid-credential": "That email and password don't match an account.",
    "auth/wrong-password": "That email and password don't match an account.",
    "auth/user-not-found": "That email and password don't match an account.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/missing-password": "Enter your password.",
    "auth/weak-password": "Choose a stronger password (at least 8 characters).",
    "auth/email-already-in-use": "An account with this email already exists. Sign in instead.",
    "auth/account-exists-with-different-credential":
      "You already have an account with this email through another sign-in method. Use that method instead.",
    "auth/too-many-requests": "Too many attempts. Wait a moment and try again.",
    "auth/network-request-failed": "Network problem. Check your connection and try again.",
    "auth/operation-not-allowed": "This sign-in method isn't enabled yet. Ask the site owner to turn it on in Firebase.",
    "auth/unauthorized-domain": "This site's address isn't authorized for sign-in yet (Firebase → Authentication → Settings → Authorized domains).",
    "auth/invalid-api-key": "Sign-in is misconfigured on the server (Firebase API key).",
    "auth/api-key-not-valid.-please-pass-a-valid-api-key.": "Sign-in is misconfigured on the server (Firebase API key).",
    "auth/popup-closed-by-user": "",
    "auth/cancelled-popup-request": "",
  };
  return error && error.code in messages ? messages[error.code] : (error?.message || "Something went wrong. Try again.");
}

// Theme: "light" | "dark" | system default. Stored per browser only.
export function applySavedTheme() {
  try {
    const saved = localStorage.getItem("inkwell-theme");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch { /* storage unavailable: follow the system theme */ }
}

export function toggleTheme() {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("inkwell-theme", next); } catch { /* not remembered */ }
}
