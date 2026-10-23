"""Start the map server: python serve.py, then open the address it prints. The web process logs who
connects, signs in, acts in a lobby and gives an order, to the console and to [server] log."""
import logging
from pathlib import Path

import uvicorn

from astrum import kernels
from astrum.app import create_app
from astrum.config import ROOT, load_config

if __name__ == "__main__":
    cfg = load_config()
    path = ROOT / cfg["server"]["log"]
    path.parent.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("astrum.web")
    log.setLevel(logging.INFO)
    for h in (logging.StreamHandler(), logging.FileHandler(path, encoding="utf-8")):
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    print(f"Invictus: Astrum on http://{cfg['server']['host']}:{cfg['server']['port']} (health: /api/health, log: {cfg['server']['log']})")
    print(kernels.status())
    uvicorn.run(create_app(cfg, sim="process", run_ahead=cfg["sim"]["run_ahead"]), host=cfg["server"]["host"], port=cfg["server"]["port"], log_level="warning")
