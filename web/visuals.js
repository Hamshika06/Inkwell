// Shared visuals: the 3D exposure blocks (dashboard deck) and the "Where your data goes" orbit map.
// Everything drawn here comes from the report and the policy's own sentences; nothing is guessed. With "reduce
// motion" on, the CSS turns every animation off and the pictures still read.
import { el } from "./shared.js";
import { classify, orbitSvg, readDataFlows } from "./orbit.js";

export { readDataFlows };

/* ---------- Exposure ---------- */

const SHORT = { sale: "sale", ads: "ads", sharing: "sharing", location: "location", retention: "keeping", delete: "delete", optout: "opt out", changes: "changes" };
const ORDER = { red: 0, fixed: 1, yellow: 2, green: 3 };

/** A concern is limited once any of its steps is ticked (a setting or a request both limit it). */
export const limitedBy = (done) => (c) => !!c && c.fixable && c.steps.some((id) => done?.[id]);

/** One cell per check, red first: { id, title, kind: red | fixed | yellow | green }. */
export function exposureCells(report, done) {
  const isLimited = limitedBy(done);
  const byId = Object.fromEntries((report.concerns || []).map((c) => [c.id, c]));
  return report.checks.map((k) => ({
    id: k.id, title: k.title,
    kind: k.tone === "bad" ? (isLimited(byId[k.id]) ? "fixed" : "red") : k.tone === "good" ? "green" : "yellow",
  })).sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);
}

const FACE = { red: ["#e5534b", "#f07c74", "#c9443d"], fixed: ["#2f9e62", "#4dbb7e", "#238052"], green: ["#2f9e62", "#4dbb7e", "#238052"], yellow: ["#e9b949", "#f3cf72", "#cfa137"] };
const HEIGHT = { red: 54, yellow: 28, green: 8, fixed: 8 };
const WORD = { red: "worth knowing", fixed: "you limited it", yellow: "not clearly answered", green: "in your favour" };

function cube(x, y, h, [front, top, side], extra = "") {
  const w = 24, d = 12;
  return `<g ${extra}><polygon points="${x},${y - h} ${x + w},${y - h - d} ${x + 2 * w},${y - h} ${x + w},${y - h + d}" fill="${top}"/>`
    + `<polygon points="${x},${y - h} ${x + w},${y - h + d} ${x + w},${y + d} ${x},${y}" fill="${front}"/>`
    + `<polygon points="${x + w},${y - h + d} ${x + 2 * w},${y - h} ${x + 2 * w},${y} ${x + w},${y + d}" fill="${side}"/></g>`;
}

/**
 * The blocks as an SVG element. cells from exposureCells(). opts: { labels, sinking: [indexes that just got fixed],
 * small }. A block that just got fixed is drawn flat and green, with its old red block sinking into the floor over it.
 */
export function blocksSvg(cells, { labels = true, sinking = [], small = false } = {}) {
  const step = 60, base = 76, width = cells.length * step + 8, height = labels ? 112 : 94;
  const parts = cells.map((c, i) => {
    const x = 4 + i * step;
    let g = cube(x, base, HEIGHT[c.kind], FACE[c.kind], `class="blk blk-${c.kind}"`);
    if (c.kind === "fixed") g += `<text x="${x + 24}" y="${base - 6}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">✓</text>`;
    if (sinking.includes(i)) g += cube(x, base, HEIGHT.red, FACE.red, 'class="blk-sink"');
    const label = labels ? `<text x="${x + 24}" y="${base + 30}" text-anchor="middle" font-size="11" fill="currentColor" opacity=".7">${SHORT[c.id] || c.id}</text>` : "";
    return `<g><title>${c.title}: ${WORD[c.kind]}</title>${g}${label}</g>`;
  }).join("");
  const box = el("span", { class: `blocks${small ? " small" : ""}`, role: "img",
    "aria-label": cells.map((c) => `${c.title}: ${WORD[c.kind]}`).join("; ") });
  // Our own fixed numbers and labels only (no text from the policy), so building the markup as a string is safe.
  box.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" aria-hidden="true">${parts}</svg>`;
  return box;
}

/* ---------- Where your data goes ---------- */

const KIND = { limit: ["You can limit it", "red"], limited: ["You limited it", "green"], service: ["Comes with the service", "grey"], some: ["Only in some cases", "light"] };
const RING_OF = { limit: "Inner ring", limited: "Moved out of the red ring", service: "Middle ring", some: "Outer ring" };

/**
 * The orbit map with its list and the picked company's sentence and fix.
 * opts: { segments | flows, report, company, isLimited(concern), onFix(concernId), onQuote(segment), selected, onSelect(key) }.
 */
export function renderDataMap({ segments, flows: known, report, company, isLimited = () => false, onFix, onQuote, selected, onSelect }) {
  const { recipients, gives } = known || readDataFlows(segments);
  const who = company || "This company";
  const flows = classify(recipients, report?.concerns, isLimited);
  if (!flows.length) {
    return el("section", { class: "dmap empty", "aria-label": "Where your data goes" },
      el("h3", { class: "dmap-title" }, "Where your data goes"),
      el("p", { class: "fine" }, `This policy doesn't name who ${who} shares your data with, in words we recognise. That isn't proof it shares with no one.`));
  }
  const pick = flows.find((f) => f.key === selected) || flows.find((f) => f.kind === "limit") || flows[0];
  const stage = el("div", { class: "dmap-stage" });
  stage.innerHTML = orbitSvg(flows, { company: who, gives, selected: pick.key, id: "orb-web" });  // Escaped inside orbitSvg.
  stage.addEventListener("click", (e) => { const g = e.target.closest?.(".planet"); if (g) onSelect?.(g.dataset.key); });
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) stage.querySelectorAll("animateMotion").forEach((a) => a.parentElement.remove());
  else {
    stage.addEventListener("pointermove", (e) => {
      const r = stage.getBoundingClientRect();
      stage.style.setProperty("--ry", `${((e.clientX - r.left) / r.width - 0.5) * 8}deg`);
      stage.style.setProperty("--rx", `${8 - ((e.clientY - r.top) / r.height - 0.5) * 6}deg`);
    });
    stage.addEventListener("pointerleave", () => { stage.style.removeProperty("--ry"); stage.style.removeProperty("--rx"); });
  }
  const list = el("ul", { class: "dmap-list", "aria-label": "Who gets your data" }, flows.map((f) => el("li", {},
    el("button", { type: "button", class: `dmap-item${f.key === pick.key ? " on" : ""}`, "aria-pressed": String(f.key === pick.key), onclick: () => onSelect?.(f.key) },
      el("i", { class: `orb-dot orb-${f.kind}`, "aria-hidden": "true" }), el("span", {}, el("b", {}, f.name), el("small", {}, `${RING_OF[f.kind]} · ${KIND[f.kind][0].toLowerCase()}`))))));
  const detail = el("div", { class: "dmap-detail", role: "status" },
    el("p", { class: "dmap-detail-k" }, `${who} → ${pick.name}`),
    el("button", { type: "button", class: "receipt", title: "Show this sentence in the full policy", onclick: () => onQuote?.(pick.segment) },
      el("span", { class: "receipt-mark", "aria-hidden": "true" }, "“"), pick.quote),
    el("div", { class: "dmap-actions" },
      pick.kind === "limit" && pick.fix && onFix ? el("button", { type: "button", class: "btn btn-primary", onclick: () => onFix(pick.fix.id) }, "✂ Fix it") : null,
      el("span", { class: "fine" }, { limit: "After you fix it, this planet moves out of the red ring and its beam turns dotted.", limited: "✓ You limited this.",
        service: "This comes with using the service.", some: "Only in some cases, such as when the law requires it." }[pick.kind])));
  return el("section", { class: "dmap", "aria-label": "Where your data goes" },
    el("div", { class: "dmap-head" }, el("h3", { class: "dmap-title" }, "Where your data goes"),
      el("span", { class: "fine" }, "From the policy's own words. Tap anyone to see the sentence.")),
    el("div", { class: "dmap-body" }, stage, el("div", { class: "dmap-side" }, list, detail)));
}
