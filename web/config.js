// Where the Inkwell API lives.
// - On Firebase Hosting (*.web.app, *.firebaseapp.com) the page is static, so it calls the Cloud Run API.
//   That service must list this site in ALLOWED_ORIGINS (see Documentation/DEPLOYMENT.md, Firebase Hosting).
// - Anywhere else, "" means the same server that served this page: the API serves web/ itself, both
//   locally (http://localhost:7860) and on Cloud Run.
const CLOUD_RUN_API = "https://inkwell-846713605562.us-east1.run.app";
window.INKWELL_API = location.port === "5173" ? "http://127.0.0.1:7860"
  : /\.(web\.app|firebaseapp\.com)$/.test(location.hostname) ? CLOUD_RUN_API : "";
