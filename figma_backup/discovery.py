"""
Discovery module -- fetches team/project/file hierarchy from Figma API
and provides interactive selection for choosing what to back up.
"""

from typing import List

from rich.prompt import Confirm

from figma_backup.api import FigmaApiClient
from figma_backup.models import FigmaTeam, FigmaProject, FigmaFile
from figma_backup.display import (
    console, show_error, show_team_tree, prompt_numbered_selection,
)


def discover_hierarchy(client: FigmaApiClient, team_ids: List[str]) -> List[FigmaTeam]:
    """Fetch the full Teams -> Projects -> Files hierarchy (metadata only).

    Iterates over team IDs, fetches projects for each team, then fetches
    file listings for each project. No file content is downloaded here.
    """
    teams = []
    for team_id in team_ids:
        try:
            data = client.get_team_projects(team_id)
        except Exception:
            show_error(f"Team {team_id} not found or no access")
            continue

        if not data or "projects" not in data:
            show_error(f"Team {team_id} not found or no access")
            continue

        team = FigmaTeam(
            id=team_id,
            name=data.get("name", team_id),
        )

        for proj_data in data.get("projects", []):
            project = FigmaProject(
                id=str(proj_data["id"]),
                name=proj_data["name"],
                team_id=team_id,
            )
            try:
                files_data = client.get_project_files(project.id)
            except Exception:
                continue

            for f in files_data.get("files", []):
                project.files.append(FigmaFile(
                    key=f["key"],
                    name=f["name"],
                    project_id=project.id,
                    last_modified=f.get("last_modified"),
                    thumbnail_url=f.get("thumbnail_url"),
                ))
            team.projects.append(project)
        teams.append(team)
    return teams


def interactive_select(teams: List[FigmaTeam]) -> List[FigmaTeam]:
    """Three-level interactive selection: teams -> projects -> files.

    Always shows the hierarchy tree first, then asks the user whether
    to back up everything or drill down into teams, projects, and files.
    """
    show_team_tree(teams)
    console.print()

    if Confirm.ask("  Back up [bold]everything[/bold]?", default=True, console=console):
        return teams

    # -- Level 1: Select teams --
    team_labels = []
    for team in teams:
        file_count = sum(len(p.files) for p in team.projects)
        team_labels.append(f"{team.name} ({len(team.projects)} projects, {file_count} files)")

    selected_team_indices = prompt_numbered_selection(team_labels, "Select teams")
    selected_teams = []

    for ti in selected_team_indices:
        team = teams[ti]

        # -- Level 2: Select projects --
        if len(team.projects) == 1:
            # Only one project, auto-include it but still ask about files
            selected_projects = list(team.projects)
        else:
            proj_labels = [
                f"{p.name} ({len(p.files)} files)" for p in team.projects
            ]
            selected_proj_indices = prompt_numbered_selection(
                proj_labels, f"Select projects from [cyan]{team.name}[/cyan]"
            )
            selected_projects = [team.projects[i] for i in selected_proj_indices]

        # -- Level 3: Select files per project --
        new_team = FigmaTeam(id=team.id, name=team.name)
        for project in selected_projects:
            if len(project.files) <= 1:
                # Only one file, auto-include
                new_team.projects.append(project)
                continue

            file_labels = [f.name for f in project.files]
            selected_file_indices = prompt_numbered_selection(
                file_labels, f"Select files from [yellow]{project.name}[/yellow]"
            )

            new_project = FigmaProject(
                id=project.id, name=project.name, team_id=project.team_id
            )
            new_project.files = [project.files[i] for i in selected_file_indices]
            if new_project.files:
                new_team.projects.append(new_project)

        if new_team.projects:
            selected_teams.append(new_team)

    return selected_teams
