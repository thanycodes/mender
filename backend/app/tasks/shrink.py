"""Reduce the context space and cost of asking Llama for extraction rules.

Pages are often 300 KB; the model only needs the selector-bearing structure (tags, classes,
ids, data-* attributes) and a few example rows of text. Less input means it fits the model's
context, costs fewer credits and leaves less noise to pick the wrong selector from.
"""

import re

from selectolax.lexbor import LexborHTMLParser, LexborNode

_REMOVED_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "iframe", "template", "link", "meta", "head"}
)
_KEPT_ATTRIBUTES = frozenset(
    {"class", "id", "href", "src", "alt", "title", "role", "aria-label", "itemprop", "type", "name"}
)
_CLASS_TOKEN = re.compile(r"[^ \t\n\f\r]+")
_WHITESPACE = re.compile(r"\s+")
_ATTRIBUTE_LIMIT = 80
_TEXT_LIMIT = 200
_SIBLING_LIMIT = 5


def _shorten(value: str, limit: int) -> str:
    return value[: limit - 1] + "…" if len(value) > limit else value


def _shrink_children(parent: LexborNode) -> list[LexborNode]:
    kept = []
    groups: dict[tuple[str, frozenset[str]], list[LexborNode]] = {}
    previous_text_ends_with_space = False

    # Snapshot the siblings before replacing or deleting any of them.
    for node in list(parent.iter(include_text=True)):
        if node.is_comment_node or node.tag in _REMOVED_TAGS:
            node.decompose()
        elif node.is_text_node:
            original = node.text_content
            text = _WHITESPACE.sub(" ", original)
            if previous_text_ends_with_space:
                text = text.lstrip(" ")
            text = _shorten(text, _TEXT_LIMIT)
            if text != original:
                node.replace_with(text)
            if text:
                previous_text_ends_with_space = text.endswith(" ")
        elif node.is_element_node:
            classes = frozenset(_CLASS_TOKEN.findall(node.attrs.get("class") or ""))
            group = groups.setdefault((node.tag, classes), [])
            group.append(node)
            if len(group) <= _SIBLING_LIMIT:
                kept.append(node)
                for name, value in node.attributes.items():
                    if name not in _KEPT_ATTRIBUTES and not name.startswith("data-"):
                        del node.attrs[name]
                    elif value is not None and len(value) > _ATTRIBUTE_LIMIT:
                        node.attrs[name] = _shorten(value, _ATTRIBUTE_LIMIT)
            if len(group) <= _SIBLING_LIMIT + 1:
                previous_text_ends_with_space = False

    for group in groups.values():
        omitted = group[_SIBLING_LIMIT:]
        if omitted:
            marker = LexborHTMLParser(
                f"<body><!-- … {len(omitted)} more similar elements omitted --></body>"
            )
            omitted[0].replace_with(marker.body.child)
            for node in omitted[1:]:
                node.decompose()

    return kept


def shrink_html(html: str, max_chars: int = 30_000) -> str:
    """Keep a compact HTML sample for selector generation.

    Lexbor parses any string the way a browser would, so there is no "invalid HTML" case to
    handle. Unexpected errors are bugs and should surface, not become an empty prompt.
    """
    document = LexborHTMLParser(html)
    container = document.body or document.root.parent
    pending = [container]
    while pending:
        pending.extend(_shrink_children(pending.pop()))

    result = container.inner_html.strip()
    limit = max(0, max_chars)
    if len(result) > limit:
        return result[:limit] + "<!-- truncated -->"
    return result
