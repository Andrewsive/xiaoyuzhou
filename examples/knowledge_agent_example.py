from __future__ import annotations

from pathlib import Path

from podcast_pipeline.knowledge_agent import answer_with_knowledge_base, print_agent_answer


def main() -> None:
    payload = answer_with_knowledge_base(
        config_path=Path("config.yaml"),
        question="Talk三联最近几期里，哪些内容谈到了年轻化？",
        top_k=3,
    )
    print(print_agent_answer(payload))


if __name__ == "__main__":
    main()
