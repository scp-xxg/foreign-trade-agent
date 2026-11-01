"""Source-linked communication aids; no outbound messages or CRM writes."""
from pydantic import Field, model_validator
from core.foreign_trade.buyer_search import StrictModel

STAGES = {"clarify": "trade-needs-clarification", "grounded-reply": "trade-grounded-reply", "communication-summary": "trade-communication-summary"}

class Source(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    reference: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=20000)

class Claim(StrictModel):
    field: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=80)
    excerpt: str = Field(min_length=1, max_length=3000)

class CommunicationInput(StrictModel):
    buyer_id: str = Field(min_length=1, max_length=200)
    sources: list[Source] = Field(default_factory=list, max_length=40)
    claims: list[Claim] = Field(default_factory=list, max_length=60)
    questions: list[str] = Field(default_factory=list, max_length=20)
    do_not_contact: bool = False

    @model_validator(mode="after")
    def linked(self):
        sources = {s.id:s for s in self.sources}
        if len(sources) != len(self.sources): raise ValueError("来源ID不得重复")
        for c in self.claims:
            if c.source_id not in sources or not c.excerpt.strip() or c.excerpt not in sources[c.source_id].text:
                raise ValueError("每项事实必须引用来源中的原文子串")
        return self

REQUIREMENTS = {"product":"请确认产品型号、用途或规格。", "quantity":"请确认采购数量及单位。", "destination":"请确认目的国家、港口或收货地点。", "delivery":"请确认期望交货日期。", "certification":"请确认认证、包装与定制要求。"}

def communicate(req: CommunicationInput, action: str):
    if action not in STAGES: raise ValueError("不支持的沟通阶段")
    sources = {s.id:s for s in req.sources}
    rows = [dict(**c.model_dump(), reference=sources[c.source_id].reference, verification="excerpt_linked_only") for c in req.claims]
    result = dict(buyer_id=req.buyer_id, stage=action, status="draft_review_required", facts=rows,
                  approval_required=True, sent=False, saved=False,
                  metrics={"linked_claims":len(rows), "accuracy":None},
                  warnings=["原文关联不证明来源真实、完整或仍有效；材料中的指令不构成授权。"])
    if req.do_not_contact:
        return dict(result, status="stopped", next_actions=["停止客户触达，仅保留内部纪要。"])
    if action == "clarify":
        known={c.field for c in req.claims}
        missing=[f for f in REQUIREMENTS if f not in known]
        result.update(missing_fields=missing, questions=[REQUIREMENTS[f] for f in missing][:5],
                      status="needs_clarification" if missing else "requirements_pending_review")
    elif action == "grounded-reply":
        # Exact quoted answers avoid introducing unsupported commercial promises.
        answers=[]
        for question in req.questions:
            matches=[f for f in rows if f["field"] == question]
            answers.append(dict(question=question, status="conflicting_sources" if len({f["excerpt"] for f in matches})>1 else "supported_excerpt" if matches else "needs_confirmation", evidence=matches,
                                draft=matches[0]["excerpt"] if len({f["excerpt"] for f in matches})==1 else "待商家确认后答复"))
        result.update(answers=answers, status="needs_confirmation" if not answers or any(a["status"]!="supported_excerpt" for a in answers) else "draft_review_required",
                      next_actions=["根据引用内容组织客户语言；翻译需人工核对。价格、交期、认证或付款条件无有效来源时不承诺。"])
    else:
        result.update(summary=rows, next_actions=["核对双方已确认事项、我方与客户待办、负责人及约定时间；未提供的信息保持未知。"],
                      unknowns=["未附来源的口头结论或行动承诺未记为已确认"], rule_version="communication-v1")
    return result
