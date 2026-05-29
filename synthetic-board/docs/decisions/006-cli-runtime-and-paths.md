# Decision 006: CLI runtime — service layer, default paths, append-only re-convene

**Date:** 2026-05-29
**Status:** accepted
**Context:** Task 9 wires the two operator-facing commands (`sboard convene`,
`sboard inspect`) over the pipeline built in Tasks 1–8. The HANDOFF specifies the
commands' behaviour ("convene runs the protocol end-to-end and writes the memo to
disk"; "inspect <memo_id> shows the full transcript") but leaves the runtime
plumbing — where the DB lives, what client convene uses, how a repeated convene
behaves — unspecified. These choices are recorded here.

**Decision:**

1. **Service layer.** Orchestration lives in `src/sboard/service.py` (`convene`,
   `load_inspection`, and pure `render_*` helpers); `cli.py` is a thin Typer
   wrapper that only parses args, renders, and maps failures to exit codes. This
   keeps the wiring unit-testable without spinning up Typer and keeps the CLI
   surface trivial.

2. **Default paths, cwd-relative.** `runs/sboard.db` (audit DB), `out/` (memo
   `.md` + `.json`), `personas/` (seat files), seed `42`. All are already covered
   by `.gitignore` (`runs/`, `out/`, `*.db`), and cwd-relative defaults make the
   documented `sboard convene tests/fixtures/...` (run from repo root, as in the
   Makefile) work with no flags. Each is overridable via flag or env var
   (`SBOARD_DB`, `SBOARD_OUT`, `SBOARD_PERSONAS`).

3. **convene uses `MockClient`.** Per HANDOFF §8, tasks 1–9 run against mocks and
   need no API key. `service.convene(..., client=...)` accepts an injected client
   so the real Anthropic client drops in at Task 10 without touching the CLI.

4. **Re-convene is append-only, not an error.** `insert_petition` enforces a
   PRIMARY KEY on `petition_id`, so a naive second convene of the same petition
   would raise `IntegrityError`. Instead the service inserts the petition only if
   absent and always appends a fresh transcript + memo. The petition stays
   immutable (written once); transcripts and memos accumulate. This matches the
   append-only audit discipline (Decision in Task 8) and lets a founder re-run a
   petition to compare meetings.

5. **inspect keys off `memo_id`.** Given a memo_id it loads the memo, then its
   petition and latest transcript via the memo's `petition_id`. Unknown id or a
   missing DB → exit code 1 with a message on stderr; it never creates an empty
   DB on a read.

6. **Source-figure safety.** Both commands render via the existing role-name-only
   formatter, and the transcript only ever contains role-keyed seat ids and file
   hashes — never `source_figure`. A CLI test asserts no source-figure token
   appears in convene or inspect output (HANDOFF §8).

7. **ruff + Typer.** Added `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls
   = ["typer.Argument", "typer.Option"]` so bugbear's B008 (function-call default)
   does not fire on Typer's declarative parameter API.

**Alternatives considered:** (1) Putting orchestration directly in `cli.py` —
rejected; couples logic to Typer and makes unit testing awkward. (2) Treating a
repeated convene as an error — rejected; brittle and hostile to the "run it again"
workflow. (3) Per-Option module-level singletons to dodge B008 — rejected as
non-idiomatic noise; `extend-immutable-calls` is the documented Typer+ruff fix.

**Consequences:** `convene`/`inspect` are fully testable through the real Typer
app against mocks. The `ab` command remains a deliberate stub that exits 2 with a
"Task 10" notice — scope discipline (HANDOFF §7 rule two / §10). The real LLM
client is the only seam Task 10 must add to make convene live.
