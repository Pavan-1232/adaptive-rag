"""Run the adopted audit judge on the saved answers from the original baseline run.

Labels are the assistant's reading: 25 correct and 3 wrong, pending the user's check.
Run from the repo root: python benchmarks/analysis/audit_false_alarms.py
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from judge_probes import REAL_WRONG

from adaptive_rag.evaluation.__main__ import DOCUMENTS, JUDGE_MODEL, _providers, _settings
from adaptive_rag.evaluation.benchmark import load_manifest
from adaptive_rag.evaluation.judge import judge_answer
from adaptive_rag.evaluation.runner import build_index
from adaptive_rag.providers import OllamaLLM
from adaptive_rag.retrieval import fit_to_budget, retrieve_baseline

RESULTS = Path("benchmarks/results")
BASE_RUN = RESULTS / "dev_embeddinggemma_300m_20261030T084407.json"


def main():
    settings = _settings("dev", "embeddinggemma:300m")
    embedder, llm = _providers(settings)
    ctx, kb, _ = build_index(
        settings, embedder, llm, load_manifest(split="dev"), DOCUMENTS, "benchmark-dev"
    )
    judge = OllamaLLM(JUDGE_MODEL, settings.ollama_host, settings.num_ctx)
    rows = []
    for saved in json.loads(BASE_RUN.read_text())["results"]:
        if not saved["answerable"] or saved["status"] != "answered":
            continue
        pool = retrieve_baseline(ctx, kb, saved["question"], settings.top_k)
        evidence = [c.text for c in fit_to_budget(pool, settings.evidence_max_tokens)]
        judgment = judge_answer(judge, saved["question"], saved["answer"], evidence)
        row = {
            "id": saved["id"],
            "label": "wrong" if saved["id"] in REAL_WRONG else "correct",
            "usable": judgment is not None,
        }
        if judgment is not None:
            row["llm_flag"] = any(not c.supported for c in judgment.claims)
            row["code_flag"] = any(not c.verified for c in judgment.claims)
            row["off_topic_flag"] = not judgment.addresses_question
            row["faithfulness"] = judgment.faithfulness
            row["claims"] = [c.model_dump() for c in judgment.claims]
        rows.append(row)
        print(
            row["id"], row["label"], {k: row.get(k) for k in row if k.endswith("flag")}, flush=True
        )
    judge.unload()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    (RESULTS / f"audit_false_alarms_{stamp}.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
