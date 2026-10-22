"""Start the map server: python serve.py, then open the address it prints."""
import uvicorn

from astrum import kernels
from astrum.app import create_app
from astrum.config import load_config

if __name__ == "__main__":
    cfg = load_config()
    print(f"Invictus: Astrum on http://{cfg['server']['host']}:{cfg['server']['port']}")
    print(kernels.status())
    uvicorn.run(create_app(cfg, sim="process", run_ahead=cfg["sim"]["run_ahead"]), host=cfg["server"]["host"], port=cfg["server"]["port"], log_level="warning")
