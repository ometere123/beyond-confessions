# Third-party attribution

This repository uses the following upstream research starter as an external runtime dependency during Milestone 1:

* Poseidon Research, [`collusion_hackathon`](https://github.com/poseidon-research/collusion_hackathon), audited at commit `e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8` on 2026-10-25.
* The relevant starter material is the `COMPUTE.md` routing guide, `util/poseidon_compute`, and `colosseum/` including Terrarium/CoLLAB integration and experiment logging.
* Colosseum cites Nakamura et al., *Colosseum: Auditing Collusion in Cooperative Multi-Agent Systems*, [arXiv:2602.15198](https://arxiv.org/abs/2602.15198).

The starter is not copied into this repository. Beyond Confessions adds a direct OpenAI endpoint adapter configuration, an external runner, request/token instrumentation, validators, cost accounting, tests, and documentation. The upstream source is not modified by this repository; the adaptation is applied through environment variables and a derived YAML config at runtime.

Refer to [docs/starter-audit.md](docs/starter-audit.md) for the inspected source paths and exact modification boundary.
