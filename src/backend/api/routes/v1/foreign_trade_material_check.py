"""Authenticated direct composer scan; no model call or chat message mutation."""
import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from core.auth.backend import UserContext,get_current_user
from core.db.engine import SessionLocal
from core.db.models import Artifact
from core.files.storage import get_storage
from core.foreign_trade.content import parse_upload, ContentPackError, MAX_UPLOAD
from core.foreign_trade.material_check import prepare
from core.infra.responses import success_response
router=APIRouter()

@router.post('/material-check')
async def material_check(text: str=Form(''), file_ids: str=Form('[]'), files: list[UploadFile]=File(default=[]), user: UserContext=Depends(get_current_user)):
    try:
        ids=json.loads(file_ids)
        if not isinstance(ids,list) or any(not isinstance(x,str) or not x or len(x)>200 for x in ids) or len(set(ids))!=len(ids):raise ValueError('附件标识无效')
        if len(ids)+len(files)>10:raise ValueError('一次最多检查10个文件')
        if len(text)>200000:raise ValueError('输入文字超过20万字符，请拆分')
        if not text.strip() and not ids and not files:raise ValueError('请先输入文字或添加文件')
        raw=[];total=0
        for i,f in enumerate(files):
            content=await f.read(MAX_UPLOAD+1);total+=len(content)
            if len(content)>MAX_UPLOAD:raise ContentPackError(413,'单文件不能超过8MiB')
            raw.append((f'local-{i}',f.filename or 'file.txt',content))
        def work():
            nonlocal total
            # Explicit selection authorizes reading the current user's imported files even before sending a chat turn.
            with SessionLocal() as db:
                for fid in ids:
                    a=db.query(Artifact).filter_by(artifact_id=fid,user_id=user.user_id).first()
                    if a is None or a.deleted_at is not None:raise ContentPackError(404,'文件不存在或无权访问')
                    if not 0<a.size_bytes<=MAX_UPLOAD:raise ContentPackError(413,'单文件不能超过8MiB')
                    content=get_storage().download_bytes(a.storage_key)
                    if not content or len(content)>MAX_UPLOAD:raise ContentPackError(413,'文件为空或过大')
                    total+=len(content);raw.append((fid,a.filename,content))
            if total>32*1024*1024:raise ContentPackError(413,'一次检查文件合计不能超过32MiB')
            attachments=[(fid,name,parse_upload(name,content)) for fid,name,content in raw]
            return prepare('sensitive',{'fields':[{'id':'composer','text':text,'placement':'输入框文字'}] if text.strip() else []},attachments)
        return success_response(data=await run_in_threadpool(work))
    except ContentPackError as exc:raise HTTPException(status_code=exc.status,detail=str(exc)) from None
    except (ValueError,TypeError,KeyError):raise HTTPException(status_code=422,detail='检查资料无效，请确认文字、文件数量与格式。') from None
    finally:
        for f in files:await f.close()
