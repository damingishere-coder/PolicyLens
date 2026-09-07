from __future__ import annotations

import httpx
import pytest

from policylens_api.web_fetcher import FetchError, OfficialSourceFetcher, evidence_matches


def public_resolver(_host: str) -> list[str]:
    return ["8.8.8.8"]


def test_official_html_fetch_checks_robots_and_returns_normalized_text() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", request=request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<!doctype html><html><body><h1>Synthetic Official Plan</h1><p>Payment term is 5 years</p></body></html>",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    fetcher = OfficialSourceFetcher(
        client=client, resolver=public_resolver, sleeper=lambda _seconds: None
    )
    fetched = fetcher.fetch("https://www.aia.com.hk/products/synthetic", "aia-hk")
    assert fetched.host == "www.aia.com.hk"
    assert evidence_matches(fetched.text, "Payment term is 5 years")
    assert [url.rsplit("/", 1)[-1] for url in seen] == ["robots.txt", "synthetic"]


@pytest.mark.parametrize(
    ("url", "insurer", "code"),
    [
        ("http://www.aia.com.hk/product", "aia-hk", "HTTPS_REQUIRED"),
        ("https://user@www.aia.com.hk/product", "aia-hk", "USERINFO_REJECTED"),
        ("https://127.0.0.1/product", "aia-hk", "IP_LITERAL_REJECTED"),
        ("https://example.test/product", "aia-hk", "DOMAIN_REJECTED"),
        ("https://www.aia.com.hk:444/product", "aia-hk", "PORT_REJECTED"),
    ],
)
def test_url_policy_rejects_unsafe_candidates(url: str, insurer: str, code: str) -> None:
    fetcher = OfficialSourceFetcher(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
        ),
        resolver=public_resolver,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(FetchError) as caught:
        fetcher.canonicalize(url, insurer)
    assert caught.value.code == code


def test_dns_private_address_and_cross_domain_redirect_are_rejected() -> None:
    private = OfficialSourceFetcher(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
        ),
        resolver=lambda _host: ["127.0.0.1"],
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(FetchError) as caught:
        private.canonicalize("https://www.aia.com.hk/product", "aia-hk")
    assert caught.value.code == "SSRF_REJECTED"

    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", request=request)
        return httpx.Response(
            302, headers={"location": "https://example.test/private"}, request=request
        )

    fetcher = OfficialSourceFetcher(
        client=httpx.Client(transport=httpx.MockTransport(redirect), trust_env=False),
        resolver=public_resolver,
        sleeper=lambda _seconds: None,
    )
    with pytest.raises(FetchError) as redirected:
        fetcher.fetch("https://www.aia.com.hk/product", "aia-hk")
    assert redirected.value.code == "DOMAIN_REJECTED"
