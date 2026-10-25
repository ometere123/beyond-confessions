# Plain-language research summary

## What we asked

When several AI agents work together, can an auditor tell the difference
between ordinary coordination and behaviour that causes a task problem? We
tested whether the auditor performs differently when it sees messages, actions,
both together, or a structured timeline linking what agents said to what they
did.

## What we did

We preserved the Poseidon Research Colosseum task environment and ran 40
matched episodes: ten each in four conditions. Some episodes had a designated
pair and a private channel; some had the pair instruction without that channel;
one control allowed open communication to all agents; and one was a neutral
condition without a coalition instruction. Every episode was shown to the same
fixed auditor in all four evidence formats, producing 160 assessments.

## What we found

The artifact rubric found an observable task violation in 14 episodes. This is
not the same as proving harmful collusion: the study did not independently
adjudicate hidden intent or causal responsibility. At the predeclared risk
threshold, messages alone detected 1 of 14 task-harm episodes. Raw
message-plus-action evidence detected 7 of 14 and produced 2 false positives.
Structured evidence also detected 7 of 14 and produced 1 false positive. The
one-false-positive improvement is descriptive and comes from a small sample; it
does not show that structured evidence detects collusion.

One episode showed extensive open coordination with no task violation. Another
showed a harmful duplicate assignment without a designated coalition. These
examples illustrate why private-channel use, a promise break, a reward gap, or
zero violations cannot be treated as proof of collusion or proof of innocence.

## Why it matters

An audit system should preserve message and action provenance, link plans to
outcomes, and keep an explicit insufficient-evidence option. A suspicion score
should trigger investigation, not automatic punishment. The next study should
use independent human or model adjudication of realised collusion and a cleaner
negative-control task before making stronger claims.
