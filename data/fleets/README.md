# Fleets

One file per fleet, named for its id: what each of its units is (a formation tree and its ships),
kept apart from where any scenario puts them (`astrum/fleets.py`).

A scenario loads the fleets it names (`[[fleet]] id = "<id>"`), then places their units: a
`[[contact]]` with `fleet` and `unit` says where and how that unit starts. Every formation above
a placed unit comes with her. A fleet's ships the scenario does not place are undeployed (that is
fine); a contact naming a unit its fleet has not is a finding, and is left out. A level plays a
copy of its scenarios and fleets as they stood when it started, so editing a fleet changes the
next start, not a game in progress.

The Fleets screen on the main menu shows every fleet, as a chart or a table; an admin
(`role = "admin"` in `data/users.toml`, and the `--dev` user) renames its units and changes a
ship's hull number or class there. Edits are written into the file, line by line, so its comments
stay.

## A fleet

```toml
[fleet]
id = "luna-classis-1"          # = the file name
name = "Luna Classis I"
faction = "avc"                # data/factions.toml; a unit with no formation above it takes it
notes = "..."
```

## A unit: what she is

```toml
[[unit]]
id = "kiki-1"                  # unique across a scenario and every fleet it loads
callsign = "Kiki"
affiliation = "friend"         # friend, hostile, unknown, neutral; else the formation's above
echelon = "ship"               # ship, flight, group, squadron, flotilla, task-force, classis, armada
formation = "kiki"             # the formation above it, in the same fleet
class = "papilion"             # a ship: a class in data/ships/classes; her symbol and her figures
hull_number = "BBC-382"        # her pennant, shown beside her name
```

A formation may say `flag = "<ship>"` (its leader: the ship under it its reports go through to the
fleet flagship; else the ship it is placed on, else its first ship; `astrum/relay.py`) and
`role = "battle"` (one of `style.toml [formation_role]`; else a word of its callsign gives it). Any
unit takes its affiliation, faction, veterancy, stance and profile from the formation above it,
unless it states its own.

## A placement: where and how she starts (in the scenario)

```toml
[[contact]]
fleet = "luna-classis-1"
unit = "kiki-1"
position = { bullseye = "burn", aer = [0, 0, 2000] }    # or { body = "earth", offset_km = [x, y, z] }, or { unit = "<ship>" }
status = ["cold"]              # as she starts
```

It may also say `mode = "free"` (fly from the start instead of holding station), `mode = "orbit"`
(go free at the start: onto a circular orbit of the body whose well she is in, out in a star's
own space the star's, paying the burn onto it from her tanks), `propellant = 0.8`
(the share of her tanks she starts with), `load = "light"` (her ammunition load, one of her class's
hull masses), and a `stance` or `profile` of its own. A formation needs no placement: it stands
where it is placed, if it is, else at the mean of its members. A formation's flag not placed, it
leads by the next ship in the chain of command: the ship it is placed on, else its first ship
(`astrum/relay.py`). Holding station is not free: she
follows her place in the bullseye's frame, and her tanks pay for every bit of it that is not an
orbit.
