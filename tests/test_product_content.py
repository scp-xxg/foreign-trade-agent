"""Product workspace checks use an isolated DB and in-memory artifact storage."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
import zipfile

import pytest
from PIL import Image, PngImagePlugin
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from core.db.models import Artifact, ForeignTradeContentPack, UserFolder, UserShadow
from core.foreign_trade import content as content
from core.foreign_trade import content_generation as generation
from api.routes.v1 import foreign_trade_content as routes


class MemoryStorage:
    def __init__(self): self.files = {}
    def upload_bytes(self, payload, key):
        self.files[key] = payload
        return "memory:" + key
    def download_bytes(self, key): return self.files[key]
    def delete(self, key): self.files.pop(key, None)


@pytest.fixture
def context(monkeypatch):
    import core.files.storage
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ForeignTradeContentPack.__table__.create(bind=engine)
    Artifact.__table__.create(bind=engine)
    UserFolder.__table__.create(bind=engine)
    UserShadow.__table__.create(bind=engine)
    storage = MemoryStorage()
    monkeypatch.setattr(content, "get_storage", lambda: storage)
    monkeypatch.setattr(core.files.storage, "get_storage", lambda: storage)
    with Session(engine) as db:
        yield content.ContentPackService(db), storage, engine
    engine.dispose()


def png_bytes():
    stream = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-note", "must be removed")
    Image.new("RGB", (80, 50), "green").save(stream, format="PNG", pnginfo=metadata)
    return stream.getvalue()


def confirmed_pack(svc):
    record = svc.create("alice", "Product pack")
    return svc.update("alice", record["pack_id"], 1, {
        "product_name": "Demonstration board", "source_url": "https://example.com/specs",
        "facts": [{"label": "Processor", "value": "2.4 GHz CPU", "source_url": "https://example.com/specs"}],
        "image_credit": "Original example photo, permission confirmed by operator",
    })


def fake_output():
    return {"listing": {"title": "Demo", "bullets": ["2.4 GHz CPU"], "description": "Verified input only"},
            "faq": [{"question": "Processor?", "answer": "2.4 GHz CPU", "source_refs": [1]}],
            "translated_facts": [{"label": "Processor", "value": "2.4 GHz CPU", "source_refs": [1]}],
            "method": "template", "warnings": [], "assets": [], "generated_at": "2026-10-21T10:00:00Z",
            "not_published": True}


def test_csv_upload_proposes_facts_without_confirming_them(context):
    svc, storage, _ = context
    record = svc.create("alice", "New")
    payload = b"label,value,source_url\nProcessor,2.4 GHz CPU,https://example.com/specs\n"
    record = svc.upload("alice", record["pack_id"], 1, "../specs.csv", payload)
    assert record["documents"][0]["name"] == "specs.csv"
    assert record["facts"] == [] and record["suggested_facts"][0]["value"] == "2.4 GHz CPU"
    assert "Processor" in record["raw_text"] and "人工确认" in "".join(record["warnings"])
    assert len(storage.files) == 1
    file = record["documents"][0]
    assert svc.read_file("alice", record["pack_id"], file["file_id"])[0] == payload


def test_bilingual_csv_template_column_mapping():
    text = "key,label_zh,label_en,value_zh,value_en,source_url\nprocessor,处理器,Processor,2.4 GHz CPU,2.4 GHz CPU,https://example.com\n"
    parsed = content.parse_upload("facts.csv", text.encode("utf-8-sig"))
    assert parsed["suggested_facts"] == [{"label": "处理器", "value": "2.4 GHz CPU", "source_url": "https://example.com"}]


def test_csv_formula_is_text_not_executed():
    parsed = content.parse_upload("facts.csv", b'label,value,source_url\nLiteral,=1+1,\n')
    assert parsed["suggested_facts"][0]["value"] == "=1+1"


def test_image_normalized_metadata_removed_and_not_ocr():
    parsed = content.parse_upload("picture.png", png_bytes())
    assert parsed["kind"] == "image" and parsed["mime_type"] == "image/png"
    with Image.open(BytesIO(parsed["content"])) as image:
        assert "private-note" not in image.info
        assert image.size == (80, 50)
    assert parsed["suggested_facts"] == [] and parsed["text"] == ""
    assert any("OCR" in warning for warning in parsed["warnings"])


@pytest.mark.parametrize("filename,payload", [("evil.svg", b"<svg/>"), ("fake.jpg", b"<html>fake</html>"),
                                               ("payload.exe", b"x"), ("fake.pdf", b"not a pdf"),
                                               ("bad.txt", b"\xff\xfe"), ("bad.txt", b"a\x00b"),
                                               ("bad.json", b"{unclosed"), ("empty.txt", b"")])
def test_invalid_or_executable_upload_rejected(filename, payload):
    with pytest.raises(content.ContentPackError): content.parse_upload(filename, payload)


def test_upload_bytes_cap():
    with pytest.raises(content.ContentPackError) as caught:
        content.parse_upload("large.txt", b"a" * (content.MAX_UPLOAD + 1))
    assert caught.value.status == 413


def test_text_truncation_is_explicit():
    parsed = content.parse_upload("long.txt", ("x" * 61000).encode())
    assert len(parsed["text"]) == 60000
    assert any("截断" in warning for warning in parsed["warnings"])


def test_zip_bomb_and_external_xlsx_links_rejected():
    for member in ["xl/externalLinks/externalLink1.xml", "xl/vbaProject.bin", "../escape.xml"]:
        data = BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("[Content_Types].xml", "x")
            archive.writestr("xl/workbook.xml", "x")
            archive.writestr(member, "x")
        with pytest.raises(content.ContentPackError): content.parse_upload("bad.xlsx", data.getvalue())
    data = BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("xl/workbook.xml", b"x" * 2_000_000)
    with pytest.raises(content.ContentPackError): content.parse_upload("bomb.xlsx", data.getvalue())


def test_xlsx_formula_never_evaluated():
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(["label", "value", "source_url"])
    book.active.append(["Calculated", "=1+1", "https://example.com"])
    output = BytesIO(); book.save(output)
    parsed = content.parse_upload("facts.xlsx", output.getvalue())
    assert "[公式未求值]" in parsed["text"]
    assert any("公式未计算" in warning for warning in parsed["warnings"])


def test_pdf_text_and_scanned_pdf_limitation():
    from pypdf import PdfWriter
    writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
    output = BytesIO(); writer.write(output)
    parsed = content.parse_upload("scan.pdf", output.getvalue())
    assert parsed["text"].strip() == ""
    assert any("未执行 OCR" in warning for warning in parsed["warnings"])


def test_owner_isolation_and_revision_cas(context):
    svc, _, engine = context
    record = svc.create("alice", "Product")
    assert svc.list("bob") == []
    for fn in [lambda: svc.get("bob", record["pack_id"]),
               lambda: svc.update("bob", record["pack_id"], 1, {"title": "other"}),
               lambda: svc.upload("bob", record["pack_id"], 1, "text.txt", b"x")]:
        with pytest.raises(content.ContentPackError) as caught: fn()
        assert caught.value.status == 404
    pending = svc._load("alice", record["pack_id"], 1)
    with Session(engine) as db:
        content.ContentPackService(db).update("alice", record["pack_id"], 1, {"title": "new"})
    with pytest.raises(content.ContentPackError) as caught:
        svc._save("alice", record["pack_id"], 1, pending)
    assert caught.value.status == 409 and svc.get("alice", record["pack_id"])["title"] == "new"


def test_file_id_is_scoped_to_pack_and_owner(context):
    svc, _, _ = context
    record = svc.create("alice", "One")
    record = svc.upload("alice", record["pack_id"], 1, "one.txt", b"product source")
    file_id = record["documents"][0]["file_id"]
    other = svc.create("alice", "Two")
    for owner, pack in [("bob", record["pack_id"]), ("alice", other["pack_id"])]:
        with pytest.raises(content.ContentPackError) as caught: svc.read_file(owner, pack, file_id)
        assert caught.value.status == 404


def test_external_file_overwrite_detected(context):
    svc, storage, _ = context
    record = svc.create("alice", "One")
    record = svc.upload("alice", record["pack_id"], 1, "one.txt", b"product source")
    key = next(iter(storage.files)); storage.files[key] = b"overwritten elsewhere"
    with pytest.raises(content.ContentPackError) as caught:
        svc.read_file("alice", record["pack_id"], record["documents"][0]["file_id"])
    assert caught.value.status == 409


def test_failed_upload_cas_cleans_only_new_artifact(context, monkeypatch):
    svc, storage, _ = context
    record = svc.create("alice", "One")
    record = svc.upload("alice", record["pack_id"], 1, "first.txt", b"keep")
    original_keys = set(storage.files)
    def conflict(*args): raise content.ContentPackError(409, "changed")
    monkeypatch.setattr(svc, "_save", conflict)
    with pytest.raises(content.ContentPackError):
        svc.upload("alice", record["pack_id"], record["revision"], "second.txt", b"discard")
    assert set(storage.files) == original_keys
    assert svc.db.query(Artifact).count() == 1


@pytest.mark.asyncio
async def test_generate_requires_confirmed_facts_and_never_promotes_uploads(context, monkeypatch):
    svc, _, _ = context
    call = AsyncMock(return_value=fake_output()); monkeypatch.setattr(generation, "generate_pack", call)
    record = svc.create("alice", "One")
    record = svc.upload("alice", record["pack_id"], 1, "facts.csv", b"label,value\nProcessor,2.4 GHz CPU\n")
    record = svc.update("alice", record["pack_id"], record["revision"], {"product_name": "Board"})
    for confirm in [False, True]:
        with pytest.raises(content.ContentPackError):
            await svc.generate("alice", record["pack_id"], record["revision"], confirm)
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_current_outputs_and_input_change_invalidates_download(context, monkeypatch):
    svc, _, _ = context
    monkeypatch.setattr(generation, "generate_pack", AsyncMock(return_value=fake_output()))
    record = confirmed_pack(svc)
    record = await svc.generate("alice", record["pack_id"], record["revision"], True)
    assert record["outputs"]["not_published"] is True and record["outputs"]["source_revision"] == 2
    assert b"2.4 GHz CPU" in svc.download("alice", record["pack_id"], "listing")[0]
    record = svc.update("alice", record["pack_id"], record["revision"], {"title": "Renamed"})
    assert record["outputs"] is None
    with pytest.raises(content.ContentPackError) as caught: svc.download("alice", record["pack_id"], "listing")
    assert caught.value.status == 409


@pytest.mark.asyncio
async def test_slow_generation_cannot_replace_new_inputs(context, monkeypatch):
    svc, _, engine = context
    record = confirmed_pack(svc)
    async def delayed(*args):
        with Session(engine) as db:
            content.ContentPackService(db).update("alice", record["pack_id"], record["revision"], {"product_name": "New product"})
        return fake_output()
    monkeypatch.setattr(generation, "generate_pack", delayed)
    with pytest.raises(content.ContentPackError) as caught:
        await svc.generate("alice", record["pack_id"], record["revision"], True)
    assert caught.value.status == 409
    assert svc.get("alice", record["pack_id"])["outputs"] is None


@pytest.mark.asyncio
async def test_last_uploaded_image_used_and_credit_required(context, monkeypatch):
    svc, _, _ = context
    record = confirmed_pack(svc)
    record = svc.upload("alice", record["pack_id"], record["revision"], "one.png", png_bytes())
    record = svc.update("alice", record["pack_id"], record["revision"], {"image_credit": ""})
    call = AsyncMock(return_value=fake_output()); monkeypatch.setattr(generation, "generate_pack", call)
    with pytest.raises(content.ContentPackError, match="授权"):
        await svc.generate("alice", record["pack_id"], record["revision"], True)
    call.assert_not_awaited()
    record = svc.update("alice", record["pack_id"], record["revision"], {"image_credit": "Operator supplied original"})
    await svc.generate("alice", record["pack_id"], record["revision"], True)
    assert call.await_args.args[1].startswith(b"\x89PNG")


@pytest.fixture
def api(context):
    _, _, engine = context
    app = FastAPI(); app.include_router(routes.router, prefix="/api")
    def get_db():
        with Session(engine) as db: yield db
    app.dependency_overrides[routes.get_db] = get_db
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="alice")
    with TestClient(app) as client: yield client, app


def test_api_upload_confirm_generate_download_contract(api, monkeypatch):
    client, app = api
    monkeypatch.setattr(generation, "generate_pack", AsyncMock(return_value=fake_output()))
    record = client.post("/api/v1/foreign-trade/content-packs", json={"title": "Product"}).json()["data"]
    root = f"/api/v1/foreign-trade/content-packs/{record['pack_id']}"
    response = client.post(root + "/upload", data={"revision": "1"}, files={"file": ("facts.csv", b"label,value\nProcessor,2.4 GHz CPU\n", "text/csv")})
    assert response.status_code == 200
    record = response.json()["data"]
    assert record["facts"] == []
    record = client.patch(root, json={"revision": 2, "product_name": "Board", "facts": record["suggested_facts"]}).json()["data"]
    response = client.post(root + "/generate", json={"revision": 3, "confirmed": True})
    assert response.status_code == 200
    assert client.get(root + "/download/listing?revision=4").status_code == 200
    assert client.get(root + "/download/listing?revision=3").status_code == 409
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="bob")
    assert client.get(root + "/download/listing").status_code == 404
    assert client.get(record["documents"][0]["url"]).status_code == 404


def test_api_explicit_template_retains_owner_confirmation_and_revision_guards(api, monkeypatch):
    client, app = api
    model = AsyncMock(side_effect=AssertionError("Offline template must not call a model"))
    monkeypatch.setattr(generation, "_translate", model)
    record = client.post("/api/v1/foreign-trade/content-packs", json={"title": "Offline template"}).json()["data"]
    path = f"/api/v1/foreign-trade/content-packs/{record['pack_id']}"
    assert client.post(path + "/generate", json={"revision": 1, "confirmed": True, "generation_mode": "template"}).status_code == 422
    record = client.patch(path, json={"revision": 1, "product_name": "Board",
        "facts": [{"label": "USB", "value": "2 USB 3.0 ports", "source_url": "https://example.com/spec"}]}).json()["data"]
    assert client.post(path + "/generate", json={"revision": 2, "confirmed": False, "generation_mode": "template"}).status_code == 422
    assert client.post(path + "/generate", json={"revision": 2, "confirmed": True, "generation_mode": "unknown"}).status_code == 422
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="bob")
    assert client.post(path + "/generate", json={"revision": 2, "confirmed": True, "generation_mode": "template"}).status_code == 404
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="alice")
    response = client.post(path + "/generate", json={"revision": 2, "confirmed": True, "generation_mode": "template"})
    assert response.status_code == 200
    output = response.json()["data"]["outputs"]
    assert output["method"] == "template" and output["generation_mode"] == "template"
    assert output["warnings"][0] == generation.LOCAL_TEMPLATE_NOTICE
    assert client.post(path + "/generate", json={"revision": 2, "confirmed": True, "generation_mode": "template"}).status_code == 409
    model.assert_not_awaited()


def test_api_fact_bounds_and_null_rejection(api):
    client, _ = api
    record = client.post("/api/v1/foreign-trade/content-packs", json={"title": "Product"}).json()["data"]
    root = f"/api/v1/foreign-trade/content-packs/{record['pack_id']}"
    for update in [{"facts": [{"label": "x", "value": "y"}] * 21}, {"facts": [{"label": "x", "value": " "}]},
                   {"facts": None}, {"source_url": "javascript:alert(1)"}, {"image_credit": None}, {"image_credit": "x" * 601}]:
        assert client.patch(root, json={"revision": 1, **update}).status_code == 422


def test_api_image_attribution_accepts_600_and_rejects_601(api):
    client, _ = api
    record = client.post("/api/v1/foreign-trade/content-packs", json={"title": "Product"}).json()["data"]
    root = f"/api/v1/foreign-trade/content-packs/{record['pack_id']}"
    assert client.patch(root, json={"revision": 1, "image_credit": "x" * 601}).status_code == 422
    response = client.patch(root, json={"revision": 1, "image_credit": "x" * 600})
    assert response.status_code == 200 and len(response.json()["data"]["image_credit"]) == 600


def test_image_export_failure_is_explicit_422(context, monkeypatch):
    svc, _, _ = context
    record = confirmed_pack(svc)
    record = svc.upload("alice", record["pack_id"], record["revision"], "photo.png", png_bytes())
    record["outputs"] = fake_output()
    record = svc._save("alice", record["pack_id"], record["revision"], record)
    def cannot_render(*args): raise ValueError("Untranslated output cannot be rendered")
    monkeypatch.setattr(generation, "export_pack", cannot_render)
    with pytest.raises(content.ContentPackError) as caught:
        svc.download("alice", record["pack_id"], "square")
    assert caught.value.status == 422


def test_pdf_extracts_actual_text_with_page_separation():
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer = PdfWriter()
    for message in ["Product source one", "Product source two"]:
        page = writer.add_blank_page(width=200, height=100)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(("BT /F1 12 Tf 10 10 Td (" + message + ") Tj ET").encode())
        page[NameObject("/Contents")] = stream
    output = BytesIO(); writer.write(output)
    text = content.parse_upload("source.pdf", output.getvalue())["text"]
    assert "Product source one" in text and "Product source two" in text
    assert "\n" in text
