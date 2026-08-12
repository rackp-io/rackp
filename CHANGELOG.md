# Changelog

The RACK Protocol specification is versioned as a whole. The normative content spans
[RFC-0001](docs/RFC-0001.md), [RFC-0002](docs/RFC-0002.md), `schemas/` and `norms/`, so no
single document carries a version of its own. Each version below is a signed git tag on this
repository, and an artifact's `rackp_version` field resolves to one of them.

Versions are `0.x` while the core semantics layer is a draft. Per semantic versioning, a `0.x`
release may change anything; the minor number is raised whenever the meaning of a field, the
set of required fields, or a computation changes. Editorial revisions do not raise it.

## 0.2.0-alpha

Released 2026-08-12.

### Changed

- `POH_CERTIFICATE`: `provenance` no longer partitions the artifact. `ai_ratio` reports only
  positively evidenced AI involvement and MUST NOT be derived as the complement of
  `human_ratio`; `1 - human_ratio - ai_ratio` is an unattributed remainder. A reader of a
  certificate issued before this version cannot assume either reading from the value alone
  ([#6](https://github.com/rackp-io/rackp/issues/6)).
- `CONTRIBUTION_RESULT`: `assessment.certification.proof_hash` now covers the result body.
  It previously had no defined subject, and the reference implementation hashed only the
  `cert_id` and issuance time, which committed to nothing about the verdict
  ([#13](https://github.com/rackp-io/rackp/issues/13)).

### Added

- `POH_CERTIFICATE`: `keeper.keeper_public_key`, required. A Referee MUST obtain the Keeper's
  key and MUST NOT issue a certificate without it, so that the certificate carries its own root
  of trust once `keeper_endpoint` stops resolving
  ([#10](https://github.com/rackp-io/rackp/issues/10)).
- `CONTRIBUTION_RESULT`: `signature`, required. The verdict was the only issued artifact that
  carried no signature, leaving a recipient unable to confirm either its authorship or its
  contents ([#13](https://github.com/rackp-io/rackp/issues/13)).
- `CONTRIBUTION_RESULT`, `POH_CERTIFICATE`, `REFEREE_PROFILE`: `rackp_version`, required. The
  version of this specification the issuer implements. `issue_date` does not recover it, since
  a date records what the specification said rather than what the issuing implementation
  followed ([#12](https://github.com/rackp-io/rackp/issues/12)).
- `POH_CERTIFICATE`: `norms_used`, required. The Norm Profiles applied, each with the SHA-256
  of the RFC 8785 canonical form of the document the Referee retrieved. A profile identifier
  and its URL stay constant across a revision, so neither identifies which text produced a
  ratio — and for PoHI the measurement definition lives in the profile rather than in this
  specification. One hash per profile rather than one digest over the set, so a profile that
  is still retrievable stays verifiable when another issuer's document is gone.
  `profile_version` is not recorded: the hash pins the document, and the version is inside the
  document it pins ([#11](https://github.com/rackp-io/rackp/issues/11)).
- `CLAIM_ANCHOR`: `norm_profiles[].norm_document_hash`, optional. Records the governing
  revision before the work is produced, so a document replaced between declaration and
  assessment becomes visible instead of silently changing the outcome. Optional deliberately:
  requiring it would make a Norm publisher's availability a precondition for anchoring at all
  ([#11](https://github.com/rackp-io/rackp/issues/11)).
- RFC-0001 Section 9.4: guidance that a published Norm Profile should not be edited in place,
  that a revision changing a requirement or a computation should take a new `profile_id` and
  URL, and that an authority should keep every published revision retrievable. These are
  conventions rather than checks — RACKP cannot bind issuers in namespaces it does not
  control, which is why an assessment records the hash of the document it applied.

### Removed

- The per-document `Version` row in the RFC-0001 and RFC-0002 headers. The specification is
  versioned as a whole; carrying a version in each document invited them to disagree with each
  other and with `schemas/`, which is equally normative.

### Upgrading

This release adds required fields to messages a Keeper validates on receipt, so **deploy
Referees before Keepers** — a Keeper on the new schemas rejects messages from a Referee still
on the old ones. The reverse order is safe.

Artifacts issued before this release are not reissued: `proof_hash` and the issuer's signature
fix their contents at issuance.

## 0.1.0-alpha

Initial public specification, 2026-07-16.
