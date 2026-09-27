#!/usr/bin/env python3
"""Reader-mode extraction for the Kindle digest.

Reads the feeds, pulls each article down to its text with trafilatura, drops
whatever fails to extract, and writes digest.json for digest.recipe to package.
calibre never fetches a page, so its weak built-in readability never runs.
"""
import json, os, re, html, sys, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import feedparser
import trafilatura

FEEDS_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds.txt")


def load_feeds():
    """Feeds live in feeds.txt so adding one is appending a line."""
    out = []
    if not os.path.exists(FEEDS_FILE):
        return out
    for line in open(FEEDS_FILE, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        name, url = line.split("|", 1)
        out.append((name.strip(), url.strip()))
    return out

DAYS          = 7
MAX_PER_FEED  = 12
MIN_CHARS     = 900     # below this it is a stub, a paywall, or a landing page
MAX_DENSITY   = 0.15    # above this it is still page furniture
WORKERS       = 8
UA            = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
OUT           = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest.json")


def density(h):
    """Share of text that lives inside links. Prose is near zero."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()
    atext = " ".join(re.sub(r"<[^>]+>", "", m)
                     for m in re.findall(r"<a\s[^>]*>(.*?)</a>", h, re.S))
    atext = re.sub(r"\s+", " ", html.unescape(atext)).strip()
    return len(atext) / max(len(text), 1), len(text)


def fetch(url):
    """Fetch with a browser user-agent. trafilatura's own is widely blocked."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            enc = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(enc, "replace")
    except Exception:
        return trafilatura.fetch_url(url)      # last resort


def embedded(entry):
    """Full article HTML carried in the feed itself, if it is there."""
    for c in entry.get("content") or []:
        v = c.get("value") or ""
        if len(v) > 2000:
            return v
    return None


def site(url):
    h = urllib.parse.urlsplit(url or "").hostname or ""
    for prefix in ("www.", "feeds.", "feed.", "rss."):
        if h.startswith(prefix):
            h = h[len(prefix):]
    return h


def same_site(a, b):
    a, b = site(a), site(b)
    return bool(a and b) and (a.endswith(b) or b.endswith(a))


def author_of(entry, feed_url, page):
    """The article's writer, or "" if unknown.

    A publisher's own feed names the writer, and does so better than the page
    metadata does (Ars: "Alec MacGillis, ProPublica" against just "ProPublica").
    An aggregator's feed names whoever submitted the link, which is the wrong
    person entirely -- so for off-site articles only the page's own byline is
    trusted, and there is no fallback to the submitter.
    """
    name = ""
    if same_site(entry.get("link"), feed_url):
        name = entry.get("author") or ""
    if not name and page:
        meta = trafilatura.extract_metadata(page, default_url=entry.get("link"))
        name = (meta.author or "") if meta else ""
    name = re.sub(r"\s+", " ", name).strip()
    return re.sub(r"^by\s+", "", name, flags=re.I)


def extract(entry, feed_url=""):
    """Return (clean article HTML, reason, author); HTML is None on failure."""
    url = entry.get("link")
    if not url:
        return None, "no url", ""

    page = None
    src = embedded(entry)          # free: no fetch needed
    if src is None:
        src = page = fetch(url)
        if src is None:
            return None, "fetch blocked", ""

    out = trafilatura.extract(src, output_format="html", url=url,
                              include_comments=False, include_tables=True,
                              favor_precision=True)
    if not out:
        return None, "no article found", ""

    d, chars = density(out)
    if chars < MIN_CHARS:
        return None, f"too short ({chars}c)", ""
    if d > MAX_DENSITY:
        return None, f"still furniture (density {d:.2f})", ""

    # Gate first, byline after, so the name never affects the quality checks.
    author = author_of(entry, feed_url, page)
    if author:
        out = f"<p><strong>By {html.escape(author)}</strong></p>\n" + out
    return out, f"{chars}c density {d:.2f}", author



def check(url):
    """Test a feed before adding it. Reports why it will not work, if it will not."""
    print(f"checking {url}")

    try:
        raw = fetch(url)
        if raw is None:
            raise ValueError
    except Exception:
        print("  FAILED  the feed itself could not be fetched.")
        print("          Check the URL. Some publishers block non-browser clients entirely.")
        return 1

    parsed = feedparser.parse(raw)
    n = len(parsed.entries)
    if n == 0:
        print("  FAILED  the feed loaded but contains no items.")
        print("          Some sites serve an empty feed, or a page that is not a feed at all.")
        return 1
    print(f"  feed OK: {n} items")

    results = []
    for e in parsed.entries[:3]:
        body, why, author = extract(e, url)
        title = re.sub(r"\s+", " ", e.get("title", "?")).strip()[:44]
        by = f"  by {author}" if author else ("  (no author)" if body else "")
        print(f"    {'ok  ' if body else 'FAIL'}  {title:<46} {why}{by}")
        results.append((body is not None, why))

    ok = sum(1 for good, _ in results if good)
    if ok == len(results):
        print("  GOOD    articles extract cleanly. Safe to add.")
        return 0
    if ok:
        print(f"  MIXED   {ok} of {len(results)} articles extracted.")
        print("          Usable. The rest will be dropped from each issue automatically.")
        return 0

    why = results[0][1]
    print("  UNUSABLE  no article could be extracted.")
    if "fetch blocked" in why:
        print("          The feed loads but article pages refuse us. Nothing to be done here.")
    elif "no article found" in why:
        print("          The pages carry no article text. Sites that render their text in")
        print("          JavaScript look complete but are empty to any extractor. Only a")
        print("          headless browser could read this. Pick a different source.")
    else:
        print("          Articles came back too short, which usually means a paywall or a")
        print("          feed of teasers rather than full pieces.")
    return 1


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)
    seen_urls, seen_titles = set(), set()
    sections, kept, dropped = [], 0, 0

    for name, url in load_feeds():
        parsed = feedparser.parse(url)
        entries = []
        for e in parsed.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t and datetime(*t[:6], tzinfo=timezone.utc) < cutoff:
                continue
            link = (e.get("link") or "").split("?")[0].rstrip("/")
            title = re.sub(r"\s+", " ", e.get("title", "")).strip()
            key = title.lower()
            if not link or link in seen_urls or key in seen_titles:
                continue      # aggregators surface the same link repeatedly
            seen_urls.add(link); seen_titles.add(key)
            entries.append(e)
            if len(entries) >= MAX_PER_FEED:
                break

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(lambda e: extract(e, url), entries))

        arts = []
        for e, (body, why, author) in zip(entries, results):
            title = re.sub(r"\s+", " ", e.get("title", "Untitled")).strip()
            if body is None:
                dropped += 1
                print(f"  drop  {title[:58]:<60} {why}", file=sys.stderr)
                continue
            kept += 1
            arts.append({
                "title": title,
                "url": e.get("link"),
                "date": e.get("published", ""),
                "author": author,
                "description": body,
            })

        print(f"{name}: kept {len(arts)}", file=sys.stderr)
        if arts:
            sections.append({"title": name, "articles": arts})

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"built": datetime.now(timezone.utc).isoformat(),
                   "sections": sections}, f, ensure_ascii=False)

    print(f"\nkept {kept}, dropped {dropped}, {len(sections)} sections -> {OUT}",
          file=sys.stderr)
    return 0 if kept else 1


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2]))
    sys.exit(main())
