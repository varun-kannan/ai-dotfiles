"""ai-dotfiles harness engine: project detection, decisions, generation, checks."""
import os
from pathlib import Path

# Bump when the generated block or its inputs change shape; projects regenerate on the next trigger.
ENGINE_VERSION = 1

BASE = Path(__file__).resolve().parent.parent
SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
DATA = SHARED / "data"


def tokens(text):
    """Rough token estimate (chars/4). A guide for budgets, not a tokenizer."""
    return (len(text) + 3) // 4
