import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FieldType(enum.StrEnum):
    """What kind of value a field holds. It only shapes the instruction given to the model."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"


class Template(Base):
    """A set of fields to extract from a document (for example "NDA summary card").

    A template says WHAT to look for, never WHERE: nothing in it depends on a document
    type, so the same mechanism serves contracts, invoices or any other source.
    """

    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # selectin: async SQLAlchemy cannot lazy-load on attribute access, so fields are loaded
    # together with the template (one extra query for all templates, not one per template).
    fields: Mapped[list["TemplateField"]] = relationship(
        back_populates="template",
        order_by="TemplateField.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TemplateField(Base):
    __tablename__ = "template_fields"
    __table_args__ = (UniqueConstraint("template_id", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    # Stable machine name used in the DOCX placeholder ("{{notice_period}}") and in results.
    key: Mapped[str] = mapped_column(String(64))
    # Human name, also used to search the document ("Termination notice period").
    label: Mapped[str] = mapped_column(String(200))
    # Optional hint for the search and the model ("days of written notice for convenience").
    description: Mapped[str | None] = mapped_column(Text)
    field_type: Mapped[FieldType] = mapped_column(
        Enum(
            FieldType,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=FieldType.TEXT,
    )
    position: Mapped[int] = mapped_column(Integer)
    template: Mapped[Template] = relationship(back_populates="fields")
