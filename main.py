"""
main.py — CLI entry point for the AI Frontend Generation Agent.

Usage:
    python main.py --image input/images/ref.png \
                   --stories input/user_stories/stories.json \
                   --project my-app

Pipeline:
    Stage 1: Image Analysis  → ui_spec.json
    Stage 2: Story Mapping   → story_ui_mapping.json
    Stage 3: Code Generation → React/Vite project + HTML

Run the web UI instead:
    python ui/app_ui.py
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

# Config must be loaded before any agent imports
from config import settings
from agent import ImageAnalyzer, StoryMapper, CodeGenerator
from utils.groq_client import GroqClient
from utils.file_manager import FileManager
from utils.json_utils import save_json

console = Console()


# ---------------------------------------------------------------------------
# Pipeline banner
# ---------------------------------------------------------------------------

BANNER = """
╔══════════════════════════════════════════════════════════╗
║        AI-Powered Frontend Generation Agent  v1.0        ║
║           Groq × React × Vite × Python 3.11              ║
╚══════════════════════════════════════════════════════════╝
"""


def print_banner() -> None:
    console.print(BANNER, style="bold cyan")


# ---------------------------------------------------------------------------
# Stage runner with timing
# ---------------------------------------------------------------------------

class PipelineStage:
    def __init__(self, name: str, number: int) -> None:
        self.name = name
        self.number = number
        self.status = "pending"
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.messages: list[str] = []

    def start(self) -> None:
        self.status = "running"
        self.start_time = time.monotonic()

    def complete(self) -> None:
        self.status = "done"
        self.end_time = time.monotonic()

    def fail(self) -> None:
        self.status = "failed"
        self.end_time = time.monotonic()

    @property
    def elapsed(self) -> str:
        if self.start_time is None:
            return "—"
        end = self.end_time or time.monotonic()
        delta = int(end - self.start_time)
        return str(timedelta(seconds=delta))

    def status_icon(self) -> str:
        return {"pending": "○", "running": "◉", "done": "✓", "failed": "✗"}.get(
            self.status, "?"
        )

    def status_color(self) -> str:
        return {
            "pending": "dim",
            "running": "yellow",
            "done": "green",
            "failed": "bold red",
        }.get(self.status, "white")


def build_pipeline_table(stages: list[PipelineStage], total_start: float) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("icon", style="bold", width=3)
    table.add_column("stage", width=10)
    table.add_column("name", width=22)
    table.add_column("time", width=10)
    table.add_column("last_msg")

    for s in stages:
        icon = Text(s.status_icon(), style=s.status_color())
        stage_label = Text(f"Stage {s.number}", style="dim")
        name = Text(s.name, style=s.status_color())
        elapsed = Text(f"[{s.elapsed}]", style="dim")
        msg = Text(s.messages[-1][:50] if s.messages else "", style="dim italic")
        table.add_row(icon, stage_label, name, elapsed, msg)

    # Total
    total_elapsed = int(time.monotonic() - total_start)
    total_str = str(timedelta(seconds=total_elapsed))
    table.add_row(Text(""), Text(""), Text("Total", style="bold white"), Text(f"[{total_str}]", style="bold"), Text(""))

    return table


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Frontend Generation Agent — Generates React/Vite apps from UI screenshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--image",
        type=Path,
        required=True,
        help="Path to the reference UI screenshot (PNG or JPG)",
    )
    parser.add_argument(
        "--stories",
        type=Path,
        required=True,
        help="Path to user_stories.json",
    )
    parser.add_argument(
        "--project",
        type=str,
        default="generated-app",
        help="Project name (used for output directory)",
    )
    parser.add_argument(
        "--lang",
        choices=["tsx", "jsx"],
        default=None,
        help="Output language override (tsx or jsx). Defaults to OUTPUT_LANGUAGE from .env",
    )
    parser.add_argument(
        "--skip-npm",
        action="store_true",
        help="Skip npm install after code generation",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    # Override language if specified
    if args.lang:
        settings.output_language = args.lang

    print_banner()

    console.print(f"[bold]Project:[/bold] {args.project}")
    console.print(f"[bold]Image:[/bold]   {args.image}")
    console.print(f"[bold]Stories:[/bold] {args.stories}")
    console.print(f"[bold]Language:[/bold] {settings.output_language.upper()}")
    console.print(f"[bold]Vision model:[/bold]  {settings.vision_model}")
    console.print(f"[bold]Code model:[/bold]    {settings.code_model}")
    console.print()

    # Validate inputs
    if not args.image.exists():
        console.print(f"[red][ERROR] Image not found: {args.image}[/red]")
        return 1
    if not args.stories.exists():
        console.print(f"[red][ERROR] Stories file not found: {args.stories}[/red]")
        return 1

    # Setup
    groq_client = GroqClient()
    file_manager = FileManager(args.project)
    image_analyzer = ImageAnalyzer(groq_client)
    story_mapper = StoryMapper(groq_client)
    code_generator = CodeGenerator(groq_client)

    stages = [
        PipelineStage("Image Analysis", 1),
        PipelineStage("Story Mapping", 2),
        PipelineStage("Code Generation", 3),
    ]

    total_start = time.monotonic()

    with Live(
        Panel(build_pipeline_table(stages, total_start), title="[bold cyan]Pipeline Progress[/bold cyan]", border_style="cyan"),
        refresh_per_second=4,
        console=console,
    ) as live:

        def update_display() -> None:
            live.update(
                Panel(
                    build_pipeline_table(stages, total_start),
                    title="[bold cyan]Pipeline Progress[/bold cyan]",
                    border_style="cyan",
                )
            )

        def make_progress_cb(stage: PipelineStage):
            def cb(msg: str) -> None:
                stage.messages.append(msg)
                update_display()
            return cb

        # ----------------------------------------------------------------
        # Stage 1 — Image Analysis
        # ----------------------------------------------------------------
        stages[0].start()
        update_display()

        ui_spec_path = file_manager.metadata_dir / "ui_spec.json"
        ui_spec = image_analyzer.analyze(
            image_path=args.image,
            output_path=ui_spec_path,
            progress_cb=make_progress_cb(stages[0]),
        )

        if ui_spec is None:
            stages[0].fail()
            update_display()
            console.print("\n[bold red]Stage 1 FAILED — aborting pipeline.[/bold red]")
            return 1

        stages[0].complete()
        update_display()

        # ----------------------------------------------------------------
        # Stage 2 — Story Mapping
        # ----------------------------------------------------------------
        stages[1].start()
        update_display()

        mapping_path = file_manager.metadata_dir / "story_ui_mapping.json"
        mapping_doc = story_mapper.map(
            ui_spec=ui_spec,
            ui_spec_path=ui_spec_path,
            stories_path=args.stories,
            output_path=mapping_path,
            progress_cb=make_progress_cb(stages[1]),
        )

        if mapping_doc is None:
            stages[1].fail()
            update_display()
            console.print("\n[bold red]Stage 2 FAILED — aborting pipeline.[/bold red]")
            return 1

        stages[1].complete()
        update_display()

        # ----------------------------------------------------------------
        # Stage 3 — Code Generation
        # ----------------------------------------------------------------
        stages[2].start()
        update_display()

        traceability = code_generator.generate(
            image_path=args.image,
            ui_spec=ui_spec,
            ui_spec_path=ui_spec_path,
            mapping_doc=mapping_doc,
            mapping_path=mapping_path,
            file_manager=file_manager,
            project_name=args.project,
            progress_cb=make_progress_cb(stages[2]),
        )

        stages[2].complete()
        update_display()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    console.print()
    console.print(Panel.fit(
        f"[bold green]✓ Generation Complete![/bold green]\n\n"
        f"[bold]Output:[/bold]   {file_manager.project_root}\n"
        f"[bold]HTML:[/bold]     {file_manager.static_html_dir}\n"
        f"[bold]React App:[/bold] {file_manager.react_app_dir}\n\n"
        f"[bold cyan]To run the generated app:[/bold cyan]\n"
        f"  cd {file_manager.react_app_dir}\n"
        f"  npm install   [dim](if not already done)[/dim]\n"
        f"  npm run dev\n\n"
        f"[bold]Coverage:[/bold] {traceability.coverage_percent if traceability else 'N/A'}%",
        title="[bold]Result[/bold]",
        border_style="green",
    ))

    if traceability and traceability.warnings:
        console.print(f"\n[yellow]Warnings ({len(traceability.warnings)}):[/yellow]")
        for w in traceability.warnings[:5]:
            console.print(f"  [yellow]• {w}[/yellow]")

    # Print file tree
    console.print("\n[bold]Generated file tree:[/bold]")
    console.print(file_manager.file_tree())

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run(parse_args()))
