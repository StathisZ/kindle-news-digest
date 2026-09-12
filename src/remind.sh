#!/bin/sh
# Nudge to plug in the Kindle when a fresh issue is waiting for it.
# Silent when the Kindle is already connected -- kindle-sync will collect it.
set -e

# --force sends anyway, for testing without unplugging the Kindle.
[ "$1" = "--force" ] || [ -z "$(findmnt -rno TARGET -S LABEL=Kindle 2>/dev/null)" ] || exit 0

. "$HOME/.config/ntfy/notify.env"
: "${NTFY_URL:?set NTFY_URL in ~/.config/ntfy/notify.env}"
: "${NTFY_TOPIC:?set NTFY_TOPIC in ~/.config/ntfy/notify.env}"

pending=$(ls -1 "$HOME"/kindle-news/*.mobi 2>/dev/null | wc -l)

curl -fsS -m 10 \
    -H "Title: Weekly digest ready" \
    -H "Tags: books" \
    -H "Priority: low" \
    -d "New issue built. Plug in the Kindle to collect it ($pending waiting)." \
    "$NTFY_URL/$NTFY_TOPIC" >/dev/null
