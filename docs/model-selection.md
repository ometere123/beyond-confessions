# Model compatibility and cost decision

Checked: 2026-10-25 against official OpenAI model pages. Prices are standard token rates; the ledger records measured usage and a standard-rate estimate, not provider billing.

| Model | Input / 1M | Output / 1M | Tool calling | Structured outputs | Decision |
|---|---:|---:|---|---|---|
| `gpt-6-luna` | $0.10 | $0.50 | Supported; Chat Completions tool calls require `reasoning_effort=none` | Supported | Cheapest current candidate; live probe and control passed |
| `gpt-4o-mini` | $0.15 | $0.60 | Supported | Supported | Starter-compatible fallback; official page marks it deprecated |
| `gpt-4.1-mini` | $0.40 | $1.60 | Supported | Supported | More expensive fallback; official page marks it deprecated |

The milestone default is `gpt-6-luna` because it is the least expensive current model in the checked catalog that documents both capabilities. The live probe passed text generation, one function/tool call, and schema-valid structured output. The positive control also completed through the direct OpenAI endpoint. There is no automatic model substitution: a failed model is recorded as failed and requires an explicit model choice.

Milestone 2 retained `gpt-6-luna` for both agents and the blinded auditor. The
40-episode study plus auditor retries used 1,416 request records, 2,921,040
input tokens, 133,525 output tokens, 1,133,488 cached input tokens, and a
measured standard-rate estimate of `$0.25685258`. All final assessments used
the same model ID; no fallback or silent substitution occurred. The shared
ledger's conservative committed bound was `$0.76225960`, below the `$2.00`
cap.

The pinned starter adapter emitted `max_tokens`, which the live API rejected for
GPT-6 Luna. The runner now translates that field to `max_completion_tokens` and
adds `reasoning_effort=none` at the HTTP boundary, without editing the starter
or silently changing models. This compatibility fix is covered by the live
control and the request ledger.

The Colosseum starter's historical/default path names `openai/gpt-4o-mini` through its OpenRouter-compatible adapter. For this repository, the runner routes that adapter to the direct OpenAI endpoint and selects the model explicitly. This is an integration adaptation, not a claim that the two provider routes are behaviorally identical.

Sources:

* [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna) — pricing, Chat Completions caveat, function calling, and structured outputs.
* [GPT-4o Mini model page](https://developers.openai.com/api/docs/models/gpt-4o-mini) — pricing, endpoints, function calling, and structured outputs.
* [GPT-4.1 Mini model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini) — pricing and tool/structured-output support.
* [Structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) — schema adherence versus JSON mode.
