# Founder Pipeline

An evidence-aware fork of YC Outreach for finding small B2B teams with a plausible paid product-area role or scoped project. Standard library only, Python 3.9+, no API key and no build step.

The default screen targets teams of 1–5 in YC batches from 2025–2026. Directory keywords identify research candidates; they do not establish hiring demand, Pakistan eligibility, budget or missing features. Unknowns stay explicit. Direct receivables companies are held for competition/IP clearance. The effort target is 70% employment and 30% scoped projects.

## Run

```sh
python3 serve.py
# Open http://localhost:8765
```

Screen a batch, review survivors, load founder profiles selectively, and copy a company-specific research prompt. Complete the research card using current original sources, then save it to calculate separate employment and project decisions. The workspace is saved in the browser; export it for backup. Card evaluation uses a stateless endpoint and does not save cards on the server. The app never sends outreach.

## Bulk discovery

```sh
# All YC batches in the configured 2025–2026 window; no founder/contact crawl yet
python3 pipeline.py screen --out data/pipeline --packets 25

# Specific batches
python3 pipeline.py screen --batches "Summer 2026" "Fall 2026" --out data/pipeline

# Other ecosystems or existing yc_scraper.py output
python3 pipeline.py screen --input companies.json --out data/imported

# Optional private profile: override team/year window, positioning and permitted proof context
python3 pipeline.py screen --profile your.private.json --out data/pipeline

# Skip companies already present in your operating tracker
python3 pipeline.py screen --input companies.json --known existing.private.json --out data/pipeline

# Validate completed cards exported from a researcher
python3 pipeline.py evaluate --input research-cards.json --out data/evaluated.json
```

A screen writes all deduplicated company records, `companies.csv`, `summary.json`, blank cards, and individual research prompts. It preserves rejections and holds. `--known` accepts an array of canonical IDs or company names and skips those companies when generating fresh research packets. Import `companies.json` or completed `cards.json` into the browser. Raw non-YC inputs must be arrays of objects with a name; include website, source, team_size, industry, description and a source URL when available. Missing team size or batch does not fabricate a pass or rejection.

Research prompts are handoffs for a human or research-capable agent. This version does **not** independently perform deep web research, verify source contents, discover all non-YC ecosystems, or prove that a current role accepts Pakistan. No LLM service is required. Fill cards from original current pages; review interpretations before drafting. Existing spreadsheet trackers can ingest the CSV, but this release does not modify them automatically.

## Qualification rules

The engine implements the Acquisition Toolkit's 13-factor, 100-point scoring model, with distinct employment E and project P scores and neutral base B. Route gates are independent: geography, budget, need, authority, timing, depth, reviewer and IP. A blocked role never automatically qualifies a project.

Evidence requires a claim, original HTTP(S) URL and check date. Gate evidence older than 30 days becomes unknown; rating evidence older than 90 days defaults to 1. These are metadata checks, **not factual source verification**. Source event and publication dates can be recorded separately. A funding announcement does not prove salary budget; remote or EMEA does not establish Pakistan eligibility.

Unknown budget or geography caps priority at 59, both unknown at 49, and unconfirmed need at 54. Hard blockers override scores. Penalties apply once each. Unresolved gates stay at L1. No score automatically authorizes a custom implementation or predicts a close.

Drafts are typed per company. Copy unlocks only with a complete card, verified contact evidence, live-source recheck within 48 hours, explicit claim review and a body of at most 140 words. Qualification drafts may ask about unresolved gates; they must not present unknown conditions as confirmed. There is no automatic Sent state.

Private strategy docs, compensation floors, employer records, references and proprietary artifacts do not belong in this public repository. `data/`, `private-context/`, `*.private.json` and research-card exports are ignored. Profiles should carry only the permitted context needed by your researcher. Review exports before sharing.

## API and deployment

`GET /api/yc?action=screen&batch=Summer%202026` screens fixed YC directory data before enrichment. `GET /api/yc?action=profiles&slugs=example` reads founder profiles from YC and omits guessed emails. Both accept the same strict batch/slug formats as upstream. Neither accepts arbitrary URLs. `POST /api/evaluate` validates one card (maximum 256 KB), does no network fetching, and returns an uncached decision. It works locally and as a Vercel Python function.

The original template interface remains at `legacy-outreach.html`; original scraper and optional Apify utilities remain available. They are separate from the qualification workflow and have their original guessed-email behavior. No paid enrichment is invoked by the new pipeline.

```sh
python3 -m unittest discover -s tests -v
```

CI runs the qualification and API tests on Python 3.9. MIT license; upstream documentation follows.

---

# YC Outreach

Pick any Y Combinator batch, get every company's founders and their likely email addresses, and write a personalised
cold email to each one from a single template. Free by default (no API keys, no sign-up); optional verified emails
with your own Apify token.

```
python3 serve.py        # open http://localhost:8765
```

Python 3.9+, standard library only. Nothing to install.

## What it does

1. **Pick a batch** (Summer 2005 through the latest) from YC's public directory.
2. **Founders load 20 companies at a time** (about 5–10 s per 20); click **Load more** for the next 20. For each
   company the server reads its ycombinator.com page for the founders' names, titles, LinkedIn and X. Loaded
   companies are kept in your browser, so reopening a batch is instant.
3. **Emails are filled in** for each founder, best source first:

   | Label | Source | Reliability |
   |---|---|---|
   | `verified` | Apify lookup with your token (optional) | Checked by Apify |
   | `unverified` | Apify lookup that couldn't confirm the mailbox | Usually right |
   | `on site` | Email published on the company's homepage or `/contact` page | Real address, may be generic |
   | `guess` | `first@domain`, then `first.last@`, `flast@`, `firstlast@` | First guess right ~80% of the time |

   The reliability figure comes from a check against 151 Apify-verified founder emails: the first guess matched 80%, and
   the right address was somewhere in the guess list 93% of the time.
4. **Write once, send many.** Fill in your name and links, edit the subject and body, and every draft updates live.
   Copy the text or open it in your mail app. Mark companies as sent to hide them.

Your details, template, "sent" marks and loaded batches are stored in your browser (`localStorage`). There's no
database and no account.

## Deploy

Import the repo on [Vercel](https://vercel.com/new). No build step, no environment variables. `index.html` is served
as a static page and `api/yc.py` runs as a Python serverless function (`vercel.json` gives it 60 s).

## Project layout

| File | Role |
|---|---|
| `index.html` | The whole UI: one HTML file with inline CSS and JS, no framework, no build. |
| `api/yc.py` | Serverless function (Vercel Python runtime, `handler` class). YC search + founder pages. |
| `serve.py` | Local dev server: serves `index.html` and routes `/api/yc` to the same handler. |
| `vercel.json` | Function timeout. |
| `yc_scraper.py` | CLI: scrape whole batches to JSON/CSV. |
| `apify_enrich.py` | CLI: add Apify-found emails to the scraper's output. |

## HTTP API

All endpoints are `GET` and return JSON. Errors return `{"error": "..."}` with status 400 (bad input) or 502 (YC
unreachable).

### `/api/yc?action=batches`

```json
[{"batch": "Fall 2026", "count": 110}, {"batch": "Summer 2026", "count": 231}]
```

Newest first. Includes `"Unspecified"`, which the UI hides.

### `/api/yc?action=companies&batch=Winter%202024`

```json
[{"name": "Indemni", "slug": "indemni", "batch": "Winter 2024", "website": "http://www.indemni.com",
  "one_liner": "Cargo Theft and Fraud Prevention Platform", "industry": "B2B -> Supply Chain and Logistics",
  "team_size": 7, "launched_at": 1708029636}]
```

`batch` must look like `Winter 2024` (season + year).

### `/api/yc?action=founders&slugs=indemni,parcelbio`

At most 10 slugs per call (`^[a-z0-9-]+$`). The UI loads 20 companies per click as two parallel calls. About
5–9 s per call; each company's website check is cut off after 4 s (`SITE_DEADLINE`) so one slow site can't stall
the batch.

```json
[{"slug": "indemni", "website": "http://www.indemni.com", "domain": "indemni.com",
  "linkedin": "https://www.linkedin.com/company/...", "twitter": "", "site_emails": [],
  "founders": [{"name": "Omar Draz", "title": "Founder", "linkedin": "https://linkedin.com/in/odraz",
                "twitter": "https://twitter.com/oamdraz", "emails_found": [],
                "email_guesses": ["omar@indemni.com", "omar.draz@indemni.com", "odraz@indemni.com", "omardraz@indemni.com"]}]}]
```

A company whose YC page fails to load comes back as `{"slug": "...", "error": "..."}`. Guesses are empty when the
domain doesn't resolve.

## Where the data comes from

- **Batches and companies:** YC's public company search (Algolia). The read-only search key is read from
  `ycombinator.com/companies` at runtime, so no key is stored here.
- **Founders:** the `data-page` JSON embedded in each `ycombinator.com/companies/<slug>` page. Browsers can't fetch
  these cross-origin, which is why this part runs on a server.
- **Verified emails (optional):** the Apify actor
  [`snipercoder/email-finder-by-name-and-domain`](https://apify.com/snipercoder/email-finder-by-name-and-domain),
  called **from the browser** with the visitor's own token, so the token never reaches the server. Results are
  matched on the `Name` and `Domain` fields of each dataset item. Each run covers up to 50 founders and is capped
  with `maxTotalChargeUsd`.

## Command line

For bulk exports. Output files are gitignored.

```
python3 yc_scraper.py --batches "Winter 2024" "Summer 2024" --out yc_founders   # -> yc_founders.json + .csv
python3 apify_enrich.py --input yc_founders.json --out yc_founders_enriched      # needs APIFY_TOKEN
```

`yc_scraper.py` flags: `--batches` (default `"Summer 2026" "Fall 2026"`), `--out`, `--workers` (default 12),
`--limit` (first N companies, for testing). It checks six contact pages per site and retries, so it's slower but
more thorough than the web API.

`apify_enrich.py` reads `APIFY_TOKEN` from the environment or a `.env` file (gitignored). Flags: `--input`, `--out`,
`--limit`, `--chunk` (founders per run, default 50), `--max-charge` (USD cap per run, default 1).

## Notes for AI agents and contributors

- Standard library only, on purpose. Don't add dependencies or a build step.
- `api/yc.py` and `yc_scraper.py` share logic but are separate on purpose: the function has to finish inside a
  serverless timeout, so it makes one attempt per fetch, checks 2 pages, and gives up on a website after 4 s;
  the CLI retries and checks 6.
- The function only accepts a batch name or slugs. Websites always come from YC's data, never from the request, so
  it can't be used to fetch arbitrary URLs. Keep it that way.
- Everything from YC is untrusted text. `index.html` escapes it (`esc()`) and only links `http(s)` URLs (`url()`).
- To test locally: `python3 serve.py`, then
  `curl 'localhost:8765/api/yc?action=founders&slugs=reddit'`.

## Be decent

Write to people one at a time, keep it short, and take "no" for an answer.

## License

MIT
