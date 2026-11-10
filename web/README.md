# Inkwell web

Static frontend for the Inkwell API: plain HTML, CSS and JavaScript, with no build step and no dependencies.

## Pages

- **`index.html`**: the public home page: what Inkwell does, an animated example report card, what we check, free vs account, About, our privacy promise and FAQ. No sign-in needed.
- **`login.html`**: sign in with Google, GitHub, or email and password (with a username at sign-up, and a password reset link). Uses Firebase Authentication; the settings come from the API's `/auth-config`. New email and password accounts stop at a "Check your inbox" screen until the address is confirmed. When sign-in isn't configured on the server, this page says so and links to the app.
- **`app.html`**: the product. Visitors without an account get a **free check** (300 KB, rate-limited by the API): the report card's verdicts, the quotes for the first two checks that have one, and the topic overview. Everything else shows a "Sign up free" prompt. Signed-in users get everything, and every analysis carries their Firebase ID token, which the API checks. `app.html?sample=1` runs the sample policy straight away.

## Features

- **Decision bar** (top of the report card): what the policy allows, how much of it you can switch off with steps from the policy, and three equal choices: take the steps, agree anyway, or not for me. Nothing is pre-selected and nothing is called good or bad; the reader's **priorities** (pick what matters, saved per account or browser) decide what is highlighted.
- **Your steps:** a checklist of opt-out links from the policy, general advice where marked, and pre-written opt-out, deletion and access emails to the policy's privacy address ("Open in my email app" or "Copy text"; nothing is sent by Inkwell).
- **My policies:** save a check (name, the 8 answers, choice, ticked steps and a SHA-256 fingerprint of the text, never the text). "Check again" shows which answers changed. Stored in Cloud Firestore for accounts (`store.js`, rules in `firestore.rules`), or in the browser when Firestore isn't set up or sign-in is off. Free checks can't save.
- **Report card** (shown first): eight checks (sells your data, targeted ads, sharing, location, retention, deletion, opt-out, policy changes), each with a verdict, one line on what it means for you, and the exact sentence behind it. Comes from `inkwell/report.py`.
- **What you can do:** opt-out links, privacy emails and settings paths found in the policy.
- **Full breakdown** (behind a button): the views below.
- **One model:** a RoBERTa model trained on OPP-115, PolicyIE and GoPPC sorts every paragraph into five topics (Data Collection & Use, Data Sharing, User Rights & Choices, Data Security & Retention, Policy Scope & Changes). "How Inkwell reads a policy" in the run card explains it.
- **Summary tiles:** paragraphs read, topics covered, topics not mentioned, and paragraphs with no topic.
- **Topics:** one card per topic with a plain-language description and its clause count. Topics with no matching paragraph are marked **Not mentioned**.
- **Common questions:** one question per topic, each with a one-line answer from the report card and its three strongest clauses ("Show all" for the rest).
- **Document:** every paragraph, colour-coded by topic, with filters. Selecting a paragraph shows how close it came to each topic's cutoff.
- **Exports:** a Markdown evidence report or the raw JSON.
- **Input helpers:** sample policy, .txt/.md upload, size and paragraph counters, a warning for one-long-paragraph text, "Fix line breaks", and Ctrl+Enter to run.
- **Account menu, status light, light and dark themes** (follows the system; the moon button switches and remembers it in this browser).

Policy text is only ever inserted as text, never as HTML.

## Run locally

The API serves this folder, so start it and open the API's address. On Windows, from the repository root, run `api\run_local.cmd` and open http://localhost:7860. Opening `index.html` as a file won't work: the page can't call the API from `file://`.

To work on the page with a separate static server, run `python -m http.server 5173 --directory web`. On port 5173 the page calls `http://127.0.0.1:7860`.

## Point it at another API

`config.js` defaults to the server that served the page. On static hosts (`*.vercel.app`, `*.web.app`, `*.firebaseapp.com`) it calls the Cloud Run API instead; add a custom domain to `STATIC_HOSTS` there. The API must list the site's origin in `ALLOWED_ORIGINS`, and Firebase must list its domain under Authorized domains. Vercel steps: `Documentation/DEPLOYMENT.md`, "Front end on Vercel".
