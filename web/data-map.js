// The "Where your data goes" feature page: an explanation, and a live example map of a made-up app's policy.
import { currentUser, startAuth, toggleTheme } from "./auth.js";
import { mountMenus } from "./menu.js";
import { initTour } from "./tour.js";
import { renderDataMap } from "./visuals.js";

const $ = (id) => document.getElementById(id);

// Sentences from the made-up Pigeonpost policy used across Inkwell's sample.
const SAMPLE = [
  "We collect the name, email address and phone number you give us when you create an account, and we automatically collect your device type, IP address and approximate location when you use the app.",
  "We share your personal information with advertising partners and analytics providers, and we may disclose it to law enforcement when required by law.",
  "We use service providers to host our servers and process payments, and they may receive your information to do this work.",
  "If Pigeonpost is involved in a merger or acquisition, your information may be transferred to the new owner.",
].map((text, id) => ({ id, text }));
const REPORT = { concerns: [{ id: "ads", fixable: true, steps: ["optout"] }, { id: "sharing", fixable: true, steps: ["optout"] }] };

let selected = null, limited = false;
function draw() {
  $("dmp-map").replaceChildren(renderDataMap({
    segments: SAMPLE, report: REPORT, company: "Pigeonpost", selected,
    isLimited: () => limited,
    onSelect: (key) => { selected = key; draw(); },
    onFix: () => { limited = true; draw(); },  // On the example, Fix it shows what happens: the red line turns dotted.
  }));
}

$("theme").addEventListener("click", toggleTheme);
mountMenus(document.querySelector(".nav-links"));
draw();
(async () => {
  let signedIn = false;
  try {
    const ctx = await startAuth();
    signedIn = !ctx.enabled || !!(await currentUser(ctx));
    if (ctx.enabled && signedIn) { $("nav-signin").hidden = true; $("nav-cta").textContent = "Open Inkwell"; }
  } catch { /* server asleep: the example still works */ }
  initTour({ signedIn });
})();
