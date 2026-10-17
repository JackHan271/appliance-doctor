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


class UserMemory(Base):
    """长期记忆：跨会话保留的用户信息（偏好 / 事实 / 结论）。

    按 (user_id, key) 唯一——同 key 覆盖即为"记忆更新"，避免同一事实存多份。
    """

    __tablename__ = "user_memory"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    key = Column(String, nullable=False)          # 如「品牌」「偏好」「结论」
    value = Column(String, nullable=False)        # 如「海尔冰箱」
    category = Column(String, default="fact")     # preference | fact | conclusion
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "updated": self.updated_at.strftime("%m-%d %H:%M") if self.updated_at else "",
        }


def init_db() -> None:
    """建表（幂等）。在应用启动时调用。"""
    Base.metadata.create_all(engine)
