"use client";

import { useMemo, useState } from "react";

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function copyToClipboard(text: string) {
  await navigator.clipboard.writeText(text);
}

function downloadBlob(filename: string, blob: Blob) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

const DEFAULT_CUSTOM_TEMPLATE = `Rewrite the resume to match the JD. Preserve employers/dates/education. No new metrics. No JD copy-paste.
If needs, you can edit job titles slightly to better match the JD.
Output ONLY the resume text.`;

export default function Home() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

  const [provider, setProvider] = useState<"ollama" | "deepseek">("ollama");

  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [tolerance, setTolerance] = useState(40);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tailored, setTailored] = useState("");

  const [jobUrl, setJobUrl] = useState("");
  const [fetchingJd, setFetchingJd] = useState(false);

  const [jobLinksText, setJobLinksText] = useState("");
  const [batchLoading, setBatchLoading] = useState(false);

  const [promptMode, setPromptMode] = useState<"default" | "custom">("default");
  const [customPrompt, setCustomPrompt] = useState<string>(DEFAULT_CUSTOM_TEMPLATE);


  const mode = useMemo(() => {
    if (tolerance === 100) return "Evil";
    if (tolerance < 30) return "Conservative";
    if (tolerance < 70) return "Balanced";
    return "Creative";
  }, [tolerance]);

  const canRun = resumeText.trim().length >= 80 && jdText.trim().length >= 80 && !loading;

  async function onGenerate() {
    setLoading(true);
    setError(null);
    setTailored("");

    try {
      const r = await fetch(`${apiBase}/tailor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          jd_text: jdText,
          tolerance,
          provider,
          plan: null,
        }),
      });

      const data = await r.json();
      if (!r.ok) throw new Error(data?.detail || data?.error || "Request failed");

      setTailored(data?.tailored_resume || "");
    } catch (e: any) {
      setError(e?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function onCopy() {
    if (!tailored) return;
    await copyToClipboard(tailored);
  }

  function onDownload() {
    if (!tailored) return;
    downloadText("tailored_resume.txt", tailored);
  }

  async function onFetchJd() {
    if (!jobUrl.trim()) return;
    setFetchingJd(true);
    setError(null);

    try {
      const r = await fetch(`${apiBase}/extract_jd`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: jobUrl.trim() }),
      });

      const data = await r.json();
      if (!r.ok) throw new Error(data?.detail || "Failed to extract JD");

      setJdText(data.jd_text || "");
    } catch (e: any) {
      setError(e?.message || "Unknown error");
    } finally {
      setFetchingJd(false);
    }
  }

  async function onDownloadPdf() {
    if (!tailored) return;

    const r = await fetch(`${apiBase}/resume_pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_text: tailored, filename: "tailored_resume.pdf" }),
    });

    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data?.detail || "PDF generation failed");
    }

    const blob = await r.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "tailored_resume.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  }
  async function onGenerateBatchZip() {
    setError(null);

    const links = jobLinksText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

    if (links.length === 0) {
      setError("Paste at least 1 job link.");
      return;
    }
    if (links.length > 10) {
      setError("Max 10 links for MVP. Please paste 10 or fewer.");
      return;
    }
    if (resumeText.trim().length < 80) {
      setError("Paste your base resume first.");
      return;
    }

    setBatchLoading(true);
    try {
      const r = await fetch(`${apiBase}/batch_zip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_resume_text: resumeText,
          job_urls: links,
          tolerance,
          provider,
          format: "pdf+txt",
        }),
      });

      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(data?.detail || "Batch generation failed");
      }

      const blob = await r.blob();
      downloadBlob("tailored_resumes.zip", blob);
    } catch (e: any) {
      setError(e?.message || "Unknown error");
    } finally {
      setBatchLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-10">
        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              AI Resume Tailor <span className="text-slate-500">(MVP)</span>
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              Paste your base resume + job description → generate a truthful tailored resume (FastAPI + Ollama).
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="flex flex-wrap items-center gap-3">
              <div className="text-sm font-semibold text-slate-900">Tolerance</div>
              <input
                id="tolerance"
                type="range"
                disabled={promptMode==="custom"}
                min={0}
                max={100}
                value={tolerance}
                onChange={(e) => setTolerance(parseInt(e.target.value, 10))}
                className="w-72"
              />
              <div className="text-sm font-bold text-slate-900">{tolerance}</div>
              <div className="text-sm text-slate-600">({mode})</div>
            </div>
            <div className="flex-1" />
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value as any)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="ollama">Local (Ollama)</option>
              <option value="deepseek">DeepSeek (Online)</option>
            </select>
            <button
              onClick={onGenerate}
              disabled={!canRun}
              className={[
                "inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-semibold",
                "border border-slate-300 bg-slate-900 text-white shadow-sm",
                "hover:bg-slate-800 active:bg-slate-900",
                "disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-700 disabled:border-slate-300",
              ].join(" ")}
            >
              {loading ? "Generating..." : "Generate Tailored Resume"}
            </button>
          </div>
          <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-bold text-slate-900">Prompt</h2>
                <p className="mt-1 text-xs text-slate-500">Use default prompts or customize them.</p>
              </div>

              <select
                value={promptMode}
                onChange={(e) => setPromptMode(e.target.value as any)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                <option value="default">Default</option>
                <option value="custom">Custom</option>
              </select>
            </div>

            {promptMode === "custom" && (
              <div className="mt-4">
                <textarea
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  className="mt-2 h-56 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-900 outline-none focus:ring-2 focus:ring-slate-400"
                />
              </div>
            )}
          </div>

          {/* Inputs */}
          <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">Base Resume</h2>
                <span className="text-xs text-slate-500">{resumeText.trim().length} chars</span>
              </div>
              <textarea
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                placeholder="Paste your base resume text here..."
                className="mt-3 h-80 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-900 outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-slate-900">Job Description</h2>
                <span className="text-xs text-slate-500">{jdText.trim().length} chars</span>
              </div>
              <div className="mb-3 flex gap-2">
                <input
                  value={jobUrl}
                  onChange={(e) => setJobUrl(e.target.value)}
                  placeholder="Paste job link (optional)"
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-slate-400"
                />
                <button
                  onClick={onFetchJd}
                  disabled={!jobUrl.trim() || fetchingJd}
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {fetchingJd ? "Fetching..." : "Fetch JD"}
                </button>
              </div>
              <textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste job description text here..."
                className="mt-3 h-80 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-900 outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <div className="font-semibold">Error</div>
              <div className="mt-1">{error}</div>
            </div>
          )}
        </div>

        {/* Output */}
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Tailored Resume</h2>
              <p className="mt-1 text-xs text-slate-500">
                Tip: Keep it truthful. No invented tools, numbers, or new employers.
              </p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={onCopy}
                disabled={!tailored}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Copy
              </button>
              <button
                onClick={onDownload}
                disabled={!tailored}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Download .txt
              </button>
              <button
                onClick={() => onDownloadPdf().catch(e => setError(e.message))}
                disabled={!tailored}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Download PDF
              </button>
            </div>
          </div>
          {/* Batch Generate */}
          <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-sm font-bold text-slate-900">Batch Generate (ZIP)</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Paste up to 10 job links (one per line). Downloads a ZIP with PDF + TXT for each.
                </p>
              </div>

              <button
                onClick={onGenerateBatchZip}
                disabled={batchLoading || resumeText.trim().length < 80}
                className="rounded-xl border border-slate-300 bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-700"
              >
                {batchLoading ? "Generating ZIP..." : "Generate ZIP (PDF+TXT)"}
              </button>
            </div>

            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-slate-900">Job Links</div>
                <div className="text-xs text-slate-500">
                  {jobLinksText.split("\n").map(s => s.trim()).filter(Boolean).length}/10
                </div>
              </div>

              <textarea
                value={jobLinksText}
                onChange={(e) => setJobLinksText(e.target.value)}
                placeholder={`https://company.com/jobs/123\nhttps://boards.greenhouse.io/...`}
                className="mt-3 h-40 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-900 outline-none focus:ring-2 focus:ring-slate-400"
              />

              <div className="mt-2 text-xs text-slate-500">
                Output files will include <span className="font-mono">errors.txt</span> for any links that failed to fetch/parse.
              </div>
            </div>
          </div>

          <pre className="mt-4 max-h-130 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-900">
            {tailored || "No output yet. Paste resume + JD and click Generate."}
          </pre>
        </div>
      </div>
    </main>
  );
}
