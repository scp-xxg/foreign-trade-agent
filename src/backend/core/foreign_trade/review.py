"""Deterministic draft review against versioned public rules; no model calls."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import html
from importlib.resources import files
import json
import re
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from core.db.models.foreign_trade import ForeignTradeInquiry
from core.db.models.foreign_trade_content import ForeignTradeContentPack
from core.db.models.foreign_trade_review import ForeignTradeKnowledgeRule, ForeignTradeReview
from core.foreign_trade.content import ContentPackError, ContentPackService
from core.foreign_trade.inquiry import now_iso
from core.foreign_trade.ai import _quantity_for_sku, _pack_for_sku

CHANNELS = {"alibaba_rfq": ("sales", "inquiry"), "amazon_listing": ("operations", "content_pack")}
CATEGORIES = {"platform_rules", "quotation_terms"}
SEVERITY = {"info": 0, "low": 1, "medium": 2, "high": 3}
REVIEW_SCOPE = "确定性规则与来源一致性检查；结果是待审草稿反馈，不是平台全合规、法律结论或对外发布批准。"


class ReviewError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _actor(user_id):
    if not user_id:
        raise ReviewError(403, "审核与知识检索需要当前认证用户")
    return str(user_id)


def _source_ready(source_type, record):
    return bool((record.get("quote") or {}).get("ok")) if source_type == "inquiry" else bool(record.get("facts") and record.get("outputs"))


def _bundle():
    data = json.loads(files("foreign_trade").joinpath("knowledge_rules.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not data.get("knowledge_version"):
        raise ReviewError(500, "知识规则版本无效")
    return data


class KnowledgeService:
    def __init__(self, db):
        self.db = db

    def _seed(self):
        bundle = _bundle()
        version = bundle["knowledge_version"]
        for rule in bundle["rules"]:
            key = _hash([version, rule["rule_id"]])
            existing = self.db.query(ForeignTradeKnowledgeRule).filter_by(rule_key=key).first()
            if existing:
                if existing.payload != rule:
                    raise ReviewError(409, "同一知识版本内容发生变化，请发布新版本，不能覆盖历史规则")
                continue
            try:
                with self.db.begin_nested():
                    self.db.add(ForeignTradeKnowledgeRule(rule_key=key, knowledge_version=version,
                        rule_id=rule["rule_id"], rule_version=rule["rule_version"], category=rule["category"],
                        status=rule["status"], payload=deepcopy(rule), created_at=now_iso()))
                    self.db.flush()
            except IntegrityError:
                existing = self.db.query(ForeignTradeKnowledgeRule).filter_by(rule_key=key).first()
                if existing is None or existing.payload != rule:
                    raise ReviewError(409, "知识版本存在并发冲突，请刷新后重试") from None
        return version

    def search(self, user_id, query="", channel=None, category=None, language="en", limit=50, include_superseded=False):
        _actor(user_id)
        if channel is not None and channel not in CHANNELS or category is not None and category not in CATEGORIES:
            raise ReviewError(422, "知识检索平台或校验类别无效")
        if language not in {"en", "es"} or not isinstance(query, str) or len(query) > 300 or type(limit) is not int or not 1 <= limit <= 100:
            raise ReviewError(422, "知识检索参数无效")
        version = self._seed()
        rows = self.db.query(ForeignTradeKnowledgeRule).filter_by(knowledge_version=version).order_by(
            ForeignTradeKnowledgeRule.rule_id).all()
        rules = [deepcopy(row.payload) for row in rows if (include_superseded or row.status == "active")
                 and (category is None or row.category == category)
                 and (channel is None or channel in row.payload["channels"])]
        terms = query.casefold().split()
        if terms:
            rules = [rule for rule in rules if all(term in " ".join(str(rule.get(k, "")) for k in
                     ("rule_id", "title", "summary", "scope_note", "source_publisher")).casefold() for term in terms)]
        self.db.commit()
        return {"knowledge_version": version, "language": language, "rules": rules[:limit],
                "total_matches": len(rules), "scope_note": REVIEW_SCOPE}


def _fields(draft):
    return [(name, draft[name]) for name in ("title", "item_highlights", "body")] + [
        (f"bullets[{index}]", value) for index, value in enumerate(draft["bullets"])]


def _positive_claim(text, start, end):
    before, after = text[max(0, start - 120):start].casefold(), text[end:end + 50].casefold()
    # A negative freight clause must not negate a separate positive tax claim.
    before = re.split(r"[,;.!?\n]|\b(?:but|however|yet|pero)\b", before)[-1]
    conjunctions = list(re.finditer(r"\b(?:and/or|and|or|y|o)\b", before))
    if conjunctions:
        # Preserve explicit negative object lists: "no free shipping or taxes
        # included". An independent predicate ("freight not included and ...")
        # starts a new scope, as does an unrelated promise about discounts.
        negative_list = re.search(
            r"\b(?:no|without|sin|not\s+(?:offer|provide|include))\s+"
            r"(?:free\s+)?(?:shipping|freight|delivery|tax(?:es)?|duties|env[ií]o|transporte|impuestos|aranceles)"
            r"\s+(?:and/or|and|or|y|o)\s*$", before)
        if negative_list:
            return False
        before = before[conjunctions[-1].end():]
    negative = r"(?:not(?!\s+only\b)|no|without|never|sin|nunca)"
    return not (re.search(r"\b" + negative + r"\b[^.;\n]{0,30}$", before)
                or re.match(r"\s*(?:is|are|est[aá]|est[aá]n)?\s*(?:not(?!\s+only\b)|unconfirmed|pending|unknown|no confirmado|pendiente)\b", after))


def _money(value, language):
    value = value.replace(" ", "")
    if "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        value = value.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in value:
        value = value.replace(",", ".") if len(value.rsplit(",", 1)[1]) == 2 else value.replace(",", "")
    elif language == "es" and value.count(".") == 1 and len(value.rsplit(".", 1)[1]) == 3:
        value = value.replace(".", "")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


_MONEY = re.compile(r"(?:(?P<currency>USD|EUR|GBP|\$|€|£)\s*(?P<amount>\d[\d.,]*)|(?P<after_amount>\d[\d.,]*)\s*(?P<after_currency>USD|EUR|GBP)\b)", re.I)
_FREIGHT_TAX = re.compile(r"\b(?:free\s+(?:shipping|freight|delivery)|(?:shipping|freight|tax(?:es)?|duties)\s+(?:is\s+|are\s+)?(?:free|included)|(?:includes?|including)\s+(?:shipping|freight|tax(?:es)?|duties)|(?:env[ií]o|transporte|entrega)\s+(?:gratis|gratuit[oa])|(?:env[ií]o|transporte|impuestos|aranceles)\s+incluid[oa]s?|incluye\s+(?:env[ií]o|impuestos|aranceles))\b", re.I)
_CLAIMS = re.compile(r"\b(?:CE\s+certified|FDA\s+approved|ISO\s+certified|certified|authorized\s+(?:reseller|distributor)|official\s+distributor|certificad[oa]|distribuidor\s+(?:autorizado|oficial)|revendedor\s+autorizado)\b", re.I)
_STOPWORDS = set("a an the and or but for to of in on at by with from as is are un una unos unas el la los las y o pero para de del en con por al a".split())


def _money_context(text, match):
    before = re.split(r"[;\n]|\.(?=\s)", text[:match.start()])[-1][-90:].casefold()
    earlier_amounts = list(_MONEY.finditer(before))
    if earlier_amounts:
        before = before[earlier_amounts[-1].end():]
    after = re.split(r"[;\n]|\.(?=\s)", text[match.end():])[0][:30].casefold()
    labels = list(re.finditer(r"\b(?:packaging|embalaje|unit(?:\s+price)?|unidad|goods|merchandise|mercanc[ií]a|"
                             r"(?:grand\s+)?(?:sub)?total|quote|quotation|offer|cotizaci[oó]n|presupuesto|importe|"
                             r"freight|shipping|tax(?:es)?|dut(?:y|ies)|env[ií]o|impuestos|aranceles)\b", before))
    label = labels[-1].group() if labels else ""
    if "total" in label and len(labels) >= 2:
        preceding = labels[-2].group()
        if preceding in {"packaging", "embalaje", "goods", "merchandise", "mercancía", "mercancia"}:
            label = preceding
    if re.search(r"unit|unidad", label) or re.match(r"\s*(?:/\s*unit|per\s+unit|por\s+unidad)", after):
        return "pack_unit" if re.search(r"packaging|embalaje", before) else "unit"
    if re.search(r"packaging|embalaje", label):
        return "pack_total"
    if re.search(r"goods|merchandise|mercanc[ií]a", label):
        return "goods_total"
    if re.search(r"freight|shipping|tax|dut|env[ií]o|impuestos|aranceles", label):
        return "unknown_fee"
    if label:
        return "total"
    return "unlabelled"


def _evaluate(draft, channel, source, rules):
    annotations, checks = [], []
    fields = _fields(draft)
    combined = "\n".join(value for _, value in fields)
    def locate(fragment):
        for field, value in fields:
            match = re.search(re.escape(fragment), value, re.I)
            if match:
                return field, match.group()
        return "body", ""
    quote = (source.get("quote") or {}).get("data") or {}
    us_scope = draft["locale"].lower().replace("-", "_") in {"us", "en_us", "es_us", "amazon.com"}
    for rule in rules:
        rid, before, applicable = rule["rule_id"], len(annotations), True
        def add(field, fragment, message, suggestion, severity="medium", status="issue"):
            # Repeated claims in one field need distinct identities. Preserve
            # each occurrence and its count; a deterministic ordinal also keeps
            # repeated evaluation stable without requiring UTF-16 offsets.
            annotations.append({"annotation_id": "annotation_" + _hash([rid, field, fragment, message, len(annotations)])[:24],
                "rule_id": rid, "category": rule["category"], "field": field, "quote": str(fragment)[:240],
                "severity": severity, "status": status, "message": message, "suggestion": suggestion})
        if rid.startswith("amazon.") and rid != "amazon.scope_confirmation" and not us_scope:
            applicable = False
        elif rid in {"amazon.title_length", "amazon.item_highlights_length", "amazon.combined_length"}:
            field = {"amazon.title_length": "title", "amazon.item_highlights_length": "item_highlights", "amazon.combined_length": "draft"}[rid]
            value = draft["title"] + draft["item_highlights"] if field == "draft" else draft[field]
            if field == "title" and not value.strip():
                add(field, "", "缺少商品标题", "根据已确认产品事实填写标题。", "high")
            elif len(value) > rule["max_chars"]:
                add(field, value if field != "draft" else "", f"按美国非媒体基线，当前{len(value)}个字符超过{rule['max_chars']}上限",
                    "保留核心产品信息，压缩本字段；不要把规格或承诺移入不适用字段以规避规则。", "high")
        elif rid == "amazon.title_characters":
            brand = str(source.get("brand") or "")
            for char in sorted(set(draft["title"]) & set(rule["forbidden_characters"])):
                brand_spans = [match.span() for match in re.finditer(re.escape(brand), draft["title"], re.I)] if brand else []
                brand_exception = bool(brand_spans and all(any(start <= index < end for start, end in brand_spans)
                    for index, value in enumerate(draft["title"]) if value == char))
                add("title", char, "标题含受限制字符；该字符可能位于品牌名称中，例外须人工确认" if brand_exception else "标题含2025公告基线限制的字符",
                    "核对真实品牌写法及当前类目规则；没有适用例外时移除该字符。",
                    "low" if brand_exception else "high", "needs_confirmation" if brand_exception else "issue")
        elif rid == "amazon.title_repetition":
            original_words = re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", draft["title"], re.UNICODE)
            words = [word.casefold() for word in original_words]
            for word, count in Counter(words).items():
                if word not in _STOPWORDS and not word.isdigit() and count > rule["max_word_occurrences"]:
                    add("title", next(value for value in original_words if value.casefold() == word), f"同一词出现{count}次，超过标题重复词基线", "减少重复词，并人工核对词性、品牌和类目例外。")
        elif rid == "amazon.scope_confirmation":
            add("draft", draft["locale"], "请确认美国非媒体类目及逐步实施状态" if us_scope else "当前站点不在本项目自动平台规则范围内",
                "在对应站点后台核对实际类目、字段和rollout；本报告不作全平台合规保证。", "info", "needs_confirmation")
        elif rid == "alibaba.rfq_alignment":
            items = source.get("items", [])
            skus = [item["sku"] for item in items]
            normalized = re.sub(r"\b(?:unidades|piezas|uds)\b", "units", combined, flags=re.I)
            normalized = re.sub(r"\bembalaje\s+personalizado\b", "custom packaging", normalized, flags=re.I)
            normalized = re.sub(r"\bembalaje\s+est[aá]ndar\b", "standard packaging", normalized, flags=re.I)
            for item in items:
                item_field, item_fragment = locate(item["sku"])
                if not re.search(r"(?<![\w-])" + re.escape(item["sku"]) + r"(?![\w-])", combined, re.I):
                    add("body", "", f"草稿未明确列出询盘产品{item['sku']}", "列出对应SKU和已确认规格，回应买家具体需求。", status="needs_confirmation")
                pair = _quantity_for_sku(normalized, item["sku"], skus)
                if pair and pair[0] != item["quantity"]:
                    add(item_field, item_fragment, f"草稿数量{pair[0]}与询盘数量{item['quantity']}不一致", "按当前询盘更正数量，变更需求应先更新询盘并重算报价。", "high")
                elif pair is None:
                    add(item_field, item_fragment, "未找到该SKU与数量的明确对应", "在同一行或句中列出SKU和已确认数量，不用总量代替分项数量。", status="needs_confirmation")
                expected_pack = item["custom_packaging"]
                if _pack_for_sku(normalized, item["sku"], not expected_pack, skus):
                    add(item_field, item_fragment, "草稿包装方式与当前询盘不一致", "核对本SKU的标准或定制包装；变更包装应先更新询盘并重算报价。", "high")
                elif not _pack_for_sku(normalized, item["sku"], expected_pack, skus):
                    add(item_field, item_fragment, "未找到该SKU与包装方式的明确对应", "明确说明本产品使用标准或定制包装，其他规格仍应对照产品资料人工核对。", status="needs_confirmation")
            for field, value in fields:
                for match in re.finditer(r"(?:production(?:\s+lead\s+time)?|producci[oó]n)\s*(?:within|of|:|en|de)?\s*(\d+)\s*(?:days?|d[ií]as)", value, re.I):
                    if quote.get("production_lead_days") and int(match.group(1)) < quote["production_lead_days"] and _positive_claim(value, *match.span()):
                        add(field, match.group(), "生产时间短于当前报价参考周期", "改为当前参考周期并保留实际供货待确认说明；不要把运输时间算入生产周期。", "high")
                for match in re.finditer(r"(?:delivery|delivered|arrival|arrive|entrega|llegada)\s*(?:within|in|:|en|dentro\s+de)?\s*(\d+)\s*(?:days?|d[ií]as)", value, re.I):
                    if quote.get("delivery_lead_days") is None and _positive_claim(value, *match.span()):
                        add(field, match.group(), "到货时限没有已确认运输依据", "可保留买家期望，但应注明到货日期待确认，不能把生产周期当作到货承诺。", status="needs_confirmation")
        elif rid == "quote.amount_consistency":
            for field, value in fields:
                for match in _MONEY.finditer(value):
                    amount = _money((match.group("amount") or match.group("after_amount")).rstrip(".,"), draft["language"])
                    currency = (match.group("currency") or match.group("after_currency")).upper()
                    currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(currency, currency)
                    if not quote:
                        add(field, match.group(), "该金额没有当前报价作为依据", "保留为待供应商确认，不将独立产品资料自动变为报价。", status="needs_confirmation")
                        continue
                    if currency != quote.get("currency"):
                        add(field, match.group(), "草稿币种与当前报价不一致", "使用当前报价币种；币种转换须另有明确依据。", "high")
                        continue
                    context = _money_context(value, match)
                    if context == "unknown_fee" and amount == 0:
                        add(field, match.group(), "当前没有零运费或零税费依据", "未知费用应写待确认，不能用0代替。", "high")
                        continue
                    if context == "unknown_fee":
                        add(field, match.group(), "当前报价没有该费用的确认金额", "保留费用待确认，不写成已核定收费。", status="needs_confirmation")
                        continue
                    if context == "pack_unit":
                        expected = {Decimal(line["packaging_unit_surcharge"]) for line in quote["items"]}
                    elif context == "pack_total":
                        expected = {Decimal(quote["packaging_subtotal"])}
                    elif context == "unit":
                        expected = {Decimal(line["unit_price"]) for line in quote["items"]}
                    elif context == "goods_total":
                        expected = {Decimal(quote["merchandise_subtotal"])}
                    elif context == "total":
                        expected = {Decimal(quote["subtotal"])}
                    else:
                        expected = {Decimal(quote["subtotal"])}
                        if amount != Decimal(quote["subtotal"]):
                            known_amounts = {Decimal(quote[key]) for key in ("subtotal", "merchandise_subtotal", "packaging_subtotal")}
                            known_amounts.update(Decimal(line[key]) for line in quote["items"] for key in ("unit_price", "packaging_unit_surcharge", "line_subtotal"))
                            if amount not in known_amounts:
                                add(field, match.group(), "声明金额未对应当前报价的任何分项", "更正金额，并明确它是单价、货值、包装费还是小计。", "high")
                            else:
                                add(field, match.group(), "金额用途未标明，无法与报价分项唯一对应", "注明商品单价、货值、包装费或小计，再核对当前报价。", status="needs_confirmation")
                            continue
                    if context in {"unit", "pack_unit"} and len(quote["items"]) > 1:
                        clause = re.split(r"[;\n]|\.(?=\s)", value[:match.start()])[-1]
                        scoped = [line for line in quote["items"] if re.search(r"(?<![\w-])" + re.escape(line["sku"]) + r"(?![\w-])", clause, re.I)]
                        if len(scoped) == 1:
                            expected = {Decimal(scoped[0]["unit_price" if context == "unit" else "packaging_unit_surcharge"])}
                        elif len(expected) > 1:
                            add(field, match.group(), "多产品单价没有与SKU明确对应", "在同一行注明SKU与对应单价，不能借用另一产品的价格。", status="needs_confirmation")
                            continue
                    if amount not in expected:
                        add(field, match.group(), "声明金额与当前报价对应分项不一致", "按保存的报价更正金额；不要由审核服务补算或猜测真实价格。", "high")
        elif rid == "quote.unknown_freight_tax":
            for field, value in fields:
                for match in _FREIGHT_TAX.finditer(value):
                    if _positive_claim(value, *match.span()):
                        add(field, match.group(), "没有已确认的运费或税费依据，不能承诺免费或已包含", "将费用范围写为不含运费/税费且待确认，除非先补充可靠商务依据。", "high")
        elif rid == "quote.commercial_terms":
            for name, pattern in (("付款条件", r"payment|deposit|net\s*\d+|pago|dep[oó]sito"),
                                  ("报价有效期", r"valid(?:ity|\s+until|\s+for)|v[aá]lid[oa]|vigencia"),
                                  ("Incoterm", r"incoterms?|\b(?:EXW|FOB|CIF|CFR|DAP|DDP|FCA|CPT|CIP|DPU|FAS)\b")):
                match = next(((field, m.group()) for field, value in fields for m in re.finditer(pattern, value, re.I)), None)
                add(match[0] if match else "body", match[1] if match else "", f"{name}尚无结构化确认依据",
                    f"保留{name}待确认；涉及具体承诺时由业务人员补充依据后复核。", "low", "needs_confirmation")
        elif rid == "quote.unsubstantiated_claims":
            evidence = " ".join(f.get("label", "") + " " + f.get("value", "") for f in source.get("facts", [])).casefold()
            for field, value in fields:
                for match in _CLAIMS.finditer(value):
                    if _positive_claim(value, *match.span()) and match.group().casefold() not in evidence:
                        add(field, match.group(), "未找到与该认证或授权声明相符的已确认事实", "补充并人工核对证据，或将声明改为未确认；不据此判定违法或认证无效。", "medium", "needs_confirmation")
        elif rid == "quote.simulation_disclosure":
            simulated = bool((source.get("quote") or {}).get("is_simulated") or (source.get("catalog_binding") or {}).get("is_simulated"))
            if simulated and not re.search(r"\bdemo\b|simulat|fictional|demostraci[oó]n|simulad", combined, re.I):
                add("body", "", "草稿未保留模拟目录/报价说明", "明确写明演示或模拟，不构成真实供货或销售承诺。", "high")
            applicable = simulated
        else:
            applicable = False
        added = annotations[before:]
        status = "issue" if any(item["status"] == "issue" for item in added) else "needs_confirmation" if added else "passed" if applicable else "not_applicable"
        checks.append({"rule_id": rid, "status": status, "annotation_count": len(added)})
    issue_count = sum(item["status"] == "issue" for item in annotations)
    confirmation_count = len(annotations) - issue_count
    labels = []
    for rule in rules:
        found = [item for item in annotations if item["rule_id"] == rule["rule_id"]]
        if found:
            labels.append({"code": rule["rule_id"], "label": rule["title"],
                "severity": max((item["severity"] for item in found), key=SEVERITY.get), "count": len(found)})
    return {"text_annotations": annotations, "checks": checks, "risk_labels": labels,
        "summary": {"issue_count": issue_count, "needs_confirmation_count": confirmation_count,
                    "review_status": "needs_revision" if issue_count else "needs_confirmation" if confirmation_count else "no_issues_detected"}}


class ReviewService:
    def __init__(self, db):
        self.db = db

    def _row(self, user_id, review_id):
        row = self.db.query(ForeignTradeReview).filter_by(owner_user_id=_actor(user_id), review_id=review_id).populate_existing().first()
        if row is None:
            raise ReviewError(404, "审核记录不存在或无权访问")
        return row

    def _source(self, user_id, source_type, source_id, require_ready=False):
        self.db.expire_all()
        if source_type == "inquiry":
            row = self.db.query(ForeignTradeInquiry).filter_by(owner_user_id=_actor(user_id), inquiry_id=source_id).first()
            fields = ("buyer", "raw_inquiry", "items", "destination_country", "requested_lead_days", "quote", "quote_revision", "is_demo_inquiry", "source_note")
        elif source_type == "content_pack":
            row = self.db.query(ForeignTradeContentPack).filter_by(owner_user_id=_actor(user_id), pack_id=source_id).first()
            fields = ("product_name", "brand", "model", "source_url", "facts", "documents", "image_credit", "outputs", "catalog_binding")
        else:
            raise ReviewError(422, "审核来源类型无效")
        if row is None:
            raise ReviewError(404, "审核来源不存在或无权访问")
        record = deepcopy(row.payload)
        if require_ready and not _source_ready(source_type, record):
            raise ReviewError(422, "请先生成当前询盘报价，或确认事实并生成当前产品资料包")
        snapshot = {"type": source_type, "id": source_id, "revision": row.revision,
                    "fingerprint": _hash({key: record.get(key) for key in fields})}
        return snapshot, record

    def _fresh(self, user_id, snapshot):
        try:
            current, record = self._source(user_id, snapshot["type"], snapshot["id"])
            stale = current["revision"] != snapshot["revision"] or current["fingerprint"] != snapshot["fingerprint"]
            return {**snapshot, "current_revision": current["revision"], "stale": stale,
                    "stale_reason": "source_changed" if stale else None}, record
        except ReviewError as exc:
            if exc.status != 404:
                raise
            return {**snapshot, "current_revision": None, "stale": True, "stale_reason": "source_unavailable"}, None

    def get(self, user_id, review_id):
        row = self._row(user_id, review_id)
        result = {**deepcopy(row.payload), "review_id": row.review_id, "created_at": row.created_at}
        result["source"], _ = self._fresh(user_id, result["source"])
        return result

    def list(self, user_id, source_type=None, source_id=None, limit=50):
        query = self.db.query(ForeignTradeReview).filter_by(owner_user_id=_actor(user_id))
        if source_type is not None:
            query = query.filter_by(source_type=source_type)
        if source_id is not None:
            query = query.filter_by(source_id=source_id)
        rows = query.order_by(ForeignTradeReview.created_at.desc(), ForeignTradeReview.review_id).limit(limit).all()
        return [self.get(user_id, row.review_id) for row in rows]

    def create(self, user_id, values):
        user_id = _actor(user_id)
        # Shared API validation also protects direct tool/service callers.
        from api.routes.v1.foreign_trade_review import CreateReview
        from pydantic import ValidationError
        try:
            values = CreateReview.model_validate(values).model_dump()
        except ValidationError:
            raise ReviewError(422, "审核参数无效，请核对草稿、来源版本与平台") from None
        role, required_source = CHANNELS[values["channel"]]
        if values["source_type"] != required_source:
            raise ReviewError(422, "Alibaba RFQ需要当前询盘报价；Amazon上品需要已确认并生成的产品资料包")
        snapshot, source = self._source(user_id, values["source_type"], values["source_id"])
        if snapshot["revision"] != values["source_revision"]:
            raise ReviewError(409, "来源已更新，请读取当前版本后提交审核")
        if not _source_ready(values["source_type"], source):
            raise ReviewError(422, "请先生成当前询盘报价，或确认事实并生成当前产品资料包")
        previous = None
        if values["previous_review_id"]:
            previous = deepcopy(self._row(user_id, values["previous_review_id"]).payload)
            if previous["channel"] != values["channel"] or previous["source"]["type"] != snapshot["type"] or previous["source"]["id"] != snapshot["id"]:
                raise ReviewError(422, "前一轮审核必须属于同一来源和平台")
        version = KnowledgeService(self.db)._seed()
        rows = self.db.query(ForeignTradeKnowledgeRule).filter_by(knowledge_version=version, status="active").order_by(ForeignTradeKnowledgeRule.rule_id).all()
        rules = [deepcopy(row.payload) for row in rows if values["channel"] in row.payload["channels"]]
        feedback = _evaluate(values["draft"], values["channel"], source, rules)
        comparison = None
        if previous:
            old_rules = {item["rule_id"] for item in previous["text_annotations"]}
            new_rules = {item["rule_id"] for item in feedback["text_annotations"]}
            comparison = {"previous_review_id": values["previous_review_id"], "resolved_rule_ids": sorted(old_rules - new_rules),
                "persisting_rule_ids": sorted(old_rules & new_rules), "new_rule_ids": sorted(new_rules - old_rules),
                "previous_summary": deepcopy(previous["summary"]),
                "source_changed": previous["source"] != snapshot, "rules_changed": previous["rule_version"] != version,
                "language_changed": previous["draft"]["language"] != values["draft"]["language"]}
        current, _ = self._source(user_id, snapshot["type"], snapshot["id"])
        if current != snapshot:
            self.db.rollback()
            raise ReviewError(409, "审核期间来源已更新，请使用最新版本重新审核")
        identifier, timestamp = "review_" + uuid4().hex, now_iso()
        payload = {"document_type": "foreign_trade_review", "document_version": 1,
            "previous_review_id": values["previous_review_id"], "channel": values["channel"], "role": role,
            "source": snapshot, "draft": deepcopy(values["draft"]), "rule_version": version,
            "rule_evidence": rules, **feedback, "comparison": comparison, "scope_note": REVIEW_SCOPE,
            "not_sent": True, "not_published": True}
        self.db.add(ForeignTradeReview(review_id=identifier, owner_user_id=user_id, source_type=snapshot["type"],
            source_id=snapshot["id"], channel=values["channel"], previous_review_id=values["previous_review_id"],
            payload=payload, created_at=timestamp))
        self.db.commit()
        return self.get(user_id, identifier)

    def download(self, user_id, review_id, kind):
        record = self.get(user_id, review_id)
        if record["source"]["stale"]:
            raise ReviewError(409, "审核来源已变化，请提交新版审核后下载")
        if kind == "json":
            result = (json.dumps(record, ensure_ascii=False, indent=2).encode(), "application/json", review_id + ".json")
        elif kind == "md":
            result = (_markdown(record).encode(), "text/markdown; charset=utf-8", review_id + ".md")
        else:
            raise ReviewError(422, "审核报告仅支持 md 或 json")
        current, source = self._fresh(user_id, record["source"])
        if current["stale"]:
            raise ReviewError(409, "来源在导出期间已变化，请重新审核")
        if current["type"] == "content_pack":
            try:
                for document in source.get("documents", []):
                    ContentPackService(self.db).read_file(user_id, current["id"], document["file_id"])
            except ContentPackError:
                raise ReviewError(409, "产品原文件已变化或不可访问，请核对来源后重新审核") from None
        if self._fresh(user_id, record["source"])[0]["stale"]:
            raise ReviewError(409, "来源在导出期间已变化，请重新审核")
        return result


def _markdown(record):
    def safe(value):
        value = html.escape(str(value), quote=True).replace("\r", "").replace("\n", " ")
        for character in ("\\", "`", "*", "_", "[", "]", "(", ")", "#", "!"):
            value = value.replace(character, "\\" + character)
        return value
    source = record["source"]
    lines = ["# 外贸草稿审核报告", "", "审核编号：" + record["review_id"], "平台：" + record["channel"],
        "规则版本：" + record["rule_version"], f"来源：{source['type']} {source['id']} / revision {source['revision']}",
        "来源指纹：" + source["fingerprint"], "", record["scope_note"], "未发送消息；未发布商品。", "", "## 草稿"]
    lines += [f"- {field}: {safe(value)}" for field, value in _fields(record["draft"])]
    lines += ["", "## 文本批注与风险"]
    for item in record["text_annotations"]:
        lines += [f"- {safe(item['field'])} / {item['severity']} / {item['status']}: {safe(item['message'])}",
                  "  引用片段：" + safe(item["quote"]), "  修改建议：" + safe(item["suggestion"])]
    if not record["text_annotations"]:
        lines.append("本轮未发现已实现规则覆盖的风险；不代表全平台合规。")
    lines += ["", "## 规则依据"]
    for rule in record["rule_evidence"]:
        lines += [f"- {safe(rule['title'])} / {rule['rule_version']} / 核验 {rule['verified_at']}",
                  "  " + safe(rule["summary"]), "  范围：" + safe(rule["scope_note"]), "  来源：" + rule["source_url"]]
    if record["comparison"]:
        comparison = record["comparison"]
        lines += ["", "## 与前一轮比较", "前一轮：" + comparison["previous_review_id"],
                  "已消除规则项：" + safe(", ".join(comparison["resolved_rule_ids"]) or "无"),
                  "仍存在规则项：" + safe(", ".join(comparison["persisting_rule_ids"]) or "无"),
                  "新增规则项：" + safe(", ".join(comparison["new_rule_ids"]) or "无"),
                  f"来源变化：{comparison['source_changed']}；规则变化：{comparison['rules_changed']}；语言变化：{comparison['language_changed']}"]
    return "\n".join(lines) + "\n"
