// Guides page: the menus, the theme switch, and "rate Inkwell" for suggesting a guide.
import { currentUser, startAuth, toggleTheme } from "./auth.js";
import { mountMenus } from "./menu.js";
import { openReviewModal, writeLink } from "./reviews.js";

const $ = (id) => document.getElementById(id);

$("theme").addEventListener("click", toggleTheme);
mountMenus(document.querySelector(".nav-links"));
$("gp-rate").addEventListener("click", async () => {
  try { const ctx = await startAuth(); openReviewModal({ ctx, user: await currentUser(ctx) }); }
  catch { location.href = writeLink(); }
});
(async () => {
  try {
    const ctx = await startAuth();
    if (ctx.enabled && (await currentUser(ctx))) { $("nav-signin").hidden = true; $("nav-cta").textContent = "Open Inkwell"; }
  } catch { /* server asleep: the links still work */ }
})();
