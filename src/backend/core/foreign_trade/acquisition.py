"""Evidence-first acquisition stages. No CRM writes, identity claims or outbound contact."""
from __future__ import annotations
import asyncio
import hashlib
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, unquote
from pydantic import Field, StrictInt, field_validator
from core.foreign_trade.buyer_search import StrictModel, SearchInput, assess_rules, domain, buyer_id
from core.foreign_trade.public_data import _fetch_public, _parse_html, verify_buyer, PublicDataError


def now():
    return datetime.now(timezone.utc).isoformat()



class ProfileInput(StrictModel):
    product: str = Field(min_length=1, max_length=500)
    markets: list[str] = Field(default_factory=list, max_length=8)
    buyer_types: list[str] = Field(default_factory=lambda: ['distributor', 'importer'], max_length=8)
    constraints: str = Field(default='', max_length=5000)

    @field_validator('product')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('请填写产品')
        return value.strip()


def draft_profile(req: ProfileInput):
    # A deterministic draft of merchant statements, never invented business facts.
    stamp = now()
    queries = [' '.join(filter(None, [req.product, b, m])) for b in req.buyer_types or ['distributor'] for m in req.markets or ['']][:12]
    return dict(profile_id='profile-' + hashlib.sha256(str(req.model_dump()).encode()).hexdigest()[:16],
                version=1, status='draft', created_at=stamp, product=req.product,
                merchant_statements=req.model_dump(), rules=[], search_plan=[dict(queries=queries)],
                evidence=[dict(type='user_statement', excerpt=req.constraints or req.product, retrieved_at=stamp)],
                unresolved=['请确认买家类型、目标市场及硬性承接条件；自由文本限制尚未转为自动规则。',
                            '采购量、认证适用性、需求与付款能力均未验证。'], evaluation_status='not_evaluated')


class ResearchInput(StrictModel):
    company_name: str = Field(min_length=1, max_length=200)
    website: str = Field(min_length=1, max_length=2048)
    country: str = Field(default='', max_length=80)
    profile: dict | None = None
    excluded_channels: list[str] = Field(default_factory=list, max_length=500)
    max_pages: StrictInt = Field(default=3, ge=1, le=4)

    @field_validator('website')
    @classmethod
    def public_domain(cls, value):
        if not domain(value):
            raise ValueError('请输入有效公开网站')
        return value if '://' in value else 'https://' + value

    @field_validator('profile')
    @classmethod
    def valid_profile(cls, value):
        return SearchInput(profile=value).profile


_slots = asyncio.Semaphore(2)

async def due_diligence(req: ResearchInput, *, verify=None):
    start = time.monotonic()
    async with _slots:
        evidence = await (verify or verify_buyer)(req.company_name, req.website, country=req.country)
    rules, decision = assess_rules((req.profile or {}).get('rules', []), domain(req.website))
    return dict(buyer_id=buyer_id(req.website), dossier_version=now(), profile_id=(req.profile or {}).get('profile_id'),
                profile_version=(req.profile or {}).get('version'), company_name=req.company_name, website=req.website,
                decision='rejected' if decision == 'rejected' else 'needs_review', domain_rule_decision=decision,
                identity_status='unverified', rule_results=rules, evidence=evidence,
                match=dict(known=sum(r['result'] != 'unknown' for r in rules), total=len(rules)),
                evidence_sufficiency=dict(sourced_facts=sum(bool(f.get('source_url')) for f in evidence['facts']), total_facts=len(evidence['facts'])),
                unresolved=['网站与法人归属关系待人工核验', '语义规则、经营规模、采购意向及信用能力待核实'],
                metrics=dict(elapsed_seconds=round(time.monotonic()-start, 2)),
                next_action='review_dossier_before_contact_discovery')


def extract_channels(page, excluded):
    parser = _parse_html(page)
    found = []
    # Explicit mailto links or visible addresses only; no inferred email patterns.
    raw = [(unquote(link[7:]).split('?')[0], link) for link in parser.links if link.lower().startswith('mailto:')]
    raw += [(m.group(), m.group()) for m in re.finditer(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', parser.text)]
    for value, excerpt in raw:
        value = value.strip().lower()
        if not re.fullmatch(r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}', value) or value in excluded:
            continue
        found.append(dict(channel=value, type='email', evidence=excerpt[:400]))
    for link in parser.links:
        absolute = urljoin(page.url, link)
        parsed = urlsplit(absolute)
        if parsed.scheme not in {'https', 'http'} or parsed.username or parsed.password:
            continue
        if domain(absolute) == domain(page.url) and re.search(r'contact|kontakt|联系我们', parsed.path, re.I):
            if absolute.casefold() not in excluded:
                found.append(dict(channel=absolute, type='contact_page', evidence=link[:400]))
    return [dict(**c, source_url=page.url, retrieved_at=page.retrieved_at, status='publicly_listed',
                 person_name=None, role=None, employment_status='unknown', role_status='unknown',
                 deliverability='unknown', company_relationship='website_claim') for c in found]


async def discover_contacts(req: ResearchInput, *, fetch=None):
    start = time.monotonic(); channels = {}; sources = []; warnings = []
    pending = [req.website]; visited = set(); excluded = {c.strip().casefold() for c in req.excluded_channels}
    async def read(url):
        return await asyncio.to_thread(fetch or _fetch_public, url)
    async with _slots:
        try:
            async with asyncio.timeout(45):
                while pending and len(visited) < req.max_pages:
                    url = pending.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)
                    try:
                        page = await read(url)
                        if domain(page.url) != domain(req.website):
                            warnings.append('网页跳转至其他域名，未采用联系人证据。'); continue
                        parsed = _parse_html(page)
                        sources.append(dict(url=page.url, retrieved_at=page.retrieved_at, excerpt=parsed.text[:1200], status='retrieved'))
                        for c in extract_channels(page, excluded):
                            channels.setdefault(c['channel'], c)
                        for link in parsed.links:
                            absolute = urljoin(page.url, link)
                            if domain(absolute) == domain(req.website) and re.search(r'contact|about|team|kontakt', urlsplit(absolute).path, re.I) and absolute not in visited and absolute not in pending:
                                if len(pending) < 12:
                                    pending.append(absolute)
                    except (PublicDataError, ValueError, OSError):
                        sources.append(dict(url=url, retrieved_at=now(), status='unavailable'))
                        warnings.append('页面无法读取，保留缺口。')
        except TimeoutError:
            warnings.append('达到45秒预算，保留已获取渠道。')
    return dict(buyer_id=buyer_id(req.website), checked_at=now(), channels=list(channels.values())[:100], sources=sources,
                warnings=warnings, status='needs_review' if channels else 'no_public_channel',
                unresolved=['当前仅提取公开邮箱与站内联系页；具名采购负责人、职级及在职情况需人工补充。',
                            '公开列出不等于适合营销联系；邮箱归属、可投递性与采购权限未验证。'],
                metrics=dict(pages_attempted=len(visited), pages_read=sum(s['status']=='retrieved' for s in sources),
                             channels_found=min(100,len(channels)), elapsed_seconds=round(time.monotonic()-start,2)))
