#!/bin/sh
# Install the Kindle weekly news digest into ~/kindle-news.
#
# Run as yourself on a Linux desktop. Needs no root, writes only inside your
# home directory, and touches nothing on the Kindle beyond copying issues into
# its documents folder.
#
# Amazon ended support for every Kindle released in 2012 or earlier on
# 20 May 2026. NEVER factory reset or deregister such a device: it cannot be
# re-registered afterwards and stops working permanently.
set -e

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIR="$HOME/kindle-news"
UNITS="$HOME/.config/systemd/user"

echo "== checking prerequisites =="
command -v ebook-convert >/dev/null || {
    echo "calibre is missing. Install it first, e.g.:"
    echo "    sudo apt-get install -y --no-install-recommends calibre"
    exit 1
}
command -v python3 >/dev/null || { echo "python3 is missing."; exit 1; }
command -v findmnt  >/dev/null || { echo "findmnt is missing (util-linux)."; exit 1; }
systemctl --user is-system-running >/dev/null 2>&1 || {
    echo "No systemd user session. The scripts will still work; the timers will not."
}

echo "== locating the Kindle =="
# The mount point differs by distribution: /media/<user>/ on Debian and Ubuntu
# derivatives, /run/media/<user>/ on Fedora. Detect it rather than assume.
MNT=$(findmnt -rno TARGET -S LABEL=Kindle 2>/dev/null || true)
if [ -z "$MNT" ]; then
    echo "Kindle not currently mounted."
    echo "Plug it in and re-run, or type its mount point now"
    printf "(e.g. /media/%s/Kindle), or press Enter to skip: " "$USER"
    read -r MNT || true      # EOF here must not kill the script under set -e

    # A typo writes a dead path into the systemd unit, and the symptom is
    # silence: issues simply never copy across. Reject anything that is not an
    # absolute path rather than accept it.
    while [ -n "$MNT" ] && [ "${MNT#/}" = "$MNT" ]; do
        echo "  '$MNT' is not an absolute path -- it must start with /"
        printf "  mount point (or Enter to skip): "
        read -r MNT || MNT=""
    done
fi
if [ -z "$MNT" ]; then
    echo "No mount point given, assuming the usual location."
    MNT="/media/$USER/Kindle"
fi
MNT="${MNT%/}"
if [ ! -d "$MNT/documents" ]; then
    echo "note: $MNT/documents does not exist right now."
    echo "      Fine if the Kindle is unplugged. If issues never copy across once"
    echo "      it is plugged in, check this path in $UNITS/kindle-sync.service"
    echo "      against: findmnt -rno TARGET -S LABEL=Kindle"
fi
echo "using: $MNT"

mkdir -p "$DIR" "$UNITS"

echo "== creating the virtualenv =="
# trafilatura cannot live in calibre's Python (calibre ships its own
# interpreter), and most distributions now refuse pip under PEP 668.
[ -d "$DIR/venv" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet trafilatura feedparser

echo "== installing the pipeline =="
# @EMBED src/extract.py -> extract.py
cp "$HERE/src/extract.py" "$DIR/extract.py"
# @EMBED src/digest.recipe -> digest.recipe
cp "$HERE/src/digest.recipe" "$DIR/digest.recipe"
# @EMBED src/fetch.sh -> fetch.sh
cp "$HERE/src/fetch.sh" "$DIR/fetch.sh"
# @EMBED src/remind.sh -> remind.sh
cp "$HERE/src/remind.sh" "$DIR/remind.sh"

# Never overwrite a feed list the user has already customised.
if [ -f "$DIR/feeds.txt" ]; then
    echo "feeds.txt already exists, keeping it."
else
    # @EMBED src/feeds.txt -> feeds.txt
    cp "$HERE/src/feeds.txt" "$DIR/feeds.txt"
fi

chmod +x "$DIR/fetch.sh" "$DIR/remind.sh" "$DIR/extract.py"

echo "== writing the systemd user units =="
cat > "$UNITS/kindle-news.service" <<EOF
[Unit]
Description=Build the weekly Kindle news digest
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=%h/kindle-news/fetch.sh
ExecStartPost=/bin/sh -c 'find %h/kindle-news -maxdepth 1 -name "????-??-??-*.mobi" -mtime +14 -delete'
ExecStartPost=%h/kindle-news/remind.sh
EOF

# ConditionPathExists needs a literal path, so the mount point is baked in here.
cat > "$UNITS/kindle-sync.service" <<EOF
[Unit]
Description=Copy pending news issues to the Kindle, purge issues older than 14 days
ConditionPathExists=$MNT/documents

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'cp --update=none %h/kindle-news/*.mobi $MNT/documents/ 2>/dev/null; true'
ExecStartPost=/bin/sh -c 'find $MNT/documents -maxdepth 1 -name "????-??-??-*.mobi" -mtime +14 -delete; sync; true'
EOF

# @EMBED systemd/kindle-news.timer -> UNITS/kindle-news.timer
cp "$HERE/systemd/kindle-news.timer" "$UNITS/kindle-news.timer"
# @EMBED systemd/kindle-sync.timer -> UNITS/kindle-sync.timer
cp "$HERE/systemd/kindle-sync.timer" "$UNITS/kindle-sync.timer"

if systemctl --user is-system-running >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable --now kindle-news.timer kindle-sync.timer
fi

echo
echo "== your feeds =="
cat <<'EOF'
Four technology feeds are installed as examples. You can add your own now and
each one will be tested before it is accepted, or skip this and edit
feeds.txt later.

The test matters. A feed can return a perfectly good list of articles whose
pages carry no readable text at all, and you would not find out until you
were holding the Kindle.
EOF

if [ ! -t 0 ]; then
    echo
    echo "(stdin is not a terminal, skipping. Edit feeds.txt and use --check by hand.)"
else
    printf "\nDrop the four examples? [y/N]: "
    read -r ANS || ANS=""
    case "$ANS" in
        y|Y|yes) sed -i 's|^\([A-Za-z]\)|# \1|' "$DIR/feeds.txt"
                 echo "examples commented out." ;;
    esac

    while :; do
        printf "\nFeed URL (Enter when done): "
        read -r URL || break
        [ -z "$URL" ] && break
        echo
        if "$DIR/venv/bin/python" "$DIR/extract.py" --check "$URL"; then
            printf "Name to show in the digest: "
            read -r NAME || NAME=""
            [ -z "$NAME" ] && NAME="$URL"
            printf '%s | %s\n' "$NAME" "$URL" >> "$DIR/feeds.txt"
            echo "added."
        else
            echo "not added."
        fi
    done

    echo
    echo "feeds now configured:"
    grep -v '^[[:space:]]*#' "$DIR/feeds.txt" | grep '|' | sed 's/^/  /' || echo "  (none yet)"
fi

cat <<EOF

== done ==

Installed into $DIR

It runs itself from here: builds every Saturday at 07:00, and copies to the
Kindle within two minutes of you plugging it in. Issues older than 14 days are
purged from both places. The purge matches dated filenames only, so sideloaded
books are never touched.

Add or check a feed at any time:

    \$EDITOR $DIR/feeds.txt
    $DIR/venv/bin/python $DIR/extract.py --check <url>

Optional, for a push notification when an issue is waiting and the Kindle is
unplugged, create ~/.config/ntfy/notify.env at mode 600 containing NTFY_URL
and NTFY_TOPIC. Treat the topic as a secret, not a label. Without that file
remind.sh errors and the build still succeeds.

Build one now to check it works:

    $DIR/fetch.sh
EOF
