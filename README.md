# Bitget Wallet PR Monitor

A lightweight GitHub Pages dashboard for tracking Bitget Wallet and wallet competitors across media coverage, share of voice, narratives, sentiment, and journalist opportunities.

## Tracked brands

- Bitget Wallet
- MetaMask
- Trust Wallet
- Phantom Wallet
- OKX Wallet
- Coinbase Wallet / Base App

## Dashboard sections

1. Overview KPIs
2. Wallet Share of Voice
3. Recent coverage
4. Narrative ownership
5. Journalist & Narrative Tracker
6. Competitor coverage map

## Files

```text
run.py
index.html
manual_overrides.csv
.github/workflows/monitor.yml
data/
```

## Generated data files

`run.py` generates:

```text
data/manifest.json
data/articles.json
data/metrics.json
data/journalists.json
```

## How to run locally

```bash
python run.py
```

Then open `index.html` in a local server, or push the repo to GitHub Pages.

## Manual QA

Use `manual_overrides.csv` to correct article classification without changing code.

Supported override columns:

```text
URL
Correct Brand
Correct Narrative
Correct Sentiment
Correct Author
Correct Article Type
Include / Exclude
Notes
```

For `Include / Exclude`, use either:

```text
include
exclude
```

## GitHub Pages setup

1. Upload all files to your GitHub repository.
2. Go to **Settings → Pages**.
3. Under **Build and deployment**, choose:
   - Source: Deploy from a branch
   - Branch: main
   - Folder: /root
4. Save.
5. Go to **Actions → Update PR Monitor → Run workflow**.
6. After the workflow succeeds, open your GitHub Pages URL.

## Data quality notes

This is an MVP. Before using for executive reporting:

- Check whether Bitget Wallet mentions are mixed with Bitget Exchange mentions.
- Check whether Base App / Coinbase Wallet data includes generic Base chain coverage.
- Check whether Phantom Wallet data includes non-crypto “phantom” mentions.
- Review SEO/comparison articles and exclude low-value results if needed.
- Manually check bylines for high-value “Unknown author” articles.
