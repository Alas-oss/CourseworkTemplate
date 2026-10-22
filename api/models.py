from pydantic import BaseModel, Field


class CostCreate(BaseModel):
    service_name: str = Field(
        min_length=1,
        max_length=80
    )
    description: str = ""
    cost_per_hour: float = Field(ge=0)
    currency: str = "GBP"
    enabled_by_default: bool = True


class CostUpdate(BaseModel):
    description: str | None = None
    cost_per_hour: float | None = Field(
        default=None,
        ge=0
    )
    currency: str | None = None
    enabled_by_default: bool | None = None


class CostCalculation(BaseModel):
    services: list[str] | None = None
    hours: float = Field(
        default=1,
        gt=0
    )
    instances: dict[str, int] = Field(
        default_factory=dict
    )


class CarbonCreate(BaseModel):
    service_name: str
    energy_kwh: float = Field(ge=0)
    carbon_intensity_gco2e_per_kwh: float = Field(ge=0)
    embodied_emissions_gco2e: float = Field(ge=0)
    functional_unit: float = Field(gt=0)
    functional_unit_name: str = "request"
    notes: str = ""


class CarbonUpdate(BaseModel):
    energy_kwh: float | None = Field(
        default=None,
        ge=0
    )
    carbon_intensity_gco2e_per_kwh: float | None = Field(
        default=None,
        ge=0
    )
    embodied_emissions_gco2e: float | None = Field(
        default=None,
        ge=0
    )
    functional_unit: float | None = Field(
        default=None,
        gt=0
    )
    functional_unit_name: str | None = None
    notes: str | None = None


class SCICalculation(BaseModel):
    services: list[str] | None = None
    functional_units: float | None = Field(
        default=None,
        gt=0
    )