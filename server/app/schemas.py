"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["admin", "farmer"]
FieldSource = Literal["segment", "manual", "segment+edited"]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    name: str = Field(min_length=1, max_length=32)
    phone: str | None = Field(default=None, max_length=20)
    role: Role = "farmer"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    name: str
    phone: str | None = None
    role: Role
    created_at: str
    field_count: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class FieldBase(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    crop: str | None = None
    stage_key: str | None = None
    plant_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str | None = Field(default=None, max_length=200)


class FieldCreate(FieldBase):
    geometry: dict[str, Any]
    source: FieldSource = "manual"
    confidence: float | None = None

    @field_validator("geometry")
    @classmethod
    def _check_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("geometry must be a Polygon or MultiPolygon")
        return value


class FieldUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    crop: str | None = None
    stage_key: str | None = None
    plant_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str | None = Field(default=None, max_length=200)
    geometry: dict[str, Any] | None = None
    rev: int | None = Field(default=None, description="乐观锁版本号")


class FieldOut(BaseModel):
    id: str
    owner_id: str
    owner_name: str | None = None
    name: str
    crop: str | None
    stage_key: str | None
    plant_date: str | None
    note: str | None
    geometry: dict[str, Any]
    area_m2: float
    area_mu: float
    area_ha: float
    source: str
    confidence: float | None
    created_at: str
    updated_at: str
    rev: int
    kc: float | None = None
    stage_label: str | None = None
    crop_label: str | None = None


class SegmentRequest(BaseModel):
    bbox: tuple[float, float, float, float]
    zoom: int | None = Field(default=None, ge=12, le=20)
    provider: str = "esri"
    min_area_ha: float | None = Field(default=None, ge=0.001, le=50)
    conf: float | None = Field(default=None, ge=0.05, le=0.95)
    datum: Literal["wgs84", "gcj02"] = "wgs84"


class SyncOp(BaseModel):
    op_id: str = Field(min_length=8, max_length=64)
    kind: Literal["field.create", "field.update", "field.delete"]
    entity_id: str | None = None
    payload: dict[str, Any]
    client_updated_at: str | None = None


class SyncRequest(BaseModel):
    ops: list[SyncOp] = Field(default_factory=list, max_length=200)
    since: str | None = None


class SyncResult(BaseModel):
    applied: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    server_time: str
    fields: list[FieldOut] = Field(default_factory=list)


class ParamsUpdate(BaseModel):
    """按行政区作用域写覆盖：scope 形如 global / province:370000 / city:370500。

    ``values`` 里某个参数传 null 表示删除该层覆盖、回退到上一层。
    """

    scope: str = Field(default="global", pattern=r"^(global|province:\d{2,6}|city:\d{2,6})$")
    values: dict[str, float | None] = Field(default_factory=dict)


class HealthOut(BaseModel):
    ok: bool
    app: str
    segmentation: dict[str, Any]
    et_grid: dict[str, Any]
    era5: dict[str, Any] = {}
    imagery: list[dict[str, Any]]
