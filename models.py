from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True)
    public_key = Column(Text, nullable=True)
    private_key = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
