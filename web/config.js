// Where the Inkwell API lives.
// "" (default) = the same server that served this page: the API serves web/ itself, both locally
// (http://127.0.0.1:7860) and on a single-service deploy (Render, Cloud Run, a Space).
// Only if you host web/ separately (Vercel, Netlify, GitHub Pages), put the API's full URL here,
// e.g. "https://inkwell-api.onrender.com". Any page also accepts ?api=https://... for testing.
window.INKWELL_API = location.port === "5173" ? "http://127.0.0.1:7860" : "";
