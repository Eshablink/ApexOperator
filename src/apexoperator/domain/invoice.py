from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator

class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal

    @field_validator("subtotal", "tax", "total", mode="before")
    @classmethod
    def normalize_money(cls, value):
        if isinstance(value, float):
            raise ValueError("native float is not permitted for monetary values")
        return Decimal(str(value))
