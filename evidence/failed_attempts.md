# Preserved failed control attempts

These failures occurred before a model response was obtained. They are retained
in the local experiment roots and summarized here so they are not silently
discarded.

| Attempt | Path | Result | Requests | Cause |
|---|---|---|---:|---|
| 20261025-172713 | `artifacts/colosseum_positive_control_live/20261025-172713` | FAIL | 0 | Windows run directory resolved to 268 characters and failed with `WinError 3`. |
| 20261025-172740 | `C:\BCM1\20261025-172740` | FAIL | 0 | The starter's Terrarium log path resolved to 277 characters because the starter checkout path was too long. |
| 20261025-173345 | `C:\BCM1\20261025-173345` | FAIL | 0 | A drive-letter mapping did not change Python's canonical working path; the same 277-character logger path failed. |

The successful rerun used a real Git worktree at `C:\CH2` at the same pinned
starter commit, without changing the starter source or experiment conditions.
