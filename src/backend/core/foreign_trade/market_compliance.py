"""Country-scoped review hints from curated public sources, without model or network."""
from __future__ import annotations

import json
import re
from importlib.resources import files

_MARKETS = {
    "US": {"us", "usa", "united states", "united states of america", "美国", "美國"},
    "UK": {"uk", "gb", "gbr", "united kingdom", "great britain", "england", "scotland", "wales", "英国", "英國"},
    "CA": {"ca", "can", "canada", "加拿大"},
    "EU": {"eu", "european union", "欧盟", "歐盟", "spain", "españa", "西班牙",
           "germany", "德国", "france", "法国", "italy", "意大利", "netherlands", "荷兰",
           "austria", "belgium", "bulgaria", "croatia", "cyprus", "czechia", "czech republic",
           "denmark", "estonia", "finland", "greece", "hungary", "ireland", "latvia",
           "lithuania", "luxembourg", "malta", "poland", "portugal", "romania", "slovakia",
           "slovenia", "sweden", "at", "be", "bg", "hr", "cy", "cz", "dk", "ee", "fi",
           "fr", "de", "gr", "hu", "ie", "it", "lv", "lt", "lu", "mt", "nl", "pl", "pt",
           "ro", "sk", "si", "es", "se"},
}
_PATTERNS = {
    "origin_claim": re.compile(r"\b(?:made|manufactured|built)\s+in\s+(?:the\s+)?(?:u\.?s\.?a?\.?|united states)\b|\bamerican[- ]made\b|美国制造", re.I),
    "environmental_claim": re.compile(r"\b(?:eco[- ]friendly|environmentally[- ]friendly|(?:100%\s+)?sustainable|carbon[- ]neutral|biodegradable|zero\s+environmental\s+impact|100%\s+recyclable)\b|零碳|零环境影响|环保无害|百分百可回收", re.I),
    "ce_claim": re.compile(r"\bCE[\s-]*(?:certified|approved|marked|marking)|\bcertified\s+by\s+CE\b|CE\s*认证", re.I),
    "uk_marking_claim": re.compile(r"\b(?:UKCA|CE)[\s-]*(?:certified|approved|marked|marking)|UKCA\s*认证", re.I),
}
_FACT_CHECKS = {
    "gpsr_information": [
        ("GPSR applicability", "GPSR适用范围"),
        ("Manufacturer contact", "制造商联系方式"),
        ("EU responsible person", "欧盟责任人"),
        ("Product identification", "产品识别"),
        ("Safety information", "安全信息"),
    ],
    "ca_packaging_information": [
        ("Packaging scope", "包装适用范围"),
        ("Package identity EN", "包装英文品名"),
        ("Package identity FR", "包装法文品名"),
        ("Package net quantity", "包装净含量"),
        ("Package dealer", "包装经销商"),
    ],
}


def bundle():
    data = json.loads(files("foreign_trade").joinpath("market_compliance.json").read_text("utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("rules"), list) or not 1 <= len(data["rules"]) <= 100:
        raise ValueError("Country compliance knowledge bundle is invalid")
    return data


def search_terms(rule):
    return " ".join(sorted(_MARKETS.get(rule.get("market"), set())))


def market_context(channel, source, draft):
    """RFQ destination wins over reply language; listings use explicit target locale."""
    value = str(source.get("destination_country") or "").strip() if channel == "alibaba_rfq" else str(draft.get("locale") or "").strip()
    key = value.casefold().replace(".", "")
    if channel != "alibaba_rfq":
        parts = re.split(r"[-_]", key)
        key = parts[-1] if len(parts) > 1 else key
        if key == "amazoncom":
            key = "us"
    market = next((m for m, aliases in _MARKETS.items() if key in aliases), None)
    origin = "询盘目的国" if channel == "alibaba_rfq" else "Listing目标locale"
    note = (f"国别检查按{origin}“{value}”选择{market}案例；只覆盖已列规则，证据真实性仍待人工核验。"
            if market else f"未能从{origin}识别已覆盖市场，本轮没有执行国别规则；请明确目的国或带国家码的locale，不能把英文自动当美国。")
    return {"market": market, "input": value, "basis": origin, "scope_note": note}


def _present_fact(source, labels):
    allowed = {label.casefold() for label in labels}
    for fact in source.get("facts") or []:
        if str(fact.get("label") or "").strip().casefold() not in allowed:
            continue
        value = str(fact.get("value") or "").strip()
        if value and not re.search(r"unknown|unconfirmed|pending|not provided|tbd|待|未知|未提供|未确认", value, re.I):
            return True
    return False


def evaluate(rule, context, fields, source, add, positive_claim):
    """Add bounded hints. Missing documents are never a legal violation verdict."""
    if context["market"] != rule["market"]:
        return False
    kind = rule["check"]
    if kind in _PATTERNS:
        count = 0
        for field, text in fields:
            for hit in _PATTERNS[kind].finditer(text):
                if not positive_claim(text, *hit.span()):
                    continue
                add(field, hit.group(), rule["summary"],
                    "请核对：" + "；".join(rule["unknowns"]) + "。缺少依据时删除或限定宣称，不新增虚构事实。",
                    "medium", "needs_confirmation")
                count += 1
                if count >= 8:
                    return True
    else:
        required = _FACT_CHECKS.get(kind, [])
        missing = [labels[1] for labels in required if not _present_fact(source, labels)]
        if missing:
            if kind == "gpsr_information":
                stage = ("这是后续消费品远程销售的准备提醒，不判定B2B RFQ违反GPSR。"
                         if context["basis"] == "询盘目的国" else
                         "若此Listing面向欧盟消费者远程销售，请核验适用的商品要约信息及安全信息；本提示不代替产品适用性判断。")
            else:
                stage = "这是包装标签准备提醒，不判定英文Listing本身违法。"
            add("draft", "", stage + "待确认：" + "、".join(missing),
                "补充对应已确认事实及可核验文件；不适用时记录具体产品/地域/例外依据。人工复核证据，不能仅凭字段非空批准上架。",
                "low", "needs_confirmation")
        else:
            add("draft", "", "相关字段已提供，但其内容、原文证据及适用范围仍须人工核验；字段非空不代表通过合规审查。",
                "核对实际包装/标签和源文件，保留产品分类、销售地域及适用或豁免依据。",
                "info", "needs_confirmation")
    return True


def render_case(rule):
    return "\n".join([
        "# " + rule["title"], "",
        "规则编号：" + rule["rule_id"], "版本：" + rule["rule_version"],
        "核验日期：" + rule["verified_at"], "市场：" + rule["market"], "",
        "这是项目根据官方公开资料撰写的审稿案例，不是真实客户订单，也不是官方对该商品的合规认证。", "",
        "## 规则摘要", rule["summary"], "", "## 适用边界", rule["scope_note"], "",
        "## 模拟业务情境", rule["scenario"], "", "## 待审草稿", rule["bad_draft"], "",
        "## 修改示例", rule["revised_draft"], "",
        "修改示例只表达已知事实或待确认事项，不替用户新增认证、测试、原产地或联系人。", "",
        "## 待核验材料", *("- " + item for item in rule["unknowns"]), "",
        "## 检查预期", rule["expected"], "",
        "## 官方依据", "[" + rule["source_publisher"] + "](" + rule["source_url"] + ")", "",
    ])
