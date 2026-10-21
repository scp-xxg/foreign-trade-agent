"""Offline content grounding, attribution and download checks."""
import io
import json
import zipfile

import pytest
from PIL import Image
from core.services import foreign_trade_content_generation as generation


@pytest.fixture
def pack():
    return {"product_name": "Raspberry Pi 5", "brand": "Raspberry Pi", "model": "5",
            "revision": 2, "source_url": "https://www.raspberrypi.com/products/raspberry-pi-5/",
            "image_credit": "Photo: Example Author / CC BY 4.0 / https://creativecommons.org/licenses/by/4.0/",
            "facts": [{"label": "USB", "value": "2 USB 3.0 ports", "source_url": "https://example.org/spec"}]}


def photo():
    stream = io.BytesIO()
    Image.new("RGB", (640, 400), "#228866").save(stream, "PNG")
    return stream.getvalue()


async def test_grounded_generation_and_all_downloads(monkeypatch, pack):
    async def model(facts):
        return {"facts": [{"index": 1, "label": "USB", "value": "2 USB 3.0 ports"}]}
    monkeypatch.setattr(generation, "_translate", model)
    pack["outputs"] = await generation.generate_pack(pack, photo())
    assert pack["outputs"]["method"] == "ai_grounded"
    assert len(pack["outputs"]["assets"]) == 3
    assert pack["outputs"]["faq"][0]["source_refs"] == [1]
    content, mime, name = generation.export_pack(pack, "zip", photo())
    assert mime == "application/zip" and name.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert len(archive.namelist()) == 8
        assert "Example Author" in archive.read("provenance.txt").decode()
        assert "2 USB 3.0 ports" in archive.read("english-listing.md").decode()
        assert json.loads(archive.read("facts.json"))["facts"] == pack["facts"]
        for kind, w, h in generation.ASSETS:
            with Image.open(io.BytesIO(archive.read(f"product-{kind}.png"))) as image:
                assert image.size == (w, h)
                assert "CC BY 4.0" in image.info["Attribution"]
                assert "without cropping" in image.info["Processing"]


@pytest.mark.parametrize("row", [
    {"index": 1, "label": "USB", "value": "4 USB 3.0 ports"},
    {"index": 1, "label": "USB", "value": "2 USB 3.0 ports, free shipping"},
    {"index": 2, "label": "USB", "value": "2 USB 3.0 ports"},
    {"index": True, "label": "USB", "value": "2 USB 3.0 ports"},
    {"index": 1, "label": "USB接口", "value": "2 USB 3.0 ports"},
    {"index": 1, "label": "USB", "value": "<script>2 USB 3.0 ports</script>"},
])
def test_rejects_unsupported_translation(row, pack):
    with pytest.raises(ValueError):
        generation.validate_translations({"facts": [row]}, pack["facts"])


def test_missing_and_duplicate_facts_rejected(pack):
    with pytest.raises(ValueError):
        generation.validate_translations({"facts": []}, pack["facts"])
    row = {"index": 1, "label": "USB", "value": "2 USB 3.0 ports"}
    with pytest.raises(ValueError):
        generation.validate_translations({"facts": [row, row]}, pack["facts"] * 2)


async def test_failed_model_is_explicit_and_no_fake_images(monkeypatch, pack):
    async def fail(_):
        raise RuntimeError("sensitive provider detail must not leak")
    monkeypatch.setattr(generation, "_translate", fail)
    pack["outputs"] = await generation.generate_pack(pack)
    assert pack["outputs"]["method"] == "template"
    assert pack["outputs"]["assets"] == []
    assert "sensitive" not in json.dumps(pack["outputs"])
    assert "AI 翻译" in pack["outputs"]["warnings"][0]
    with pytest.raises(ValueError):
        generation.export_pack(pack, "square")
    data, _, _ = generation.export_pack(pack, "zip")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert len(archive.namelist()) == 5


@pytest.mark.parametrize("value", ["=WEBSERVICE(1)", " +cmd", "-1+1", "@SUM(1)", "\t=1", "\n=1"])
def test_csv_formula_protection(value):
    assert generation._csv_cell(value).startswith("'")


async def test_missing_facts_and_name_block_generation(pack):
    with pytest.raises(ValueError):
        await generation.generate_pack({**pack, "facts": []})
    with pytest.raises(ValueError):
        await generation.generate_pack({**pack, "product_name": ""})
    with pytest.raises(ValueError):
        generation.export_pack(pack, "zip")


@pytest.mark.parametrize("source,output", [
    ("2 USB 3.0 ports and 2 USB 2.0 ports", "3.0 USB 3.0 ports and 2 USB 2.0 ports"),
    ("5V input", "5A input"),
])
def test_number_multiplicity_and_unit_pairs(source, output):
    with pytest.raises(ValueError):
        generation.validate_translations({"facts": [{"index": 1, "label": "Specification", "value": output}]},
                                          [{"label": "Specification", "value": source}])


async def test_chinese_fallback_never_exports_broken_english_images(monkeypatch, pack):
    async def fail(_):
        raise RuntimeError("unavailable")
    monkeypatch.setattr(generation, "_translate", fail)
    pack["facts"][0]["label"] = "USB 接口"
    pack["outputs"] = await generation.generate_pack(pack, photo())
    assert pack["outputs"]["assets"] == []
    data, _, _ = generation.export_pack(pack, "zip", photo())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert not any(name.endswith(".png") for name in archive.namelist())
    with pytest.raises(ValueError):
        generation.export_pack(pack, "square", photo())


async def test_chinese_product_name_is_translated_and_refs_remain_original(monkeypatch, pack):
    pack["product_name"] = "树莓派 5"
    async def translate(_):
        return {"facts": [{"index": 1, "label": "Product name", "value": "Raspberry Pi 5"},
                          {"index": 2, "label": "USB", "value": "2 USB 3.0 ports"}]}
    monkeypatch.setattr(generation, "_translate", translate)
    result = await generation.generate_pack(pack, photo())
    assert result["listing"]["title"] == "Raspberry Pi 5"
    assert result["translated_facts"][0]["source_refs"] == [1]
