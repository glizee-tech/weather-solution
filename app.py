from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator
from weather_client import GeocodingError, WeatherAPIError, ban_geocode_address, ban_reverse_geocode, build_weekly_plan_payload

app = FastAPI(title="Running Planner V2")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class GeocodeRequest(BaseModel):
    address: str = Field(min_length=2)


class ReverseRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class PlanRequest(BaseModel):
    address: str = ""
    latitude: float | None = None
    longitude: float | None = None
    rain_threshold_mm_per_h: float = 0.5
    wind_threshold_kmh: float = 20.0
    run_duration_hours: float = 0.5
    weekday_start_h: int = 17
    weekday_end_h: int = 20
    weekend_start_h: int = 9
    weekend_end_h: int = 20
    recommended_per_week: int = 10

    @model_validator(mode="after")
    def _address_or_coords(self) -> "PlanRequest":
        addr = self.address.strip()
        coords_ok = self.latitude is not None and self.longitude is not None
        if len(addr) < 2 and not coords_ok:
            raise ValueError("Adresse (2 caractères min.) ou latitude et longitude requis.")
        return self


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    # Starlette 1.x : premier argument = Request, puis le nom du template.
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/reverse")
def reverse(req: ReverseRequest) -> dict:
    try:
        lat, lon, label = ban_reverse_geocode(req.latitude, req.longitude)
        return {
            "ok": True,
            "location": {"address_input": "", "label": label, "latitude": lat, "longitude": lon},
        }
    except GeocodingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except WeatherAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/api/geocode")
def geocode(req: GeocodeRequest) -> dict:
    try:
        lat, lon, label = ban_geocode_address(req.address)
        return {
            "ok": True,
            "location": {"address_input": req.address, "label": label, "latitude": lat, "longitude": lon},
        }
    except GeocodingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except WeatherAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/api/plan")
def plan(req: PlanRequest) -> dict:
    try:
        payload = build_weekly_plan_payload(
            address=req.address.strip(),
            rain_threshold_mm_per_h=req.rain_threshold_mm_per_h,
            wind_threshold_kmh=req.wind_threshold_kmh,
            run_duration_hours=req.run_duration_hours,
            weekday_start_h=req.weekday_start_h,
            weekday_end_h=req.weekday_end_h,
            weekend_start_h=req.weekend_start_h,
            weekend_end_h=req.weekend_end_h,
            recommended_per_week=req.recommended_per_week,
            latitude=req.latitude,
            longitude=req.longitude,
        )
        return {"ok": True, "plan": payload}
    except GeocodingError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except WeatherAPIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
