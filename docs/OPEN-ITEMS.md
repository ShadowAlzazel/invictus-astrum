# Open items

What waits on the owner's answer, and what has been answered. An item leaves "Waiting" for
"Answered" with its date and the answer, in the same commit as whatever the answer changes.
Ours to build is in `docs/REFACTORS.md` (by number) and `docs/COMBAT.md` (Open).

## Waiting on the owner

| # | Question | As it is today | Where |
|---|---|---|---|
| 1 | **The spine against light.** With the wreck rule (blind and no radiators is out), light decides a battle: 4 spinal salvo orders in LF-1's Venus action at 30 s, none in TF-2's (716 before the rule). Should the spine matter more? | The rule stands. Undo: drop the `saw` clause in `Systems.disabled`. | `astrum/systems.py`, COMBAT.md (the Venus action) |
| 2 | **Where a hit lands.** Her silhouette and attitude by basic shapes from her class's layout, in place of shares by kind; light on radiators by her profile and angle; her crew (§8.2) and prompt upset (§8.5). | A channel lands on a kind of system by its share of her (TEMPORARY). | `data/ships/rules.toml` [damage.share], REFACTORS 24 |
| 3 | **The damage figures.** Hit points by rate, the citadel's factor, two radiators a ship. | 15,000 / 5,000 / 3,000 / 2,000 MJ (line, frigate, auxiliary, unrated); citadel 2x; 2 radiators (all TEMPORARY). | `data/ships/rules.toml` [damage], `astrum/systems.py` RADIATORS |
| 4 | **Damaged, disabled, destroyed told apart.** What repair and salvage make of each. | Alike in the simulation: all out. | COMBAT.md, REFACTORS 26 |
| 5 | **A dazzled sensor.** Its sweep blind a while behind its shutter. | Said by the dwell, not done. | `astrum/optics.py` |
| 6 | **How hard she burns into a pass,** as a profile's setting ("the pass is expensive", 24 October). | Half the way at her cruise g. | `data/profiles.toml`, COMBAT.md |
| 7 | **The lost node's wait.** | `wait_s = 600`, TESTING (root and Ballistic orders). | `data/profiles.toml` |
| 8 | **Projectiles' figures.** Mass, g, burn time, payload, burst radius, seeker; whether point defence sees only what the sweep sees. | Launched and logged, not flown. | COMBAT.md, REFACTORS 23 |
| 9 | **A battery with no cycle in its data.** | `cycle_s = 60`, TEMPORARY. | `data/minerva.toml` |
| 10 | **The heat figures.** What a ship sheds with her wings folded; how fast her store empties spread. | `cold_share = 0.01`, `recover = 4`, TEMPORARY. | `data/ships/rules.toml` |
| 11 | **Old Forest and SALTICIDAE figures** not yet stated: aim (YGGDRASIL, HOLZWEIBER, DRYAD), quiet load (those and SALTICIDAE), whether a DRYAD has wings. | Marked `est`, TEMPORARY, each with a note. | `data/ships/classes/` |
| 12 | **The salvo's estimates,** to check against the canon when it gives them. | `size_k` 0.479 (TELVM §1.3.4's three sizes), `muzzle_share` 0.25 (gives TORMENTA §4.8's table), `station_share` 0.9. | `data/ships/rules.toml` [salvo], `data/minerva.toml` |
| 13 | **TF-2's callsigns.** `tools/formation_tf2.py` writes over them. | Not to be run again before the owner's names are in. | `tools/formation_tf2.py` |

## Answered

| Date | Question | Answer |
|---|---|---|
| 28 October | Hold fire's readiness: the data had III, the 25 October note said I. | III (the note was a typo). The data stands. |
| 28 October | The battle tick by default. | 30 s, among 10, 30, 60, 300, 600 (`data/minerva.toml`). |
| 28 October | Does a map burn over a go-to clear it? | Yes: clearer to the player (`3103c80`). |
| 27 October | Merged salvos at longer ticks: one draw or many? | A tick's cycles at once, each salvo its own draw; canon figures are bases, as close as can be. |
| 27 October | Damage. | By system, in lists by state: OPERATIONAL, then DAMAGED, DISABLED, DESTROYED; only what is operational is read. |
| 25 October | Stance against profile. | One automaton, MINERVA: ReadyStances are its entry and exit, the profile its engagement; the CAPTAIN runs it. Hold ground the default; TF-2 on return fire. |
