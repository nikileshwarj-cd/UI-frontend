"""
agent/ui_regenerator.py
React UI Regeneration Agent (Refinement Agent)

Refines existing TSX/JSX and CSS code using the UI Validation Report
and wireframe blueprint until high visual similarity is achieved.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from rich.console import Console

from config import settings
from utils.groq_client import GroqClient
from utils.file_manager import FileManager

console = Console()


class UIRegenerator:
    """
    Refines and regenerates TSX/JSX and CSS code based on visual validation report.
    """

    def __init__(self, groq_client: GroqClient) -> None:
        self._client = groq_client
        self._system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        prompt_path = settings.prompts_dir / "ui_regeneration.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return "You are an expert React UI Regeneration Agent. Refine code for pixel-perfect match."

    def regenerate(
        self,
        file_manager: FileManager,
        validation_report: Dict[str, Any],
        project_name: str,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Refine generated code if visual similarity is below acceptable threshold.
        """
        def emit(msg: str) -> None:
            if progress_cb:
                progress_cb(msg)
            console.print(f"  [cyan]{msg}[/cyan]")

        score = validation_report.get("similarity_score", 100)
        if score >= 98:
            emit(f"UI visual similarity score is high ({score}%) — no refinement needed.")
            return False

        emit(f"UI visual similarity score is {score}% (< 98%). Running React UI Regeneration Agent...")

        ext = settings.output_language
        app_file = file_manager.react_src_dir / f"App.{ext}"
        css_file = file_manager.react_src_dir / "index.css"

        current_react = app_file.read_text(encoding="utf-8") if app_file.exists() else ""
        current_css = css_file.read_text(encoding="utf-8") if css_file.exists() else ""

        user_prompt = (
            f"VISUAL VALIDATION REPORT & DIFFERENCES:\n"
            f"```json\n{json.dumps(validation_report, indent=2)}\n```\n\n"
            f"CURRENT REACT COMPONENT ({ext.upper()}):\n"
            f"```{ext}\n{current_react}\n```\n\n"
            f"CURRENT CSS STYLESHEET:\n"
            f"```css\n{current_css}\n```\n\n"
            "Refine the React component and CSS stylesheet to eliminate all visual differences. "
            "Output Block 1 as React JSX/TSX and Block 2 as Vanilla CSS inside code blocks."
        )

        raw_output = self._client.chat(
            system_prompt=self._system_prompt,
            user_prompt=user_prompt,
            model=settings.code_model,
        )

        code_blocks = re.findall(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)```", raw_output)
        if len(code_blocks) >= 2:
            refined_jsx = code_blocks[0].strip()
            refined_css = code_blocks[1].strip()

            # Auto-repair unclosed quotes on JSX lines
            lines = refined_jsx.splitlines()
            fixed = []
            for line in lines:
                quotes = line.count('"') - line.count('\\"')
                if quotes % 2 != 0 and ('<' in line or '>' in line or '=' in line):
                    line = line.rstrip() + '"'
                fixed.append(line)
            refined_jsx = "\n".join(fixed)

            if refined_jsx:
                file_manager.write_text(app_file, refined_jsx)
            if refined_css:
                file_manager.write_text(css_file, refined_css)

            emit("✓ React UI Regeneration complete — updated App component & CSS styles.")
            return True
        elif len(code_blocks) == 1 and code_blocks[0].strip():
            file_manager.write_text(app_file, code_blocks[0].strip())
            emit("✓ React UI Regeneration complete — updated App component.")
            return True

        emit("[WARN] UI Regeneration response contained no valid code blocks.")
        return False
