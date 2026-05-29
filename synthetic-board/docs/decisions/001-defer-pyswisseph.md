# Decision 001: Defer pyswisseph to optional dependency

**Date:** 2026-05-29
**Status:** accepted
**Context:** pyswisseph requires a C compiler (gcc/build-essential) to build from source. The build environment lacks build-essential and sudo access. pyswisseph is specified in the stack for natal chart computation in the persona-build pipeline (`tools/build_persona.py`), which is noted as "to be implemented" in docs/04-personas.md. The three MVP persona files already contain pre-computed chart signatures in their YAML frontmatter. No MVP runtime code calls pyswisseph.
**Decision:** Move pyswisseph from core dependencies to `[project.optional-dependencies.chart]`. The MVP installs without it. The persona-build tool (post-MVP) will require `pip install sboard[chart]`.
**Alternatives considered:** (1) Pre-build a wheel — adds CI complexity for a dependency no MVP code uses. (2) Skip it entirely — loses the documented intent. Optional dependency preserves intent without blocking the build.
**Consequences:** `tools/build_persona.py` (when implemented) must import pyswisseph conditionally or declare the `chart` extra. No impact on Tasks 1-10.
