# `prune` Timer Unattended-Fire Qualification Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device — same device as every other report in this directory.

**Status:** Confirmed a genuine unattended `sovereign-update-prune.timer`
elapse, closing the one remaining named gap in
[BACKUP_AND_JOURNAL.md](../../update/BACKUP_AND_JOURNAL.md)'s retention
section: "an actual unattended timer-elapsed run has not been separately
observed."

## Method

No action was taken to trigger this — the device had been running normally
since earlier session work, and this was a passive observation of state
already on the device, specifically to avoid the prior gap (every previous
verification of this timer used a manual `systemctl start`).

```console
$ sudo systemctl list-timers sovereign-update-prune.timer --no-legend
Mon 2026-08-10 00:58:51 BST 13h  Sun 2026-08-09 10:05:18 BST 1h 45min ago  sovereign-update-prune.timer sovereign-update-prune.service

$ sudo journalctl -u sovereign-update-prune.service --no-pager -n 50
Aug 09 10:05:18 sovereign systemd[1]: Starting sovereign-update-prune.service - Prune Sovereign backups, releases, and transaction journals beyond retention policy...
Aug 09 10:05:18 sovereign sovereign-update[5371]: {"removed_backups": [], "removed_releases": [], "removed_transactions": [], "status": "pruned"}
Aug 09 10:05:18 sovereign systemd[1]: sovereign-update-prune.service: Deactivated successfully.
Aug 09 10:05:18 sovereign systemd[1]: Finished sovereign-update-prune.service - Prune Sovereign backups, releases, and transaction journals beyond retention policy.

$ journalctl --list-boots -q
0 a7aa3a61ac9e445b94ebf03a0ba0a46e Sun 2026-08-09 09:24:40 BST Sun 2026-08-09 11:50:36 BST
```

## Analysis

`systemctl list-timers`' "last triggered" column is populated from the
*timer unit's* own `LastTriggerUSec`, which only updates when the timer
itself activates its service — a manual `systemctl start
sovereign-update-prune.service` (as every prior qualification pass used)
never touches it. Seeing a real, recent value here is itself evidence this
run was timer-driven, not operator-driven.

The specific timing confirms which path: the unit is `OnCalendar=daily` with
`RandomizedDelaySec=1h`, i.e. the plain schedule should fire once somewhere
in the 00:00–01:00 BST window. The observed run instead landed at 10:05:18
BST — outside that window — but the journal shows the device only booted at
09:24:40 BST that same morning, with no earlier boot in journald's history.
The device was off (or between reboots) through the scheduled midnight
window, missed it, and `Persistent=true` fired the missed run about 41
minutes after boot instead — exactly the documented catch-up behavior
("catches up on boot if a run was missed"). The *next* scheduled fire,
00:58:51 BST, does fall inside the normal window, confirming the timer's
regular schedule is otherwise intact.

`who -b` was tried first and discarded as unreliable for this: it read a
stale boot record (`2026-04-13 20:38`) inconsistent with the device's
actual recent reflash/reboot history, a known failure mode on Raspberry Pi
hardware without a battery-backed RTC (`utmp` can retain a bogus early
boot time recorded before NTP sync corrects the clock, uncorrected
afterward). `journalctl --list-boots`, which timestamps from the journal
itself rather than `utmp`, was used instead and is consistent with every
other timestamp in this report.

The prune run itself removed nothing (`"removed_backups": [],
"removed_releases": [], "removed_transactions": []`) — expected, since
device state was already within the default retention policy's bounds, as
seen previously in the
[prune and trust rotation qualification report](prune-and-rotate-trust-hardware-qualification-report.md).
This report is about confirming the timer fires unattended at all, not
about retention arithmetic, which was already covered there.

## Conclusion

`sovereign-update-prune.timer` fires without operator involvement, via its
`Persistent=true` boot-catch-up path. The plain in-window
(`OnCalendar=daily` + jitter) firing path was not separately caught in the
act this way — it's the same underlying timer mechanism and the next
scheduled fire was confirmed still correctly scheduled inside its window —
but the gap this closes was specifically "has this timer ever fired without
a person running `systemctl start`," and it has.
