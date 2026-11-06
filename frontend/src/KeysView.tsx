import { useEffect, useRef, useState } from "react";
import { api, PROVIDER_NAMES, type CloudProvider, type KeySources } from "./api";

const PROVIDERS: CloudProvider[] = ["openai", "gemini", "anthropic"];

const SOURCE_TEXT = {
  keychain: "Saved in the system keychain",
  env: "Set in .env (edit it there)",
  "not set": "Not set",
};

export default function KeysView() {
  const [sources, setSources] = useState<KeySources | null>(null);
  const [error, setError] = useState("");

  const load = () =>
    api
      .keySources()
      .then(setSources)
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-6 px-6 py-8">
        <div>
          <h1 className="text-base font-semibold">API keys</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Optional. Keys are stored in your system keychain and never shown again. Ollama runs locally and needs no key.
          </p>
        </div>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <div className="divide-y divide-zinc-200 rounded-lg border border-zinc-200">
          {sources &&
            PROVIDERS.map((p) => (
              <KeyRow key={p} provider={p} source={sources[p]} onChange={load} onError={setError} />
            ))}
        </div>
      </div>
    </div>
  );
}

function KeyRow({
  provider,
  source,
  onChange,
  onError,
}: {
  provider: CloudProvider;
  source: KeySources[CloudProvider];
  onChange: () => void;
  onError: (message: string) => void;
}) {
  // Uncontrolled input: the key is never held in React state, and the field is cleared after sending.
  const field = useRef<HTMLInputElement>(null);
  const [saving, setSaving] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const key = field.current?.value ?? "";
    if (field.current) field.current.value = "";
    if (!key.trim()) return;
    setSaving(true);
    try {
      await api.saveKey(provider, key);
      onError("");
    } catch (e) {
      onError((e as Error).message);
    }
    setSaving(false);
    onChange();
  }

  async function remove() {
    try {
      await api.removeKey(provider);
      onError("");
    } catch (e) {
      onError((e as Error).message);
    }
    onChange();
  }

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="w-40">
        <p className="text-sm font-medium">{PROVIDER_NAMES[provider]}</p>
        <p className="text-xs text-zinc-500" data-testid={`source-${provider}`}>
          {SOURCE_TEXT[source]}
        </p>
      </div>
      {source === "keychain" && (
        <button onClick={remove} className="ml-auto rounded-md px-3 py-1 text-sm text-zinc-500 hover:bg-zinc-100 hover:text-red-700">
          Remove
        </button>
      )}
      {source === "not set" && (
        <form onSubmit={save} className="ml-auto flex gap-2">
          <input
            ref={field}
            type="password"
            autoComplete="off"
            spellCheck={false}
            aria-label={`${PROVIDER_NAMES[provider]} API key`}
            placeholder="Paste key"
            className="w-56 rounded-md border border-zinc-300 px-2 py-1 text-sm focus:border-zinc-500 focus:outline-none"
          />
          <button type="submit" disabled={saving} className="rounded-md bg-zinc-900 px-3 py-1 text-sm text-white disabled:opacity-40">
            Save
          </button>
        </form>
      )}
    </div>
  );
}
