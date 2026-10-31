"""Request-scoped, evidence-linked lead assessment and bilingual outreach drafts."""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from core.foreign_trade.buyer_search import StrictModel, domain
from core.foreign_trade.acquisition import now

WEIGHTS = {'product': 35, 'buyer_type': 25, 'market': 20, 'supply': 20}

class Assessment(StrictModel):
    dimension: Literal['product', 'buyer_type', 'market', 'supply']
    result: Literal['match', 'partial', 'mismatch', 'unknown'] = 'unknown'
    excerpt: str = Field(default='', max_length=2000)
    source_url: str = Field(default='', max_length=2048)
    retrieved_at: str = Field(default='', max_length=100)

    @model_validator(mode='after')
    def evidence_required(self):
        if self.result != 'unknown' and (not self.excerpt.strip() or not domain(self.source_url) or not self.retrieved_at.strip()):
            raise ValueError('已知判断必须提供证据摘录、公开来源 URL 和获取时间')
        return self

class LeadInput(StrictModel):
    buyer_id: str = Field(min_length=1, max_length=200)
    dossier_version: str = Field(min_length=1, max_length=100)
    review_version: str = Field(min_length=1, max_length=100)
    review_decision: Literal['suitable', 'unsuitable', 'unknown']
    review_reason: str = Field(min_length=1, max_length=2000)
    hard_excluded: bool = False
    do_not_contact: bool = False
    has_channel: bool = False
    assessments: list[Assessment] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def unique_dimensions(self):
        if len({a.dimension for a in self.assessments}) != len(self.assessments):
            raise ValueError('评分维度不得重复')
        if not self.review_reason.strip():
            raise ValueError('请填写审核理由')
        return self


def prioritize(req: LeadInput):
    known = sum(WEIGHTS[a.dimension] for a in req.assessments if a.result != 'unknown')
    points = sum(WEIGHTS[a.dimension] * {'match': 1, 'partial': .5, 'mismatch': 0, 'unknown': 0}[a.result] for a in req.assessments)
    fit = round(100 * points / known, 1) if known else None
    coverage = known / 100
    stopped = req.do_not_contact or req.hard_excluded or req.review_decision == 'unsuitable'
    if stopped:
        priority = 'stop'
    elif req.review_decision != 'suitable' or coverage < .75:
        priority = 'research_first'
    elif fit is not None and fit < 75:
        priority = 'defer'
    elif not req.has_channel:
        priority = 'research_first'
    else:
        priority = 'follow_up'
    return dict(buyer_id=req.buyer_id, dossier_version=req.dossier_version, review_version=req.review_version,
                fit_score=fit, evidence_coverage=coverage, ranking_score=round(points, 1), priority=priority,
                contact_readiness='public_channel_unverified' if req.has_channel else 'missing',
                assessments=[a.model_dump() for a in req.assessments],
                unknowns=[key for key in WEIGHTS if not any(a.dimension == key and a.result != 'unknown' for a in req.assessments)],
                next_action={'stop': '停止联系', 'research_first': '补充证据、审核或联系渠道', 'defer': '暂缓跟进，核对匹配差距', 'follow_up': '审核联系用途后生成开发信草稿'}[priority],
                rule_version='v1-uncalibrated', thresholds=dict(min_coverage=.75, min_fit=75),
                evaluation_status='not_evaluated', created_at=now(), input_snapshot=req.model_dump())

class OutreachInput(StrictModel):
    lead: LeadInput
    channel: str = Field(min_length=1, max_length=2048)
    channel_type: Literal['email', 'contact_page']
    channel_source_url: str = Field(min_length=1, max_length=2048)
    channel_retrieved_at: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=200)
    sender_company: str = Field(min_length=1, max_length=200)
    product_en: str = Field(min_length=1, max_length=300)
    supplier_claim_en: str = Field(min_length=1, max_length=1000)
    supplier_claim_reference: str = Field(min_length=1, max_length=500)
    buyer_fact_en: str = Field(default='', max_length=1000)
    buyer_fact_dimension: Literal['product', 'buyer_type', 'market', 'supply'] = 'product'
    goal: Literal['find_contact', 'share_catalog', 'confirm_interest'] = 'find_contact'
    facts_confirmed: bool = False

    @field_validator('company_name', 'sender_company', 'product_en', 'supplier_claim_en', 'supplier_claim_reference', 'channel_retrieved_at')
    @classmethod
    def clean(cls, value):
        if not value.strip() or any(c in value for c in ['\r', '\n', '{{', '}}', '[TODO]']):
            raise ValueError('请填写单行已审核资料，不得含占位符')
        return value.strip()

    @model_validator(mode='after')
    def validate_channel(self):
        import re
        if not domain(self.channel_source_url):
            raise ValueError('联系渠道须有公开来源')
        if self.channel_type == 'email' and not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', self.channel):
            raise ValueError('邮箱格式无效')
        if self.channel_type == 'contact_page' and not domain(self.channel):
            raise ValueError('联系页 URL 无效')
        return self


def draft_outreach(req: OutreachInput):
    lead = prioritize(req.lead)
    if lead['priority'] != 'follow_up' or not req.facts_confirmed:
        raise ValueError('须先完成适合审核、证据评分及渠道确认，并核对商家声明和个性化事实')
    fact = req.buyer_fact_en.strip()
    evidence = next((a for a in req.lead.assessments if a.dimension == req.buyer_fact_dimension and a.result in {'match', 'partial'}), None)
    if fact and evidence is None:
        raise ValueError('个性化事实须关联符合或部分符合的买家证据')
    opening = f'Your website states: {fact}\n\n' if fact else ''
    ctas = {'find_contact': 'Who would be the right person to contact about this product category?',
            'share_catalog': 'May I send a short product catalog for your review?',
            'confirm_interest': 'Is this product category relevant to your current sourcing needs?'}
    ctas_zh = {'find_contact': '请问该产品类别应联系哪位负责人？', 'share_catalog': '是否方便发送一份简短产品目录供您参考？', 'confirm_interest': '该产品类别是否与贵司目前的采购需求相关？'}
    body = f'Hello {req.company_name} team,\n\n{opening}I am contacting you from {req.sender_company} about {req.product_en}.\n{req.supplier_claim_en}\n\n{ctas[req.goal]}\n\nBest regards,\n{req.sender_company}'
    body_zh = f'{req.company_name} 团队，您好：\n\n' + (f'贵司网站信息（已审核英文原文）：{fact}\n\n' if fact else '') + f'我们是 {req.sender_company}，希望向贵司介绍：{req.product_en}。\n供货声明（已审核英文原文）：{req.supplier_claim_en}\n\n{ctas_zh[req.goal]}\n\n{req.sender_company}'
    return dict(buyer_id=req.lead.buyer_id, created_at=now(), review_status='draft', language='en',
                recipient_type='company_team', channel=req.channel, channel_type=req.channel_type,
                subject_options=[f'{req.product_en} — supplier introduction', f'{req.company_name}: product category enquiry'],
                body=body, body_zh=body_zh, translation_note='中文对照保留用户英文事实原文，未自动翻译产品与供货声明。',
                buyer_evidence=[evidence.model_dump()] if fact and evidence else [],
                supplier_claims=[dict(value=req.supplier_claim_en, reference=req.supplier_claim_reference, type='user_statement')],
                channel_evidence=dict(source_url=req.channel_source_url, retrieved_at=req.channel_retrieved_at),
                checks=dict(placeholders='passed', supplied_facts='user_confirmed', independent_fact_verification='not_performed'),
                missing_fields=[], sending_status='not_sent', generation_mode='reviewed_facts_template', input_snapshot=req.model_dump())
