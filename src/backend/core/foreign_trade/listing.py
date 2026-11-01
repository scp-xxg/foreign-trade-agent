"""Versioned, source-grounded listing preparation. No external publishing."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import re
import warnings
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

STAGES = {
    'normalize': 'trade-product-normalization',
    'taxonomy': 'trade-listing-taxonomy',
    'keywords': 'trade-listing-keyword-planning',
    'compose': 'trade-listing-content-composition',
    'media': 'trade-listing-media-adaptation',
    'preflight': 'trade-listing-preflight',
}
class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Source(Model):
    id: str = Field(min_length=1,max_length=100)
    reference: str = Field(min_length=1,max_length=1000)
    text: str = Field(min_length=1,max_length=60000)
class Evidence(Model):
    source_id: str
    excerpt: str = Field(min_length=1,max_length=6000)
class Fact(Model):
    field: str = Field(min_length=1,max_length=80)
    value: str = Field(min_length=1,max_length=3000)
    confirmed: bool = False
    evidence: list[Evidence] = Field(min_length=1,max_length=10)
    valid_until: AwareDatetime | None = None
class Product(Model):
    sku: str = Field(min_length=1,max_length=100)
    product_id: str = Field(min_length=1,max_length=100)
    version: str = Field(min_length=1,max_length=100)
    facts: list[Fact] = Field(default_factory=list,max_length=150)
class Attribute(Model):
    field: str = Field(min_length=1,max_length=80)
    required: bool = True
    values: list[str] = Field(default_factory=list,max_length=200)
class Category(Model):
    id: str = Field(min_length=1,max_length=100)
    path: str = Field(min_length=1,max_length=1000)
    attributes: list[Attribute] = Field(default_factory=list,max_length=100)
    match_fields: list[str] = Field(default_factory=list,max_length=30)
    variant_fields: list[str] = Field(default_factory=list,max_length=10)
class Rules(Model):
    version: str = Field(min_length=1,max_length=100)
    retrieved_at: AwareDatetime
    valid_until: AwareDatetime
    evidence: list[Evidence] = Field(min_length=1,max_length=10)
    categories: list[Category] = Field(min_length=1,max_length=100)
    required_fields: list[str] = Field(min_length=1,max_length=100)
    title_max: int = Field(ge=1,le=1000)
    description_max: int = Field(ge=1,le=60000)
    min_images: int = Field(ge=1,le=20)
    min_width: int = Field(ge=1,le=4096)
    min_height: int = Field(ge=1,le=4096)
    max_width: int = Field(ge=1,le=4096)
    max_height: int = Field(ge=1,le=4096)
    max_image_bytes: int = Field(ge=100,le=8388608)
    formats: list[str] = Field(min_length=1,max_length=3)
    forbidden_terms: list[str] = Field(default_factory=list,max_length=100)
    required_review_checks: list[str] = Field(default_factory=lambda:['restricted_products','intellectual_property','claims'],max_length=30)
    @model_validator(mode='after')
    def valid(self):
        if self.valid_until < self.retrieved_at or self.min_width>self.max_width or self.min_height>self.max_height:
            raise ValueError('规则时间或尺寸范围错误')
        if any(f not in {'PNG','JPEG','WEBP'} for f in self.formats):raise ValueError('图片格式不受支持')
        if len({c.id for c in self.categories})!=len(self.categories):raise ValueError('类目ID重复')
        for c in self.categories:
            if len({a.field for a in c.attributes})!=len(c.attributes):raise ValueError('属性重复')
        return self
class Selection(Model):
    sku: str
    category_id: str
    confirmed: bool = False
class Keyword(Model):
    sku: str
    term: str = Field(min_length=1,max_length=200)
    intent: str = Field(min_length=1,max_length=100)
    fact_fields: list[str] = Field(min_length=1,max_length=30)
    confirmed: bool = False
    origin: str = Field(default='model_suggestion',pattern=r'^(model_suggestion|platform_report|business_history)$')
    search_volume: int | None = Field(default=None,ge=0)
    evidence: list[Evidence] = Field(default_factory=list,max_length=10)
    @model_validator(mode='after')
    def measured(self):
        if (self.origin!='model_suggestion' or self.search_volume is not None) and not self.evidence:
            raise ValueError('真实数据须有报告证据')
        if self.origin=='model_suggestion' and self.search_volume is not None:raise ValueError('建议词不能虚构搜索量')
        return self
class Draft(Model):
    sku: str
    title: str = Field(min_length=1,max_length=2000)
    description: str = Field(min_length=1,max_length=60000)
    fact_fields: list[str] = Field(min_length=1,max_length=100)
    reviewed: bool = False
class Media(Model):
    sku: str
    file_id: str = Field(min_length=1,max_length=200)
    role: str = Field(default='detail',pattern=r'^(main|detail|dimensions|packaging|scene)$')
    sku_confirmed: bool = False
    rights_reference: str = Field(default='',max_length=1000)
    appearance_reviewed: bool = False
    reviewed_sha256: str = Field(default='',pattern=r'^([a-f0-9]{64})?$')
class Review(Model):
    scope_hash: str = Field(default='',pattern=r'^([a-f0-9]{64})?$')
    sku: str
    check: str = Field(min_length=1,max_length=100)
    state: str = Field(pattern=r'^(passed|blocked|pending)$')
    evidence: list[Evidence] = Field(min_length=1,max_length=10)
class ListingInput(Model):
    batch_id: str = Field(min_length=1,max_length=100)
    as_of: AwareDatetime
    platform: str = Field(min_length=1,max_length=100)
    site: str = Field(min_length=1,max_length=100)
    language: str = Field(min_length=1,max_length=100)
    sources: list[Source] = Field(default_factory=list,max_length=100)
    products: list[Product] = Field(default_factory=list,max_length=100)
    rules: Rules | None = None
    selections: list[Selection] = Field(default_factory=list,max_length=100)
    keywords: list[Keyword] = Field(default_factory=list,max_length=300)
    drafts: list[Draft] = Field(default_factory=list,max_length=100)
    media: list[Media] = Field(default_factory=list,max_length=20)
    reviews: list[Review] = Field(default_factory=list,max_length=300)
    @model_validator(mode='after')
    def linked(self):
        src={s.id:s for s in self.sources};skus={p.sku for p in self.products}
        if len(src)!=len(self.sources) or len(skus)!=len(self.products):raise ValueError('来源或SKU重复')
        for rows,keys in [(self.selections,('sku',)),(self.drafts,('sku',)),(self.media,('sku','file_id')),(self.reviews,('sku','check'))]:
            if len({tuple(getattr(x,k) for k in keys) for x in rows})!=len(rows):raise ValueError('记录重复')
        for x in [*self.selections,*self.keywords,*self.drafts,*self.media,*self.reviews]:
            if x.sku not in skus:raise ValueError('引用未知SKU')
        refs=[]
        for p in self.products:
            for f in p.facts:
                refs.extend(f.evidence)
                if not any(f.value in e.excerpt for e in f.evidence):raise ValueError('字段值须出现在证据原文中')
        for x in [*self.keywords,*self.reviews]:refs.extend(x.evidence)
        if self.rules:refs.extend(self.rules.evidence)
        for e in refs:
            if e.source_id not in src or e.excerpt not in src[e.source_id].text:raise ValueError('证据须为来源原文子串')
        for x in self.selections:
            if self.rules and x.category_id not in {c.id for c in self.rules.categories}:raise ValueError('引用未知类目')
        return self

ALIASES={'型号':'model','Model':'model','Model No.':'model','Item No.':'model','材质':'material','Material':'material','产品名称':'name','Product Name':'name','容量':'capacity','Capacity':'capacity','重量':'weight','MOQ':'moq','起订量':'moq','交期':'delivery','币种':'currency','价格':'price','计价单位':'price_unit','包装':'packaging','认证':'certification'}
UNITS={'g':('kg',Decimal('0.001')),'kg':('kg',Decimal(1)),'ml':('L',Decimal('0.001')),'l':('L',Decimal(1)),'mm':('mm',Decimal(1)),'cm':('mm',Decimal(10)),'m':('mm',Decimal(1000))}
def normalized(field,value):
    field=ALIASES.get(field,field)
    m=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(g|kg|ml|l|mm|cm|m)',value,re.I)
    if m and field in {'capacity','weight','length','width','height'}:
        unit,factor=UNITS[m[2].lower()]
        dimension={'capacity':{'L'},'weight':{'kg'},'length':{'mm'},'width':{'mm'},'height':{'mm'}}[field]
        if unit in dimension:return field,f'{format((Decimal(m[1])*factor).normalize(),"f")} {unit}'
    return field,value.strip()

def fact_map(p,as_of):
    grouped=defaultdict(list)
    for f in p.facts:
        field,value=normalized(f.field,f.value);grouped[field].append((f,value))
    result={}
    for field,items in grouped.items():
        values={v for _,v in items}
        state='conflict' if len(values)>1 else 'expired' if any(f.valid_until and f.valid_until<as_of for f,_ in items) else 'confirmed' if all(f.confirmed for f,_ in items) else 'pending'
        result[field]={'value':next(iter(values)) if len(values)==1 else None,'state':state,'entries':[f.model_dump(mode='json') for f,_ in items]}
    return result

def review_hash(req):
    payload=req.model_dump(mode='json',exclude={'reviews','as_of'})
    return sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def digest(req):
    return sha256(json.dumps(req.model_dump(mode='json'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def prepare(req: ListingInput,action: str,media_reports=None):
    if action not in STAGES:raise ValueError('未知发品步骤')
    current=bool(req.rules and req.rules.retrieved_at<=req.as_of<=req.rules.valid_until)
    result=dict(batch_id=req.batch_id,platform=req.platform,site=req.site,language=req.language,stage=action,
        input_hash=digest(req),review_scope_hash=review_hash(req),rules_version=req.rules.version if req.rules else None,
        rules_current=current,published=False,approval_required=True,status='draft_review_required',items=[],
        metrics={'accuracy':None,'business_effect':None},warnings=['仅核对提供资料；确认、规则来源及权利声明未独立鉴真。无实时平台规则、搜索量查询或发布。'])
    maps={p.sku:fact_map(p,req.as_of) for p in req.products}
    selections={s.sku:s for s in req.selections}
    drafts={d.sku:d for d in req.drafts}
    def selection(sku):
        s=selections.get(sku)
        return next((c for c in req.rules.categories if s and c.id==s.category_id and s.confirmed),None) if req.rules else None
    def attributes(sku,c):
        facts=maps[sku];out=[]
        for a in c.attributes:
            f=facts.get(a.field)
            state='missing' if not f else f['state'] if f['state']!='confirmed' else 'invalid_enum' if a.values and f['value'] not in a.values else 'mapped'
            out.append(dict(field=a.field,value=f['value'] if f else None,required=a.required,state=state))
        return out
    duplicate_variants=defaultdict(list)
    for p in req.products:
        c=selection(p.sku)
        if c and c.variant_fields:
            key=(p.product_id,c.id,tuple(maps[p.sku].get(f,{}).get('value') for f in c.variant_fields))
            duplicate_variants[key].append(p.sku)
    seen_main=defaultdict(list)
    for k in req.keywords:
        if k.confirmed:seen_main[k.term.casefold()].append(k.sku)
    for p in req.products:
        facts=maps[p.sku];good={f:v['value'] for f,v in facts.items() if v['state']=='confirmed'}
        c=selection(p.sku);issues=[]
        required=req.rules.required_fields if req.rules else ['name','model','material','moq','delivery']
        for f in required:
            if f not in good:issues.append(dict(code='missing_or_unconfirmed_fact',field=f))
        issues.extend(dict(code='fact_'+v['state'],field=f) for f,v in facts.items() if v['state']!='confirmed')
        if any(f in good for f in ['price','price_unit','currency']) and not all(f in good for f in ['price','price_unit','currency','moq']):
            issues.append(dict(code='incomplete_price_context'))
        item=dict(sku=p.sku,product_id=p.product_id,version=p.version,issues=issues)
        if action=='normalize':
            item.update(facts=facts,required_fields=required,complete_count=sum(f in good for f in required),required_count=len(required))
        elif action=='taxonomy':
            candidates=[]
            if req.rules:
                for candidate in req.rules.categories:
                    matches=[f for f in candidate.match_fields if f in good and good[f].casefold() in candidate.path.casefold()]
                    candidates.append(dict(id=candidate.id,path=candidate.path,matched_fields=matches,score=len(matches)))
            candidates.sort(key=lambda x:(-x['score'],x['id']))
            item.update(candidates=candidates[:5],selected_category=c.id if c else None,attributes=attributes(p.sku,c) if c else [],needs_confirmation=c is None or not current)
        elif action=='keywords':
            words=[]
            for k in req.keywords:
                if k.sku!=p.sku:continue
                supported=all(f in good for f in k.fact_fields)
                words.append({**k.model_dump(mode='json'),'state':'reviewed' if supported and k.confirmed else 'pending_review','duplicate_skus':sorted(set(seen_main[k.term.casefold()])-{p.sku})})
            item.update(keywords=words,suggested_seeds=[good[f] for f in ['name','material','application'] if f in good],priority_basis='资料完整度与人工相关性；未推断搜索热度',priority=len(good),publish_plan='review_required')
        elif action=='compose':
            d=drafts.get(p.sku)
            # Fact-only fallback; free text from reused writing/localization skill must be reviewed.
            title=' '.join(good[f] for f in ['name','model','material'] if f in good)
            desc='\n'.join(f'{f}: {value}' for f,value in good.items())
            if d:title,desc=d.title,d.description
            unsupported=[f for f in d.fact_fields if f not in good] if d else []
            item.update(title=title,description=desc,origin='submitted_draft' if d else 'fact_only_template',reviewed=bool(d and d.reviewed and not unsupported),unsupported_fields=unsupported,
                title_length=len(title),description_length=len(desc),format_passed=bool(current and title and desc and len(title)<=req.rules.title_max and len(desc)<=req.rules.description_max),
                keyword_coverage=[dict(term=k.term,in_title=k.term.casefold() in title.casefold(),in_description=k.term.casefold() in desc.casefold()) for k in req.keywords if k.sku==p.sku],facts=good)
        elif action=='media':
            reports=[x for x in (media_reports or []) if x['sku']==p.sku]
            item.update(media=reports,missing_main=not any(m.sku==p.sku and m.role=='main' for m in req.media),
                missing_roles=[role for role in ['main','detail','dimensions','packaging'] if not any(m.sku==p.sku and m.role==role for m in req.media)])
        elif action=='preflight':
            if not current:issues.append(dict(code='rules_missing_or_stale'))
            if not c:issues.append(dict(code='category_not_confirmed'))
            if c:
                issues.extend(dict(code='attribute_'+a['state'],field=a['field']) for a in attributes(p.sku,c) if a['state']!='mapped' and (a['required'] or a['state']!='missing'))
                for f in c.variant_fields:
                    if f not in good:issues.append(dict(code='variant_missing',field=f))
                if c.variant_fields:
                    key=(p.product_id,c.id,tuple(facts.get(f,{}).get('value') for f in c.variant_fields))
                    if len(duplicate_variants[key])>1:issues.append(dict(code='duplicate_variant',skus=duplicate_variants[key]))
            d=drafts.get(p.sku)
            if not d or not d.reviewed:issues.append(dict(code='draft_missing_or_unreviewed'))
            if d:
                if any(f not in good for f in d.fact_fields):issues.append(dict(code='draft_unsupported_fields'))
                if set(good)-set(d.fact_fields):issues.append(dict(code='draft_fact_coverage_needs_review',fields=sorted(set(good)-set(d.fact_fields))))
                text=d.title+'\n'+d.description
                if re.search(r'\{\{|待确认|TODO|TBD',text,re.I):issues.append(dict(code='unresolved_placeholder'))
                if req.rules:
                    if len(d.title)>req.rules.title_max or len(d.description)>req.rules.description_max:issues.append(dict(code='content_length_exceeded'))
                    for term in req.rules.forbidden_terms:
                        if term.casefold() in text.casefold():issues.append(dict(code='forbidden_term',term=term))
            words=[k for k in req.keywords if k.sku==p.sku and k.confirmed and all(f in good for f in k.fact_fields)]
            if not words:issues.append(dict(code='keywords_unreviewed'))
            reports=[x for x in (media_reports or []) if x['sku']==p.sku]
            if not req.rules or len(reports)<req.rules.min_images:issues.append(dict(code='insufficient_media'))
            if not any(m.sku==p.sku and m.role=='main' for m in req.media):issues.append(dict(code='main_image_missing'))
            for report in reports:
                if not report.get('spec_passed'):issues.append(dict(code='media_spec_failed',file_id=report['file_id']))
                m=next((m for m in req.media if m.sku==p.sku and m.file_id==report['file_id']),None)
                if not m or not m.reviewed_sha256 or m.reviewed_sha256!=report.get('sha256'):issues.append(dict(code='media_changed_or_unreviewed',file_id=report['file_id']))
            for m in req.media:
                if m.sku==p.sku and not(m.sku_confirmed and m.appearance_reviewed and m.rights_reference):issues.append(dict(code='media_review_or_rights_missing',file_id=m.file_id))
            reviews={x.check:x for x in req.reviews if x.sku==p.sku}
            checks=set(req.rules.required_review_checks if req.rules else [])|{'restricted_products','intellectual_property','claims'}
            for check in sorted(checks):
                if check not in reviews or reviews[check].state!='passed' or reviews[check].scope_hash!=review_hash(req):issues.append(dict(code='review_incomplete',check=check))
            item.update(status='blocked' if issues else 'ready_for_publish_review',media=reports,checked_input_hash=sha256((digest(req)+json.dumps(media_reports or [],sort_keys=True)).encode()).hexdigest())
        item.setdefault('status','needs_completion' if issues else 'draft_review_required')
        result['items'].append(item)
    if not result['items']:result['status']='needs_products'
    elif action=='preflight':result['status']='ready_for_publish_review' if all(i['status']=='ready_for_publish_review' for i in result['items']) else 'needs_completion'
    return result

def adapt_image(content: bytes,rules: Rules | None, *, convert: bool):
    """Decode real bytes; resize without cropping, upscaling, recoloring or inventing content."""
    from PIL import Image,ImageOps
    if not 0<len(content)<=8*1024*1024:raise ValueError('图片为空或超过8MiB')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as im:
            if im.format not in {'PNG','JPEG','WEBP'} or im.width*im.height>20000000:raise ValueError('格式或像素超限')
            fmt=im.format
            if getattr(im,'n_frames',1)!=1:raise ValueError('动画图片请先选择静态帧')
            im.load();image=ImageOps.exif_transpose(im)
            original_size=list(image.size)
            if convert:
                if not rules:raise ValueError('素材转换须先提供平台规则')
                image.thumbnail((rules.max_width,rules.max_height),Image.Resampling.LANCZOS)
                fmt=rules.formats[0]
                image=image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
                if fmt=='JPEG' and 'A' in image.getbands():
                    background=Image.new('RGB',image.size,'white');background.paste(image,mask=image.getchannel('A'));image=background
                out=BytesIO();image.save(out,format=fmt);payload=out.getvalue()
            else:payload=content
            passed=bool(rules and rules.min_width<=image.width<=rules.max_width and rules.min_height<=image.height<=rules.max_height and len(payload)<=rules.max_image_bytes and fmt in rules.formats)
            return payload,dict(width=image.width,height=image.height,format=fmt,bytes=len(payload),original_size=original_size,spec_passed=passed,sha256=sha256(payload).hexdigest())
