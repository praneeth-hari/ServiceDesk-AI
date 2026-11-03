"""
Dataset loader module for ServiceDesk500.

Provides programmatic access to the validated dataset splits ('train', 'test', 'all').
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import json


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "servicedesk500"


@dataclass(frozen=True)
class TicketExample:
    """Represents a validated ticket example from the ServiceDesk500 dataset."""

    id: str
    text: str  # title + "\n" + description (strictly excludes label_note and labels)
    category: str
    priority: str
    difficulty: str
    group: str


def load_split(
    name: Literal["train", "test", "all"],
    data_dir: Path | str | None = None,
) -> list[TicketExample]:
    """
    Load ticket examples for a given split ('train', 'test', or 'all').

    Args:
        name: Name of the split to load ('train', 'test', or 'all').
        data_dir: Directory containing the dataset files. Defaults to data/servicedesk500.

    Returns:
        List of TicketExample objects. Each object contains id, text (title + "\n" + description),
        category, priority, difficulty, and group.
    """
    valid_splits = {"train", "test", "all"}
    split_name = name.strip().lower()
    if split_name not in valid_splits:
        raise ValueError(
            f"Invalid split name '{name}'. Allowed values are: 'train', 'test', 'all'."
        )

    base_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR

    if split_name == "train":
        filepath = base_dir / "train.jsonl"
    elif split_name == "test":
        filepath = base_dir / "test.jsonl"
    else:  # "all"
        filepath = base_dir / "servicedesk500.jsonl"
        if not filepath.exists():
            # Fallback to train + test if servicedesk500.jsonl is absent
            return load_split("train", data_dir=base_dir) + load_split("test", data_dir=base_dir)

    if not filepath.is_file():
        raise FileNotFoundError(f"Split file not found: {filepath.resolve()}")

    examples: list[TicketExample] = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            data = json.loads(line_str)
            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            text = f"{title}\n{description}" if title and description else (title or description)

            examples.append(
                TicketExample(
                    id=data["id"],
                    text=text,
                    category=data["category"],
                    priority=data["priority"],
                    difficulty=data["difficulty"],
                    group=data.get("group", data["id"]),
                )
            )

    return examples

