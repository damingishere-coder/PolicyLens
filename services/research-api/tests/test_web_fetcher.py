from __future__ import annotations

import socket

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


def test_fake_dns_uses_verified_https_resolution_and_pins_real_request(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.8", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fdfe:dcba:9876::4", 443, 0, 0)),
        ],
    )
    dns_requests = []
    requests = []

    def dns_handler(request):
        dns_requests.append(request)
        assert str(request.url).startswith("https://1.1.1.1/dns-query?")
        assert request.url.params["name"] == "www.prudential.com.hk"
        return httpx.Response(200, json={"Status": 0, "Answer": [{"type": 1, "data": "8.8.8.8"}]})

    def network(_transport, request):
        requests.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "www.prudential.com.hk"
        assert request.extensions["sni_hostname"] == "www.prudential.com.hk"
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html>Official synthetic content for verification</html>",
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", network)
    with httpx.Client(transport=httpx.MockTransport(dns_handler)) as dns:
        fetcher = OfficialSourceFetcher(dns_client=dns, sleeper=lambda _: None)
        try:
            result = fetcher.fetch("https://www.prudential.com.hk/product", "prudential-hk")
            assert result.canonical_url == "https://www.prudential.com.hk/product"
            assert len(requests) == 2
            assert dns_requests
        finally:
            fetcher.close()


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "198.18.0.1", "fdfe:dcba:9876::4"]
)
def test_private_dns_fallback_answers_are_still_rejected(monkeypatch, address) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.8", 443)),
        ],
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"Status": 0, "Answer": [{"type": 1, "data": address}]}
            )
        )
    ) as dns:
        fetcher = OfficialSourceFetcher(dns_client=dns)
        try:
            with pytest.raises(FetchError) as error:
                fetcher.canonicalize("https://www.prudential.com.hk/product", "prudential-hk")
            assert error.value.code == "SSRF_REJECTED"
        finally:
            fetcher.close()


def test_private_system_dns_is_not_overridden_and_dns_redirect_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (
                calls.append(request)
                or httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
            )
        )
    ) as dns:
        fetcher = OfficialSourceFetcher(dns_client=dns)
        try:
            with pytest.raises(FetchError, match="非公网"):
                fetcher.canonicalize("https://www.aia.com.hk/product", "aia-hk")
            assert calls == []
            monkeypatch.setattr(
                socket,
                "getaddrinfo",
                lambda *_args, **_kwargs: [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.8", 443)),
                ],
            )
            with pytest.raises(FetchError) as error:
                fetcher.canonicalize("https://www.aia.com.hk/product", "aia-hk")
            assert error.value.code == "DNS_FAILED"
            assert len(calls) == 1
        finally:
            fetcher.close()


def test_default_transport_revalidates_and_repins_official_redirect(monkeypatch) -> None:
    seen = []
    addresses = {"prudential.com.hk": "8.8.8.8", "www.prudential.com.hk": "1.1.1.1"}

    def network(_transport, request):
        host = request.headers["host"]
        seen.append((host, request.url.host, request.extensions["sni_hostname"]))
        assert request.url.host == addresses[host]
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if host == "prudential.com.hk":
            return httpx.Response(
                302, headers={"location": "https://www.prudential.com.hk/product"}
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html>Official synthetic product</html>",
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", network)
    fetcher = OfficialSourceFetcher(resolver=lambda host: [addresses[host]], sleeper=lambda _: None)
    try:
        result = fetcher.fetch("https://prudential.com.hk/product", "prudential-hk")
        assert result.canonical_url == "https://www.prudential.com.hk/product"
        assert seen[-1] == ("www.prudential.com.hk", "1.1.1.1", "www.prudential.com.hk")
    finally:
        fetcher.close()
