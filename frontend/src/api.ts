const API_BASE = "http://localhost:8000";

export async function getHealth() {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 3000);

  try {
    const res = await fetch(`${API_BASE}/health`, {
      signal: controller.signal,
      mode: "cors",
    });

    if (!res.ok) throw new Error("Backend is not responding");
    return res.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function getSample() {
  const res = await fetch(`${API_BASE}/sample`, { mode: "cors" });
  if (!res.ok) throw new Error("Could not load sample request");
  return res.json();
}

export async function generateAkiflowCommand(payload: unknown) {
  const res = await fetch(`${API_BASE}/commands/akiflow-ai`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    mode: "cors",
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data;
}