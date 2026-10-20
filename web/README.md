# Inkwell web

Static frontend for the Inkwell API: plain HTML, CSS and JavaScript, with no build step and no dependencies.

## Pages

- **`login.html`**: sign in with Google, GitHub, or email and password (with a username at sign-up, and a password reset link). Uses Firebase Authentication; the settings come from the API's `/auth-config`. When sign-in isn't configured on the server, this page says so and links to the app.
- **`index.html`**: the product. When sign-in is on, visitors who aren't signed in are sent to the login page, and every analysis carries the user's Firebase ID token, which the API checks.

## Features

- **Models:** pick TF-IDF + SVM, DistilBERT or RoBERTa (C3PA + OPP-115), or **Compare all models** on the same text. Each option shows its speed and whether the server has it loaded.
- **Summary tiles:** paragraphs read, topics covered, topics not mentioned, and analysis time.
- **Overview:** one card per topic with a plain-language description and its clause count. Topics with no matching paragraph are marked **Not mentioned**.
- **Common questions:** the five FAQ questions, each answered with the exact paragraphs the model tagged.
- **Document:** every paragraph, colour-coded by topic, with filters. Selecting a paragraph shows how close it came to each topic's cutoff.
- **Compare models:** a per-topic count table, plus paragraph-by-paragraph agreement with a "show only disagreements" toggle.
- **Exports:** a Markdown evidence report or the raw JSON.
- **Input helpers:** sample policy, .txt/.md upload, size and paragraph counters, a warning for one-long-paragraph text, "Fix line breaks", and Ctrl+Enter to run.
- **Account menu, status light, light and dark themes** (follows the system; the moon button switches and remembers it in this browser).

Policy text is only ever inserted as text, never as HTML.

## Run locally

The API serves this folder, so start it and open the API's address. On Windows, from the repository root, run `api\run_local.cmd` and open http://localhost:7860. Opening `index.html` as a file won't work: the page can't call the API from `file://`.

To work on the page with a separate static server, run `python -m http.server 5173 --directory web`. On port 5173 the page calls `http://127.0.0.1:7860`.

## Point it at another API

`config.js` defaults to the server that served the page. If you host this folder separately (Vercel, Netlify, GitHub Pages), set the API's URL there and add the site's origin to the API's `ALLOWED_ORIGINS`. To try another API without editing, add `?api=https://...` to the page URL.
