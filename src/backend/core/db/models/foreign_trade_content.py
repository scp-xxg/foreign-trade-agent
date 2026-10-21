"""Owner-isolated product content packs with revisioned inputs and outputs."""
from sqlalchemy import Column, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from core.db.engine import Base

class ForeignTradeContentPack(Base):
    __tablename__ = "foreign_trade_content_packs"
    pack_id = Column(String(64), primary_key=True)
    owner_user_id = Column(String(64), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    created_at = Column(String(40), nullable=False)
    updated_at = Column(String(40), nullable=False)
    __table_args__ = (Index("idx_trade_content_owner_updated", "owner_user_id", "updated_at"),)
