"""`python -m backend` 진입점."""

import asyncio

from backend.orchestrator import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료합니다.")
