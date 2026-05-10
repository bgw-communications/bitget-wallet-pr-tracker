#!/usr/bin/env python3
from __future__ import annotations

import csv, datetime as dt, email.utils, html, json, logging, os, re, time
import urllib.error, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bitget_wallet_pr_monitor")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

QTD_START = os.getenv("QTD_START", "2026-04-01")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "18"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.35"))
MAX_PER_FEED = int(os.getenv("MAX_PER_FEED", "80"))
FETCH_BYLINES = os.getenv("FETCH_BYLINES", "1") != "0"
MAX_BYLINE_FETCHES = int(os.getenv("MAX_BYLINE_FETCHES", "120"))

USER_AGENT = "Mozilla/5.0 (compatible; BitgetWalletPRMonitor/2.0)"
NOW = dt.datetime.now(dt.timezone.utc)
QTD_START_DT = dt.datetime.fromisoformat(QTD_START).replace(tzinfo=dt.timezone.utc)
PRIMARY_BRAND = "Bitget Wallet"

BRANDS: Dict[str, Dict[str, Any]] = {
    "Bitget Wallet": {
        "include": [r"\bBitget Wallet\b", r"\bBitgetWallet\b", r"\bBitget Wallet Card\b", r"\bBitget Wallet Pay\b", r"\bBitget Wallet xStocks\b", r"\bBitget Wallet Skill\b"],
        "exclude": [r"\bBitget Exchange\b", r"\bBitget futures\b", r"\bBitget copy trading\b", r"\bBitget token\b", r"\bBitget CEO\b"],
        "color": "#00f0b5",
    },
    "MetaMask": {"include": [r"\bMetaMask\b", r"\bMetaMask Wallet\b", r"\bMetaMask Card\b", r"\bMetaMask.*wallet\b"], "exclude": [], "color": "#f6851b"},
    "Trust Wallet": {"include": [r"\bTrust Wallet\b", r"\bTrustWallet\b", r"\bTrust Wallet.*AI\b", r"\bTrust Wallet.*card\b"], "exclude": [], "color": "#3375bb"},
    "Phantom Wallet": {
        "include": [r"\bPhantom Wallet\b", r"\bPhantom crypto wallet\b", r"\bPhantom Solana wallet\b", r"\bPhantom.*wallet\b", r"\bPhantom.*Solana\b"],
        "exclude": [r"\bphantom stock\b", r"\bphantom pain\b", r"\bphantom power\b", r"\bPhantom of the Opera\b", r"\bRolls[- ]Royce Phantom\b"],
        "color": "#ab9ff2",
    },
    "OKX Wallet": {"include": [r"\bOKX Wallet\b", r"\bOKX Web3 Wallet\b", r"\bOKXWallet\b"], "exclude": [r"\bOKX exchange\b", r"\bOKX futures\b"], "color": "#ffffff"},
    "Coinbase Wallet": {"include": [r"\bCoinbase Wallet\b", r"\bCoinbase Smart Wallet\b", r"\bBase App\b", r"\bCoinbase wallet app\b", r"\bBase wallet\b"], "exclude": [r"\bbase rate\b", r"\bbase layer\b", r"\bCoinbase exchange\b", r"\bCoinbase earnings\b", r"\bCoinbase stock\b"], "color": "#0052ff"},
}

GOOGLE_NEWS_QUERIES = {
    "Bitget Wallet": [f'"Bitget Wallet" after:{QTD_START}', f'"Bitget Wallet Card" after:{QTD_START}', f'"Bitget Wallet" stablecoin after:{QTD_START}', f'"Bitget Wallet" payment after:{QTD_START}', f'"Bitget Wallet" QR after:{QTD_START}', f'"Bitget Wallet" Polymarket after:{QTD_START}', f'"Bitget Wallet" Stellar after:{QTD_START}', f'"Bitget Wallet" "tokenized stocks" after:{QTD_START}', f'"Bitget Wallet" xStocks after:{QTD_START}'],
    "MetaMask": [f'MetaMask wallet after:{QTD_START}', f'"MetaMask Card" after:{QTD_START}', f'MetaMask stablecoin after:{QTD_START}', f'MetaMask payments after:{QTD_START}', f'MetaMask self-custody after:{QTD_START}', f'MetaMask snaps wallet after:{QTD_START}'],
    "Trust Wallet": [f'"Trust Wallet" after:{QTD_START}', f'"Trust Wallet" AI wallet after:{QTD_START}', f'"Trust Wallet" stablecoin after:{QTD_START}', f'"Trust Wallet" card after:{QTD_START}', f'"Trust Wallet" self-custody after:{QTD_START}'],
    "Phantom Wallet": [f'"Phantom Wallet" after:{QTD_START}', f'"Phantom" "crypto wallet" after:{QTD_START}', f'"Phantom" "Solana wallet" after:{QTD_START}', f'"Phantom wallet" "Sui" after:{QTD_START}', f'"Phantom wallet" "Bitcoin" after:{QTD_START}'],
    "OKX Wallet": [f'"OKX Wallet" after:{QTD_START}', f'"OKX Web3 Wallet" after:{QTD_START}', f'"OKX Wallet" DEX after:{QTD_START}', f'"OKX Wallet" stablecoin after:{QTD_START}', f'"OKX Wallet" self-custody after:{QTD_START}'],
    "Coinbase Wallet": [f'"Coinbase Wallet" after:{QTD_START}', f'"Coinbase Smart Wallet" after:{QTD_START}', f'"Base App" Coinbase after:{QTD_START}', f'"Base wallet" Coinbase after:{QTD_START}', f'"Coinbase Wallet" stablecoin after:{QTD_START}', f'"Coinbase Wallet" self-custody after:{QTD_START}'],
}

NARRATIVES = {
    "Stablecoin payments": ["stablecoin payment", "stablecoin payments", "usdt payment", "usdc payment", "stablecoin settlement", "payfi", "cross-border payment", "remittance", "onchain payment", "crypto payment"],
    "Crypto card": ["crypto card", "wallet card", "debit card", "mastercard", "visa", "spend crypto", "card launch", "virtual card", "cashback"],
    "QR payments": ["qr payment", "qr code", "pos", "point-of-sale", "merchant qr", "scan to pay", "offline payment"],
    "Self-custody": ["self-custody", "self custody", "non-custodial", "noncustodial", "seed phrase", "private key", "wallet ownership"],
    "Wallet UX": ["wallet ux", "user experience", "mobile wallet", "onboarding", "simple", "ease of use", "interface", "passkey", "social login"],
    "Onchain trading / swaps": ["swap", "dex", "trading", "perpetual", "perps", "memecoin", "onchain trading", "liquidity", "bridge", "cross-chain", "gasless"],
    "RWA / tokenized assets": ["rwa", "real-world asset", "real world asset", "tokenized stock", "tokenized stocks", "tokenized equity", "tokenized etf", "xstocks", "ondo", "treasuries"],
    "Prediction markets": ["prediction market", "prediction markets", "polymarket", "event market", "sports market", "forecast market"],
    "Security": ["security", "secure", "hack", "exploit", "phishing", "vulnerability", "breach", "audit", "scam", "stolen"],
    "Regulation": ["regulation", "regulatory", "compliance", "sec", "cftc", "mica", "kyc", "aml", "license", "legal"],
    "AI / agentic finance": ["ai", "artificial intelligence", "agentic", "agent", "autonomous", "x402", "wallet skill", "machine learning"],
}
KEYWORD_STOPWORDS = {"crypto","wallet","wallets","bitget","metamask","trust","phantom","okx","coinbase","base","news","says","new","launch","launches","after","from","with","that","this","and","the","for","are","being","will","into","about","amid","latest","guide","review","price","market","markets","million","billion","users"}
POSITIVE_WORDS = ["launch","expand","growth","partner","integrate","milestone","record","support","introduce","enable","raise","approved","adoption","rollout","collaborate","secure","improve","upgrade","new","wins"]
NEGATIVE_WORDS = ["hack","exploit","breach","scam","fraud","lawsuit","fine","ban","investigation","outage","stolen","phishing","risk","vulnerability","collapse","illegal","warning"]
SEO_PATTERNS = [r"\bbest crypto wallet\b", r"\bbest wallet\b", r"\btop \d+ crypto wallets\b", r"\breview 20\d\d\b", r"\bcomparison\b", r"\balternatives\b"]
TIER1_OUTLETS = {"Bloomberg","Reuters","CNBC","Forbes","Fortune","Financial Times","The Wall Street Journal","TechCrunch","CoinDesk","The Block","Blockworks","Cointelegraph","Decrypt","DL News"}
MEDIA_RSS_FEEDS = [{"name":"CoinTelegraph","url":"https://cointelegraph.com/rss"},{"name":"CoinDesk","url":"https://www.coindesk.com/arc/outboundfeeds/rss/"},{"name":"Decrypt","url":"https://decrypt.co/feed"},{"name":"Blockworks","url":"https://blockworks.co/feed/"},{"name":"The Block","url":"https://www.theblock.co/rss.xml"},{"name":"CryptoNews","url":"https://cryptonews.com/news/feed/"},{"name":"Crypto Briefing","url":"https://cryptobriefing.com/feed/"},{"name":"BeInCrypto","url":"https://beincrypto.com/feed/"},{"name":"AMBCrypto","url":"https://ambcrypto.com/feed/"},{"name":"U.Today","url":"https://u.today/rss"},{"name":"NewsBTC","url":"https://www.newsbtc.com/feed/"},{"name":"Protos","url":"https://protos.com/feed/"}]

@dataclass
class Article:
    id: str; date: str; source: str; headline: str; url: str; author: str; snippet: str
    brands: List[str]; primary_brand: str; narrative: str; sentiment: str; article_type: str
    tier: str; relevance_score: int; bitget_wallet_mentioned: bool; competitor_mentioned: str
    include: bool; exclude_reason: str

def fetch_url(url: str) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:
        log.warning("Fetch failed: %s — %s", url, exc); return None

def text_of(elem, default=""):
    return html.unescape(elem.text).strip() if elem is not None and elem.text else default

def parse_date(raw: str) -> str:
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return NOW.isoformat()

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()

def canonical_url(url: str) -> str:
    url = html.unescape(url or "")
    if "news.google.com" in url and "url=" in url:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if qs.get("url"): url = qs["url"][0]
    return url

def google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en".format(urllib.parse.quote_plus(query))

def normalize_author(author: str) -> str:
    author = clean_text(author)
    author = re.sub(r"^by\s+", "", author, flags=re.I)
    author = re.sub(r"\s+[-|].*$", "", author).strip()
    if len(author) > 80 or author.lower() in {"staff","admin","editor","news desk","press release","guest author"}:
        return ""
    return author

def parse_rss(raw: bytes, fallback_source: str) -> List[Dict[str,str]]:
    items = []
    try: root = ET.fromstring(raw)
    except ET.ParseError: return items
    for item in root.findall(".//item")[:MAX_PER_FEED]:
        title = clean_text(text_of(item.find("title")))
        link = canonical_url(text_of(item.find("link")))
        desc = clean_text(text_of(item.find("description")))
        pub = parse_date(text_of(item.find("pubDate")))
        author = ""
        for path in ["author", "{http://purl.org/dc/elements/1.1/}creator"]:
            author = normalize_author(text_of(item.find(path)))
            if author: break
        source = fallback_source
        source_elem = item.find("source")
        if source_elem is not None and source_elem.text: source = clean_text(source_elem.text)
        if title and link: items.append({"date":pub,"source":source,"headline":title,"url":link,"author":author,"snippet":desc})
    return items

def extract_meta_author(page: str) -> str:
    patterns = [
        r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']article:author["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']parsely-author["\'][^>]+content=["\']([^"\']+)["\']',
        r'"author"\s*:\s*{\s*"@type"\s*:\s*"Person"\s*,\s*"name"\s*:\s*"([^"]+)"',
        r'"author"\s*:\s*"([^"]+)"',
        r'class=["\'][^"\']*author[^"\']*["\'][^>]*>\s*(?:By\s*)?([^<]+)<',
    ]
    for p in patterns:
        m = re.search(p, page, flags=re.I|re.S)
        if m:
            a = normalize_author(html.unescape(m.group(1)))
            if a: return a
    return ""

def load_manual_authors() -> Dict[str,str]:
    path = ROOT / "manual_authors.csv"
    if not path.exists(): return {}
    out = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            u, a = (row.get("URL") or "").strip(), normalize_author(row.get("Author") or "")
            if u and a: out[u] = a
    return out

def enrich_authors(items):
    manual = load_manual_authors(); fetched = 0
    for item in items:
        if item["url"] in manual: item["author"] = manual[item["url"]]; continue
        if item.get("author") or not FETCH_BYLINES or fetched >= MAX_BYLINE_FETCHES: continue
        raw = fetch_url(item["url"]); fetched += 1
        if raw:
            a = extract_meta_author(raw.decode("utf-8", errors="ignore"))
            if a: item["author"] = a
        time.sleep(REQUEST_DELAY)

def regex_any(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in patterns)

def match_brands(headline, snippet):
    text = f"{headline} {snippet}"; matched=[]; exclude_reason=""
    for brand,cfg in BRANDS.items():
        inc, exc = regex_any(cfg["include"], text), regex_any(cfg["exclude"], text)
        if inc and not exc: matched.append(brand)
        elif inc and exc: exclude_reason=f"Excluded by {brand} exclusion rule"
    if not matched: return [], "", False, exclude_reason or "No tracked wallet brand matched"
    primary = PRIMARY_BRAND if PRIMARY_BRAND in matched else matched[0]
    competitor = ", ".join([b for b in matched if b != PRIMARY_BRAND])
    return matched, primary, PRIMARY_BRAND in matched, competitor

def classify_narrative(headline, snippet):
    text = f"{headline} {snippet}".lower(); scores={}
    for n,kws in NARRATIVES.items():
        score = sum(1 for kw in kws if kw.lower() in text)
        if score: scores[n]=score
    return max(scores.items(), key=lambda x:x[1])[0] if scores else "General wallet coverage"

def classify_sentiment(headline, snippet):
    text = f"{headline} {snippet}".lower()
    pos, neg = sum(w in text for w in POSITIVE_WORDS), sum(w in text for w in NEGATIVE_WORDS)
    return "Positive" if pos > neg else "Negative" if neg > pos else "Neutral"

def classify_article_type(headline, snippet):
    text = f"{headline} {snippet}".lower()
    if any(re.search(p, text, flags=re.I) for p in SEO_PATTERNS): return "SEO / comparison"
    if any(w in text for w in ["press release","globenewswire","pr newswire","newsfile"]): return "Press release pickup"
    if any(w in text for w in ["op-ed","opinion","commentary"]): return "Opinion / commentary"
    if any(w in text for w in ["interview","q&a","exclusive"]): return "Interview / feature"
    if any(w in text for w in ["market","price","rally","trader","trading volume"]): return "Market commentary"
    return "Original / news"

def outlet_tier(source):
    return "Tier 1" if any(o.lower() in source.lower() for o in TIER1_OUTLETS) else "Crypto / other"

def relevance_score(article_type, tier, narrative, bitget, competitor):
    score = 2 + (tier=="Tier 1")*2 + (narrative!="General wallet coverage")*2 + bitget*2 + bool(competitor) + (article_type in ["Interview / feature","Opinion / commentary","Original / news"])
    if article_type == "SEO / comparison": score -= 1
    return max(1, min(int(score), 10))

def article_id(url, headline):
    return re.sub(r"[^a-zA-Z0-9]+", "", str(abs(hash((url or headline).lower()))))[:16]

def is_qtd(iso_date):
    try:
        d = dt.datetime.fromisoformat(iso_date.replace("Z","+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
        return d >= QTD_START_DT
    except Exception: return True

def is_similar(a,b): return bool(a and b and SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.90)

def dedupe(raw_items):
    seen=set(); kept=[]
    for item in raw_items:
        url=item["url"].split("?")[0]; title=item["headline"]
        if url in seen or any(is_similar(title,k["headline"]) for k in kept[-300:]): continue
        seen.add(url); kept.append(item)
    return kept

def extract_keywords(articles, n=50):
    c=Counter()
    for a in articles:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", f"{a.headline} {a.snippet}".lower())
        for t in tokens:
            t=t.strip("-").lower()
            if t in KEYWORD_STOPWORDS or len(t)<4: continue
            if t.endswith("s") and len(t)>5: t=t[:-1]
            c[t]+=1
    return [{"keyword":k,"count":v} for k,v in c.most_common(n)]

def load_manual_overrides():
    path=ROOT/"manual_overrides.csv"
    if not path.exists(): return {}
    out={}
    with path.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            u=(row.get("URL") or "").strip()
            if u: out[u]=row
    return out

def apply_override(article, override):
    if not override: return article
    decision=(override.get("Include / Exclude") or "").strip().lower()
    if decision=="exclude": article.include=False; article.exclude_reason=override.get("Notes") or "Manual exclusion"
    elif decision=="include": article.include=True; article.exclude_reason=""
    for col, attr in {"Correct Brand":"primary_brand","Correct Narrative":"narrative","Correct Sentiment":"sentiment","Correct Author":"author","Correct Article Type":"article_type"}.items():
        val=(override.get(col) or "").strip()
        if val: setattr(article, attr, val)
    return article

def collect_items():
    raw_items=[]
    for queries in GOOGLE_NEWS_QUERIES.values():
        for q in queries:
            raw=fetch_url(google_news_url(q))
            if raw: raw_items.extend(parse_rss(raw, "Google News"))
            time.sleep(REQUEST_DELAY)
    for feed in MEDIA_RSS_FEEDS:
        raw=fetch_url(feed["url"])
        if raw: raw_items.extend(parse_rss(raw, feed["name"]))
        time.sleep(REQUEST_DELAY)
    items=dedupe([x for x in raw_items if is_qtd(x.get("date",""))])
    enrich_authors(items)
    return items

def classify_items(items):
    overrides=load_manual_overrides(); out=[]
    for item in items:
        brands, primary, bitget, competitor = match_brands(item["headline"], item.get("snippet",""))
        include=bool(brands); exclude_reason="" if include else "No tracked wallet brand matched"
        narrative=classify_narrative(item["headline"], item.get("snippet",""))
        sentiment=classify_sentiment(item["headline"], item.get("snippet",""))
        a_type=classify_article_type(item["headline"], item.get("snippet",""))
        tier=outlet_tier(item.get("source",""))
        score=relevance_score(a_type,tier,narrative,bitget,competitor)
        if a_type=="SEO / comparison" and tier!="Tier 1": include=False; exclude_reason="Filtered low-value SEO/comparison article"
        art=Article(article_id(item["url"],item["headline"]), item["date"], item.get("source",""), item["headline"], item["url"], item.get("author","") or "Unknown author", item.get("snippet",""), brands, primary or "", narrative, sentiment, a_type, tier, score, bitget, competitor, include, exclude_reason)
        art=apply_override(art, overrides.get(art.url, {}))
        if art.include: out.append(art)
    out.sort(key=lambda x:x.date, reverse=True)
    return out

def pitch_angle(narrative):
    return {
        "Stablecoin payments":"Stablecoin payment adoption, settlement, and real-world utility.",
        "Crypto card":"Self-custodial crypto card usage and everyday spending.",
        "QR payments":"APAC QR payment adoption and wallet-based stablecoin spend.",
        "RWA / tokenized assets":"Tokenized stocks/RWAs as the next asset-access layer inside wallets.",
        "Prediction markets":"Prediction markets moving from standalone venues into mobile wallet distribution.",
        "Self-custody":"Self-custody becoming usable everyday finance infrastructure.",
        "Security":"Wallet security data, user-risk taxonomy, or expert commentary.",
    }.get(narrative, "Wallet distribution, usability, and onchain finance infrastructure.")

def build_competitor_intelligence(articles):
    cards = []
    for brand in BRANDS.keys():
        if brand == PRIMARY_BRAND:
            continue
        brand_articles = [a for a in articles if a.primary_brand == brand]
        if not brand_articles:
            cards.append({
                "brand": brand,
                "tagline": "No material QTD signal detected",
                "threat_level": "LOW",
                "mentions": 0,
                "top_narrative": "—",
                "latest_articles": [],
                "verdict": "No meaningful competitor coverage detected in the tracked source set.",
                "suggested_response": "No immediate action required.",
            })
            continue

        top_narrative = Counter(a.narrative for a in brand_articles).most_common(1)[0][0]
        positive = sum(1 for a in brand_articles if a.sentiment == "Positive")
        negative = sum(1 for a in brand_articles if a.sentiment == "Negative")
        tier1 = sum(1 for a in brand_articles if a.tier == "Tier 1")
        mentions = len(brand_articles)

        # Simple PR threat logic, directional only
        if mentions >= 12 or tier1 >= 3 or top_narrative in {"Stablecoin payments", "Crypto card", "RWA / tokenized assets", "Prediction markets"}:
            threat = "HIGH"
        elif mentions >= 5 or tier1 >= 1:
            threat = "MEDIUM"
        else:
            threat = "LOW"

        tagline_map = {
            "MetaMask": "Incumbent self-custody and distribution benchmark",
            "Trust Wallet": "Retail wallet scale and UX competitor",
            "Phantom Wallet": "Solana-native wallet expanding cross-chain",
            "OKX Wallet": "Exchange-backed Web3 wallet and DEX competitor",
            "Coinbase Wallet": "US-regulated wallet and Base ecosystem gateway",
        }

        response_map = {
            "Stablecoin payments": "Respond with data-led payment utility, stablecoin settlement, and real-world spend narratives.",
            "Crypto card": "Emphasize Bitget Wallet Card usability, self-custody, fees, cashback, and spend coverage.",
            "QR payments": "Push APAC QR payment and local merchant acceptance stories.",
            "RWA / tokenized assets": "Position Bitget Wallet as a unified asset-access layer for tokenized stocks and RWAs.",
            "Prediction markets": "Frame Bitget Wallet as the mobile distribution layer for prediction markets.",
            "Onchain trading / swaps": "Highlight Super DEX, routing, gas abstraction, and multi-chain execution.",
            "AI / agentic finance": "Connect wallet UX to AI-assisted discovery, execution, and agent-ready payments.",
        }
        suggested_response = response_map.get(top_narrative, "Monitor for narrative overlap and prepare relevant Bitget Wallet proof points.")

        verdict = f"{brand} is gaining QTD visibility around {top_narrative.lower()} with {mentions} tracked mentions"
        if tier1:
            verdict += f", including {tier1} Tier-1 / high-impact articles"
        verdict += "."

        cards.append({
            "brand": brand,
            "tagline": tagline_map.get(brand, "Wallet competitor"),
            "threat_level": threat,
            "mentions": mentions,
            "positive": positive,
            "negative": negative,
            "tier1": tier1,
            "top_narrative": top_narrative,
            "latest_articles": [
                {
                    "date": a.date,
                    "headline": a.headline,
                    "source": a.source,
                    "url": a.url,
                    "narrative": a.narrative,
                    "sentiment": a.sentiment,
                }
                for a in brand_articles[:4]
            ],
            "verdict": verdict,
            "suggested_response": suggested_response,
        })

    threat_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    cards.sort(key=lambda c: (threat_order.get(c["threat_level"], 0), c["mentions"]), reverse=True)
    return cards


def build_metrics(articles):
    brand_counts=Counter(); sentiment_counts=Counter(); narrative_counts=Counter(); tier_counts=Counter(); article_type_counts=Counter()
    brand_sentiment = {b: Counter() for b in BRANDS.keys()}
    brand_narratives = {b: Counter() for b in BRANDS.keys()}

    for a in articles:
        if a.primary_brand:
            brand_counts[a.primary_brand]+=1
            brand_sentiment[a.primary_brand][a.sentiment] += 1
            brand_narratives[a.primary_brand][a.narrative] += 1
        sentiment_counts[a.sentiment]+=1; narrative_counts[a.narrative]+=1; tier_counts[a.tier]+=1; article_type_counts[a.article_type]+=1

    total=sum(brand_counts.values()) or 1
    brand_metrics=[]
    for b,cfg in BRANDS.items():
        count = brand_counts.get(b,0)
        brand_metrics.append({
            "brand": b,
            "mentions": count,
            "sov": round(count/total*100,2),
            "color": cfg["color"],
            "sentiment": dict(brand_sentiment[b]),
            "top_narrative": brand_narratives[b].most_common(1)[0][0] if brand_narratives[b] else "—",
        })

    rss_articles = len([a for a in articles if a.source != "Google News"])
    google_news_articles = len([a for a in articles if a.source == "Google News"])

    return {
        "generated_at":NOW.isoformat(),
        "time_window":f"QTD from {QTD_START}",
        "qtd_start":QTD_START,
        "total_articles":len(articles),
        "rss_articles": rss_articles,
        "google_news_articles": google_news_articles,
        "meltwater_articles": 0,
        "total_mentions":total,
        "exchanges_tracked": len(BRANDS),
        "primary_brand":PRIMARY_BRAND,
        "brands":brand_metrics,
        "sentiment":dict(sentiment_counts),
        "primary_sentiment": dict(brand_sentiment[PRIMARY_BRAND]),
        "narratives":dict(narrative_counts),
        "keyword_cloud":extract_keywords(articles),
        "tiers":dict(tier_counts),
        "article_types":dict(article_type_counts),
        "top_sources":Counter(a.source for a in articles).most_common(15),
        "competitor_intelligence": build_competitor_intelligence(articles),
    }

def build_journalists(articles):
    named={}; unknown=[]
    for a in articles:
        if not a.author or a.author.lower() in {"unknown author","staff","admin"}:
            unknown.append({"outlet":a.source,"headline":a.headline,"url":a.url,"date":a.date,"narrative":a.narrative,"brand":a.primary_brand}); continue
        key=(a.author.strip(),a.source.strip())
        rec=named.setdefault(key,{"journalist":a.author.strip(),"outlet":a.source.strip(),"articles":0,"recent_articles":[],"narratives":Counter(),"brands":Counter(),"bitget_wallet_covered":False,"tier1_articles":0,"avg_relevance":0,"_relevance_sum":0})
        rec["articles"]+=1; rec["recent_articles"].append({"headline":a.headline,"url":a.url,"date":a.date,"narrative":a.narrative,"brand":a.primary_brand})
        rec["narratives"][a.narrative]+=1; rec["brands"][a.primary_brand]+=1; rec["bitget_wallet_covered"]=rec["bitget_wallet_covered"] or a.bitget_wallet_mentioned
        rec["tier1_articles"] += 1 if a.tier=="Tier 1" else 0; rec["_relevance_sum"] += a.relevance_score
    final=[]
    for rec in named.values():
        rec["avg_relevance"]=round(rec["_relevance_sum"]/max(1,rec["articles"]),1); del rec["_relevance_sum"]
        top=rec["narratives"].most_common(1)[0][0] if rec["narratives"] else "General wallet coverage"
        score=min(10,max(1,min(3,rec["articles"])+(2 if rec["tier1_articles"] else 0)+(2 if rec["bitget_wallet_covered"] else 0)+(2 if top!="General wallet coverage" else 0)+(1 if any(b!=PRIMARY_BRAND for b in rec["brands"]) else 0)))
        rec["top_narrative"]=top; rec["top_brand"]=rec["brands"].most_common(1)[0][0] if rec["brands"] else ""
        rec["narratives"]=dict(rec["narratives"]); rec["brands"]=dict(rec["brands"]); rec["pitch_priority_score"]=score; rec["suggested_pitch_angle"]=pitch_angle(top); rec["recent_articles"]=rec["recent_articles"][:5]
        final.append(rec)
    final.sort(key=lambda r:(r["pitch_priority_score"],r["articles"]), reverse=True)
    return {"named":final,"unknown":unknown[:250],"summary":{"named_journalists":len(final),"unknown_author_articles":len(unknown),"high_priority_journalists":sum(1 for r in final if r["pitch_priority_score"]>=7)}}

def write_json(name,obj):
    (DATA_DIR/name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def main():
    raw=collect_items()
    articles=classify_items(raw)
    metrics=build_metrics(articles); journalists=build_journalists(articles)
    manifest={"last_updated":NOW.isoformat(),"time_window":f"QTD from {QTD_START}","qtd_start":QTD_START,"article_count":len(articles),"tracked_brands":list(BRANDS.keys()),"primary_brand":PRIMARY_BRAND,"generated_by":"run.py v2"}
    write_json("manifest.json",manifest); write_json("articles.json",[asdict(a) for a in articles]); write_json("metrics.json",metrics); write_json("journalists.json",journalists)

if __name__=="__main__":
    main()
