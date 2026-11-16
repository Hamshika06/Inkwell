// Runs only on Inkwell's own website. When the connect page hands over the sign-in, pass it to the extension.
addEventListener("message", async (event) => {
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data;
  if (!data || data.source !== "inkwell-page") return;
  if (data.type === "ping") {
    postMessage({ source: "inkwell-ext", type: "ready" }, location.origin);
  } else if (data.type === "connect" && location.pathname === "/connect.html") {
    const auth = { open: !!data.open, refreshToken: data.refreshToken, apiKey: data.apiKey, email: data.email, name: data.name };
    const reply = await chrome.runtime.sendMessage({ type: "connect", auth });
    if (reply?.ok && reply.value) postMessage({ source: "inkwell-ext", type: "connected" }, location.origin);
  }
});
