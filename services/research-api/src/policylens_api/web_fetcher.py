from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from pypdf import PdfReader

MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_ROBOTS_BYTES = 256 * 1024
MAX_REDIRECTS = 4
USER_AGENT = "PolicyLensPublicResearch/0.2 (+local evidence verifier)"

OFFICIAL_HOSTS: dict[str, frozenset[str]] = {
    "aia-hk": frozenset({"aia.com.hk", "www.aia.com.hk"}),
    "prudential-hk": frozenset({"prudential.com.hk", "www.prudential.com.hk"}),
    "manulife-hk": frozenset({"manulife.com.hk", "www.manulife.com.hk"}),
}


class FetchError(RuntimeError):
    def __init__(self, message: str, code: str = "FETCH_REJECTED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FetchedSource:
    canonical_url: str
    host: str
    status_code: int
    content_type: str
    content: bytes
    text: str
    sha256: str
    page_count: int | None
    etag: str | None
    last_modified: str | None


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._blocked = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "template"}:
            self._blocked += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "template"} and self._blocked:
            self._blocked -= 1

    def handle_data(self, data: str) -> None:
        if not self._blocked and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def normalize_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\u00ad", "")
    return " ".join(normalized.split()).casefold()


def evidence_matches(source_text: str, excerpt: str) -> bool:
    needle = normalize_evidence(excerpt)
    return len(needle) >= 12 and needle in normalize_evidence(source_text)


class OfficialSourceFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Callable[[str], list[str]] | None = None,
        dns_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._resolved: dict[str, list[str]] = {}
        self._dns_client = dns_client
        self.client = client or httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9"},
            trust_env=False,
            limits=httpx.Limits(max_keepalive_connections=0),
            event_hooks={"request": [self._pin_request]},
        )
        self._owns_client = client is None
        self.resolver = resolver or self._resolve
        self.sleeper = sleeper
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}

    def _resolve(self, host: str) -> list[str]:
        try:
            addresses = sorted(
                {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
            )
        except OSError as exc:
            raise FetchError("官方域名 DNS 解析失败。", "DNS_FAILED") from exc
        # TUN resolvers may return benchmark/ULA placeholders instead of routable IPs.
        # Never allow those addresses through; obtain a public address over verified TLS.
        fake_ranges = (
            ipaddress.ip_network("198.18.0.0/15"),
            ipaddress.ip_network("fdfe:dcba:9876::/48"),
        )
        if addresses and all(
            any(ipaddress.ip_address(address) in network for network in fake_ranges)
            for address in addresses
        ):
            if host not in {host for hosts in OFFICIAL_HOSTS.values() for host in hosts}:
                raise FetchError("仅允许解析预置官方域名。", "DOMAIN_REJECTED")
            owned = self._dns_client is None
            client = self._dns_client or httpx.Client(
                timeout=10, trust_env=False, follow_redirects=False
            )
            try:
                with client.stream(
                    "GET",
                    "https://1.1.1.1/dns-query",
                    params={"name": host, "type": "A"},
                    headers={"Accept": "application/dns-json"},
                ) as response:
                    if response.status_code != 200:
                        raise FetchError("安全 DNS 查询失败。", "DNS_FAILED")
                    data = json.loads(self._read_response(response, 65_536))
                if not isinstance(data, dict) or data.get("Status") != 0:
                    raise FetchError("安全 DNS 没有返回可用地址。", "DNS_FAILED")
                answers = data.get("Answer", [])
                if not isinstance(answers, list) or any(
                    not isinstance(item, dict) for item in answers
                ):
                    raise FetchError("安全 DNS 返回格式无效。", "DNS_FAILED")
                addresses = [item["data"] for item in answers if item.get("type") == 1]
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise FetchError("安全 DNS 查询失败。", "DNS_FAILED") from exc
            finally:
                if owned:
                    client.close()
        return addresses

    def _pin_request(self, request: httpx.Request) -> None:
        host = request.url.host
        addresses = self._resolved.get(host)
        if request.url.scheme != "https" or not addresses:
            raise FetchError("请求缺少已验证的官网地址。", "DNS_REJECTED")
        # The actual socket uses the checked IP; Host, SNI and certificate verification
        # continue to use the official domain. No second system DNS lookup is needed.
        request.headers["Host"] = host
        request.extensions["sni_hostname"] = host
        request.url = request.url.copy_with(host=addresses[0])

    def canonicalize(self, url: str, insurer_id: str) -> str:
        try:
            parsed = urlsplit(url.strip())
            port = parsed.port
        except ValueError as exc:
            raise FetchError("候选 URL 无效。", "INVALID_URL") from exc
        host = (parsed.hostname or "").rstrip(".").lower()
        if parsed.scheme.lower() != "https":
            raise FetchError("官方来源只允许 HTTPS。", "HTTPS_REQUIRED")
        if parsed.username or parsed.password:
            raise FetchError("官方来源 URL 不允许包含用户信息。", "USERINFO_REJECTED")
        if port not in {None, 443}:
            raise FetchError("官方来源只允许标准 HTTPS 端口。", "PORT_REJECTED")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise FetchError("官方来源不允许使用 IP 字面量。", "IP_LITERAL_REJECTED")
        if insurer_id not in OFFICIAL_HOSTS or host not in OFFICIAL_HOSTS[insurer_id]:
            raise FetchError("候选 URL 不属于已核验的保险公司官方域名。", "DOMAIN_REJECTED")
        addresses = self.resolver(host)
        if not addresses:
            raise FetchError("官方域名没有可用地址。", "DNS_FAILED")
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise FetchError("DNS 返回了无效地址。", "DNS_REJECTED") from exc
            if not ip.is_global:
                raise FetchError("DNS 指向非公网地址，已拒绝访问。", "SSRF_REJECTED")
        self._resolved[host] = addresses
        path = parsed.path or "/"
        return urlunsplit(("https", host, path, parsed.query, ""))

    def _throttle(self, host: str) -> None:
        now = time.monotonic()
        wait = 1.0 - (now - self._last_request.get(host, 0.0))
        if wait > 0:
            self.sleeper(wait)
        self._last_request[host] = time.monotonic()

    def _read_response(self, response: httpx.Response, maximum: int) -> bytes:
        declared = response.headers.get("content-length")
        if declared:
            try:
                if int(declared) > maximum:
                    raise FetchError("官方来源超过大小上限。", "SOURCE_TOO_LARGE")
            except ValueError as exc:
                raise FetchError("官方来源 Content-Length 无效。", "INVALID_RESPONSE") from exc
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > maximum:
                raise FetchError("官方来源超过大小上限。", "SOURCE_TOO_LARGE")
            chunks.append(chunk)
        return b"".join(chunks)

    def _request(
        self, url: str, insurer_id: str, maximum: int
    ) -> tuple[str, httpx.Response, bytes]:
        current = self.canonicalize(url, insurer_id)
        for redirect_count in range(MAX_REDIRECTS + 1):
            host = urlsplit(current).hostname or ""
            for attempt in range(3):
                self._throttle(host)
                try:
                    request = self.client.build_request(
                        "GET",
                        current,
                        headers={
                            "User-Agent": USER_AGENT,
                            "Accept": "text/html,application/pdf;q=0.9",
                        },
                    )
                    response = self.client.send(request, stream=True)
                except httpx.TimeoutException as exc:
                    if attempt == 2:
                        raise FetchError("官方来源请求超时。", "FETCH_TIMEOUT") from exc
                    continue
                except httpx.RequestError as exc:
                    if attempt == 2:
                        raise FetchError("官方来源网络请求失败。", "FETCH_NETWORK_ERROR") from exc
                    continue
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    response.close()
                    if attempt == 2:
                        raise FetchError("官方来源暂时不可用。", "UPSTREAM_RETRY_EXHAUSTED")
                    retry_after = response.headers.get("retry-after", "1")
                    self.sleeper(min(float(retry_after) if retry_after.isdigit() else 1.0, 5.0))
                    continue
                break
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise FetchError("官方来源重定向缺少目标。", "INVALID_REDIRECT")
                if redirect_count == MAX_REDIRECTS:
                    raise FetchError("官方来源重定向次数过多。", "TOO_MANY_REDIRECTS")
                current = self.canonicalize(urljoin(current, location), insurer_id)
                continue
            try:
                content = self._read_response(response, maximum)
            finally:
                response.close()
            return current, response, content
        raise FetchError("官方来源重定向次数过多。", "TOO_MANY_REDIRECTS")

    def _check_robots(self, canonical_url: str, insurer_id: str) -> None:
        host = urlsplit(canonical_url).hostname or ""
        parser = self._robots.get(host)
        if parser is None:
            robots_url = f"https://{host}/robots.txt"
            final_url, response, content = self._request(robots_url, insurer_id, MAX_ROBOTS_BYTES)
            if response.status_code == 404:
                parser = RobotFileParser()
                parser.parse([])
            elif response.status_code == 200:
                parser = RobotFileParser(final_url)
                parser.parse(content.decode("utf-8", errors="replace").splitlines())
            else:
                raise FetchError("无法确认官方站点 robots 规则。", "ROBOTS_UNAVAILABLE")
            self._robots[host] = parser
        if not parser.can_fetch(USER_AGENT, canonical_url):
            raise FetchError("官方站点 robots 规则不允许抓取该页面。", "ROBOTS_DENIED")

    def fetch(self, url: str, insurer_id: str) -> FetchedSource:
        canonical = self.canonicalize(url, insurer_id)
        self._check_robots(canonical, insurer_id)
        final_url, response, content = self._request(canonical, insurer_id, MAX_SOURCE_BYTES)
        if response.status_code != 200:
            raise FetchError(f"官方来源返回 HTTP {response.status_code}。", "UPSTREAM_HTTP_ERROR")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content.startswith(b"%PDF-"):
            if content_type not in {"application/pdf", "application/octet-stream"}:
                raise FetchError("PDF 来源的 Content-Type 不匹配。", "CONTENT_TYPE_REJECTED")
            try:
                reader = PdfReader(BytesIO(content))
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                page_count: int | None = len(reader.pages)
            except Exception as exc:
                raise FetchError("官方 PDF 无法安全解析。", "PDF_PARSE_FAILED") from exc
            if not text.strip():
                raise FetchError("官方 PDF 没有可核对文本。", "PDF_TEXT_MISSING")
        else:
            prefix = content[:2048].lower()
            if content_type not in {"text/html", "application/xhtml+xml"} or not (
                b"<html" in prefix or b"<!doctype html" in prefix
            ):
                raise FetchError("官方来源不是受支持的 HTML 或 PDF。", "CONTENT_TYPE_REJECTED")
            parser = _VisibleTextParser()
            parser.feed(content.decode(response.encoding or "utf-8", errors="replace"))
            text = parser.text()
            page_count = None
            if not text.strip():
                raise FetchError("官方网页没有可核对文本。", "HTML_TEXT_MISSING")
        return FetchedSource(
            canonical_url=final_url,
            host=urlsplit(final_url).hostname or "",
            status_code=response.status_code,
            content_type=content_type,
            content=content,
            text=text[:2_000_000],
            sha256=hashlib.sha256(content).hexdigest(),
            page_count=page_count,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
