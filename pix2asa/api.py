"""FastAPI REST API for pix2asa.

Endpoints:
    GET  /api/version           → { version: str }
    GET  /api/devices           → list[TargetDeviceSchema]
    POST /api/convert           → ConversionResultSchema

Start with:
    uvicorn pix2asa.api:app --reload
or via the CLI:
    pix2asa --serve 8000
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .converter import convert, ConversionOptions, VirtualInterface
from .models import SourceVersion, TARGET_DEVICES, TargetVersion

__all__ = ["app"]

app = FastAPI(
    title="pix2asa",
    description="Cisco PIX to ASA configuration converter",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class VersionResponse(BaseModel):
    """Response schema for the /api/version endpoint."""
    version: str


class TargetDeviceSchema(BaseModel):
    """Schema representing a supported ASA target device returned by /api/devices."""
    slug: str
    name: str          # alias for display_name — used by frontend
    display_name: str
    interfaces: list[str]
    max_vlans: int
    device_type: str = "target"


class ConvertRequest(BaseModel):
    """Request body for the POST /api/convert endpoint."""
    config: str = Field(..., description="Raw PIX configuration text")
    target_platform: str = Field("", description='Target ASA slug, e.g. "asa-5520"')
    source_version: Literal[6, 7] = Field(6, description="PIX source OS major version (6 or 7)")
    target_version: Literal[84] = Field(84, description="ASA target OS version (84 for 8.4+)")
    interface_map: dict[str, str] = Field(default_factory=dict,
                                          description='Explicit interface overrides e.g. {"ethernet0": "GigabitEthernet0/0"}')
    custom_5505: bool = Field(False, description="Generate ASA 5505 switch default config")
    boot_system: str | None = Field(None, description="Boot system image path")
    convert_names: bool = Field(True, description="Convert 'name' commands to ASA host objects")
    debug: bool = Field(False, description="Log extra debug info (e.g. NAT translation table) to the conversion log")
    source_filename: str = Field("", description="Original source filename, recorded in the conversion log")
    context_mode: bool = Field(False, description="Emit multi-context system-config block")
    virtual_interfaces: list[dict] = Field(default_factory=list,
                                           description='Virtual interface mappings for context mode e.g. [{"src_pix_if":"ethernet0","physical":"Port-channel1.1400","nameif":"outside"}]')


class ConvertResponse(BaseModel):
    """Response schema for the POST /api/convert endpoint."""
    output: str
    log: str
    warnings: list[str]
    errors: list[str]
    converted_names: dict[str, str] = {}  # name → IP for all converted 'name' commands

    @classmethod
    def from_result(cls, r: "ConversionResult") -> "ConvertResponse":
        """Construct a :class:`ConvertResponse` from a :class:`ConversionResult`."""
        return cls(
            output=r.output,
            log=r.log,
            warnings=r.warnings,
            errors=r.errors,
            converted_names=r.converted_names,
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/version", response_model=VersionResponse, tags=["meta"])
def get_version() -> VersionResponse:
    """Return the current pix2asa package version."""
    return VersionResponse(version=__version__)


@app.get("/api/devices", response_model=list[TargetDeviceSchema], tags=["meta"])
def list_devices() -> list[TargetDeviceSchema]:
    """Return a sorted list of all supported ASA target devices."""
    return [
        TargetDeviceSchema(
            slug=slug,
            name=dev.display_name,
            display_name=dev.display_name,
            interfaces=list(dev.interfaces),
            max_vlans=dev.max_vlans,
        )
        for slug, dev in sorted(TARGET_DEVICES.items())
    ]


@app.post("/api/convert", response_model=ConvertResponse, tags=["convert"])
def api_convert(req: ConvertRequest) -> ConvertResponse:
    """Convert a PIX configuration to ASA format and return the result."""
    if req.target_platform and req.target_platform not in TARGET_DEVICES:
        raise HTTPException(status_code=422,
                            detail=f"Unknown target_platform: {req.target_platform!r}. "
                                   f"Valid: {sorted(TARGET_DEVICES)}")

    src_ver = SourceVersion.PIX7 if req.source_version == 7 else SourceVersion.PIX6
    tgt_ver = TargetVersion.ASA84

    opts = ConversionOptions(
        target_platform=req.target_platform,
        source_version=src_ver,
        target_version=tgt_ver,
        interface_map=req.interface_map,
        custom_5505=req.custom_5505,
        boot_system=req.boot_system or "",
        convert_names=req.convert_names,
        debug=req.debug,
        source_filename=req.source_filename,
        context_mode=req.context_mode,
        virtual_interfaces=[
            VirtualInterface(
                src_pix_if=vi.get("src_pix_if", ""),
                physical=vi.get("physical", ""),
                nameif=vi.get("nameif", ""),
            )
            for vi in req.virtual_interfaces
            if vi.get("src_pix_if") and vi.get("physical") and vi.get("nameif")
        ],
    )

    result = convert(req.config, opts)
    return ConvertResponse.from_result(result)


# Mount the built React SPA at / — must come AFTER all API routes so that
# /api/* routes are matched first by FastAPI's router.
import os as _os
_ui_dist = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "ui", "dist")
if _os.path.isdir(_ui_dist):
    app.mount("/", StaticFiles(directory=_ui_dist, html=True), name="ui")
