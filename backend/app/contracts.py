"""Shared wire contracts from TASKS_3people.md §3. Mongo IDs serialize as `_id`."""

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Tier = Literal["T0", "T1", "T2"]
Trust = Literal["dry_run", "supervised", "autonomous"]
JobType = Literal["mine", "forge", "heal", "prune", "consolidate", "interpret"]
EventType = Literal[
    "suggestion_new",
    "forge_started",
    "forged",
    "gate_passed",
    "gate_failed",
    "promoted",
    "run_completed",
    "trust_changed",
    "drift_detected",
    "healed",
    "pruned",
    "policy_changed",
    "frame_labeled",
    "capture_paused",
    "race_step",
]


class Contract(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Evidence(Contract):
    frame_ids: list[str] = Field(default_factory=list)
    ocr_snippet: str = ""
    tier: Tier = "T0"
    confidence: float = Field(default=1, ge=0, le=1)
    needs_review: bool = False


class ObservationMeta(Contract):
    user_id: str
    source: str


class Cost(Contract):
    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0, ge=0)


class Observation(Contract):
    ts: AwareDatetime
    meta: ObservationMeta
    session_id: str | None = None
    action: str
    signature: str
    target: dict[str, Any] = Field(default_factory=dict)
    args_shape: dict[str, Any] = Field(default_factory=dict)
    params_hash: str | None = None
    intent_text: str = ""
    cost: Cost = Field(default_factory=Cost)
    duration_ms: float = Field(default=0, ge=0)
    error: str | None = None
    evidence: Evidence = Field(default_factory=Evidence)
    artifacts: dict[str, list[str]] = Field(default_factory=dict)


class ObservationBatch(Contract):
    user_id: str
    events: list[Observation]

    @model_validator(mode="after")
    def matching_users(self):
        if any(event.meta.user_id != self.user_id for event in self.events):
            raise ValueError("Observation meta.user_id must match batch user_id")
        return self


class Element(Contract):
    role: str = ""
    name: str = ""
    data_attr: dict[str, str] = Field(default_factory=dict)


class ValueShape(Contract):
    len: int = Field(ge=0)
    type: str


class UIEvent(Contract):
    ts: AwareDatetime
    kind: Literal["click", "submit", "nav", "burst_end"]
    url_template: str
    element: Element = Field(default_factory=Element)
    value_shape: ValueShape | None = None
    frame_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    source: Literal["chrome"] = "chrome"


class CaptureFrame(Contract):
    client_id: str
    ts: AwareDatetime
    trigger: Literal["click", "nav", "burst", "heartbeat", "flag", "video_replay"]
    app: str
    window_title: str
    url_template: str
    image_webp_b64: str = Field(min_length=1, max_length=8_000_000)


class CaptureBatch(Contract):
    user_id: str
    capture_session_id: str
    source: Literal["chrome", "video_replay", "desktop"]
    events: list[UIEvent] = Field(default_factory=list, max_length=1000)
    frames: list[CaptureFrame] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def matching_users(self):
        if any(event.user_id not in (None, self.user_id) for event in self.events):
            raise ValueError("UI event user_id must match batch user_id")
        if len({frame.client_id for frame in self.frames}) != len(self.frames):
            raise ValueError("Frame client_ids must be unique within a batch")
        return self


class CaptureAck(Contract):
    ui_events: int = Field(ge=0)
    frames_kept: int = Field(ge=0)
    frames_dropped: int = Field(ge=0)
    paused: bool


class FrameLabel(Contract):
    verb: str
    args_shape: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    source: Literal["vlm", "nn_copy", "dom"]
    needs_review: bool = False

    @model_validator(mode="after")
    def review_low_confidence(self):
        if self.confidence < 0.6:
            self.needs_review = True
        return self


class Frame(Contract):
    id: str = Field(alias="_id")
    user_id: str
    session_id: str
    ts: AwareDatetime
    source: Literal["chrome", "video_replay", "desktop"]
    app: str
    window_title: str
    url_template: str
    trigger: str
    dhash: str = ""
    gridfs_id: str | None = None
    thumb: bytes = b""
    display: dict[str, Any] = Field(default_factory=dict)
    ocr: dict[str, Any] = Field(default_factory=dict)
    click_target: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)
    embedding_model: str | None = None
    label: FrameLabel | None = None
    redactions: list[str] = Field(default_factory=list)
    expires_at: AwareDatetime


class Session(Contract):
    id: str = Field(alias="_id")
    user_id: str
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    status: Literal["open", "closed"]
    source: str
    signature_seq: list[str]
    intent_summary: str = ""
    intent_embedding: list[float] = Field(default_factory=list)
    embedding_model: str | None = None
    outcome: str | None = None
    tokens: int = 0
    minutes: float = 0
    artifacts: dict[str, list[str]] = Field(default_factory=dict)


class DynamicParam(Contract):
    name: str
    type: str


class Pattern(Contract):
    id: str = Field(alias="_id")
    user_id: str
    status: Literal["mined", "proposed", "accepted", "declined", "toolified", "stale"]
    title: str
    signature: list[str]
    static_steps: dict[str, Any]
    dynamic_params: list[DynamicParam]
    support: int
    distinct_days: int
    variance: float
    periodicity: float
    burstiness: float
    avg_minutes: float
    avg_tokens: int
    value: float
    evidence_session_ids: list[str]
    intent_centroid: list[float] = Field(default_factory=list)
    cooldown_until: AwareDatetime | None = None
    declined_reason: str | None = None


class Derivation(Contract):
    observed_tier: Tier
    execution_path: Literal["api", "browser", "cli", "assisted"]


class Requires(Contract):
    scopes: list[str] = Field(default_factory=list)
    deps: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class ToolSpec(Contract):
    name: str
    purpose: str
    params_schema: dict[str, Any]
    outputs: dict[str, Any] = Field(default_factory=dict)
    requires: Requires = Field(default_factory=Requires)
    keywords: list[str] = Field(default_factory=list)
    derivation: Derivation
    not_automatable: dict[str, str] | None = None


class Lineage(Contract):
    calls: list[str] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)
    merged_from: list[str] = Field(default_factory=list)
    merged_into: str | None = None


class ToolVersion(Contract):
    tool_id: str
    version: int = Field(ge=1)
    code: str
    params_schema: dict[str, Any]
    tests: str = ""
    fixtures_ref: list[str] = Field(default_factory=list)
    tutorial_md: str
    requires: Requires
    derivation: Derivation
    created_from: dict[str, str]
    approved_at: AwareDatetime | None = None


class ToolSummary(Contract):
    tool_id: str
    name: str
    title: str
    status: str
    trust: Trust
    runs: int
    success_rate: float
    p50_ms: float
    minutes_saved: float


class ToolDetail(ToolSummary):
    user_id: str
    tier: Literal["lean", "heavy"] = "lean"
    active_version: int
    lineage: Lineage = Field(default_factory=Lineage)
    version: ToolVersion


class ToolHit(Contract):
    tool_id: str
    name: str
    score: float


class ToolDep(Contract):
    tool_id: str
    name: str
    version: int
    code: str


class EpisodeHit(Contract):
    session_id: str
    date: AwareDatetime
    intent_summary: str
    minutes: float
    tokens: int
    score: float


class FrameEvidence(Contract):
    frame_id: str
    ts: AwareDatetime
    thumb_url: str
    verb: str


class WhyResponse(Contract):
    episodes: list[EpisodeHit]
    frames: list[FrameEvidence]


class Write(Contract):
    path: str
    kind: str = "file"


class SandboxResult(Contract):
    ok: bool
    output: dict[str, Any]
    intended_writes: list[Write]
    stdout: str
    error: str | None
    duration_ms: float


class RunResult(Contract):
    run_id: str
    mode: Literal["dry_run", "live"]
    output: dict[str, Any]
    intended_writes: list[Write]
    needs_confirm: bool
    duration_ms: float
    tokens: int
    route: Literal["found", "related", "not_found"] | None = None
    tool_id: str | None = None
    score: float | None = None


class Run(Contract):
    id: str = Field(alias="_id")
    tool_id: str
    version: int
    user_id: str
    tier: Literal["lean", "heavy"]
    trust_at_run: Trust
    outcome: str
    inputs: dict[str, Any]
    output_ref: str | None = None
    user_edited: bool = False
    cost: Cost = Field(default_factory=Cost)
    duration_ms: float = 0
    error: str | None = None
    started_at: AwareDatetime


class Verdict(Contract):
    id: str = Field(alias="_id")
    tool_id: str | None = None
    candidate_version: int
    checks: dict[str, bool]
    decision: Literal["passed", "failed"]
    reason: str


class Candidate(Contract):
    id: str = Field(alias="_id")
    user_id: str
    pattern_id: str | None = None
    idea_id: str | None = None
    spec: ToolSpec
    code: str
    tests: str
    tutorial_md: str
    params_schema: dict[str, Any]
    requires: Requires
    derivation: Derivation
    verdict_id: str | None = None
    verdict: Verdict | None = None
    status: Literal["gating", "passed", "failed", "approved", "rejected"]
    created_at: AwareDatetime


class PolicyChange(Contract):
    id: str
    field: str
    old: Any = Field(alias="from")
    new: Any = Field(alias="to")
    direction: Literal["tighten", "loosen"]
    because: str
    origin_feedback_ids: list[str]
    status: Literal["applied", "pending"]


class PolicyDoc(Contract):
    id: str = Field(alias="_id")
    version: int
    thresholds: dict[str, Any]
    rules: list[dict[str, Any]]
    changes: list[PolicyChange]


class LLMResult(Contract):
    text: str
    json_: dict[str, Any] | None = Field(default=None, alias="json")
    tokens_in: int
    tokens_out: int
    usd: float
    model: str
    cached: bool


class BaselineResult(Contract):
    race_id: str
    output: dict[str, Any]
    steps: int
    seconds: float
    tokens: int


class RaceStep(Contract):
    race_id: str
    side: Literal["baseline", "tool"]
    step: int
    label: str
    tokens: int
    elapsed_ms: float
    done: bool


class Metrics(Contract):
    minutes_saved_week: float
    tokens: dict[str, int]
    break_even_runs: float | None
    replay_pass_rate: float
    time_to_heal_seconds: float | None
    decoy_false_positive_rate: float
    toolbox_count: int
    ablation: dict[str, dict[str, int]]
    capture_quality: dict[str, float]
    cost_to_observe_usd_day: float
    race: dict[str, dict[str, float]]
    detection: dict[str, float] = Field(default_factory=dict)
    repair_loops: int = 0
    toolbox_size_over_time: list[dict[str, Any]] = Field(default_factory=list)


class CaptureState(Contract):
    paused: bool
    allowed_origins: list[str]


class CaptureSession(Contract):
    user_id: str
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    sources: list[str]
    apps_seen: list[str]
    frames_kept: int
    frames_dropped_by_rule: dict[str, int]
    paused: bool


class LineageNode(ToolDep):
    depth: int = Field(ge=0)


class LineageResponse(Contract):
    calls: list[LineageNode]
    merged_from: list[str]
    merged_into: str | None
    dependents: list[str]


class ChatReply(Contract):
    conversation_id: str
    reply: str
    tool_calls: list[dict[str, Any]]
    cards: list[dict[str, Any]]


class IdeaAnalysis(Contract):
    covered_by_tool_id: str | None
    feasible: bool
    scopes: list[str]
    deps: list[str]
    est_minutes_saved_week: float
    spec: ToolSpec | None


class Job(Contract):
    id: str = Field(alias="_id")
    type: JobType
    payload: dict[str, Any]
    status: Literal["queued", "running", "done", "failed"] = "queued"
    error: str | None = None
    created_at: AwareDatetime


class Event(Contract):
    type: EventType
    ts: datetime
    data: dict[str, Any]
