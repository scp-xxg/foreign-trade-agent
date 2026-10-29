"""Create an unconfirmed content pack for the same fictional DESK-001 item."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import foreign_trade
from foreign_trade.engine import get_product
from core.db.models.foreign_trade_content import ForeignTradeContentPack
from core.files.artifacts.service import store_bytes_as_artifact
from core.files.storage import get_storage
from core.foreign_trade.content import parse_upload
from core.foreign_trade.inquiry import now_iso


def create_catalog_content(db, user_id: str, inquiry: dict) -> tuple[str, list[str]]:
    """Flush into the caller's transaction; never confirm facts or generate outputs."""
    items = inquiry.get("items", [])
    if len(items) != 1 or items[0].get("sku") != "DESK-001":
        raise ValueError("自动资料包当前仅支持单一 DESK-001 模拟产品；其他产品请关联独立参考资料")
    product = get_product("DESK-001")["data"]
    folder = Path(foreign_trade.__file__).parent / "demo_product"
    manifest = json.loads((folder / "desk-001-demo-sources.json").read_text())
    identifier, timestamp = "pack_" + uuid4().hex, now_iso()
    documents, candidates, keys, texts = [], [], [], []
    try:
        for name in ("desk-001-demo-specs.csv", "desk-001-demo-schematic.png"):
            content = (folder / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != manifest["files"][name]:
                raise ValueError("模拟资料包校验失败")
            parsed = parse_upload(name, content)
            artifact = store_bytes_as_artifact(db, user_id=user_id, content=parsed["content"],
                filename=identifier + "-" + name, mime_type=parsed["mime_type"],
                parsed_text=parsed["text"], source="foreign_trade_simulated_catalog",
                extra={"pack_id": identifier, "is_simulated": True}, commit=False)
            keys.append(artifact.storage_key)
            documents.append({"file_id": artifact.artifact_id, "name": name, "kind": parsed["kind"],
                "mime_type": parsed["mime_type"], "size": len(parsed["content"]),
                "sha256": hashlib.sha256(parsed["content"]).hexdigest(),
                "url": f"/api/v1/foreign-trade/content-packs/{identifier}/files/{artifact.artifact_id}",
                "text": parsed["text"], "uploaded_at": timestamp,
                **{k: parsed[k] for k in ("width", "height") if k in parsed}})
            candidates.extend(parsed["suggested_facts"])
            texts.append(parsed["text"])
        payload = {"title": "DESK-001 模拟订单产品资料", "product_name": product["name"],
            "brand": "", "model": "DESK-001", "source_url": "", "raw_text": "\n\n".join(texts),
            "facts": [], "suggested_facts": candidates, "image_credit": manifest["image_credit"],
            "documents": documents, "outputs": None,
            "warnings": ["规格来自模拟目录；图片为程序绘制的虚构几何示意图，不是真实照片或实际结构证据。"],
            "catalog_binding": {"sku": "DESK-001", "product_name": product["name"],
                "record_ref": product["source"]["record_ref"], "is_simulated": True,
                "allowed_facts": deepcopy(candidates)}}
        db.add(ForeignTradeContentPack(pack_id=identifier, owner_user_id=user_id, revision=1,
                                      payload=payload, created_at=timestamp, updated_at=timestamp))
        db.flush()
        return identifier, keys
    except Exception:
        db.rollback()
        for key in keys:
            try:
                get_storage().delete(key)
            except Exception:
                pass
        raise
