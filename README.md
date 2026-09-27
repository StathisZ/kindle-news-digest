# kindle-news-digest

A weekly newspaper for a Kindle, built from RSS feeds and delivered over USB.

On 20 May 2026 Amazon ended support for every Kindle released in 2012 or earlier. The store is gone from those devices, and so is Send to Kindle — Amazon's own guidance is that affected e-readers are USB only for personal documents. The hardware cannot negotiate modern TLS and cannot be patched, so there is no wireless route back.

This turns such a device into something that receives a weekly digest instead. It builds itself on a schedule and copies across when you plug the cable in.

> **Never factory reset or deregister a cut-off Kindle.** It cannot be re-registered afterwards and stops working entirely. Many older repurposing guides open by telling you to reset first; that instruction now destroys the device. This project only writes to your computer, and touches the Kindle only by copying files into its `documents` folder.

## Why not just use calibre's recipes

calibre has a perfectly good periodical builder, and this uses it. What it does not have is a reliable article extractor. Its `auto_cleanup` readability returns the entire page whenever it cannot identify the article body, which on a 600x800 e-ink screen is unreadable.

Measured on a real issue built with `auto_cleanup`: median link density 0.06 across 86 sections, nine articles broken, one carrying 77 links inside 5.4KB of text.

So extraction is separated from packaging. [trafilatura](https://github.com/adbar/trafilatura) reduces each article to its text, then calibre packages the result with `use_embedded_content = True` and never fetches a page itself. The same issue after the change: median and maximum link density both 0.000, 11MB down to 515KB.

Extraction cannot run inside calibre, incidentally — calibre ships its own Python interpreter, so a recipe cannot import anything you install. That constraint is what makes the two-stage split the natural shape rather than a workaround.

## What this installs

Everything lands in `~/kindle-news`, plus four systemd **user** units. No root, nothing outside your home directory.

- `feeds.txt` — your sources, one `Name | URL` line each.
- `extract.py` — reads the feeds, pulls each article down to its text with the writer's name at the top, drops what fails.
- `digest.recipe` — packaging only. calibre fetches nothing.
- `fetch.sh` — runs both stages, then copies if the Kindle is plugged in.
- `remind.sh` — optional [ntfy](https://ntfy.sh) nudge when an issue is waiting and the device is not connected.
- `kindle-news.timer` — builds every Saturday at 07:00. `Persistent=true`, so a run missed because the machine was off happens at the next boot.
- `kindle-sync.timer` — every two minutes, copies pending issues if the Kindle is mounted.

Both timers also purge issues older than fourteen days.

## Install

calibre first, since the installer checks for it rather than guessing your package manager:

```
sudo apt-get install -y --no-install-recommends calibre
```

Then either clone this repository:

```
git clone https://github.com/StathisZ/kindle-news-digest
cd kindle-news-digest
./install.sh
```

or take the single-file version, which needs no clone:

```
curl -O https://nevrast.xyz/kindle.sh
sh kindle.sh
```

Download it and run it as a file rather than piping it into `sh`. A piped script has the pipe as its standard input, so its prompts would read lines of the script instead of your answers.

The installer detects the Kindle's mount point, or asks for it and rejects anything that is not an absolute path. It then offers to replace the four example feeds with your own, checking each before accepting it.

## Checking a feed

```
~/kindle-news/venv/bin/python ~/kindle-news/extract.py --check <url>
```

Do this before adding any source. A feed can return a perfectly healthy list of articles whose pages contain no readable text at all, and you would not find out until you were holding the Kindle.

The checker fetches the feed, counts the items, then puts three articles through the real extractor:

```
  feed OK: 100 items
    ok    The intractable problems pulling modern Brit   11236c density 0.00  by Charlie Bentley-Astor
    ok    Are the directors all perverts?                 5632c density 0.00  by Robert Thicknesse
  GOOD    articles extract cleanly. Safe to add.
```

Each line also shows the byline the article will carry, or `(no author)`, so you can see whether a source names its writers before you add it.

It separates three failure modes, because only one is worth retrying:

| Verdict | Meaning |
|---|---|
| `fetch blocked` | The publisher refuses non-browser clients. Sometimes retryable. |
| `no article found` | The text is rendered in JavaScript. No extractor will ever see it. |
| `too short` | A paywall, or a feed of teasers rather than full pieces. |

The second one is worth knowing about. A page can be 454KB, carry an `<article>` element and the right `<title>`, and still contain zero real paragraph nodes because all of them live inside `<script>` tags. Count DOM nodes, not string occurrences, before blaming your extractor.

## Bylines

Each article opens with its writer's name. Where that name comes from depends on the feed, because feeds disagree about what "author" means.

A publisher's own feed names the writer, and does it better than the article page's metadata. Ars Technica's page declares only `ProPublica`; its feed says `Alec MacGillis, ProPublica`. So for articles on the feed's own site, the feed's author field is used.

An aggregator's feed names the person who *submitted* the link. Hacker News reports a username; Lobsters reports `site.com via username`. Showing that as the author would be wrong. So for articles that live somewhere other than the feed's site, only the byline on the article page itself is used, and there is no fallback to the submitter. Where a page declares no author, the article carries none rather than a wrong one.

## Notifications

Optional, and off until you create `~/.config/ntfy/notify.env` at mode 600:

```
NTFY_URL=https://your.server
NTFY_TOPIC=yourtopic
```

Treat the topic as a secret rather than a label — anyone who knows it can read and publish to it. Without that file `remind.sh` errors and the build still succeeds. `remind.sh --force` sends one regardless, for testing.

## Notes

- The purge matches `????-??-??-*.mobi` only. Sideloaded books never begin with a date, so they cannot be caught by it. Verified by artificially ageing real books and confirming they survive.
- `cp` sets the copy time rather than the build time, so the fourteen days run from when an issue reached the device. An issue you never collected does not arrive already expired.
- `kindle.sh` is generated from `install.sh` and `src/` by `make-standalone.py`. Edit the sources, not the generated file.

Full write-up: [a weekly newspaper for a cut-off Kindle](https://nevrast.xyz/kindle-tutorial.html)

## Licence

MIT. See [LICENSE](LICENSE).
