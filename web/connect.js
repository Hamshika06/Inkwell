// Hands this browser's Inkwell sign-in to the Inkwell extension, then the extension closes this tab and
// returns the person to the page they were checking. The extension's small script on this site (bridge.js)
// receives the message; nothing is sent anywhere else. Without the extension, the page says so.
import { currentUser, isVerified, startAuth } from "./auth.js";

const $ = (id) => document.getElementById(id);
const say = (title, message, showActions = false) => {
  $("title").textContent = title; $("message").textContent = message; $("actions").hidden = !showActions;
};
const mode = new URLSearchParams(location.search).get("mode") === "signup" ? "signup" : "signin";
const toLogin = () => location.replace(`login.html?mode=${mode}&next=${encodeURIComponent("/connect.html")}`);

/** Resolves true once the extension answers on this page, false after a few seconds without it. */
function extensionPresent() {
  return new Promise((resolve) => {
    const timer = setTimeout(() => { removeEventListener("message", onMessage); resolve(false); }, 3000);
    function onMessage(event) {
      if (event.source !== window || event.data?.source !== "inkwell-ext" || event.data.type !== "ready") return;
      clearTimeout(timer); removeEventListener("message", onMessage); resolve(true);
    }
    addEventListener("message", onMessage);
    postMessage({ source: "inkwell-page", type: "ping" }, location.origin);
  });
}

function send(payload) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => { removeEventListener("message", onMessage); resolve(false); }, 5000);
    function onMessage(event) {
      if (event.source !== window || event.data?.source !== "inkwell-ext" || event.data.type !== "connected") return;
      clearTimeout(timer); removeEventListener("message", onMessage); resolve(true);
    }
    addEventListener("message", onMessage);
    postMessage({ source: "inkwell-page", type: "connect", ...payload }, location.origin);
  });
}

async function main() {
  let ctx;
  try { ctx = await startAuth(); } catch { return say("The server is waking up", "Reload this page in a minute.", false); }
  let payload = { open: true };  // Sign-in is off on this server: the extension needs no account.
  if (ctx.enabled) {
    const user = await currentUser(ctx);
    if (!user) return toLogin();
    if (!(await isVerified(user).catch(() => true))) return toLogin();
    payload = { refreshToken: user.refreshToken, apiKey: ctx.auth.app.options.apiKey,
                email: user.email || "", name: user.displayName || (user.email || "").split("@")[0] };
  }
  if (!(await extensionPresent())) {
    return say("You're signed in", "The Inkwell extension isn't installed in this browser, so there's nothing to connect. You can keep using Inkwell here.", true);
  }
  if (await send(payload)) say("Extension connected", "Taking you back to the page you were checking. You can close this tab if it stays open.");
  else say("Couldn't connect", "The extension didn't answer. Open the Inkwell icon and try again.", true);
}

main();
