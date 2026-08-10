"""Strict API request contracts for the bounded M1 surface."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntakeRequest(StrictModel):
    sku_id: str = Field(min_length=1, max_length=80)
    store_id: str = Field(min_length=1, max_length=80)
    supplier_id: str = Field(min_length=1, max_length=80)
    as_of_ts: datetime
    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def validate_timestamps(self) -> IntakeRequest:
        timestamps = (self.as_of_ts, self.window_start, self.window_end)
        if any(value.tzinfo is None for value in timestamps):
            raise ValueError("All timestamps must include an explicit timezone")
        if self.window_start >= self.window_end or self.window_end > self.as_of_ts:
            raise ValueError("Demand window must end on or before as_of_ts")
        return self


class ReviewAction(StrEnum):
    APPROVE = "approve"
    EDIT_APPROVE = "edit_approve"
    REJECT = "reject"
    ESCALATE = "escalate"


class ReviewRequest(StrictModel):
    action: ReviewAction
    draft_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    edited_payload: dict[str, object] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_action_fields(self) -> ReviewRequest:
        if self.action == ReviewAction.EDIT_APPROVE and self.edited_payload is None:
            raise ValueError("edited_payload is required for edit_approve")
        if self.action != ReviewAction.EDIT_APPROVE and self.edited_payload is not None:
            raise ValueError("edited_payload is only permitted for edit_approve")
        if self.action in {ReviewAction.REJECT, ReviewAction.ESCALATE} and not self.reason:
            raise ValueError("reason is required for reject and escalate")
        if self.action in {ReviewAction.APPROVE, ReviewAction.EDIT_APPROVE} and self.reason:
            raise ValueError("reason is not permitted for approve actions")
        return self
