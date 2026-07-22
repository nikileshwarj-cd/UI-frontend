"""
models/story_mapping.py
Pydantic schemas for Stage 2 output: story_ui_mapping.json
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Behavior(BaseModel):
    """A single frontend behavior linked to an acceptance criterion."""

    behavior_type: str = Field(
        ...,
        alias="behaviorType",
        description="click | input | validation | navigation | display | api_placeholder | animation | other",
    )
    trigger: str = Field(
        ..., description="Event that triggers this behavior: onClick | onChange | onSubmit | onLoad | etc."
    )
    action: Optional[str] = Field(default="", description="Description of what happens")
    target_element_id: Optional[str] = Field(
        default=None, alias="targetElementId", description="Element affected by the action"
    )
    is_backend_dependent: bool = Field(
        default=False,
        alias="isBackendDependent",
        description="True if this behavior needs a backend (will become a TODO comment)",
    )
    placeholder_code: Optional[str] = Field(
        default=None,
        alias="placeholderCode",
        description="Frontend placeholder snippet for backend-dependent behaviors",
    )

    model_config = {"populate_by_name": True}


class StoryUIMapping(BaseModel):
    """Mapping of one user story to its UI elements and behaviors."""

    story_id: str = Field(..., alias="storyId")
    story_title: str = Field(..., alias="storyTitle")
    page_id: str = Field(..., alias="pageId")
    page_name: str = Field(..., alias="pageName")
    route: str = Field(default="/")
    element_id: str = Field(..., alias="elementId")
    element_type: str = Field(..., alias="elementType")
    requirement: Optional[str] = Field(default="", description="The user story / requirement text")
    acceptance_criteria: List[str] = Field(
        default_factory=list, alias="acceptanceCriteria"
    )
    behaviors: List[Behavior] = Field(default_factory=list)
    css_classes: List[str] = Field(default_factory=list, alias="cssClasses")
    notes: Optional[str] = Field(default=None)

    model_config = {"populate_by_name": True}


class MappingDocument(BaseModel):
    """Top-level output of Stage 2 — Story Mapper."""

    mapping_version: str = Field(default="1.0", alias="mappingVersion")
    source_spec: str = Field(..., alias="sourceSpec")
    source_stories: str = Field(..., alias="sourceStories")
    mappings: List[StoryUIMapping] = Field(default_factory=list)
    unmapped_stories: List[str] = Field(
        default_factory=list,
        alias="unmappedStories",
        description="Story IDs that could not be mapped to any UI element",
    )

    model_config = {"populate_by_name": True}

    def stories_for_page(self, page_id: str) -> List[StoryUIMapping]:
        return [m for m in self.mappings if m.page_id == page_id]

    def unique_story_ids(self) -> List[str]:
        return list(dict.fromkeys(m.story_id for m in self.mappings))
