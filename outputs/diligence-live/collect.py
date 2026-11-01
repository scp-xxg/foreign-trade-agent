import sys,json
from pathlib import Path
sys.path.insert(0,'src/backend')
from core.foreign_trade.public_data import _fetch_public,_parse_html
out=Path('outputs/diligence-live')
for name,url,isjson in [('website','https://www.lyreco.com/group/',False),('contact','https://www.lyreco.com/group/contacts',False),('registry','https://api.gleif.org/api/v1/lei-records/9695008VOHGGNWBV6W58',True)]:
 try:
  p=_fetch_public(url,json_only=isjson)
  text=p.body if isinstance(p.body,str) else p.body.decode() if isinstance(p.body,bytes) else str(p.body)
  if not isjson:text=_parse_html(p).text
  record={'url':p.url,'retrieved_at':p.retrieved_at,'text':text}
  (out/(name+'-source.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
  print(name,text[:16000] if isjson else '\n'.join(text[max(0,i-150):i+500] for word in ['office supplies','privacy.office','furniture','Contact us'] if (i:=text.lower().find(word.lower()))>=0),flush=True)
 except Exception as e:print(name,type(e).__name__,str(e),flush=True)
