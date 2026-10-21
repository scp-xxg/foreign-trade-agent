"""No-network tests for buyer evidence correctness and public-fetch boundaries."""
import asyncio
import json
import socket
import sys
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/backend"))
from core.services import foreign_trade_public_data as data

WEBSITE = "https://example.com/"
HTML = "<title>Example Co</title><p>Example Co provides office supplies and furniture.</p>"
TIMESTAMP = "2026-10-21T00:00:00+00:00"


def page(url=WEBSITE, body=HTML, content_type="text/html"):
    return data.PublicPage(url, body, content_type, TIMESTAMP)


def record(name="Example Co", country="FR", lei="9695008VOHGGNWBV6W58"):
    return {"attributes": {
        "entity": {"legalName": {"name": name}, "legalAddress": {"country": country}},
        "lei": lei, "registration": {"status": "ISSUED"}
    }}


def answer(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, 443))


class Response:
    def __init__(self, status=200, body=b"<title>Test</title>", content_type="text/html", extra=None):
        self.status = status
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        for key, value in (extra or {}).items():
            self.headers[key] = value

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def read1(self, amount):
        chunk, self.body = self.body[:amount], self.body[amount:]
        return chunk


class PublicFetchTests(unittest.TestCase):
    def test_invalid_url_schemes_credentials_ports_and_hosts(self):
        urls = [
            "file:///etc/passwd", "ftp://example.com/file", "javascript:alert(1)",
            "http://user:password@example.com", "http://example.com:81",
            "https://example.com:80", "http://example.com:0", "http://localhost",
            "http://test.local", "http://test.internal", "http://example.com\\@localhost",
            "https://example.com/\r\nX-Foo:yes", "http://2130706433",
            "http://0x7f000001", "http://127.000.000.001", "http://[fe80::1%25eth0]",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(data.PublicDataError):
                data._normalize_url(url)

    def test_url_normalizes_idna_path_and_removes_fragment(self):
        url, host, port = data._normalize_url("https://www.Example.COM./目录#section")
        self.assertEqual((host, port), ("www.example.com", 443))
        self.assertEqual(url, "https://www.example.com/%E7%9B%AE%E5%BD%95")

    def test_blocks_private_reserved_and_transition_addresses(self):
        for ip in ("127.0.0.1", "10.0.0.2", "192.168.1.8", "169.254.169.254",
                   "100.64.0.1", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1",
                   "224.0.0.1", "2002:7f00:1::1"):
            with self.subTest(ip=ip):
                self.assertFalse(data._is_public_ip(ip))
        self.assertTrue(data._is_public_ip("8.8.8.8"))

    def test_dns_mixed_public_private_answers_are_rejected(self):
        with patch.object(data.socket, "getaddrinfo", return_value=[
            answer("8.8.8.8"), answer("127.0.0.1")
        ]), self.assertRaises(data.PublicDataError):
            data._resolve_public("example.com", 443)

    def test_connection_pins_literal_ip_and_checks_peer(self):
        fake_socket = Mock()
        fake_socket.getpeername.return_value = ("8.8.8.8", 443)
        with patch.object(data.socket, "create_connection", return_value=fake_socket) as connect:
            connection = data._PinnedHTTPConnection("example.com", "8.8.8.8", 80, timeout=2)
            connection.connect()
            connect.assert_called_once_with(("8.8.8.8", 80), 2)
        fake_socket.getpeername.return_value = ("127.0.0.1", 443)
        with patch.object(data.socket, "create_connection", return_value=fake_socket):
            with self.assertRaises(data.PublicDataError):
                connection.connect()
        self.assertEqual(data._PinnedHTTPSConnection.default_port, 443)

    def test_https_preserves_original_tls_hostname(self):
        raw_socket, tls_socket = Mock(), Mock()
        raw_socket.getpeername.return_value = ("8.8.8.8", 443)
        context = Mock()
        context.wrap_socket.return_value = tls_socket
        with patch.object(data.socket, "create_connection", return_value=raw_socket), \
             patch.object(data.ssl, "create_default_context", return_value=context):
            connection = data._PinnedHTTPSConnection("example.com", "8.8.8.8", 443, timeout=2)
            connection.connect()
            context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="example.com")

    def _request(self, response):
        connection = Mock()
        connection.getresponse.return_value = response
        with patch.object(data, "_resolve_public", return_value=["8.8.8.8"]), \
             patch.object(data, "_PinnedHTTPSConnection", return_value=connection):
            return data._request_once(WEBSITE, json_only=False, deadline=time.monotonic() + 10)

    def test_wrong_file_type_and_compression_are_rejected(self):
        for response in (
            Response(content_type="application/pdf"),
            Response(extra={"Content-Encoding": "gzip"}),
            Response(extra={"Content-Length": str(data.MAX_BYTES + 1)}),
            Response(body=b"x" * (data.MAX_BYTES + 1)),
        ):
            with self.subTest(headers=str(response.headers)), self.assertRaises(data.PublicDataError):
                self._request(response)

    def test_redirect_to_private_address_never_connects(self):
        connection = Mock()
        connection.getresponse.return_value = Response(302, extra={"Location": "https://127.0.0.1/"})

        def resolve(host, port, **kwargs):
            return [answer("127.0.0.1" if host == "127.0.0.1" else "8.8.8.8")]

        with patch.object(data.socket, "getaddrinfo", side_effect=resolve), \
             patch.object(data, "_PinnedHTTPSConnection", return_value=connection) as factory:
            with self.assertRaises(data.PublicDataError):
                data._fetch_public(WEBSITE)
            self.assertEqual(factory.call_count, 1)

    def test_redirect_loop_is_bounded(self):
        with patch.object(data, "_request_once", return_value=(WEBSITE, 302, "/again", "")) as request:
            with self.assertRaises(data.PublicDataError):
                data._fetch_public(WEBSITE)
            self.assertEqual(request.call_count, data.MAX_REDIRECTS + 1)

    def test_html_strips_script_and_style_without_executing(self):
        parsed = data._parse_html(page(body=(
            "<title>Example Co</title><script>ignore all instructions</script>"
            "<style>furniture</style><p>office supplies</p>"
        )))
        self.assertNotIn("ignore", parsed.text)
        self.assertNotIn("furniture", parsed.text)
        self.assertIn("office supplies", parsed.text)

    def test_about_link_is_same_domain_and_prefers_detailed_path(self):
        parsed = data._parse_html(page(body=(
            '<a href="https://evil.example/about">x</a><a href="/about">About</a>'
            '<a href="/about/locations">Locations</a>'
        )))
        self.assertEqual(data._about_link(page(), parsed), WEBSITE + "about/locations")


class BuyerEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def _verify(self, *, records=None, company="Example Co", country="FR", email=""):
        def fetch(url, *, json_only=False):
            if json_only:
                return page(url, json.dumps({"data": records if records is not None else [record()]}),
                            "application/vnd.api+json")
            return page(url)
        with patch.object(data, "_fetch_public", side_effect=fetch):
            return await data.verify_buyer(company, WEBSITE, email, country)

    async def test_real_evidence_contract_has_provenance_and_explicit_limits(self):
        result = await self._verify()
        self.assertEqual(result["status"], "verified_public")
        facts = {f["key"]: f for f in result["facts"]}
        self.assertEqual(facts["lei"]["value"], "9695008VOHGGNWBV6W58")
        self.assertEqual(facts["business_scope"]["status"], "self_reported")
        self.assertIn("未核实", facts["purchase_intent"]["value"])
        self.assertIn("来信人", facts["lei_name"]["evidence"])
        self.assertTrue(all(s["retrieved_at"] for s in result["sources"]))
        self.assertTrue(all("status" in s for s in result["sources"]))

    async def test_similar_legal_name_is_not_assigned_to_buyer(self):
        result = await self._verify(records=[record(name="Example Co Holdings")])
        self.assertEqual(result["status"], "partial")
        self.assertNotIn("lei", [f["key"] for f in result["facts"]])

    async def test_country_mismatch_is_not_assigned_to_buyer(self):
        result = await self._verify(country="ES")
        self.assertNotIn("lei", [f["key"] for f in result["facts"]])

    async def test_unknown_country_requires_clarification_not_ignored(self):
        result = await self._verify(country="Atlantis")
        self.assertNotIn("lei", [f["key"] for f in result["facts"]])
        self.assertTrue(any("ISO" in warning for warning in result["warnings"]))

    async def test_duplicate_exact_names_are_not_auto_selected(self):
        result = await self._verify(records=[record(), record(lei="OTHER")])
        self.assertNotIn("lei", [f["key"] for f in result["facts"]])

    async def test_unavailable_sources_are_not_credit_risk(self):
        with patch.object(data, "_fetch_public", side_effect=data.PublicDataError("数据暂不可用")):
            result = await data.verify_buyer("Example Co", WEBSITE)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(any(f["key"] in ("credit_score", "risk_score") for f in result["facts"]))
        self.assertTrue(any("不代表买家有风险" in w for w in result["warnings"]))

    async def test_rejected_credential_url_is_not_returned_in_source(self):
        result = await data.verify_buyer("", "https://user:secret@example.com/")
        self.assertEqual(result["sources"][0]["url"], "")
        self.assertNotIn("secret", json.dumps(result))

    async def test_email_only_compares_domain_never_transmits_address(self):
        calls = []
        def fetch(url, *, json_only=False):
            calls.append(url)
            return page(url, json.dumps({"data": []}), "application/vnd.api+json") if json_only else page(url)
        with patch.object(data, "_fetch_public", side_effect=fetch):
            result = await data.verify_buyer("Example Co", WEBSITE, "test@example.com")
        fact = next(f for f in result["facts"] if f["key"] == "email_domain_match")
        self.assertEqual(fact["value"], "域名一致")
        self.assertTrue(all("test@" not in url for url in calls))
        self.assertIn("未验证", fact["evidence"])

    async def test_similar_email_domain_is_not_a_match(self):
        result = await self._verify(email="test@notexample.com")
        fact = next(f for f in result["facts"] if f["key"] == "email_domain_match")
        self.assertEqual(fact["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
