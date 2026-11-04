"""Evaluation commands: python -m adaptive_rag.evaluation <command>"""

import argparse
import json
import platform
import subprocess
import sys
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from adaptive_rag.config import Settings
from adaptive_rag.loaders import LOADERS
from adaptive_rag.providers import OllamaEmbeddings, OllamaLLM

from .benchmark import BENCHMARK_DIR, file_sha256, load_manifest, load_questions
from .calibration import choose_floor, sweep
from .judge import CHECK_VERSION, PROMPT_VERSION
from .questions import generate_questions
from .report import render_markdown, summarize
from .runner import (
    RECALL_BUDGET_TOKENS,
    build_index,
    is_complete,
    load_partial,
    resume_conflicts,
    run_benchmark,
    save_results,
)
from .spans import locate_quote, page_range
from .stats import is_tie, paired_difference_ci

DOCUMENTS = BENCHMARK_DIR / "documents"
RESULTS = BENCHMARK_DIR / "results"
JUDGE_MODEL = "gemma4:e4b"


def _commit() -> str:
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
    )
    dirty = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain"],  # noqa: S607
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() + ("+uncommitted" if dirty.stdout.strip() else "")


SYSTEMS = {
    "fixed": "A (fixed 512/50, top-5)",  # Stage 3's system A, in its original index folder
    "C1": "A (C1 fixed 512/50, top-5)",
    "C7": "C7 (table-aware 512/50, top-5)",
    "adaptive": "C (per-document optimizer, top-5)",
}


def _settings(split: str, model: str, chunking: str = "fixed") -> Settings:
    """Each chunking mode gets its own index folder, so systems never share chunks."""
    slug = model.replace(":", "_")
    folder = f"{split}_{slug}" if chunking == "fixed" else f"{split}_{slug}_{chunking}"
    return Settings(
        data_dir=Path("data") / "eval" / folder, embedding_model=model, chunking=chunking
    )


def _providers(settings: Settings):
    embedder = OllamaEmbeddings(
        settings.embedding_model, settings.ollama_host, settings.embedding_batch_size
    )
    return embedder, OllamaLLM(settings.llm_model, settings.ollama_host, settings.num_ctx)


def cmd_download(_: argparse.Namespace) -> int:
    failed = 0
    for item in load_manifest():
        path = DOCUMENTS / item.file
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            request = urllib.request.Request(item.url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
                path.write_bytes(response.read())
        matches = file_sha256(path) == item.sha256
        failed += not matches
        print(f"{item.file}: {'ok' if matches else 'HASH MISMATCH'}")
    return 1 if failed else 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Check format and quotes. Prints IDs and errors only, so test questions stay unseen."""
    questions = load_questions(Path(args.file))
    manifest = {item.name: item for item in load_manifest()}
    problems: list[str] = []
    texts: dict[str, object] = {}
    for question in questions:
        item = manifest.get(question.document)
        if item is None:
            problems.append(f"{question.id}: unknown document {question.document}")
            continue
        if question.document not in texts:
            texts[question.document] = LOADERS["pdf"].extract(DOCUMENTS / item.file)
        doc = texts[question.document]
        options = [o for evidence in question.evidence for o in (evidence, *evidence.alternatives)]
        for evidence in options:
            found = locate_quote(doc.text, evidence.quote, page_range(doc.units, evidence.page))
            if found is None:
                problems.append(f"{question.id}: quote not found")
                continue
            pages = [unit.number for unit in doc.units if unit.start <= found[0]]
            if evidence.page is not None and pages and pages[-1] != evidence.page:
                problems.append(f"{question.id}: quote is on page {pages[-1]}, not {evidence.page}")
    counts: dict[str, int] = {}
    for question in questions:
        counts[question.type] = counts.get(question.type, 0) + 1
    print(f"{len(questions)} questions; by type: {counts}")
    print("\n".join(problems) if problems else "All quotes found on their stated pages.")
    return 1 if problems else 0


def cmd_generate(args: argparse.Namespace) -> int:
    settings = _settings("dev", args.embedding_model)
    _, llm = _providers(settings)
    all_questions = []
    for item in load_manifest(split="dev"):
        doc = LOADERS["pdf"].extract(DOCUMENTS / item.file)
        questions, rejected = generate_questions(llm, doc, item.name, args.per_type)
        print(f"{item.name}: kept {len(questions)}; rejected {rejected}", flush=True)
        all_questions += [question.model_dump(exclude_none=True) for question in questions]
    Path(args.output).write_text(yaml.safe_dump(all_questions, sort_keys=False, allow_unicode=True))
    print(f"wrote {len(all_questions)} questions to {args.output}")
    return 0


def _metadata(args, settings, embedder, split, question_source, judge_model) -> dict:
    return {
        "system": SYSTEMS.get(getattr(args, "chunking", "fixed"), getattr(args, "chunking", "")),
        "chunking": getattr(args, "chunking", "fixed"),
        "set": split,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "embedding_model": settings.embedding_model,
        "embedding_version": embedder.version(),
        "llm_model": settings.llm_model,
        "judge_model": judge_model,
        "judge_prompt": PROMPT_VERSION if judge_model != "none" else None,
        "judge_check": CHECK_VERSION if judge_model != "none" else None,
        "recall_budget_tokens": RECALL_BUDGET_TOKENS,
        "questions_sha256": file_sha256(Path(args.questions))
        if hasattr(args, "questions")
        else None,
        "retrieval_only": getattr(args, "retrieval_only", False),
        "machine": f"{platform.machine()} {platform.system()} {platform.release()}",
        "question_source": question_source,
        "notes": getattr(args, "notes", None),
    }


def cmd_run(args: argparse.Namespace) -> int:
    if args.set == "test" and not args.final:
        print("The test set is held out. Pass --final to run it, once per release.")
        return 2
    settings = _settings(args.set, args.embedding_model, args.chunking)
    embedder, llm = _providers(settings)
    documents = load_manifest(split=args.set)
    ctx, kb, indexed = build_index(
        settings, embedder, llm, documents, DOCUMENTS, f"benchmark-{args.set}"
    )
    questions = load_questions(Path(args.questions))
    judge = None
    if args.judge:
        judge = OllamaLLM(args.judge, settings.ollama_host, settings.num_ctx)
    metadata = _metadata(
        args, settings, embedder, args.set, args.question_source, args.judge or "none"
    )

    done = {}
    if args.resume:
        path = Path(args.resume)
        saved, done = load_partial(path)
        conflicts = resume_conflicts(saved, metadata)
        if conflicts:
            print(f"Can't resume {path}: these differ from the saved run: {', '.join(conflicts)}")
            return 2
        metadata = {**saved, "resumed": [*saved.get("resumed", []), metadata["created_at"]]}
        if saved.get("commit") != metadata.get("commit"):
            metadata["resumed_commits"] = [*saved.get("resumed_commits", []), _commit()]
        print(f"Resuming {path}: {len(done)} of {len(questions)} questions already answered.")
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        suffix = "" if args.chunking == "fixed" else f"_{args.chunking}"
        model = args.embedding_model.replace(":", "_")
        path = RESULTS / f"{args.set}_{model}{suffix}_{stamp}.json"
        print(f"Saving progress to {path}. To resume after a stop, add: --resume {path}")

    def progress(result) -> None:
        print(f"{result.id}: {result.status} top={result.top_score}", flush=True)

    results = run_benchmark(
        ctx,
        kb,
        indexed,
        questions,
        answers=not args.retrieval_only,
        judge=judge,
        on_progress=progress,
        done=done,
        on_save=lambda so_far: save_results(path, metadata, so_far, complete=False),
    )
    save_results(path, metadata, results)
    rows = [asdict(result) for result in results]
    path.with_suffix(".md").write_text(render_markdown(metadata, summarize(rows)))
    print(f"wrote {path}")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.results).read_text())
    if not is_complete(payload):
        print("This run is incomplete. Resume it with: run --resume <file>")
        return 2
    if payload["metadata"]["set"] != "dev":
        print("Calibrate on dev results only.")
        return 2
    outcomes = sweep(payload["results"])
    chosen = choose_floor(outcomes, args.max_blocked)
    print("floor blocked near_miss out_of_scope system_refused false_answers saved")
    for outcome in outcomes[:51]:
        if outcome.floor <= 0.8:
            print(
                f"{outcome.floor:.2f} {outcome.answerable_blocked:.2f} "
                f"{outcome.gate_refused_near_miss} {outcome.gate_refused_out_of_scope} "
                f"{outcome.system_refused_unanswerable} {outcome.false_answers} "
                f"{outcome.llm_calls_saved:.2f}"
            )
    print("chosen:", asdict(chosen))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare two result files on the same questions, retrieval metrics only."""
    first = json.loads(Path(args.first).read_text())
    second = json.loads(Path(args.second).read_text())
    if not (is_complete(first) and is_complete(second)):
        print("At least one run is incomplete. Resume it with: run --resume <file>")
        return 2
    budgets = [run["metadata"].get("recall_budget_tokens", 2000) for run in (first, second)]
    if budgets[0] != budgets[1]:
        print(f"Not comparable: Recall@budget used {budgets[0]} and {budgets[1]} tokens.")
        return 2
    a = {r["id"]: r for r in first["results"] if r["answerable"]}
    b = {r["id"]: r for r in second["results"] if r["answerable"]}
    if a.keys() != b.keys():
        print("Result files cover different questions.")
        return 2
    ids = sorted(a)
    labels = [
        f"{r['metadata']['system']} [{r['metadata']['embedding_model']}]" for r in (first, second)
    ]
    print(f"{labels[0]} minus {labels[1]}")
    for key in ("recall_at_budget", "recall_at_5", "hit_at_5", "reciprocal_rank"):
        ci = paired_difference_ci([a[i][key] for i in ids], [b[i][key] for i in ids])
        verdict = "tie" if is_tie(ci) else "different"
        print(f"{key}: {ci[0]:+.3f} (95% CI {ci[1]:+.3f} to {ci[2]:+.3f}) {verdict}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m adaptive_rag.evaluation")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("download", help="download benchmark PDFs and verify hashes")

    validate = commands.add_parser("validate", help="check a question file")
    validate.add_argument("file")

    generate = commands.add_parser("generate", help="generate dev questions with the LLM")
    generate.add_argument("--per-type", type=int, default=6)
    generate.add_argument("--output", default=str(BENCHMARK_DIR / "questions_dev_generated.yaml"))
    generate.add_argument("--embedding-model", default="embeddinggemma:300m")

    run = commands.add_parser("run", help="run a benchmark")
    run.add_argument("--set", choices=["dev", "test"], required=True)
    run.add_argument("--questions", required=True)
    run.add_argument("--embedding-model", default="embeddinggemma:300m")
    run.add_argument("--retrieval-only", action="store_true")
    run.add_argument(
        "--chunking",
        default="fixed",
        choices=sorted(SYSTEMS) + ["C2", "C3", "C4", "C5", "C6"],
        help="fixed (Stage 3 A), C1-C7 (one config for every document), or adaptive (C)",
    )
    run.add_argument("--judge", nargs="?", const=JUDGE_MODEL, default=None)
    run.add_argument("--final", action="store_true", help="required for the held-out test set")
    run.add_argument("--question-source", default="unspecified")
    run.add_argument("--notes", default=None)
    run.add_argument("--resume", default=None, help="continue a stopped run from its results file")

    calibrate = commands.add_parser("calibrate", help="sweep score floors on dev results")
    calibrate.add_argument("results")
    calibrate.add_argument("--max-blocked", type=float, default=0.05)

    compare = commands.add_parser("compare", help="compare two result files")
    compare.add_argument("first")
    compare.add_argument("second")

    args = parser.parse_args()
    handlers = {
        "download": cmd_download,
        "validate": cmd_validate,
        "generate": cmd_generate,
        "run": cmd_run,
        "calibrate": cmd_calibrate,
        "compare": cmd_compare,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
