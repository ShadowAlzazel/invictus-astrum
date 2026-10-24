"""The ship AI's automata (astrum/shipai): read from data, run per ship, and the readiness and
endings the AI gives by them."""
import numpy as np
import pytest

from astrum.config import ROOT
from astrum.orders import KIND
from astrum.shipai import Machine, load_automata
from test_combat import _ai, _app, _drive, _hunt


def test_the_default_watches_goes_to_quarters_on_a_threat_and_stands_down_after_a_quiet_day():
    auto = load_automata(ROOT / "data" / "automata.toml")["default"]
    m = Machine(auto, 0.0)
    assert (m.state.id, m.state.quarters, m.pinging) == ("watch", 3, False)
    assert m.step(600, False, False, True) is None                       # nothing near her: she watches
    assert m.step(1200, True, False, True).id == "gq" and m.pinging and m.state.engage
    assert m.step(1200 + 23 * 3600, False, False, True) is None          # quiet, but not for a day
    assert m.step(1200 + 24 * 3600, False, False, True).id == "watch" and not m.pinging
    assert m.step(1200 + 25 * 3600, False, True, False).id == "attack" and m.state.quarters == 2
    assert m.step(1200 + 26 * 3600, False, False, True).id == "watch"
    m.back_to(1800)                                                       # set back: as it stood then
    assert (m.state.id, m.since(), len(m.history)) == ("gq", 1200, 2)


def test_an_automaton_written_wrong_is_refused(tmp_path):
    f = tmp_path / "a.toml"
    f.write_text('[automaton.default]\nname = "x"\nstart = "a"\nquiet_h = 0\n'
                 '[automaton.default.state.a]\nquarters = 4\nsensors = "loud"\non = { boom = "b" }\n')
    with pytest.raises(ValueError) as e:
        load_automata(f)
    for x in ("quiet_h", "quarters is 1, 2 or 3", "sensors is active or passive", "no event 'boom'", "goes to 'b'"):
        assert x in str(e.value)


def test_a_threat_seen_sends_her_to_general_quarters_pinging_and_only_then_she_engages(tmp_path):
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    assert _hunt(c, t) == 200
    _drive(c, t, t + 3600)
    B, i = fleet.book, fleet.c.row["tf3-es-1"]
    mine = [(float(B.at[e]), int(B.kind[e])) for e in B.queue[B.ai[B.queue]] if B.ship[e] == i]
    kinds = [k for _, k in mine]
    assert kinds[:3] == [KIND["quarters"], KIND["active"], KIND["goto"]] and len({a for a, _ in mine[:3]}) == 1
    assert fleet.c.quarters[i] == 1 and fleet.pinging(t + 3600)[i]
    far = [x for x in _ai(fleet) if x[1].startswith("kiki")]            # nothing near them: they do not know of it
    assert not far


def test_an_engagement_ends_as_her_profile_says(tmp_path):
    """C pass: a burn through where the target will be, and she does not turn on it again (the next
    she passes, each once); A keep:
    an engage with her post to come back to."""
    c, world = _app(tmp_path)
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    c.post("/api/profiles", json={"player": "arcvs", "name": "Raid", "stance": "aggressive", "end": "pass",
                                  "targets": ["hostile", "unknown"], "range": {}})
    assert c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": "tf3-es-1", "t": t,
                                      "profile": "raid", "stance": "aggressive"}).status_code == 200
    c.post("/api/profiles", json={"player": "arcvs", "name": "Wall", "stance": "aggressive", "end": "keep",
                                  "targets": ["hostile", "unknown"], "range": {}})
    assert c.post("/api/order", json={"scenario": "sol-demo", "player": "arcvs", "unit": "tf3-es-2", "t": t,
                                      "profile": "wall", "stance": "aggressive"}).status_code == 200
    _drive(c, t, t + 6 * 3600)
    B = fleet.book
    of = lambda sid: [B.of(e) for e in B.queue[B.ai[B.queue]] if fleet.c.ids[B.ship[e]] == sid]
    passes = [g for g in of("tf3-es-1") if g.burn]
    on = [g.burn["pass"] for g in passes]
    assert on[0] == "ghost-1" and len(set(on)) == len(on) and all(g.burn["label"].startswith("pass") for g in passes)
    assert not any(g.target.get("engage") for g in of("tf3-es-1"))
    held = [g for g in of("tf3-es-2") if g.target.get("engage")]
    assert held and held[0].target["resume"]["target"]["label"].startswith("back to")
    _drive(c, t + 6 * 3600, t + 34 * 3600)
    i, j = fleet.c.row["tf3-es-1"], fleet.c.row["ghost-1"]
    pos = [fleet.positions_at(x) for x in np.arange(t + 30 * 3600, t + 34 * 3600, 60.0)]
    miss = min(np.linalg.norm(p["tf3-es-1"] - p["ghost-1"]) for p in pos)
    assert miss < 0.25 * fleet.c.spec[i].engage_km * 1e3                  # through her, within her reach (ai.PASS_MISS) ...
    assert np.linalg.norm(fleet.c.v[i] - fleet.c.v[j]) > 1e5              # ... and on


def test_the_map_is_told_her_readiness(tmp_path):
    """Her quarters at the picture's moment (off the book, so a re-fly or a run-ahead does not
    change them): in her side's frame when they change, and in her engagement with her
    automaton's state and her weapons."""
    import json
    c, world = _app(tmp_path)
    host = c.app.state.sim.host
    fleet = world.fleet(world.scenarios["sol-demo"])
    t = fleet.t0 + 600
    _hunt(c, t)
    _drive(c, t, t + 3600)
    q = lambda T: json.loads(host.frame({"system": "sol", "t": T, "scenario": "sol-demo", "view": "arcvs"},
                                        conn=("arcvs", "q")))["ships"].get("tf3-es-1", {}).get("quarters")
    assert q(t) == 3 and q(t + 3600) == 1
    e = c.get("/api/engagement/sol-demo/tf3-es-1", params={"player": "arcvs", "t": t + 3600}).json()
    assert (e["combat"]["quarters"], e["combat"]["state"], e["automaton_name"]) == (1, "General quarters", "Standing watch")
    assert [w["id"] for w in e["combat"]["weapons"]] and "combat" not in c.get(
        "/api/engagement/sol-demo/tf-3", params={"player": "arcvs", "t": t + 3600}).json()
    assert c.get("/api/engagement/sol-demo/tf3-es-1", params={"player": "arcvs", "t": t}).json()["combat"]["quarters"] == 3
