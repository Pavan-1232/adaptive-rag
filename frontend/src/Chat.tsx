import { useEffect, useRef, useState } from "react";
import {
  api,
  PROVIDER_NAMES,
  type Answer,
  type Citation,
  type CloudProvider,
  type KeySources,
  type KnowledgeBase,
  type Provider,
} from "./api";
import Documents from "./Documents";

// newTopic: asked after "New topic", so follow-ups never reach back past it.
export type Turn = { question: string; answer?: Answer; error?: string; newTopic?: boolean };

/** The trace to link a follow-up to: the last successful turn, skipping failed ones, but never
 * crossing a "New topic" boundary. Turns are this knowledge base's chat only. */
export function linkableTraceId(turns: Turn[]): number | undefined {
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].answer) return turns[i].answer!.trace_id;
    if (turns[i].newTopic) return undefined;
  }
  return undefined;
}

type Props = {
  kb: KnowledgeBase;
  turns: Turn[];
  setTurns: (update: (turns: Turn[]) => Turn[]) => void;
  onKbChange: (kb: KnowledgeBase) => void;
  onKbDeleted: (id: number) => void;
};

const CLOUD: CloudProvider[] = ["openai", "gemini", "anthropic"];
// The last answer model picked, remembered in this browser. Only the provider name, never a key.
const LAST_PROVIDER = "lastProvider";

function readLastProvider(): string | null {
  try {
    return localStorage.getItem(LAST_PROVIDER);
  } catch {
    return null; // storage blocked (private window, previews): just don't remember
  }
}

function saveLastProvider(provider: Provider) {
  try {
    localStorage.setItem(LAST_PROVIDER, provider);
  } catch {
    // as above
  }
}

export default function Chat({ kb, turns, setTurns, onKbChange, onKbDeleted }: Props) {
  const [question, setQuestion] = useState("");
  const [provider, setProvider] = useState<Provider>("ollama");
  const [keys, setKeys] = useState<KeySources | null>(null);
  const [busy, setBusy] = useState(false);
  // "New topic": the next question isn't linked to the previous turn.
  const [newTopic, setNewTopic] = useState(false);
  const [showDocs, setShowDocs] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.keySources().then(setKeys).catch(() => setKeys(null));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [turns.length, busy]);

  const cloudWithKeys = CLOUD.filter((p) => keys && keys[p] !== "not set");
  // Usable here: Ollama, plus cloud providers with a key if this knowledge base allows cloud.
  const usable: Provider[] = ["ollama", ...(kb.allow_cloud ? cloudWithKeys : [])];
  const usableKey = usable.join(",");

  // Pre-select the last choice if it's usable here, else the first usable one. Re-checked when
  // keys load or cloud is switched on or off; the remembered choice itself is kept.
  useEffect(() => {
    const last = readLastProvider();
    setProvider(usable.find((p) => p === last) ?? usable[0]);
  }, [usableKey]);

  function choose(next: Provider) {
    setProvider(next);
    saveLastProvider(next);
  }

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    // The last successful turn of this knowledge base's chat (a failed turn doesn't break the
    // chain); the server decides whether the question is a follow-up and checks the KB.
    const previousTraceId = newTopic ? undefined : linkableTraceId(turns);
    setQuestion("");
    setBusy(true);
    setTurns((all) => [...all, { question: text, newTopic }]);
    setNewTopic(false);
    let result: Partial<Turn>;
    try {
      result = { answer: await api.ask(kb.id, text, provider, previousTraceId) };
    } catch (e) {
      result = { error: (e as Error).message };
    }
    setTurns((all) => all.map((turn, i) => (i === all.length - 1 ? { ...turn, ...result } : turn)));
    setBusy(false);
  }

  async function toggleCloud() {
    try {
      onKbChange(await api.setCloud(kb.id, !kb.allow_cloud));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function deleteKb() {
    try {
      await api.deleteKb(kb.id);
      onKbDeleted(kb.id);
    } catch (e) {
      setError((e as Error).message);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-3 border-b border-zinc-200 px-6 py-3">
        <h1 className="truncate text-base font-semibold">{kb.name}</h1>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <label className="flex cursor-pointer items-center gap-2 text-zinc-600" title="Cloud answer models send the retrieved passages to that provider.">
            <input type="checkbox" checked={kb.allow_cloud} onChange={toggleCloud} className="accent-zinc-900" />
            Allow cloud models
          </label>
          <button
            onClick={() => setShowDocs((v) => !v)}
            aria-expanded={showDocs}
            className="rounded-md border border-zinc-200 px-3 py-1 hover:bg-zinc-50"
          >
            Documents
          </button>
          {confirmDelete ? (
            <span className="flex items-center gap-2">
              <span className="text-red-700">Delete "{kb.name}" and all its documents?</span>
              <button onClick={deleteKb} className="rounded-md bg-red-600 px-3 py-1 text-white hover:bg-red-700">
                Delete
              </button>
              <button onClick={() => setConfirmDelete(false)} className="rounded-md px-2 py-1 hover:bg-zinc-100">
                Cancel
              </button>
            </span>
          ) : (
            <button onClick={() => setConfirmDelete(true)} className="rounded-md px-3 py-1 text-zinc-500 hover:bg-zinc-100 hover:text-red-700">
              Delete
            </button>
          )}
        </div>
      </header>

      {error && (
        <div role="alert" className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-8 px-6 py-8">
              {turns.length === 0 && (
                <p className="pt-16 text-center text-sm text-zinc-500">
                  Ask a question about the documents in {kb.name}. Answers cite document and page.
                </p>
              )}
              {turns.map((turn, i) => (
                <div key={i} className="space-y-3">
                  <div className="ml-auto w-fit max-w-[85%] rounded-2xl bg-zinc-100 px-4 py-2 text-sm">{turn.question}</div>
                  {turn.answer?.searched_question && turn.answer.searched_question !== turn.question && (
                    <p className="ml-auto w-fit max-w-[85%] text-xs text-zinc-500">Searched: {turn.answer.searched_question}</p>
                  )}
                  {turn.answer && <AnswerView answer={turn.answer} />}
                  {turn.error && (
                    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
                      {turn.error}
                    </div>
                  )}
                  {!turn.answer && !turn.error && (
                    <p className="text-sm text-zinc-400">Finding evidence and writing the answer…</p>
                  )}
                </div>
              ))}
              <div ref={bottom} />
            </div>
          </div>

          <form onSubmit={ask} className="border-t border-zinc-200 px-6 py-4">
            <div className="mx-auto max-w-3xl">
              <div className="flex items-end gap-2 rounded-xl border border-zinc-300 bg-white p-2 focus-within:border-zinc-500">
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) ask(e);
                  }}
                  placeholder="Ask a question…"
                  aria-label="Question"
                  rows={1}
                  maxLength={2000}
                  className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm focus:outline-none"
                />
                <select
                  value={provider}
                  onChange={(e) => choose(e.target.value as Provider)}
                  aria-label="Answer model"
                  className="rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-sm"
                >
                  <option value="ollama">{PROVIDER_NAMES.ollama}</option>
                  {cloudWithKeys.map((p) => (
                    <option key={p} value={p} disabled={!kb.allow_cloud}>
                      {PROVIDER_NAMES[p]}
                    </option>
                  ))}
                </select>
                <button
                  type="submit"
                  disabled={busy || !question.trim()}
                  className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-40"
                >
                  Ask
                </button>
              </div>
              {turns.length > 0 && (
                <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
                  <button
                    type="button"
                    onClick={() => setNewTopic((v) => !v)}
                    aria-pressed={newTopic}
                    className={`rounded-md border px-2 py-0.5 ${newTopic ? "border-zinc-900 bg-zinc-900 text-white" : "border-zinc-200 hover:bg-zinc-50"}`}
                  >
                    New topic
                  </button>
                  <span>{newTopic ? "The next question starts a new topic." : "Short follow-ups use the previous question."}</span>
                </div>
              )}
              {cloudWithKeys.length > 0 && !kb.allow_cloud && (
                <p className="mt-2 text-xs text-zinc-500">
                  Cloud models are off for this knowledge base. Turn on "Allow cloud models" to use them.
                </p>
              )}
            </div>
          </form>
        </div>
        {showDocs && <Documents kb={kb} />}
      </div>
    </div>
  );
}

const MARKER = /\[([^[\]]*\bE\d+\b[^[\]]*)\]/g;

export function AnswerView({ answer }: { answer: Answer }) {
  const [open, setOpen] = useState<Citation | null>(null);
  const byId = new Map(answer.citations.map((c) => [c.id, c]));
  const number = new Map(answer.citations.map((c, i) => [c.id, i + 1]));

  const chip = (citation: Citation) => (
    <button
      key={citation.id}
      onClick={() => setOpen(open?.id === citation.id ? null : citation)}
      aria-label={`Source ${number.get(citation.id)}: ${citation.label}`}
      aria-pressed={open?.id === citation.id}
      className={`mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded px-1 align-text-top text-xs font-medium ${
        open?.id === citation.id ? "bg-zinc-900 text-white" : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300"
      }`}
    >
      {number.get(citation.id)}
    </button>
  );

  // Replace [E1, E2] markers with clickable chips; unknown ids were already removed by the server.
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of answer.answer.matchAll(MARKER)) {
    parts.push(answer.answer.slice(last, match.index));
    for (const id of match[1].match(/\bE\d+\b/g) ?? []) {
      const citation = byId.get(id);
      if (citation) parts.push(chip(citation));
    }
    last = match.index! + match[0].length;
  }
  parts.push(answer.answer.slice(last));

  if (answer.status === "insufficient") {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm" role="status">
        <p className="font-medium text-amber-900">Not enough evidence</p>
        <p className="mt-1 text-amber-800">{answer.answer || "The documents don't contain enough information to answer this."}</p>
        {answer.warnings.map((w) => (
          <p key={w} className="mt-1 text-xs text-amber-700">{w}</p>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm leading-relaxed">
      {answer.status === "partial" && (
        <p className="text-xs font-medium text-amber-700">Partial answer: some parts of the question have no supporting evidence.</p>
      )}
      <p className="whitespace-pre-wrap">{parts}</p>
      {answer.warnings.map((w) => (
        <p key={w} className="text-xs text-amber-700">{w}</p>
      ))}
      {answer.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {answer.citations.map((c) => (
            <button
              key={c.id}
              onClick={() => setOpen(open?.id === c.id ? null : c)}
              className={`rounded-md border px-2 py-0.5 text-xs ${
                open?.id === c.id ? "border-zinc-900 bg-zinc-900 text-white" : "border-zinc-200 text-zinc-600 hover:bg-zinc-50"
              }`}
            >
              {number.get(c.id)}. {c.label}
            </button>
          ))}
        </div>
      )}
      {open && (
        <figure className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3" aria-label="Cited passage">
          <figcaption className="mb-2 flex flex-wrap items-baseline gap-x-2 text-xs text-zinc-500">
            <span className="font-medium text-zinc-800">{open.label}</span>
            {open.section_heading && <span>· {open.section_heading}</span>}
            {open.source === "expansion" && <span>· neighboring passage</span>}
            {open.source === "answer_key" && <span>· answer key, added for the question</span>}
          </figcaption>
          <blockquote className="max-h-72 overflow-y-auto whitespace-pre-wrap text-zinc-700">{open.passage}</blockquote>
        </figure>
      )}
      <p className="text-xs text-zinc-400">Answered by {PROVIDER_NAMES[answer.provider as Provider] ?? answer.provider}</p>
    </div>
  );
}
