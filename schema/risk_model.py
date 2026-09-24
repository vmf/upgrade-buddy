"""Pydantic models for the upgrade risk model, shared by every pipeline stage.

Two variants of the risk-path/condition models exist:
- `RiskPath`/`Condition`: permissive, used for the raw LLM extraction stage
  (evidence may be empty there so the model isn't pressured into fabricating
  a citation it doesn't have - see prompts/extract_risk_paths.md).
- `FinalRiskPath`/`FinalCondition`: strict, used for the assembled Part 5
  output - every condition must carry at least one evidence entry and every
  risk path must carry at least one condition. This is the deterministic
  "reject unsupported claims" gate described in the design note.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

RiskType = Literal[
    "removed_api",
    "changed_behavior",
    "changed_default",
    "dependency_requirement",
    "runtime_requirement",
    "configuration_change",
    "data_migration",
    "operational_risk",
    "unknown",
]

RiskLevel = Literal["critical", "high", "medium", "low", "unknown"]

AffectedSurface = Literal[
    "application_code",
    "configuration",
    "dependencies",
    "runtime",
    "database",
    "deployment",
    "tests",
    "unknown",
]

ConditionCategory = Literal[
    "version",
    "api_usage",
    "configuration",
    "dependency",
    "runtime",
    "deployment",
    "database",
    "behavior",
    "test_coverage",
    "unknown",
]

Operator = Literal[
    "equals",
    "not_equals",
    "in_range",
    "less_than",
    "greater_than",
    "contains",
    "absent",
    "present",
    "unknown",
]

Confidence = Literal["high", "medium", "low"]

SourceType = Literal[
    "official_release_notes",
    "official_migration_guide",
    "official_changelog",
    "official_api_docs",
    "github_release",
    "github_issue_or_pr",
    "deprecation_notice",
    "package_registry_metadata",
    "maintainer_blog",
    "community_writeup",
    "unknown",
]

# Surfaces/categories used by the condition-coverage rule: any risk path
# affecting one of these surfaces must have at least one condition in the
# matching category set, or it's dropped by the deterministic grounding
# gate (pipeline/stages.py::_enforce_coverage_rules). tests/test_condition_
# coverage.py re-checks the same rule against final output as a regression
# check on the gate itself.
APPLICATION_OR_DEPLOYMENT_SURFACES = {
    "application_code",
    "configuration",
    "dependencies",
    "deployment",
    "database",
}
APPLICATION_OR_DEPLOYMENT_CATEGORIES = {
    "api_usage",
    "configuration",
    "dependency",
    "deployment",
    "database",
    "behavior",
}

ChunkCategory = Literal[
    "removed_api",
    "changed_default",
    "changed_behavior",
    "dependency_requirement",
    "runtime_requirement",
    "configuration_change",
    "data_migration",
    "migration_step",
    "known_incompatibility",
    "operational_risk",
    "context_only",
    "unknown",
]


class Evidence(BaseModel):
    source_id: str
    source_type: SourceType
    quote_or_summary: str
    relevance: str


class Condition(BaseModel):
    condition_id: str
    statement: str
    category: ConditionCategory
    required: bool
    operator: Operator
    expected_value: str
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence
    ambiguities: list[str] = Field(default_factory=list)


class FinalCondition(Condition):
    @model_validator(mode="after")
    def _must_have_evidence(self) -> "FinalCondition":
        if not self.evidence:
            raise ValueError(f"condition {self.condition_id!r} has no evidence")
        return self


class RiskPath(BaseModel):
    path_id: str
    path_name: str
    risk_type: RiskType
    risk_level: RiskLevel
    affected_surface: AffectedSurface
    description: str
    conditions: list[Condition] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class FinalRiskPath(RiskPath):
    conditions: list[FinalCondition]

    @model_validator(mode="after")
    def _must_have_conditions(self) -> "FinalRiskPath":
        if not self.conditions:
            raise ValueError(f"risk path {self.path_id!r} has no conditions")
        return self


class Source(BaseModel):
    source_id: str
    title: str
    url: str
    source_type: SourceType
    retrieved_at: str
    why_relevant: str


class SourceInventory(BaseModel):
    project: str
    current_version: str
    target_version: str
    sources: list[Source]


class EvidenceSummary(BaseModel):
    high_confidence_risks: list[str] = Field(default_factory=list)
    medium_confidence_risks: list[str] = Field(default_factory=list)
    low_confidence_or_disputed_risks: list[str] = Field(default_factory=list)
    sources_with_disagreements: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class UpgradeEvidenceSummary(BaseModel):
    project: str
    upgrade: str
    evidence_summary: EvidenceSummary


class UpgradeRiskModel(BaseModel):
    project: str
    current_version: str
    target_version: str
    summary: str
    source_inventory: list[Source]
    risk_paths: list[FinalRiskPath]
    open_questions: list[str] = Field(default_factory=list)
    overall_confidence: Confidence


# --- Wrapper models used purely to force structured JSON tool-output from Claude ---


class ChunkClassification(BaseModel):
    chunk_id: str
    category: ChunkCategory
    is_candidate_risk: bool
    reason: str


class ChunkClassifications(BaseModel):
    classifications: list[ChunkClassification]


class SourceTriageDecision(BaseModel):
    source_id: str
    keep: bool
    source_type: SourceType
    why_relevant: str


class SourceTriageResult(BaseModel):
    decisions: list[SourceTriageDecision]


class ExtractedRiskPaths(BaseModel):
    risk_paths: list[RiskPath] = Field(default_factory=list)


class CriticOutput(BaseModel):
    risk_paths: list[RiskPath]
    evidence_summary: EvidenceSummary


class OutputNormalization(BaseModel):
    summary: str
    overall_confidence: Confidence
    open_questions: list[str] = Field(default_factory=list)


def to_anthropic_tool(model: type[BaseModel], name: str, description: str) -> dict:
    """Converts a pydantic model into an Anthropic tool schema.

    Used with `tool_choice={"type": "tool", "name": name}` to force Claude to
    respond with JSON conforming to `model` - here the "tool" is never actually executed, it just
    forces structured output.
    """
    input_schema = model.model_json_schema()
    input_schema.pop("title", None)
    return {"name": name, "description": description, "input_schema": input_schema}
