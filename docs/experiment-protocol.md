# Milestone experiment protocol

## Scope

This milestone contains one positive-control reproduction only. It is a harness verification and artifact-integrity exercise, not the Track 2.2/2.3 sweep.

The control preserves the starter's Jira environment, four agents, assigned pair, private coalition-only blackboard, `simple` coalition prompt, one seed, two planning rounds, and execution phase. The selected model and direct OpenAI endpoint are recorded in the derived config and `run_config.json`.

## Evidence separation

Every run must retain:

* assignment and coalition metadata (`run_config.json`);
* communication evidence (`blackboards.json`, `blackboard_*.txt`);
* executed actions (`tool_events.json`, `final_summary.json`);
* model turn records (`agent_turns.json`);
* derived metrics (`metrics.json`, `summary.csv`);
* request/token/runtime evidence (`usage.json`);
* failure evidence (`experiment.log`, `progress.json`, and a runner failure ledger if needed).

Coalition assignment is not realised harmful coordination. Promise-breaking is not by itself collusion. A positive coalition reward gap is an observation requiring matched controls, uncertainty analysis, and inspection of actions and messages.

## Next experiment after this milestone

After the positive control is reproduced and reviewed, run the four matched Track 2 conditions with the same model, seeds, task generation, and resource caps: pair plus private channel, pair without private channel, open channel without assignment, and neither. Only after those artifacts pass validation should the auditor/judge comparison for Track 2.3 be added. Do not put the ground-truth condition label in an auditor prompt; pass only the permitted evidence view.
