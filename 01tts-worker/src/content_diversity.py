"""Specific backend problems and conservative text overlap checks."""
import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class BackendTopic:
    category: str
    problem: str
    angle: str
    objective: str

    @property
    def title(self) -> str:
        return f"{self.problem} — {self.angle}"

    @property
    def prompt(self) -> str:
        return (
            f"Focus only on this backend problem: {self.problem}. "
            f"Learning objective: {self.objective}. "
            "Use one explicitly hypothetical production case. Include concrete evidence, "
            "a decision with trade-offs, and a way to verify the result. "
            "Do not pad the lesson with definitions of Java records, virtual threads, "
            "singletons, Docker containers, or a generic MySQL-versus-Redis comparison. "
            "Do not invent an actual incident, date, benchmark, or source."
        )


PROBLEMS = {
    "JAVA": [
        "Diagnosing a JVM memory leak with heap evidence",
        "Distinguishing a deadlock from a slow downstream call",
        "Propagating trace context across asynchronous Java tasks",
        "Bounding concurrency when a database pool has twenty connections",
        "Finding allocation hotspots behind garbage collection pauses",
        "Cancelling timed-out work without leaking resources",
        "Keeping mutable objects out of shared request state",
        "Choosing streaming instead of loading a large export into memory",
        "Diagnosing classloader retention after application reloads",
        "Avoiding time-zone errors in scheduled billing jobs",
        "Handling decimal rounding in payment calculations",
        "Testing race conditions in concurrent inventory updates",
    ],
    "SPRING": [
        "Finding why a Spring transaction was not applied",
        "Preventing a transaction from spanning a remote HTTP call",
        "Diagnosing connection pool exhaustion under a slow query",
        "Returning stable error contracts from a Spring API",
        "Stopping mass assignment in request-to-entity mapping",
        "Preventing duplicate scheduled jobs across service replicas",
        "Keeping readiness checks separate from liveness checks",
        "Shutting down a Spring service without losing in-flight requests",
        "Finding hidden N-plus-one queries in a paginated API",
        "Testing retries without replaying non-idempotent writes",
        "Validating configuration before a service accepts traffic",
        "Preventing sensitive fields from leaking through API responses",
    ],
    "DATA": [
        "Reading a MySQL execution plan for a slow range query",
        "Choosing a composite index for filtering and sorting",
        "Replacing deep offset pagination with a cursor",
        "Reproducing a lost update under concurrent writes",
        "Diagnosing lock waits during a bulk update",
        "Changing a large table without blocking production writes",
        "Handling replica lag in a read-after-write workflow",
        "Avoiding Redis hot keys during a flash sale",
        "Setting a memory budget and eviction policy for Redis",
        "Preventing stale cache writes after concurrent updates",
        "Verifying database restoration from a backup",
        "Rolling back a data migration with incompatible application versions",
    ],
    "DISTRIBUTED_SYSTEMS": [
        "Handling a consumer crash between database commit and acknowledgement",
        "Publishing events with a transactional outbox",
        "Ordering events for one customer across message partitions",
        "Recovering poison messages from a dead-letter queue",
        "Choosing an idempotency-key retention period",
        "Preventing retry amplification across three service layers",
        "Setting an end-to-end timeout budget across service calls",
        "Rejecting stale writers after a distributed lock expires",
        "Compensating a partially completed order workflow",
        "Detecting a missing event during reconciliation",
        "Applying backpressure when a consumer falls behind",
        "Handling clock skew in distributed event timestamps",
    ],
    "CLOUD_NATIVE": [
        "Tracing a latency spike across gateway, service, and database",
        "Distinguishing CPU throttling from a JVM performance problem",
        "Sizing Kubernetes memory limits without causing OOM restarts",
        "Avoiding dropped requests during a rolling deployment",
        "Investigating DNS failures inside a Kubernetes service",
        "Finding why a readiness probe removes every replica",
        "Designing alerts around user-visible error budgets",
        "Reducing high-cardinality metrics without losing diagnostics",
        "Testing a canary release and deciding when to roll back",
        "Rotating a service credential without downtime",
        "Containing a traffic surge with admission control",
        "Checking restore readiness after losing a deployment region",
    ],
}
ANGLES = [
    ("Diagnosis", "Reconstruct symptoms and a failure timeline; compare two hypotheses and the evidence that rules one out"),
    ("Design decision", "Compare two solutions under explicit constraints and explain the failure boundary of each"),
    ("Verification", "Build a reproducible experiment, define expected observations, and identify a misleading test result"),
    ("Recovery", "Choose immediate mitigation, define rollback triggers, and verify recovery before a permanent fix"),
]
TOPIC_CATALOG = tuple(
    BackendTopic(category, problem, angle, objective)
    for angle, objective in ANGLES
    for index in range(12)
    for category, problems in PROBLEMS.items()
    for problem in [problems[index]]
)

_STOP = set("a an the is are was were be been of to in on at for from with as by it its and or but if then we you they their our your can could should would may will do does not this that these those have has had".split())


def passage_signature(passage: str) -> Counter:
    words = [w for w in re.findall(r"[a-z]+", passage.lower()) if w not in _STOP]
    return Counter(zip(words, words[1:]))


def overlap_score(first: Counter, second: Counter) -> float:
    if not first or not second:
        return 0.0
    norm = math.sqrt(sum(n * n for n in first.values()) * sum(n * n for n in second.values()))
    return sum(n * second.get(term, 0) for term, n in first.items()) / norm


def duplicate_passage(passage: str, history: list[tuple[str, str]], threshold: float = 0.82) -> str | None:
    """Reject strong wording overlap; this is not a semantic equivalence model."""
    signature = passage_signature(passage)
    if sum(signature.values()) < 35 or passage.startswith("Audio-only lesson"):
        return None
    for content_uuid, previous in history:
        if previous.startswith("Audio-only lesson"):
            continue
        if overlap_score(signature, passage_signature(previous)) >= threshold:
            return content_uuid
    return None


def coverage_digest(lesson: dict, max_recap_chars: int = 240) -> str:
    """Summarize what a lesson covered so the generator can avoid repeating it."""
    title = " ".join(str(lesson.get("title") or "Untitled lesson").split())
    recap = str(lesson.get("simplifiedPassage") or "")
    if not recap.strip():
        recap = re.sub(r"^(Host|Expert):\s*", "", str(lesson.get("passage") or ""), flags=re.MULTILINE)
    recap = " ".join(recap.split())
    if len(recap) > max_recap_chars:
        recap = recap[:max_recap_chars].rsplit(" ", 1)[0] + "..."
    terms = [
        str(item.get("word")).strip()
        for item in (lesson.get("vocabulary") or [])[:6]
        if isinstance(item, dict) and str(item.get("word") or "").strip()
    ]
    digest = f"{title}: {recap}" if recap else title
    return digest + (f" Key terms: {', '.join(terms)}." if terms else "")
