"""ai-dotfiles harness engine: project detection, decisions, generation, checks."""
import os
import sys
from pathlib import Path

# Bump when the generated block or its inputs change shape; projects regenerate on the next trigger.
ENGINE_VERSION = 2

BASE = Path(__file__).resolve().parent.parent
SHARED = Path(os.environ.get("AI_RULES_HOME") or Path.home() / ".ai-rules")
DATA = SHARED / "data"


def tokens(text):
    """Rough token estimate (chars/4). A guide for budgets, not a tokenizer."""
    return (len(text) + 3) // 4


def configure(shared):
    """Point every engine module at another shared folder. Tests use this for isolation."""
    global SHARED, DATA
    SHARED = Path(shared)
    DATA = SHARED / "data"
    for name, mod in list(sys.modules.items()):
        if name.startswith("engine.") and mod is not None:
            if hasattr(mod, "SHARED"):
                mod.SHARED = SHARED
            if hasattr(mod, "DATA"):
                mod.DATA = DATA


def harness_off():
    return (SHARED / "harness.off").exists() or os.environ.get("AI_HARNESS_OFF") == "1"
