# Fleets

One file per fleet, named for its id: a formation tree and its ships, kept apart from any scenario
(`astrum/fleets.py`). A scenario brings a fleet in with `[[fleet]] id = "<id>"`; its units join the
scenario's own, all placed at its start. A level plays a copy of its scenarios and fleets as they
stood when it started, so editing a fleet changes the next start, not a game in progress.

The Fleets screen on the main menu shows every fleet; an admin (`role = "admin"` in
`data/users.toml`, and the `--dev` user) can rename its units and change a ship's hull number or
class there. Edits are written into the file, line by line, so its comments stay.

## A fleet

```toml
[fleet]
id = "luna-classis-1"          # = the file name
name = "Luna Classis I"
faction = "avc"                # data/factions.toml; a unit with no formation above it takes it
system = "sol"                 # where its positions are read: its bodies, the scenario player's bullseyes
notes = "..."
```

## A unit

```toml
[[contact]]
id = "kiki-1"                  # unique across a scenario and every fleet it brings in
callsign = "Kiki"
affiliation = "friend"         # friend, hostile, unknown, neutral; else the formation's above
echelon = "ship"               # ship, flight, group, squadron, flotilla, task-force, classis, armada
formation = "kiki"             # the formation above it, in the same fleet
class = "papilion"             # a ship: a class in data/ships/classes; her symbol and her figures
position = { bullseye = "burn", aer = [0, 0, 2000] }    # or { body = "earth", offset_km = [x, y, z] }
```

A ship may also say:
- `load = "light"`: her ammunition load, one of her class's hull masses (else the heaviest)
- `propellant = 0.8`: the share of her tanks she starts with (else full)
- `mode = "free"`: fly from the start instead of holding station
- `hull_number = "BBC-382"`: her pennant, shown beside her name
- `status = ["cold"]`, `veterancy`, `stance`, `profile`

A formation may say:
- `flag = "<ship>"`: its leader, the ship under it its reports go through to the fleet flagship (else
  the ship it is placed on, else its first ship; `astrum/relay.py`)
- `role = "battle"`: one of `style.toml [formation_role]`; else a word of its callsign gives it
  ("Line Flotilla 1", "Forward Scout 2")
- a `position` of its own, else it stands at the mean of its members

Any unit takes its affiliation, faction, veterancy, stance and profile from the formation above
it, unless it states its own. Holding station is not free: she follows her place in the bullseye's
frame, and her tanks pay for every bit of it that is not an orbit.
