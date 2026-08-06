"""arXiv — the one source that needs no credentials.

Deliberately thin. It fetches and parses; it does not decide what is interesting.
Nothing here writes prose, so nothing here can invent a finding: the title, the
authors, the identifier and the date all come back exactly as arXiv published
them, and the editorial layer only ever sees real records.
"""

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

from models.paper import PaperItem, SourceHealth
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_API = 'https://export.arxiv.org/api/query'
_NS = {'atom': 'http://www.w3.org/2005/Atom'}
_TIMEOUT_SECONDS = 25

# arXiv asks for a descriptive agent so they can contact heavy users.
_USER_AGENT = 'omi-paper/0.1 (+https://omi.me; daily research brief)'


# Authors write abstracts in LaTeX and arXiv serves them raw, so `\emph{...}` and
# friends arrive intact. Strip the markup, keep the words — never drop the content.
_LATEX_COMMAND = re.compile(r'\\[a-zA-Z]+\s*')
_LATEX_BRACES = re.compile(r'[{}]')
_MATH = re.compile(r'\$([^$]*)\$')


def _de_latex(text: str) -> str:
    text = _MATH.sub(r'\1', text)
    text = _LATEX_COMMAND.sub('', text)
    text = _LATEX_BRACES.sub('', text)
    return ' '.join(text.split())


def _text(entry: ET.Element, tag: str) -> str:
    node = entry.find(f'atom:{tag}', _NS)
    return _de_latex(node.text or '') if node is not None else ''


def _to_item(entry: ET.Element) -> PaperItem | None:
    """One Atom entry to a PaperItem, or None if it is unusable."""
    title = _text(entry, 'title')
    url = _text(entry, 'id')
    if not title or not url:
        return None

    identifier = url.rsplit('/abs/', 1)[-1]
    authors = [' '.join((a.text or '').split()) for a in entry.findall('atom:author/atom:name', _NS)]

    return PaperItem(
        title=title,
        # Long author lists are the norm; the byline prints the first few and says so.
        authors=', '.join(authors[:6]) + (' et al.' if len(authors) > 6 else ''),
        submitted=_text(entry, 'published')[:10],
        identifier=f'arXiv:{identifier}',
        url=url,
        # `summary` is the published abstract. It is kept verbatim on the item and is
        # the ONLY text the editorial layer is allowed to read for this paper.
        what_it_says=_text(entry, 'summary'),
    )


def fetch_papers(queries: list[str], since: date, limit: int = 40) -> tuple[list[PaperItem], SourceHealth]:
    """Recent arXiv submissions matching any query, newest first.

    ``since`` drops anything published earlier, because a briefing that surfaces
    a nine-month-old paper as news has failed even when the paper is good.
    """
    seen: dict[str, PaperItem] = {}
    failures: list[str] = []
    fetched = 0

    for query in queries:
        params = urllib.parse.urlencode(
            {
                'search_query': f'all:"{query}"',
                'start': 0,
                'max_results': limit,
                'sortBy': 'submittedDate',
                'sortOrder': 'descending',
            }
        )
        request = urllib.request.Request(f'{_API}?{params}', headers={'User-Agent': _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 — fixed host
                root = ET.fromstring(response.read())
        except Exception as e:  # noqa: BLE001 — one bad query must not kill the brief
            # The query is a learned interest topic derived from private
            # conversations, so it does not go to the log either.
            logger.warning('paper: an arxiv query failed: %s', sanitize(str(e)))
            failures.append(query)
            continue

        for entry in root.findall('atom:entry', _NS):
            fetched += 1
            item = _to_item(entry)
            if item is None or item.identifier in seen:
                continue
            if item.submitted and item.submitted < since.isoformat():
                continue
            seen[item.identifier] = item

    items = sorted(seen.values(), key=lambda p: p.submitted, reverse=True)
    health = SourceHealth(
        source='arXiv',
        ok=len(failures) < len(queries),
        fetched=fetched,
        kept=len(items),
        note=f'{len(failures)}/{len(queries)} queries failed' if failures else '',
    )
    return items, health
