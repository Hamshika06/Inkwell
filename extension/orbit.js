// "Where your data goes": who a policy says gets your data (read from its own sentences), drawn as an orbit.
// The company is a glowing hub; everyone it shares with is a planet on a tilted ring, and the ring says what
// you can do: inner red = you can limit it, middle grey = comes with the service, outer dashed = only in some
// cases. Limited ones sit just outside the red ring with a dotted beam.
// No imports, no DOM: the website (visuals.js) and the extension (extension/orbit.js, an identical copy kept
// in step by tests/test_orbit_copy.py) both use this file.

/* ---------- Reading the policy ---------- */

const SHARE = /\b(share[sd]?|sharing|disclos\w*|sells?|sold|selling|rent|provides?|provided|transfer\w*|make\s+(?:it\s+)?available|give)\b/i;
const DENY = /\b(?:do not|don't|does not|doesn't|never|will not|won't|not)\s+(?:\w+\s+)?(?:share|sell|disclose|rent|transfer)/i;
// "Receive" counts only when the recipient receives (they may receive your information), not "we receive … from".
const RECEIVE = /\b(?:they|these|which|who|providers?|partners?|vendors?|companies)\s+(?:may\s+|will\s+|also\s+)?receive\b/i;
const COLLECT = /\b(collect\w*|receive\w*|gather\w*|obtain\w*|record\w*|use your)\b/i;

/** Who the policy says gets your data. concerns: report concerns that limit it. kind when nothing limits it. */
export const RECIPIENTS = [
  { key: "advertisers", name: "Advertisers", glyph: "Ad", re: /\b(advertis\w*(?: partners?| networks?| companies)?|ad partners?|ad networks?|marketing partners?)\b/i, concerns: ["ads", "sale", "sharing"], kind: "service" },
  { key: "brokers", name: "Data brokers", glyph: "$", re: /\b(data brokers?|resellers?)\b/i, concerns: ["sale", "sharing"], kind: "service" },
  { key: "social", name: "Social networks", glyph: "@", re: /\b(social (?:media|networks?)|facebook|meta platforms)\b/i, concerns: ["ads", "sharing"], kind: "service" },
  { key: "analytics", name: "Analytics", glyph: "◔", re: /\banalytics(?: providers?| partners?| services?| tools?)?\b/i, concerns: ["sharing"], kind: "service" },
  { key: "affiliates", name: "Affiliates", glyph: "⌂", re: /\b(affiliates?|subsidiar(?:y|ies)|corporate family)\b/i, concerns: [], kind: "service" },
  { key: "providers", name: "Service providers", glyph: "⚙", re: /\b(service providers?|vendors?|processors?|contractors?)\b/i, concerns: [], kind: "service" },
  { key: "law", name: "Law enforcement", glyph: "⚖", re: /\b(law enforcement|government|public authorit\w*|courts?|legal process|subpoenas?)\b/i, concerns: [], kind: "some" },
  { key: "buyer", name: "A company that buys them", glyph: "⇄", re: /\b(mergers?|acquisitions?|acquired|bankruptcy|sale of (?:all|some|part) of)\b/i, concerns: [], kind: "some" },
];
const GIVE = [["Name", /\bnames?\b/i], ["Email", /\be-?mail\b/i], ["Phone", /\bphone\b/i], ["Location", /\blocation\b/i], ["Device", /\bdevice\b/i],
  ["IP address", /\bIP address/i], ["Payment", /\b(payment|credit card|billing)\b/i], ["Contacts", /\bcontacts?\b/i], ["Photos", /\bphotos?\b/i],
  ["Health", /\bhealth\b/i], ["Browsing", /\b(browsing|cookies)\b/i]];

/** segments: [{ id, text }]. Returns { recipients: [{ key, name, glyph, concerns, kind, quote, segment, phrase }], gives: [words] }. */
export function readDataFlows(segments) {
  const sentences = (segments || []).flatMap((s) => s.text.split(/(?<=[.!?])\s+/).map((t) => ({ text: t, segment: s.id })));
  const recipients = [];
  for (const r of RECIPIENTS) {
    const hit = sentences.find((s) => r.re.test(s.text) && (SHARE.test(s.text) || RECEIVE.test(s.text)) && !DENY.test(s.text));
    if (hit) {
      const { re, ...rest } = r;
      recipients.push({ ...rest, quote: hit.text.trim(), segment: hit.segment, phrase: hit.text.match(re)[0] });
    }
  }
  const collect = sentences.filter((s) => COLLECT.test(s.text)).map((s) => s.text).join(" ");
  return { recipients: recipients.slice(0, 7), gives: GIVE.filter(([, re]) => re.test(collect)).map(([w]) => w).slice(0, 4) };
}

/**
 * Each recipient's state, given the report's concerns: limit (red), limited (you fixed it), service, some.
 * isLimited(concern) says whether a fixable concern has been limited. Returns the flows with { kind, fix }.
 */
export function classify(recipients, concerns, isLimited) {
  const byId = Object.fromEntries((concerns || []).map((c) => [c.id, c]));
  return recipients.map((r) => {
    const linked = r.concerns.map((id) => byId[id]).filter((c) => c?.fixable);
    const kind = linked.length ? (linked.some(isLimited) ? "limited" : "limit") : r.kind;
    return { ...r, kind, fix: linked.find((c) => !isLimited(c)) || null };
  });
}

/* ---------- Drawing the orbit ---------- */

const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const COLOR = { limit: "#e5534b", limited: "#2f9e62", service: "#9aa0bd", some: "#a9b1d8" };
const LANE = { limit: 0, limited: 0.5, service: 1, some: 2 };  // Which ring (0.5 = just outside the red one).
// Angles around each ring, avoiding the top (about 230 to 310 degrees), where the ring labels sit.
const START = { limit: [28, 212, 118, 330], limited: [40, 160, 320], service: [336, 160, 75, 200], some: [100, 210, 20] };

/**
 * The orbit as an SVG string. flows: from classify(). opts: { company, gives, selected (key), compact, id }.
 * Every planet is a <g class="planet" data-key="…"> so the page can make it clickable.
 */
export function orbitSvg(flows, { company = "This company", gives = [], selected, compact = false, id = "orb" } = {}) {
  const W = compact ? 420 : 900, H = compact ? 300 : 520, cx = compact ? 236 : 488, cy = compact ? 156 : 286, s = compact ? 0.56 : 1;
  const rings = [[150, 66], [250, 110], [345, 152]].map(([rx, ry]) => [rx * s, ry * s]);
  const at = (lane, deg) => {
    const [a, b] = lane === 0.5 ? [(rings[0][0] + rings[1][0]) / 2, (rings[0][1] + rings[1][1]) / 2] : rings[lane];
    return [cx + a * Math.cos((deg * Math.PI) / 180), cy + b * Math.sin((deg * Math.PI) / 180)];
  };
  const used = { limit: 0, limited: 0, service: 0, some: 0 };
  const placed = flows.map((f) => ({ ...f, pos: at(LANE[f.kind], START[f.kind][used[f.kind]++ % START[f.kind].length]) }));
  const pick = placed.find((f) => f.key === selected) || placed.find((f) => f.kind === "limit") || placed[0];

  const defs = `<defs>
    <radialGradient id="${id}-hub" cx="38%" cy="32%" r="70%"><stop offset="0" stop-color="#8d97ff"/><stop offset=".45" stop-color="#3340c8"/><stop offset="1" stop-color="#141a5c"/></radialGradient>
    <radialGradient id="${id}-limit" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#ffb3ad"/><stop offset=".5" stop-color="#e5534b"/><stop offset="1" stop-color="#a8322b"/></radialGradient>
    <radialGradient id="${id}-limited" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#bff0d3"/><stop offset=".5" stop-color="#2f9e62"/><stop offset="1" stop-color="#1d6b41"/></radialGradient>
    <radialGradient id="${id}-service" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#e6e9f7"/><stop offset=".55" stop-color="#9aa0bd"/><stop offset="1" stop-color="#5f6584"/></radialGradient>
    <radialGradient id="${id}-some" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#ffffff"/><stop offset=".6" stop-color="#d3d8ef"/><stop offset="1" stop-color="#9ea6d6"/></radialGradient>
    <radialGradient id="${id}-you" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#b9c0ff"/><stop offset=".5" stop-color="#4c58e0"/><stop offset="1" stop-color="#2530a6"/></radialGradient>
    <radialGradient id="${id}-floor" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="var(--orb-floor, #dfe3fb)"/><stop offset="1" stop-color="var(--orb-floor, #dfe3fb)" stop-opacity="0"/></radialGradient>
    <filter id="${id}-glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="6"/></filter></defs>`;

  const RING = [["limit", "YOU CAN LIMIT"], ["service", "COMES WITH THE SERVICE"], ["some", "ONLY IN SOME CASES"]];
  let out = `<ellipse cx="${cx}" cy="${cy}" rx="${390 * s}" ry="${175 * s}" fill="url(#${id}-floor)"/>`;
  [2, 1, 0].forEach((i) => {
    const [rx, ry] = rings[i], [kind, label] = RING[i], col = COLOR[kind];
    out += `<ellipse class="ring ring-${kind}" cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="none" stroke="${col}" stroke-opacity=".14" stroke-width="${16 * s}"/>`
      + `<ellipse class="ring-line ring-${kind}" cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="none" stroke="${col}" stroke-opacity=".8" stroke-width="1.6" stroke-dasharray="${kind === "some" ? "6 8" : "60 6"}"/>`;
    if (!compact) {
      const w = label.length * 6.6 + 18;
      out += `<g class="ring-label"><rect x="${cx - w / 2}" y="${cy - ry - 11}" width="${w}" height="20" rx="10" fill="var(--orb-card, #fff)" stroke="${col}" stroke-opacity=".6"/>`
        + `<text x="${cx}" y="${cy - ry + 3}" text-anchor="middle" font-size="10" font-weight="700" letter-spacing=".9" fill="${kind === "some" ? "#7d84ad" : col}">${label}</text></g>`;
    }
  });

  // You, and what you give flowing into the hub as ink dots.
  const R = 44 * s, yx = compact ? 30 : 58, yy = cy + (compact ? 10 : 20) * s;
  for (let i = 0, n = compact ? 8 : 14; i < n; i++) {
    const t = i / (n - 1), x = yx + 30 * s + (cx - R - 6 - yx - 30 * s) * t, y = yy + (cy - yy) * t ** 1.6 - Math.sin(t * Math.PI) * 26 * s;
    out += `<circle class="stream" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${((2.2 + 2 * t) * s).toFixed(2)}" fill="#3340c8" opacity="${(0.25 + 0.55 * t).toFixed(2)}" style="--i:${i}"/>`;
  }
  if (!compact && gives.length) {
    out += `<text x="24" y="40" font-size="10.5" font-weight="700" letter-spacing="1" fill="var(--orb-muted, #575e86)">WHAT YOU GIVE THEM</text>`;
    gives.forEach((g, i) => {
      const w = g.length * 7 + 24;
      out += `<rect x="24" y="${52 + i * 32}" width="${w}" height="24" rx="12" fill="var(--orb-chip, #eef0fd)" stroke="#c7cdee"/><text x="${24 + w / 2}" y="${68 + i * 32}" text-anchor="middle" font-size="11" font-weight="600" fill="#3340c8">${esc(g)}</text>`;
    });
    out += `<path d="M64 ${56 + gives.length * 32} Q56 ${yy - 60} ${yx} ${yy - 30}" stroke="#c7cdee" stroke-width="2" fill="none" stroke-dasharray="3 5"/>`;
  }

  // Beams from the hub, the picked one lit with flowing dots.
  for (const f of placed) {
    const [px, py] = f.pos, col = COLOR[f.kind], mx = (cx + px) / 2, my = Math.min(cy, py) - 40 * s;
    const d = `M${cx} ${(cy - 6 * s).toFixed(1)} Q${mx.toFixed(1)} ${my.toFixed(1)} ${px.toFixed(1)} ${py.toFixed(1)}`;
    const dash = f.kind === "some" ? ' stroke-dasharray="4 6"' : f.kind === "limited" ? ' stroke-dasharray="1 7" stroke-linecap="round"' : "";
    if (f === pick) {
      out += `<path d="${d}" stroke="${col}" stroke-width="${14 * s}" fill="none" opacity=".18"/><path class="beam-lit" d="${d}" stroke="${col}" stroke-width="${4 * s}" fill="none"${dash}/>`;
      for (let k = 0; k < 3; k++) {
        const begin = `${(k * 0.8).toFixed(1)}s`;
        out += `<circle r="${4 * s}" fill="var(--orb-card, #fff)" stroke="${col}" stroke-width="2" visibility="hidden"><set attributeName="visibility" to="visible" begin="${begin}"/>`
          + `<animateMotion class="flow" dur="2.4s" begin="${begin}" repeatCount="indefinite" path="${d}"/></circle>`;
      }
    } else {
      out += `<path d="${d}" stroke="${col}" stroke-width="${2.2 * s}" fill="none" opacity=".6"${dash}/>`;
    }
  }

  // The hub.
  out += `<ellipse cx="${cx}" cy="${cy + R + 6}" rx="${R * 1.1}" ry="${R / 3.6}" fill="#11163a" opacity=".2"/>`
    + `<circle cx="${cx}" cy="${cy}" r="${R + 10 * s}" fill="#3340c8" opacity=".25" filter="url(#${id}-glow)"/>`
    + `<circle cx="${cx}" cy="${cy}" r="${R}" fill="url(#${id}-hub)"/><ellipse cx="${cx - R / 3}" cy="${cy - R / 2.4}" rx="${R / 2.6}" ry="${R / 5.5}" fill="#fff" opacity=".45"/>`
    + `<text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="${compact ? 12 : 14}" font-weight="700" fill="#fff">${esc(company.length > 13 ? `${company.slice(0, 12)}…` : company)}</text>`;
  out += `<ellipse cx="${yx}" cy="${yy + 30 * s}" rx="${24 * s}" ry="${6 * s}" fill="#11163a" opacity=".14"/><circle cx="${yx}" cy="${yy}" r="${26 * s}" fill="url(#${id}-you)"/>`
    + `<ellipse cx="${yx - 8 * s}" cy="${yy - 11 * s}" rx="${9 * s}" ry="${4.5 * s}" fill="#fff" opacity=".5"/><text x="${yx}" y="${yy + 5}" text-anchor="middle" font-size="${compact ? 11 : 13}" font-weight="700" fill="#fff">You</text>`;

  // The planets, each clickable.
  placed.forEach((f, i) => {
    const [px, py] = f.pos, r = (compact ? 14 : 18) * s * (compact ? 1.6 : 1), col = COLOR[f.kind], on = f === pick;
    const ink = f.kind === "limit" ? "#b8322a" : f.kind === "limited" ? "#17683b" : "var(--orb-text, #3b4268)";
    let g = `<g class="planet planet-${f.kind}${on ? " on" : ""}" data-key="${f.key}" style="--i:${i}" tabindex="-1">`;
    if (on) g += `<circle cx="${px}" cy="${py}" r="${r + 12 * s}" fill="${col}" opacity=".35" filter="url(#${id}-glow)"/><circle cx="${px}" cy="${py}" r="${r + 7 * s}" fill="none" stroke="${col}" stroke-width="2" opacity=".85"/>`;
    g += `<ellipse cx="${px}" cy="${py + r + 3}" rx="${r}" ry="${r / 3.5}" fill="#11163a" opacity=".14"/>`
      + `<circle cx="${px}" cy="${py}" r="${r}" fill="url(#${id}-${f.kind})"/><ellipse cx="${px - r / 3}" cy="${py - r / 2.6}" rx="${r / 2.6}" ry="${r / 5}" fill="#fff" opacity=".55"/>`
      + `<text x="${px}" y="${py + 4}" text-anchor="middle" font-size="${f.glyph === "Ad" ? 11 : 13}" font-weight="700" fill="#fff">${f.kind === "limited" ? "✓" : esc(f.glyph || "•")}</text>`;
    if (compact) {
      g += `<text x="${px}" y="${py + r + 15}" text-anchor="middle" font-size="13" font-weight="700" fill="${ink}">${esc(f.name.split(" ")[0])}</text>`;
    } else {
      const phrase = f.phrase.length > 24 ? `${f.phrase.slice(0, 23)}…` : f.phrase, w = Math.max(f.name.length * 7.4 + 20, phrase.length * 5.6 + 24);
      g += `<rect x="${px - w / 2}" y="${py + r + 8}" width="${w}" height="38" rx="10" fill="var(--orb-card, #fff)" stroke="${col}" stroke-opacity="${on ? 0.9 : 0.5}" stroke-width="${on ? 2 : 1.2}"/>`
        + `<text x="${px}" y="${py + r + 24}" text-anchor="middle" font-size="12.5" font-weight="700" fill="${ink}">${esc(f.name)}</text>`
        + `<text x="${px}" y="${py + r + 38}" text-anchor="middle" font-size="10" fill="var(--orb-muted, #575e86)">“${esc(phrase)}”</text>`;
    }
    out += `${g}</g>`;
  });
  return `<svg class="orbit" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Where your data goes: ${esc(placed.map((f) => f.name).join(", "))}">${defs}${out}</svg>`;
}
