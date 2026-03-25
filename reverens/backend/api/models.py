import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    wb_article: Mapped[str | None] = mapped_column(Text)
    wb_url: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str | None] = mapped_column(Text)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sellers: Mapped[list["Seller"]] = relationship(
        "Seller", back_populates="product", cascade="all, delete-orphan"
    )


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"))
    seller_name: Mapped[str] = mapped_column(Text, nullable=False)
    seller_id: Mapped[str] = mapped_column(Text, nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="sellers")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="seller", cascade="all, delete-orphan"
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("sellers.id"))
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    seller: Mapped["Seller"] = relationship("Seller", back_populates="price_history")


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(Text)
    tg_chat_id: Mapped[str | None] = mapped_column(Text)
    threshold: Mapped[int] = mapped_column(Integer, default=5)
