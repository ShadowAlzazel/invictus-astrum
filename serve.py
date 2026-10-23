"""Start the map server: python serve.py, then open the address it prints. The web process logs who
connects, signs in, acts in a lobby and gives an order, to the console and to [server] log.

python serve.py --dev [LEVEL] [--side SIDE]: for working on it, on this machine alone, no sign-in:
every browser is config.toml [dev] user, in a lobby of its level (or LEVEL: a level's id, a
scenario's or a system's) already started, and goes straight onto the map; pictures as [dev] says."""
import argparse
import logging
from pathlib import Path

import uvicorn

from astrum import kernels
from astrum.app import create_app
from astrum.config import ROOT, load_config

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="The Invictus: Astrum map server")
    ap.add_argument("--dev", nargs="?", const=True, metavar="LEVEL", help="no sign-in, straight onto a level (else [dev] level)")
    ap.add_argument("--side", help="with --dev: the side played (else [dev] side)")
    args = ap.parse_args()
    cfg = load_config()
    if args.dev:
        cfg["dev"] |= {k: v for k, v in (("level", args.dev), ("side", args.side)) if isinstance(v, str)}
        cfg["server"]["host"] = "127.0.0.1"               # no sign-in: this machine's alone
    path = ROOT / cfg["server"]["log"]
    path.parent.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("astrum.web")
    log.setLevel(logging.INFO)
    for h in (logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")):
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    print(f"Invictus: Astrum on http://{cfg['server']['host']}:{cfg['server']['port']} (health: /api/health, log: {cfg['server']['log']})")
    if args.dev:
        print(f"dev: as {cfg['dev']['user']}, {cfg['dev']['level']} as {cfg['dev']['side']}, pictures {cfg['dev']['pictures']}")
    print(kernels.status())
    uvicorn.run(create_app(cfg, sim="process", run_ahead=cfg["sim"]["run_ahead"], dev=bool(args.dev)), host=cfg["server"]["host"], port=cfg["server"]["port"], log_level="warning")
