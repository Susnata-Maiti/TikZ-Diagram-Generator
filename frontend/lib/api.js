/**
 * API client for the TikZ Diagram Generator backend.
 * Reads NEXT_PUBLIC_BACKEND_URL and NEXT_PUBLIC_ACCESS_TOKEN from the environment.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const ACCESS_TOKEN = process.env.NEXT_PUBLIC_ACCESS_TOKEN || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (ACCESS_TOKEN) h["x-access-token"] = ACCESS_TOKEN;
  return h;
}

async function _post(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

async function _get(path) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "GET",
    headers: headers(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function generateDiagram({ prompt, enableResearch = false, sketchB64 = null }) {
  return _post("/api/diagram/generate", {
    prompt,
    enable_research: enableResearch,
    sketch_b64: sketchB64,
  });
}

export async function refineDiagram({ prompt, currentIr, currentTikz = "", sessionId = "" }) {
  return _post("/api/diagram/refine", {
    prompt,
    current_ir: currentIr,
    current_tikz: currentTikz,
    session_id: sessionId,
  });
}

export async function validateDiagram({ tikzCode, ir = null }) {
  return _post("/api/diagram/validate", { tikz_code: tikzCode, ir });
}

export async function interpretSketch({ sketchB64, notes = "" }) {
  return _post("/api/diagram/sketch", { sketch_b64: sketchB64, notes });
}

export async function researchTopic(topic) {
  return _post("/api/research", { topic });
}

export async function undoDiagram({ sessionId, currentIr, currentTikz = "" }) {
  return _post("/api/diagram/undo", {
    session_id: sessionId,
    current_ir: currentIr,
    current_tikz: currentTikz,
  });
}

export async function redoDiagram({ sessionId, currentIr, currentTikz = "" }) {
  return _post("/api/diagram/redo", {
    session_id: sessionId,
    current_ir: currentIr,
    current_tikz: currentTikz,
  });
}

export async function getDiagram(diagramId) {
  return _get(`/api/diagram/${diagramId}`);
}

export function downloadUrl(diagramId, fmt = "pdf") {
  return `${BASE_URL}/api/diagram/${diagramId}/download?fmt=${fmt}`;
}

export async function healthCheck() {
  return _get("/api/health");
}
