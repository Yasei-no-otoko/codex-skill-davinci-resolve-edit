"""Write UTF-8 SRT from final-timeline frame cues without overwriting files.

Usage: python write_srt.py captions.json captions.srt [--allow-overlap]
Input: {"fps": "30000/1001", "cues": [
    {"start_frame": 0, "end_frame": 60, "text": "Caption"}
]}
Ranges are [start, end), relative to program start, not source media.
"""

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys


def require_frame(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer frame")
    return value


def frame_ms(frame, fps):
    value = Fraction(frame * 1000, 1) / fps
    # Half-up rounding; no binary float accumulation at fractional frame rates.
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def timestamp(ms):
    hours, remainder = divmod(ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def make_srt(data, allow_overlap=False):
    if not isinstance(data, dict) or set(data) != {"fps", "cues"}:
        raise ValueError("Input must contain exactly fps and cues")
    if isinstance(data["fps"], bool):
        raise ValueError("fps must be a positive rate such as 30000/1001")
    try:
        fps = Fraction(str(data["fps"]))
    except (ValueError, ZeroDivisionError):
        raise ValueError("fps must be a positive rate such as 30000/1001") from None
    if not 0 < fps <= 1000:
        raise ValueError("fps must be greater than 0 and at most 1000")
    cues = data["cues"]
    if not isinstance(cues, list) or not cues:
        raise ValueError("cues must be a nonempty list")
    blocks = []
    previous_start, greatest_end = -1, 0
    for index, cue in enumerate(cues, 1):
        if not isinstance(cue, dict) or set(cue) != {"start_frame", "end_frame", "text"}:
            raise ValueError(f"Cue {index} must contain start_frame, end_frame and text")
        start = require_frame(cue["start_frame"], f"Cue {index} start_frame")
        end = require_frame(cue["end_frame"], f"Cue {index} end_frame")
        if end <= start:
            raise ValueError(f"Cue {index} end_frame must be greater than start_frame")
        if start < previous_start:
            raise ValueError(f"Cue {index} is not in chronological order")
        if not allow_overlap and start < greatest_end:
            raise ValueError(f"Cue {index} overlaps an earlier cue")
        text = cue["text"]
        if not isinstance(text, str):
            raise ValueError(f"Cue {index} text must be a string")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text or any(not line.strip() for line in text.split("\n")):
            raise ValueError(f"Cue {index} has empty text or an empty line")
        if any(ord(char) < 32 and char not in ("\n", "\t") for char in text):
            raise ValueError(f"Cue {index} contains a control character")
        start_ms, end_ms = frame_ms(start, fps), frame_ms(end, fps)
        if end_ms <= start_ms:
            raise ValueError(f"Cue {index} has no duration after rounding to milliseconds")
        blocks.append(f"{index}\n{timestamp(start_ms)} --> {timestamp(end_ms)}\n{text}\n")
        previous_start, greatest_end = start, max(greatest_end, end)
    return "\n".join(blocks) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--allow-overlap", action="store_true")
    args = parser.parse_args()
    try:
        if args.output.suffix.lower() != ".srt":
            raise ValueError("Output filename must end in .srt")
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        content = make_srt(data, args.allow_overlap)
        # Validate before opening output; exclusive creation also protects input
        # if the caller supplies the same path twice.
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    except (OSError, ValueError) as error:
        print(f"SRT error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output.resolve()), "cues": len(data["cues"])},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
