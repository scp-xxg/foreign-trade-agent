"""Private lexicons: parse data without exec; deterministic warning-only scanning."""
from __future__ import annotations
import ast,hashlib,json,re,time
from datetime import datetime,timezone
from functools import lru_cache
from uuid import uuid4
import regex
from sqlalchemy import update
from core.db.models.foreign_trade_lexicon import ForeignTradeLexicon
LEVELS={'L1':1,'L2':2,'L3':3,'L4':4}
NOTICE='依据用户词库提示，需结合语境及证据复核；命中不等于违法，未命中不等于合规。'
SUGGESTION='核对语境、适用市场与已有证据；无依据时删去该宣称。勿自动补写认证、数值、产地或质保承诺。'
@lru_cache(maxsize=2048)
def _pattern(value):
    return regex.compile(value,regex.IGNORECASE)

def compile_markdown(source,source_name):
    if not source.strip() or len(source.encode())>1024*1024:raise ValueError('词库须为非空Markdown且不超过1MiB')
    rows=[];notes=[];lines=source.splitlines();fence=chr(96)*3
    for match in re.finditer(fence+r'python\s*\n(.*?)'+fence,source,re.S):
        for node in ast.parse(match.group(1)).body:
            if not isinstance(node,ast.Assign) or not any(isinstance(t,ast.Name) and t.id=='RULES' for t in node.targets):continue
            values=ast.literal_eval(node.value)
            if not isinstance(values,list) or len(values)>1000:raise ValueError('规则数量无效')
            for item in values:
                if not isinstance(item,(list,tuple)) or len(item)!=5 or not all(isinstance(x,str) for x in item):raise ValueError('规则格式无效')
                rid,pat,level,reason,suggestion=item;original=pat
                if level not in LEVELS or len(pat)>1000:raise ValueError('规则级别或长度无效')
                if rid=='S404':pat=r'(?i)\b(cur(?:e[sd]?|ing)|treat(?:s|ed|ing)?|heal(?:s|ed|ing)?|prevent(?:s|ed|ing)?\s+disease)\b'
                if rid=='S302':pat=r'(?i)(?<!\w)(no\.?\s*1|#1|number\s+one)(?!\w)'
                if rid=='S401':pat=r'(?i)\b(ce[\s-]*certified|certified\s*by\s*ce)\b'
                _pattern(pat)
                line=next((i+1 for i,l in enumerate(lines) if '"'+rid+'"' in l),1)
                reason={'S401':'核对CE表述的适用产品、法规、合格评定及声明依据。','S402':'核对产品是否实际获得相应FDA批准；注册、许可与批准不能互相替代。'}.get(rid,'词库列为“'+reason+'”；需核验语境和证据。')
                rows.append(dict(rule_id=rid,pattern=pat,level=level,reason=reason,suggestion=SUGGESTION,source_section='16.5 机器可读规则',source_line=line,kind='regex'))
                if pat!=original:notes.append(rid+'词形/边界已修复，原文保持不变')
    if not rows:raise ValueError('未找到可安全解析的RULES字面量列表；不会执行文档代码')
    if len({r['rule_id'] for r in rows})!=len(rows):raise ValueError('规则ID重复')
    chapter=0;section='';headers=[];level='L3';seen=set();in_code=False
    allowed={'敏感词','英文','表述','❌ 错误写法','词','高危表述','黑话','中文'}
    for number,line in enumerate(lines,1):
        if line.startswith(fence):in_code=not in_code;continue
        if in_code:continue
        if line.startswith('## '):
            section=line[3:].strip();m=re.match(r'(\d+)\.',section);chapter=int(m.group(1)) if m else 0;headers=[];level='L3'
        if line.startswith('### '):
            section=line[4:].strip();levels=re.findall(r'L[1-4]',line);level=max(levels,key=LEVELS.get) if levels else 'L3';headers=[]
        if not line.startswith('|'):headers=[];continue
        cells=[x.strip() for x in re.split(r'(?<!\\)\|',line.strip('|'))]
        if not headers:headers=cells;continue
        if all(re.fullmatch(r'[: -]+',c or '-') for c in cells):continue
        if chapter not in {*range(2,10),11,14,15,20,23} or headers[0] not in allowed:continue
        for col in [0]+([1] if headers[:2]==['中文','英文'] else []):
            if col>=len(cells):continue
            for term in re.split(r'\s*/\s*',cells[col]):
                term=re.sub(r'（[^）]*）|\([^)]*\)','',term).strip().strip(chr(96)+'* "“”')
                if not 2<=len(term)<=70 or re.search(r'XXX|XX|[<>]|…|\.\.\.|\[|无依据即|出现在',term):continue
                if term.casefold() in seen:continue
                seen.add(term.casefold());pat=regex.escape(term).replace(r'\ ',r'\s+')
                if re.match(r'[A-Za-zÀ-ž]',term):pat=r'(?<!\w)'+pat
                if re.search(r'[A-Za-zÀ-ž]$',term):pat+=r'(?!\w)'
                rid='T'+str(number)+'-'+str(col)+'-'+hashlib.sha256(term.encode()).hexdigest()[:6]
                rows.append(dict(rule_id=rid,pattern=pat,level=level,reason='此表达列于用户词库“'+section+'”，请核对条件与例外。',suggestion=SUGGESTION,source_section=section,source_line=number,kind='literal'))
    if len(rows)>1000:raise ValueError('编译规则超过限制')
    version=re.search(r'版本：[ *]*([vV][\d.]+)',source)
    return dict(version=version.group(1) if version else 'user-import',source_name=source_name,source_sha256=hashlib.sha256(source.encode()).hexdigest(),rules=rows,compiler_version='1.0',compiler_notes=notes,mode='warn_only',scope_note=NOTICE,coverage='机器规则与可提取明确词条；图片视觉、完整语义、证据真实性及市场适用性仍需人工核验。')

def activate(db,user_id,bundle,kb_id='',document_id=''):
    if not user_id:raise ValueError('需要当前账号')
    bundle={**bundle,'kb_id':kb_id,'document_id':document_id,'source_url':f'/api/v1/catalog/kb/{kb_id}/documents/{document_id}' if kb_id and document_id else ''}
    existing=db.query(ForeignTradeLexicon).filter_by(owner_user_id=str(user_id),source_sha256=bundle['source_sha256']).first()
    db.execute(update(ForeignTradeLexicon).where(ForeignTradeLexicon.owner_user_id==str(user_id)).values(active=False))
    if existing:existing.active=True;existing.payload=bundle;row=existing
    else:
        row=ForeignTradeLexicon(lexicon_id='lex_'+uuid4().hex,owner_user_id=str(user_id),active=True,source_sha256=bundle['source_sha256'],payload=bundle,created_at=datetime.now(timezone.utc).isoformat());db.add(row)
    db.commit();return row.lexicon_id

def active_bundle(db,user_id):
    if not user_id:return None
    row=db.query(ForeignTradeLexicon).filter_by(owner_user_id=str(user_id),active=True).order_by(ForeignTradeLexicon.created_at.desc()).first()
    return {**row.payload,'lexicon_id':row.lexicon_id} if row else None

def scan_fields(db,user_id,fields,*,max_hits=100):
    bundle=active_bundle(db,user_id)
    return scan_bundle(bundle,fields,max_hits=max_hits) if bundle else {'status':'not_configured','matches':[],'match_count':0}

def scan_bundle(bundle,fields,*,max_hits=100):
    if not isinstance(fields,dict) or any(not isinstance(v,str) for v in fields.values()):raise ValueError('检查字段必须为文本')
    if len(fields)>100 or sum(len(v) for v in fields.values())>100000:raise ValueError('敏感词检查超过100000字符或100个字段')
    started=time.monotonic();found=[]
    for field,text in fields.items():
        greetings=[m.span() for m in re.finditer(r'(?i)\bbest\s+(?:regards|wishes)\b',text)]
        for rule in bundle['rules']:
            if time.monotonic()-started>1.0:raise TimeoutError('敏感词检查超时，需人工核验')
            for match in _pattern(rule['pattern']).finditer(text,timeout=0.03):
                a,b=match.span()
                if a==b or any(x<=a and b<=y for x,y in greetings):continue
                found.append({k:rule[k] for k in ('rule_id','level','reason','suggestion','source_section','source_line')}|{'field':field,'start':a,'end':b,'match':match.group(),'source_url':bundle.get('source_url','')})
                if len(found)>5000:raise ValueError('命中过多，请分段检查')
    accepted=[]
    for hit in sorted(found,key=lambda h:(h['field'],-LEVELS[h['level']],h['start'],-(h['end']-h['start']))):
        if any(x['field']==hit['field'] and x['start']<hit['end'] and hit['start']<x['end'] for x in accepted):continue
        accepted.append(hit)
    accepted.sort(key=lambda h:(h['field'],h['start']))
    meta={k:bundle.get(k,'') for k in ('lexicon_id','version','source_name','source_sha256','kb_id','document_id','source_url','scope_note','coverage')}
    return {**meta,'status':'checked','mode':'warn_only','matches':accepted[:max_hits],'match_count':len(accepted),'truncated':len(accepted)>max_hits,'checked_chars':sum(len(v) for v in fields.values())}

def format_notice(report):
    if report.get('status')!='checked' or not report.get('match_count'):return ''
    def escape(s):
        s=str(s).replace('\n',' ')
        return ''.join('\\'+c if c in '\\'+chr(96)+'*_{}[]<>' else c for c in s)
    rows=['**敏感词提示**：命中'+str(report['match_count'])+'处（用户词库 '+escape(report.get('version',''))+'，仅提示、待人工核验）。']
    for h in report.get('matches',[])[:8]:
        rows.append('- '+h['level']+' · '+escape(h['match'][:240]+('…' if len(h['match'])>240 else ''))+' · '+escape(h['field'])+' 第'+str(h['start']+1)+'字符 · 词库'+escape(h['source_section'])+'，规则'+escape(h['rule_id']))
    if report['match_count']>8:rows.append('- 其余命中请分段检查或查看审核报告。')
    rows.append(SUGGESTION+' '+NOTICE)
    return '\n'.join(rows)
