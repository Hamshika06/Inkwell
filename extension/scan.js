// Functions the popup runs inside the current page, only when the person opens Inkwell (activeTab).
// Each must be self-contained: Chrome copies the function's source into the page.

/** Finds the page's privacy policy link and, on sign-up forms, quick wins before agreeing. */
export async function scanPage() {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

  // The privacy policy link.
  const seen = new Set();
  const links = [];
  for (const a of document.querySelectorAll("a[href]")) {
    const href = a.href.split("#")[0];
    if (!/^https?:/i.test(href) || seen.has(href)) continue;
    const text = clean(a.textContent || a.getAttribute("aria-label") || a.title);
    let score = /privacy\s*(policy|notice|statement)|datenschutz|politique de confidentialit|pol[ií]tica de privacidad/i.test(text) ? 3
      : /\bprivacy\b/i.test(text) ? 2 : /privacy/i.test(href) ? 1 : 0;
    if (/cookie|choices|settings|do not sell|preferences/i.test(text)) score -= 1.5;
    if (score > 0) { seen.add(href); links.push({ url: href, text: text.slice(0, 80), score }); }
  }
  links.sort((a, b) => b.score - a.score);

  // Sign-up quick wins: only on a page with a password field and sign-up wording.
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
  const labelOf = (el) => clean([...(el.labels || [])].map((l) => l.textContent).join(" ") || el.getAttribute("aria-label") ||
    el.placeholder || el.closest("label")?.textContent || el.name || el.id);
  const inputs = [...document.querySelectorAll("input, select")].filter((el) => el.type !== "hidden" && visible(el));
  const passwords = inputs.filter((el) => el.type === "password");
  const pageWords = clean([...document.querySelectorAll("h1, h2, h3, button, input[type=submit], [role=button], legend")].map((n) => n.textContent || n.value).join(" "));
  const signup = passwords.length > 1 || (passwords.length > 0 && /sign\s*up|create\s+(an\s+|your\s+)?account|register|join\s+(now|free|us)|get\s+started/i.test(pageWords));

  document.querySelectorAll("[data-inkwell-tip]").forEach((el) => el.removeAttribute("data-inkwell-tip"));
  const tips = [];
  const mark = (el, kind, detail = "") => { el.setAttribute("data-inkwell-tip", kind); tips.push({ kind, label: labelOf(el).slice(0, 60), detail }); };
  if (signup) {
    const email = inputs.find((el) => el.type === "email" || /e-?mail/i.test(labelOf(el)));
    if (email) mark(email, "email");
    const someRequired = inputs.some((el) => el.required || el.getAttribute("aria-required") === "true" || /\*/.test(labelOf(el)));
    for (const el of inputs) {
      if (el === email || el.type === "password" || el.type === "checkbox" || el.type === "radio") continue;
      const label = labelOf(el);
      if (!/phone|mobile|cell|birth|\bdob\b|gender|address|zip|postal|company|job/i.test(label)) continue;
      const optional = /optional/i.test(label) || (someRequired && !el.required && el.getAttribute("aria-required") !== "true" && !/\*/.test(label));
      if (optional) mark(el, "optional");
    }
    for (const box of inputs.filter((el) => el.type === "checkbox" && el.checked)) {
      if (/offer|newsletter|marketing|promot|partner|special deals|updates|news\b|e-?mails? (from|about)|sms|text messages/i.test(labelOf(box))) mark(box, "marketing");
    }
  }
  let location = "unknown";
  try { location = (await navigator.permissions.query({ name: "geolocation" })).state; } catch { /* not supported */ }
  return { origin: window.location.origin, title: document.title.slice(0, 100), policy: links.slice(0, 3), signup, tips, location };
}

/** Outlines the marked fields and puts a short tag beside each. Clicking a tag hides them all. */
export function highlightTips(words) {
  document.getElementById("inkwell-tip-style")?.remove();
  document.querySelectorAll(".inkwell-tip-tag").forEach((t) => t.remove());
  const marked = [...document.querySelectorAll("[data-inkwell-tip]")];
  if (!marked.length) return 0;
  const style = document.createElement("style");
  style.id = "inkwell-tip-style";
  style.textContent = `[data-inkwell-tip]{outline:3px solid #3340c8!important;outline-offset:2px!important;border-radius:6px}
  .inkwell-tip-tag{position:absolute;z-index:2147483647;background:#3340c8;color:#fff;font:600 12px/1.2 system-ui,sans-serif;padding:6px 10px;border-radius:7px;
  box-shadow:0 6px 16px -6px rgba(17,22,58,.6);cursor:pointer;white-space:nowrap;max-width:260px;overflow:hidden;text-overflow:ellipsis}`;
  document.head.append(style);
  const hide = () => { style.remove(); document.querySelectorAll(".inkwell-tip-tag").forEach((t) => t.remove());
    document.querySelectorAll("[data-inkwell-tip]").forEach((el) => el.removeAttribute("data-inkwell-tip")); };
  for (const el of marked) {
    const target = el.type === "checkbox" ? (el.closest("label") || el.parentElement || el) : el;
    const r = target.getBoundingClientRect();
    const tag = document.createElement("div");
    tag.className = "inkwell-tip-tag";
    tag.textContent = words[el.getAttribute("data-inkwell-tip")] || "Inkwell tip";
    tag.title = "Inkwell tip. Click to hide these.";
    tag.addEventListener("click", hide);
    document.body.append(tag);
    const width = tag.offsetWidth;
    const left = r.left - width - 12 >= 0 ? r.left - width - 12 : Math.max(4, r.left);
    const top = r.left - width - 12 >= 0 ? r.top + r.height / 2 - tag.offsetHeight / 2 : r.top - tag.offsetHeight - 6;
    tag.style.left = `${left + scrollX}px`;
    tag.style.top = `${Math.max(0, top + scrollY)}px`;
  }
  marked[0].scrollIntoView({ block: "center", behavior: "smooth" });
  return marked.length;
}
