# Bitget Wallet PR Monitor

v2 updates:
- Competitor section moved before Journalist section.
- Recent Coverage table simplified: removed Author, Score, Sentiment, and News Type columns.
- QTD tracking starts from `2026-04-01`.
- Daily GitHub Actions update runs at 09:00 Singapore time / 01:00 UTC.
- Broader competitor query coverage to reduce inflated Bitget Wallet SOV.
- Best-effort byline extraction from article pages.
- Added `manual_authors.csv` for manually adding journalist names.
- Narrative table replaced with keyword cloud.

## Journalist tracking

RSS feeds often do not include journalist bylines. This version tries to fetch article pages and extract bylines from metadata, but some outlets block scraping or omit author metadata.

For reliable journalist tracking, manually add key bylines to `manual_authors.csv`:

```csv
URL,Author,Outlet,Notes
https://example.com/article,Jane Doe,CoinDesk,Manual byline check
```

Then run the workflow again.

## Manual article QA

Use `manual_overrides.csv` to correct article classification:

```csv
URL,Correct Brand,Correct Narrative,Correct Sentiment,Correct Author,Correct Article Type,Include / Exclude,Notes
https://example.com/article,,,,,,exclude,Not wallet-related
```


## v3 updates

- Restores the original Bitget PR Monitor information architecture for the wallet category:
  - brand SOV cards
  - SOV chart and table
  - summary table
  - Bitget Wallet sentiment table
  - recent coverage
  - narrative chart and keyword cloud
  - competitor intelligence cards
  - journalist tracker
- Adds auto-generated competitor intelligence with:
  - threat level
  - mentions
  - top narrative
  - latest articles
  - verdict
  - suggested response
- Keeps QTD tracking from 2026-04-01 and daily 09:00 Singapore time updates.
