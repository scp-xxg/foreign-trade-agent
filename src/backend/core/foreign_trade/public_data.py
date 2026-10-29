"""Bounded source-linked public buyer evidence, never credit/purchase-intent scoring.

Website content is untrusted data and is not proof of website ownership. Direct
HTTP connections pin previously validated public IPs and retain original
Host/TLS names; there is no second hostname lookup or environment proxy.
"""
from __future__ import annotations

import asyncio
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
REQUEST_SECONDS = 12
USER_AGENT = "ForeignTradeAgent/0.1 (public company fact verification)"
GLEIF_BASE = "https://api.gleif.org/api/v1/lei-records"
BOUNDARY = "公开页面内容为网站自述；登记名称匹配仍不能验证网站、来信人与该法人关系，不是信用评级或采购意向证明；抓取失败不代表买家有风险。"


class PublicDataError(ValueError):
    """Unavailable/rejected public source, safe to show without internals."""


@dataclass(frozen=True)
class PublicPage:
    url: str
    body: str
    content_type: str
    retrieved_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_url(url: str) -> tuple[str, str, int]:
    if not isinstance(url, str) or len(url) > 2048 or not url.strip():
        raise PublicDataError("请提供有效的公开网站 URL。")
    url = url.strip()
    if re.search(r"[\x00-\x20\x7f\\]", url):
        raise PublicDataError("网站 URL 含不允许的字符。")
    try:
        part = urlsplit(url)
        if part.scheme not in ("http", "https") or not part.hostname:
            raise PublicDataError("仅支持 http/https 公开网站。")
        if part.username is not None or part.password is not None:
            raise PublicDataError("网站 URL 不得包含账号或密码。")
        host = part.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = part.port if part.port is not None else (443 if part.scheme == "https" else 80)
        if port != (443 if part.scheme == "https" else 80):
            raise PublicDataError("仅允许网站标准 HTTP/HTTPS 端口。")
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, PublicDataError):
            raise
        raise PublicDataError("网站 URL 格式无效。") from None
    if (host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
            or "%" in host or not re.fullmatch(r"[a-z0-9.:\-]+", host)):
        raise PublicDataError("仅允许可公开访问的网站域名。")
    if ":" not in host and re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+))*", host):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            raise PublicDataError("不支持非标准 IP 地址写法。") from None
    authority = "[" + host + "]" if ":" in host else host
    normalized = urlunsplit((
        part.scheme, authority, quote(part.path or "/", safe="/%:@!$&'()*+,;=-._~"),
        quote(part.query, safe="=&%/:@!$'()*+,;?-._~"), ""
    ))
    return normalized, host, port


def _is_public_ip(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(value, ipaddress.IPv6Address) and value.ipv4_mapped:
        return _is_public_ip(str(value.ipv4_mapped))
    if isinstance(value, ipaddress.IPv6Address) and (value.sixtofour or value.teredo):
        return False
    return bool(value.is_global and not value.is_multicast and not value.is_reserved)


def _resolve_public(host: str, port: int) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise PublicDataError("公开网站 DNS 暂时无法解析。") from None
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise PublicDataError("网站解析包含非公网地址，已拒绝访问。")
    return addresses


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, *, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._public_ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._public_ip, self.port), self.timeout)
        if not _is_public_ip(self.sock.getpeername()[0]):
            self.sock.close()
            raise PublicDataError("连接目标不是公网地址。")


class _PinnedHTTPSConnection(_PinnedHTTPConnection):
    default_port = 443

    def connect(self):
        super().connect()
        try:
            self.sock = ssl.create_default_context().wrap_socket(
                self.sock, server_hostname=self.host
            )
        except Exception:
            self.sock.close()
            raise


def _request_once(url: str, *, json_only: bool, deadline: float):
    normalized, host, port = _normalize_url(url)
    addresses = _resolve_public(host, port)
    part = urlsplit(normalized)
    connection_class = _PinnedHTTPSConnection if part.scheme == "https" else _PinnedHTTPConnection
    last_error = None
    for address in addresses[:2]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublicDataError("公开数据源请求超时。")
        connection = connection_class(host, address, port, timeout=min(remaining, 6.0))
        try:
            connection.request(
                "GET", urlunsplit(("", "", part.path, part.query, "")),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json, application/vnd.api+json" if json_only
                    else "text/html, application/xhtml+xml",
                    "Accept-Encoding": "identity", "Connection": "close",
                },
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                return normalized, response.status, response.getheader("Location", ""), ""
            if response.status != 200:
                raise PublicDataError(f"公开数据源返回 HTTP {response.status}，暂未取得内容。")
            content_type = response.getheader("Content-Type", "").split(";")[0].strip().lower()
            allowed = ("application/json", "application/vnd.api+json") if json_only else (
                "text/html", "application/xhtml+xml"
            )
            if content_type not in allowed:
                raise PublicDataError("公开数据源返回的文件类型不受支持。")
            if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise PublicDataError("公开数据源返回压缩内容，未继续处理。")
            try:
                declared = int(response.getheader("Content-Length", "0"))
            except ValueError:
                declared = 0
            if declared > MAX_BYTES:
                raise PublicDataError("公开页面过大，已停止读取。")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PublicDataError("公开数据源请求超时。")
                if connection.sock:
                    connection.sock.settimeout(min(remaining, 6.0))
                block = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not block:
                    break
                chunks.append(block)
                size += len(block)
                if size > MAX_BYTES:
                    raise PublicDataError("公开页面过大，已停止读取。")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                body = b"".join(chunks).decode(charset, errors="replace")
            except LookupError:
                body = b"".join(chunks).decode("utf-8", errors="replace")
            return normalized, 200, content_type, body
        except PublicDataError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            connection.close()
    raise PublicDataError("公开网站连接失败或超时；尚不能核验。") from last_error


def _fetch_public(url: str, *, json_only: bool = False) -> PublicPage:
    deadline = time.monotonic() + REQUEST_SECONDS
    current = url
    for hop in range(MAX_REDIRECTS + 1):
        final_url, status, detail, body = _request_once(
            current, json_only=json_only, deadline=deadline
        )
        if status == 200:
            return PublicPage(final_url, body, detail, _now())
        if hop >= MAX_REDIRECTS or not detail:
            raise PublicDataError("公开页面重定向次数过多或缺少目标。")
        current = urljoin(final_url, detail)
    raise PublicDataError("无法取得公开页面。")


class _CompanyHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts = []
        self.title_parts = []
        self.links = []
        self._skip = 0
        self._title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._skip += 1
        if self._skip:
            return
        if tag == "title":
            self._title = True
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "template"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._title = False

    def handle_data(self, data):
        if not self._skip:
            clean = re.sub(r"\s+", " ", data).strip()
            if clean:
                self.text_parts.append(clean)
                if self._title:
                    self.title_parts.append(clean)

    @property
    def text(self):
        return " ".join(self.text_parts)

    @property
    def title(self):
        return " ".join(self.title_parts)[:160]


def _parse_html(page: PublicPage) -> _CompanyHTML:
    parser = _CompanyHTML()
    parser.feed(page.body)
    parser.close()
    return parser


def _normalized_name(value: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


def _fact(key, label, value, status, source_url="", evidence=""):
    return dict(key=key, label=label, value=value, status=status,
                source_url=source_url, evidence=evidence[:150])


def _source(page: PublicPage, title: str) -> dict:
    return dict(url=page.url, title=title or "公开资料", retrieved_at=page.retrieved_at,
                status="retrieved")


def _about_link(page: PublicPage, parser: _CompanyHTML) -> str | None:
    origin = urlsplit(page.url)
    for href in sorted(parser.links, key=lambda href: bool(re.search(r"/about/.", href)), reverse=True):
        candidate = urljoin(page.url, href)
        parts = urlsplit(candidate)
        if (parts.hostname == origin.hostname and candidate.rstrip("/") != page.url.rstrip("/")
                and re.search(r"/(about|about-us|company|who-we-are)(/|-|$)", parts.path, re.I)):
            return candidate
    return None


def _website_facts(company_name: str, page: PublicPage, parser: _CompanyHTML) -> list[dict]:
    facts = [
        _fact("website_access", "公开网站访问", page.url, "verified", page.url,
              "已实时读取公开页面；该网址由用户提供，尚未独立确认网站归属。"),
    ]
    requested_name = _normalized_name(company_name)
    named = bool(requested_name and requested_name in _normalized_name(parser.text))
    facts.append(_fact(
        "website_name", "公司名称与页面", "页面提及所填公司名称" if named else "未发现完整名称，需人工核对",
        "self_reported" if named else "unverified", page.url, company_name if named else ""
    ))
    categories = (
        (r"\boffice supplies\b|\boffice products\b|\bstationery\b", "办公用品"),
        (r"\bfurniture\b", "家具"), (r"\bit equipment\b|\belectronics\b", "IT 设备"),
        (r"\bpersonal protective equipment\b|\bppe\b", "个人防护用品"),
        (r"\bpackaging\b", "包装用品"), (r"\bhygiene\b|\bcleaning\b", "清洁卫生用品"),
    )
    matched = [(re.search(pattern, parser.text, re.I), label) for pattern, label in categories]
    found = [label for match, label in matched if match]
    terms = [match.group(0) for match, _ in matched if match]
    if found:
        facts.append(_fact(
            "business_scope", "网站提及品类", "、".join(found), "self_reported", page.url,
            "页面词条：" + " / ".join(terms)
        ))
    return facts


async def _verify_website(company_name: str, website: str) -> tuple[list, list, list]:
    if not website:
        return [], [], ["未提供公司官网，网站信息待核验。"]
    try:
        page = await asyncio.wait_for(
            asyncio.to_thread(_fetch_public, website), REQUEST_SECONDS + 2
        )
        parser = _parse_html(page)
        facts = _website_facts(company_name, page, parser)
        sources = [_source(page, parser.title)]
        warnings = []
        about = _about_link(page, parser)
        if about:
            try:
                detail = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_public, about), REQUEST_SECONDS + 2
                )
                detail_parser = _parse_html(detail)
                if detail.url == page.url:
                    return facts, sources, warnings
                if urlsplit(detail.url).hostname != urlsplit(page.url).hostname:
                    warnings.append("公司介绍链接跳转至其他域名，未作为同域资料采用。")
                    return facts, sources, warnings
                sources.append(_source(detail, detail_parser.title))
                facts.append(_fact(
                    "company_profile", "公司介绍页", detail_parser.title or "公司介绍",
                    "self_reported", detail.url, "同域公司介绍页已读取；原文可点击核对。"
                ))
                if not any(f["key"] == "business_scope" for f in facts):
                    facts.extend(f for f in _website_facts(company_name, detail, detail_parser)
                                 if f["key"] == "business_scope")
            except (PublicDataError, TimeoutError):
                warnings.append("官网可访问，补充公司介绍页暂未取得。")
        return facts, sources, warnings
    except (PublicDataError, ValueError, TimeoutError) as exc:
        try:
            safe_url = _normalize_url(website)[0]
        except PublicDataError:
            safe_url = ""
        return [], [dict(url=safe_url, title="用户提供的网站",
                        retrieved_at=_now(), status="unavailable")], [str(exc) or "公开网站请求超时，暂未核验。"]


def _country_code(country: str) -> str:
    aliases = {
        "france": "FR", "法国": "FR", "spain": "ES", "西班牙": "ES",
        "germany": "DE", "德国": "DE", "united kingdom": "GB", "英国": "GB",
        "united states": "US", "美国": "US", "china": "CN", "中国": "CN",
        "belgium": "BE", "比利时": "BE", "netherlands": "NL", "荷兰": "NL",
    }
    clean = country.strip()
    return clean.upper() if re.fullmatch("[A-Za-z]{2}", clean) else aliases.get(clean.lower(), "")


async def _verify_lei(company_name: str, country: str) -> tuple[list, list, list]:
    if len(company_name.strip()) < 3:
        return [], [], ["完整法人名称不足，未查询 GLEIF。"]
    url = GLEIF_BASE + "?" + urlencode({
        "filter[entity.legalName]": company_name.strip()[:200], "page[size]": "5"
    })
    try:
        page = await asyncio.wait_for(
            asyncio.to_thread(_fetch_public, url, json_only=True), REQUEST_SECONDS + 2
        )
        if urlsplit(page.url).hostname != "api.gleif.org":
            raise PublicDataError("GLEIF 请求跳转至其他来源，未采用。")
        payload = json.loads(page.body)
        records = payload.get("data", []) if isinstance(payload, dict) else []
        exact = []
        expected = _normalized_name(company_name)
        country_code = _country_code(country)
        if country and not country_code:
            return [], [_source(page, "GLEIF 官方 LEI 法人名称检索")], [
                "注册国无法识别，请填写两位 ISO 国家代码后再核对法人记录。"
            ]
        for record in records if isinstance(records, list) else []:
            attributes = record.get("attributes", {})
            entity = attributes.get("entity", {})
            legal_name = entity.get("legalName", {}).get("name", "")
            legal_country = entity.get("legalAddress", {}).get("country", "")
            if (_normalized_name(legal_name) == expected
                    and (not country_code or country_code == legal_country)):
                exact.append((attributes, legal_name, legal_country))
        sources = [_source(page, "GLEIF 官方 LEI 法人名称检索")]
        if len(exact) != 1:
            return [_fact(
                "lei_match", "GLEIF 法人记录", "未找到唯一精确匹配，待补充法人全称与注册国",
                "unverified", url, "无记录或名称相似都不能用于认定该公司不存在或存在信用风险。"
            )], sources, ["GLEIF 只覆盖已取得 LEI 的法人；未匹配不能解释为买家有风险。"]
        attributes, legal_name, legal_country = exact[0]
        lei = str(attributes.get("lei", ""))
        record_url = GLEIF_BASE + "/" + quote(lei, safe="") if lei else url
        facts = [
            _fact("lei_name", "GLEIF 同名法人", legal_name, "registry_match", record_url,
                  "名称/国别匹配的登记记录；尚未验证网站、来信人与该法人关系。"),
            _fact("lei_country", "法人登记国家", legal_country, "registry_match", record_url),
            _fact("lei", "LEI 标识", lei, "registry_match", record_url),
            _fact("lei_status", "LEI 登记状态",
                  attributes.get("registration", {}).get("status", "未提供"),
                  "registry_match", record_url,
                  "此状态仅为 LEI 登记状态，不是信用评级或付款能力证明。"),
        ]
        return facts, sources, []
    except (PublicDataError, ValueError, KeyError, TypeError, AttributeError, TimeoutError):
        return [], [dict(url=url, title="GLEIF 官方 LEI 法人名称检索",
                        retrieved_at=_now(), status="unavailable")], [
            "GLEIF 官方接口暂未取得可核验结果；不据此判断公司风险。"
        ]


async def verify_buyer(company_name: str, website: str, email: str = "", country: str = "") -> dict:
    """Read public evidence and gaps. Country is registration, not destination.

    Email is compared only as user-supplied data and never sent to a service.
    """
    company_name = str(company_name or "").strip()[:200]
    website = str(website or "").strip()[:2048]
    email = str(email or "").strip()[:320]
    country = str(country or "").strip()[:80]
    website_result, lei_result = await asyncio.gather(
        _verify_website(company_name, website), _verify_lei(company_name, country)
    )
    facts = website_result[0] + lei_result[0]
    sources = website_result[1] + lei_result[1]
    warnings = website_result[2] + lei_result[2] + [BOUNDARY]
    if country:
        facts.append(_fact("provided_country", "用户填写的买家注册国", country, "user_provided"))
    if email:
        try:
            _, host, _ = _normalize_url(website)
            domain = email.rsplit("@", 1)[1].encode("idna").decode("ascii").lower().rstrip(".")
            base_host = host.removeprefix("www.")
            if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
                raise ValueError
            matched = domain == base_host or domain.endswith("." + base_host)
            facts.append(_fact(
                "email_domain_match", "所填邮箱与网站域名",
                "域名一致" if matched else "域名不一致，需进一步确认",
                "verified" if matched else "unverified", "",
                "仅比较输入的域名字符串，未验证邮箱所有权或联系人身份。"
            ))
        except (PublicDataError, ValueError, IndexError, UnicodeError):
            facts.append(_fact("email_domain_match", "所填邮箱与网站域名",
                               "输入不完整，待核验", "unverified"))
    facts.append(_fact("purchase_intent", "采购意愿与交易关系",
                       "未核实；公开资料不能证明对方发起了本次询盘", "unverified"))
    got_website = any(f["key"] == "website_access" for f in facts)
    got_lei = any(f["key"] == "lei" for f in facts)
    status = "verified_public" if got_website and got_lei else "partial" if (
        got_website or got_lei
    ) else "unavailable"
    return dict(status=status, checked_at=_now(), facts=facts, sources=sources, warnings=warnings)
