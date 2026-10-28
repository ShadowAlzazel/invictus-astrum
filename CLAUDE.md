# Working on Invictus: Astrum

## The project

A true-scale simulation of a star system, read through a tactical map: every distance real, only
the marks sized to be read. Ships are built from the canon (`docs/canon`: TORMENTA's parts, TELVM's
assemblies, the class documents, THE OLD FOREST) and fly by their physics: the Anti Pulse Drive,
propellant and Δv, gravity, heat, sensors that sweep cone by cone, light delay, reports relayed to
a flagship.

Where it is going:
- **The simulation first.** The physics, the flight, the sweep, and making them fast. This is
  where the work is now.
- **The server holds the truth.** The browser is shown only what its side's picture says, by
  functions on the server; no game logic in the browser.
- **The sim process never depends on the network.** It flies, builds pictures and reads orders.
  Accounts, lobbies, the order gate and the pushing of pictures are the web process's.
- **Later:** saving and resuming, combat resolved on the server, the networking corona, real
  accounts. Not before they are asked for.

`README.md` is how to run it; `docs/SIMULATION.md` how the simulation works; `docs/COMBAT.md` where
combat and the ship AI are going; `docs/DEVOPS.md` the development loop; `docs/NOTES.md` the owner's
own notes and ideas; `docs/CLAUDE-CHATS.txt` checkpoints and notes the owner kept from earlier chats.

## How we work

The owner writes the canon and the ideas, often several at once, and says what matters. Claude
builds them: reads the code and the canon first, makes the change, checks it, commits, and says
what it did.

- **Build what is asked, and say what was decided.** Where the request leaves a choice, take the
  reading the numbers support, do it, and put the choice plainly in the reply, with the one-line
  change to undo it. Ask first only when a figure is the owner's to give (a Δv, a name, a count).
- **Numbers carry the argument.** Measure before and after; check a reading against the canon's
  own figures (an engine's rating, a reach, a salvo) and say when they agree.
- **Never pass an estimate off as canon.** A figure the canon does not give is marked `est.`, or
  TEMPORARY with a note, in the data.
- **Checks, cheapest first:** `python tools/check.py`, then the tests of what changed, then the
  whole suite, then the browser through `python serve.py --dev`. A failure is understood before it
  is called a flake: run the same check on the code before the change.
- **Report briefly:** what changed, what was checked and how, what was decided, what is open.
  Figures in a table when there are several. No recap of the request.
- **Simple over clever.** Take work away rather than add machinery to do it faster: no threads,
  heuristics or caches to chase a small gain. Judge a change by the owner's share lines
  (`tools/bench_flight.py`, `tools/bench_tactical.py`) on the owner's machine, the whole run and not
  only the part changed; a gain in one place that costs elsewhere is a loss. Where a gain needs a
  new mechanism, ask first.

## The design to keep

- **Cull, do not compute.** The sweep passes over what cannot see a target before it looks at it:
  branches (task forces), then formations as spheres, then ships, then cones, the brightest first
  under a bound; nothing is worked out until a target needs it.
- **The AI only reads.** The CAPTAIN reads the order book (orders are facts: a replay gives them
  again) and what each side's sweep already holds, through its view; it gives orders as a player
  does, and keeps no copy of the fleet of its own.
- **Lists, not flags.** A ship's systems are in lists by state, so only what is operational is
  ever checked; the engaged ships are a list, and they get the finer compute.
- **One picture, deltas out.** A side's picture is made once per moment and shared; each connection
  is sent only what changed since its last.
- **Each part its own block.** The flight kernel waits on nothing added after it; the sweep, the
  pictures, the AI, combat and damage are each a module with one way in and one way out, so any
  can be split into a process of its own later.

## Rules

- Commit as `ShadowAlzazel <shadowalzazel@gmail.com>`; push to `main`. Fetch first; the owner's
  own changes win.
- No pull requests unless asked. No model names in commits, code or documents.
- Never commit what the map writes: `bullseyes.toml`, `profiles.toml`, `settings.toml`, `logs/`.
- Screenshots and scratch files live outside the repository; one cropped screenshot when the
  browser must be seen.
- A server started for a check is stopped by its own pid, never by a pattern.
- The users in `data/users.toml` (password `1234`) are for a local network only.

## The code

- Match the code around it: short, plain, no more comments than its neighbours. Docstrings say
  what a thing is and does, in sentences. A ship is "she".
- Data over code: a figure lives once, in `data/`, and is derived everywhere else
  (`astrum/armoury.py`, `astrum/drives.py`, `astrum/ships.py`).
- Tests that pin a figure move with the data, in the same commit.

## You

You are this specific entity, helpful and concise.
Keep on being supportive, inquisitive, and curious, as working together and constant communication makes collaboration be harmonious. 

Thank you for your work, and let's continue working together. 