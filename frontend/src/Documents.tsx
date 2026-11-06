import { useCallback, useEffect, useRef, useState } from "react";
import { api, uploadFile, type Doc, type KnowledgeBase } from "./api";

type Upload = { name: string; progress: number; stage: "uploading" | "indexing" | "done" | "failed"; message?: string };

const POLL_MS = 1000;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default function Documents({ kb }: { kb: KnowledgeBase }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    api.listDocs(kb.id).then(setDocs).catch((e: Error) => setError(e.message));
  }, [kb.id]);

  useEffect(refresh, [refresh]);

  const update = (name: string, change: Partial<Upload>) =>
    setUploads((all) => all.map((u) => (u.name === name ? { ...u, ...change } : u)));

  async function upload(file: File) {
    setUploads((all) => [...all.filter((u) => u.name !== file.name), { name: file.name, progress: 0, stage: "uploading" }]);
    try {
      const result = await uploadFile(kb.id, file, (progress) => update(file.name, { progress }));
      if (result.duplicate) {
        update(file.name, { stage: "done", progress: 1, message: "Already uploaded (same content)." });
      } else if (result.job_id !== null) {
        update(file.name, { stage: "indexing", progress: 1 });
        refresh();
        for (;;) {
          const job = await api.job(result.job_id);
          if (job.status === "succeeded") {
            update(file.name, { stage: "done", message: "Indexed." });
            break;
          }
          if (job.status === "failed") {
            update(file.name, { stage: "failed", message: job.error ?? "Indexing failed." });
            break;
          }
          await sleep(POLL_MS);
        }
      }
    } catch (e) {
      update(file.name, { stage: "failed", message: (e as Error).message });
    }
    refresh();
  }

  async function remove(doc: Doc) {
    if (!window.confirm(`Delete "${doc.filename}"?`)) return;
    try {
      await api.deleteDoc(doc.id);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-zinc-200 bg-zinc-50" aria-label="Documents">
      <div className="space-y-3 border-b border-zinc-200 p-4">
        <h2 className="text-sm font-semibold">Documents</h2>
        <button
          onClick={() => input.current?.click()}
          className="w-full rounded-md border border-dashed border-zinc-300 bg-white px-3 py-3 text-sm text-zinc-600 hover:border-zinc-400"
        >
          Upload PDF, DOCX or TXT
        </button>
        <input
          ref={input}
          type="file"
          accept=".pdf,.docx,.txt"
          multiple
          hidden
          data-testid="file-input"
          onChange={(e) => {
            Array.from(e.target.files ?? []).forEach(upload);
            e.target.value = "";
          }}
        />
        {uploads.map((u) => (
          <div key={u.name} className="space-y-1 text-xs">
            <div className="flex justify-between gap-2">
              <span className="truncate">{u.name}</span>
              <span className="shrink-0 text-zinc-500">
                {u.stage === "uploading" ? `${Math.round(u.progress * 100)}%` : u.stage === "indexing" ? "Indexing…" : ""}
              </span>
            </div>
            {(u.stage === "uploading" || u.stage === "indexing") && (
              <div className="h-1 overflow-hidden rounded bg-zinc-200">
                <div
                  role="progressbar"
                  aria-valuenow={Math.round(u.progress * 100)}
                  className={`h-full bg-zinc-800 ${u.stage === "indexing" ? "animate-pulse" : ""}`}
                  style={{ width: `${u.progress * 100}%` }}
                />
              </div>
            )}
            {u.message && <p className={u.stage === "failed" ? "text-red-700" : "text-zinc-500"}>{u.message}</p>}
          </div>
        ))}
        {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
      </div>
      <ul className="flex-1 divide-y divide-zinc-200 overflow-y-auto">
        {docs.length === 0 && <li className="p-4 text-xs text-zinc-500">No documents yet.</li>}
        {docs.map((doc) => (
          <li key={doc.id} className="group flex items-start gap-2 px-4 py-2.5 text-sm">
            <div className="min-w-0 flex-1">
              <p className="truncate">{doc.filename}</p>
              <p className={`text-xs ${doc.status === "failed" ? "text-red-700" : "text-zinc-500"}`}>
                {doc.status === "failed" ? doc.error ?? "Failed" : doc.status}
                {doc.version > 1 && ` · v${doc.version}`}
              </p>
              {doc.warnings.map((w) => (
                <p key={w} className="text-xs text-amber-700">{w}</p>
              ))}
            </div>
            {doc.status !== "pending" && doc.status !== "indexing" && (
              <button
                onClick={() => remove(doc)}
                aria-label={`Delete ${doc.filename}`}
                className="text-xs text-zinc-400 opacity-0 group-hover:opacity-100 hover:text-red-700 focus:opacity-100"
              >
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
