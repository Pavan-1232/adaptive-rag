import { useEffect, useState } from "react";
import { api, type Evaluation } from "./api";

const fmt = (x: number) => x.toFixed(3);
const signed = (x: number) => (x > 0 ? "+" : "") + x.toFixed(3);
const withCi = ([mean, low, high]: number[]) => `${fmt(mean)} (95% CI ${fmt(low)}–${fmt(high)})`;

const verdictStyle = (verdict: string) =>
  verdict.startsWith("better")
    ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
    : verdict.startsWith("worse")
      ? "bg-red-50 text-red-800 ring-red-200"
      : "bg-zinc-100 text-zinc-700 ring-zinc-200";

export default function EvaluationView() {
  const [data, setData] = useState<Evaluation | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.evaluation().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        <div>
          <h1 className="text-base font-semibold">Evaluation</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Measured results, read from the committed result files. Nothing here is estimated.
          </p>
        </div>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {data && (
          <>
            <p className="text-sm text-zinc-600">{data.dataset}</p>
            <section className="rounded-lg border border-zinc-200 p-4">
              <h2 className="text-sm font-semibold">Baseline · {data.baseline.name}</h2>
              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
                <dt className="text-zinc-500">Recall@budget</dt>
                <dd>{withCi(data.baseline.recall_at_budget)}</dd>
                <dt className="text-zinc-500">Hit rate@5</dt>
                <dd>{withCi(data.baseline.hit_at_5)}</dd>
                <dt className="text-zinc-500">MRR</dt>
                <dd>{withCi(data.baseline.reciprocal_rank)}</dd>
                <dt className="text-zinc-500">Unanswerable refused</dt>
                <dd>
                  {data.baseline.unanswerable_refused} of {data.baseline.unanswerable}
                </dd>
                <dt className="text-zinc-500">Answer time (median)</dt>
                <dd>{data.baseline.generation_p50_s.toFixed(1)} s</dd>
              </dl>
            </section>
            <section className="space-y-3">
              <h2 className="text-sm font-semibold">Compared with the baseline</h2>
              {data.comparisons.map((c) => (
                <div key={c.name} className="rounded-lg border border-zinc-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="text-sm font-medium">{c.name}</h3>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${verdictStyle(c.verdict)}`}>
                      {c.verdict}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-zinc-700">
                    {c.metric}: difference {signed(c.difference)} (95% CI {signed(c.ci_low)} to {signed(c.ci_high)}), {c.n} questions
                  </p>
                  {c.note && <p className="mt-1 text-xs text-zinc-500">{c.note}</p>}
                </div>
              ))}
            </section>
            <p className="text-xs text-zinc-400">Sources: {data.sources.join(", ")}</p>
          </>
        )}
      </div>
    </div>
  );
}
