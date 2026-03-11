from __future__ import annotations

from html.parser import HTMLParser
from urllib.request import Request, urlopen


USER_AGENT = "personal-agent/0.1"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._inside_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._inside_title = True
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._inside_title = False
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._inside_title:
            self._title_parts.append(value)
        if self._skip_depth == 0:
            self._text_parts.append(value)

    @property
    def title(self) -> str:
        return " ".join(self._title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self._text_parts).strip()


def fetch_url_capture(url: str, timeout: int = 15) -> dict[str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        charset = response.headers.get_content_charset() or "utf-8"

    text_body = body.decode(charset, errors="replace")

    if "html" not in content_type.lower():
        snippet = text_body.strip()
        return {
            "url": url,
            "content_type": content_type,
            "title": "",
            "text": snippet,
        }

    parser = _HTMLTextExtractor()
    parser.feed(text_body)
    return {
        "url": url,
        "content_type": content_type,
        "title": parser.title,
        "text": parser.text,
    }
