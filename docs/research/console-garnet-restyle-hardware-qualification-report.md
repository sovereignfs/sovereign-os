# Console Garnet Restyle Hardware Qualification Report

**Date:** 2026-08-11

## Purpose

Verify the Garnet visual direction ([console-visual-direction.md](../design/console-visual-direction.md)) — `tokens.css`, the restyled Health page, and new Chat/Home Assistant/Activity preview routes — actually renders correctly on physical Raspberry Pi 5 hardware behind the real Nginx proxy, not just against a local mock server.

## Method

Deployed onto the device (running the real, shipped `0.1.0-proof.3`, `committed`) without a full update transaction, matching this project's established manual-qualification pattern (see [console-authentication-hardware-qualification-report.md](console-authentication-hardware-qualification-report.md)):

1. Recorded SHA-256 checksums of every live file about to be modified (`index.html`, `console.css`, `console.js`, `nginx/sovereign.conf`) and pulled their exact bytes to a local backup, verified byte-identical to the device before any change.
2. Staged the new files (`tokens.css`, restyled `console.css`/`index.html`/`console.js`, and `nginx/sovereign.conf` with three new route blocks) into the `sovereign` user's home directory — no root needed for this step, since the live files are world-readable.
3. Two deploy passes, each run interactively by the device owner via `sudo install -o root -g root -m 0644 ...` (never a password typed to or handled by the agent):
   - Pass 1: `tokens.css`, restyled `console.css`, restyled `index.html` (Health page only).
   - Pass 2: adds the pill/routing logic in `console.js`, the Chat/Home Assistant/Activity preview sections in `index.html`, and the corresponding `nginx/sovereign.conf` routes — validated with `nginx -t` before `systemctl reload nginx`, matching the ADR-0007 precedent.
4. Verified live checksums matched the staged files exactly after each pass (byte-for-byte, not just "looks right").

## Result

- `GET /console/`, `/console/health/`, `/console/chat/`, `/console/home/`, `/console/activity/` all `200` through the real Nginx, each carrying the full CSP (`default-src 'none'; connect-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`).
- `GET /console/chat`, `/console/home`, `/console/activity` (no trailing slash) all `308` to their slashed form, matching the existing `/console/health` precedent.
- `GET /console/assets/tokens.css`, `/console/assets/console.css`, `/console/assets/console.js` all `200`.
- `GET /api/v1/health` returns real, live, healthy data from the device (Raspberry Pi 5 Model B Rev 1.1, real temperature/memory/storage, `192.168.50.10`) — confirms the restyle didn't touch the health service's own contract.
- `GET /dns/admin/` still `302`s (ADR-0010's sign-in gate intact) and `dig @sovereign.local` still resolves — Pi-hole and DNS are unaffected by the Console change.
- `nginx -t` passed on the real device config before every reload; no `systemctl --failed` units afterward.
- Visually confirmed via a local mock server serving the exact same asset bytes deployed to the device (Health, Chat, Home Assistant, and Activity pages; light and dark via `prefers-color-scheme`; the sign-in popover open state; the unavailable/error status state) — direct in-browser verification against `sovereign.local` itself was blocked by this session's Browser-pane per-site approval gate, which did not clear even after explicit user confirmation in chat; the device owner separately confirmed the live page visually via their own browser.

## Cleanup

**Not yet done.** Unlike prior qualification campaigns in this project, this deployment has been left live on the device at the project owner's request, pending further review of the design (`"It requires some improvements, but I would like to commit, push and create PR at this point. We can make those improvements later"`). The original pre-qualification bytes for every modified file (including `nginx/sovereign.conf`) are preserved at `~/console-restyle-qual/backup-original/` on the device, and a tested revert script (`~/console-restyle-qual/hw-qual-revert-v2.sh`) is staged there — it restores every file to its exact original checksum and reloads Nginx after validating the restored config. Run it whenever the device should return to the shipped `0.1.0-proof.3` Console.

## Recommendation

The restyle and the three new preview routes work end-to-end on real hardware, including the part most likely to hide a bug in a local-only check — Nginx actually serving the new `location` blocks with the right CSP, and `nginx -t` actually validating the edited config before anything reloads. Remaining before this ships through a real release:

- This has only ever been deployed manually for qualification; it has never gone through an actual signed release install.
- No font files are bundled — Hanken Grotesk/JetBrains Mono fall back to system fonts on-device, per the design brief's own documented approach, not a defect.
- The Chat/Home Assistant/Activity pages are static, non-interactive design previews only (explicitly labeled as such in-page); they have no backend and are not wired to any capability.
- The device-visible design still needs another pass per the project owner's own review before being considered final.
