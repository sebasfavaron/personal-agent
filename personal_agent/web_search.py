from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "personal-agent/0.1"
SEARCH_URL_TEMPLATE = "https://html.duckduckgo.com/html/?q={query}"


class _DuckDuckGoResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current_href = ""
        self._capture_link_text = False
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_map = dict(attrs)
        class_name = attrs_map.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._current_href = attrs_map.get("href", "")
            self._capture_link_text = True
            self._text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_link_text:
            title = " ".join(part for part in self._text_parts if part).strip()
            if self._current_href and title:
                self.results.append(
                    {
                        "title": title,
                        "url": self._current_href,
                        "domain": urlparse(self._current_href).netloc,
                    }
                )
            self._current_href = ""
            self._capture_link_text = False
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if not self._capture_link_text:
            return
        value = " ".join(data.split())
        if value:
            self._text_parts.append(value)


def parse_duckduckgo_html(html: str) -> list[dict[str, str]]:
    parser = _DuckDuckGoResultsParser()
    parser.feed(html)
    return parser.results


def search_web(query: str, max_results: int = 5, timeout: int = 15) -> dict[str, object]:
    request_url = SEARCH_URL_TEMPLATE.format(query=quote_plus(query))
    request = Request(request_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        charset = response.headers.get_content_charset() or "utf-8"

    html = body.decode(charset, errors="replace")
    results = parse_duckduckgo_html(html)[:max_results]
    return {
        "query": query,
        "engine": "duckduckgo_html",
        "results": results,
        "raw_result_count": len(results),
        "request_url": request_url,
        "raw_payload": json.dumps(results, sort_keys=True),
    }
