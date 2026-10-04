"""Run with `uv run python -m app.seed [source.csv]` from backend/."""
from pathlib import Path
import sys

from app.config import Settings
from app.database import Database
from app.services.demo_data import seed_demo


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit("Usage: python -m app.seed [source.csv]")
    source = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(__file__).resolve().parents[2] / "dcccustomerservicerequestsp20130409-0956.csv"
    database = Database(Settings.from_env())
    try:
        database.initialize()
        result = seed_demo(database, source)
        print(f"Synthetic demo scenarios: inserted={result['inserted']} skipped={result['skipped']} total={result['total_scenarios']}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
