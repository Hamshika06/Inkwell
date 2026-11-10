// Where the Inkwell API lives.
// - On static hosts (Vercel *.vercel.app, Firebase Hosting *.web.app / *.firebaseapp.com) the page has no
//   server of its own, so it calls the Cloud Run API. That service must list the site's address in
//   ALLOWED_ORIGINS (see Documentation/DEPLOYMENT.md, "Front end on Vercel").
// - Anywhere else, "" means the same server that served this page: the API serves web/ itself, both
//   locally (http://localhost:7860) and on Cloud Run.
// On a custom domain pointed at Vercel, add the domain to STATIC_HOSTS.
const CLOUD_RUN_API = "https://inkwell-846713605562.us-east1.run.app";
const STATIC_HOSTS = /\.(vercel\.app|web\.app|firebaseapp\.com)$/;
window.INKWELL_API = location.port === "5173" ? "http://127.0.0.1:7860"
  : STATIC_HOSTS.test(location.hostname) ? CLOUD_RUN_API : "";
