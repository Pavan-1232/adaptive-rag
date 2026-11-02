"""Replay score floors against recorded results, without re-running the LLM."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FloorOutcome:
    floor: float
    answerable_blocked: float
    gate_refused_near_miss: float | None
    gate_refused_out_of_scope: float | None
    system_refused_unanswerable: float | None
    false_answers: int
    llm_calls_saved: float


def _share(items: list[bool]) -> float | None:
    return sum(items) / len(items) if items else None


def evaluate_floor(results: list[dict], floor: float) -> FloorOutcome:
    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]
    near_miss = [r for r in unanswerable if r["type"] == "near_miss"]
    out_of_scope = [r for r in unanswerable if r["type"] == "out_of_scope"]

    def gated(result: dict) -> bool:
        return result["top_score"] is None or result["top_score"] < floor

    def refused(result: dict) -> bool:
        return gated(result) or result.get("status") == "insufficient"

    return FloorOutcome(
        floor=floor,
        answerable_blocked=_share([gated(r) for r in answerable]) or 0.0,
        gate_refused_near_miss=_share([gated(r) for r in near_miss]),
        gate_refused_out_of_scope=_share([gated(r) for r in out_of_scope]),
        system_refused_unanswerable=_share([refused(r) for r in unanswerable]),
        false_answers=sum(not refused(r) for r in unanswerable),
        llm_calls_saved=_share([gated(r) for r in results]) or 0.0,
    )


def sweep(results: list[dict], step: float = 0.02) -> list[FloorOutcome]:
    count = int(round(1 / step))
    return [evaluate_floor(results, round(index * step, 4)) for index in range(count + 1)]


def choose_floor(outcomes: list[FloorOutcome], max_blocked: float = 0.05) -> FloorOutcome:
    """The highest floor that wrongly blocks at most max_blocked of answerable questions."""
    allowed = [outcome for outcome in outcomes if outcome.answerable_blocked <= max_blocked]
    return allowed[-1]
