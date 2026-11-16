// My requests: every request sent from the extension, its legal deadline, and a reminder when a company is late.
import { DAY, TEMPLATES, el, listRequests, mailto, saveRequests, shortDate } from "./common.js";

const list = document.getElementById("list");

async function update(id, patch) {
  const requests = await listRequests();
  const i = requests.findIndex((r) => r.id === id);
  if (i >= 0) { requests[i] = { ...requests[i], ...patch }; await saveRequests(requests); }
  render();
}

async function remove(id) {
  await saveRequests((await listRequests()).filter((r) => r.id !== id));
  render();
}

function row(r, auth) {
  const now = Date.now();
  const left = Math.ceil((r.dueAt - now) / DAY);
  const late = r.status === "waiting" && left < 0;
  const total = Math.max(1, (r.dueAt - r.sentAt) / DAY);
  const status = r.status === "done" ? el("span", { class: "st done" }, "Done")
    : late ? el("span", { class: "st late" }, `Overdue by ${-left} day${left === -1 ? "" : "s"}`)
    : el("span", { class: "st wait" }, "Waiting");
  const progress = r.status === "done" ? el("div", {}, el("small", {}, `Marked answered ${shortDate(r.doneAt || now)}`))
    : late ? el("div", {}, el("small", {}, "They haven't replied in time."))
    : el("div", {}, el("small", {}, `${left} day${left === 1 ? "" : "s"} left`),
      el("div", { class: "bar" }, el("i", { style: `width:${Math.min(100, Math.max(3, ((now - r.sentAt) / DAY / total) * 100))}%` })));
  const reminder = () => TEMPLATES.reminder.make(r.company, auth?.name || "[your name]", auth?.email || "[the email on your account]", r);
  const actions = [];
  if (late) actions.push(el("a", { class: "mini", href: mailto(r.to, reminder()), onclick: () => update(r.id, { remindedAt: now }) }, "Send reminder"));
  if (r.status !== "done") actions.push(el("button", { class: "mini ghost", onclick: () => update(r.id, { status: "done", doneAt: Date.now() }) }, "They replied"));
  else actions.push(el("button", { class: "mini ghost", onclick: () => update(r.id, { status: "waiting", doneAt: null }) }, "Reopen"));
  actions.push(el("button", { class: "mini ghost", title: "Remove from the list", onclick: () => remove(r.id) }, "Remove"));
  return el("li", { class: `rq${late ? " late" : ""}` },
    el("div", {}, el("b", {}, r.company), el("small", {}, r.title)),
    el("div", {}, `Sent ${shortDate(r.sentAt)}`, el("small", {}, `Due ${shortDate(r.dueAt)} · to ${r.to}`)),
    status, progress, el("div", { class: "actions" }, actions));
}

async function render() {
  const [requests, { auth }] = await Promise.all([listRequests(), chrome.storage.local.get("auth")]);
  if (!requests.length) {
    list.replaceChildren(el("li", { class: "empty" }, "No requests yet. When a red line on the Inkwell card says ✉ Request, the email is written for you and tracked here."));
    return;
  }
  const order = (r) => (r.status === "done" ? 2 : r.dueAt < Date.now() ? 0 : 1);
  list.replaceChildren(...[...requests].sort((a, b) => order(a) - order(b) || a.dueAt - b.dueAt).map((r) => row(r, auth)));
}

chrome.storage.onChanged.addListener((changes) => { if (changes.requests) render(); });
render();
