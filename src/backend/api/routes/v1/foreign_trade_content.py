"""Owner-authenticated product content uploads, confirmation, generation and export."""
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from core.auth.backend import UserContext, get_current_user
from core.db.engine import get_db
from core.infra.responses import created_response, success_response
from core.services.foreign_trade_content import ContentPackError, ContentPackService, MAX_UPLOAD, demo_file

router = APIRouter(prefix="/v1/foreign-trade/content-packs", tags=["Product content packs"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreatePack(StrictRequest):
    title: str = Field(default="新品资料包", min_length=1, max_length=200)


class ProductFact(StrictRequest):
    label: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=1500)
    source_url: str = Field(default="", max_length=2000)

    @field_validator("label", "value")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("产品事实不能为空")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def source_url_is_public_link(cls, value):
        if value and not value.lower().startswith(("https://", "http://")):
            raise ValueError("来源必须为 HTTP/HTTPS 链接或留空引用上传资料")
        return value


class RevisionRequest(StrictRequest):
    revision: StrictInt = Field(gt=0)


class UpdatePack(RevisionRequest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    product_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=2000)
    raw_text: str | None = Field(default=None, max_length=100000)
    facts: list[ProductFact] | None = Field(default=None, max_length=20)
    image_credit: str | None = Field(default=None, max_length=600)

    @field_validator("title", "product_name", "brand", "model", "source_url", "raw_text", "facts", "image_credit")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("字段不能为 null")
        return value

    @field_validator("source_url")
    @classmethod
    def source_is_link(cls, value):
        return ProductFact.source_url_is_public_link(value)


class GeneratePack(RevisionRequest):
    confirmed: StrictBool


def _call(fn, *args):
    try:
        return fn(*args)
    except ContentPackError as exc:
        raise HTTPException(status_code=exc.status, detail={"message": exc.message}) from None


def _file_response(data, inline=False):
    content, mime, filename = data
    disposition = "inline" if inline else "attachment"
    return Response(content, media_type=mime, headers={
        "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(filename),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get("")
def list_packs(limit: int = Query(default=100, ge=1, le=200),
               user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(ContentPackService(db).list, user.user_id, limit))


@router.post("")
def create_pack(req: CreatePack, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return created_response(data=_call(ContentPackService(db).create, user.user_id, req.title))


@router.get("/demo/{kind}")
def download_demo(kind: Literal["txt", "csv", "photo"], user: UserContext = Depends(get_current_user)):
    return _file_response(_call(demo_file, kind))


@router.get("/{pack_id}")
def get_pack(pack_id: str, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(ContentPackService(db).get, user.user_id, pack_id))


@router.patch("/{pack_id}")
def update_pack(pack_id: str, req: UpdatePack, user: UserContext = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return success_response(data=_call(ContentPackService(db).update, user.user_id, pack_id, req.revision,
                                      req.model_dump(exclude_unset=True, exclude={"revision"})))


@router.post("/{pack_id}/upload")
async def upload(pack_id: str, revision: int = Form(..., ge=1), file: UploadFile = File(...),
                 user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    service = ContentPackService(db)
    _call(service._load, user.user_id, pack_id, revision)
    try:
        content = await file.read(MAX_UPLOAD + 1)
        result = await run_in_threadpool(_call, service.upload, user.user_id, pack_id, revision,
                                        file.filename or "", content)
    finally:
        await file.close()
    return success_response(data=result)


@router.get("/{pack_id}/files/{file_id}")
def download_source(pack_id: str, file_id: str, user: UserContext = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    data = _call(ContentPackService(db).read_file, user.user_id, pack_id, file_id)
    return _file_response(data, inline=data[1] == "image/png")


@router.post("/{pack_id}/generate")
async def generate(pack_id: str, req: GeneratePack, user: UserContext = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    try:
        record = await ContentPackService(db).generate(user.user_id, pack_id, req.revision, req.confirmed)
    except ContentPackError as exc:
        raise HTTPException(status_code=exc.status, detail={"message": exc.message}) from None
    return success_response(data=record)


@router.get("/{pack_id}/download/{kind}")
def download(pack_id: str, kind: Literal["zip", "listing", "faq", "square", "landscape", "spec"],
             revision: int | None = Query(default=None, ge=1), user: UserContext = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return _file_response(_call(ContentPackService(db).download, user.user_id, pack_id, kind, revision))
