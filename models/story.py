from pydantic import BaseModel, Field
from datetime import datetime


class Story(BaseModel):
    id: int = Field(default=None, primary_key=True)
    title: str
    url: str
    timestamp: datetime
    summary: str | None = None
