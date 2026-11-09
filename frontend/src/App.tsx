import { useEffect, useState } from "react";
import { api, type Health, type KnowledgeBase } from "./api";
import Chat, { type Turn } from "./Chat";
import EvaluationView from "./EvaluationView";
import KeysView from "./KeysView";

type View = "chat" | "keys" | "evaluation";

export default function App() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [view, setView] = useState<View>("chat");
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  // Chat history per knowledge base, kept in memory for this page only.
  const [history, setHistory] = useState<Record<number, Turn[]>>({});

  useEffect(() => {
    api
      .listKbs()
      .then((list) => {
        setKbs(list);
        setSelectedId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((e: Error) => setError(e.message));
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const selected = kbs.find((kb) => kb.id === selectedId) ?? null;

  async function createKb(event: React.FormEvent) {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      const kb = await api.createKb(newName.trim());
      setKbs((list) => [...list, kb]);
      setSelectedId(kb.id);
      setView("chat");
      setNewName("");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function onKbChange(kb: KnowledgeBase) {
    setKbs((list) => list.map((item) => (item.id === kb.id ? kb : item)));
  }

  function onKbDeleted(id: number) {
    const rest = kbs.filter((kb) => kb.id !== id);
    setKbs(rest);
    setSelectedId(rest[0]?.id ?? null);
    setHistory(({ [id]: _, ...others }) => others);
  }

  const navButton = (target: View, label: string) => (
    <button
      onClick={() => setView(target)}
      className={`w-full rounded-md px-3 py-1.5 text-left text-sm ${
        view === target ? "bg-zinc-200 font-medium" : "text-zinc-600 hover:bg-zinc-100"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex h-screen">
      <aside className="flex w-64 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50">
        <div className="px-4 pt-5 pb-3 text-sm font-semibold tracking-tight">Adaptive RAG</div>
        <div className="px-4 pb-1 text-xs font-medium uppercase tracking-wide text-zinc-400">
          Knowledge bases
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2" aria-label="Knowledge bases">
          {kbs.map((kb) => (
            <button
              key={kb.id}
              onClick={() => {
                setSelectedId(kb.id);
                setView("chat");
              }}
              aria-current={view === "chat" && kb.id === selectedId ? "page" : undefined}
              className={`w-full truncate rounded-md px-3 py-1.5 text-left text-sm ${
                view === "chat" && kb.id === selectedId
                  ? "bg-white font-medium shadow-sm ring-1 ring-zinc-200"
                  : "text-zinc-700 hover:bg-zinc-100"
              }`}
            >
              {kb.name}
            </button>
          ))}
          <form onSubmit={createKb} className="px-1 pt-2">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="+ New knowledge base"
              aria-label="New knowledge base name"
              maxLength={100}
              className="w-full rounded-md border border-transparent bg-transparent px-2 py-1.5 text-sm placeholder:text-zinc-400 focus:border-zinc-300 focus:bg-white focus:outline-none"
            />
          </form>
        </nav>
        <div className="space-y-0.5 border-t border-zinc-200 p-2">
          {navButton("keys", "API keys")}
          {navButton("evaluation", "Evaluation")}
          {health && health.status !== "ok" && (
            <p className="px-3 pt-2 text-xs text-amber-700">
              Ollama isn't fully available. Local answers may fail.
            </p>
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        {error && (
          <div role="alert" className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        {view === "keys" && <KeysView />}
        {view === "evaluation" && <EvaluationView />}
        {view === "chat" &&
          (selected ? (
            <Chat
              key={selected.id}
              kb={selected}
              turns={history[selected.id] ?? []}
              setTurns={(update) =>
                setHistory((all) => ({ ...all, [selected.id]: update(all[selected.id] ?? []) }))
              }
              onKbChange={onKbChange}
              onKbDeleted={onKbDeleted}
            />
          ) : (
            <div className="m-auto max-w-sm text-center text-sm text-zinc-500">
              Create a knowledge base in the sidebar to get started.
            </div>
          ))}
      </main>
    </div>
  );
}
