# 08 — Roadmap

This is not a plan to execute. This is a list of what becomes possible *if and only if* the A/B gate fires. If the gate fails, this file is archived and the project ends.

## Phase 1 — MVP (current)
- One meeting type: Idea Screen.
- Three seats: Operator-CEO (Grove), Devil's Advocate (Munger), Outsider (synthetic).
- CLI only.
- A/B test against single-LLM baseline.

## Phase 2 — Cast expansion (post-gate)
Triggered only by Phase 1 pass.
- Add 4 seats: Visionary, CFO, CTO, CMO.
- Build their persona files (chart-grounded).
- Update the diversity check to handle 7 seats.
- Re-run A/B with 7-seat Idea Screen against 3-seat board (does adding seats actually help, or does it hurt?).

## Phase 3 — Meeting types
- Pre-Mortem (Klein protocol — assume failure, enumerate causes).
- Red Team Assault (DA leads, find fatal flaw).
- Strategy Review (full board, periodic).
- Capital Decision (CFO weighted higher).
- Post-Mortem (chains to a prior memo, scores kill criteria).

## Phase 4 — Memory and learning
- Activate the semantic memory store. Surface base rates and prior verdicts on related petitions to the seats at IDENTIFIED_REBUTTAL (never before).
- Calibration dashboard: verdict-correct rate, kill-criteria-fired rate, per-seat calibration over time.
- Decide whether to update persona files based on calibration. Default: do not. Frozen personas + calibrated trust is the safer path.

## Phase 5 — Productization
- Web UI.
- Multi-tenant.
- Founder-level persistence (their own boards, their own memos).
- Audit export for investors / advisors.

## Phase 6 — Research
- Model diversity: route seats to different providers (Anthropic / OpenAI / Google) to test whether model diversity adds to persona diversity.
- Adversarial robustness: prompt-injection testing, jailbreak resistance.
- Cross-meeting learning vs frozen personas: which produces better calibration?

## What is NOT on the roadmap
- Astrology branding. The chart is internal infrastructure, never product surface.
- Real-time human-in-the-loop during meetings. Founder submits, founder receives. No mid-meeting interventions.
- Open-sourcing the engine while it has commercial potential. Open-source the *prompt templates and steering files* later if needed for trust.

## The discipline
Phase 2 starts only after Phase 1 wins the gate. Phase 3 starts only after Phase 2 produces a measurable lift over Phase 1. Each phase has its own success criterion, documented before the phase begins. No phase starts on enthusiasm alone.
