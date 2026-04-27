from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FishSpecies = Literal["pike", "perch", "bream"]
# Krasnoyarsk reservoir bay-based zoning. Anglers navigate by named bays
# rather than abstract upper/middle/lower regions. The dam (Divnogorsk)
# is the northern boundary of the reservoir — what's downstream of it is
# the Yenisei river proper and out of scope.
ReservoirZone = Literal[
    "tubinsky",
    "karasug",
    "ubey",
    "yezagash",
    "syda",
    "koma",
    "izhul",
    "ogur",
    "anash",
    "derbino",
    "sisim",
    "biryusa",
    "main_channel",
]


class ScoreFactor(BaseModel):
    name: str
    contribution: float
    detail: str | None = None


class ForecastDay(BaseModel):
    date: date
    species: FishSpecies
    score: float = Field(ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    air_temp_c: float
    pressure_hpa: float  # MSL (mean sea level)
    surface_pressure_hpa: float | None = None  # actual pressure at water edge
    water_temp_c: float
    wind_speed_m_s: float
    wind_direction_deg: float = Field(ge=0, le=360)
    moon_phase: float = Field(ge=0, le=1)
    cloud_cover_pct: float = Field(default=0.0, ge=0, le=100)
    precipitation_mm: float = Field(default=0.0, ge=0)
    humidity_pct: float = Field(default=0.0, ge=0, le=100)
    pressure_trend_6h_hpa: float = 0.0
    pressure_trend_24h_hpa: float = 0.0
    daylight_hours: float = Field(default=12.0, ge=0, le=24)
    sunrise: datetime | None = None
    sunset: datetime | None = None
    water_level_m: float | None = None
    water_level_trend_7d_m: float = 0.0
    water_level_source: str | None = None
    zone: ReservoirZone | None = None
    zone_label: str | None = None
    thermocline_strength: float = Field(default=0.0, ge=0, le=1)
    thermocline_depth_m: int | None = None
    thermocline_recommended_depth_m: int | None = None
    thermocline_advice: str | None = None
    stale: bool = False
    factors: list[ScoreFactor] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    generated_at: datetime
    last_updated_at: datetime | None = None
    water_level_m: float | None = None
    water_level_trend_7d_m: float = 0.0
    water_level_source: str | None = None
    water_level_is_fresh: bool = False
    zone: ReservoirZone | None = None
    zone_label: str | None = None
    days: list[ForecastDay]


class WaterLevelCreate(BaseModel):
    day: date
    level_m: float = Field(ge=200.0, le=250.0)
    inflow_m3s: float | None = Field(default=None, ge=0)
    outflow_m3s: float | None = Field(default=None, ge=0)
    source: str = Field(default="manual", max_length=64)
    note: str | None = Field(default=None, max_length=500)


class WaterLevelResponse(BaseModel):
    day: date
    level_m: float
    inflow_m3s: float | None = None
    outflow_m3s: float | None = None
    source: str
    note: str | None = None
    recorded_at: datetime


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=10, max_length=200)


class PushCondition(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    params: dict[str, float | int | str | bool] = Field(default_factory=dict)


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: PushSubscriptionKeys
    name: str | None = Field(default=None, max_length=128)
    scope_zone: str | None = Field(default=None, max_length=32)
    scope_species: FishSpecies | None = None
    conditions: list[PushCondition] = Field(default_factory=list, max_length=20)


class PushSubscriptionRecord(BaseModel):
    id: str
    user_id: str
    endpoint: str
    name: str | None
    scope_zone: str | None
    scope_species: FishSpecies | None
    conditions: list[PushCondition]
    last_notified_for_day: date | None
    created_at: datetime
    updated_at: datetime


class PushVapidPublicKeyResponse(BaseModel):
    public_key: str
    enabled: bool


class PushConditionTypeInfo(BaseModel):
    type: str
    label: str
    params_schema: list[dict] = Field(default_factory=list)


class PushConditionTypesResponse(BaseModel):
    types: list[PushConditionTypeInfo]


class WarningSeverity(BaseModel):
    pass  # placeholder to avoid name clashes; severity is plain Literal below.


class WarningItem(BaseModel):
    code: str
    severity: Literal["danger", "warn", "info"]
    title: str
    body: str
    valid_from: date | None = None
    valid_to: date | None = None


class WarningsResponse(BaseModel):
    generated_at: datetime
    zone: ReservoirZone | None = None
    zone_label: str | None = None
    warnings: list[WarningItem]


class WaterTempReadingCreate(BaseModel):
    measured_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    surface_temp_c: float
    thermocline_depth_m: float | None = None
    below_thermocline_temp_c: float | None = None
    instrument: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("measured_at")
    @classmethod
    def ensure_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("measured_at must include timezone")
        return value


class WaterTempReadingRecord(BaseModel):
    id: str
    user_id: str
    measured_at: datetime
    latitude: float
    longitude: float
    zone: str | None
    surface_temp_c: float
    thermocline_depth_m: float | None
    below_thermocline_temp_c: float | None
    instrument: str | None
    note: str | None
    created_at: datetime


class WaterTempReadingsResponse(BaseModel):
    points: list[WaterTempReadingRecord]


class WaterLevelStateResponse(BaseModel):
    latest_level_m: float
    latest_day: date
    trend_7d_m: float
    source: str
    is_fresh: bool


class WaterLevelHistoryPoint(BaseModel):
    day: date
    level_m: float
    source: str


class WaterLevelHistoryResponse(BaseModel):
    days_requested: int
    points: list[WaterLevelHistoryPoint]
    npu_m: float = 243.0
    umo_m: float = 225.0


class WeatherHistoryPoint(BaseModel):
    day: date
    air_temp_c: float
    pressure_hpa: float
    surface_pressure_hpa: float | None = None
    water_temp_c: float
    wind_speed_m_s: float
    cloud_cover_pct: float
    precipitation_mm: float
    pressure_trend_24h_hpa: float


class WeatherHistoryResponse(BaseModel):
    days_requested: int
    points: list[WeatherHistoryPoint]


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
    linked_cloud_cover_pct: float = 0.0
    linked_precipitation_mm: float = 0.0
    linked_humidity_pct: float = 0.0
    linked_pressure_trend_24h_hpa: float = 0.0
    linked_daylight_hours: float = 12.0
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
