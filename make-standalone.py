#!/usr/bin/env python3
"""Build the single-file installer from install.sh and src/.

install.sh copies its files out of the clone. The copy published at
nevrast.xyz/kindle.sh has to stand alone, so each "@EMBED" marker and the cp
line beneath it are replaced with a heredoc carrying the file's contents.
One set of sources, two delivery forms, no chance of the two drifting apart.

    python3 make-standalone.py > kindle.sh
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
lines = (HERE / "install.sh").read_text(encoding="utf-8").splitlines(keepends=True)

out, i, n = [], 0, 0
while i < len(lines):
    m = re.match(r'(\s*)# @EMBED (\S+) -> (\S+)\s*$', lines[i])
    if not m:
        out.append(lines[i]); i += 1; continue

    indent, src, dest = m.groups()
    assert lines[i + 1].lstrip().startswith("cp "), f"no cp after marker: {src}"
    body = (HERE / src).read_text(encoding="utf-8").rstrip("\n")
    assert "KINDLE_EMBED" not in body, f"delimiter collision in {src}"

    target = f'"$UNITS/{dest.split("/", 1)[1]}"' if dest.startswith("UNITS/") else f'"$DIR/{dest}"'
    n += 1
    tag = f"KINDLE_EMBED_{n}_EOF"
    out.append(f"{indent}cat > {target} <<'{tag}'\n")
    out.append(body + "\n")
    out.append(f"{tag}\n")
    i += 2

text = "".join(out)
# $HERE only existed to locate the sources being embedded.
text = text.replace('HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n', "")
text = text.replace(
    "# Install the Kindle weekly news digest into ~/kindle-news.",
    "# kindle.sh -- install the Kindle weekly news digest into ~/kindle-news.\n"
    "#\n"
    "# Generated from install.sh and src/ by make-standalone.py. Do not edit:\n"
    "# edit the sources at https://github.com/StathisZ/kindle-news-digest\n"
    "#\n"
    "# INSTALL: curl -O https://nevrast.xyz/kindle.sh ; sh kindle.sh\n"
    "# README:  https://nevrast.xyz/kindle-tutorial.html")
assert "$HERE" not in text, "standalone still references the clone"
sys.stdout.write(text)
