"""
Converts the comment of an nLab edit (MarkdownItex, as on the nForum) into
Zulip Markdown.

* Math: $...$ becomes Zulip's inline $$...$$; $$...$$, \\[...\\] and
  \\begin{equation}...\\end{equation} at the start of a line become a math
  block. itex-only commands are rewritten for KaTeX (itex_to_katex.py).
  \\$ is a literal dollar sign.
* [[wikilinks]] become Markdown links to the nLab.
* <a href="...">...</a> becomes a Markdown link (Zulip escapes raw HTML).
* Relative link targets become absolute, relative to the nLab page (Zulip
  would prefix them with "http://"); see resolve_url.
* Mentions are made silent (@**X** becomes @_**X**), so that nobody can
  notify Zulip users, or a whole channel, through the nLab edit form.
* Code spans and fenced code blocks are left alone.

Adapted from the nForum -> Zulip converter (render.py), which uses the same
patterns as the nForum's MarkdownItex extension.
"""

import re
import urllib.parse

from itex_to_katex import itex_to_katex

BLOCK_MATH_RE = re.compile(
    r"^[ ]{0,3}(?:\$\$|\\\[|\\begin\{equation\})(.*?)(?:\$\$|\\\]|\\end\{equation\})\s*$",
    re.S | re.M)
INLINE_MATH_RE = re.compile(r"(?<!\\)\$((?:[^\$]|\\\$)+)\$")
WIKILINK_RE = re.compile(r"(?<!\\)\[\[\s*([^\]\s][^\]]*?)\s*\]\]")
FENCED_CODE_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^(?P=fence)[ \t]*$", re.S | re.M)
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.S)
HTML_LINK_RE = re.compile(
    r'<a\s+[^>]*?href\s*=\s*["\']?([^"\'\s>]+)["\']?[^>]*>(.*?)</a>',
    re.S | re.I)
MENTION_RE = re.compile(r"(?<![\w@])@(?=\*)")
SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# Paths on the nLab, also without the leading slash: "/nlab/files/x.pdf", "schreiber/show/y"
NLAB_PATH_RE = re.compile(r"/?[A-Za-z0-9_-]+/(?:show|files|revision|new|edit|history|source|print|published|list|recently_revised|search)(?=[/?#]|$)")
EMBEDDED_URL_RE = re.compile(r"https?://[^\s()\[\]<>]+")  # "/http://msp.org/...", "(https://arxiv.org/...)"
DOMAIN_RE = re.compile(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:[/:?#]|$)")  # "www.example.org/x.pdf"
DOI_RE = re.compile(r"10\.\d{4,}/")
MD_URL = r"[^\s<>()]+(?:\([^\s<>()]*\)[^\s<>()]*)*"  # with balanced parentheses, as in DOIs
MD_LINK_TARGET_RES = [
    re.compile(r"(\]\(\s*<?)(%s)" % MD_URL),
    # Link definitions; not footnotes ("[^1]: ...") and other text after "[x]:"
    re.compile(r"""^([ ]{0,3}\[(?!\^)[^\]\n]+\]:[ \t]*<?)(%s)(?=>?(?:[ \t]+["'(].*)?[ \t]*$)""" % MD_URL, re.M),
]
PLACEHOLDER_RE = re.compile(r"QQ(\d+)QQ")


def _wikilink(inner, nlab_url):
    """(url, label) of a wikilink, as the nForum's MarkdownItex built it."""
    m = re.match(r"^([A-Za-z]*):(.*)", inner, re.S)
    if m:
        link, kind = m.group(2), m.group(1).lower()
    else:
        link, kind = inner, "none"
    m = re.match(r"(.*)\|(.*)$", link, re.S)
    if m:
        link, label = m.group(1), m.group(2)
    else:
        label = link + ("" if kind == "none" else " (" + kind + ")")
    targets = {
        "none": nlab_url + "nlab/show/%s",
        "google": "https://www.google.com/search?q=%s",
        "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search=%s",
        "publications": nlab_url + "publications/published/%s",
    }
    url = targets.get(kind, nlab_url + kind + "/show/%s")
    return url.replace("%s", urllib.parse.quote(link, safe="")), label


def resolve_url(url, nlab_url, page_url):
    """The absolute URL of a link target in the comment of an edit of the page at page_url.
    Relative ones are mostly page names ("adjoint+functor#InTermsOfHomIsomorphism"); nLab paths
    without the leading slash, DOIs, bare domain names and absolute URLs with junk around them
    are taken as meant, as in the nForum -> Zulip converter."""
    url = re.sub(r"[\t\n\r]", "", url.strip())
    if not url or SCHEME_RE.match(url):
        return url
    m = EMBEDDED_URL_RE.search(url)
    if m:
        return m.group(0)
    if NLAB_PATH_RE.match(url):
        return nlab_url + url[1:] if url.startswith("/") else nlab_url + url
    if DOI_RE.match(url):
        return "https://doi.org/" + url
    if DOMAIN_RE.match(url):
        return "http://" + url
    return urllib.parse.urljoin(page_url, url.replace(" ", "+"))


def to_zulip_markdown(text, nlab_url, page_url=None):
    """Zulip Markdown for a MarkdownItex comment. nlab_url ends with '/'; page_url is the edited
    page's (relative links are relative to it), by default the nLab web's HomePage."""
    page_url = page_url or nlab_url + "nlab/show/HomePage"
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    stash = []

    def put(value):
        stash.append(value)
        return "QQ%dQQ" % (len(stash) - 1)

    text = FENCED_CODE_RE.sub(lambda m: put(m.group(0)), text)
    text = CODE_SPAN_RE.sub(lambda m: put(m.group(0)), text)

    text = BLOCK_MATH_RE.sub(
        lambda m: "\n\n" + put(
            "```math\n" + itex_to_katex(m.group(1)).strip() + "\n```") + "\n\n",
        text)
    text = INLINE_MATH_RE.sub(
        lambda m: put("$$" + " ".join(itex_to_katex(m.group(1)).split()) + "$$"),
        text)
    text = text.replace("\\$", put("$"))

    def wikilink(m):
        url, label = _wikilink(m.group(1), nlab_url)
        return put("[%s](%s)" % (label, url))

    text = WIKILINK_RE.sub(wikilink, text)
    for pattern in MD_LINK_TARGET_RES:
        text = pattern.sub(lambda m: m.group(1) + resolve_url(m.group(2), nlab_url, page_url), text)
    text = HTML_LINK_RE.sub(lambda m: "[%s](%s)" % (m.group(2), resolve_url(m.group(1), nlab_url, page_url)), text)
    text = MENTION_RE.sub("@_", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Placeholders can be nested (a wikilink label may contain math).
    for _ in range(3):
        text = PLACEHOLDER_RE.sub(lambda m: stash[int(m.group(1))], text)
    return text.strip()
