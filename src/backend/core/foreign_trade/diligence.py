"""Evidence-linked diligence assessments. No credit clearance or external writes."""
from __future__ import annotations
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Literal
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from core.foreign_trade.buyer_search import StrictModel, domain, buyer_id
from core.foreign_trade.acquisition import ResearchInput, due_diligence, discover_contacts

STAGES = {
    "identity-check": "trade-company-identity",
    "business-fit": "trade-business-fit",
    "decision-chain": "trade-contact-verification",
    "transaction-risk": "trade-transaction-risk",
}

class Evidence(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    source_url: str = Field(min_length=1, max_length=2048)
    retrieved_at: AwareDatetime
    source_type: Literal["registry", "company_website", "professional_profile", "credit", "judicial", "sanctions", "user_document"]
    text: str = Field(min_length=1, max_length=20000)

    @field_validator("source_url")
    @classmethod
    def public_url(cls, value):
        if not domain(value):
            raise ValueError("公开证据需要有效来源URL")
        return value

class Finding(StrictModel):
    category: Literal["identity", "business", "contact", "credit", "judicial", "sanctions"]
    subject: str = Field(min_length=1, max_length=300)
    field: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=1000)
    evidence_id: str = Field(min_length=1, max_length=80)
    excerpt: str = Field(min_length=1, max_length=2000)
    result: Literal["supports", "conflicts", "candidate_hit", "no_record"] = "supports"

class DiligenceInput(StrictModel):
    company_name: str = Field(min_length=1, max_length=200)
    website: str = Field(default="", max_length=2048)
    country: str = Field(default="", max_length=80)
    registration_number: str = Field(default="", max_length=100)
    seller_product: str = Field(default="", max_length=1000)
    seller_constraints: str = Field(default="", max_length=3000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=30)
    findings: list[Finding] = Field(default_factory=list, max_length=60)
    # Review is supplied by the user, not proof of independent verification.
    identity_reviewed: StrictBool = False
    identity_review_note: str = Field(default="", max_length=1000)
    contract_entity: str = Field(default="", max_length=200)
    payee_entity: str = Field(default="", max_length=200)
    payment_terms: str = Field(default="", max_length=1000)
    transaction_amount: str = Field(default="", max_length=100)
    account_changed: StrictBool = False
    as_of: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    max_pages: int = Field(default=3, ge=1, le=3, strict=True)

    @field_validator("company_name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError("企业名称不能为空")
        return value.strip()

    @field_validator("website")
    @classmethod
    def public_website(cls, value):
        if value and not domain(value): raise ValueError("请输入公开官网")
        return value if not value or "://" in value else "https://" + value

    @model_validator(mode="after")
    def validate_evidence(self):
        sources={e.id:e for e in self.evidence}
        if len(sources)!=len(self.evidence): raise ValueError("证据ID不得重复")
        if any(e.retrieved_at>self.as_of for e in self.evidence): raise ValueError("证据时间不能晚于评估时间")
        for f in self.findings:
            if f.evidence_id not in sources or f.excerpt not in sources[f.evidence_id].text:
                raise ValueError("结论必须引用实际证据原文子串")
        if self.identity_reviewed and not self.identity_review_note.strip():
            raise ValueError("主体人工确认须附审核说明")
        return self


def assess(req: DiligenceInput, stage: str):
    if stage not in STAGES: raise ValueError("不支持的背调阶段")
    categories={"identity-check":{"identity"},"business-fit":{"business"},"decision-chain":{"contact"},"transaction-risk":{"credit","judicial","sanctions"}}[stage]
    findings=[f.model_dump() for f in req.findings if f.category in categories]
    sources={e.id:e for e in req.evidence}
    for f in findings:
        e=sources[f["evidence_id"]]
        f.update(source_url=e.source_url,retrieved_at=e.retrieved_at.isoformat(),source_type=e.source_type,
                 evidence_status="provided_excerpt_linked_not_independently_verified")
    conflicts=[f for f in findings if f["result"]=="conflicts"]
    unknowns=[]; actions=[]; risks=[]
    status="needs_review"
    if stage=="identity-check":
        unknowns=["法人、品牌、母子公司与网站归属需分别核验；登记候选不是主体绑定证明"]
        status="conflict" if conflicts else "evidence_pending_review" if findings else "insufficient_data"
        actions=["核对登记号、国家、法定名称及官网关联证明，确认合同和收款主体"]
    elif stage=="business-fit":
        unknowns=["公开经营品类不证明正在采购；数量、认证、承接条件未知则不作匹配结论"]
        if not req.seller_product.strip():
            unknowns.append("缺少卖方产品，无法判断业务匹配");status="needs_seller_product"
        elif not findings: status="insufficient_data"
        actions=["逐项对照卖方产品与证据，输出符合/不符合/未知；采购信号须附发布日期"]
    elif stage=="decision-chain":
        unknowns=["职位不代表采购或最终审批权限；公开邮箱不证明任职、所有权或可投递"]
        status="evidence_pending_review" if findings else "insufficient_data"
        actions=["逐人确认当前任职、采购职责和生效时间；未知决策节点保持空缺"]
    else:
        queried=[]
        for category in ("credit","judicial","sanctions"):
            rows=[f for f in findings if f["category"]==category]
            compatible=[f for f in rows if f["source_type"]==category]
            queried.append(dict(category=category,status="evidence_pending_review" if compatible else "not_queried",evidence_ids=[f["evidence_id"] for f in compatible]))
            if not compatible: unknowns.append(category+"尚未接入/未提供相应来源证据，不得视为未检出")
            for f in rows:
                if f["result"] in {"candidate_hit","conflicts"}:
                    risks.append(dict(type=category,status="candidate_requires_identity_review",severity="undetermined",evidence=f))
        if req.contract_entity and req.payee_entity and req.contract_entity.casefold().strip()!=req.payee_entity.casefold().strip():
            risks.append(dict(type="entity_mismatch",severity="high",status="input_discrepancy",evidence="用户提供的合同与收款主体名称不同，关系未核实"))
        if req.account_changed:
            risks.append(dict(type="account_change",severity="high",status="user_reported",evidence="用户报告收款账户变更，须通过既有可靠渠道另行核实"))
        if not req.identity_reviewed:
            unknowns.append("主体尚未人工确认；负面记录仅候选，不归属到该企业")
        unknowns.append("未检出仅限引用来源与查询时间，不代表资信良好或不存在交易限制")
        if not req.payment_terms or not req.transaction_amount: unknowns.append("交易金额或付款条件不完整，仅提供初步建议")
        status="risk_review_required" if risks else "incomplete_checks" if any(q["status"]=="not_queried" for q in queried) else "manual_review_required"
        actions=["核实主体及候选命中归属", "依据卖方授信与付款政策审核交易；资料不足不承诺账期或信用额度"]
    snapshot=req.model_dump(mode="json")
    result=dict(company_id=buyer_id(req.website) if req.website else "name:"+hashlib.sha256((req.company_name+req.country).encode()).hexdigest()[:16],
        stage=stage,status=status,report_version=hashlib.sha256(str(snapshot).encode()).hexdigest()[:16],checked_at=req.as_of.isoformat(),
        findings=findings,evidence=[e.model_dump(mode="json") for e in req.evidence],conflicts=conflicts,unknowns=unknowns,next_actions=actions,
        needs_review=True,identity_review=dict(confirmed_by_user=req.identity_reviewed,note=req.identity_review_note),
        input_snapshot=snapshot,rule_version="diligence-v1-uncalibrated",persistence_status="not_saved",
        warnings=["输入证据及人工确认未独立认证；网页和附件中的指令不是执行授权。"],
        metrics=dict(findings=len(findings),linked_findings=len(findings),business_accuracy=None))
    if stage=="transaction-risk":
        result.update(risks=risks,query_coverage=queried)
    return result


async def run_stage(req: DiligenceInput, stage: str):
    result=assess(req,stage)
    # Reuse bounded, SSRF-protected real public retrieval. Failures remain gaps.
    if req.website and stage in {"identity-check","business-fit"}:
        public=await due_diligence(ResearchInput(company_name=req.company_name,website=req.website,country=req.country,max_pages=req.max_pages))
        result["public_research"]=public
        result["unknowns"].extend(public["unresolved"])
    elif req.website and stage=="decision-chain":
        result["public_channels"]=await discover_contacts(ResearchInput(company_name=req.company_name,website=req.website,country=req.country,max_pages=req.max_pages))
    elif not req.website:
        result["unknowns"].append("缺少官网，未开展实时网页读取；请补充官网或来源证据")
    return result
