import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { generateAkiflowCommand, getHealth, getSample } from "./api";

type PlanResult = {
  command: string;
  plan: {
    scheduled_items?: Array<{
      title: string;
      start?: string;
      end?: string;
      duration?: number;
      project?: string;
      priority?: string;
    }>;
    deferred_items?: Array<{
      title: string;
      reason?: string;
    }>;
    risks?: string[];
    summary?: string;
  };
};

function App() {
  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [input, setInput] = useState("");
  const [command, setCommand] = useState("No command generated yet.");
  const [plan, setPlan] = useState<PlanResult["plan"] | null>(null);
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
    const sample = await getSample();
    setInput(JSON.stringify(sample, null, 2));
  }

  async function generate() {
    setError("");

    try {
      const payload = JSON.parse(input);
      const result: PlanResult = await generateAkiflowCommand(payload);

      setCommand(result.command);
      setPlan(result.plan);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  async function copyCommand() {
    await navigator.clipboard.writeText(command);
  }

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

      <section className="actions">
        <button onClick={loadSample}>Load Sample Day</button>
        <button className="primary" onClick={generate}>
          Plan Today
        </button>
        <button onClick={copyCommand}>Copy Akiflow Command</button>
      </section>

      <section className="dashboard-grid">
        <div className="panel focus-panel">
          <h2>Today’s Focus</h2>
          {plan?.scheduled_items?.length ? (
            <ul className="focus-list">
              {plan.scheduled_items.slice(0, 5).map((item, index) => (
                <li key={`${item.title}-${index}`}>
                  <span className="rank">{index + 1}</span>
                  <div>
                    <strong>{item.title}</strong>
                    <p>
                      {item.start ?? "Unscheduled"} {item.end ? `– ${item.end}` : ""}
                      {item.duration ? ` • ${item.duration} min` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Generate a plan to see today’s focus.</p>
          )}
        </div>

        <div className="panel">
          <h2>Risks</h2>
          {plan?.risks?.length ? (
            <ul>
              {plan.risks.map((risk, index) => (
                <li key={`${risk}-${index}`}>{risk}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No risks identified yet.</p>
          )}

          <h2>Deferred</h2>
          {plan?.deferred_items?.length ? (
            <ul>
              {plan.deferred_items.map((item, index) => (
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

export default App;