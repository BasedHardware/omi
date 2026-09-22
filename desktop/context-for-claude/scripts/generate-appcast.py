#!/usr/bin/env python3
"""Generate the Sparkle 2 appcast a micro-app release publishes as its update feed.

Every value in the emitted item comes from something real: the packaged ZIP on disk supplies
`length`, Sparkle's `sign_update` supplies `sparkle:edSignature`, the app's own
`Resources/Info.plist` supplies `sparkle:minimumSystemVersion`, and the caller supplies the
version, numeric build, and enclosure URL. Nothing is defaulted into existence — a missing
`LSMinimumSystemVersion` or an unreadable ZIP is an error rather than a guess, because a feed
that merely parses is not the same thing as a feed that describes the artifact users download.

The feed is not a tracked file. It lives as an asset on a fixed GitHub release, so the previous
feed has to be handed in with --existing for its items to survive; without that the run would
silently publish a feed whose only entry is today's release, and Sparkle clients on older
builds would lose every intermediate version. An --existing file that exists but does not parse
is a hard failure for the same reason: dropping history is never the safer branch.

Re-running with the same inputs is a no-op. An item whose sparkle:version already appears is
replaced in place and keeps its original pubDate, so a retried release does not reorder the
feed or invent a new publication date for an already-published build.

Usage:
  generate-appcast.py --output dist/appcast.xml \
      --title "Context for Claude" \
      --feed-url https://github.com/OWNER/REPO/releases/download/context-for-claude-appcast/appcast.xml \
      --version 1.1.0 --build 1001000 \
      --zip dist/ContextForClaude-1.1.0.zip \
      --signature "$ED_SIGNATURE" \
      --enclosure-url https://github.com/OWNER/REPO/releases/download/context-for-claude-v1.1.0/ContextForClaude-1.1.0.zip \
      --info-plist Resources/Info.plist \
      [--existing dist/appcast-current.xml] [--notes-file notes.md] [--pub-date "<RFC 2822>"] [--rehearsal]
"""

from __future__ import annotations

import argparse
import os
import plistlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime

SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
DC_NS = "http://purl.org/dc/elements/1.1/"
ET.register_namespace("sparkle", SPARKLE_NS)
ET.register_namespace("dc", DC_NS)

# 64 raw EdDSA bytes, base64-encoded. A truncated or empty signature makes every client reject
# the update, and the failure surfaces only on a user's machine, so it is checked here instead.
SIGNATURE_RE = re.compile(r"^[A-Za-z0-9+/]{86}==$")

REHEARSAL_BANNER = (
    "  REHEARSAL FEED — NOT DISTRIBUTABLE.\n"
    "  Produced by a rehearsal run: the enclosure it names is not a notarized Developer ID\n"
    "  build, so Gatekeeper refuses it on any machine but the one that built it. Never upload\n"
    "  this file to the production update feed.\n"
)


def die(message: str) -> "None":
    print(f"generate-appcast: {message}", file=sys.stderr)
    raise SystemExit(1)


def sparkle(tag: str) -> str:
    return f"{{{SPARKLE_NS}}}{tag}"


def minimum_system_version(info_plist: str) -> str:
    """The app's own LSMinimumSystemVersion — the single copy of this fact."""
    try:
        with open(info_plist, "rb") as handle:
            plist = plistlib.load(handle)
    except OSError as error:
        die(f"cannot read --info-plist {info_plist}: {error}")
    except plistlib.InvalidFileException as error:
        die(f"--info-plist {info_plist} is not a readable plist: {error}")
    value = plist.get("LSMinimumSystemVersion")
    if not isinstance(value, str) or not value.strip():
        die(
            f"{info_plist} has no usable LSMinimumSystemVersion; Sparkle would offer this update "
            "to systems that cannot run it"
        )
    return value.strip()


def load_channel(existing: str | None) -> tuple[ET.Element, ET.Element]:
    """Return (rss, channel), reusing an existing feed's items when one was handed in."""
    if existing and os.path.exists(existing) and os.path.getsize(existing) > 0:
        try:
            rss = ET.parse(existing).getroot()
        except ET.ParseError as error:
            die(
                f"--existing {existing} does not parse as XML ({error}); refusing to publish a feed "
                "that would drop the update history it contains"
            )
        if rss.tag != "rss":
            die(f"--existing {existing} is not an RSS feed (root element is <{rss.tag}>)")
        channel = rss.find("channel")
        if channel is None:
            die(f"--existing {existing} has no <channel>")
        return rss, channel
    rss = ET.Element("rss", {"version": "2.0"})
    return rss, ET.SubElement(rss, "channel")


def set_channel_text(channel: ET.Element, tag: str, text: str) -> None:
    element = channel.find(tag)
    if element is None:
        element = ET.Element(tag)
        first_item = channel.find("item")
        # Ahead of the items, so the channel metadata stays readable at the top of the file.
        if first_item is None:
            channel.append(element)
        else:
            channel.insert(list(channel).index(first_item), element)
    element.text = text


def build_item(args: argparse.Namespace, length: int | None, pub_date: str, min_system: str) -> ET.Element:
    item = ET.Element("item")
    ET.SubElement(item, "title").text = args.version
    ET.SubElement(item, "pubDate").text = pub_date
    ET.SubElement(item, sparkle("version")).text = str(args.build)
    ET.SubElement(item, sparkle("shortVersionString")).text = args.version
    ET.SubElement(item, sparkle("minimumSystemVersion")).text = min_system
    ET.SubElement(item, "description").text = args.notes
    enclosure = {
        "url": args.enclosure_url,
        sparkle("edSignature"): args.signature,
        "type": "application/octet-stream",
    }
    # Omitted rather than zero when it is genuinely unknown: Sparkle treats a zero length as a
    # broken enclosure, while an absent one only costs it a progress bar.
    if length is not None:
        enclosure["length"] = str(length)
    ET.SubElement(item, "enclosure", enclosure)
    return item


def replace_or_insert(channel: ET.Element, item: ET.Element, build: int) -> str | None:
    """Swap the item for the same build if present (returning its pubDate), else insert newest-first."""
    items = channel.findall("item")
    for existing in items:
        version = existing.findtext(sparkle("version"), "").strip()
        if version == str(build):
            previous = existing.findtext("pubDate")
            index = list(channel).index(existing)
            channel.remove(existing)
            channel.insert(index, item)
            return previous
    if items:
        channel.insert(list(channel).index(items[0]), item)
    else:
        channel.append(item)
    return None


def serialize(rss: ET.Element, rehearsal: bool) -> str:
    ET.indent(rss, space="  ")
    body = ET.tostring(rss, encoding="unicode")
    banner = f"<!--\n{REHEARSAL_BANNER}-->\n" if rehearsal else ""
    return f'<?xml version="1.0" encoding="utf-8"?>\n{banner}{body}\n'


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, help="feed to write")
    parser.add_argument("--existing", help="the feed currently published, whose items must survive")
    parser.add_argument("--title", required=True, help="channel title (the product name)")
    parser.add_argument("--feed-url", required=True, help="the URL the app's SUFeedURL points at")
    parser.add_argument("--version", required=True, help="short version string, x.y.z")
    parser.add_argument("--build", required=True, type=int, help="numeric Sparkle build")
    parser.add_argument("--zip", help="the packaged Sparkle enclosure, read for its byte length")
    parser.add_argument("--length", type=int, help="enclosure byte length when no --zip is available")
    parser.add_argument("--signature", required=True, help="sparkle:edSignature from sign_update")
    parser.add_argument("--enclosure-url", required=True, help="download URL of the ZIP this item names")
    parser.add_argument("--info-plist", required=True, help="the app's Info.plist, read for LSMinimumSystemVersion")
    parser.add_argument("--notes", help="release notes for the item description")
    parser.add_argument("--notes-file", help="file to read the release notes from")
    parser.add_argument("--pub-date", help="RFC 2822 pubDate (default: now, or the replaced item's)")
    parser.add_argument("--rehearsal", action="store_true", help="mark the feed as a non-distributable rehearsal")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        die(f"--version must be a stable semantic version (x.y.z), got '{args.version}'")
    if args.build <= 0:
        die("--build must be a positive integer")
    if not SIGNATURE_RE.match(args.signature):
        die("--signature is not a base64 EdDSA signature; refusing to publish an unverifiable enclosure")
    for name, url in (("--feed-url", args.feed_url), ("--enclosure-url", args.enclosure_url)):
        if not url.startswith("https://"):
            die(f"{name} must be an https URL, got '{url}'")
        # `releases/latest/download` resolves to the newest release of the whole repository, which
        # ships other products' tags almost daily, so it would 404 or hand out the wrong bundle.
        if "releases/latest/download" in url:
            die(f"{name} uses releases/latest/download, which does not name this product's release")
    if args.notes and args.notes_file:
        die("pass either --notes or --notes-file, not both")
    if args.notes_file:
        try:
            with open(args.notes_file, encoding="utf-8") as handle:
                args.notes = handle.read().strip()
        except OSError as error:
            die(f"cannot read --notes-file {args.notes_file}: {error}")
    if not args.notes:
        args.notes = f"{args.title} {args.version}."
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    length: int | None = None
    if args.zip:
        if not os.path.isfile(args.zip):
            die(f"--zip {args.zip} does not exist; the enclosure length must be the real byte size")
        length = os.path.getsize(args.zip)
        if length <= 0:
            die(f"--zip {args.zip} is empty")
    elif args.length is not None:
        if args.length <= 0:
            die("--length must be positive; omit it entirely when the size is unknown")
        length = args.length

    min_system = minimum_system_version(args.info_plist)
    rss, channel = load_channel(args.existing)
    set_channel_text(channel, "title", args.title)
    set_channel_text(channel, "link", args.feed_url)
    set_channel_text(channel, "description", f"Updates for {args.title}.")
    set_channel_text(channel, "language", "en")

    pub_date = args.pub_date or format_datetime(datetime.now(timezone.utc))
    item = build_item(args, length, pub_date, min_system)
    previous_pub_date = replace_or_insert(channel, item, args.build)
    if previous_pub_date and not args.pub_date:
        # A retried release republishes the same build; its publication date already happened.
        item.find("pubDate").text = previous_pub_date

    output = serialize(rss, args.rehearsal)
    directory = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(directory, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(output)

    items = channel.findall("item")
    print(
        f"generate-appcast: wrote {args.output} — build {args.build} ({args.version}), "
        f"length {'omitted' if length is None else length}, {len(items)} item(s) in the feed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
