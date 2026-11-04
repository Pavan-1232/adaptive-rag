"""The selection rule (DESIGN.md section 5).

1. Exclude candidates that failed checks. 2. Rank by mean Recall@budget on selection questions.
3. Paired bootstrap 95% CI of each candidate minus the leader. 4. An interval that includes zero
is a tie. 5. Among tied candidates, pick the simplest, then the smallest storage.
"""

from dataclasses import dataclass

from adaptive_rag.evaluation.stats import is_tie, paired_difference_ci

from .candidates import BY_ID


@dataclass
class Ranking:
    candidate_id: str
    mean: float
    difference_vs_leader: tuple[float, float, float]
    tied_with_leader: bool
    storage_tokens: int


def select(scores: dict[str, list[float]], storage: dict[str, int]) -> tuple[str, list[Ranking]]:
    """scores: candidate id -> Recall@budget per selection question, same question order."""
    if not scores:
        raise ValueError("no candidate to select from")
    means = {cid: sum(v) / len(v) if v else 0.0 for cid, v in scores.items()}
    leader = max(means, key=lambda cid: (means[cid], -BY_ID[cid].simplicity))
    rankings = []
    for cid, values in scores.items():
        ci = (0.0, 0.0, 0.0) if cid == leader else paired_difference_ci(values, scores[leader])
        rankings.append(
            Ranking(cid, means[cid], ci, cid == leader or is_tie(ci), storage.get(cid, 0))
        )
    tied = [r for r in rankings if r.tied_with_leader]
    winner = min(tied, key=lambda r: (BY_ID[r.candidate_id].simplicity, r.storage_tokens))
    rankings.sort(key=lambda r: -r.mean)
    return winner.candidate_id, rankings
