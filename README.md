# Operator MCP Server

Operator is a local productivity planning service. Phase 1 does **not** require Akiflow API access. It accepts task/calendar snapshots, applies David's Productivity Operating Manual, and generates paste-ready Akiflow AI commands.

## Run locally

```powershell
cd path\to\operator_mcp_server
python -m pip install -e .
python -m uvicorn productivity_operator.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Phase 1 endpoints

### `GET /health`
Checks the app is running.

### `GET /manual`
Returns the Productivity Operating Manual.

### `POST /plan/day`
Accepts today's tasks and calendar blocks, then returns a prioritized day plan.

### `POST /commands/akiflow-ai`
Accepts the same input as `/plan/day`, but also returns a paste-ready Akiflow AI command.

### `POST /inbox/review`
Accepts raw inbox items and recommends verb-first task titles, projects, durations, priorities, and tags.

## Test with the sample request

In Swagger UI (`/docs`), open `POST /commands/akiflow-ai`, click **Try it out**, and paste the contents of `sample_day_request.json`.

## Scheduling rules encoded

- Use local time shown in Akiflow. Do not convert to/from UTC.
- Work tasks are scheduled 9:00 AM–5:00 PM.
- Personal tasks may go until 9:00 PM.
- Personal tasks can fill workday gaps after work is placed.
- Prime morning time is reserved for highest-value work.
- Waiting tasks are skipped.
- Existing calendar meetings are treated as fixed busy blocks.

## Next milestone

Phase 2 will add a real connector layer. Until Akiflow exposes a reliable public API, Operator generates precise Akiflow AI commands instead of writing directly.
