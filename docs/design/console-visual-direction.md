# Design Brief: Console Visual Direction ("Garnet")

**Status:** Draft — proposed, not yet accepted
**Owner:** Project creator
**Target phase:** Console Foundation / Update Discovery and Console Controls

## User Problem

The Console's current styling ([console.css](../../image-builder/sovereign/appliance/console/assets/console.css))
is dark-only, uses a background gradient and `backdrop-filter: blur`, and
defines its palette as raw hex values with no light-mode option and no
documented semantic mapping. There is no reusable token system, so every new
Console surface (Update Discovery, the 01.2 conversation UI) would either
copy that ad-hoc palette forward or invent its own.

## Users and Context

Same as [console-health.md](console-health.md): a household operator viewing
Console on a trusted LAN, desktop or mobile, in whichever OS theme they
already use.

## Desired Outcome

A single documented token system — stone neutrals plus a garnet accent, full
light/dark semantic mappings, `--sv-*` custom properties — that the shipped
Console (today: Health) and future Console surfaces (Update Discovery,
01.2's conversation UI) all draw from, replacing the current one-off palette.
Flat surfaces, no gradient or backdrop blur, both color schemes, zero
external resources.

The proposed reference lives at
[console-design-system-reference.html](console-design-system-reference.html)
— a static, dependency-free page (open directly in a browser, no build
step) covering the palette, typography (Hanken Grotesk / JetBrains Mono,
with the machine-facts-in-mono convention), the Core mark, and mocked-up
Console screens (first-run, Health, sign-in). It is reference documentation
only; nothing in the appliance image changes until a follow-up
implementation PR consumes it.

Two of the mocked-up screens (Chat, Home Assistant) additionally preview
longer-term assistant-vision capabilities (voice, Home Assistant device
control) that are explicitly out of scope for milestone 01.2 — see that
reference's own screens section for the boundary. They are included for
visual-direction continuity, not as a claim that those capabilities ship
with the token system.

## Scope

- Primitive and semantic color tokens, light and dark
- Typography tokens and the mono-for-machine-facts convention
- Spacing, radius, motion, and shadow primitives
- The Core mark (SVG, three preview sizes)
- Documented garnet-vs-danger adjacency rule (danger stays a bright, pure
  red — never darkened toward the garnet accent)

## Non-Scope

- Replacing `console.css` itself (separate implementation PR)
- Real exported icon assets (favicon, apple-touch-icon) — the reference
  only has inline preview SVG at three sizes
- Any capability, screen, or interaction not already committed in
  [console-health.md](console-health.md) or the 01.2 roadmap
- Hardware qualification (only required once a restyle actually ships)

## Experience Requirements

Same non-negotiables as [console-health.md](console-health.md#experience-requirements):
no external fonts/scripts/resources, reduced-motion respected, keyboard and
screen-reader accessible, calm and legible on small and large screens.

## States and Failure Cases

N/A — this brief covers tokens and a mark, not a stateful interface. States
are the responsibility of each Console surface that consumes the tokens.

## Accessibility

- Computed contrast for every semantic text/surface pairing: all pass WCAG
  AA except `text-muted`/`text-subtle`, which originally read 3.84:1 and
  2.38:1 (light) / 6.32:1 and 2.49:1 (dark) against their worst-case
  surface — below the 4.5:1 floor that applies to the machine-fact/caption
  content those tokens actually carry (11–13px, not exempt "large text").
  Fixed in the reference by repointing both tokens to the lightest stone
  step that clears AA per theme (`stone-600` light, `stone-400` dark,
  unchanged from the existing `text-muted` dark value). No stone-ramp step
  exists between "fails AA" and "reads as primary text," so `text-muted`
  and `text-subtle` are now the same color in both themes — there isn't
  room for a third, lighter, AA-compliant text tier at this hue/saturation.
  A real third tier would need either a new primitive off this hue path or
  restricting `text-subtle` to non-text/decorative use only.
- `prefers-reduced-motion: reduce` disables transitions, matching the
  existing `console.css` behavior.
- Status is conveyed through icon/text, not color alone, consistent with
  `console-health.md`'s accessibility requirements.

## Privacy and Trust

No change from `console-health.md` — this brief only affects visual
presentation, not what data any Console surface exposes.

## Constraints

- All assets ship in the image; no build step for the Console itself.
- Nginx remains the sole LAN listener; this brief does not touch routing.
- Any restyle of the shipped Health console is a change to an already
  **Accepted** design (`console-health.md`) and, once implemented, needs
  the same real-hardware qualification as the rest of Console per
  `CONTRIBUTING.md`'s hardware-qualification rule.

## Acceptance Criteria

- Project owner accepts the palette, typography, and mark direction.
- A follow-up implementation PR extracts the tokens into a real
  `tokens.css` shipped in the appliance image and restyles `console.css`,
  `console.js`, and `index.html` to match.
- That follow-up PR is hardware-qualified on Raspberry Pi before being
  considered done.

## Open Questions

- Should `tokens.css` live under `image-builder/sovereign/appliance/console/assets/`
  alongside the files it replaces, or somewhere shared if a future Console
  surface (e.g. the 01.2 conversation UI) is served from a different route?
- Does the garnet accent read correctly against every existing status color
  (warning/success/info), or only against error, which is the one pairing
  explicitly documented in the reference?
