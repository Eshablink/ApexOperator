from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentConfidence(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str
    vendor_name: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("invoice_id", "vendor_name")
    @classmethod
    def text_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text value cannot be empty")
        return value

    @field_validator("subtotal", "tax", "total", mode="before")
    @classmethod
    def money_as_decimal(cls, value):
        if isinstance(value, float):
            raise ValueError("native float is not permitted for document money")
        return Decimal(str(value))

    @property
    def confidence_class(self) -> DocumentConfidence:
        return (
            DocumentConfidence.HIGH
            if self.confidence >= Decimal("0.85")
            else DocumentConfidence.LOW
        )
