#!/usr/bin/env python3
# check_refs.py — cross-check every RFC/STD/schema reference in the sim against the
# current specification. A guard against stale references (e.g. the §10.4 → §9.5
# renumber): run it after editing sim comments and before publishing.
#
# A sim-maintenance tool, not a scenario — it lives in sim/tools/ and scans sim/.
# Run from anywhere: `python sim/tools/check_refs.py` (exit 1 on any broken reference).
#
# What it validates, per reference found in the sim sources:
#   §N.M / "Section N.M" / "RFC-000X SN.M"  → must be a real heading in RFC-0001/-0002/BINDING
#   STD-NNN                                  → must be defined in norms/rackp-standard-v1.json
#   schemas/<name>.json                      → must exist in rackp/schemas/
#   "type": "X" message literals             → X must be declared by some schema's type.const
#                                              (reverse check; sim-convenience allowlist below)
#
# It also cross-checks the specs themselves: every STD-NNN cited in the RFCs, the
# transport binding, the schemas, or the norms file must resolve to a norm_id defined
# in norms/rackp-standard-v1.json (the docs↔norms pass below).
#
# Severity:
#   ERROR  — a §ref that resolves in NO known spec, an unknown STD, or a missing schema file.
#            These are unambiguous breakage (exit code 1).
#   WARN   — a §ref that resolves but is ambiguous: it exists in BOTH RFCs and the citing
#            line carries no RFC-000X label, OR it is labelled for a doc that does not
#            contain it (possible mislabel). Needs a human eye, does not fail the run.
#
# Reference resolution is label-aware: within a line, a §ref is governed by the nearest
# preceding "RFC-0001"/"RFC-0002"/"binding §N" token (so "(RFC §6.14, §7, RFC-0002 §2.3)"
# attributes §6.14/§7 to no-label and §2.3 to RFC-0002).
import json
import re
import sys
from pathlib import Path

# Spec/comment context lines contain non-cp932 characters (em-dash, arrows). Force UTF-8
# output so the checker never crashes on its own report on a Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS_DIR = Path(__file__).resolve().parent   # sim/tools
SIM_DIR   = TOOLS_DIR.parent                   # sim
RACKP     = SIM_DIR.parent                      # rackp
DOCS      = RACKP / "docs"
SCHEMAS   = RACKP / "schemas"

# Sim comments cite three specs by number: the two RFCs and the transport binding.
# "binding §N" / "TRANSPORT-BINDING.md §N" refer to BINDING, not the RFCs.
DOC_FILES = {
    "RFC-0001": DOCS / "RFC-0001.md",
    "RFC-0002": DOCS / "RFC-0002.md",
    "BINDING":  DOCS / "TRANSPORT-BINDING.md",
}

# --- build the ground truth from the specs ------------------------------------------
HEADING = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)\.?\s*(.*)")
STD_TOK = re.compile(r"STD-(\d+)")

sections, titles = {}, {}   # doc -> set("6.14", ...) ; doc -> {num: heading title}
for doc, path in DOC_FILES.items():
    text = path.read_text(encoding="utf-8-sig")
    tmap = {}
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            tmap[m.group(1)] = m.group(2).strip()
    sections[doc] = set(tmap)
    titles[doc]   = tmap

# STD ground truth is the machine-readable Standard Norm, not "appears in an RFC".
# STD-033/034 lesson (2026-07-09): both were cited by RFC-0001 / the binding / the
# schemas and implemented everywhere, but the norm entries themselves were never added
# to rackp-standard-v1.json — and this checker, which took any RFC mention as a
# definition, was structurally unable to notice. Definitions now come only from
# norm_id entries; every mention anywhere else is a reference to be validated.
NORMS_FILE = RACKP / "norms" / "rackp-standard-v1.json"
NORM_ID = re.compile(r"RACKP-STD-(\d+)")

def std_key(num_str):
    return f"STD-{int(num_str):03d}"

known_stds = set()
for entry in json.loads(NORMS_FILE.read_text(encoding="utf-8-sig")).get("norms", []):
    m = NORM_ID.fullmatch(entry.get("norm_id", ""))
    if m:
        known_stds.add(std_key(m.group(1)))

# --- docs↔norms pass: dangling STD references in the specs themselves ----------------
# The sim scan below guards sim comments; this guards the specs. Scope: the three spec
# docs, every schema description, and the norms file's own cross-references.
std_doc_errors = []
_spec_sources = list(DOC_FILES.items()) + [("norms/" + NORMS_FILE.name, NORMS_FILE)]
_spec_sources += [("schemas/" + p.name, p) for p in sorted(SCHEMAS.glob("*.json"))]
for label, path in _spec_sources:
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        for n in STD_TOK.findall(line):
            if std_key(n) not in known_stds:
                std_doc_errors.append((f"{label}:{lineno}", std_key(n), line.strip()))

# Each schema's declared message type (properties.type.const) — paired with every schema
# reference in the human-review report so a person can confirm the right schema is cited.
schema_types = {}
for p in SCHEMAS.glob("*.json"):
    try:
        schema_types[p.name] = (json.loads(p.read_text(encoding="utf-8-sig"))
                                .get("properties", {}).get("type", {}).get("const"))
    except Exception:
        schema_types[p.name] = None
schema_files = set(schema_types)

# --- reverse check ground truth: message types the spec actually declares -------------
# G4 lesson (2026-07-05): the sim-invented ANCHOR_CHAIN_QUERY carried spec-level duties
# (§9.3 Norm retrieval, evidence_sufficiency coverage) for months without any schema, and
# none of the forward checks above could see it — a `"type": "X"` literal makes no
# reference to check. This closes the class: every message type the sim constructs must
# be declared by some schema's `properties.type.const`, or be an allowlisted convenience.
KNOWN_SCHEMA_TYPES = {t for t in schema_types.values() if t}
SIM_CONVENIENCE_TYPES = {
    # Direct APPEAL_REJECTED message to the appellant is a sim convenience; the canonical
    # records are the claim_anchor / incident_notice action_type values (see Referee.py).
    "APPEAL_REJECTED",
}
TYPE_LIT = re.compile(r"""["']type["']\s*:\s*["']([A-Z][A-Z0-9_]*)["']""")

# --- scan the sim sources -----------------------------------------------------------
# One combined token walker per line: doc labels set the active context; §/Section/S
# tokens record a (section, label) reference under that context.
TOKEN = re.compile(
    r"(RFC-0001|RFC-0002)"                        # 1: an RFC label
    r"|\b(TRANSPORT-BINDING|binding(?=\s*§))\b"   # 2: transport-binding doc ("TRANSPORT-BINDING" or the "binding §N" idiom; bare "binding" as a noun is not a doc ref)
    r"|§(\d+(?:\.\d+)*)"                           # 3: §N.M
    r"|Section\s+(\d+(?:\.\d+)*)"                  # 4: Section N.M
    r"|(?<![\w/])S(\d+\.\d+)(?![\d])",             # 5: SN.M (e.g. "RFC-0001 S9.5")
    re.IGNORECASE,
)
SCHEMA_REF = re.compile(r"schemas/([a-z0-9_]+\.json)")

sec_errors, sec_warns, std_errors, schema_errors, type_errors = [], [], [], [], []
review_secs, review_schemas = [], []   # resolved refs for the human-review pass

sources = (sorted(SIM_DIR.glob("*.py"))
           + sorted(SIM_DIR.glob("classes/*.py"))
           + sorted(SIM_DIR.glob("scenario_actor/*.py")))

for src in sources:
    rel = src.relative_to(SIM_DIR)
    for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
        where = f"{rel}:{lineno}"
        ctx   = line.strip()
        # section references (label-aware walk)
        label = None   # active doc context within this line
        for m in TOKEN.finditer(line):
            if m.group(1):
                label = m.group(1).upper()
                continue
            if m.group(2):
                label = "BINDING"
                continue
            num  = m.group(3) or m.group(4) or m.group(5)
            rdoc = None    # the doc this ref resolves to (for the review pairing)
            if label in ("RFC-0001", "RFC-0002", "BINDING"):
                if num in sections[label]:
                    rdoc = label
                elif any(num in sections[d] for d in sections):
                    sec_warns.append((where, f"§{num} labelled {label} but not found there", ctx))
                else:
                    sec_errors.append((where, f"§{num} ({label})", ctx))
            else:
                in0001, in0002 = num in sections["RFC-0001"], num in sections["RFC-0002"]
                if in0001 and in0002:
                    sec_warns.append((where, f"§{num} ambiguous (both RFCs); add an RFC-000X label", ctx))
                    rdoc = "BOTH"
                elif in0001 or in0002:
                    rdoc = "RFC-0001" if in0001 else "RFC-0002"
                else:
                    sec_errors.append((where, f"§{num}", ctx))
            if rdoc:
                title = (f'{titles["RFC-0001"].get(num, "?")} | {titles["RFC-0002"].get(num, "?")}'
                         if rdoc == "BOTH" else titles.get(rdoc, {}).get(num, "?"))
                review_secs.append((where, num, rdoc, title, ctx))
        # STD references
        for n in STD_TOK.findall(line):
            std = std_key(n)
            if std not in known_stds:
                std_errors.append((where, std, ctx))
        # schema references
        for name in SCHEMA_REF.findall(line):
            if name not in schema_files:
                schema_errors.append((where, f"schemas/{name}", ctx))
            else:
                review_schemas.append((where, name, schema_types.get(name), ctx))
        # reverse check: constructed message types must have a declaring schema
        for t in TYPE_LIT.findall(line):
            if t not in KNOWN_SCHEMA_TYPES and t not in SIM_CONVENIENCE_TYPES:
                type_errors.append((where, f'"type": "{t}" has no declaring schema', ctx))

# --- report -------------------------------------------------------------------------
def dump(title, rows):
    print(f"\n{title}: {len(rows)}")
    for where, what, ctx in rows:
        print(f"  {where}  ->  {what}")
        print(f"      | {ctx}")

print("=== sim reference check ===")
print(f"specs: RFC-0001 ({len(sections['RFC-0001'])} sections), "
      f"RFC-0002 ({len(sections['RFC-0002'])} sections), "
      f"{len(known_stds)} STDs (defined in norms/{NORMS_FILE.name}), {len(schema_files)} schemas")
print(f"scanned: {len(sources)} sim source files + {len(_spec_sources)} spec/schema files (docs<->norms STD pass)")

errors = sec_errors + std_errors + std_doc_errors + schema_errors + type_errors
if sec_errors:    dump("ERROR  unresolved §section refs (in NO known spec)", sec_errors)
if std_errors:    dump("ERROR  unknown STD refs", std_errors)
if std_doc_errors: dump("ERROR  STD refs in specs/schemas with no norms definition", std_doc_errors)
if schema_errors: dump("ERROR  missing schema files", schema_errors)
if type_errors:   dump("ERROR  message types with no declaring schema (sim-invented?)", type_errors)
if sec_warns:     dump("WARN   ambiguous / mislabelled §section refs (manual check)", sec_warns)

# --- human-review report (gitignored): the topic / message-schema pass --------------
# Existence is mechanical (above). This file pairs each resolved reference with the
# heading title / schema type it points to, so a human can confirm the cited section or
# schema actually matches what the comment claims (which no mechanical rule can judge).
review_path = TOOLS_DIR / "ref_review.txt"
out = [
    "# ref_review.txt - generated by sim/tools/check_refs.py (gitignored).",
    "# Existence is checked mechanically (console output). This is the topic pass:",
    "# eyeball that each cited section/schema matches what the comment actually claims.",
    "",
    f"== section references ({len(review_secs)}) - does the heading title fit the comment? ==",
]
for where, num, doc, title, ctx in review_secs:
    out.append(f'{where}  §{num} [{doc}]  "{title}"')
    out.append(f"    {ctx}")
out += ["", f"== schema references ({len(review_schemas)}) - does the message type fit the cited schema? =="]
for where, name, const, ctx in review_schemas:
    out.append(f"{where}  schemas/{name}  type={const}")
    out.append(f"    {ctx}")
review_path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"[review] {len(review_secs)} section + {len(review_schemas)} schema refs -> sim/tools/{review_path.name} (gitignored, for manual topic check)")

print()
if errors:
    print(f"[FAIL] {len(errors)} error(s), {len(sec_warns)} warning(s).")
    sys.exit(1)
print(f"[OK] no broken references. {len(sec_warns)} warning(s) for manual review.")
sys.exit(0)
