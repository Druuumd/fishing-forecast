from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FishSpecies = Literal["pike", "perch"]


class ForecastDay(BaseModel):
    date: date
    species: FishSpecies
    score: float = Field(ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    air_temp_c: float
    pressure_hpa: float
    water_temp_c: float
    wind_speed_m_s: float
    wind_direction_deg: float = Field(ge=0, le=360)
    moon_phase: float = Field(ge=0, le=1)
    stale: bool = False


class ForecastResponse(BaseModel):
    generated_at: datetime
    last_updated_at: datetime | None = None
    days: list[ForecastDay]


class CatchCreate(BaseModel):
    species: FishSpecies
    score: float = Field(ge=0, le=5)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    note: str | None = Field(default=None, max_length=500)
    caught_at: datetime | None = None

    @field_validator("caught_at")
    @classmethod
    def ensure_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("caught_at must include timezone")
        return value


class CatchRecord(BaseModel):
    id: str
    user_id: str
    species: FishSpecies
    score: float
    latitude: float
    longitude: float
    note: str | None
    caught_at: datetime
    linked_weather_date: date
    linked_air_temp_c: float
    linked_pressure_hpa: float
    linked_water_temp_c: float
    linked_wind_speed_m_s: float
    linked_wind_direction_deg: float
    linked_moon_phase: float
    created_at: datetime


class ConsentUpdate(BaseModel):
    geo_allowed: bool
    push_allowed: bool
    analytics_allowed: bool


class ConsentRecord(ConsentUpdate):
    user_id: str
    updated_at: datetime


class DeleteMeDataResponse(BaseModel):
    status: str
    user_id: str
    deleted_catches: int
    deleted_consent: bool
    processed_at: datetime


class MeDataExportResponse(BaseModel):
    status: str
    user_id: str
    catches: list[CatchRecord]
    consent: ConsentRecord | None
    exported_at: datetime


class LegalInfoResponse(BaseModel):
    status: str
    contact_email: str
    support_email: str
    privacy_url: str
    terms_url: str
    data_deletion_url: str
    cookie_tracking_url: str
    updated_at: datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
