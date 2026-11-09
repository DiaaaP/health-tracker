"""Validate the static entry point before publishing it to GitHub Pages."""

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


class PageValidator(HTMLParser):
    void_tags = set("area base br col embed hr img input link meta param source track wbr".split())

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tags = Counter()
        self.ids = set()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags[tag] += 1
        if "id" in attrs:
            assert attrs["id"] not in self.ids, f"Duplicate id: {attrs['id']}"
            self.ids.add(attrs["id"])
        if tag == "script" and attrs.get("src"):
            self.assets.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.assets.append(attrs["href"])
        if tag not in self.void_tags:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, f"Unexpected closing tag: {tag}"
        self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void_tags:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if data.strip():
            assert self.stack and self.stack[-1] not in {"html", "head", "body"}, (
                "Unwrapped text or CSS outside its element"
            )


def validate_frontend():
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    parser = PageValidator()
    parser.feed((frontend / "index.html").read_text(encoding="utf-8"))
    parser.close()
    assert not parser.stack, f"Unclosed tags: {parser.stack}"
    for tag in ("html", "head", "body"):
        assert parser.tags[tag] == 1, f"Expected one {tag} element"
    assert parser.assets, "Missing application assets"
    for asset in parser.assets:
        assert (frontend / asset.split("?")[0]).is_file(), f"Missing asset: {asset}"
    print("Frontend HTML and assets validated")


if __name__ == "__main__":
    validate_frontend()
