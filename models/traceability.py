"""
models/traceability.py
Pydantic schemas for traceability.json — cross-reference report.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class TraceabilityEntry(BaseModel):
    """One row in the traceability matrix."""

    element_id: str = Field(..., alias="elementId")
    element_type: str = Field(..., alias="elementType")
    page_id: str = Field(..., alias="pageId")
    story_ids: List[str] = Field(default_factory=list, alias="storyIds")
    html_file: Optional[str] = Field(default=None, alias="htmlFile")
    react_file: Optional[str] = Field(default=None, alias="reactFile")
    css_class: Optional[str] = Field(default=None, alias="cssClass")
    data_ui_id_verified: bool = Field(
        default=False,
        alias="dataUiIdVerified",
        description="True if data-ui-id was confirmed present in generated code",
    )

    model_config = {"populate_by_name": True}


class TraceabilityReport(BaseModel):
    """Full traceability matrix linking elementIds across all artifacts."""

    report_version: str = Field(default="1.0", alias="reportVersion")
    project_name: str = Field(..., alias="projectName")
    total_elements: int = Field(default=0, alias="totalElements")
    total_stories: int = Field(default=0, alias="totalStories")
    coverage_percent: float = Field(default=0.0, alias="coveragePercent")
    entries: List[TraceabilityEntry] = Field(default_factory=list)
    warnings: List[str] = Field(
        default_factory=list,
        description="Elements missing data-ui-id or story mappings",
    )

    model_config = {"populate_by_name": True}
