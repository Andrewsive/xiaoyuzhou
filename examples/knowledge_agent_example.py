from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from podcast_pipeline.knowledge_agent import answer_with_knowledge_base, print_agent_answer


def safe_print(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    sanitized = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore")
    print(sanitized)


def main() -> None:
    payload = answer_with_knowledge_base(
        config_path=ROOT / "config.yaml",
        question="Talk三联最近几期里，哪些内容谈到了年轻化？",
        top_k=3,
    )
    safe_print(print_agent_answer(payload))


if __name__ == "__main__":
    main()
