"""Current-user role coordination, not a shared team ACL."""
from sqlalchemy import Column, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from core.db.engine import Base


class ForeignTradeCollaboration(Base):
    __tablename__ = "foreign_trade_collaborations"
    collaboration_id = Column(String(64), primary_key=True)
    owner_user_id = Column(String(64), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    created_at = Column(String(40), nullable=False)
    updated_at = Column(String(40), nullable=False)
    __table_args__ = (Index("idx_foreign_trade_collaboration_owner_updated", "owner_user_id", "updated_at"),)
