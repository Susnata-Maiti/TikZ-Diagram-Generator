import { useState, useCallback, useRef } from "react";
import { v4 as uuidv4 } from "uuid";
import {
  generateDiagram,
  refineDiagram,
  undoDiagram,
  redoDiagram,
  researchTopic,
} from "../lib/api";

/**
 * Central state hook for the diagram generator.
 * Manages: current diagram, history, refinement chat, and status.
 */
export function useDiagramState() {
  const [sessionId] = useState(() => uuidv4());
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState(null);

  // Diagram state
  const [diagramId, setDiagramId] = useState(null);
  const [ir, setIr] = useState(null);
  const [tikzCode, setTikzCode] = useState("");
  const [pdfB64, setPdfB64] = useState(null);
  const [pngB64, setPngB64] = useState(null);
  const [validation, setValidation] = useState(null);
  const [research, setResearch] = useState(null);
  const [compilationLog, setCompilationLog] = useState(null);

  // Chat history
  const [chatMessages, setChatMessages] = useState([]);

  const _applyResult = useCallback((data) => {
    setDiagramId(data.diagram_id || null);
    setIr(data.ir || null);
    setTikzCode(data.tikz_code || "");
    setPdfB64(data.pdf_base64 || null);
    setPngB64(data.png_base64 || null);
    setValidation(data.validation || null);
    setResearch(data.research || null);
    setCompilationLog(data.compilation_log || null);
    if (data.compilation_success === false) {
      setError(data.status || "Compilation failed.");
      setStatus("Compilation failed");
    } else {
      setStatus(data.status || "Done");
    }
  }, []);

  const generate = useCallback(
    async (prompt, options = {}) => {
      setLoading(true);
      setError(null);
      setChatMessages((prev) => [...prev, { role: "user", text: prompt }]);
      try {
        const data = await generateDiagram({
          prompt,
          enableResearch: options.enableResearch ?? false,
          sketchB64: options.sketchB64 ?? null,
        });
        _applyResult(data);
        setChatMessages((prev) => [
          ...prev,
          { role: "assistant", text: data.agent_summary || "Diagram generated." },
        ]);
      } catch (e) {
        setError(e.message);
        setStatus("Error");
        setChatMessages((prev) => [
          ...prev,
          { role: "assistant", text: `Error: ${e.message}` },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [_applyResult]
  );

  const refine = useCallback(
    async (instruction) => {
      if (!ir) {
        return generate(instruction);
      }
      setLoading(true);
      setError(null);
      setChatMessages((prev) => [...prev, { role: "user", text: instruction }]);
      try {
        const data = await refineDiagram({
          prompt: instruction,
          currentIr: ir,
          currentTikz: tikzCode,
          sessionId,
        });
        _applyResult(data);
        setChatMessages((prev) => [
          ...prev,
          { role: "assistant", text: data.agent_summary || "Diagram refined." },
        ]);
      } catch (e) {
        setError(e.message);
        setStatus("Error");
        setChatMessages((prev) => [
          ...prev,
          { role: "assistant", text: `Error: ${e.message}` },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [ir, tikzCode, sessionId, generate, _applyResult]
  );

  const undo = useCallback(async () => {
    if (!ir || !sessionId) return;
    setLoading(true);
    try {
      const data = await undoDiagram({ sessionId, currentIr: ir, currentTikz: tikzCode });
      _applyResult(data);
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: "↩ Reverted to previous state." },
      ]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [ir, tikzCode, sessionId, _applyResult]);

  const redo = useCallback(async () => {
    if (!ir || !sessionId) return;
    setLoading(true);
    try {
      const data = await redoDiagram({ sessionId, currentIr: ir, currentTikz: tikzCode });
      _applyResult(data);
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: "↪ Redone." },
      ]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [ir, tikzCode, sessionId, _applyResult]);

  const reset = useCallback(() => {
    setDiagramId(null);
    setIr(null);
    setTikzCode("");
    setPdfB64(null);
    setPngB64(null);
    setValidation(null);
    setResearch(null);
    setCompilationLog(null);
    setStatus("Ready");
    setError(null);
    setChatMessages([]);
  }, []);

  return {
    sessionId,
    loading,
    status,
    error,
    diagramId,
    ir,
    tikzCode,
    setTikzCode,
    pdfB64,
    pngB64,
    validation,
    research,
    compilationLog,
    chatMessages,
    generate,
    refine,
    undo,
    redo,
    reset,
  };
}
