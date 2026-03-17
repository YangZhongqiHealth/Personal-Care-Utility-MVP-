import argparse
from pathlib import Path

from mvp.backend.pcu_pipeline import build_payload, payload_to_json


def main():
    parser = argparse.ArgumentParser(description="Build PCU MVP playback log.")
    parser.add_argument("--dataset-root", required=True, help="Path to CGMacros-015 folder.")
    parser.add_argument("--participant", default=None, help="Participant id (e.g., pers2003).")
    parser.add_argument("--max-meals", type=int, default=6, help="Max meals to include.")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    payload = build_payload(dataset_root, participant=args.participant, max_meals=args.max_meals)
    print(payload_to_json(payload))


if __name__ == "__main__":
    main()
