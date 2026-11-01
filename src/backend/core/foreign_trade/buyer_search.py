# Modified by foreign-trade-agent contributors, 2026-10-31.
"""Bounded discovery of public website candidates; no inferred purchase intent."""
from __future__ import annotations
import ipaddress
import hashlib
import asyncio
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any, Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from core.foreign_trade.public_data import PublicDataError, _fetch_public, _parse_html, _normalize_url
from extensions.mcp_servers.internet_search_mcp.impl import SearchService
from extensions.mcp_servers.internet_search_mcp.models import SearchRequest

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SearchInput(StrictModel):
    product_terms: list[str] = Field(default_factory=list, max_length=12)
    buyer_terms: list[str] = Field(default_factory=list, max_length=8)
    markets: list[str] = Field(default_factory=list, max_length=8)
    queries: list[str] = Field(default_factory=list, max_length=12)
    excluded_domains: list[str] = Field(default_factory=list, max_length=500)
    profile: dict[str, Any] | None = None
    target_count: StrictInt = Field(default=10, ge=1, le=50)
    max_queries: StrictInt = Field(default=4, ge=1, le=12)
    max_pages: StrictInt = Field(default=8, ge=0, le=30)
    max_seconds: StrictInt = Field(default=90, ge=5, le=120)

    @field_validator("product_terms", "buyer_terms", "markets", "queries", "excluded_domains")
    @classmethod
    def clean(cls, values):
        if any(not v.strip() or len(v) > 500 for v in values):
            raise ValueError("每项须为 1–500 字符")
        return list(dict.fromkeys(v.strip() for v in values))

    @field_validator("profile")
    @classmethod
    def bounded_profile(cls, value):
        import json
        if value is not None:
            if len(json.dumps(value, ensure_ascii=False)) > 100000:
                raise ValueError("画像不能超过 100000 字符")
            if not isinstance(value.get("rules", []), list) or len(value.get("rules", [])) > 100:
                raise ValueError("rules 须为最多 100 项的数组")
            ids = set()
            for r in value.get("rules", []):
                if (not isinstance(r, dict) or not isinstance(r.get("rule_id"), str)
                    or not r["rule_id"] or r["rule_id"] in ids
                    or r.get("level") not in {"must", "exclude", "should"}):
                    raise ValueError("规则须有唯一 rule_id 及 must/exclude/should 层级")
                if r.get("basis") == "hypothesis" and r["level"] != "should":
                    raise ValueError("假设不能作为硬条件")
                ids.add(r["rule_id"])
            plan=value.get("search_plan", [])
            if not isinstance(plan, list) or any(not isinstance(p, dict) or not isinstance(p.get("queries", []), list)
                or any(not isinstance(q, str) or not q.strip() or len(q)>500 for q in p.get("queries", [])) for p in plan):
                raise ValueError("search_plan 中 queries 须为非空字符串数组")
        return value


def domain(value: str) -> str:
    try:
        url = value if "://" in value else "https://" + value
        _, host, _ = _normalize_url(url)
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global or address.is_multicast or address.is_reserved:
                return ""
        except ValueError:
            pass
        return host.removeprefix("www.")
    except PublicDataError:
        return ""


def buyer_id(website: str) -> str:
    return 'buyer-' + hashlib.sha256(domain(website).encode()).hexdigest()[:20]

def search_available() -> bool:
    from core.config.store.runtime_env import get_runtime_value
    from extensions.mcp_servers.internet_search_mcp.providers import KEY_NAMES
    engine = (get_runtime_value("INTERNET_SEARCH_ENGINE") or "tavily").strip().lower()
    return bool((get_runtime_value(KEY_NAMES[engine]) or "").strip()) if engine in KEY_NAMES else any(
        (get_runtime_value(key) or "").strip() for key in KEY_NAMES.values())


def make_plan(req: SearchInput) -> dict:
    queries = list(req.queries)
    if not queries and req.profile:
        queries = [q.strip() for p in req.profile.get("search_plan", []) for q in p.get("queries", [])]
    if not queries:
        for product in req.product_terms:
            for buyer in req.buyer_terms or ["distributor", "importer"]:
                for market in req.markets or [""]:
                    queries.append(" ".join(filter(None, [product, buyer, market])))
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:req.max_queries]
    if not queries:
        raise ValueError("请提供产品关键词、查询词或包含 search_plan 的客户画像。")
    return {"queries": queries, "search_available": search_available(),
        "profile_id": (req.profile or {}).get("profile_id"), "profile_version": (req.profile or {}).get("version"),
        "budget": {k: getattr(req, k) for k in ("max_queries", "max_pages", "max_seconds", "target_count")},
        "note": "按查询逐批执行；目标为候选网站数量，不代表采购意向或企业身份已验证。"}


def assess_rules(rules: list[dict], host: str) -> tuple[list, str]:
    """Only exact domain membership is deterministic here; semantic rules remain unknown."""
    results=[]
    for rule in rules:
        level=rule["level"]
        result="unknown"
        reason="需人工或后续背调核实；未由搜索关键词推断符合。"
        value=rule.get("value")
        values=value if isinstance(value,list) else [value]
        if rule.get("field") == "domain" and rule.get("operator") in {"equals", "in"} and values and all(isinstance(v,str) and domain(v) for v in values):
            match=host in {domain(v) for v in values}
            result=("hit" if match else "clear") if level=="exclude" else (("pass" if match else "fail") if level=="must" else ("match" if match else "no_match"))
            reason="标准化域名精确比较；未合并集团或别名。"
        results.append({"rule_id":rule["rule_id"], "level":level, "result":result, "reason":reason})
    if any(r["result"] in {"fail","hit"} for r in results):
        return results, "rejected"
    hard=[r for r in results if r["level"]!="should"]
    return results, "qualified" if hard and all(r["result"]!="unknown" for r in hard) else "needs_review"


DIRECTORIES={"linkedin.com","facebook.com","instagram.com","youtube.com","wikipedia.org","alibaba.com","amazon.com"}
_slots=asyncio.Semaphore(2)

async def run_search(req: SearchInput, *, search=None, fetch=None) -> dict:
    plan=make_plan(req)
    start=time.monotonic()
    candidates=[]; logs=[]; seen=set(); reads=0; low_yield=0
    excluded={domain(x) for x in req.excluded_domains}
    if "" in excluded:
        raise ValueError("排除名单中含无效域名。")
    stop="queries_exhausted"; warnings=[]
    async def run(service_search):
        nonlocal reads, stop, low_yield
        for query in plan["queries"]:
            if time.monotonic()-start >= req.max_seconds:
                stop="time_budget"; break
            new=0
            try:
                async with asyncio.timeout(max(.01,req.max_seconds-(time.monotonic()-start))):
                    batch=await service_search(SearchRequest(query=query,max_results=8,search_depth="basic"))
            except TimeoutError:
                logs.append({"query":query,"status":"timeout","new_candidates":0})
                stop="time_budget"; warnings.append("达到本次搜索时间预算；已保留先前结果。")
                break
            except (RuntimeError,ValueError,httpx.HTTPError):
                logs.append({"query":query,"status":"error","new_candidates":0})
                stop="search_error"; warnings.append("搜索服务未配置、不可用或超时；没有补造结果。")
                break
            log={"query":query,"status":batch.get("status","error"),"provider":batch.get("provider"),
                 "query_statuses":batch.get("query_statuses",[]),"new_candidates":0,"skipped":0}
            logs.append(log)
            if batch.get("status")=="error":
                stop="search_error"; warnings.append("搜索提供方返回失败，已保留先前结果。")
                break
            for source in batch.get("results",[]):
                url=str(source.get("url") or "")
                host=domain(url)
                if not host or host in seen or any(host==e or host.endswith("."+e) for e in excluded) or any(host==e or host.endswith("."+e) for e in DIRECTORIES):
                    log["skipped"]+=1; continue
                seen.add(host)
                rule_results,decision=assess_rules((req.profile or {}).get("rules",[]),host)
                if decision=="rejected":
                    log["skipped"]+=1; continue
                item={"id":buyer_id(host),"name":str(source.get("title") or host)[:300],
                    "domain":host,"website":url,"discovery_url":url,"query":query,
                    "discovered_at":datetime.now(timezone.utc).isoformat(),
                    "summary":str(source.get("content") or "")[:1500],"page_status":"not_read",
                    "page_url":None,"page_excerpt":"","page_read_at":None,
                    "decision":decision,"rule_results":rule_results,"identity_status":"unverified",
                    "unresolved":["企业与网站身份关联", "采购需求、采购量和决策人", "产品、买家类型及经营市场匹配度"]}
                if reads < req.max_pages and time.monotonic()-start < req.max_seconds:
                    reads+=1
                    try:
                        async with asyncio.timeout(max(.01,req.max_seconds-(time.monotonic()-start))):
                            page=await (fetch(url) if fetch else asyncio.to_thread(_fetch_public,url))
                        parser=_parse_html(page)
                        # A redirect to another domain changes the identity; never silently reassign it.
                        if domain(page.url)!=host:
                            item["page_status"]="redirect_requires_review"
                        else:
                            item.update(page_status="read",page_url=page.url,page_excerpt=parser.text[:4000],page_read_at=page.retrieved_at)
                            if parser.title: item["name"]=parser.title
                    except (PublicDataError,TimeoutError):
                        item["page_status"]="unavailable"
                candidates.append(item); new+=1
                if len(candidates)>=req.target_count:
                    stop="target_reached"; break
                if time.monotonic()-start>=req.max_seconds:
                    stop="time_budget"; break
            log["new_candidates"]=new
            low_yield=low_yield+1 if not new else 0
            if stop in {"target_reached","time_budget"}: break
            if low_yield>=3:
                stop="low_yield"; break
    if search:
        await run(search)
    else:
        if _slots.locked():
            raise RuntimeError("买家搜索繁忙，请稍后重试。")
        async with _slots:
            async with httpx.AsyncClient(trust_env=False) as client:
                await run(SearchService(client).search)
    return {"document_type":"buyer_search","document_version":1,"plan":plan,"candidates":candidates,
        "search_log":logs,"stop_reason":stop,"warnings":warnings,
        "metrics":{"candidate_count":len(candidates),"queries_executed":len(logs),"pages_attempted":reads,
            "pages_read":sum(c["page_status"]=="read" for c in candidates),"elapsed_seconds":round(time.monotonic()-start,2),
            "effective_lead_rate":None,"unit_effective_lead_cost":None},
        "limitations":["搜索标题不是已核验公司名称；页面内容是网站自述。", "语义筛选条件需人工审核，未读取页面不算已验证。", "费用取决于搜索供应商账单，未接入计费；有效率需人工标注。"]}
