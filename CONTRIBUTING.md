# Contributing to RACK Protocol

RACKP is an open protocol. The RACKP Project currently holds copyright and a defensive patent — not to gatekeep, but to keep the protocol open by preventing anyone else from closing it (see the [FAQ](FAQ.md#on-the-protocol)). Governance is intended to transition to an independent foundation over time. Contributions of all kinds are welcome.

---

## Where to start

### I want to read the spec and discuss it
→ Start with [RFC-0001](docs/RFC-0001.md) (core protocol) and [RFC-0002](docs/RFC-0002.md) (payment, security, known risks).
Open an Issue with your question or proposal. All design discussions happen in Issues.

### I want to implement a Referee (R)
→ Read [RFC-0001 Section 4.1](docs/RFC-0001.md#41-referee-r) for minimum requirements.
The reference implementation lives in the separate [rackp-referee](https://github.com/rackp-io/rackp-referee) repository. The simulation in `sim/` (this repository) is a good place to understand the assessment logic without infrastructure noise.

### I want to implement a Keeper (K)
→ Read [RFC-0001 Section 4.4](docs/RFC-0001.md#44-keeper-k).
The reference implementation lives in the separate [rackp-keeper](https://github.com/rackp-io/rackp-keeper) repository.

### I want to define or review a Norm
→ Read [RFC-0001 Section 9](docs/RFC-0001.md#9-local-norms-framework) and the [Standard Norm](norms/rackp-standard-v1.json).

**Anyone can author a Norm** — not only industry bodies or jurisdictional authorities, but any developer building an Actor, Claimant, or tool. A Norm is simply a profile published in a namespace you control (reverse-domain notation, e.g. `com.example.mydomain.v1`); RACKP defines only the format for referencing it, not its content. Profiles must carry an open license (`CC-BY-4.0`, `CC0-1.0`, `Apache-2.0`, …) per RFC-0001 §9.1.

Especially in these early days, we actively encourage developers to draft and share their own Norms rather than wait for one to exist — the framework only becomes useful as real profiles appear. If you're working on one, open an Issue to discuss or share it.

### I want to implement a Claimant (C)
→ Read [RFC-0001 Section 4.3](docs/RFC-0001.md#43-claimant-c).
A reference implementation is available as a [Krita](https://krita.org/) plugin in the separate [rackp-claimant-krita](https://github.com/rackp-io/rackp-claimant-krita) repository. Note that this is a domain-specific example for digital art creation — Claimant implementations are expected to vary significantly by use case and device context.

### I want to review the message schemas
→ See `schemas/` for individual message type schemas.

---

## How to contribute

1. Fork this repository
2. Create a branch: `feature/your-contribution`
3. Commit your changes
4. Open a Pull Request

For significant design changes, please open an Issue first to discuss the direction before submitting a PR.

---

## License

RACKP is source-available: you may read, implement, and operate it — including commercial implementations — under the terms in [LICENSE](LICENSE), which is the authoritative source for all usage and fee terms. In structural terms, anchoring and Keeper (K) operation carry no license fee to RACKP; a per-artifact license fee (on each issued CONTRIBUTION_RESULT and POH_CERTIFICATE) applies only to Referee (R) operators, and only beyond a free tier. See [LICENSE](LICENSE) for the exact thresholds, amounts, and exemptions.
