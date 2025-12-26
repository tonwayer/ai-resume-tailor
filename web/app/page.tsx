"use client";

import { useMemo, useState } from "react";

export default function Home() {
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [tolerance, setTolerance] = useState(40);

  const [loading, setLoading] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [tailored, setTailored] = useState<string>("");

  const [error, setError] = useState<string | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE;

  const mode = useMemo(() => {
    if (tolerance < 30) return "Conservative";
    if (tolerance < 70) return "Balanced";
    return "Creative";
  }, [tolerance]);

  async function post(path: string, body: any) {
    const r = await fetch(`${apiBase}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data?.detail || data?.error || "Request failed");
    return data;
  }

  async function onGeneratePlan() {
    setLoading(true);
    setError(null);
    try {
      const data = await post("/plan", { resume_text: resumeText, jd_text: jdText, tolerance });
      setPlan(data);
    } catch (e: any) {
      setError(e.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function onGenerateTailored() {
    setLoading(true);
    setError(null);
    try {
      const data = await post("/tailor", {
        resume_text: resumeText,
        jd_text: jdText,
        tolerance,
        plan, // pass plan if we already made it
      });
      setTailored(data.tailored_resume || "");
    } catch (e: any) {
      setError(e.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>AI Resume Tailor — MVP</h1>
      <p style={{ marginTop: 8, opacity: 0.8 }}>
        Day 2: Plan → Tailor (Next.js + FastAPI + Ollama llama3.1:8b).
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 20 }}>
        <div>
          <h3 style={{ fontWeight: 700 }}>Base Resume (paste text)</h3>
          <textarea
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            placeholder="Paste your resume text here..."
            style={{ width: "100%", height: 260, marginTop: 8, padding: 10 }}
          />
        </div>

        <div>
          <h3 style={{ fontWeight: 700 }}>Job Description (paste text)</h3>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Paste job description here..."
            style={{ width: "100%", height: 260, marginTop: 8, padding: 10 }}
          />
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <strong>Tolerance:</strong>
          <input
            type="range"
            min={0}
            max={100}
            value={tolerance}
            onChange={(e) => setTolerance(parseInt(e.target.value, 10))}
            style={{ width: 320 }}
          />
          <span>
            {tolerance} — {mode}
          </span>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          <button
            onClick={onGeneratePlan}
            disabled={loading || resumeText.length < 50 || jdText.length < 50}
            style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #ccc", cursor: "pointer" }}
          >
            {loading ? "Working..." : "Generate Plan"}
          </button>

          <button
            onClick={onGenerateTailored}
            disabled={loading || resumeText.length < 50 || jdText.length < 50}
            style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #ccc", cursor: "pointer" }}
          >
            {loading ? "Working..." : "Generate Tailored Resume"}
          </button>
        </div>

        {error && <p style={{ marginTop: 10, color: "crimson" }}>Error: {error}</p>}
      </div>

      <div style={{ display: "flex" }}>
        <div style={{ width: "50%" }}>
          <h3 style={{ fontWeight: 700 }}>Plan JSON</h3>
          <pre style={{ marginTop: 8, padding: 12, background: "#f6f6f6", borderRadius: 8, maxHeight: 420, overflow: "auto" }}>
            {plan ? JSON.stringify(plan, null, 2) : "No plan yet."}
          </pre>
        </div>

        <div style={{ width: "50%" }}>
          <h3 style={{ fontWeight: 700 }}>Tailored Resume</h3>
          <pre style={{ marginTop: 8, padding: 12, background: "#f6f6f6", borderRadius: 8, maxHeight: 420, overflow: "auto", whiteSpace: "pre-wrap" }}>
            {tailored || "No tailored resume yet."}
          </pre>
        </div>
      </div>
    </main>
  );
}
