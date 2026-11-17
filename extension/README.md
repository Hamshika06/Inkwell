# Inkwell for Chrome

A toolbar button that checks a site's privacy policy before you agree, and shows the quickest way to limit each thing.
It does nothing until you click it, and reads the policy only when you press **Check policy**.

## What it does

1. **Click the Inkwell icon** on any site. The first time, it asks you to sign up or sign in with Inkwell. It opens
   Inkwell's sign-in page (`connect.html`), then closes that tab and brings you back.
2. **Quick wins on sign-up pages.** It outlines the email field (use a hidden email), optional fields (leave them empty)
   and pre-ticked marketing boxes (untick them). If the site already has your location, **Block location** turns that off.
3. **Check policy.** The policy link found on the page is read by the Inkwell server (`/fetch-policy`, then `/report`).
4. **The card.** Each answer is red (worth knowing), yellow (not clearly answered) or green (in your favour). The colours
   describe answers, not the company, and there's no overall score. Each red line says how long it takes to limit:

   | Label | What the button does |
   |---|---|
   | ⚡ **Fix now** | Turns on "don't sell or share my data" (Global Privacy Control), or blocks location for the site |
   | ⚙ **In settings · ~2 min** | Opens the site's own settings page: from our hand-checked list, a link on the policy page, or the ad-industry opt-out |
   | ✉ **Request · up to 45 days** (1 month in the EU/UK) | Opens a pre-written email in your email app; Inkwell tracks the deadline |
   | — **Comes with the service** | Nothing to switch off; the choice is whether to use it |

5. **See the full report on Inkwell** opens `app.html?url=…`, which checks the policy on the website.
6. **My requests** (`requests.html`) lists every request and its deadline. It reminds you a week before the deadline and
   again when a company is late, and offers a pre-written reminder email.
7. **Rate Inkwell.** A strip under the card (and an item in Settings): tapping a star opens the review form on the
   Inkwell site (`reviews.html?write=1&stars=N&site=…`) with that rating filled in; halves can be picked there.

## Try it (unpacked)

1. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and pick this `extension` folder.
2. Pin Inkwell from the puzzle-piece menu.
3. It talks to the live server by default. To use a local server instead, open the popup's ⚙ settings, then
   **Advanced: Inkwell server**, and enter `http://127.0.0.1:7860`.

The live server needs this version deployed (it adds `connect.html`, `app.html?url=` and the `fixes` list in
`/fetch-policy`).

## Permissions, and why

| Permission | Why |
|---|---|
| `activeTab`, `scripting` | Read the current page for its policy link and sign-up form, only when you click the icon |
| `storage` | Your settings, your sign-in, your requests (this browser only) |
| `alarms`, `notifications` | Request reminders |
| `declarativeNetRequest` | Add the `Sec-GPC: 1` header when "don't sell or share" is on |
| Inkwell server and `securetoken.googleapis.com` | Call the Inkwell API, and keep your sign-in fresh |
| *Optional* `<all_urls>` | Asked only when you turn on "don't sell or share": the signal goes to every site |
| *Optional* `contentSettings` | Asked only when you press **Block location** |

The policy text is never stored. The card is kept for the browser session, so reopening the popup shows it again.

## Sign-in handoff

`connect.html` on the Inkwell site posts the Firebase refresh token to `bridge.js`. That's the extension's only script on
web pages, and it runs only on Inkwell's `connect.html`. The background worker exchanges the refresh token for short-lived
ID tokens at `securetoken.googleapis.com`. If your Firebase API key has HTTP-referrer restrictions in Google Cloud, add the
extension's origin (`chrome-extension://<id>/*`) to them.

## Publishing (Chrome Web Store)

- One-time $5 developer fee. Zip this folder; the store asks for screenshots and a privacy disclosure.
- Disclose: the policy link you check is sent to the Inkwell server; nothing is collected in the background.
- Before publishing, add a `key` to `manifest.json` (or use the store's ID) so the extension ID stays fixed.

## Files

`manifest.json` · `background.js` (sign-in, GPC, reminders) · `popup.html/.css/.js` (the popup) · `scan.js` (runs in the
page on click) · `bridge.js` (sign-in handoff on Inkwell's site) · `gpc.js` (`navigator.globalPrivacyControl`) ·
`requests.html/.css/.js` (My requests) · `common.js` (shared helpers and email templates)
