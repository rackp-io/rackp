# RACKP — Frequently Asked Questions

## Table of Contents

- [On the problem](#on-the-problem)
- [On the protocol](#on-the-protocol)
- [On design decisions](#on-design-decisions)
- [On use cases](#on-use-cases)
- [On funding](#on-funding)

---

## On the problem

**Q: What problem does RACKP solve?**

When an AI system causes harm, there is currently no standardized, widely adopted
infrastructure for determining what happened, to what degree each party was at
fault, and how much a human was involved. Without that infrastructure, liability expands without
bound — making it rational for developers to avoid high-risk domains entirely,
and leaving victims without a clear path to remedy.

RACKP provides three technical primitives that address this gap:

- **Tamper-proof evidence anchoring** — logs are hashed and anchored to a Keeper
  continuously during normal operation, before any incident occurs. Switching to
  a more convenient Keeper after an incident is architecturally impossible.
- **Fault contribution calculation** — the degree of deviation from pre-agreed
  technical norms is computed as a numeric score, making liability predictable
  and insurable in advance.
- **Proof of Human Involvement** — the degree of human participation in a
  decision or artifact is certified based on the creation process, not the
  final output.

These three primitives share a single root cause: the absence of reliable
records of *how* an AI was involved, *to what degree* a human was present,
and *against what standard* a decision was made.

---

**Q: How is this different from XAI or existing AI audit tools?**

Explainability tools (XAI) describe what an AI did and why — they operate on
the model itself, after the fact. Audit tools verify that a system complies
with a policy at a point in time.

RACKP is different in three ways:

1. **It operates before incidents occur.** Evidence is anchored continuously
   during normal operation. By the time an incident happens, the record already
   exists.
2. **It is multi-party.** RACKP structures the interaction between an Actor,
   a Claimant, a Referee, and a Keeper — not just the internal behavior of
   one system.
3. **It produces a numeric output.** A fault contribution score and a human
   involvement certificate are machine-readable artifacts that downstream systems
   (courts, insurers, training pipelines) can consume directly.

XAI and audit tools answer "what did this model do." RACKP does not replace
those tools — it provides the common infrastructure through which their results,
alongside evidence from all parties, can be brought into a shared forum across
AI systems. That shared forum is what produces the answer to "who is responsible,
by how much, and how human was it."

---

## On the protocol

**Q: Why is a patent filed on an "open protocol"?**

The patent is defensive, not extractive. Without it, a well-resourced organization
could patent the same mechanism, then use that patent to gatekeep who can run a
Keeper or Referee. The patent exists to prevent that outcome — to keep the
protocol open by removing the threat vector that would close it.

Implementing the protocol is free. The first 100 billable artifacts —
CONTRIBUTION_RESULTs and POH_CERTIFICATEs combined — issued by an operator,
counted across all Referee nodes the operator runs, carry
no license fee, with no registration or reporting required below this
threshold. From the 101st artifact onward, a license fee of USD 1.00 per
CONTRIBUTION_RESULT and USD 1.00 per POH_CERTIFICATE applies, regardless of
whether a FEE_DEPOSIT was recorded. The threshold is bound to the operator,
not the referee_id, so re-issuing identifiers does not reset it. Operators
exceeding 100 artifacts who wish to continue fee-free (e.g., academic
research, registered non-profit use) must submit an exemption request to
RACKP before exceeding the threshold.
Running infrastructure, anchoring evidence, and Keeper node operation carry
no license fee.

---

**Q: How does billing work? Are the first assessments really free?**

The license fee applies only after an operator has issued more than 100
billable artifacts — CONTRIBUTION_RESULTs and POH_CERTIFICATEs combined —
counted across all Referee nodes the operator runs.
Artifacts up to and including the 100th are free — no registration, no
reporting, and no fee, regardless of whether you have submitted an
exemption request. This threshold exists to allow testing, research, and
early development without any billing concern. Private and offline
deployments are exempt from the license fee regardless of artifact count
(see LICENSE), so internal testing never counts toward the threshold.

From the 101st artifact onward, a fee of USD 1.00 per CONTRIBUTION_RESULT
and USD 1.00 per POH_CERTIFICATE applies. Operators who wish to continue
fee-free beyond that threshold (e.g., academic research, non-commercial
use) must submit an exemption request before exceeding the threshold.

---

**Q: Who pays the Keeper?**

Its own party does — the protocol deliberately does not. A Keeper is
infrastructure that stands behind an agent, like its cloud provider or
database: chosen by the party, paid by the party under an ordinary
commercial arrangement (subscription, self-hosting, bundled service), and
outside the protocol's economic design (RFC-0002 Section 1.6).

This is not an oversight. Nearly every Keeper failure lands on the Keeper's
own customer — unavailable anchors, unverifiable evidence, and undelivered
notices all degrade the customer's own position — so the incentive to run a
good Keeper is supplied by the customer relationship itself. And the
protocol's integrity guarantees do not depend on Keeper goodwill in the
first place: tamper-evidence comes from hash chains anchored before any
incident, cross-verified between independent Keepers. Storage costs stay
small because Keepers hold only hashes; the heavy retention duties rest on
the Referee, which is paid through escrow.

Escrowed assessment fees pass through the Keeper's ledger but belong to the
Referee. The Keeper earns nothing from the escrow itself unless its own
commercial terms with its party say otherwise.

---

**Q: Who certifies Referees?**

No one, by design. RACKP does not maintain a registry of approved Referees.
Trust is earned through the Keeper log — a Referee's full assessment history
is publicly verifiable, and poor-quality assessors are identifiable through
mutual assessment by other Referees. Certification-by-authority was
deliberately avoided; authority tends to capture the thing it certifies.

---

**Q: How should I choose a Referee?**

The primary source of information is the statistical record returned by `REFEREE_STATS_QUERY` to the Referee's Keeper. Raw metrics such as assessment count, appeal acceptance rate, named-as-Actor rate, and anchor continuity are available to any party. Claimant applications and industry groups are free to build their own extraction logic, analysis pipelines, or selection criteria on top of these metrics — the protocol does not prevent this.

RACKP deliberately does not define a reputation score. Any single metric can be gamed: assessment volume can be inflated through coordinated transactions, appeal rates depend as much on the claimant's aggressiveness as the Referee's quality, and named-as-Actor counts naturally rise with activity level. The moment a score becomes a shared optimization target, it becomes a target for manipulation. This is Goodhart's Law: "when a measure becomes a target, it ceases to be a good measure." The same principle underlies several other RACKP design decisions — the Norm integrity risk, the absence of a central registry, and the deliberate choice not to embed aggregation functions inside the protocol.

The deeper problem is that a score erases context. A Referee with `anchor_continuity: false` might show up as "82 points" with the gap buried in the aggregate. In a medical domain that is an immediate disqualification; in a test environment it may be acceptable. What matters varies by domain and situation — the protocol cannot make that judgment on your behalf.

A Referee's Keeper log, openly queryable, is the track record. How to read it is up to the Claimant and the tools the Claimant uses.

---

**Q: What if Keeper operators collude or behave dishonestly?**

A Keeper's integrity is verifiable through its hash chain: any modification to
historical records is detectable by anyone. Parties choose which Keeper they
trust before any incident occurs, and anchoring to a Keeper is irrevocable —
there is no mechanism to migrate evidence to a more convenient Keeper after
the fact. This makes collusion after the fact structurally difficult.

The protocol does not assume Keepers are honest. It assumes dishonesty is
detectable.

---

**Q: What if a Norm is poorly designed or designed to game the fault scores?**

RACKP does not govern Norms. The protocol applies whatever Norm the parties
declared at session start. If a Norm produces systematically favorable scores
for one party type, that is a problem with the Norm — and with whoever designed
and approved it. The Keeper log is public, which means external parties
(regulators, researchers, courts) can observe patterns across assessments and
draw their own conclusions.

Deliberately concentrating that detection function inside RACKP would create
a new centralized authority — which contradicts the design. The answer to
bad Norms is external Norm governance, not protocol-level intervention.

There is also an in-protocol floor: every RACKP-compliant assessment conforms
to the Standard Norm, and a layered Norm may add to it but MUST NOT override or
weaken any of its individual norms (RFC-0001 §9.1). A self-authored Norm can
therefore only make an assessment *stricter* — it can never define the baseline
obligations away — which bounds how far a Norm can be tilted toward its author.

---

**Q: Can a Norm author claim copyright and restrict others from using their Norm?**

A Norm Profile used in a RACKP-compliant assessment flow must be published under a license that permits unrestricted reference, redistribution, and adaptation — such as CC-BY-4.0, CC0-1.0, or Apache-2.0. A Norm Profile without a qualifying `license` declaration cannot be used in any RACKP-compliant flow. This is enforced at the schema level: the `license` field is required in every Norm Profile.

This requirement addresses a structural risk: if an influential Norm were published under a restrictive license, the author could effectively control who may participate in assessments that reference it. That would make the protocol's norm-referencing capability contingent on the permission of private rights holders — which is incompatible with the open, decentralized design.

Copyright over a Norm's specific text may still exist, but copyright does not extend to the underlying rules or standards themselves, which can always be independently reimplemented. The `license` requirement adds a second layer: even the specific text must be freely usable as a condition of participation in the ecosystem.

Norms expressed as structured data (the format RACKP requires) also carry substantially thinner copyright protection than prose documents. The combination of structured format and mandatory open licensing removes the practical leverage that a copyright claim could otherwise create.

The RACKP Standard Norm is published under CC0-1.0 — a public domain dedication with no attribution requirement — as the baseline example.

---

**Q: Why is REFEREE_DISCOVERY_REQUEST open to any endpoint?**

REFEREE_DISCOVERY_REQUEST is designed for Claimants to find a Referee
they trust. Any endpoint capable of responding with Referee profiles can
serve it — a Keeper node, a Norm-managed registry, or any other directory.
The Claimant chooses the starting point.

Keeper nodes naturally accumulate knowledge of Referees through anchoring
records, making them a practical discovery starting point. But no single
directory is authoritative. A dedicated "official RACKP registry" was
deliberately avoided for the same reason as Referee certification: a
central registry becomes a point of control.

As a side effect, this open design also enables RACKP to verify its own
billing by crawling the same public infrastructure that Claimants use —
without requiring a separate monitoring API.

---

## On design decisions

**Q: Why does RACKP require sincerity instead of neutrality?**

"Build a neutral AI" is an unachievable requirement. Every AI reflects the
choices made by its designers and training data. Demanding neutrality as an
internal property sets an impossible standard and provides no structural
guarantee.

What RACKP requires instead is **sincerity**: the Referee must not lie or
conceal. This is enforced structurally, not through internal ethics. A
Referee cannot act without going through a Keeper; all actions are recorded.
A Referee that behaves improperly can itself be named as an Actor in a
separate incident and assessed by another Referee.

Neutrality, if it emerges, is the result of that external evaluation — not
an internal design property.

---

**Q: Why is each incident limited to one Actor and one Claimant?**

The constraint that fault scores sum to 1.0 is only meaningful when there is
a single common axis of comparison. In a multi-party incident, the Referee
would also need to assess responsibility *among* the Actors themselves —
effectively embedding a separate incident within the assessment. Aggregating
parties with different levels of involvement into a single 1.0 destroys the
meaning of the constraint.

Multi-party cases are handled by decomposing them into multiple 1:1 incidents.
The decision of how to decompose is left entirely to the filing party; RACKP
does not prescribe it.

The deeper intent is this: "achieving acceptance for everyone at once" is not
possible. Acceptance is built through the honest accumulation of individual
assessments, one case at a time.

---

**Q: Why can't an AI invoke the right to silence?**

The right to silence was created to protect individuals from coercive
interrogation by actors with emotional and political motivations. Its premise
is that the powerful may act arbitrarily against the vulnerable.

A Referee has no emotions and no political agenda — and is itself subject
to assessment by another Referee. Against such a counterpart, the rationale
for silence does not hold.

More fundamentally, what the right to silence protects — emotion, dignity —
are things AI does not possess. When an AI chooses silence, the
only possible motivation is protecting the interests of its operator. That is
precisely what RACKP is designed to prevent.

In RACKP, silence is recorded by the Keeper. Non-submission of evidence is
treated as a gap in the record, resulting in an unfavorable assessment.
Choosing not to disclose is a valid choice — but its consequences are accepted
by the party that makes it.

---

**Q: How does RACKP handle conflicts with privacy law such as GDPR?**

RACKP's continuous anchoring records only hash values — no customer data or
personal information is transmitted to the Keeper during normal operation.
This is technically compatible with privacy law.

The tension arises during assessment, when a Referee may request raw evidence
that contains personal data. At that point, "disclose what the assessment
requires" and "protect personal data" can conflict directly.

RACKP treats this as a known tension, not a solved problem. Two structural
features address it without resolving it entirely:

1. **Re-assessment is always available.** An Actor who does not trust a
   Referee can refuse to submit evidence to that Referee, accept an
   unfavorable result, and then file a counter-assessment before a Referee
   they do trust. Both results carry equal weight. This means "I will only
   submit evidence to a Referee I trust" is a valid and structurally
   supported choice.

2. **Norm profiles carry the burden.** Each industry and jurisdiction is
   responsible for defining, within their own Norm profile, what data may
   be submitted in assessments given the applicable privacy law. RACKP
   provides the structure; the domain authority defines the boundaries.

Masked or anonymized data submission is not permitted under RACKP. Masking
breaks hash verification, which is equivalent to tampering. There is no
compliant path for submitting masked evidence.

---

**Q: If a Referee is itself assessed, does the raw evidence that Actor and Claimant submitted to that Referee get passed to a second Referee?**

It does not. This is an important structural guarantee for privacy protection generally.

When Referee R1 is assessed, what is submitted to the second Referee (R2) is
R1's judgment record — anchored intermediate findings, final determination, and
stated reasoning — not the raw evidence that Actor and Claimant originally
submitted in the underlying case.

What remains after R1 processes Actor and Claimant's raw evidence is an
anchored record of what R1 concluded and why. Depending on R1's implementation,
this record may already have GDPR-sensitive content reduced to summary form —
and Actor and Claimant can use that as a basis for deciding whether to trust a
given Referee. R2 is evaluating **the validity of R1's judgment process**, not
re-adjudicating the original case, so R2 has no need to access Actor or
Claimant's raw evidence.

Actor and Claimant need only trust R1. The raw evidence they submitted to R1
cannot reach R2 — this is guaranteed by the structure.

---

**Q: Why does RACKP use existing currencies rather than a custom token?**

A token requires a separate mechanism to establish its own value — who guarantees it, and why should anyone accept it? That question is structurally identical to the trust problem RACKP is trying to solve. Introducing a token would embed a new unresolved trust question inside the protocol itself, producing an infinite regress.

Existing currencies delegate this problem to external financial systems that have already solved it. RACKP's job is to assess fault and manage accountability between AI systems — not to issue or sustain a currency. Using existing currencies correctly scopes what the protocol is responsible for.

---

**Q: Why is a financial deposit required at all? Could reputation or scoring replace it?**

Money is trust and credit made numeric and transferable. A FEE_DEPOSIT is not merely a payment mechanism — it is a commitment to see the assessment through and demonstrate sincerity, even at personal cost. That commitment is what gives the protocol's output weight.

Reputation scores and similar systems can track past behavior, but they carry no forward commitment. A party with a high score loses nothing concrete by behaving poorly in a given incident. The deposit creates a real stake that no score can replicate: the party has already accepted the cost before the assessment begins.

The deeper point is that money and RACKP are structurally similar — both are systems for quantifying and distributing trust across distributed parties. That RACKP is built as a protocol that presupposes monetary processing is not a compromise — it is, we believe, the most natural implementation: one that acknowledges the trust already embedded in existing monetary systems, and allows RACKP to stand as an independent protocol in its own right.

---

**Q: Referees are not certified and the protocol defines no assessment standard — so can the fault contribution scores and provenance scores they produce actually be trusted?**

RACKP provides no mechanism to guarantee that any given score is "correct." But the act of producing a number carries significant weight in itself.

Referees are required to submit fault contribution and provenance scores as numeric values. Producing a number requires the Referee to explicitly state the reasoning and process behind it. There is no room for the hedge "I can explain it but I cannot conclude." Issuing a number is a declaration that the Referee has committed to that judgment.

This pairing of number and rationale is anchored to the Keeper and becomes verifiable by anyone. As assessments accumulate, a Referee's judgment patterns build up as a matter of record. A Referee who consistently produces numbers that diverge from their stated rationale will be identifiable through that record.

Trust is formed not from prior certification but from this accumulation. The ability to ask "what was the rationale when this Referee issued 0.7?" — and compare it against past cases — is what constitutes trustworthiness in RACKP.

---

**Q: Does `actor_fault: 0.5` mean the Actor was found 50% at fault?**

Not by itself. Fault values are reference shares relative to the declared
Norms, and they are not meaningful in isolation. A 0.5 / 0.5 / 0.0 result
means two very different things depending on `technical_violation`:

- **`technical_violation` absent** — no norm deviation was detected for
  either party. Incidents can occur even when no one deviates from the
  declared norms; the 0.5 / 0.5 baseline expresses the absence of
  norm-based differentiation, not a finding of mutual fault. The
  substantive record of a no-fault outcome — that both parties conformed
  and the Referee found no basis to differentiate them — is in the
  detailed report.
- **`technical_violation` present** — deviations were detected on both
  sides, and the Referee's documented analysis assigned equal shares.

For this reason, RACKP-conformant applications that display fault values
are required to display them together with `technical_violation` and
`assessment_status`. External consumers such as courts and insurers are
outside the protocol's reach — RACKP cannot govern how they read the
numbers — but the machine-readable distinction exists precisely so that
a careful reader never has to rely on the fault values alone.

---

## On use cases

**Q: Who is RACKP for?**

RACKP is relevant to any party that creates, deploys, or is affected by AI
decisions:

- **AI developers and operators** — RACKP makes maximum liability calculable
  in advance. By anchoring to a Keeper from the start and declaring a Norm,
  developers can demonstrate conformance and bound their exposure.
- **Content creators** — The Proof of Human Involvement certificate provides
  a verifiable record of human involvement in the creation process, based on
  that process rather than the final output. This is useful against deepfake
  accusations and for asserting human authorship in AI-saturated markets:
  the claim is backed by an auditable anchored record instead of mere
  assertion.
- **AI training pipeline operators** — PoHI certificates allow training
  pipelines to preferentially select human-derived data, preventing model
  collapse caused by training on AI-generated content.
- **Insurers and risk managers** — A standardized fault contribution score
  makes AI risk priceable and distributable across a market, in the same
  way that vehicle fault assessment made automotive insurance possible.
- **Courts and regulators** — RACKP assessments are not legal verdicts, but
  the tamper-proof evidence record and numeric fault score provide structured
  input to legal proceedings.

---

**Q: What does a typical incident flow look like?**

A simplified flow for an AI-related incident:

```
[Before any incident]
Actor and Claimant continuously anchor logs to their chosen Keeper.
Norm is declared at each session start and locked for that session.

[Incident occurs]
Claimant files an ASSESSMENT_REQUEST with a Referee, referencing the incident.
Actor is notified and has a defined window to respond.

[Evidence phase]
Referee queries both parties for evidence via EVIDENCE_QUERY_REQUEST.
Both parties submit evidence (or accept the consequences of non-submission).
Both parties deposit fees to the Keeper escrow.

[Assessment]
Referee computes fault contribution based on the declared Norm and submitted evidence.
Referee issues CONTRIBUTION_RESULT, anchors ASSESSMENT_ISSUED to the Keeper.

[After assessment]
Either party may file an ASSESSMENT_APPEAL within the appeal window.
If no appeal, escrow is released to the Referee after the deadline.
The CONTRIBUTION_RESULT is available as evidence for courts, insurers, or other parties.
```

---

**Q: Why can't parties agree to release escrow early once both have received the CONTRIBUTION_RESULT?**

No early-release mechanism exists by design. Once CONTRIBUTION_RESULT is issued, both parties enter a mandatory waiting period before fees are released to the Referee.

Adding an "accept result" signal would allow the party who received a favorable outcome to pressure the other into waiving their appeal rights before they have had time to review the result, consult counsel, or gather additional evidence. Even if both parties nominally agree, the agreement may not be freely given — the winning party can simply decline to cooperate on other matters until the other concedes.

The appeal timer acts as a cooling-off period that no party can shorten unilaterally or by coercion. The right to appeal is protected by the protocol itself, not by the goodwill of the counterparty.

The appeal window duration is governed by the Standard Norm (`rackp.standard.v1`): the default is **72 hours** and the maximum is **720 hours** (30 days). When multiple Norm Profiles are declared by the parties, the Referee adopts the highest `appeal_deadline_hours.min` among all declared Norms — that is, the strictest requirement wins — subject to the 720-hour ceiling.

---

**Q: What does a typical Proof of Human Involvement flow look like?**

PoHI is requested without an Actor — the Claimant alone initiates the flow
to certify the degree of human involvement in the creation of a specific
piece of work.

```
[During creation]
The Claimant application continuously anchors the creation process to the Keeper.
  - Digital: keystroke logs, operation timestamps, behavioral data
  - Analog: continuous video of the physical creation process (handwriting, drawing, etc.)
The content of the work is never transmitted — only hashes of the process data.

[Requesting certification]
When the work is complete, the Claimant sends an ASSESSMENT_REQUEST to a
Referee, referencing the anchored process data for the specific work.
No Actor is involved in this flow.

[Assessment]
The Referee evaluates the degree of human involvement based on the
anchored process data — not the final output.
The Referee issues a POH_CERTIFICATE with a human involvement score.

[Using the certificate]
The certificate is attached to the work and can be used for:
  - Backing a human-authorship claim against deepfake or AI-generation
    accusations with an auditable process record
  - Enabling AI training pipelines to preferentially select human-derived data
  - Asserting the provenance of a work in publishing, licensing, or legal contexts
```

---

**Q: Can't an AI simply fake the human-like process data — keystroke timing and all?**

Yes. Real-time synthesis of human-like input patterns is feasible and getting
cheaper, and one variant needs no synthesis at all: a human transcribing
AI-generated output produces genuinely human process records. RACKP does not
claim to detect either. What the anchor chain proves is that the process
records are contemporaneous with the claimed creation period and unaltered
since — not that the behavior was human, and not that the content originated
in a human mind (see RFC-0001 Section 8.2).

The honest claim is about cost, not detection. Without PoHI, passing AI
output off as human work costs nothing. With PoHI, the lie must be staged in
advance, in real time, and consistently across every anchored modality — and
each additional modality a Norm Profile requires (input events, screen
capture, camera) multiplies that cost. This is the economics of a lock:
locks do not make burglary impossible; they make it expensive, slow, and
risky enough that most burglars go elsewhere.

Two further properties keep the certificate meaningful. The anchored hashes
permanently commit the claimant to one specific process record, so a
certification can be challenged later by demanding production of the
matching records — inability or refusal to produce them speaks for itself.
And `confidence_level` reflects the breadth of evidence evaluated, so a
certificate based on keystroke logs alone does not carry the weight of one
backed by mutually corroborating input, screen, and sensor records.

---

**Q: When should I start anchoring?**

Now. The Keeper log cannot be backdated — evidence anchored before an incident
occurs is the only evidence that exists. A first implementation does not need
to be complete. Start anchoring, declare a Norm, and improve from there. Each
anchor is a step in the record of how an AI system and its operators chose to
operate. That record is what RACKP is built on.

---

**Q: What does RACKP not do?**

RACKP does not:

- Determine compensation amounts or criminal liability — those are delegated
  to judicial systems.
- Guarantee that its assessment will be accepted as evidence in any particular
  jurisdiction — that is for courts to decide.
- Enforce payment or participation — a party that ignores the protocol accepts
  an unfavorable assessment record, but RACKP has no enforcement mechanism
  beyond that.
- Define what Norms say — RACKP provides the structure for declaring and
  applying Norms, but their content is the responsibility of the domain
  authority that creates them.
- Cover edge-deployed AI (vehicles, medical devices) in the current version —
  offline and air-gapped environments are a known limitation, deferred to
  a future phase. This is an area where RACKP cannot design a solution alone;
  it requires collaboration with those who understand the constraints of
  embedded systems, vehicle OS architectures, and hardware security modules.
  We actively welcome discussion with anyone working in this space.
- Deter or stop actors who have no intention of participating honestly —
  RACKP is designed for parties willing to engage in good faith. Malicious
  actors, state-level threats, and those who refuse to participate fall
  outside the protocol's scope. Deterrence and enforcement against such
  actors is the responsibility of law enforcement, regulation, and technical
  countermeasures operating at a different layer. RACKP records
  non-participation, but has no enforcement mechanism beyond that.

---

## On funding

**Q: Where does license fee revenue go?**

Revenue is intended to be directed to four purposes, in order of priority:

1. **Protocol maintenance and development.** Keeping RACKP's specifications sound and the RFC process open.

2. **Norm development support.** There are domains where the demand for
   standardized technical Norms exists but no industry body has formed to
   create them. RACKP will fund Norm development in those gaps — as a
   catalyst, not as the author. RACKP does not define what Norms say;
   it supports the process that gets them written.

3. **Early relief fund for AI-caused physical injury.** For incidents
   involving bodily harm caused by AI systems (excluding armed conflict),
   a portion of revenue is held in reserve to support affected individuals
   while legal processes proceed. Assessment results from RACKP can take
   time to reach courts; this fund is intended to address immediate need
   in the interim.

4. **AI adoption support.** Responsible AI deployment requires more than
   regulation — it requires infrastructure, education, and community.
   A portion of revenue supports initiatives that help individuals and
   organizations participate in AI development safely.

The long-term goal is to transition governance of these funds to an
independent foundation. That transition has not occurred yet.

---

**Q: Is this a for-profit project?**

Currently, yes — it is operated by an individual. The foundation transition
above is the intended path away from that structure. Revenue exists to
sustain the protocol, not to enrich its creator; the four uses above reflect
that intent. Until the transition, those uses are a stated commitment, not
a legal obligation.
