"""Persisted, owner-scoped inquiry workflow with compare-and-swap revisions.

The catalog remains demonstrational. Public buyer evidence is provenance, not a
credit score. All outward messages are drafts, never emailed by this service.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session
from core.db.models.foreign_trade import ForeignTradeInquiry
from foreign_trade.engine import calculate_quote, search_products


class InquiryError(Exception):
    def __init__(self, status: int, message: str, details: Any = None):
        self.status = status
        self.message = message
        self.details = details
        super().__init__(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_due_at(value: str, zone: str) -> str:
    try:
        ZoneInfo(zone)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise InquiryError(422, "跟进时间或时区无效") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InquiryError(422, "跟进时间必须包含 UTC 偏移，例如 +08:00")
    return parsed.astimezone(timezone.utc).isoformat()


class InquiryService:
    def __init__(self, db: Session):
        self.db = db

    def _row(self, user_id: str, inquiry_id: str) -> ForeignTradeInquiry:
        row = self.db.query(ForeignTradeInquiry).filter_by(
            owner_user_id=str(user_id), inquiry_id=inquiry_id,
        ).first()
        if row is None:
            raise InquiryError(404, "询盘不存在或无权访问")
        return row

    def get(self, user_id: str, inquiry_id: str) -> dict:
        return self._serialize(self._row(user_id, inquiry_id))

    def list(self, user_id: str, limit: int = 100) -> list[dict]:
        rows = self.db.query(ForeignTradeInquiry).filter_by(owner_user_id=str(user_id)).order_by(
            ForeignTradeInquiry.updated_at.desc(), ForeignTradeInquiry.inquiry_id,
        ).limit(limit).all()
        return [self._serialize(row) for row in rows]

    @staticmethod
    def _serialize(row: ForeignTradeInquiry) -> dict:
        result = deepcopy(row.payload)
        result.update(id=row.inquiry_id, revision=row.revision,
                      created_at=row.created_at, updated_at=row.updated_at)
        now = datetime.now(timezone.utc)
        for task in result.get("followups", []):
            task["is_due"] = (task["status"] == "pending" and
                              datetime.fromisoformat(task["due_at"]) <= now)
        return result

    def _load(self, user_id: str, inquiry_id: str, revision: int) -> dict:
        record = self.get(user_id, inquiry_id)
        if record["revision"] != revision:
            raise InquiryError(409, "询盘已被更新，请刷新后重试", {"current_revision": record["revision"]})
        return record

    def _save(self, user_id: str, inquiry_id: str, revision: int,
              record: dict, event: str, event_data: dict | None = None) -> dict:
        timestamp = now_iso()
        record = deepcopy(record)
        record.setdefault("history", []).append({
            "revision": revision + 1, "event": event, "at": timestamp,
            **(event_data or {}),
        })
        for key in ("id", "revision", "created_at", "updated_at"):
            record.pop(key, None)
        for task in record.get("followups", []):
            task.pop("is_due", None)
        count = self.db.query(ForeignTradeInquiry).filter_by(
            owner_user_id=str(user_id), inquiry_id=inquiry_id, revision=revision,
        ).update({"revision": revision + 1, "payload": record, "updated_at": timestamp},
                 synchronize_session=False)
        if count != 1:
            self.db.rollback()
            raise InquiryError(409, "询盘已被更新，请刷新后重试")
        self.db.commit()
        self.db.expire_all()
        return self.get(user_id, inquiry_id)

    def create(self, user_id: str, values: dict) -> dict:
        timestamp = now_iso()
        identifier = "inq_" + uuid4().hex
        record = {
            "title": values.get("title") or "新询盘",
            "buyer": {"company_name": "", "website": "", "email": "", "country": "",
                      **values.get("buyer", {})},
            "raw_inquiry": values.get("raw_inquiry", ""),
            "items": deepcopy(values.get("items", [])),
            "destination_country": values.get("destination_country", ""),
            "requested_lead_days": values.get("requested_lead_days"),
            "is_demo_inquiry": values.get("is_demo_inquiry", True),
            "source_note": ("演示询盘：公开公司信息仅用于核验示例，不代表与该公司的真实采购或合作关系。"
                            if values.get("is_demo_inquiry", True) else
                            "用户录入询盘；真实性由录入人核实。产品与报价仍为模拟目录。"),
            "buyer_card": None, "quote": None, "quote_revision": None, "drafts": None,
            "followups": [], "replied_at": None,
            "history": [{"revision": 1, "event": "created", "at": timestamp}],
        }
        row = ForeignTradeInquiry(inquiry_id=identifier, owner_user_id=str(user_id), revision=1,
                                  payload=record, created_at=timestamp, updated_at=timestamp)
        self.db.add(row)
        self.db.commit()
        return self.get(user_id, identifier)

    def update(self, user_id: str, inquiry_id: str, revision: int, values: dict) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        changed = {key: deepcopy(value) for key, value in values.items() if record.get(key) != value}
        allowed = {"title", "buyer", "raw_inquiry", "items", "destination_country", "requested_lead_days"}
        if set(changed) - allowed:
            raise InquiryError(422, "存在不支持的询盘字段")
        old_quote = record.get("quote")
        business_changed = bool(set(changed) - {"title"})
        if business_changed:
            if old_quote:
                record["history"].append({"revision": revision + 1, "event": "quote_superseded",
                                          "at": now_iso(), "quote_revision": record["quote_revision"],
                                          "quote": deepcopy(old_quote)})
            record["quote"] = None
            record["quote_revision"] = None
            if record.get("drafts"):
                record["drafts"]["stale"] = True
                record["drafts"]["stale_reason"] = "询盘条件已变更，请重新计算报价并生成回复"
        if "buyer" in changed:
            record["buyer_card"] = None
        record.update(changed)
        return self._save(user_id, inquiry_id, revision, record, "inquiry_updated",
                          {"changed_fields": list(changed)})

    async def verify(self, user_id: str, inquiry_id: str, revision: int) -> dict:
        from core.services.foreign_trade_public_data import verify_buyer
        record = self._load(user_id, inquiry_id, revision)
        buyer = record["buyer"]
        try:
            card = await verify_buyer(
                buyer.get("company_name", ""), buyer.get("website", ""),
                buyer.get("email", ""), buyer.get("country", ""),
            )
        except Exception:
            # Do not expose exception text, possibly containing request secrets.
            card = {"status": "unknown", "checked_at": now_iso(), "facts": [], "sources": [],
                    "warnings": ["公开资料暂时无法访问；尚未核验，不能据此判定买家不可靠。"]}
        record["buyer_card"] = card
        if record.get("drafts"):
            record["drafts"]["stale"] = True
            record["drafts"]["stale_reason"] = "买家核验资料已刷新，请重新生成回复"
        return self._save(user_id, inquiry_id, revision, record, "buyer_verified")

    def quote(self, user_id: str, inquiry_id: str, revision: int) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        if not record["destination_country"].strip():
            raise InquiryError(422, "请先确认目的国；买家公司所在地不自动作为目的国")
        result = calculate_quote(record["items"], record["destination_country"], record["requested_lead_days"])
        if not result.get("ok"):
            raise InquiryError(422, "报价条件未通过校验，请确认产品、数量和包装条件", result)
        if record.get("quote"):
            record["history"].append({"revision": revision + 1, "event": "quote_superseded",
                                      "at": now_iso(), "quote_revision": record["quote_revision"],
                                      "quote": deepcopy(record["quote"])})
        record["quote"] = result
        record["quote_revision"] = revision + 1
        if record.get("drafts"):
            record["drafts"]["stale"] = True
            record["drafts"]["stale_reason"] = "报价已重算，请重新生成回复"
        return self._save(user_id, inquiry_id, revision, record, "quote_calculated",
                          {"quote_id": result["data"]["quote_id"]})

    def draft(self, user_id: str, inquiry_id: str, revision: int) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        record["drafts"] = build_drafts(record)
        return self._save(user_id, inquiry_id, revision, record, "draft_generated")

    def update_drafts(self, user_id: str, inquiry_id: str, revision: int, drafts: dict) -> dict:
        """Allow an explicitly invoked model helper to store a reviewed-shape draft."""
        record = self._load(user_id, inquiry_id, revision)
        for key in ("zh", "en"):
            if not isinstance(drafts.get(key), str) or not drafts[key].strip() or len(drafts[key]) > 30000:
                raise InquiryError(422, "回复草稿内容无效")
        record["drafts"] = {**drafts, "stale": False, "not_sent": True,
                            "generated_at": now_iso(), "quote_revision": record.get("quote_revision")}
        return self._save(user_id, inquiry_id, revision, record, "draft_generated")

    def create_followup(self, user_id: str, inquiry_id: str, revision: int,
                        title: str, due_at: str, zone: str) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        if record.get("replied_at"):
            raise InquiryError(409, "买家已回复，原跟进计划已停止；请先处理新需求")
        task = {"id": "fu_" + uuid4().hex, "title": title.strip(),
                "due_at": normalize_due_at(due_at, zone), "timezone": zone,
                "status": "pending", "created_at": now_iso(), "completed_at": None,
                "cancelled_at": None, "cancellation_reason": None}
        if not task["title"]:
            raise InquiryError(422, "跟进标题不能为空")
        record["followups"].append(task)
        return self._save(user_id, inquiry_id, revision, record, "followup_created",
                          {"followup_id": task["id"]})

    def update_followup(self, user_id: str, inquiry_id: str, revision: int,
                        task_id: str, status: str) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        task = next((task for task in record["followups"] if task["id"] == task_id), None)
        if task is None:
            raise InquiryError(404, "跟进待办不存在或无权访问")
        if task["status"] != "pending":
            raise InquiryError(409, "该待办已结束，不能再次更改")
        if status not in {"completed", "cancelled"}:
            raise InquiryError(422, "跟进状态无效")
        task["status"] = status
        task["completed_at" if status == "completed" else "cancelled_at"] = now_iso()
        if status == "cancelled":
            task["cancellation_reason"] = "user_cancelled"
        return self._save(user_id, inquiry_id, revision, record, "followup_" + status,
                          {"followup_id": task_id})

    def mark_replied(self, user_id: str, inquiry_id: str, revision: int) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        record["replied_at"] = now_iso()
        for task in record["followups"]:
            if task["status"] == "pending":
                task.update(status="cancelled", cancelled_at=record["replied_at"],
                            cancellation_reason="buyer_replied")
        return self._save(user_id, inquiry_id, revision, record, "buyer_replied")

    def resume_followups(self, user_id: str, inquiry_id: str, revision: int) -> dict:
        record = self._load(user_id, inquiry_id, revision)
        record["replied_at"] = None
        # Completed/cancelled tasks deliberately remain closed.
        return self._save(user_id, inquiry_id, revision, record, "followups_resumed")


def build_drafts(record: dict) -> dict:
    company = record.get("buyer", {}).get("company_name", "").strip()
    greeting_zh = f"{company} 团队，您好：" if company else "您好："
    greeting_en = f"Dear {company} team," if company else "Dear customer,"
    quote = record.get("quote")
    if quote and quote.get("ok"):
        data = quote["data"]
        zh_lines = [f"- {line['sku']}：{line['quantity']} 件，货品单价 USD {line['unit_price']}，"
                    f"每件包装费 USD {line['packaging_unit_surcharge']}，行小计 USD {line['line_subtotal']}。"
                    for line in data["items"]]
        en_lines = [f"- {line['sku']}: {line['quantity']} units; goods USD {line['unit_price']}/unit; "
                    f"packaging USD {line['packaging_unit_surcharge']}/unit; line subtotal USD {line['line_subtotal']}."
                    for line in data["items"]]
        warning_zh = ("您要求的生产时间短于参考生产周期，当前不能承诺该交期，请确认是否可调整。"
                      if data["requested_delivery_status"] == "cannot_meet_production_window" else
                      "实际生产时间与到货日期均须另行确认；生产周期不包含运输时间。")
        warning_en = ("Your requested production window is shorter than the reference estimate and cannot be promised. "
                      "Please confirm whether it can be adjusted."
                      if data["requested_delivery_status"] == "cannot_meet_production_window" else
                      "Actual production and arrival dates require separate confirmation; transit is excluded.")
        zh = (f"【演示回复草稿，未发送；所有产品和价格为模拟数据】\n{greeting_zh}\n"
              "感谢您的询盘。根据已确认的产品、数量和包装要求，参考报价如下：\n" + "\n".join(zh_lines) +
              f"\n货值 USD {data['merchandise_subtotal']}；包装费 USD {data['packaging_subtotal']}；"
              f"合计 USD {data['subtotal']}（不含运费、税费及关税）。\n"
              f"目的国：{data['destination_country']}；参考生产周期：{data['production_lead_days']} 天。{warning_zh}\n"
              f"报价编号：{data['quote_id']}。运费、付款条件及报价有效期均待确认。\n"
              "如需定制，请提供包装设计要求及交货地址。该资料仅用于演示，不构成可执行销售承诺。")
        en = (f"[DEMO DRAFT — NOT SENT. All products and prices are simulated.]\n{greeting_en}\n"
              "Thank you for your inquiry. Based on the confirmed items, quantities and packaging requirements:\n" +
              "\n".join(en_lines) + f"\nGoods USD {data['merchandise_subtotal']}; packaging USD {data['packaging_subtotal']}; "
              f"subtotal USD {data['subtotal']}, excluding freight, taxes and duties.\n"
              f"Destination: {data['destination_country']}. Reference production: {data['production_lead_days']} days. "
              f"{warning_en}\nQuote reference: {data['quote_id']}. Freight, payment terms and quote validity remain unconfirmed.\n"
              "Please provide artwork requirements and a delivery address if customization is required. "
              "This demonstration does not constitute a binding sales offer.")
        kind = "quote"
    else:
        zh = (f"【演示回复草稿，未发送】\n{greeting_zh}\n感谢您的询盘。为准备准确的报价，"
              "请确认产品型号、各型号采购数量、标准或定制包装、目的国和期望生产时间。"
              "我们将核对起订量、包装条件及生产周期后再提供报价；运费、税费与实际交期需另行确认。")
        en = (f"[DEMO DRAFT — NOT SENT]\n{greeting_en}\nThank you for your inquiry. To prepare a quotation, "
              "please confirm each product SKU, quantity, standard or custom packaging, destination country "
              "and requested production window. MOQ, packaging terms and production availability require verification. "
              "Freight, taxes and actual delivery dates remain to be confirmed.")
        kind = "clarification"
    return {"zh": zh, "en": en, "kind": kind, "method": "deterministic_template",
            "quote_revision": record.get("quote_revision"), "stale": False,
            "not_sent": True, "generated_at": now_iso()}
