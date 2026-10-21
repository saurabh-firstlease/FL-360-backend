from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.core.config import MEDIA_URL

HotspotType = Literal["nav", "info", "link"]


def wrap180(deg: float) -> float:
    return ((deg + 180) % 360 + 360) % 360 - 180


def media_url(path: str | None) -> str | None:
    return f"{MEDIA_URL}/{path}" if path else None


MediaUrl = Annotated[str | None, BeforeValidator(media_url)]
Pitch = Annotated[float, Field(ge=-90, le=90)]
Fraction = Annotated[float, Field(ge=0, le=1)]


def _clean_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


def _check_url(v: str | None) -> str | None:
    v = _clean_text(v)
    if v is None:
        return None
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")
    return v


# ---------- Output ----------

class HotspotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scene_id: int
    type: HotspotType
    target_scene_id: int | None
    yaw: float
    pitch: float
    label: str | None
    description: str | None
    url: str | None


class SceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    name: str
    description: str | None
    image_url: MediaUrl = Field(validation_alias="image_path")
    preview_url: MediaUrl = Field(validation_alias="preview_path")
    thumb_url: MediaUrl = Field(validation_alias="thumb_path")
    width: int
    height: int
    heading: float
    initial_yaw: float
    initial_pitch: float
    map_x: float | None
    map_y: float | None
    sort_order: int
    hotspots: list[HotspotOut]


class TourOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    property_ref: str | None
    published: bool
    start_scene_id: int | None
    floorplan_url: MediaUrl = Field(validation_alias="floorplan_path")
    created_at: datetime
    updated_at: datetime
    scenes: list[SceneOut]


class TourSummary(BaseModel):
    id: int
    title: str
    description: str | None
    property_ref: str | None
    published: bool
    scene_count: int
    cover_url: str | None
    updated_at: datetime


# ---------- Input ----------

class TourCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    property_ref: str | None = Field(None, max_length=100)

    _clean = field_validator("description", "property_ref")(_clean_text)


class TourUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    property_ref: str | None = Field(None, max_length=100)
    published: bool | None = None
    start_scene_id: int | None = None

    _clean = field_validator("description", "property_ref")(_clean_text)


class SceneOrder(BaseModel):
    scene_ids: list[int]


class SceneUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=5000)
    heading: float | None = Field(None, ge=-720, le=720)
    initial_yaw: float | None = Field(None, ge=-720, le=720)
    initial_pitch: Pitch | None = None
    map_x: Fraction | None = None
    map_y: Fraction | None = None

    _clean = field_validator("description")(_clean_text)

    @field_validator("heading", "initial_yaw")
    @classmethod
    def _wrap(cls, v: float | None) -> float | None:
        return None if v is None else wrap180(v)


class HotspotBase(BaseModel):
    yaw: float = Field(ge=-720, le=720)
    pitch: Pitch
    label: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=2000)
    url: str | None = Field(None, max_length=500)

    _clean = field_validator("label", "description")(_clean_text)
    _url = field_validator("url")(_check_url)

    @field_validator("yaw")
    @classmethod
    def _wrap(cls, v: float) -> float:
        return wrap180(v)


class HotspotCreate(HotspotBase):
    type: HotspotType
    target_scene_id: int | None = None
    # Also create a hotspot in the target room that walks back here.
    add_return: bool = False


class HotspotUpdate(BaseModel):
    type: HotspotType | None = None
    target_scene_id: int | None = None
    yaw: float | None = Field(None, ge=-720, le=720)
    pitch: Pitch | None = None
    label: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=2000)
    url: str | None = Field(None, max_length=500)

    _clean = field_validator("label", "description")(_clean_text)
    _url = field_validator("url")(_check_url)

    @field_validator("yaw")
    @classmethod
    def _wrap(cls, v: float | None) -> float | None:
        return None if v is None else wrap180(v)


class AutoConnectOut(BaseModel):
    created: int
    tour: TourOut
