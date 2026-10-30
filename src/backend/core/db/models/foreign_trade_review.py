"""Versioned public rules and immutable, owner-scoped draft reviews."""
from sqlalchemy import Column, Index, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from core.db.engine import Base


class ForeignTradeKnowledgeRule(Base):
    __tablename__ = "foreign_trade_knowledge_rules"
    rule_key = Column(String(64), primary_key=True)
    knowledge_version = Column(String(80), nullable=False)
    rule_id = Column(String(100), nullable=False)
    rule_version = Column(String(100), nullable=False)
    category = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    created_at = Column(String(40), nullable=False)
    __table_args__ = (Index("idx_foreign_trade_rule_version_category", "knowledge_version", "category"),)


class ForeignTradeReview(Base):
    __tablename__ = "foreign_trade_reviews"
    review_id = Column(String(64), primary_key=True)
    owner_user_id = Column(String(64), nullable=False)
    source_type = Column(String(24), nullable=False)
    source_id = Column(String(64), nullable=False)
    channel = Column(String(40), nullable=False)
    previous_review_id = Column(String(64), nullable=True)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    created_at = Column(String(40), nullable=False)
    __table_args__ = (Index("idx_foreign_trade_review_owner_source", "owner_user_id", "source_type", "source_id", "created_at"),)
