"""Pruebas de web_search y fetch_url (documentación en Internet, bloqueo SSRF y auto-reparación)."""

from __future__ import annotations

import httpx
import pytest

from agente_ia.tools import READ_TOOLS, parse_xml_tool_calls
from agente_ia.web_research import _assert_public_url, fetch_url, html_to_text, parse_ddg_html, web_search
from agente_ia.workspace import WorkspaceError


def test_parse_web_research_tools():
    assert "web_search" in READ_TOOLS and "fetch_url" in READ_TOOLS
    _, c1 = parse_xml_tool_calls('<tool_call>{"name": "web_search", "arguments": {"query": "PySide6 QMainWindow QSS"}}</tool_call>')
    assert len(c1) == 1 and c1[0]["name"] == "web_search"
    _, c2 = parse_xml_tool_calls('{"name": "fetch_url", "arguments": {"url": "https://docs.python.org/3/"}}')
    assert len(c2) == 1 and c2[0]["name"] == "fetch_url"


def test_ssrf_blocks_localhost_private_and_non_http():
    for bad in (
        "file:///C:/Windows/win.ini",
        "http://localhost:8080/secret",
        "http://127.0.0.1/admin",
        "http://192.168.1.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
    ):
        with pytest.raises(WorkspaceError):
            _assert_public_url(bad)


def test_web_search_and_fetch_url_parse_cleanly():
    sample_ddg = (
        '<html><body>'
        '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fsqlite3.html">sqlite3 — DB-API 2.0</a>'
        '<a class="result__snippet">Documentación oficial de SQLite en Python.</a>'
        '</body></html>'
    )
    rows = parse_ddg_html(sample_ddg, max_results=3)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://docs.python.org/3/library/sqlite3.html"
    assert "SQLite" in rows[0]["snippet"]

    def mock_handler(req: httpx.Request) -> httpx.Response:
        if "duckduckgo.com" in str(req.url):
            return httpx.Response(200, text=sample_ddg, headers={"content-type": "text/html"})
        return httpx.Response(
            200,
            text="<html><head><style>body{}</style><script>alert(1)</script></head><body><h1>Guía Rust</h1><p>Usa Result&lt;T, E&gt;.</p></body></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(mock_handler)
    res_s = web_search("python sqlite3", transport=transport)
    assert res_s["count"] == 1 and "Referencia externa" in res_s["notice"]

    res_f = fetch_url("https://example.org/rust", transport=transport)
    assert "Guía Rust" in res_f["text"] and "alert(1)" not in res_f["text"]
    assert html_to_text("<script>x()</script><p>Hola</p>") == "Hola"
