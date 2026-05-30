# Decision 008: v2 chart-grounding relaxation (Bezos, Ogilvy, Torvalds)

**Date:** 2026-05-30
**Status:** accepted
**Context:** The v1 chart-pipeline rule (docs/04-personas.md §3.1) admits only **AA**
and **A** Rodden-rated figures as chart-grounded seats; lower ratings fall back to
synthetic. v2 adds four figures. Two were known at planning time to lack reliable
birth times (Bezos, Ogilvy); a third (Torvalds) was flagged "Rodden A — verify."

**Decision:** Relax the AA/A-only rule in v2, **with explicit acknowledgment**, for
figures whose birth time is undocumented. Such seats:
- use a **noon chart** (`birth.time: "12:00"`, `time_known: false`),
- **omit the ascendant** (`chart_signature.ascendant: null`) and any time-dependent
  points (no MC/houses),
- carry `rodden_rating: "X"` with a `rodden_source` note,
- lean on the figure's **documented archetype** in the Markdown body rather than
  chart-specific traits (the body is the load-bearing steering, not the chart).

The chart remains only a diversity-forcing seed (§3); the behavioral steering is
the worldview vector and the body, neither of which depends on a precise time.

**Who is relaxed:**

| Seat | Figure | Rodden | Why |
|---|---|---|---|
| visionary | Jobs | **AA** | Birth certificate; full chart, ascendant Virgo. *Not* relaxed. |
| growth-advisor | Bezos | **X** | Birth time unknown; noon chart. Relaxed (planned). |
| marketing | Ogilvy | **X** | Birth time unknown; noon chart. Relaxed (planned). |
| technical | Torvalds | **X** | **Verified** — relaxed after the fact (see below). |

**Torvalds verification (the "expanded" part).** The plan listed Torvalds as
"Rodden A — verify against astrodatabank." Verification on 2026-05-30:
- astro.com Astrodatabank — page gated, no data retrievable.
- astrotheme.com/astrology/Linus_Torvalds — states **"Date without time of birth …
  arbitrarily calculated for noon"**; no Rodden rating given.
- astro-charts.com — birth time **missing**.

No AA or A surfaced; only an untimed (effectively **X**) record. Per discipline
rule 1, Torvalds is **downgraded to a noon chart** (Sun Capricorn, Moon Leo,
ascendant null, `time_known: false`, `rodden_rating: X`) and **added to this
decision's relaxed list**. So three of the four new chart-grounded seats are
noon-chart figures; only the Visionary (Jobs, AA) has a confirmed time.

**Note on noon-chart moon/element/modality.** For the three X-rated figures, the
Sun sign is unambiguous from the date; the Moon and dominant element/modality are
**noon-chart approximations** (the Moon can change sign within a day), recorded as
archetype seeds, not precision claims. They were taken from public chart sources
where available (Torvalds: Moon Leo) and otherwise chosen to fit the documented
archetype. This is exactly the relaxation this decision authorizes.

**Alternatives considered:** (1) Make Bezos/Ogilvy/Torvalds **synthetic** (chart-free)
per the strict v1 rule — rejected; their documented archetypes are strong and the
chart is only a seed, so a noon chart plus a sharp body loses nothing material.
(2) Invent a plausible birth time to keep an "A" — rejected as dishonest; an
unknown time is recorded as unknown.

**Consequences:** v2 has four chart-grounded new seats, three on noon charts,
honestly flagged `X`/`time_known: false`. The diversity check and the body-quality
(compression) discipline are unaffected — both are independent of birth time.
