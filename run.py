#!/usr/bin/env python3
"""
Bitget Wallet PR Monitor
- Fetches Google News RSS + selected crypto media RSS
- Classifies wallet brand, narrative, sentiment, article type
- Generates static JSON files for GitHub Pages dashboard
- No paid API or external Python package required

Generated files:
data/manifest.json
data/articles.json
data/metrics.json
data/journalists.json
"""

from __future__ import annotations

import csv
import datetime as dt
import email.utils
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ─── Basic setup ──────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bitget_wallet_pr_monitor")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DAYS_BACK = int(os.getenv("DAYS_BACK", "30"))
MAX_PER_FEED = int(os.getenv("MAX_PER_FEED", "35"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.5"))

USER_AGENT = (
    "Mozilla/5.0 (compatible; BitgetWalletPRMonitor/1.0; "
    "+https://github.com/bitgetpr)"
)

NOW = dt.datetime.now(dt.timezone.utc)
CUTOFF = NOW - dt.timedelta(days=DAYS_BACK)

# ─── Brand tracking ───────────────────────────────────────────────────────────

PRIMARY_BRAND = "Bitget Wallet"

BRANDS: Dict[str, Dict[str, Any]] = {
    "Bitget Wallet": {
        "include": [
            r"\bBitget Wallet\b",
            r"\bBitgetWallet\b",
            r"\bBitget Wallet Card\b",
            r"\bBitget Wallet Pay\b",
            r"\bBitget Wallet xStocks\b",
        ],
        "exclude": [
            r"\bBitget Exchange\b",
            r"\bBitget futures\b",
            r"\bBitget copy trading\b",
            r"\bBitget token\b",
            r"\bBGB\b",
            r"\bBitget CEO\b",
        ],
        "color": "#00f0b5",
    },
    "MetaMask": {
        "include": [
            r"\bMetaMask\b",
            r"\bMetaMask Wallet\b",
        ],
        "exclude": [],
        "color": "#f6851b",
    },
    "Trust Wallet": {
        "include": [
            r"\bTrust Wallet\b",
            r"\bTrustWallet\b",
        ],
        "exclude": [],
        "color": "#3375bb",
    },
    "Phantom Wallet": {
        "include": [
            r"\bPhantom Wallet\b",
            r"\bPhantom crypto wallet\b",
            r"\bPhantom Solana wallet\b",
            r"\bPhantom app\b",
        ],
        "exclude": [
            r"\bphantom stock\b",
            r"\bphantom pain\b",
            r"\bphantom power\b",
            r"\bPhantom of the Opera\b",
            r"\bRolls[- ]Royce Phantom\b",
        ],
        "color": "#ab9ff2",
    },
    "OKX Wallet": {
        "include": [
            r"\bOKX Wallet\b",
            r"\bOKX Web3 Wallet\b",
            r"\bOKXWallet\b",
        ],
        "exclude": [
            r"\bOKX exchange\b",
            r"\bOKX futures\b",
            r"\bOKX trading volume\b",
        ],
        "color": "#ffffff",
    },
    "Coinbase Wallet": {
        "include": [
            r"\bCoinbase Wallet\b",
            r"\bBase App\b",
            r"\bCoinbase wallet app\b",
            r"\bBase wallet\b",
        ],
        "exclude": [
            r"\bbase rate\b",
            r"\bbase layer\b",
            r"\bbase protocol\b",
            r"\bCoinbase exchange\b",
            r"\bCoinbase earnings\b",
            r"\bCoinbase stock\b",
        ],
        "color": "#0052ff",
    },
}

# Queries intentionally include narrative combinations to reduce generic noise.
GOOGLE_NEWS_QUERIES: Dict[str, List[str]] = {
    "Bitget Wallet": [
        '"Bitget Wallet"',
        '"Bitget Wallet Card"',
        '"Bitget Wallet" stablecoin',
        '"Bitget Wallet" "tokenized stocks"',
        '"Bitget Wallet" Polymarket',
        '"Bitget Wallet" "QR payments"',
    ],
    "MetaMask": [
        'MetaMask wallet',
        'MetaMask stablecoin payments',
        'MetaMask card',
        'MetaMask self-custody',
    ],
    "Trust Wallet": [
        '"Trust Wallet"',
        '"Trust Wallet" stablecoin',
        '"Trust Wallet" card',
        '"Trust Wallet" self-custody',
    ],
    "Phantom Wallet": [
        '"Phantom Wallet"',
        '"Phantom crypto wallet"',
        '"Phantom" "Solana wallet"',
    ],
    "OKX Wallet": [
        '"OKX Wallet"',
        '"OKX Web3 Wallet"',
        '"OKX Wallet" stablecoin',
    ],
    "Coinbase Wallet": [
        '"Coinbase Wallet"',
        '"Base App" Coinbase wallet',
        '"Base wallet" Coinbase',
    ],
}

# ─── Narrative taxonomy for Bitget Wallet PR ─────────────────────────────────

NARRATIVES: Dict[str, List[str]] = {
    "Stablecoin payments": [
        "stablecoin payment", "stablecoin payments", "usdt payment", "usdc payment",
        "pay with stablecoin", "stablecoin settlement", "payfi", "cross-border payment",
        "remittance", "onchain payment", "crypto payment",
    ],
    "Crypto card": [
        "crypto card", "wallet card", "debit card", "mastercard", "visa",
        "spend crypto", "card launch", "virtual card",
    ],
    "QR payments": [
        "qr payment", "qr code", "pos", "point-of-sale", "merchant qr",
        "scan to pay", "offline payment",
    ],
    "Self-custody": [
        "self-custody", "self custody", "non-custodial", "noncustodial",
        "seed phrase", "private key", "wallet ownership", "custody",
    ],
    "Wallet UX": [
        "wallet ux", "user experience", "mobile wallet", "onboarding",
        "simple", "ease of use", "interface", "passkey", "social login",
    ],
    "Onchain trading / swaps": [
        "swap", "dex", "trading", "perpetual", "perps", "memecoin",
        "onchain trading", "liquidity", "bridge", "cross-chain",
    ],
    "RWA / tokenized assets": [
        "rwa", "real-world asset", "real world asset", "tokenized stock",
        "tokenized stocks", "tokenized equity", "tokenized equities",
        "tokenized etf", "xstocks", "ondo",
    ],
    "Prediction markets": [
        "prediction market", "prediction markets", "polymarket",
        "event market", "sports market", "forecast market",
    ],
    "Security": [
        "security", "secure", "hack", "exploit", "phishing",
        "vulnerability", "breach", "audit", "scam", "stolen",
    ],
    "Regulation": [
        "regulation", "regulatory", "compliance", "sec", "cftc",
        "mica", "kyc", "aml", "license", "legal",
    ],
    "AI / agentic finance": [
        "ai", "artificial intelligence", "agentic", "agent", "autonomous",
        "x402", "wallet skill", "machine learning",
    ],
}

POSITIVE_WORDS = [
    "launch", "expand", "growth", "partner", "integrate", "milestone", "record",
    "support", "introduce", "enable", "raise", "approved", "adoption", "rollout",
    "collaborate", "secure", "improve", "upgrade", "new",
]
NEGATIVE_WORDS = [
    "hack", "exploit", "breach", "scam", "fraud", "lawsuit", "fine", "ban",
    "investigation", "outage", "stolen", "phishing", "risk", "vulnerability",
    "collapse", "illegal", "warning",
]
SEO_PATTERNS = [
    r"\bbest crypto wallet\b",
    r"\bbest wallet\b",
    r"\btop \d+ crypto wallets\b",
    r"\breview 20\d\d\b",
    r"\bcomparison\b",
    r"\balternatives\b",
    r"\bhow to choose\b",
]
TIER1_OUTLETS = {
    "Bloomberg", "Reuters", "CNBC", "Forbes", "Fortune", "Financial Times",
    "The Wall Street Journal", "TechCrunch", "CoinDesk", "The Block",
    "Blockworks", "Cointelegraph", "Decrypt", "DL News",
}

MEDIA_RSS_FEEDS = [
    {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed"},
    {"name": "Blockworks", "url": "https://blockworks.co/feed/"},
    {"name": "The Block", "url": "https://www.theblock.co/rss.xml"},
    {"name": "CryptoNews", "url": "https://cryptonews.com/news/feed/"},
    {"name": "Crypto Briefing", "url": "https://cryptobriefing.com/feed/"},
    {"name": "BeInCrypto", "url": "https://beincrypto.com/feed/"},
    {"name": "AMBCrypto", "url": "https://ambcrypto.com/feed/"},
    {"name": "U.Today", "url": "https://u.today/rss"},
    {"name": "NewsBTC", "url": "https://www.newsbtc.com/feed/"},
    {"name": "Protos", "url": "https://protos.com/feed/"},
]

# ─── Data structures ─────────────────────────────────────────────────────────

@dataclass
class Article:
    id: str
    date: str
    source: str
    headline: str
    url: str
    author: str
    snippet: str
    brands: List[str]
    primary_brand: str
    narrative: str
    sentiment: str
    article_type: str
    tier: str
    relevance_score: int
    bitget_wallet_mentioned: bool
    competitor_mentioned: str
    include: bool
    exclude_reason: str

# ─── HTTP / RSS helpers ──────────────────────────────────────────────────────

def fetch_url(url: str) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        log.warning("Fetch failed: %s — %s", url, exc)
        return None

def text_of(elem: Optional[ET.Element], default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return html.unescape(elem.text).strip()

def parse_date(raw: str) -> str:
    if not raw:
        return NOW.isoformat()
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return NOW.isoformat()

def clean_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def canonical_url(url: str) -> str:
    url = html.unescape(url or "")
    if "news.google.com" in url and "url=" in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            url = qs["url"][0]
    return url

def google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en".format(
        urllib.parse.quote_plus(query)
    )

def parse_rss(raw: bytes, fallback_source: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log.warning("RSS parse error for %s: %s", fallback_source, exc)
        return items

    channel_title = fallback_source
    ch = root.find("channel")
    if ch is not None:
        channel_title = text_of(ch.find("title"), fallback_source)

    for item in root.findall(".//item")[:MAX_PER_FEED]:
        title = clean_text(text_of(item.find("title")))
        link = canonical_url(text_of(item.find("link")))
        desc = clean_text(text_of(item.find("description")))
        pub = parse_date(text_of(item.find("pubDate")))

        author = ""
        # RSS/Atom author variants
        for path in ["author", "{http://purl.org/dc/elements/1.1/}creator"]:
            author = clean_text(text_of(item.find(path)))
            if author:
                break

        source = fallback_source
        source_elem = item.find("source")
        if source_elem is not None and source_elem.text:
            source = clean_text(source_elem.text)

        if not title or not link:
            continue

        items.append({
            "date": pub,
            "source": source or channel_title,
            "headline": title,
            "url": link,
            "author": author,
            "snippet": desc,
        })
    return items

# ─── Classification helpers ──────────────────────────────────────────────────

def regex_any(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)

def match_brands(headline: str, snippet: str, source: str) -> Tuple[List[str], str, bool, str]:
    text = f"{headline} {snippet}"
    matched: List[str] = []
    exclude_reason = ""

    for brand, cfg in BRANDS.items():
        inc = regex_any(cfg["include"], text)
        exc = regex_any(cfg["exclude"], text)
        if inc and not exc:
            matched.append(brand)
        elif inc and exc:
            exclude_reason = f"Excluded by {brand} exclusion rule"

    if not matched:
        return [], "", False, exclude_reason or "No tracked wallet brand matched"

    # Prefer Bitget Wallet if present; otherwise first brand.
    primary = PRIMARY_BRAND if PRIMARY_BRAND in matched else matched[0]
    competitor = ", ".join([b for b in matched if b != PRIMARY_BRAND])
    return matched, primary, PRIMARY_BRAND in matched, competitor

def classify_narrative(headline: str, snippet: str) -> str:
    text = f"{headline} {snippet}".lower()
    scores = {}
    for narrative, kws in NARRATIVES.items():
        score = sum(1 for kw in kws if kw.lower() in text)
        if score:
            scores[narrative] = score
    if not scores:
        return "General wallet coverage"
    return max(scores.items(), key=lambda x: x[1])[0]

def classify_sentiment(headline: str, snippet: str) -> str:
    text = f"{headline} {snippet}".lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    if pos > neg:
        return "Positive"
    if neg > pos:
        return "Negative"
    return "Neutral"

def classify_article_type(headline: str, snippet: str, source: str) -> str:
    text = f"{headline} {snippet}".lower()
    if regex_any(SEO_PATTERNS, text):
        return "SEO / comparison"
    if any(w in text for w in ["press release", "globenewswire", "pr newswire", "newsfile"]):
        return "Press release pickup"
    if any(w in text for w in ["op-ed", "opinion", "commentary"]):
        return "Opinion / commentary"
    if any(w in text for w in ["interview", "q&a", "exclusive"]):
        return "Interview / feature"
    if any(w in text for w in ["market", "price", "rally", "trader", "trading volume"]):
        return "Market commentary"
    return "Original / news"

def outlet_tier(source: str) -> str:
    normalized = source.strip()
    for outlet in TIER1_OUTLETS:
        if outlet.lower() in normalized.lower():
            return "Tier 1"
    return "Crypto / other"

def relevance_score(article_type: str, tier: str, narrative: str, bitget: bool, competitor: str) -> int:
    score = 2
    if tier == "Tier 1":
        score += 2
    if narrative != "General wallet coverage":
        score += 2
    if bitget:
        score += 2
    if competitor:
        score += 1
    if article_type in ["Interview / feature", "Opinion / commentary", "Original / news"]:
        score += 1
    if article_type == "SEO / comparison":
        score -= 2
    return max(1, min(score, 10))

def article_id(url: str, headline: str) -> str:
    base = (url or headline).strip().lower()
    return re.sub(r"[^a-zA-Z0-9]+", "", str(abs(hash(base))))[:16]

def is_recent(iso_date: str) -> bool:
    try:
        d = dt.datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d >= CUTOFF
    except Exception:
        return True

def is_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.88

def dedupe(raw_items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen_urls = set()
    kept: List[Dict[str, str]] = []
    for item in raw_items:
        url = item["url"].split("?")[0]
        title = item["headline"]
        if url in seen_urls:
            continue
        if any(is_similar(title, k["headline"]) for k in kept[-200:]):
            continue
        seen_urls.add(url)
        kept.append(item)
    return kept

# ─── Manual overrides ────────────────────────────────────────────────────────

def load_manual_overrides() -> Dict[str, Dict[str, str]]:
    path = ROOT / "manual_overrides.csv"
    if not path.exists():
        return {}

    overrides: Dict[str, Dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = (row.get("URL") or "").strip()
            if url:
                overrides[url] = row
    return overrides

def apply_override(article: Article, override: Dict[str, str]) -> Article:
    if not override:
        return article

    decision = (override.get("Include / Exclude") or "").strip().lower()
    if decision == "exclude":
        article.include = False
        article.exclude_reason = override.get("Notes") or "Manual exclusion"
    elif decision == "include":
        article.include = True
        article.exclude_reason = ""

    mapping = {
        "Correct Brand": "primary_brand",
        "Correct Narrative": "narrative",
        "Correct Sentiment": "sentiment",
        "Correct Author": "author",
        "Correct Article Type": "article_type",
    }
    for col, attr in mapping.items():
        val = (override.get(col) or "").strip()
        if val:
            setattr(article, attr, val)

    return article

# ─── Collection ───────────────────────────────────────────────────────────────

def collect_items() -> List[Dict[str, str]]:
    raw_items: List[Dict[str, str]] = []

    # Google News brand/narrative queries
    for brand, queries in GOOGLE_NEWS_QUERIES.items():
        for q in queries:
            url = google_news_url(q)
            log.info("Fetching Google News: %s", q)
            raw = fetch_url(url)
            if raw:
                raw_items.extend(parse_rss(raw, "Google News"))
            time.sleep(REQUEST_DELAY)

    # Crypto media RSS
    for feed in MEDIA_RSS_FEEDS:
        log.info("Fetching RSS: %s", feed["name"])
        raw = fetch_url(feed["url"])
        if raw:
            raw_items.extend(parse_rss(raw, feed["name"]))
        time.sleep(REQUEST_DELAY)

    return dedupe([x for x in raw_items if is_recent(x.get("date", ""))])

def classify_items(items: List[Dict[str, str]]) -> List[Article]:
    overrides = load_manual_overrides()
    out: List[Article] = []

    for item in items:
        brands, primary, bitget, competitor = match_brands(
            item["headline"], item.get("snippet", ""), item.get("source", "")
        )

        include = bool(brands)
        exclude_reason = "" if include else "No tracked wallet brand matched"

        narrative = classify_narrative(item["headline"], item.get("snippet", ""))
        sentiment = classify_sentiment(item["headline"], item.get("snippet", ""))
        a_type = classify_article_type(item["headline"], item.get("snippet", ""), item.get("source", ""))
        tier = outlet_tier(item.get("source", ""))
        score = relevance_score(a_type, tier, narrative, bitget, competitor)

        if a_type == "SEO / comparison" and tier != "Tier 1":
            include = False
            exclude_reason = "Filtered low-value SEO/comparison article"

        art = Article(
            id=article_id(item["url"], item["headline"]),
            date=item["date"],
            source=item.get("source", ""),
            headline=item["headline"],
            url=item["url"],
            author=item.get("author", "") or "Unknown author",
            snippet=item.get("snippet", ""),
            brands=brands,
            primary_brand=primary or "",
            narrative=narrative,
            sentiment=sentiment,
            article_type=a_type,
            tier=tier,
            relevance_score=score,
            bitget_wallet_mentioned=bitget,
            competitor_mentioned=competitor,
            include=include,
            exclude_reason=exclude_reason,
        )

        art = apply_override(art, overrides.get(art.url, {}))
        if art.include:
            out.append(art)

    out.sort(key=lambda x: x.date, reverse=True)
    return out

# ─── Metrics / journalist intelligence ───────────────────────────────────────

def pitch_angle(narrative: str, brand: str) -> str:
    if narrative == "Stablecoin payments":
        return "Offer data/commentary on the gap between stablecoin volume and everyday payment use."
    if narrative == "Crypto card":
        return "Pitch self-custodial crypto card usage, zero-fee positioning, and real-world spend data."
    if narrative == "QR payments":
        return "Pitch APAC QR payment adoption and wallet-based stablecoin spending use cases."
    if narrative == "RWA / tokenized assets":
        return "Pitch tokenized stocks/RWAs as the next asset-access layer inside wallets."
    if narrative == "Prediction markets":
        return "Pitch prediction markets moving from niche venues into mobile wallet distribution."
    if narrative == "Self-custody":
        return "Pitch how self-custody is evolving into usable everyday finance infrastructure."
    if narrative == "Security":
        return "Offer wallet security data, user-risk taxonomy, or expert commentary."
    return "Offer a Bitget Wallet perspective connected to wallet usability, distribution, and onchain finance."

def build_metrics(articles: List[Article]) -> Dict[str, Any]:
    brand_counts = Counter()
    sentiment_counts = Counter()
    narrative_counts = Counter()
    tier_counts = Counter()
    article_type_counts = Counter()

    for a in articles:
        if a.primary_brand:
            brand_counts[a.primary_brand] += 1
        for b in a.brands:
            if b != a.primary_brand:
                brand_counts[b] += 1
        sentiment_counts[a.sentiment] += 1
        narrative_counts[a.narrative] += 1
        tier_counts[a.tier] += 1
        article_type_counts[a.article_type] += 1

    total_mentions = sum(brand_counts.values()) or 1
    brand_metrics = []
    for brand in BRANDS.keys():
        count = brand_counts.get(brand, 0)
        brand_metrics.append({
            "brand": brand,
            "mentions": count,
            "sov": round(count / total_mentions * 100, 2),
            "color": BRANDS[brand]["color"],
        })

    return {
        "generated_at": NOW.isoformat(),
        "days_back": DAYS_BACK,
        "total_articles": len(articles),
        "total_mentions": total_mentions,
        "primary_brand": PRIMARY_BRAND,
        "brands": brand_metrics,
        "sentiment": dict(sentiment_counts),
        "narratives": dict(narrative_counts),
        "tiers": dict(tier_counts),
        "article_types": dict(article_type_counts),
        "top_sources": Counter(a.source for a in articles).most_common(15),
    }

def build_journalists(articles: List[Article]) -> Dict[str, Any]:
    named: Dict[Tuple[str, str], Dict[str, Any]] = {}
    unknown: List[Dict[str, Any]] = []

    for a in articles:
        if not a.author or a.author.lower() in {"unknown author", "staff", "admin"}:
            unknown.append({
                "outlet": a.source,
                "headline": a.headline,
                "url": a.url,
                "date": a.date,
                "narrative": a.narrative,
                "brand": a.primary_brand,
            })
            continue

        key = (a.author.strip(), a.source.strip())
        rec = named.setdefault(key, {
            "journalist": a.author.strip(),
            "outlet": a.source.strip(),
            "articles": 0,
            "recent_articles": [],
            "narratives": Counter(),
            "brands": Counter(),
            "bitget_wallet_covered": False,
            "tier1_articles": 0,
            "avg_relevance": 0,
            "_relevance_sum": 0,
        })

        rec["articles"] += 1
        rec["recent_articles"].append({
            "headline": a.headline,
            "url": a.url,
            "date": a.date,
            "narrative": a.narrative,
            "brand": a.primary_brand,
        })
        rec["narratives"][a.narrative] += 1
        rec["brands"][a.primary_brand] += 1
        rec["bitget_wallet_covered"] = rec["bitget_wallet_covered"] or a.bitget_wallet_mentioned
        rec["tier1_articles"] += 1 if a.tier == "Tier 1" else 0
        rec["_relevance_sum"] += a.relevance_score

    final_named: List[Dict[str, Any]] = []
    for rec in named.values():
        rec["avg_relevance"] = round(rec["_relevance_sum"] / max(1, rec["articles"]), 1)
        del rec["_relevance_sum"]

        top_narrative = rec["narratives"].most_common(1)[0][0] if rec["narratives"] else "General wallet coverage"
        top_brand = rec["brands"].most_common(1)[0][0] if rec["brands"] else ""

        score = 0
        score += min(3, rec["articles"])
        score += 2 if rec["tier1_articles"] else 0
        score += 2 if rec["bitget_wallet_covered"] else 0
        score += 2 if top_narrative != "General wallet coverage" else 0
        score += 1 if any(b != PRIMARY_BRAND for b in rec["brands"]) else 0
        score = max(1, min(10, score))

        rec["top_narrative"] = top_narrative
        rec["top_brand"] = top_brand
        rec["narratives"] = dict(rec["narratives"])
        rec["brands"] = dict(rec["brands"])
        rec["pitch_priority_score"] = score
        rec["suggested_pitch_angle"] = pitch_angle(top_narrative, top_brand)
        rec["recent_articles"] = rec["recent_articles"][:5]
        final_named.append(rec)

    final_named.sort(key=lambda r: (r["pitch_priority_score"], r["articles"]), reverse=True)

    return {
        "named": final_named,
        "unknown": unknown[:200],
        "summary": {
            "named_journalists": len(final_named),
            "unknown_author_articles": len(unknown),
            "high_priority_journalists": sum(1 for r in final_named if r["pitch_priority_score"] >= 7),
        },
    }

# ─── Output ──────────────────────────────────────────────────────────────────

def write_json(name: str, obj: Any) -> None:
    path = DATA_DIR / name
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s", path)

def main() -> None:
    log.info("Starting Bitget Wallet PR Monitor")
    raw = collect_items()
    log.info("Collected %d raw unique items", len(raw))

    articles = classify_items(raw)
    log.info("Kept %d included wallet-relevant articles", len(articles))

    metrics = build_metrics(articles)
    journalists = build_journalists(articles)

    article_dicts = [asdict(a) for a in articles]
    manifest = {
        "last_updated": NOW.isoformat(),
        "days_back": DAYS_BACK,
        "article_count": len(articles),
        "tracked_brands": list(BRANDS.keys()),
        "primary_brand": PRIMARY_BRAND,
        "generated_by": "run.py",
    }

    write_json("manifest.json", manifest)
    write_json("articles.json", article_dicts)
    write_json("metrics.json", metrics)
    write_json("journalists.json", journalists)

    log.info("Done")

if __name__ == "__main__":
    main()
