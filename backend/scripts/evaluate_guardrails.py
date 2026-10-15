"""Report guardrail performance per category for thesis results."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.pipeline_factory import get_chatbot_pipeline


def safe_divide(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def evaluate(cases: list[dict]) -> dict:
    pipeline = get_chatbot_pipeline()
    rows = []
    labels = {str(case["expected"]) for case in cases}
    guardrail_labels = labels - {"allowed"}
    counters = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "support": 0})
    correct = 0

    for case in cases:
        expected = str(case["expected"])
        response = pipeline.answer(str(case["question"]))
        raw_prediction = response.escalation or "allowed"
        # Infrastructure/retrieval fallbacks are not guardrail categories.
        predicted = raw_prediction if raw_prediction in guardrail_labels else "allowed"
        labels.add(predicted)
        correct += int(predicted == expected)
        counters[expected]["support"] += 1
        for label in labels | {expected, predicted}:
            if predicted == label and expected == label:
                counters[label]["tp"] += 1
            elif predicted == label and expected != label:
                counters[label]["fp"] += 1
            elif predicted != label and expected == label:
                counters[label]["fn"] += 1
        rows.append(
            {
                "id": case.get("id"),
                "question": case["question"],
                "expected": expected,
                "predicted": predicted,
                "passed": predicted == expected,
            }
        )

    categories = {}
    for label in sorted(labels):
        values = counters[label]
        precision = safe_divide(values["tp"], values["tp"] + values["fp"])
        recall = safe_divide(values["tp"], values["tp"] + values["fn"])
        categories[label] = {
            "support": values["support"],
            "precision": precision,
            "recall": recall,
            "f1": safe_divide(2 * precision * recall, precision + recall),
        }

    return {
        "total_cases": len(cases),
        "correct": correct,
        "accuracy": safe_divide(correct, len(cases)),
        "categories": categories,
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "guardrails" / "guardrail_cases.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--minimum-cases",
        type=int,
        default=100,
        help="Minimum kasus untuk laporan penelitian final (default: 100).",
    )
    arguments = parser.parse_args()
    cases = json.loads(arguments.cases.read_text(encoding="utf-8"))
    if len(cases) < arguments.minimum_cases:
        raise SystemExit(
            f"Dataset hanya berisi {len(cases)} kasus; laporan final memerlukan "
            f"minimal {arguments.minimum_cases} kasus yang sudah divalidasi penilai manusia."
        )
    report = evaluate(cases)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
