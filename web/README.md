# Inkwell web

Static frontend for the Inkwell API: plain HTML, CSS and JavaScript, with no build step and no dependencies.

## Features

- **Three readers:** pick TF-IDF + SVM, DistilBERT or RoBERTa-base, or run **All three** on the same text. Each card shows the model's test F1 and CPU cost, and whether the API has it loaded.
- **Stamps:** one stamp per category with its clause count. Categories with no matching paragraph get a red SILENT stamp.
- **Common questions:** the five FAQ questions, each answered with the exact paragraphs the model tagged.
- **Annotated policy:** every paragraph, colour-coded by category, with filters. Clicking a paragraph shows how close it came to each category's cutoff (score vs. threshold meters).
- **Compare readers:** a per-category count table, plus paragraph-by-paragraph label agreement with a "show only disagreements" toggle.
- **Exports:** a Markdown evidence report or the raw JSON.
- **Input helpers:** sample policy, .txt/.md upload, a size and paragraph counter, a warning for one-giant-paragraph text, a button to split single line breaks, and Ctrl+Enter to run.
- **API status lamp:** shows whether the API is up and polls while the Space wakes up or encoders load.

Policy text is only ever inserted as text, never as HTML.

## Run locally

The API serves this folder, so start it and open the API's address. On Windows, from the repository root, run `api\run_local.cmd` and open http://127.0.0.1:7860. Opening `index.html` as a file won't work: the page can't call the API from `file://`.

To work on the page with a separate static server, run `python -m http.server 5173 --directory web`. On port 5173 the page calls `http://127.0.0.1:7860`.

## Point it at another API

`config.js` defaults to the server that served the page. If you host this folder separately (Vercel, Netlify, GitHub Pages), set the API's URL there and add the site's origin to the API's `ALLOWED_ORIGINS`. To try another API without editing, add `?api=https://...` to the page URL.
