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
    # 1. Strip <think>...</think> blocks first (including unclosed <think> blocks)
    if "<think>" in text.lower():
        if "</think>" in text.lower():
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
        else:
            # Unclosed <think> block — keep content starting from first JSON brace '{' or '['
            json_start = -1
            for ch in ('{', '['):
                pos = text.find(ch)
                if pos != -1 and (json_start == -1 or pos < json_start):
                    json_start = pos
            if json_start != -1:
                text = text[json_start:].strip()
            else:
                text = re.sub(r"<think>.*", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

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
    Attempt to repair a truncated JSON string by completing unclosed string quotes,
    removing incomplete trailing key/value fragments, and closing open brackets and braces.
    """
    json_str = json_str.rstrip()

    # 1. Strip incomplete trailing key / colon / value fragments at cutoff point
    json_str = re.sub(r',\s*"[^"]*$', '', json_str)
    json_str = re.sub(r',\s*"[^"]*"\s*:\s*$', '', json_str)
    json_str = re.sub(r',\s*"[^"]*"\s*:\s*"[^"]*$', '', json_str)
    json_str = re.sub(r'[:,\s]+$', '', json_str)

    # 2. Count unmatched opening brackets/braces
    stack = []
    in_string = False
    escaped = False

    for char in json_str:
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

    if in_string:
        json_str = json_str.rstrip('\\') + '"'

    json_str = re.sub(r'[:,\s]+$', '', json_str)

    # 3. Append missing closing brackets in reverse order
    closing_map = {'{': '}', '[': ']'}
    for char in reversed(stack):
        json_str += closing_map[char]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback repair attempt: strip trailing malformed lines line-by-line
        lines = json_str.splitlines()
        for i in range(len(lines) - 1, max(0, len(lines) - 10), -1):
            trimmed = "\n".join(lines[:i])
            trimmed = re.sub(r'[:,\s]+$', '', trimmed)
            sub_stack = []
            s_in_string = False
            s_escaped = False
            for c in trimmed:
                if s_escaped:
                    s_escaped = False
                    continue
                if c == '\\':
                    s_escaped = True
                    continue
                if c == '"':
                    s_in_string = not s_in_string
                    continue
                if s_in_string:
                    continue
                if c in '{[':
                    sub_stack.append(c)
                elif c in '}]':
                    if sub_stack and ((c == '}' and sub_stack[-1] == '{') or (c == ']' and sub_stack[-1] == '[')):
                        sub_stack.pop()
            if s_in_string:
                trimmed += '"'
            trimmed = re.sub(r'[:,\s]+$', '', trimmed)
            for c in reversed(sub_stack):
                trimmed += closing_map[c]
            try:
                return json.loads(trimmed)
            except json.JSONDecodeError:
                continue
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
