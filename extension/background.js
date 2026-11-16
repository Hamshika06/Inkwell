// Background worker: keeps the Inkwell sign-in, turns the "don't sell or share" signal on and off, and
// reminds people about requests that are due. It never reads pages by itself; the popup does that on a click.
import { DAY, apiBase, getSettings, listRequests, saveRequests, saveSettings, shortDate } from "./common.js";

const GPC_RULE = 1;
const ALL_TYPES = ["main_frame", "sub_frame", "stylesheet", "script", "image", "font", "object", "xmlhttprequest",
  "ping", "csp_report", "media", "websocket", "other"];

/* ---------- Sign-in ---------- */

/** A fresh Firebase ID token for API calls; "" when the server needs no sign-in; null when signed out. */
async function idToken() {
  const { auth } = await chrome.storage.local.get("auth");
  if (!auth) return null;
  if (auth.open) return "";
  const { token } = await chrome.storage.session.get("token");
  if (token && token.exp > Date.now() + 60_000) return token.value;
  const response = await fetch(`https://securetoken.googleapis.com/v1/token?key=${encodeURIComponent(auth.apiKey)}`, {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: auth.refreshToken }),
  });
  if (!response.ok) {
    if (response.status === 400 || response.status === 401 || response.status === 403) await signOut();  // Revoked or expired.
    return null;
  }
  const data = await response.json();
  if (data.refresh_token && data.refresh_token !== auth.refreshToken) await chrome.storage.local.set({ auth: { ...auth, refreshToken: data.refresh_token } });
  await chrome.storage.session.set({ token: { value: data.id_token, exp: Date.now() + Number(data.expires_in || 3600) * 1000 } });
  return data.id_token;
}

async function signOut() {
  await chrome.storage.local.remove("auth");
  await chrome.storage.session.remove("token");
}

/** The connect page on Inkwell's site handed over a sign-in: keep it, close that tab, go back to the checked page. */
async function connected(auth, sender) {
  const settings = await getSettings();
  if (!sender.url || new URL(sender.url).origin !== new URL(apiBase(settings)).origin) return false;
  await chrome.storage.local.set({ auth: auth.open ? { open: true } :
    { refreshToken: auth.refreshToken, apiKey: auth.apiKey, email: auth.email || "", name: auth.name || "" } });
  await chrome.storage.session.remove("token");
  const { returnTo } = await chrome.storage.session.get("returnTo");
  await chrome.storage.session.remove("returnTo");
  setTimeout(async () => {
    try { if (sender.tab?.id) await chrome.tabs.remove(sender.tab.id); } catch { /* already closed */ }
    if (returnTo) {
      try {
        const tab = await chrome.tabs.update(returnTo, { active: true });
        await chrome.windows.update(tab.windowId, { focused: true });
      } catch { /* that tab was closed */ }
    }
  }, 1200);
  return true;
}

/* ---------- "Don't sell or share my data" (Global Privacy Control) ---------- */

async function applyGpc(on) {
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: [GPC_RULE],
    addRules: on ? [{ id: GPC_RULE, priority: 1, condition: { urlFilter: "*", resourceTypes: ALL_TYPES },
      action: { type: "modifyHeaders", requestHeaders: [{ header: "Sec-GPC", operation: "set", value: "1" }] } }] : [],
  });
  const registered = await chrome.scripting.getRegisteredContentScripts({ ids: ["gpc"] });
  if (registered.length) await chrome.scripting.unregisterContentScripts({ ids: ["gpc"] });
  if (on) {
    await chrome.scripting.registerContentScripts([{ id: "gpc", matches: ["<all_urls>"], js: ["gpc.js"],
      runAt: "document_start", world: "MAIN", allFrames: true, persistAcrossSessions: true }]);
  }
}

/** On start: the switch stays on only while Chrome still allows it on every site. */
async function syncGpc() {
  const { gpc } = await getSettings();
  const allowed = await chrome.permissions.contains({ origins: ["<all_urls>"] });
  if (gpc && !allowed) await saveSettings({ gpc: false });
  await applyGpc(gpc && allowed);
}

/* ---------- Request reminders ---------- */

async function checkRequests() {
  const requests = await listRequests();
  const now = Date.now();
  let changed = false;
  for (const r of requests) {
    if (r.status !== "waiting") continue;
    if (now > r.dueAt && !r.remindedLate) {
      notify(r.id, `${r.company} is late`, `They haven't answered your “${r.title}” request, due ${shortDate(r.dueAt)}. You can send a reminder.`);
      r.remindedLate = changed = true;
    } else if (now > r.dueAt - 7 * DAY && now <= r.dueAt && !r.remindedSoon) {
      notify(r.id, `${r.company} has a week left`, `Your “${r.title}” request is due ${shortDate(r.dueAt)}. Has it been answered?`);
      r.remindedSoon = changed = true;
    }
  }
  if (changed) await saveRequests(requests);
}

function notify(id, title, message) {
  chrome.notifications.create(`request:${id}`, { type: "basic", iconUrl: "icons/icon128.png", title, message, priority: 1 });
}

/* ---------- Wiring ---------- */

chrome.runtime.onInstalled.addListener(() => { syncGpc(); chrome.alarms.create("requests", { periodInMinutes: 360 }); });
chrome.runtime.onStartup.addListener(() => { syncGpc(); checkRequests(); });
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === "requests") checkRequests(); });
// Chrome may close the popup while it asks for a permission; finish what the person asked for here.
chrome.permissions.onAdded.addListener(async (added) => {
  const { pending } = await chrome.storage.session.get("pending");
  if (!pending) return;
  await chrome.storage.session.remove("pending");
  if (pending.gpc && added.origins?.includes("<all_urls>")) { await saveSettings({ gpc: true }); await applyGpc(true); }
  if (pending.block && added.permissions?.includes("contentSettings")) {
    await chrome.contentSettings.location.set({ primaryPattern: `${pending.block}/*`, setting: "block" });
  }
});
chrome.permissions.onRemoved.addListener(async (removed) => {
  if (removed.origins?.includes("<all_urls>")) { await saveSettings({ gpc: false }); await applyGpc(false); }
});
chrome.notifications.onClicked.addListener((id) => {
  if (id.startsWith("request:")) chrome.tabs.create({ url: chrome.runtime.getURL("requests.html") });
  chrome.notifications.clear(id);
});

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  const handlers = {
    token: () => idToken(),
    "sign-out": () => signOut(),
    "connect-start": async () => {
      await chrome.storage.session.set({ returnTo: message.tabId });
      const settings = await getSettings();
      await chrome.tabs.create({ url: `${apiBase(settings)}/connect.html?mode=${message.mode === "signup" ? "signup" : "signin"}` });
      return true;
    },
    connect: () => connected(message.auth || {}, sender),
    "gpc-set": async () => { await saveSettings({ gpc: !!message.on }); await applyGpc(!!message.on); return true; },
    "check-requests": () => checkRequests(),
  };
  const handler = handlers[message?.type];
  if (!handler) return false;
  // Only the connect message may come from a web page (through bridge.js); the rest come from the extension's own pages.
  if (message.type !== "connect" && sender.id !== chrome.runtime.id) return false;
  if (message.type !== "connect" && sender.url && !sender.url.startsWith(chrome.runtime.getURL(""))) return false;
  Promise.resolve(handler()).then((value) => reply({ ok: true, value }), (error) => reply({ ok: false, error: String(error?.message || error) }));
  return true;
});
