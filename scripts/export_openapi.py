"""Export the current FastAPI app's OpenAPI schema to a file.

Usage:
    SECRET_KEY=x DATABASE_URL=sqlite:///./tmp.db python scripts/export_openapi.py [out_path]

out_path defaults to openapi-snapshot.json. Run this (pointed at openapi-snapshot.json) only when
deliberately dropping backward compatibility for old app builds -- see docs/api-compatibility.md.
"""
import json
import sys

from src.main import app


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "openapi-snapshot.json"
    with open(out_path, "w") as f:
        json.dump(app.openapi(), f, indent=2)
        f.write("\n")
    print(f"Wrote OpenAPI schema to {out_path}")


if __name__ == "__main__":
    main()
