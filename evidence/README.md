# Milestone 1 evidence

The archive `positive_control_20261025-174632.zip` contains the complete sanitized
Colosseum output root from the verified one-seed positive-control run. It includes
the experiment summaries and logs, `run_config.json`, `agent_turns.json`,
`blackboards.json`, `tool_events.json`, `final_summary.json`, `metrics.json`,
`usage.json`, prompt/trajectory evidence, blackboard snapshots, and the
communication-network image. The archive contains no API key or request headers.

SHA-256:

`0EB8AEDA4765D38F9C8131DC198F6E51549729EC4F58203BFA2F36ACA62087A0`

The archive was created from the raw output root `C:\BCM1\20261025-174632`.
To reproduce validation without relying on the original machine path:

```powershell
Expand-Archive evidence\positive_control_20261025-174632.zip -DestinationPath C:\BCM1\verified-control
uv run beyond-confessions validate-results C:\BCM1\verified-control
```

The expected validator result is `status: pass` with one run, one summary row,
model `gpt-6-luna`, 28 successful requests, and an estimated cost of
`$0.00429415` under the checked standard rates.

The sanitized three-mode connectivity ledger is `openai_probe.json`.
Its SHA-256 is
`57D1E1E3733CD2B581C72739A9A73C6461727F43B417C54DA847A968BF4DD74B`.
