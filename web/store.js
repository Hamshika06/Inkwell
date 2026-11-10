// Where a person's priorities and saved policies live: their account (Cloud Firestore, one document per
// user plus one per saved policy) when they're signed in, or this browser otherwise. If Firestore isn't
// set up or can't be reached, an account falls back to this browser and says so.
// Saved policies keep a name, verdicts, the chosen decision, ticked steps and a SHA-256 fingerprint of the
// text, never the text itself.
const FIREBASE_SDK = "https://www.gstatic.com/firebasejs/13.0.0";
const TIMEOUT_MS = 6000;

export async function openStore(ctx, user) {
  // Without sign-in on the server there are no accounts, so everything is saved in this browser.
  const local = localStore(user ? user.uid : ctx.enabled ? "guest" : "local");
  if (!ctx.enabled || !user) return local;
  try {
    const fs = await import(`${FIREBASE_SDK}/firebase-firestore.js`);
    const db = fs.getFirestore(ctx.auth.app);
    const profile = fs.doc(db, "users", user.uid);
    // Fails fast when Firestore isn't enabled, the rules refuse, or the network is down.
    const snap = await withTimeout(fs.getDoc(profile));
    return cloudStore(fs, db, user.uid, snap.exists() ? snap.data() : {});
  } catch (error) {
    console.warn("Saving to this browser only:", error?.code || error?.message || error);
    return { ...local, mode: "device", fallback: true };
  }
}

function withTimeout(promise) {
  return Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), TIMEOUT_MS))]);
}

function localStore(owner) {
  const key = `inkwell:${owner}`;
  const read = () => { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch { return {}; } };
  const write = (data) => { try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* storage full or blocked */ } };
  return {
    mode: owner === "guest" ? "guest" : "device",
    async getPriorities() { return read().priorities ?? null; },
    async setPriorities(list) { write({ ...read(), priorities: list }); },
    async listPolicies() { return Object.entries(read().policies || {}).map(([id, doc]) => ({ id, ...doc })); },
    async putPolicy(id, patch) {
      const data = read();
      data.policies = { ...(data.policies || {}), [id]: { ...(data.policies?.[id] || {}), ...patch } };
      write(data);
    },
    async deletePolicy(id) { const data = read(); delete data.policies?.[id]; write(data); },
  };
}

function cloudStore(fs, db, uid, profile) {
  const policies = fs.collection(db, "users", uid, "policies");
  return {
    mode: "account",
    async getPriorities() { return profile.priorities ?? null; },
    async setPriorities(list) {
      profile.priorities = list;
      await withTimeout(fs.setDoc(fs.doc(db, "users", uid), { priorities: list }, { merge: true }));
    },
    async listPolicies() {
      const snap = await withTimeout(fs.getDocs(policies));
      return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
    },
    async putPolicy(id, patch) { await withTimeout(fs.setDoc(fs.doc(policies, id), patch, { merge: true })); },
    async deletePolicy(id) { await withTimeout(fs.deleteDoc(fs.doc(policies, id))); },
  };
}

/** A short id from a policy's name: "Pigeonpost" -> "pigeonpost". */
export function policyId(name) {
  return (name || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "policy";
}

/** SHA-256 of the text with whitespace collapsed, so re-pasting the same policy gives the same fingerprint. */
export async function fingerprint(text) {
  const bytes = new TextEncoder().encode(text.replace(/\s+/g, " ").trim());
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
