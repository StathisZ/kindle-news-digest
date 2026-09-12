#!/bin/sh
# Build the weekly digest and drop it on the Kindle if it is plugged in.
#
# Two stages: extract.py pulls each article down to its text with trafilatura,
# then calibre packages the result. calibre never fetches a page itself, so its
# weak built-in readability never runs.
set -e

DIR="$HOME/kindle-news"
out="$DIR/$(date +%F)-weekly.mobi"

"$DIR/venv/bin/python" "$DIR/extract.py"
ebook-convert "$DIR/digest.recipe" "$out" --output-profile kindle

mnt=$(findmnt -rno TARGET -S LABEL=Kindle 2>/dev/null || true)
if [ -n "$mnt" ] && [ -d "$mnt/documents" ]; then
    cp --update=none "$out" "$mnt/documents/"
    sync
    echo "copied to $mnt/documents/"
else
    echo "Kindle not mounted; left at $out"
fi
