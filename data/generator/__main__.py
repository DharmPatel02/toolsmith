import argparse
import json

from data.generator import write_history

parser = argparse.ArgumentParser(description="Generate deterministic synthetic analyst history")
parser.add_argument("--out", default="data/seed")
parser.add_argument("--user-id", default="u_1")
parser.add_argument("--start", default="2026-09-07", help="First Monday, YYYY-MM-DD")
args = parser.parse_args()
print(json.dumps(write_history(args.out, user_id=args.user_id, start=args.start), indent=2))
