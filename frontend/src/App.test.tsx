import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { linkableTraceId } from "./Chat";
import type { Answer } from "./api";

// A tiny fake backend: "METHOD /path" -> [status, body] or a function of the request body.
type Route = [number, unknown] | ((body: unknown) => [number, unknown]);
let routes: Record<string, Route>;
let calls: { key: string; body: unknown }[];

const KB = { id: 1, name: "MBA Materials", allow_cloud: false, embedding_model: "e" };
const KEYS_NONE = { openai: "not set", gemini: "not set", anthropic: "not set" };

beforeEach(() => {
  calls = [];
  routes = {
    "GET /api/kbs": [200, [KB]],
    "GET /api/health": [200, { status: "ok", embedding_model: true, llm_model: true }],
    "GET /api/keys": [200, KEYS_NONE],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      const body = init?.body ? JSON.parse(init.body as string) : undefined;
      calls.push({ key, body });
      const route = routes[key];
      if (!route) return new Response(JSON.stringify({ detail: `no route ${key}` }), { status: 404 });
      const [status, payload] = typeof route === "function" ? route(body) : route;
      return new Response(status === 204 ? null : JSON.stringify(payload), { status });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

const answer = (overrides: Partial<Answer> = {}): Answer => ({
  status: "answered",
  answer: "Revenue grew 8% [E1]. Costs fell [E1, E2].",
  citations: [
    {
      id: "E1", document_id: 3, filename: "report.pdf", label: "report.pdf, p. 4",
      section_heading: "Results", snippet: "Revenue grew", passage: "Revenue grew 8% in 2024, driven by services.", source: "direct",
    },
    {
      id: "E2", document_id: 3, filename: "report.pdf", label: "report.pdf, p. 5",
      section_heading: null, snippet: "Costs", passage: "Costs fell 2%.", source: "expansion",
    },
  ],
  warnings: [],
  provider: "ollama",
  trace_id: 1,
  ...overrides,
});

async function ask(question: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Question"), question);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return user;
}

describe("knowledge bases", () => {
  it("lists knowledge bases and creates a new one", async () => {
    routes["POST /api/kbs"] = (body) => [201, { ...KB, id: 2, name: (body as { name: string }).name }];
    render(<App />);
    const nav = await screen.findByRole("navigation", { name: "Knowledge bases" });
    expect(await within(nav).findByText("MBA Materials")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("New knowledge base name"), "Research Papers{Enter}");
    expect(await within(nav).findByText("Research Papers")).toBeInTheDocument();
    expect(calls).toContainEqual({ key: "POST /api/kbs", body: { name: "Research Papers" } });
  });

  it("deletes a knowledge base only after confirming", async () => {
    routes["DELETE /api/kbs/1"] = [204, null];
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(calls.some((c) => c.key === "DELETE /api/kbs/1")).toBe(false);
    expect(screen.getByText(/Delete "MBA Materials" and all its documents\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.getByText(/Create a knowledge base/)).toBeInTheDocument());
    expect(calls.some((c) => c.key === "DELETE /api/kbs/1")).toBe(true);
  });
});

describe("questions and citations", () => {
  it("shows the answer with clickable citations that open the passage", async () => {
    routes["POST /api/kbs/1/query"] = [200, answer()];
    render(<App />);
    const user = await ask("How did revenue change?");
    expect(await screen.findByText(/Revenue grew 8%/)).toBeInTheDocument();
    expect(calls).toContainEqual({
      key: "POST /api/kbs/1/query",
      body: { question: "How did revenue change?", provider: "ollama" },
    });
    expect(screen.getAllByRole("button", { name: /Source 1: report.pdf, p. 4/ })).toHaveLength(2);

    await user.click(screen.getAllByRole("button", { name: /Source 1/ })[0]);
    const passage = screen.getByRole("figure", { name: "Cited passage" });
    expect(passage).toHaveTextContent("Revenue grew 8% in 2024, driven by services.");
    expect(passage).toHaveTextContent("report.pdf, p. 4");
    expect(passage).toHaveTextContent("Results");

    await user.click(screen.getByRole("button", { name: "2. report.pdf, p. 5" }));
    expect(screen.getByRole("figure", { name: "Cited passage" })).toHaveTextContent("neighboring passage");
  });

  it("shows insufficient evidence as its own state", async () => {
    routes["POST /api/kbs/1/query"] = [
      200,
      answer({ status: "insufficient", answer: "The documents don't say.", citations: [] }),
    ];
    render(<App />);
    await ask("What is the CEO's favourite colour?");
    const box = await screen.findByRole("status");
    expect(box).toHaveTextContent("Not enough evidence");
    expect(box).toHaveTextContent("The documents don't say.");
  });

  it("shows the API's error message as-is", async () => {
    routes["POST /api/kbs/1/query"] = [503, { detail: "Ollama is not reachable at http://localhost:11434." }];
    render(<App />);
    await ask("Anything?");
    expect(await screen.findByText("Ollama is not reachable at http://localhost:11434.")).toBeInTheDocument();
  });

  it("offers only cloud providers with keys, disabled until the knowledge base opts in", async () => {
    routes["GET /api/keys"] = [200, { ...KEYS_NONE, gemini: "keychain" }];
    routes["PATCH /api/kbs/1"] = [200, { ...KB, allow_cloud: true }];
    routes["POST /api/kbs/1/query"] = [200, answer({ provider: "gemini" })];
    render(<App />);
    const picker = await screen.findByLabelText("Answer model");
    const gemini = await within(picker).findByRole("option", { name: "Gemini" });
    expect(within(picker).queryByRole("option", { name: "OpenAI" })).toBeNull();
    expect(gemini).toBeDisabled();
    expect(screen.getByText(/Cloud models are off for this knowledge base/)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Allow cloud models"));
    await waitFor(() => expect(gemini).toBeEnabled());
    await user.selectOptions(picker, "gemini");
    await ask("Revenue?");
    expect(await screen.findByText("Answered by Gemini")).toBeInTheDocument();
    expect(calls).toContainEqual({ key: "POST /api/kbs/1/query", body: { question: "Revenue?", provider: "gemini" } });
  });

  it("remembers the last chosen provider and falls back to the first usable one", async () => {
    localStorage.setItem("lastProvider", "gemini");
    routes["GET /api/keys"] = [200, { ...KEYS_NONE, gemini: "env", openai: "keychain" }];
    routes["PATCH /api/kbs/1"] = [200, { ...KB, allow_cloud: true }];
    const { unmount } = render(<App />);
    const picker = (await screen.findByLabelText("Answer model")) as HTMLSelectElement;
    await within(picker).findByRole("option", { name: "Gemini" });
    expect(picker.value).toBe("ollama"); // cloud not allowed for this knowledge base

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Allow cloud models"));
    await waitFor(() => expect(picker.value).toBe("gemini"));
    await user.selectOptions(picker, "openai");
    expect(localStorage.getItem("lastProvider")).toBe("openai");
    expect(Object.keys(localStorage)).toEqual(["lastProvider"]); // a name, nothing else
    unmount();

    // Next visit: OpenAI remembered but its key is gone, so the first usable one (Ollama).
    routes["GET /api/kbs"] = [200, [{ ...KB, allow_cloud: true }]];
    routes["GET /api/keys"] = [200, { ...KEYS_NONE, gemini: "env" }];
    render(<App />);
    const next = (await screen.findByLabelText("Answer model")) as HTMLSelectElement;
    await within(next).findByRole("option", { name: "Gemini" });
    expect(next.value).toBe("ollama");
    expect(localStorage.getItem("lastProvider")).toBe("openai"); // kept for when it's usable again
  });

  it("ignores a junk remembered provider", async () => {
    localStorage.setItem("lastProvider", "<script>");
    render(<App />);
    const picker = (await screen.findByLabelText("Answer model")) as HTMLSelectElement;
    await waitFor(() => expect(calls.some((c) => c.key === "GET /api/keys")).toBe(true));
    expect(picker.value).toBe("ollama");
  });
});

describe("follow-up questions", () => {
  const FIRST = "Can you give me a solution to question 1, the Vega Ltd question?";

  it("links a follow-up to the previous turn, shows what was searched, and New topic unlinks", async () => {
    let next = 11;
    routes["POST /api/kbs/1/query"] = (body) => {
      const { question, previous_trace_id } = body as { question: string; previous_trace_id?: number };
      const searched = previous_trace_id ? `${FIRST} — ${question}` : question;
      return [200, answer({ trace_id: next++, searched_question: searched })];
    };
    render(<App />);
    await ask(FIRST);
    expect(await screen.findAllByText("Answered by Ollama (local)")).toHaveLength(1);
    expect(screen.queryByText(/^Searched:/)).toBeNull(); // same as typed: not shown

    await ask("what is the answer");
    expect(await screen.findByText(`Searched: ${FIRST} — what is the answer`)).toBeInTheDocument();
    const queries = () => calls.filter((c) => c.key === "POST /api/kbs/1/query").map((c) => c.body);
    expect(queries()[1]).toEqual({ question: "what is the answer", provider: "ollama", previous_trace_id: 11 });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "New topic" }));
    expect(screen.getByText("The next question starts a new topic.")).toBeInTheDocument();
    await ask("explain it simply");
    await waitFor(() => expect(queries()).toHaveLength(3));
    expect(queries()[2]).toEqual({ question: "explain it simply", provider: "ollama" }); // unlinked
  });

  it("links past a failed turn to the last successful one, but not past New topic", async () => {
    let n = 0;
    routes["POST /api/kbs/1/query"] = () => {
      n += 1;
      if (n === 2 || n === 4) return [503, { detail: "Gemini returned HTTP 503 (UNAVAILABLE) after one retry." }];
      return [200, answer({ trace_id: 30 + n })];
    };
    const queries = () => calls.filter((c) => c.key === "POST /api/kbs/1/query").map((c) => c.body);
    render(<App />);
    await ask(FIRST); // ok, trace 31
    await screen.findByText("Answered by Ollama (local)");
    await ask("what is the answer"); // fails
    await screen.findByText(/HTTP 503/);
    await ask("what is the answer"); // retried by the user: linked to 31, not to the failure
    await waitFor(() => expect(queries()).toHaveLength(3));
    expect(queries()[2]).toEqual({ question: "what is the answer", provider: "ollama", previous_trace_id: 31 });

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "New topic" }));
    await ask("What is prudence?"); // new topic, and it fails
    await waitFor(() => expect(queries()).toHaveLength(4));
    expect(queries()[3]).toEqual({ question: "What is prudence?", provider: "ollama" });
    await ask("explain it simply"); // must not reach back past the New topic boundary
    await waitFor(() => expect(queries()).toHaveLength(5));
    expect(queries()[4]).toEqual({ question: "explain it simply", provider: "ollama" });
  });

  it("never sends another knowledge base's turn", async () => {
    const OTHER = { ...KB, id: 2, name: "Research Papers" };
    routes["GET /api/kbs"] = [200, [KB, OTHER]];
    routes["POST /api/kbs/1/query"] = [200, answer({ trace_id: 21 })];
    routes["POST /api/kbs/2/query"] = [200, answer({ trace_id: 22 })];
    render(<App />);
    await ask(FIRST);
    await screen.findByText("Answered by Ollama (local)");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Research Papers" }));
    await ask("what is the answer");
    await waitFor(() => expect(calls.some((c) => c.key === "POST /api/kbs/2/query")).toBe(true));
    expect(calls.find((c) => c.key === "POST /api/kbs/2/query")?.body).toEqual({
      question: "what is the answer",
      provider: "ollama",
    });
  });
});

describe("general explanation", () => {
  const LABEL = "Explanation (general knowledge, not from your documents)";
  const STRONG = "Explanation (general knowledge, not from your documents — may differ from ICAI's answer, verify before relying on it)";

  it("is off by default, remembered when turned on, and shown apart from the cited answer", async () => {
    routes["POST /api/kbs/1/query"] = (body) => {
      const { explain } = body as { explain?: boolean };
      return [200, answer(explain ? { explanation: "Gains are investing, not operating.", explanation_label: LABEL } : {})];
    };
    const queries = () => calls.filter((c) => c.key === "POST /api/kbs/1/query").map((c) => c.body);
    const { unmount } = render(<App />);
    const toggle = (await screen.findByLabelText(/Add a general explanation/)) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    await ask("Revenue?");
    await waitFor(() => expect(queries()).toHaveLength(1));
    expect(queries()[0]).toEqual({ question: "Revenue?", provider: "ollama" }); // no explain
    expect(screen.queryByRole("region", { name: "General explanation" })).toBeNull();

    const user = userEvent.setup();
    await user.click(toggle);
    expect(localStorage.getItem("explain")).toBe("on");
    await ask("Why?");
    const box = await screen.findByRole("region", { name: "General explanation" });
    expect(within(box).getByText(LABEL)).toBeInTheDocument();
    expect(within(box).getByText("Gains are investing, not operating.")).toBeInTheDocument();
    expect(within(box).queryAllByRole("button")).toHaveLength(0); // no citation chips inside
    expect(queries()[1]).toMatchObject({ question: "Why?", explain: true });
    unmount();

    render(<App />); // remembered in this browser
    expect(((await screen.findByLabelText(/Add a general explanation/)) as HTMLInputElement).checked).toBe(true);
  });

  it("shows the stronger label on a not-enough-evidence answer, and an explanation error quietly", async () => {
    localStorage.setItem("explain", "on");
    let n = 0;
    routes["POST /api/kbs/1/query"] = () => {
      n += 1;
      return n === 1
        ? [200, answer({ status: "insufficient", answer: "Not enough.", citations: [], explanation: "In general, ...", explanation_label: STRONG })]
        : [200, answer({ explanation: null, explanation_error: "The general explanation couldn't be generated: HTTP 503." })];
    };
    render(<App />);
    await ask("Which option is right?");
    const box = await screen.findByRole("region", { name: "General explanation" });
    expect(within(box).getByText(STRONG)).toBeInTheDocument();
    expect(screen.getByText("Not enough evidence")).toBeInTheDocument(); // grounded part unchanged
    await ask("And this one?");
    expect(await screen.findByText(/couldn't be generated: HTTP 503/)).toBeInTheDocument();
    expect(screen.getAllByText("Revenue grew 8%", { exact: false }).length).toBeGreaterThan(0); // answer still shown
  });
});

describe("linkableTraceId", () => {
  const ok = (trace_id: number) => ({ question: "q", answer: answer({ trace_id }) });
  it("skips failed turns and stops at a New topic boundary", () => {
    expect(linkableTraceId([])).toBeUndefined();
    expect(linkableTraceId([ok(1), { question: "q", error: "503" }])).toBe(1);
    expect(linkableTraceId([ok(1), { question: "q", error: "503", newTopic: true }])).toBeUndefined();
    expect(linkableTraceId([ok(1), { ...ok(2), newTopic: true }, { question: "q", error: "x" }])).toBe(2);
  });
});

describe("API keys", () => {
  it("sends the key once, clears the field, and keeps it nowhere in the page", async () => {
    const SECRET = "sk-test-CANARY-1234567890";
    let sources = { ...KEYS_NONE, anthropic: "env" };
    routes["GET /api/keys"] = () => [200, sources];
    routes["PUT /api/keys/openai"] = () => {
      sources = { ...sources, openai: "keychain" };
      return [204, null];
    };
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "API keys" }));
    expect(await screen.findByTestId("source-anthropic")).toHaveTextContent("Set in .env");
    const field = screen.getByLabelText("OpenAI API key");
    expect(field).toHaveAttribute("type", "password");
    await user.type(field, SECRET);
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => expect(screen.getByTestId("source-openai")).toHaveTextContent("Saved in the system keychain"));
    expect(calls).toContainEqual({ key: "PUT /api/keys/openai", body: { key: SECRET } });
    expect(field).toHaveValue("");
    expect(document.documentElement.outerHTML).not.toContain(SECRET);
    const stored = [JSON.stringify({ ...localStorage }), JSON.stringify({ ...sessionStorage }), document.cookie];
    stored.forEach((text) => expect(text).not.toContain(SECRET));
    // Only the PUT carried it.
    expect(calls.filter((c) => JSON.stringify(c).includes(SECRET))).toHaveLength(1);
  });

  it("removes a keychain key", async () => {
    let sources = { ...KEYS_NONE, gemini: "keychain" };
    routes["GET /api/keys"] = () => [200, sources];
    routes["DELETE /api/keys/gemini"] = () => {
      sources = { ...KEYS_NONE };
      return [204, null];
    };
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "API keys" }));
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    await waitFor(() => expect(screen.getByTestId("source-gemini")).toHaveTextContent("Not set"));
  });
});

describe("evaluation", () => {
  it("shows each comparison's verdict in plain words next to the numbers", async () => {
    routes["GET /api/evaluation"] = [
      200,
      {
        dataset: "Held-out test set",
        baseline: {
          name: "A", answerable: 24, unanswerable: 6, recall_at_budget: [0.86, 0.708, 0.985],
          hit_at_5: [0.875, 0.75, 1], reciprocal_rank: [0.716, 0.572, 0.85], unanswerable_refused: 6, generation_p50_s: 32.1,
        },
        comparisons: [
          {
            name: "S adaptive retrieval vs A", metric: "Recall", n: 24, difference: -0.01852, ci_low: -0.14352,
            ci_high: 0.10648, verdict: "inconclusive: not shown to be better than baseline", note: "",
          },
        ],
        sources: ["benchmarks/results/x.json"],
      },
    ];
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Evaluation" }));
    expect(await screen.findByText("inconclusive: not shown to be better than baseline")).toBeInTheDocument();
    expect(screen.getByText(/difference -0.019 \(95% CI -0.144 to \+0.106\), 24 questions/)).toBeInTheDocument();
    expect(screen.getByText("0.860 (95% CI 0.708–0.985)")).toBeInTheDocument();
  });
});

describe("uploads", () => {
  class FakeXHR {
    static instances: FakeXHR[] = [];
    upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
    onload?: () => void;
    onerror?: () => void;
    status = 0;
    responseText = "";
    url = "";
    open(_method: string, url: string) {
      this.url = url;
    }
    send() {
      FakeXHR.instances.push(this);
    }
    respond(status: number, body: unknown) {
      this.status = status;
      this.responseText = JSON.stringify(body);
      this.onload?.();
    }
  }

  beforeEach(() => {
    FakeXHR.instances = [];
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    routes["GET /api/kbs/1/documents"] = [200, []];
  });

  async function chooseFile(name: string) {
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Documents" }));
    await user.upload(screen.getByTestId("file-input"), new File(["x"], name, { type: "application/pdf" }));
    await waitFor(() => expect(FakeXHR.instances).toHaveLength(1));
    return FakeXHR.instances[0];
  }

  it("shows upload progress, then polls the job until indexed", async () => {
    const doc = { id: 7, filename: "a.pdf", format: "pdf", status: "ready", error: null, warnings: [], version: 1 };
    routes["GET /api/jobs/9"] = [200, { id: 9, status: "succeeded", error: null }];
    const xhr = await chooseFile("a.pdf");
    expect(xhr.url).toBe("/api/kbs/1/documents");
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
    expect(await screen.findByText("50%")).toBeInTheDocument();
    routes["GET /api/kbs/1/documents"] = [200, [doc]];
    xhr.respond(202, { document: { ...doc, status: "pending" }, job_id: 9, duplicate: false });
    expect(await screen.findByText("Indexed.")).toBeInTheDocument();
    expect(await screen.findByText("ready")).toBeInTheDocument();
  });

  it("shows the API's rejection message as-is", async () => {
    const xhr = await chooseFile("scan.pdf");
    xhr.respond(400, { detail: "This PDF has no text layer. It looks scanned and needs OCR." });
    expect(await screen.findByText("This PDF has no text layer. It looks scanned and needs OCR.")).toBeInTheDocument();
  });
});
