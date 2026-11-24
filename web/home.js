// Landing page: rotating headline, scroll reveals, the demo report card and a signed-in aware nav.
import { currentUser, startAuth, toggleTheme } from "./auth.js";
import { mountMenus } from "./menu.js";
import { initTour } from "./tour.js";
import { inkwell } from "./progress.js";

const $ = (id) => document.getElementById(id);
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

const WORDS = ["sell your data", "share it with advertisers", "track your location", "keep it forever",
  "let you delete it", "let you opt out", "can change the rules without telling you"];

function rotate() {
  if (calm) return;
  const word = $("rotator-word");
  let i = 0;
  setInterval(() => {
    word.classList.add("out");
    setTimeout(() => {
      i = (i + 1) % WORDS.length;
      word.textContent = WORDS[i];
      word.classList.replace("out", "in");
      requestAnimationFrame(() => requestAnimationFrame(() => word.classList.remove("in")));
    }, 350);
  }, 2600);
}

function reveal() {
  const items = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) return items.forEach((el) => el.classList.add("in"));
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) { entry.target.classList.add("in"); io.unobserve(entry.target); }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
  items.forEach((el) => io.observe(el));
}

// The hero's 3D example: the answers float off the page once, then the scene leans toward the mouse.
function demo() {
  const stage = $("demo");
  if (!stage) return;
  const well = inkwell();
  well.style.setProperty("--level", 0.62);
  $("hero-well")?.append(well);
  requestAnimationFrame(() => stage.classList.add("play"));
  if (!calm) setInterval(() => { well.classList.remove("full"); void well.offsetWidth; well.classList.add("full"); }, 5000);  // A drop now and then.
  if (calm || !matchMedia("(min-width: 981px)").matches) return;
  const hero = stage.closest(".hero"), rig = stage.querySelector(".hv-rig");
  hero.addEventListener("pointermove", (e) => {
    const r = hero.getBoundingClientRect();
    rig.style.setProperty("--ry", `${-28 + ((e.clientX - r.left) / r.width - 0.5) * 12}deg`);
    rig.style.setProperty("--rx", `${14 - ((e.clientY - r.top) / r.height - 0.5) * 8}deg`);
  });
  hero.addEventListener("pointerleave", () => { rig.style.removeProperty("--ry"); rig.style.removeProperty("--rx"); });
}

function nav() {
  const bar = document.querySelector(".nav");
  const onScroll = () => bar.classList.toggle("scrolled", scrollY > 8);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  $("theme").addEventListener("click", toggleTheme);
  mountMenus(document.querySelector(".nav-links"));
}

// Signed-in visitors get "Open Inkwell" instead of the sign-in prompts. Failing quietly keeps the page usable.
async function account() {
  let signedIn = false;
  try {
    const ctx = await startAuth();
    signedIn = !ctx.enabled || !!(await currentUser(ctx));  // Sign-in off (local testing) works like an account.
    if (ctx.enabled && signedIn) { $("nav-signin").hidden = true; $("nav-cta").textContent = "Open Inkwell"; }
  } catch { /* server asleep: the links still work */ }
  initTour({ signedIn });
}

nav(); rotate(); reveal(); demo(); account();
