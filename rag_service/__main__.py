from __future__ import annotations

import argparse

from rag_service.config import load_config
from rag_service.doctor import run_doctor


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis local RAG service")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "doctor"])
    args = parser.parse_args()

    if args.command == "doctor":
        checks = run_doctor()
        for check in checks:
            status = "OK" if check.ok else "WARN"
            print(f"{status:4} {check.name}: {check.detail}")
        return

    config = load_config()
    import uvicorn

    uvicorn.run("rag_service.api:app", host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()
