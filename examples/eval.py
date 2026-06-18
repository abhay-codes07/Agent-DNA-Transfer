"""Run the built-in recall-quality benchmark and print the metrics.

Runnable:  uv run python examples/eval.py
(Equivalent to `helix eval`. Metrics depend on the active embedder — hashing vs fastembed.)
"""

from __future__ import annotations

from helix_core.eval import CODING_BENCHMARK, run_eval


def main() -> None:
    res = run_eval(CODING_BENCHMARK, k=5)
    print("Helix recall benchmark (coding-agent memory):")
    for key, value in res.as_dict().items():
        print(f"  {key:16} {value}")


if __name__ == "__main__":
    main()
