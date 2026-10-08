from typing import Literal
from pydantic import BaseModel, Field, model_validator

Category = Literal["educational", "funny", "emotional", "controversial", "inspirational",
                   "storytelling", "surprising", "technical", "opinion"]

class ClipCandidate(BaseModel):
    start: float = Field(ge=0)
    end: float
    title: str = Field(min_length=1, max_length=120)
    hook: str = ""
    reason: str = ""
    score: float = Field(ge=0, le=100)
    category: Category = "opinion"

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self

class ClipUpdate(BaseModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = None
    title: str | None = None
    caption_style: Literal["classic", "bold", "highlight", "creator", "minimal", "off"] | None = None
    aspect: Literal["9:16", "1:1", "16:9"] | None = None
