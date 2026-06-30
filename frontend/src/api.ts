const API_BASE = "http://localhost:8000";

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

export type TaskAnalysis = {
  estimated_duration_minutes?: number;
  requires_deep_work?: boolean;
  can_split?: boolean;
  recommended_chunks?: string[];
  best_time_of_day?: "morning" | "afternoon" | "evening" | "anytime";
  energy_required?: "low" | "medium" | "high";
  context_switch_cost?: "low" | "medium" | "high";
};

export type AnalyzedTask = DashboardTask & {
  analysis?: TaskAnalysis;
};

export type SimulationTask = DashboardTask & {
  score?: number;
  reasons?: string[];
  analysis?: TaskAnalysis;
  defer_reason?: string;
};

export type PlanningSimulation = {
  current_plan: SimulationTask[];
  recommended_plan: SimulationTask[];
  deferred_tasks: SimulationTask[];
  remaining_minutes: number;
  explanation: string;
  changes_summary: {
    recommended_count: number;
    deferred_count: number;
    would_modify_akiflow: boolean;
  };
};

export type OperatorTask = {
  task_id: string;
  title: string;
  description?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  duration?: number | null;
  priority?: string | null;
  tags?: string[];
  links?: string[];
  status?: string | null;
  scheduled_start?: string | null;
  scheduled_date?: string | null;
  deadline?: string | null;
  done: boolean;
  source: "akiflow";
  last_synced_at: string;
};

export type ApplyPlanResponse = {
  applied: boolean;
  dry_run: boolean;
  would_modify_akiflow: boolean;
  actions: Array<{
    action?: string;
    type?: string;
    task_id?: string | null;
    title?: string;
    start_datetime?: string;
    duration?: number;
    position?: number;
    reason?: string;
    dry_run?: boolean;
    error?: string;
    [key: string]: unknown;
  }>;
  skipped_actions: Array<{
    action?: string;
    type?: string;
    task_id?: string | null;
    title?: string;
    start_datetime?: string;
    duration?: number;
    reason?: string;
    [key: string]: unknown;
  }>;
  succeeded_actions: Array<{
    action?: string;
    type?: string;
    task_id?: string | null;
    title?: string;
    start_datetime?: string;
    duration?: number;
    reason?: string;
    [key: string]: unknown;
  }>;
  failed_actions: Array<{
    action?: string;
    type?: string;
    task_id?: string | null;
    title?: string;
    start_datetime?: string;
    duration?: number;
    reason?: string;
    error?: string;
    [key: string]: unknown;
  }>;
  message: string;
};

export type SyncTasksResponse = {
  synced: number;
  tasks: OperatorTask[];
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

function extractAnalyzedTasks(data: unknown): AnalyzedTask[] {
  if (Array.isArray(data)) return data.filter(isAnalyzedTask);

  if (data && typeof data === "object") {
    const candidate = data as {
      tasks?: unknown;
      analyzed_tasks?: unknown;
    };

    const tasks = candidate.tasks ?? candidate.analyzed_tasks;
    if (Array.isArray(tasks)) return tasks.filter(isAnalyzedTask);
  }

  return [];
}

function isAnalyzedTask(value: unknown): value is AnalyzedTask {
  if (!value || typeof value !== "object") return false;

  const task = value as { title?: unknown; analysis?: unknown };
  return typeof task.title === "string" && (typeof task.analysis === "object" || typeof task.analysis === "undefined");
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

export async function analyzeTasks(payload: unknown): Promise<AnalyzedTask[]> {
  const res = await fetch(`${API_BASE}/analyze/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    mode: "cors",
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return extractAnalyzedTasks(data);
}

export async function getPlanningSimulation(): Promise<PlanningSimulation> {
  const res = await fetch(`${API_BASE}/planning/simulation`, { mode: "cors" });
  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data as PlanningSimulation;
}

export async function applyPlan(confirm = false): Promise<ApplyPlanResponse> {
  const res = await fetch(`${API_BASE}/planning/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm }),
    mode: "cors",
  });
  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data as ApplyPlanResponse;
}

export async function syncTasks(startDate: string, endDate: string): Promise<SyncTasksResponse> {
  const res = await fetch(`${API_BASE}/tasks/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
    mode: "cors",
  });
  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data as SyncTasksResponse;
}

export async function getTaskRegistry(): Promise<OperatorTask[]> {
  const res = await fetch(`${API_BASE}/tasks/registry`, { mode: "cors" });
  const data = await res.json();

  if (!res.ok) {
    throw new Error(JSON.stringify(data, null, 2));
  }

  return data as OperatorTask[];
}
