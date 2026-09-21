"""业务数据库（PostgreSQL）：个人家电名单 + 维修历史。"""
from sqlalchemy import Column, DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


class Appliance(Base):
    __tablename__ = "appliances"

    id = Column(Integer, primary_key=True)
    brand = Column(String, nullable=False)
    model = Column(String, nullable=False)
    category = Column(String, default="冰箱")
    category_en = Column(String, default="refrigerator")
    purchase_date = Column(String, default="")
    warranty = Column(String, default="")
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "brand": self.brand,
            "model": self.model,
            "category": self.category,
            "category_en": self.category_en,
            "date": self.purchase_date,
            "warranty": self.warranty,
        }


class RepairHistory(Base):
    __tablename__ = "repair_history"

    id = Column(Integer, primary_key=True)
    brand = Column(String, nullable=False)
    model = Column(String, default="")
    level = Column(String, default="yellow")
    issue = Column(String, default="")
    detail = Column(String, default="")
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "brand": self.brand,
            "model": self.model,
            "level": self.level,
            "issue": self.issue,
            "detail": self.detail,
            "date": (self.created_at.strftime("%m-%d") if self.created_at else "刚刚"),
        }


def init_db() -> None:
    """建表（幂等）。在应用启动时调用。"""
    Base.metadata.create_all(engine)
