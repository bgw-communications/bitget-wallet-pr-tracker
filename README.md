# Bitget Wallet PR Monitor v4

This version mirrors the original Bitget PR Monitor information architecture, adapted for the wallet category.

## Included sections

- Brand SOV cards
- Share of Voice chart
- Summary table
- Bitget Wallet sentiment
- Recent coverage
- Interactive Narrative Ownership by brand
- Interactive Keyword Cloud by brand
- Competitor Intelligence
- Past 24h news and narrative pulse

## v4 changes

- Removed Journalist & Narrative Tracker and Unknown Author Articles.
- Added Past 24h News / Narrative Pulse for daily team monitoring.
- Competitor Intelligence now removes Suggested Response and uses a more insightful Verdict.
- Coinbase Wallet tracking now explicitly includes Base App / Base wallet terms.
- Narrative Ownership and Keyword Cloud include competitor comparison via interactive dropdowns.
- QTD tracking starts from 2026-04-01.
- Daily GitHub Actions update runs at 09:00 Singapore time / 01:00 UTC.

## Manual article QA

Use `manual_overrides.csv` to correct article classification:

```csv
URL,Correct Brand,Correct Narrative,Correct Sentiment,Correct Author,Correct Article Type,Include / Exclude,Notes
https://example.com/article,,,,,,exclude,Not wallet-related
```


## Workflow fix

This package includes an updated `.github/workflows/monitor.yml` that avoids non-fast-forward push failures by syncing with the latest `origin/main`, using native git commit / rebase / push, and preventing overlapping workflow runs.
