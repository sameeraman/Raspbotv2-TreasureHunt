#!/usr/bin/env python3
"""Launch the Ringo web dashboard.

Usage:
    python web_main.py
    python web_main.py --host 0.0.0.0 --port 8080

Open http://localhost:8080 in a browser.
Pages:
  /          — Live log dashboard + session control
  /control   — Remote control: camera, movement, sensors, lights
"""
import argparse
import sys

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Ringo Web Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Hot-reload (dev only)")
    args = parser.parse_args()

    print(f"🌐  Starting Ringo dashboard on http://{args.host}:{args.port}")
    print(f"    Dashboard:    http://localhost:{args.port}/")
    print(f"    Remote ctrl:  http://localhost:{args.port}/control")
    print()

    uvicorn.run(
        "web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",   # suppress uvicorn access logs; Ringo has its own
    )


if __name__ == "__main__":
    main()
