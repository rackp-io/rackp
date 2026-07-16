# RACK Protocol Reference Simulation

An executable, single-process simulation of the RACK Protocol. Each scenario drives the
protocol agents (Referee, Actor, Claimant, Keeper) through a message flow and asserts the
expected outcome, so the suite doubles as a behavioral specification and a regression check.

## Layout

- `classes/` — protocol agents and the in-process message bus (`World`): `Referee`, `Actor`,
  `Claimant`, `Keeper`, plus `Claim`, `Message`, `Hasher`.
- `scenario_actor/` — adversarial / variant Actors (liar, replay, selective, …) used by edge scenarios.
- `base_01_*.py` … `base_11_*.py` — happy-path and core protocol flows.
- `edge_01_*.py` … `edge_12_*.py` — deviation cases (falsified evidence, timeouts, abandonment, …).
- `tools/check_refs.py` — cross-checks every `§section` / `STD-NNN` / `schemas/*` reference in
  the sim against RFC-0001, RFC-0002, TRANSPORT-BINDING.md and the schema files.

## Setup

The only third-party dependency is `jsonschema` (used by the transport-binding validation
path); everything else is the Python standard library. Python 3.12 is recommended.

Using [uv](https://docs.astral.sh/uv/), from the repo root:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r sim/requirements.txt   # Windows
# uv pip install --python .venv/bin/python -r sim/requirements.txt          # macOS / Linux
```

Using the standard library, from the repo root:

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -r sim/requirements.txt                 # Windows
# .venv/bin/python -m pip install -r sim/requirements.txt                    # macOS / Linux
```

The virtual environment lives at the repo root, not inside `sim/`, so `tools/check_refs.py`
does not scan the installed packages.

## Running

Each scenario is standalone. Run it from `sim/` with the venv's interpreter:

```sh
../.venv/Scripts/python base_01_basic.py     # Windows
# ../.venv/bin/python   base_01_basic.py      # macOS / Linux
```

A scenario prints its message trace and a final `[OK] …` line on success; a failed assertion
raises and the process exits non-zero. To run the whole suite, loop over the scenario files,
e.g. (bash):

```sh
for f in base_*.py edge_*.py; do ../.venv/bin/python "$f" > /dev/null || echo "FAIL $f"; done
```

## Reference checker

```sh
../.venv/Scripts/python tools/check_refs.py
```

It reports any unresolved `§section` / `STD-NNN` / `schemas/*` reference (exiting non-zero if
found) and regenerates `tools/ref_review.txt` — a human-review dump pairing each reference
with the heading it resolves to, for topic-level checks the machine cannot make (a section
number that is valid but points to the wrong topic). That file is regenerated each run and is
gitignored.
