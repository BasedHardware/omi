# Export memories as an Atom feed

Turn local `omi memory list` JSON exports into an Atom 1.0 feed for a feed reader
such as NetNewsWire or Thunderbird. The converter uses only the Python standard
library, makes no network requests, and requires Python 3.10 or later.

## Export and convert

Export one page of memories and convert it to a new XML file:

```sh
omi --json memory list --limit 200 --offset 0 > memories-page-0.json
python memories_to_atom.py memories.xml memories-page-0.json
```

For more than 200 memories, export additional pages with increasing offsets, then
pass all the files to the converter:

```sh
omi --json memory list --limit 200 --offset 200 > memories-page-1.json
python memories_to_atom.py memories.xml memories-page-0.json memories-page-1.json
```

You can also pipe one page directly from the CLI:

```sh
omi --json memory list --limit 200 --offset 0 | python memories_to_atom.py memories.xml -
```

Check that each `omi` command succeeded before converting its output. A page is
limited to 200 records; passing one page does not make a complete account backup.
When pages overlap, the last input file wins for a repeated memory ID.

## Feed contents and privacy

Each memory becomes one entry. The memory content is the entry title; the summary
contains only its category, visibility, tags, and creation time. Both Atom
`published` and `updated` use `created_at`, normalized to UTC. An absent or
unparseable timestamp uses the Unix epoch so the entry remains valid. Entries are
sorted newest first.

The feed includes the memory text in its titles. Keep the XML file in a private
location and do not publish it unless you intend to share those memories. The
converter XML-escapes values and removes XML 1.0 control characters, lone
surrogates, and Unicode non-characters. Memory IDs are percent-encoded in Atom
IDs. Rows without an ID are skipped, and loosely typed fields are converted to
text.

The output path must not already exist. The file is created with owner-only
permissions on systems that support POSIX file modes. To regenerate a feed, choose
a new output filename or remove the old file yourself after checking it.

## Example reader setup

Add the resulting `memories.xml` file to a reader that supports local feeds. Some
readers require the file to be served from a local web server instead of opening a
`file://` URL; in that case, serve only a directory that is not accessible to
other people.
