"""Private, versioned user lexicons. Source documents stay in their private KB."""
from sqlalchemy import Column,Index,JSON,String,Boolean
from core.db.engine import Base

class ForeignTradeLexicon(Base):
    __tablename__='foreign_trade_lexicons'
    lexicon_id=Column(String(64),primary_key=True)
    owner_user_id=Column(String(64),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    source_sha256=Column(String(64),nullable=False)
    payload=Column(JSON,nullable=False)
    created_at=Column(String(40),nullable=False)
    __table_args__=(Index('ix_trade_lexicon_owner_active','owner_user_id','active'),)
