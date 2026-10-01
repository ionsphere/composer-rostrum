"""Report installed music programs and an honest route for requested operations."""
import argparse
import json

from composer_rostrum.music_programs import choose_music_program, discover_music_programs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operations", nargs="*", help="Canonical operations required by the request")
    parser.add_argument("--prefer", choices=("reaper", "audacity"))
    args = parser.parse_args()
    programs = discover_music_programs()
    result = {"programs": [program.to_dict() for program in programs],
              "choice": choose_music_program(args.operations, programs, args.prefer).to_dict()}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
