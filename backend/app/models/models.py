"""
Petal Backend — SQLAlchemy ORM Models
"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, String, Text, Boolean, Integer, SmallInteger,
    Numeric, DateTime, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    openid = Column(String(64), unique=True, nullable=False, index=True)
    nickname = Column(String(128))
    avatar_url = Column(Text)
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    skin_analyses = relationship("SkinAnalysis", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    brand = Column(String(128))
    category = Column(String(64), index=True)
    description = Column(Text)
    cover_image = Column(Text)
    price = Column(Numeric(10, 2))
    tags = Column(JSONB, default=[])  # 功效标签: ["控油", "祛痘", ...]
    status = Column(SmallInteger, default=1)  # 1:上架 0:下架
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AntiFakeCode(Base):
    __tablename__ = "anti_fake_codes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    code_hash = Column(String(128), index=True)
    product_id = Column(BigInteger, ForeignKey("products.id"))
    batch_no = Column(String(64))
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    verified_by = Column(BigInteger, ForeignKey("users.id"))
    query_count = Column(Integer, default=0)
    status = Column(String(16), default="unused")  # unused/verified/warning/suspicious
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Product")


class SkinAnalysis(Base):
    __tablename__ = "skin_analyses"

    id = Column(String(64), primary_key=True)  # ana_20260401_abc123
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    image_url = Column(Text, nullable=False)
    analysis_type = Column(String(32), default="face_full")
    analysis_result = Column(JSONB)
    suggestions = Column(JSONB)
    overall_score = Column(Integer)
    skin_type = Column(String(32))
    model_version = Column(String(32))
    status = Column(SmallInteger, default=0)  # 0:处理中 1:完成 2:失败 3:超时
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="skin_analyses")

    __table_args__ = (
        Index("ix_skin_analyses_user_created", "user_id", "created_at"),
    )


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    description = Column(Text)
    product_id = Column(BigInteger, ForeignKey("products.id"))
    promo_type = Column(String(32))
    discount_value = Column(Numeric(10, 2))
    min_purchase = Column(Numeric(10, 2))
    stock = Column(Integer, default=0)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(SmallInteger, default=0)  # 0:草稿 1:待上架 2:进行中 3:已结束 4:已终止
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Product")

    __table_args__ = (
        Index("ix_promotions_status_time", "status", "start_time", "end_time"),
    )


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(String(64), primary_key=True)
    promotion_id = Column(BigInteger, ForeignKey("promotions.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    discount_type = Column(String(32))
    discount_value = Column(Numeric(10, 2))
    min_purchase = Column(Numeric(10, 2))
    valid_until = Column(DateTime)
    status = Column(String(16), default="unused")  # unused / used / expired
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_coupons_user_promo", "user_id", "promotion_id", unique=True),
    )


class PromoClick(Base):
    __tablename__ = "promo_clicks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    promotion_id = Column(BigInteger, ForeignKey("promotions.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    action = Column(String(32))
    source = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_promo_clicks_promo_action", "promotion_id", "action"),
    )
