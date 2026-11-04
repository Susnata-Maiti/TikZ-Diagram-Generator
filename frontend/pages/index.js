import { useState, useRef, useCallback } from "react";
import { useDiagramState } from "../hooks/useDiagramState";
import { downloadUrl } from "../lib/api";

const DIAGRAM_TYPES = [
  "auto-detect", "uml_class", "uml_use_case", "uml_sequence", "uml_activity",
  "uml_state", "flowchart", "dfd", "bpmn", "erd", "architecture",
  "electrical", "digital_logic", "quantum_circuit", "neural_network",
  "ml_pipeline", "resource_allocation", "generic",
];

const NOTATION_PROFILES = [
  "default", "uml_2x", "bpmn_2_0", "chen_erd", "crows_foot",
  "yourdon_dfd", "gane_sarson", "ieee_circuit", "quantum_std",
];

const EXAMPLE_PROMPTS = [
  "UML class diagram for a Library system with Book, Member, and Loan classes showing inheritance and associations",
  "Flowchart for a login process with username/password input, validation decision, error path, and success path",
  "Quantum circuit with Hadamard gate on q0, CNOT between q0 and q1, and measurement on both qubits",
  "ERD for an e-commerce database with Customer, Order, Product, and OrderItem entities using Crow's Foot notation",
  "Bistable multivibrator circuit with two NPN transistors, coupling resistors, and collector resistors",
  "Resource allocation graph showing two processes P1, P2 competing for resources R1, R2 with a deadlock cycle",
  "Microservices architecture with API Gateway, Auth Service, User Service, Order Service, and PostgreSQL databases",
  "Data Flow Diagram Level 1 for an online banking system with Account Management and Transaction Processing",
];

export default function Home() {
  const state = useDiagramState();
  const [prompt, setPrompt] = useState("");
  const [diagramType, setDiagramType] = useState("auto-detect");
  const [notationProfile, setNotationProfile] = useState("default");
  const [enableResearch, setEnableResearch] = useState(false);
  const [sketchFile, setSketchFile] = useState(null);
  const [activeTab, setActiveTab] = useState("preview");
  const [chatInput, setChatInput] = useState("");
  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  const scrollChat = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleGenerate = useCallback(async () => {
    if (!prompt.trim() && !sketchFile) return;
    let sketchB64 = null;
    if (sketchFile) {
      sketchB64 = await fileToBase64(sketchFile);
    }
    let fullPrompt = prompt;
    if (diagramType !== "auto-detect") {
      fullPrompt = `[Diagram type: ${diagramType}] ${prompt}`;
    }
    if (notationProfile !== "default") {
      fullPrompt += ` [Notation: ${notationProfile}]`;
    }
    await state.generate(fullPrompt, { enableResearch, sketchB64 });
    setActiveTab("preview");
    setTimeout(scrollChat, 100);
  }, [prompt, sketchFile, diagramType, notationProfile, enableResearch, state]);

  const handleChat = useCallback(async (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const msg = chatInput;
    setChatInput("");
    await state.refine(msg);
    setActiveTab("preview");
    setTimeout(scrollChat, 100);
  }, [chatInput, state]);

  const handleSketchChange = (e) => {
    setSketchFile(e.target.files?.[0] ?? null);
  };

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <h1 style={styles.title}>🖊 TikZ Diagram Generator</h1>
        <p style={styles.subtitle}>
          AI-powered • IBM Granite • Publication-quality diagrams
        </p>
      </header>

      <div style={styles.layout}>
        {/* ── Left panel ── */}
        <aside style={styles.sidebar}>
          <Section title="Describe your diagram">
            <textarea
              style={styles.textarea}
              rows={6}
              placeholder="e.g. UML class diagram for a banking system with Account, Customer, and Transaction classes..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.ctrlKey && e.key === "Enter") handleGenerate(); }}
            />
            <small style={styles.hint}>Ctrl+Enter to generate</small>
          </Section>

          <Section title="Options">
            <label style={styles.label}>Diagram Type</label>
            <select style={styles.select} value={diagramType} onChange={(e) => setDiagramType(e.target.value)}>
              {DIAGRAM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>

            <label style={styles.label}>Notation Profile</label>
            <select style={styles.select} value={notationProfile} onChange={(e) => setNotationProfile(e.target.value)}>
              {NOTATION_PROFILES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>

            <label style={styles.checkLabel}>
              <input type="checkbox" checked={enableResearch} onChange={(e) => setEnableResearch(e.target.checked)} />
              {" "}Enable research (web search)
            </label>
          </Section>

          <Section title="Upload Sketch (optional)">
            <input
              type="file"
              accept="image/*"
              ref={fileInputRef}
              style={{ display: "none" }}
              onChange={handleSketchChange}
            />
            <button style={styles.btnSecondary} onClick={() => fileInputRef.current?.click()}>
              {sketchFile ? `📎 ${sketchFile.name}` : "Choose image…"}
            </button>
            {sketchFile && (
              <button style={{ ...styles.btnSecondary, marginLeft: 8 }} onClick={() => setSketchFile(null)}>
                ✕ Clear
              </button>
            )}
          </Section>

          <div style={styles.actionRow}>
            <button
              style={state.loading ? styles.btnDisabled : styles.btnPrimary}
              onClick={handleGenerate}
              disabled={state.loading}
            >
              {state.loading ? "⏳ Generating…" : "🚀 Generate"}
            </button>
            <button style={styles.btnSecondary} onClick={state.undo} disabled={state.loading || !state.ir}>↩</button>
            <button style={styles.btnSecondary} onClick={state.redo} disabled={state.loading || !state.ir}>↪</button>
            <button style={styles.btnSecondary} onClick={state.reset}>🔄 Reset</button>
          </div>

          <Section title="Examples">
            {EXAMPLE_PROMPTS.map((ex, i) => (
              <button key={i} style={styles.exampleBtn} onClick={() => setPrompt(ex)}>
                {ex.slice(0, 60)}…
              </button>
            ))}
          </Section>

          <StatusBar status={state.status} error={state.error} loading={state.loading} />
        </aside>

        {/* ── Right panel ── */}
        <main style={styles.main}>
          {/* Tab bar */}
          <div style={styles.tabBar}>
            {["preview", "tikz", "ir", "validation", "research", "chat"].map((tab) => (
              <button
                key={tab}
                style={activeTab === tab ? styles.tabActive : styles.tab}
                onClick={() => setActiveTab(tab)}
              >
                {{ preview: "🖼 Preview", tikz: "📝 TikZ Source", ir: "🕸 IR", validation: "✅ Validation", research: "🔬 Research", chat: "💬 Chat" }[tab]}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={styles.tabContent}>
            {activeTab === "preview" && (
              <PreviewTab
                pngB64={state.pngB64}
                pdfB64={state.pdfB64}
                diagramId={state.diagramId}
                compilationLog={state.compilationLog}
                error={state.error}
              />
            )}
            {activeTab === "tikz" && (
              <TikZTab tikzCode={state.tikzCode} setTikzCode={state.setTikzCode} />
            )}
            {activeTab === "ir" && (
              <pre style={styles.codeBlock}>
                {state.ir ? JSON.stringify(state.ir, null, 2) : "(no IR yet)"}
              </pre>
            )}
            {activeTab === "validation" && (
              <ValidationTab validation={state.validation} />
            )}
            {activeTab === "research" && (
              <ResearchTab research={state.research} />
            )}
            {activeTab === "chat" && (
              <ChatTab
                messages={state.chatMessages}
                chatInput={chatInput}
                setChatInput={setChatInput}
                onSubmit={handleChat}
                loading={state.loading}
                chatEndRef={chatEndRef}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h3 style={styles.sectionTitle}>{title}</h3>
      {children}
    </div>
  );
}

function StatusBar({ status, error, loading }) {
  const color = error ? "#b91c1c" : loading ? "#1d4ed8" : "#166534";
  return (
    <div style={{ ...styles.statusBar, color }}>
      {loading ? "⏳ " : error ? "❌ " : "✅ "}{error || status}
    </div>
  );
}

function PreviewTab({ pngB64, pdfB64, diagramId, compilationLog, error }) {
  if (!pngB64 && !pdfB64) {
    if (compilationLog || error) {
      return (
        <div style={{ padding: 20 }}>
          <p style={{ color: "#b91c1c", fontWeight: 600, marginBottom: 12 }}>
            ❌ Compilation failed — the diagram could not be rendered.
          </p>
          <p style={{ color: "#57606a", fontSize: 13, marginBottom: 8 }}>
            The TikZ source was generated but LaTeX could not compile it. Check
            the <strong>TikZ Source</strong> tab to inspect or edit the code, then try
            regenerating. The compiler log is shown below.
          </p>
          {compilationLog && (
            <pre style={{ ...styles.logBlock }}>
              {compilationLog}
            </pre>
          )}
        </div>
      );
    }
    return <div style={styles.empty}>Generate a diagram to see the preview here.</div>;
  }
  return (
    <div style={styles.previewContainer}>
      {pngB64 && (
        <div style={styles.previewCard}>
          <img
            src={`data:image/png;base64,${pngB64}`}
            alt="Diagram preview"
            style={styles.previewImage}
          />
        </div>
      )}
      {diagramId && (
        <div style={styles.downloadRow}>
          <a href={downloadUrl(diagramId, "pdf")} download style={styles.downloadBtn}>📄 Download PDF</a>
          <a href={downloadUrl(diagramId, "tex")} download style={styles.downloadBtn}>📝 Download TikZ (.tex)</a>
          <a href={downloadUrl(diagramId, "png")} download style={styles.downloadBtn}>🖼 Download PNG</a>
        </div>
      )}
    </div>
  );
}

function TikZTab({ tikzCode, setTikzCode }) {
  return (
    <textarea
      style={{ ...styles.codeBlock, width: "100%", height: "100%", resize: "none", border: "none" }}
      value={tikzCode}
      onChange={(e) => setTikzCode(e.target.value)}
      spellCheck={false}
    />
  );
}

function ValidationTab({ validation }) {
  if (!validation) return <div style={styles.empty}>No validation results yet.</div>;
  return (
    <div style={{ padding: 16 }}>
      <p style={{ fontWeight: 600, color: validation.passed ? "#166534" : "#b91c1c" }}>
        {validation.passed ? "✅ All validation stages passed." : "❌ Validation issues found."}
      </p>
      {validation.errors?.length > 0 && (
        <>
          <h4>Errors</h4>
          <ul>{validation.errors.map((e, i) => <li key={i} style={{ color: "#b91c1c" }}>{e}</li>)}</ul>
        </>
      )}
      {validation.warnings?.length > 0 && (
        <>
          <h4>Warnings</h4>
          <ul>{validation.warnings.map((w, i) => <li key={i} style={{ color: "#92400e" }}>{w}</li>)}</ul>
        </>
      )}
    </div>
  );
}

function ResearchTab({ research }) {
  if (!research) return <div style={styles.empty}>Enable research mode and generate a diagram to see findings here.</div>;
  return (
    <div style={{ padding: 16 }}>
      <p><strong>Summary:</strong> {research.summary}</p>
      {research.components?.length > 0 && (
        <><strong>Key components:</strong><ul>{research.components.map((c, i) => <li key={i}>{c}</li>)}</ul></>
      )}
      {research.sources?.length > 0 && (
        <>
          <strong>Sources:</strong>
          <ul>
            {research.sources.map((s, i) => (
              <li key={i}><a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a></li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ChatTab({ messages, chatInput, setChatInput, onSubmit, loading, chatEndRef }) {
  return (
    <div style={styles.chatPanel}>
      <div style={styles.chatMessages}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            Generate a diagram first, then type a refinement command below.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={m.role === "user" ? styles.chatUser : styles.chatAssistant}>
            <strong>{m.role === "user" ? "You" : "Granite Agent"}</strong>
            <p style={{ margin: "4px 0 0" }}>{m.text}</p>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>
      <form onSubmit={onSubmit} style={styles.chatForm}>
        <input
          style={styles.chatInput}
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          placeholder='e.g. "Add a feedback loop from the output back to the input"'
          disabled={loading}
        />
        <button
          type="submit"
          style={loading ? styles.btnDisabled : styles.btnPrimary}
          disabled={loading}
        >
          Send
        </button>
      </form>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      // Strip data: prefix
      const result = reader.result;
      const b64 = result.split(",")[1] ?? result;
      resolve(b64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}


// ── Styles ────────────────────────────────────────────────────────────────────

const C = {
  bg: "#faf9f5",
  surface: "#f3f0e8",
  surfaceWhite: "#ffffff",
  border: "#e5e0d4",
  text: "#1f2124",
  muted: "#6b665f",
  accent: "#cc5533",       // Warm Claude terracotta
  accentHover: "#b84728",
  accentSoft: "#fdf3ee",
  success: "#166534",
  error: "#b91c1c",
};

const styles = {
  root: { fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif', fontSize: 14, color: C.text, background: C.bg, minHeight: "100vh" },
  header: { background: C.surfaceWhite, borderBottom: `1px solid ${C.border}`, padding: "16px 28px", boxShadow: "0 1px 3px rgba(0,0,0,0.03)" },
  title: { margin: 0, fontSize: 20, fontWeight: 700, color: C.text, letterSpacing: "-0.01em" },
  subtitle: { margin: "4px 0 0", color: C.muted, fontSize: 13 },
  layout: { display: "flex", height: "calc(100vh - 74px)", overflow: "hidden" },
  sidebar: { width: 340, minWidth: 300, borderRight: `1px solid ${C.border}`, padding: 20, overflowY: "auto", background: C.surface },
  main: { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: C.bg },
  sectionTitle: { margin: "0 0 8px", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: C.muted },
  textarea: { width: "100%", boxSizing: "border-box", border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px", fontSize: 13, lineHeight: 1.5, fontFamily: "inherit", resize: "vertical", background: C.surfaceWhite, outline: "none", boxShadow: "inset 0 1px 2px rgba(0,0,0,0.02)" },
  hint: { color: C.muted, fontSize: 11, marginTop: 4, display: "block" },
  label: { display: "block", marginBottom: 4, fontSize: 12, fontWeight: 600, color: C.muted },
  select: { width: "100%", border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 10px", fontSize: 13, marginBottom: 10, background: C.surfaceWhite, color: C.text },
  checkLabel: { display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 10, cursor: "pointer", color: C.text },
  actionRow: { display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" },
  btnPrimary: { background: C.accent, color: "#fff", border: "none", borderRadius: 8, padding: "9px 18px", cursor: "pointer", fontSize: 13, fontWeight: 600, boxShadow: "0 1px 2px rgba(0,0,0,0.1)", transition: "all 0.15s" },
  btnSecondary: { background: C.surfaceWhite, color: C.text, border: `1px solid ${C.border}`, borderRadius: 8, padding: "8px 14px", cursor: "pointer", fontSize: 13, fontWeight: 500 },
  btnDisabled: { background: "#d1cec7", color: "#8a857d", border: "none", borderRadius: 8, padding: "9px 18px", cursor: "not-allowed", fontSize: 13, fontWeight: 600 },
  exampleBtn: { display: "block", width: "100%", textAlign: "left", background: C.surfaceWhite, border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 10px", marginBottom: 5, cursor: "pointer", fontSize: 12, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", transition: "border-color 0.15s" },
  statusBar: { fontSize: 12, marginTop: 14, padding: "9px 12px", borderRadius: 6, background: C.surfaceWhite, border: `1px solid ${C.border}` },
  tabBar: { display: "flex", borderBottom: `1px solid ${C.border}`, background: C.surfaceWhite, flexShrink: 0, paddingLeft: 12 },
  tab: { padding: "12px 18px", border: "none", background: "none", cursor: "pointer", fontSize: 13, color: C.muted, fontWeight: 500, borderBottom: "2px solid transparent", transition: "all 0.15s" },
  tabActive: { padding: "12px 18px", border: "none", background: "none", cursor: "pointer", fontSize: 13, color: C.accent, fontWeight: 700, borderBottom: `2px solid ${C.accent}` },
  tabContent: { flex: 1, overflow: "auto" },
  empty: { color: C.muted, padding: 48, textAlign: "center", fontSize: 14 },
  previewContainer: { padding: 24, maxWidth: "100%", display: "flex", flexDirection: "column", alignItems: "center" },
  previewCard: { background: C.surfaceWhite, border: `1px solid ${C.border}`, borderRadius: 12, padding: 24, boxShadow: "0 4px 24px rgba(0,0,0,0.06)", maxWidth: "100%", margin: "0 auto 16px", overflowX: "auto", textAlign: "center" },
  previewImage: { display: "block", maxWidth: "100%", height: "auto", margin: "0 auto", borderRadius: 4 },
  downloadRow: { display: "flex", gap: 10, justifyContent: "center", margin: "8px 0 24px", flexWrap: "wrap" },
  downloadBtn: { background: C.surfaceWhite, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 14px", fontSize: 12, textDecoration: "none", color: C.text, fontWeight: 500, boxShadow: "0 1px 2px rgba(0,0,0,0.04)" },
  codeBlock: { background: "#1c1b19", color: "#f5f3ed", fontFamily: 'ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Courier New",monospace', fontSize: 12.5, padding: 20, margin: 0, overflowX: "auto", lineHeight: 1.6, height: "100%", boxSizing: "border-box" },
  logBlock: { background: "#fff5f5", border: "1px solid #fca5a5", borderRadius: 8, color: "#7f1d1d", fontFamily: "monospace", fontSize: 11.5, padding: 14, overflowX: "auto", lineHeight: 1.5, whiteSpace: "pre-wrap", maxHeight: 400 },
  chatPanel: { display: "flex", flexDirection: "column", height: "100%", background: C.surfaceWhite },
  chatMessages: { flex: 1, overflow: "auto", padding: 20 },
  chatUser: { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "12px 16px", marginBottom: 12, maxWidth: "80%", alignSelf: "flex-end" },
  chatAssistant: { background: C.accentSoft, border: `1px solid #fed7aa`, borderRadius: 10, padding: "12px 16px", marginBottom: 12, maxWidth: "85%" },
  chatForm: { display: "flex", gap: 10, padding: 16, borderTop: `1px solid ${C.border}`, background: C.surfaceWhite },
  chatInput: { flex: 1, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 14px", fontSize: 13, fontFamily: "inherit", outline: "none" },
};
