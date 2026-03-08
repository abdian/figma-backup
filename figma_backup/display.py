"""
Display module -- all terminal UI rendering using Rich library.
Provides banner, progress bars, tree views, tables, and user prompts.
"""

import sys
import io
from typing import Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn,
)
from rich.prompt import Confirm
from rich.text import Text
from rich import box

from figma_backup import __version__
from figma_backup.utils import human_size

# Force UTF-8 on Windows to avoid cp1252 encoding errors with Rich
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console()


def show_banner():
    """Display the application banner with version info."""
    banner_text = Text.assemble(
        ("Figma Backup", "bold cyan"),
        (f" v{__version__}", "dim"),
    )
    console.print(Panel(
        banner_text,
        subtitle="Complete Figma Account Backup Tool",
        box=box.DOUBLE,
        style="blue",
        padding=(1, 4),
    ))


def show_user_info(name: str, email: str):
    """Display authenticated user info."""
    console.print(f"  [green][OK][/green] Authenticated as [bold]{name}[/bold] ({email})")


def show_error(message: str):
    """Display an error message in red."""
    console.print(f"  [bold red][X] ERROR[/bold red] {message}")


def show_warning(message: str):
    """Display a warning message in yellow."""
    console.print(f"  [bold yellow][!] WARNING[/bold yellow] {message}")


def show_success(message: str):
    """Display a success message in green."""
    console.print(f"  [bold green][OK][/bold green] {message}")


def show_team_tree(teams: list):
    """Render teams > projects > files as a Rich tree view."""
    tree = Tree("[bold blue]Figma Account[/bold blue]")
    total_files = 0
    for team in teams:
        team_branch = tree.add(f"[bold cyan]Team: {team.name}[/bold cyan]")
        for project in team.projects:
            file_count = len(project.files)
            total_files += file_count
            proj_branch = team_branch.add(
                f"[yellow]Project: {project.name}[/yellow] [dim]({file_count} files)[/dim]"
            )
            for file in project.files:
                proj_branch.add(f"[dim]- {file.name}[/dim]")
    console.print(tree)
    console.print(f"\n  [dim]Total: {total_files} file(s) across {len(teams)} team(s)[/dim]")


def show_summary_table(stats: Dict[str, int], backup_path: str, elapsed: float, total_bytes: int = 0):
    """Display final backup summary as a styled table."""
    table = Table(title="Backup Summary", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold white", justify="right")

    for key, value in stats.items():
        if value == 0 and key != "errors":
            continue
        label = key.replace("_", " ").title()
        style = "red" if key == "errors" and value > 0 else ""
        table.add_row(label, str(value), style=style)

    minutes, seconds = divmod(int(elapsed), 60)
    if minutes > 0:
        table.add_row("Duration", f"{minutes}m {seconds}s")
    else:
        table.add_row("Duration", f"{seconds}s")
    if total_bytes > 0:
        table.add_row("Total Size", human_size(total_bytes))
    table.add_row("Location", backup_path)
    console.print(Panel(table, style="green"))


def create_backup_progress() -> Progress:
    """Create a multi-column progress bar for tracking backup items."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TextColumn("[green]{task.fields[downloaded]}[/green]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def confirm_resume(backup_path: str) -> bool:
    """Ask user whether to resume an incomplete backup."""
    return Confirm.ask(
        f"\n  [yellow]Incomplete backup found at[/yellow] [bold]{backup_path}[/bold].\n  Resume?",
        console=console,
    )


def prompt_numbered_selection(items: List[str], label: str) -> List[int]:
    """Display a numbered list and let the user pick one or more items.

    Returns list of 0-based indices. Entering 0 selects all items.
    """
    console.print(f"\n  [bold]{label}:[/bold]")
    for i, name in enumerate(items):
        console.print(f"    [cyan]{i + 1}[/cyan]. {name}")
    console.print(f"    [cyan]0[/cyan]. All")

    while True:
        try:
            choice = console.input("\n  Enter selection (comma-separated, 0=all): ").strip()
            if choice == "0":
                return list(range(len(items)))
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
            if all(0 <= i < len(items) for i in indices):
                return indices
            show_error("Invalid selection. Try again.")
        except ValueError:
            show_error("Please enter numbers separated by commas.")


def prompt_team_ids() -> List[str]:
    """Prompt the user to enter Figma team IDs with a help guide.

    Shows how to find team IDs from the Figma URL and accepts
    one or more comma-separated IDs.
    """
    console.print()
    console.print(Panel(
        "[bold]How to find your Team ID:[/bold]\n\n"
        "1. Open [link=https://www.figma.com]figma.com[/link] in your browser\n"
        "2. Click on your team name\n"
        "3. Look at the URL:\n"
        "   https://www.figma.com/files/team/[bold cyan]1234567890[/bold cyan]/My-Team\n"
        "                                     [bold cyan]^^^^^^^^^^[/bold cyan]\n"
        "                                     This is your Team ID",
        title="[yellow]No Team ID configured[/yellow]",
        box=box.ROUNDED,
        padding=(1, 2),
    ))

    while True:
        raw = console.input("\n  Enter Team ID(s), separated by commas: ").strip()
        if not raw:
            show_error("Please enter at least one Team ID.")
            continue
        ids = [t.strip() for t in raw.split(",") if t.strip()]
        if all(t.isdigit() for t in ids):
            return ids
        show_error("Team IDs should be numbers only.")
