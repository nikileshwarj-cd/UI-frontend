"""
utils/json_utils.py
Utilities for cleaning LLM responses and validating JSON.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError
from rich.console import Console

console = Console()
T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Fence stripping
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"^```(?:json|javascript|typescript|tsx|jsx|html|css|python|bash|sh|)?\s*\n?"
    r"(.*?)"
    r"\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)

_INLINE_FENCE_RE = re.compile(r"`{1,3}[a-z]*\n?", re.IGNORECASE)

# Matches <think>...</think> blocks produced by reasoning/thinking models
# (e.g. Qwen3, DeepSeek-R1). We strip these before any further processing.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_fences(text: str) -> str:
    """Remove markdown code fences and <think> reasoning blocks from LLM responses."""
    text = text.strip()
    # 1. Strip <think>...</think> blocks first (reasoning/thinking models)
    text = _THINK_RE.sub("", text).strip()
    # 2. Try multi-line fence block
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # 3. Fall back: strip any remaining backtick sequences
    return _INLINE_FENCE_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def repair_truncated_json(json_str: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to repair a truncated JSON string by trimming incomplete trailing keys/values
    and closing open brackets and braces.
    """
    if not json_str or not json_str.strip():
        return None

    s = json_str.strip()

    # Direct parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Iteratively trim incomplete key/value tokens at the end until valid JSON is achieved
    for _ in range(15):
        s = re.sub(r'[:,\s]+$', '', s)
        # Trim dangling key e.g. , "elementId or , "elementId"
        s = re.sub(r',\s*"[^"]*"?$', '', s)
        s = re.sub(r'[:,\s]+$', '', s)

        stack = []
        in_string = False
        escaped = False

        for char in s:
            if escaped:
                escaped = False
                continue
            if char == '\\':
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if char in '{[':
                stack.append(char)
            elif char in '}]':
                if stack:
                    if (char == '}' and stack[-1] == '{') or (char == ']' and stack[-1] == '['):
                        stack.pop()

        candidate = s
        if in_string:
            candidate = candidate.rstrip('\\') + '"'

        candidate = re.sub(r'[:,\s]+$', '', candidate)
        closing_map = {'{': '}', '[': ']'}
        candidate += "".join(closing_map[c] for c in reversed(stack))

        try:
            res = json.loads(candidate)
            if isinstance(res, dict):
                return res
        except json.JSONDecodeError:
            # Drop trailing element (key-value, item, or container) and retry
            s = re.sub(r',?\s*(?:"[^"]*"|\d+|true|false|null|\}\s*|\]\s*)$', '', s)

    return None


def parse_json_safe(text: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to parse text as JSON.
    Returns parsed dict or None on failure.
    Handles:
    - <think>...</think> reasoning blocks (Qwen3, DeepSeek-R1, etc.)
    - Markdown code fences
    - JSON buried inside prose
    - Truncated JSON (auto-repairs unclosed brackets/quotes)
    """
    cleaned = strip_fences(text)

    # Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to extract the first complete {...} or [...] block.
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass

    # If parsing still failed, attempt to repair truncated JSON starting from first '{'
    start = cleaned.find('{')
    if start != -1:
        repaired = repair_truncated_json(cleaned[start:])
        if repaired is not None:
            console.print("[cyan][json_utils] Successfully repaired truncated JSON response![/cyan]")
            return repaired

    console.print("[yellow][json_utils] Could not parse JSON from LLM response.[/yellow]")
    return None


def validate_model(data: Dict[str, Any], model_cls: Type[T]) -> Optional[T]:
    """Validate a dict against a Pydantic model. Returns instance or None."""
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        console.print(f"[yellow][json_utils] Pydantic validation warning: {exc}[/yellow]")
        # Return a partial object if possible by building with what we have
        try:
            return model_cls.model_construct(**data)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_json(data: Any, path: Path, indent: int = 2) -> None:
    """Serialise data to a JSON file. Creates parent dirs automatically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        text = data.model_dump_json(indent=indent, by_alias=True)
    else:
        text = json.dumps(data, indent=indent, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    console.print(f"[green]  ✓ Saved:[/green] {path}")


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse a JSON file. Returns None on error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        console.print(f"[red][json_utils] Failed to load {path}: {exc}[/red]")
        return None


def validate_and_save_json(
    data: Dict[str, Any],
    path: Path,
    model_cls: Optional[Type[T]] = None,
) -> bool:
    """Validate (optionally against a Pydantic model) and save JSON. Returns success."""
    try:
        # Ensure it's serialisable
        json.dumps(data)
    except (TypeError, ValueError) as exc:
        console.print(f"[red][json_utils] Data is not JSON-serialisable: {exc}[/red]")
        return False

    if model_cls is not None:
        instance = validate_model(data, model_cls)
        if instance is None:
            console.print(f"[red][json_utils] Validation failed for {model_cls.__name__}[/red]")
            return False
        save_json(instance, path)
    else:
        save_json(data, path)
    return True
