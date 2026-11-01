"""Current-user sensitive-term metadata and explicit text checking."""
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy.orm import Session
from core.auth.backend import UserContext,get_current_user
from core.db.engine import get_db
from core.infra.responses import success_response
from core.foreign_trade.lexicon import active_bundle,scan_fields,format_notice

router=APIRouter(prefix='/v1/foreign-trade/lexicon',tags=['Private sensitive terms'])
class ScanInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    fields:dict[str,str]=Field(min_length=1,max_length=100)

@router.get('')
def metadata(user:UserContext=Depends(get_current_user),db:Session=Depends(get_db)):
    data=active_bundle(db,user.user_id)
    return success_response(data={'configured':bool(data),**({k:v for k,v in data.items() if k!='rules'} if data else {}),'rule_count':len(data['rules']) if data else 0})

@router.post('/scan')
def scan(req:ScanInput,user:UserContext=Depends(get_current_user),db:Session=Depends(get_db)):
    try:
        result=scan_fields(db,user.user_id,req.fields)
    except (ValueError,TimeoutError) as e:
        raise HTTPException(422,detail=str(e)) from None
    return success_response(data={**result,'notice':format_notice(result)})
