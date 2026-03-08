"""
CLI module -- Click-based command line interface.
Defines the main 'figma-backup' command and the 'discover' subcommand.
"""

import sys
import logging

import click
from rich.logging import RichHandler

from figma_backup import __version__, __app_name__
from figma_backup.config import load_config, validate_config
from figma_backup.api import FigmaApiClient
from figma_backup.backup import BackupOrchestrator
from figma_backup.discovery import discover_hierarchy, interactive_select
from figma_backup.display import (
    console, show_banner, show_user_info, show_error,
    show_success, show_team_tree, prompt_team_ids,
)


@click.group(invoke_without_command=True)
@click.option("--token", envvar="FIGMA_TOKEN", help="Figma personal access token")
@click.option("--team-id", "team_ids", multiple=True, help="Team ID(s) to back up (repeatable)")
@click.option("--output", "-o", "output_dir", default=None, help="Output directory")
@click.option("--interactive", "-i", is_flag=True, help="Interactive team/project selection")
@click.option("--export-images", is_flag=True, help="Export pages/frames as images")
@click.option("--export-format", multiple=True, default=["png"],
              type=click.Choice(["png", "svg", "pdf"]), help="Image export format(s)")
@click.option("--export-scale", default=2.0, type=float, help="Image export scale (default: 2x)")
@click.option("--no-comments", is_flag=True, help="Skip comments backup")
@click.option("--no-versions", is_flag=True, help="Skip version history backup")
@click.option("--no-resume", is_flag=True, help="Disable resume (always start fresh)")
@click.option("--compress", "-z", is_flag=True, help="Compress backup to zip after completion")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging output")
@click.version_option(version=__version__, prog_name=__app_name__)
@click.pass_context
def cli(ctx, token, team_ids, output_dir, interactive, export_images,
        export_format, export_scale, no_comments, no_versions,
        no_resume, compress, verbose):
    """Figma Backup -- Complete Figma account backup tool.

    Back up all your Figma teams, projects, files, components, styles,
    comments, versions, and image exports.
    """
    if ctx.invoked_subcommand is not None:
        return

    # Configure logging: console only shows critical, details go to backup.log
    console_handler = RichHandler(console=console, show_path=False)
    console_handler.setLevel(logging.CRITICAL if not verbose else logging.DEBUG)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        handlers=[console_handler],
    )

    show_banner()

    # Load config with priority: CLI args > env vars > .env > defaults
    config = load_config(
        token=token,
        team_ids=list(team_ids) if team_ids else None,
        output_dir=output_dir,
        interactive=interactive,
        include_image_exports=export_images,
        export_formats=list(export_format),
        export_scale=export_scale,
        include_comments=not no_comments,
        include_versions=not no_versions,
        resume=not no_resume,
        compress=compress,
    )

    errors = validate_config(config)
    if errors:
        for err in errors:
            show_error(err)
        console.print("\n  [dim]Tip: Copy .env.example to .env and fill in your values[/dim]")
        sys.exit(1)

    # Validate token by calling /me
    client = FigmaApiClient(config.figma_token)
    try:
        user = client.get_me()
        if "handle" not in user and "email" not in user:
            raise ValueError("Invalid response")
        show_user_info(user.get("handle", "Unknown"), user.get("email", ""))
    except Exception:
        show_error("Invalid Figma token. Check your .env or --token value.")
        sys.exit(1)

    # If no team IDs configured, prompt the user to enter them
    if not config.team_ids:
        config.team_ids = prompt_team_ids()

    # Discover the team/project/file hierarchy
    console.print("\n  [dim]Discovering teams and projects...[/dim]")
    teams = discover_hierarchy(client, config.team_ids)

    if not teams:
        show_error("No teams found. Check your team IDs.")
        sys.exit(1)

    # Always let user choose what to back up
    teams = interactive_select(teams)
    if not teams:
        console.print("  [yellow]No items selected. Exiting.[/yellow]")
        sys.exit(0)

    # Run the backup pipeline
    console.print()
    orchestrator = BackupOrchestrator(config, client)
    orchestrator.run(teams)


@cli.command()
@click.option("--token", envvar="FIGMA_TOKEN", help="Figma personal access token")
@click.option("--team-id", "team_ids", multiple=True, help="Team ID(s)")
def discover(token, team_ids):
    """List all teams, projects, and files without downloading anything."""
    show_banner()

    config = load_config(token=token, team_ids=list(team_ids) if team_ids else None)
    errors = validate_config(config)
    if errors:
        for err in errors:
            show_error(err)
        sys.exit(1)

    client = FigmaApiClient(config.figma_token)
    try:
        user = client.get_me()
        show_user_info(user.get("handle", "Unknown"), user.get("email", ""))
    except Exception:
        show_error("Invalid Figma token.")
        sys.exit(1)

    if not config.team_ids:
        config.team_ids = prompt_team_ids()

    console.print("\n  [dim]Discovering teams and projects...[/dim]")
    teams = discover_hierarchy(client, config.team_ids)

    if not teams:
        show_error("No teams found.")
        sys.exit(1)

    show_team_tree(teams)
    show_success("Discovery complete. No files were downloaded.")


if __name__ == "__main__":
    cli()
