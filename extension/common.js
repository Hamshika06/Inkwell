// Shared by the popup, the requests page and the background worker.

export const DEFAULT_API = "https://inkwell-846713605562.us-east1.run.app";
export const DAY = 24 * 60 * 60 * 1000;

const DEFAULTS = { api: DEFAULT_API, gpc: false, tips: true, region: "us" };

export async function getSettings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
}
export const saveSettings = (patch) => chrome.storage.local.set(patch);
export const apiBase = (settings) => (settings.api || DEFAULT_API).replace(/\/+$/, "");

/** How long a company has to answer a request, by where the person lives. */
export function deadline(region) {
  return region === "eu" ? { days: 30, text: "1 month", law: "GDPR" } : { days: 45, text: "45 days", law: "CCPA" };
}
export const shortDate = (ms) => new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/** Builds a DOM node. Text is always added as text, never as HTML. */
export function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  return node;
}

// Pre-written requests: the same wording as the Inkwell website.
const LAW = "Where they apply to me, I'm making this request under privacy laws such as the California Consumer Privacy Act (CCPA, as amended by the CPRA) and the EU/UK General Data Protection Regulation (GDPR).";
export const TEMPLATES = {
  delete: { title: "Delete my data", make: (c, name, email) => ({
    subject: "Request to delete my personal information",
    body: `Hello ${c} privacy team,\n\nI'm asking you to delete the personal information you hold about me, and to tell any companies you have shared it with to delete it too.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nPlease confirm when this is done. If you keep any of my information, please tell me what you keep and why, and let me know if you need anything else to verify my identity.\n\n${LAW}\n\nThank you,\n${name}` }) },
  optout: { title: "Stop selling or sharing my data", make: (c, name, email) => ({
    subject: "Please do not sell or share my personal information",
    body: `Hello ${c} privacy team,\n\nPlease stop selling or sharing my personal information, including for targeted (cross-context behavioral) advertising, and opt me out of any such use from now on.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nPlease confirm once this is in place.\n\n${LAW}\n\nThank you,\n${name}` }) },
  access: { title: "Copy of my data", make: (c, name, email) => ({
    subject: "Request for a copy of my personal information",
    body: `Hello ${c} privacy team,\n\nPlease send me a copy of the personal information you hold about me, including where you got it, what you use it for, and which companies you have shared or sold it to.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nLet me know if you need anything else to verify my identity.\n\n${LAW}\n\nThank you,\n${name}` }) },
  reminder: { title: "Reminder", make: (c, name, email, original) => ({
    subject: `Follow-up: ${original.subject}`,
    body: `Hello ${c} privacy team,\n\nOn ${new Date(original.sentAt).toLocaleDateString()} I sent you a request (“${original.subject}”). I haven't had a reply, and the time the law allows for one has passed.\n\nPlease respond as soon as possible.\n\nName: ${name}\nEmail address I use with you: ${email}\n\nThank you,\n${name}` }) },
};

export const mailto = (to, { subject, body }) =>
  `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

export async function listRequests() {
  return (await chrome.storage.local.get({ requests: [] })).requests;
}
export async function saveRequests(requests) {
  await chrome.storage.local.set({ requests });
}
