from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    vendor_name: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal

    @field_validator("invoice_id", "vendor_name")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text fields cannot be empty")
        return value

    @field_validator("subtotal", "tax", "total", mode="before")
    @classmethod
    def normalize_money(cls, value):
        if isinstance(value, float):
            raise ValueError("native float is not permitted for monetary values")
        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError("invalid monetary value") from exc

    @model_validator(mode="after")
    def validate_non_negative_money(self):
        for field_name in ("subtotal", "tax", "total"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")
        return self
