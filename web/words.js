// Plain words for the report card: what each answer means for the reader, and short explanations of the jargon
// policies use (shown when you hover or focus a dotted word). Nothing here changes a verdict; it only explains it.

/** "For you, this means": one line per check, for answers that are worth knowing (red). {co} is the company. */
export const FOR_YOU = {
  sale: "Your details could be sold to other companies, who can then use them for their own purposes.",
  ads: "The ads you see, in {co} and possibly in other apps and sites, are picked using what you do in {co}. Ad companies may get that information too.",
  sharing: "Other companies get some of your information. The policy decides who, not you.",
  location: "{co} can know roughly where you are, and in some cases where you go.",
  retention: "Your data may stay with {co} long after you stop using it.",
  delete: "You may not be able to get your data removed, even if you leave.",
  optout: "There's no clear way to say no to how your data is used.",
  changes: "The rules can change later, and you may not be told before they do.",
};

export const forYou = (id, company) => (FOR_YOU[id] || "").replaceAll("{co}", company || "this company");

/** Jargon, matched in quoted sentences and explanations. The first match of each term in a block gets a tooltip. */
const TERMS = [
  [/\bthird[- ]part(?:y|ies)\b/i, "Third parties", "Any company that isn't {co} or you."],
  [/\b(?:advertising|ad|marketing) partners\b|\badvertisers\b/i, "Advertising partners", "Other companies that show or measure ads. Policies rarely name them, so you can't tell exactly who."],
  [/\banalytics(?: providers| partners| services)?\b/i, "Analytics", "Tools that record how you use an app or site, often run by another company."],
  [/\baffiliates?\b/i, "Affiliates", "Companies owned by, or connected to, the same parent company as {co}."],
  [/\bservice providers?\b|\bvendors\b|\bprocessors\b/i, "Service providers", "Companies hired to run parts of the service, such as hosting, payments or customer support."],
  [/\bcookies?\b/i, "Cookies", "Small files a website saves in your browser so it can recognise you next time."],
  [/\bpersonal (?:information|data)\b/i, "Personal information", "Anything that can identify you: your name, email, phone number, device IDs or location."],
  [/\bopt[- ]out\b/i, "Opt out", "Telling a company to stop doing something with your data."],
  [/\bdo not track\b/i, "Do Not Track", "A browser setting that asks sites not to track you. Most sites ignore it."],
  [/\bglobal privacy control\b|\bGPC\b/, "Global Privacy Control", "A browser signal meaning “don't sell or share my data”. In California and some other US states, companies must follow it."],
  [/\bCCPA\b|\bCPRA\b/, "CCPA", "California's privacy law. It gives California residents the right to know, delete and stop the sale of their data."],
  [/\bGDPR\b/, "GDPR", "The EU and UK privacy law. It gives people there strong rights over their data."],
  [/\bIP address(?:es)?\b/i, "IP address", "Your device's internet address. It reveals roughly where you are."],
  [/\bretain(?:s|ed)?\b|\bretention\b/i, "Retain", "Keep. How long a company retains data is how long it keeps it."],
  [/\bdevice (?:identifiers?|IDs?|information)\b/i, "Device identifiers", "Codes that identify your phone or computer, which can link what you do across apps."],
];

/**
 * Adds hover explanations to jargon inside `root`, in the elements matching `selector`. Each term is explained
 * once per block. Inside buttons (quoted sentences) the explanation shows on hover; elsewhere it can also be focused.
 */
export function glossify(root, selector, company) {
  if (!root) return;
  for (const block of root.querySelectorAll(selector)) {
    if (block.dataset.glossed) continue;
    block.dataset.glossed = "1";
    const focusable = !block.closest("button");
    const used = new Set();
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.parentElement.closest(".term") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (let node of nodes) {
      while (node) {
        // The earliest unexplained term in what's left of this text.
        let best = null;
        for (const t of TERMS) {
          if (used.has(t[1])) continue;
          const m = t[0].exec(node.data);
          if (m && (!best || m.index < best.m.index)) best = { m, t };
        }
        if (!best) break;
        const { m, t: [, title, text] } = best;
        used.add(title);
        const after = node.splitText(m.index);
        const rest = after.splitText(m[0].length);
        const term = document.createElement("span");
        term.className = "term";
        if (focusable) term.tabIndex = 0;
        const tip = document.createElement("span");
        tip.className = "term-tip";
        tip.setAttribute("role", "tooltip");
        tip.append(Object.assign(document.createElement("b"), { textContent: title }), text.replaceAll("{co}", company || "the company"));
        term.append(after.data, tip);
        after.replaceWith(term);
        node = rest;
      }
    }
  }
}
