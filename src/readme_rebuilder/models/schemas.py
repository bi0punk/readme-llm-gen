from __future__ import annotations

from pydantic import BaseModel, Field


class ExistingReadmeInsight(BaseModel):
    summary: str
    reusable_details: list[str] = Field(default_factory=list)
    stale_or_unverified_claims: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)


class ContextDigest(BaseModel):
    project_name: str
    inferred_goal: str
    architecture_notes: list[str] = Field(default_factory=list)
    setup_notes: list[str] = Field(default_factory=list)
    usage_notes: list[str] = Field(default_factory=list)
    testing_notes: list[str] = Field(default_factory=list)
    docker_notes: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ReadmeBlueprint(BaseModel):
    project_name: str
    project_type: str
    primary_language: str
    one_liner: str
    title: str
    tagline: str
    overview: str
    features: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    installation: list[str] = Field(default_factory=list)
    configuration: list[str] = Field(default_factory=list)
    usage: list[str] = Field(default_factory=list)
    testing: list[str] = Field(default_factory=list)
    docker: list[str] = Field(default_factory=list)
    repository_notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
