"""Owner-scoped checkpoints for the optional acquisition workspace, not verified facts."""
from copy import deepcopy
import json
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from core.db.models.foreign_trade import AcquisitionProgress
from core.foreign_trade.inquiry import now_iso

class SaveProgress(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=0)
    payload: dict

    @field_validator('payload')
    @classmethod
    def bounded(cls, value):
        fields = {'product','markets','buyers','constraints','profileText','confirmed','run','dossiers','contacts','reviews','leads','excluded'}
        if set(value) - fields:
            raise ValueError('进度包含不支持的字段')
        if len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode()) > 2 * 1024 * 1024:
            raise ValueError('进度不能超过2MiB')
        for key in ('product','markets','buyers','constraints','profileText','excluded'):
            if key in value and (not isinstance(value[key],str) or len(value[key])>100000):
                raise ValueError('表单字段须为不超过100000字符的文本')
        for key in ('dossiers','contacts','reviews','leads'):
            if key in value and (not isinstance(value[key],dict) or len(value[key])>50):
                raise ValueError('每次进度最多包含50家买家')
        if 'confirmed' in value and not isinstance(value['confirmed'],bool):
            raise ValueError('确认状态须为布尔值')
        if value.get('run') is not None:
            from core.foreign_trade.buyer_search import domain
            run=value['run']
            if not isinstance(run,dict) or not isinstance(run.get('candidates'),list) or len(run['candidates'])>50:
                raise ValueError('搜索进度格式无效')
            for c in run['candidates']:
                if not isinstance(c,dict) or not isinstance(c.get('id'),str) or not isinstance(c.get('name'),str) or not domain(c.get('discovery_url','')):
                    raise ValueError('候选买家格式无效')
        run=value.get('run')
        if run is not None:
            if not isinstance(run.get('warnings',[]),list) or any(not isinstance(w,str) for w in run.get('warnings',[])):
                raise ValueError('搜索警告格式无效')
            run.setdefault('warnings',[])
        for contact in value.get('contacts',{}).values():
            if not isinstance(contact,dict) or any(not isinstance(contact.get(k),list) for k in ('channels','warnings','unresolved')):
                raise ValueError('联系人进度格式无效')
            if any(not isinstance(c,dict) or any(not isinstance(c.get(k),str) for k in ('channel','type','source_url','retrieved_at')) for c in contact['channels']):
                raise ValueError('联系渠道格式无效')
            if any(not isinstance(w,str) for w in [*contact['warnings'],*contact['unresolved']]):
                raise ValueError('联系人提示格式无效')
        for review in value.get('reviews',{}).values():
            if not isinstance(review,dict) or review.get('decision') not in {'suitable','unsuitable','unknown'} or not isinstance(review.get('reason'),str):
                raise ValueError('审核进度格式无效')
        return value

def read_progress(db, user_id):
    row=db.get(AcquisitionProgress,user_id)
    return {'revision':row.revision,'payload':deepcopy(row.payload),'updated_at':row.updated_at,'is_checkpoint':True} if row else {'revision':0,'payload':None,'updated_at':None,'is_checkpoint':True}

def save_progress(db,user_id,req):
    timestamp=now_iso()
    if req.revision==0:
        db.add(AcquisitionProgress(owner_user_id=user_id,revision=1,payload=deepcopy(req.payload),updated_at=timestamp))
        try: db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'进度已存在，请先恢复最新进度') from None
    else:
        changed=db.execute(update(AcquisitionProgress).where(AcquisitionProgress.owner_user_id==user_id,AcquisitionProgress.revision==req.revision).values(revision=req.revision+1,payload=deepcopy(req.payload),updated_at=timestamp)).rowcount
        if changed!=1:
            db.rollback();raise HTTPException(409,'进度已变化，请先恢复最新进度')
        db.commit()
    db.expire_all()
    return read_progress(db,user_id)
