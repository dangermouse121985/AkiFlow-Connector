const API_BASE = "http://localhost:8000";

export const AKIFLOW_LOGIN_URL = `${API_BASE}/akiflow/login`;

export type DashboardTask = {
  id?: string | null;
  title: string;
  duration?: number;
  priority?: string;
  project?: string | null;
  tags?: string[];
  task_type?: string;
  [key: string]: unknown;
};

export type ScoredTask = {
  id?: string | null;
  title: string;
  score?: number;
  reasons?: string[];
  [key: string]: unknown;
};

export type AkiflowTask = {
  id: string;
  title: string;
  status?: string;
  priority?: string;
  start?: string;
  deadline?: string;
  duration?: number;
  source: "akiflow";
};

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

function extractScoredTasks(data: unknown): ScoredTask[] {
  if (Array.isArray(data)) return data.filter(isScoredTask);

  if (data && typeof data === "object") {
    const candidate = data as {
      tasks?: unknown;
      scored_tasks?: unknown;
      scores?: unknown;
    };

    const tasks = candidate.tasks ?? candidate.scored_tasks ?? candidate.scores;
    if (Array.isArray(tasks)) return tasks.filter(isScoredTask);
  }

  return [];
}

function isScoredTask(value: unknown): value is ScoredTask {
  if (!value || typeof value !== "object") return false;

  const task = value as { title?: unknown; score?: unknown };
  return (
    typeof task.title === "string" &&
    (typeof task.score === "number" || typeof task.score === "undefined")
  );
}

export async function scoreTasks(payload: unknown): Promise<ScoredTask[]> {
  const res = await fetch(`${API_BASE}/score/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    mode: "cors",
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return extractScoredTasks(data);
}

export async function createAkiflowTestTask() {
  const res = await fetch(`${API_BASE}/akiflow/test-task`, {
    method: "POST",
    mode: "cors",
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data;
}

export async function getAkiflowToday(): Promise<AkiflowTask[]> {
  const res = await fetch(`${API_BASE}/akiflow/today`, { mode: "cors" });
  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  if (!data || !Array.isArray(data.tasks)) return [];
  return data.tasks.filter(isAkiflowTask);
}

export async function completeAkiflowTask(taskId: string) {
  const res = await fetch(`${API_BASE}/akiflow/complete-task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId }),
    mode: "cors",
  });
  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data;
}

function isAkiflowTask(value: unknown): value is AkiflowTask {
  if (!value || typeof value !== "object") return false;

  const task = value as { id?: unknown; title?: unknown; source?: unknown };
  return typeof task.id === "string" && typeof task.title === "string" && task.source === "akiflow";
}
