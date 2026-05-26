from pydantic import BaseModel, Field


class PreferencesRequest(BaseModel):
    preferences: str = Field(min_length=1)


class SearchRunRequest(BaseModel):
    keywords: str = "software engineer"
    location: str = "United States"
    pages: int = Field(default=2, ge=1, le=10)


class FeedbackRequest(BaseModel):
    job_id: str = Field(min_length=1)
    feedback: str = Field(min_length=1)
    reason: str = ""
    title: str = "Unknown"
    company: str = "Unknown"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class EmailLatestRequest(BaseModel):
    to_email: str = ""


class ScheduleRequest(BaseModel):
    enabled: bool = False
    time: str = "09:00"
    days: dict[str, bool] = Field(
        default_factory=lambda: {
            "mon": True,
            "tue": True,
            "wed": True,
            "thu": True,
            "fri": True,
            "sat": False,
            "sun": False,
        }
    )
    keywords: str = "software engineer"
    location: str = "United States"
    pages: int = Field(default=2, ge=1, le=10)
    email_to: str = ""
