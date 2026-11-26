# How Inkwell's product evolved

One folder per version, oldest first. Each holds screenshots of that version's own pages, rebuilt from git history.

| Folder | Date | Commit | What changed |
|---|---|---|---|
| 01_stage-1-demo | Oct 3 | `9bc5983` | Stage 1 demo: one page, paste text, "Find clauses", answers beside the original policy. Includes the original screenshot from the repo |
| 02_web-app-three-models | Oct 6 | `a062133` | First web app (FastAPI): pick a reader (TF-IDF + SVM, DistilBERT, RoBERTa or all three), evidence stamps by category |
| 03_second-frontend-distilbert | Oct 6 | `43ee6b3` | Second frontend build around DistilBERT |
| 04_redesign-and-login | Oct 20 | `87a797a` | Redesigned UI; sign-in with Google, GitHub and email (Firebase) |
| 05_frontend-update-user-testing | Oct 20–27 | `c27b354` | Frontend changes for the first user testing session |
| 06_account-settings | Nov 3 | `c01fdfd` | Password change, email confirmation, email address change |
| 07_inkwell-1.1-report-card-dashboard | Nov 10 | `691c49e` | Inkwell 1.1: one five-topic model, new home page, privacy report card with the 8 key questions, steps, saved policies |
| 08_links-fixes-compare | Nov 14 | `6cb202c` | Check by link, dashboard, compare two policies |
| 09_extension-and-breather | Nov 16 | `9d66598` | Chrome extension (red/yellow/green card, fix tiers, request tracking, "don't sell" signal), welcome screens, ink line |
| 10_reviews-menus-guides | Nov 16 | `1cddaa7` | Reviews and ratings, Features and Resources menus, Guides page |
| 11_tour-exposure-fix-it | Nov 19 | `0d8cf77` | Guided tour, exposure score, Fix it buttons, plain-word explanations, edge-case checks |
| 12_3d-visuals | Nov 24 | `fe4e242` | 3D hero, inkwell checking screen and Done!, dashboard deck, compare as an open book, Guides redesign (teammate) |
| 13_now_orbit-map-and-flat-bar | Nov 25 | working copy | "Where your data goes" orbit map (site and extension), full-page checking, back to the flat exposure bar |

File names: `01_home`, `02_check_page`, `03_report` (after checking the sample policy), then the other pages that existed in that version, `99_phone_home`, and `extension_*` where the extension existed.

**How these were made.** Each version's own web files were served from git, so pages, layout and wording are exactly as they were. Their analysis calls went to today's local server, because the old three-model servers and weights are not available. So the numbers inside reports come from today's model, and early versions show "~NaN ms" for reader speed. Extension screenshots come from test runs made when those versions were built.
