// Landing page: rotating headline, scroll reveals, the demo report card and a signed-in aware nav.
import { currentUser, startAuth, toggleTheme } from "./auth.js";

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

// Replays the demo card's "analysis" every few seconds while it is on screen.
function demo() {
  const card = $("demo");
  if (calm) return card.classList.add("play");
  const play = () => { card.classList.remove("play"); void card.offsetWidth; card.classList.add("play"); };
  play();
  let timer = setInterval(play, 9000);
  new IntersectionObserver(([entry]) => {
    clearInterval(timer);
    if (entry.isIntersecting) { play(); timer = setInterval(play, 9000); }
  }).observe(card);
}

function nav() {
  const bar = document.querySelector(".nav");
  const onScroll = () => bar.classList.toggle("scrolled", scrollY > 8);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  $("theme").addEventListener("click", toggleTheme);
}

// Signed-in visitors get "Open Inkwell" instead of the sign-in prompts. Failing quietly keeps the page usable.
async function account() {
  try {
    const ctx = await startAuth();
    if (!ctx.enabled || !(await currentUser(ctx))) return;
    $("nav-signin").hidden = true;
    $("nav-cta").textContent = "Open Inkwell";
  } catch { /* server asleep: the links still work */ }
}

nav(); rotate(); reveal(); demo(); account();
