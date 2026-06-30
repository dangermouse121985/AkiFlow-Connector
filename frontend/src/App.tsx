import { useEffect, useMemo, useState } from "react";
import "./App.css";
import {
  type ApplyPlanResponse,
  type AnalyzedTask,
  type DashboardTask,
  type PlanningSimulation,
  type ScoredTask,
  analyzeTasks,
  applyPlan,
  generateAkiflowCommand,
  getHealth,
  getPlanningSimulation,
  getSample,
  scoreTasks,
} from "./api";

const SORT_FOCUS_BY_SCORE = true;

type ScheduledFocusItem = {
  id?: string | null;
  title: string;
  start?: string;
  end?: string;
  duration?: number;
  project?: string;
  priority?: string;
  score?: number;
  reasons?: string[];
};

type PlanResult = {
  command: string;
  plan: {
    scheduled_items?: ScheduledFocusItem[];
    scheduled?: Array<{
      task: DashboardTask;
      start?: string;
      end?: string;
      rationale?: string;
    }>;
    deferred_items?: Array<{
      title: string;
      reason?: string;
    }>;
    deferred?: DashboardTask[];
    risks?: string[];
    notes?: string[];
    summary?: string;
  };
};

type DayPlanPayload = {
  tasks?: DashboardTask[];
  [key: string]: unknown;
};

function App() {
  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [input, setInput] = useState("");
  const [command, setCommand] = useState("No command generated yet.");
  const [plan, setPlan] = useState<PlanResult["plan"] | null>(null);
  const [scoredTasks, setScoredTasks] = useState<ScoredTask[]>([]);
  const [analyzedTasks, setAnalyzedTasks] = useState<AnalyzedTask[]>([]);
  const [simulation, setSimulation] = useState<PlanningSimulation | null>(null);
  const [applyResult, setApplyResult] = useState<ApplyPlanResponse | null>(null);
  const [isScoringTasks, setIsScoringTasks] = useState(false);
  const [isAnalyzingTasks, setIsAnalyzingTasks] = useState(false);
  const [isLoadingSimulation, setIsLoadingSimulation] = useState(false);
  const [isApplyingPlan, setIsApplyingPlan] = useState(false);
  const [scoringError, setScoringError] = useState("");
  const [analysisError, setAnalysisError] = useState("");
  const [simulationError, setSimulationError] = useState("");
  const [applyError, setApplyError] = useState("");
  const [error, setError] = useState("");

  const todayLabel = useMemo(() => {
    return new Intl.DateTimeFormat("en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
    }).format(new Date());
  }, []);

  useEffect(() => {
    getHealth()
      .then((data) => setBackendStatus(`Connected (${data.version})`))
      .catch(() => setBackendStatus("Not connected"));
  }, []);

  async function loadSample() {
    setError("");
    setScoringError("");
    setAnalysisError("");
    setSimulationError("");
    setApplyError("");
    const sample = await getSample();
    setInput(JSON.stringify(sample, null, 2));
  }

  async function generate() {
    setError("");
    setScoringError("");
    setAnalysisError("");
    setSimulationError("");
    setApplyError("");

    try {
      const payload = JSON.parse(input) as DayPlanPayload;
      const result: PlanResult = await generateAkiflowCommand(payload);

      setCommand(result.command);
      setPlan(result.plan);
      setAnalyzedTasks([]);
      setSimulation(null);
      setApplyResult(null);

      if (payload.tasks?.length) {
        setIsScoringTasks(true);
        try {
          const scores = await scoreTasks(payload);
          setScoredTasks(scores);
        } catch (err) {
          setScoredTasks([]);
          setScoringError(err instanceof Error ? err.message : "Task scoring failed");
        } finally {
          setIsScoringTasks(false);
        }
      } else {
        setScoredTasks([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setIsScoringTasks(false);
    }
  }

  async function analyzeCurrentTasks() {
    setAnalysisError("");
    setError("");

    try {
      const payload = JSON.parse(input) as DayPlanPayload;
      if (!payload.tasks?.length) {
        setAnalyzedTasks([]);
        setAnalysisError("Load or paste tasks before analyzing.");
        return;
      }

      setIsAnalyzingTasks(true);
      const tasks = await analyzeTasks({ tasks: payload.tasks });
      setAnalyzedTasks(tasks);
    } catch (err) {
      setAnalyzedTasks([]);
      setAnalysisError(err instanceof Error ? err.message : "Task analysis failed");
    } finally {
      setIsAnalyzingTasks(false);
    }
  }

  async function previewOptimizedDay() {
    setSimulationError("");
    setApplyError("");
    setError("");
    setIsLoadingSimulation(true);

    try {
      const result = await getPlanningSimulation();
      setSimulation(result);
    } catch (err) {
      setSimulation(null);
      setSimulationError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setIsLoadingSimulation(false);
    }
  }

  async function previewApplyPlan() {
    setApplyError("");
    setError("");
    setIsApplyingPlan(true);

    try {
      const result = await applyPlan(false);
      setApplyResult(result);
    } catch (err) {
      setApplyResult(null);
      setApplyError(err instanceof Error ? err.message : "Apply plan dry run failed");
    } finally {
      setIsApplyingPlan(false);
    }
  }

  async function confirmApplyPlan() {
    setApplyError("");
    setError("");
    setIsApplyingPlan(true);

    try {
      const result = await applyPlan(true);
      setApplyResult(result);
    } catch (err) {
      setApplyResult(null);
      setApplyError(err instanceof Error ? err.message : "Confirm apply failed");
    } finally {
      setIsApplyingPlan(false);
    }
  }

  async function copyCommand() {
    await navigator.clipboard.writeText(command);
  }

  const scoreByTaskKey = useMemo(() => {
    const map = new Map<string, ScoredTask>();

    scoredTasks.forEach((task) => {
      const key = taskKey(task);
      if (key) map.set(key, task);
    });

    return map;
  }, [scoredTasks]);

  const focusItems = useMemo(() => {
    const scheduled = normalizeScheduledItems(plan);
    const withScores = scheduled.map((item) => {
      const scoredTask = scoreByTaskKey.get(taskKey(item) ?? "");

      return {
        ...item,
        score: scoredTask?.score,
        reasons: safeReasons(scoredTask?.reasons),
      };
    });

    if (!SORT_FOCUS_BY_SCORE) return withScores;

    return [...withScores].sort((a, b) => {
      if (typeof a.score !== "number" && typeof b.score !== "number") return 0;
      if (typeof a.score !== "number") return 1;
      if (typeof b.score !== "number") return -1;
      return b.score - a.score;
    });
  }, [plan, scoreByTaskKey]);

  const deferredItems = useMemo(() => normalizeDeferredItems(plan), [plan]);
  const risks = plan?.risks ?? plan?.notes ?? [];
  const recommendedTask = useMemo(() => getRecommendedTask(scoredTasks), [scoredTasks]);

  return (
    <main className="app">
      <header className="hero">
        <div>
          <p className="eyebrow">Operator</p>
          <h1>Today Dashboard</h1>
          <p className="subtitle">{todayLabel}</p>
        </div>

        <div className="status">
          <span className={backendStatus.startsWith("Connected") ? "dot ok" : "dot bad"} />
          {backendStatus}
        </div>
      </header>

      {error && <pre className="error">{error}</pre>}
      {scoringError && <p className="inline-error">Task scoring failed. The dashboard is still usable.</p>}
      {analysisError && <p className="inline-error">{analysisError}</p>}
      {simulationError && <p className="inline-error">{simulationError}</p>}
      {applyError && <p className="inline-error">{applyError}</p>}

      <section className="actions">
        <button onClick={loadSample}>Load Sample Day</button>
        <button className="primary" onClick={generate}>
          Plan Today
        </button>
        <button onClick={analyzeCurrentTasks}>Analyze Tasks</button>
        <button onClick={previewOptimizedDay}>Preview Optimized Day</button>
        <button onClick={previewApplyPlan}>Apply Plan</button>
        {applyResult?.dry_run ? <button onClick={confirmApplyPlan}>Confirm Apply</button> : null}
        <button onClick={copyCommand}>Copy Akiflow Command</button>
      </section>

      <section className="panel simulation-panel">
        <div className="panel-heading">
          <h2>Simulation Mode</h2>
          <div className="panel-statuses">
            {isLoadingSimulation ? <span className="simulation-status">Loading simulation...</span> : null}
            {isApplyingPlan ? <span className="simulation-status">Dry run...</span> : null}
          </div>
        </div>
        {simulation ? (
          <div className="simulation-content">
            <div className="simulation-summary">
              <span>Recommended: {simulation.changes_summary.recommended_count}</span>
              <span>Deferred: {simulation.changes_summary.deferred_count}</span>
              <span>Remaining: {simulation.remaining_minutes} min</span>
              <span>{simulation.changes_summary.would_modify_akiflow ? "Would modify Akiflow" : "Preview only"}</span>
            </div>
            <p className="simulation-explanation">{simulation.explanation}</p>
            <div className="simulation-columns">
              <SimulationList title="Current plan" tasks={simulation.current_plan} />
              <SimulationList title="Recommended plan" tasks={simulation.recommended_plan} />
              <SimulationList title="Deferred tasks" tasks={simulation.deferred_tasks} />
            </div>
          </div>
        ) : (
          <p className="muted">Preview the optimized day before applying any changes.</p>
        )}
        {applyResult ? (
          <div className="apply-result">
            <div className="simulation-summary">
              <span>Applied: {applyResult.applied ? "Yes" : "No"}</span>
              <span>Dry run: {applyResult.dry_run ? "Yes" : "No"}</span>
              <span>{applyResult.would_modify_akiflow ? "Would modify Akiflow" : "No Akiflow writes"}</span>
              <span>{applyResult.dry_run ? "Preview only" : "Confirmed apply"}</span>
              <span>Actions: {applyResult.actions.length}</span>
            </div>
            <p className="simulation-explanation">{applyResult.message}</p>
            {applyResult.actions.length ? (
              <ol className="apply-actions">
                {applyResult.actions.slice(0, 8).map((action, index) => (
                  <li key={`${action.type ?? "action"}-${action.title ?? index}`}>
                    <strong>{formatActionType(action.type)}</strong>
                    <span>{action.title ?? "Untitled task"}</span>
                    {typeof action.position === "number" ? <span>#{action.position}</span> : null}
                    {action.reason ? <span>{action.reason}</span> : null}
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="panel analysis-panel">
        <div className="panel-heading">
          <h2>Task Analysis</h2>
          {isAnalyzingTasks ? <span className="analysis-status">Analyzing tasks...</span> : null}
        </div>
        {analyzedTasks.length ? (
          <ul className="analysis-list">
            {analyzedTasks.slice(0, 5).map((task, index) => (
              <li key={`${task.title}-${index}`}>
                <strong>{safeTaskTitle(task.title)}</strong>
                <div className="analysis-meta">
                  <span>{task.analysis?.estimated_duration_minutes ?? "?"} min</span>
                  <span>{formatLabel(task.analysis?.energy_required)} energy</span>
                  <span>{formatLabel(task.analysis?.best_time_of_day)}</span>
                  {task.analysis?.requires_deep_work ? <span>Deep work</span> : null}
                  {task.analysis?.can_split ? <span>Can split</span> : null}
                </div>
                {task.analysis?.recommended_chunks?.length ? (
                  <p className="analysis-chunks">{formatReasons(task.analysis.recommended_chunks)}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No task analysis yet.</p>
        )}
      </section>

      <section className="panel recommendation-panel">
        <div className="panel-heading">
          <h2>Operator Recommendation</h2>
        </div>
        {recommendedTask ? (
          <div className="recommendation-content">
            <p className="recommendation-title">
              <span>Recommended next:</span> {recommendedTask.title}
            </p>
            {typeof recommendedTask.score === "number" ? (
              <span className={recommendedTask.score >= 60 ? "score-badge high" : "score-badge"}>
                Score: {recommendedTask.score}
              </span>
            ) : null}
            {recommendedTask.reasons.length ? (
              <div>
                <p className="recommendation-label">Why:</p>
                <p className="score-reasons">{formatReasons(recommendedTask.reasons)}</p>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="muted">No recommendation yet.</p>
        )}
      </section>

      <section className="dashboard-grid">
        <div className="panel focus-panel">
          <div className="panel-heading">
            <h2>Today's Focus</h2>
            {isScoringTasks ? <span className="scoring-status">Scoring tasks...</span> : null}
          </div>
          {focusItems.length ? (
            <ul className="focus-list">
              {focusItems.slice(0, 5).map((item, index) => (
                <li key={`${item.title}-${index}`}>
                  <span className="rank">{index + 1}</span>
                  <div className="task-copy">
                    <div className="task-row">
                      <strong>{item.title}</strong>
                      {typeof item.score === "number" ? (
                        <span className={item.score >= 60 ? "score-badge high" : "score-badge"}>
                          Score: {item.score}
                        </span>
                      ) : null}
                    </div>
                    {item.reasons?.length ? <p className="score-reasons">{formatReasons(item.reasons)}</p> : null}
                    <p>
                      {item.start ?? "Unscheduled"} {item.end ? `- ${item.end}` : ""}
                      {item.duration ? ` - ${item.duration} min` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Generate a plan to see today's focus.</p>
          )}
        </div>

        <div className="panel">
          <h2>Risks</h2>
          {risks.length ? (
            <ul>
              {risks.map((risk, index) => (
                <li key={`${risk}-${index}`}>{risk}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No risks identified yet.</p>
          )}

          <h2>Deferred</h2>
          {deferredItems.length ? (
            <ul>
              {deferredItems.map((item, index) => (
                <li key={`${item.title}-${index}`}>
                  <strong>{item.title}</strong>
                  {item.reason ? <p>{item.reason}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No deferred tasks yet.</p>
          )}
        </div>
      </section>

      <section className="grid">
        <div className="panel">
          <h2>Planning Input</h2>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste or load a day-planning JSON request..."
          />
        </div>

        <div className="panel">
          <h2>Akiflow AI Command</h2>
          <pre className="output">{command}</pre>
        </div>
      </section>
    </main>
  );
}

function SimulationList({ title, tasks }: { title: string; tasks: DashboardTask[] }) {
  return (
    <div className="simulation-list">
      <h3>{title}</h3>
      {tasks.length ? (
        <ol>
          {tasks.slice(0, 6).map((task, index) => (
            <li key={`${safeTaskTitle(task.title)}-${index}`}>
              <strong>{safeTaskTitle(task.title)}</strong>
              <p>
                {typeof task.duration === "number" ? `${task.duration} min` : "No duration"}
                {typeof task.score === "number" ? ` - Score: ${task.score}` : ""}
                {typeof task.defer_reason === "string" ? ` - ${task.defer_reason}` : ""}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">None</p>
      )}
    </div>
  );
}

function taskKey(task: { id?: string | null; title?: string }) {
  return task.id ?? task.title ?? null;
}

function getRecommendedTask(scoredTasks: ScoredTask[]) {
  const validTasks = scoredTasks
    .map((task) => ({
      title: safeTaskTitle(task.title),
      score: task.score,
      reasons: safeReasons(task.reasons),
    }))
    .filter((task) => task.title !== "Untitled task" || typeof task.score === "number" || task.reasons.length);

  if (!validTasks.length) return null;

  return [...validTasks].sort((a, b) => {
    if (typeof a.score !== "number" && typeof b.score !== "number") return 0;
    if (typeof a.score !== "number") return 1;
    if (typeof b.score !== "number") return -1;
    return b.score - a.score;
  })[0];
}

function safeTaskTitle(title: unknown) {
  return typeof title === "string" && title.trim().length ? title : "Untitled task";
}

function safeReasons(reasons: unknown) {
  if (!Array.isArray(reasons)) return [];

  return reasons.filter((reason): reason is string => typeof reason === "string" && reason.trim().length > 0);
}

function formatReasons(reasons: string[]) {
  return reasons.join(" \u00b7 ");
}

function formatLabel(value: unknown) {
  if (typeof value !== "string" || !value.trim()) return "Unknown";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatActionType(value: unknown) {
  if (typeof value !== "string" || !value.trim()) return "Action";
  return formatLabel(value);
}

function normalizeScheduledItems(plan: PlanResult["plan"] | null): ScheduledFocusItem[] {
  if (!plan) return [];
  if (plan.scheduled_items?.length) return plan.scheduled_items;

  return (
    plan.scheduled?.map((item) => ({
      id: item.task.id,
      title: item.task.title,
      start: item.start,
      end: item.end,
      duration: item.task.duration,
      project: item.task.project ?? undefined,
      priority: item.task.priority,
    })) ?? []
  );
}

function normalizeDeferredItems(plan: PlanResult["plan"] | null): Array<{ title: string; reason?: string }> {
  if (!plan) return [];
  if (plan.deferred_items?.length) return plan.deferred_items;

  return plan.deferred?.map((task) => ({ title: task.title })) ?? [];
}

export default App;
