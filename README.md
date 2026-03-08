# Figma Backup

Complete backup tool for your Figma account. Downloads **everything** -- files, components, styles, comments, version history, thumbnails, and images -- with a beautiful terminal interface.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Features](#features)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Command Line Options](#command-line-options)
  - [Examples](#examples)
- [Configuration](#configuration)
  - [Getting Your Figma Token](#getting-your-figma-token)
  - [Finding Your Team ID](#finding-your-team-id)
  - [.env Variables](#env-variables)
- [What Gets Backed Up](#what-gets-backed-up)
- [Incremental Backup](#incremental-backup)
- [Retry & Verification](#retry--verification)
- [Resume Capability](#resume-capability)
- [Backup Directory Structure](#backup-directory-structure)
- [Rate Limits](#rate-limits)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Prerequisites

You only need **one thing** installed on your computer:

| Requirement | Version | Download |
|-------------|---------|----------|
| **Python** | 3.8 or higher | [python.org/downloads](https://www.python.org/downloads/) |

> **That's it!** All other dependencies (requests, rich, click, python-dotenv) are installed **automatically** when you run the tool for the first time.

### How to check if Python is installed

Open your terminal and run:

```bash
python --version
```

If you see `Python 3.x.x`, you're good to go. If not, download it from the link above.

> **Windows users:** During Python installation, make sure to check **"Add Python to PATH"**.

---

## Quick Start

### Step 1: Download the project

```bash
git clone https://github.com/abdian/figma-backup.git
cd figma-backup
```

Or [download the ZIP](https://github.com/abdian/figma-backup/archive/refs/heads/main.zip) and extract it.

### Step 2: Set up your configuration

Copy the example config file and edit it:

```bash
cp .env.example .env
```

Open `.env` in any text editor and add your Figma token:

```env
FIGMA_TOKEN=paste_your_token_here
```

> Don't know how to get your token? See [Getting Your Figma Token](#getting-your-figma-token) below.

> **Team ID is optional!** If you don't set `FIGMA_TEAM_IDS` in your `.env`, the tool will ask you for it when you run it and show you how to find it.

### Step 3: Run the backup

**On Linux / macOS:**
```bash
chmod +x figma-backup.sh
./figma-backup.sh
```

**On Windows:**
```cmd
figma-backup.bat
```

The launcher script will automatically:
1. Create a virtual environment
2. Install all dependencies
3. Start the backup

That's it! Your backup will be saved in the `figma_backup_output/` folder.

---

## Features

| Feature | Description |
|---------|-------------|
| **Complete Backup** | Files, comments, versions, components, component sets, styles, thumbnails, image fills |
| **Incremental Backup** | Only downloads changed files; copies unchanged from previous backup |
| **Auto Retry** | Failed downloads are automatically retried with exponential backoff |
| **Verification** | Final check after backup confirms all items were saved correctly |
| **Image Export** | Export pages and frames as PNG, SVG, or PDF |
| **Resume** | If interrupted, resume from where it stopped |
| **Interactive Selection** | Choose exactly what to back up: teams, projects, or individual files |
| **Optional Team ID** | Don't know your Team ID? The tool will ask and guide you |
| **Beautiful UI** | Progress bars, download size, colored output, tree views, summary tables |
| **Smart Rate Limiting** | Automatically respects Figma API limits |
| **Compression** | Optionally compress backup to a ZIP file |
| **Secure** | Your token stays in `.env`, never hardcoded |
| **Cross-Platform** | Works on Linux, macOS, and Windows |

---

## Usage

### Basic Usage

```bash
# Run the backup -- you'll be asked what to back up
./figma-backup.sh

# Just see your teams and files (no download)
./figma-backup.sh discover
```

> **Windows users:** Replace `./figma-backup.sh` with `figma-backup.bat` in all examples.

When you run the tool, it will:
1. Show all your teams, projects, and files
2. Ask: **"Back up everything?"**
3. If you say **no**, you can select specific teams, projects, or even individual files

### Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--token TEXT` | | Figma token (overrides .env) |
| `--team-id TEXT` | | Team ID to back up (can be used multiple times) |
| `--output TEXT` | `-o` | Output folder (default: `figma_backup_output`) |
| `--interactive` | `-i` | Pick teams/projects/files interactively |
| `--export-images` | | Also export frames as images |
| `--export-format` | | Image format: `png`, `svg`, or `pdf` (can be used multiple times) |
| `--export-scale` | | Image scale (default: 2x) |
| `--no-comments` | | Skip comments |
| `--no-versions` | | Skip version history |
| `--no-resume` | | Always start fresh (don't resume) |
| `--compress` | `-z` | Create a ZIP file after backup |
| `--verbose` | `-v` | Show detailed logs |
| `--version` | | Show version number |
| `--help` | | Show help |

### Examples

**Run and choose what to back up:**
```bash
./figma-backup.sh
```

**Back up specific teams (skip the prompt):**
```bash
./figma-backup.sh --team-id 123456789 --team-id 987654321
```

**Back up with image exports in PNG and SVG:**
```bash
./figma-backup.sh --export-images --export-format png --export-format svg
```

**Fast backup (skip comments and versions):**
```bash
./figma-backup.sh --no-comments --no-versions
```

**Compressed backup:**
```bash
./figma-backup.sh -z
```

**Advanced: Run directly with Python (without launcher):**
```bash
pip install -r requirements.txt
python -m figma_backup --help
```

---

## Configuration

### Getting Your Figma Token

1. Go to your [Figma Account Settings](https://www.figma.com/settings)
2. Scroll down to **"Personal access tokens"**
3. Click **"Generate new token"**
4. Give it a name (e.g. "Backup Tool")
5. Copy the token -- **you won't be able to see it again!**
6. Paste it in your `.env` file as `FIGMA_TOKEN`

### Finding Your Team ID

> **This is optional!** If you don't set your Team ID, the tool will ask you when you run it and show you how to find it.

1. Open [Figma](https://www.figma.com) in your browser
2. Click on your team name in the left sidebar
3. Look at the URL in your browser:
   ```
   https://www.figma.com/files/team/1234567890/My-Team
                                      ^^^^^^^^^^
                                      This is your Team ID
   ```
4. Copy the number and paste it in your `.env` file as `FIGMA_TEAM_IDS`

> **Multiple teams?** Separate them with commas: `FIGMA_TEAM_IDS=111111,222222,333333`

### .env Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FIGMA_TOKEN` | Yes | -- | Your personal access token |
| `FIGMA_TEAM_IDS` | No | -- | Comma-separated team IDs (will be prompted if empty) |
| `FIGMA_OUTPUT_DIR` | No | `figma_backup_output` | Where to save backups |

---

## What Gets Backed Up

### For Each File

| File | Description |
|------|-------------|
| `file_data.json` | Complete file content and structure |
| `comments.json` | All comments and replies |
| `versions.json` | Full version history |
| `components.json` | Component metadata |
| `component_sets.json` | Component set metadata |
| `styles.json` | Style definitions (colors, text, effects) |
| `thumbnail.png` | File thumbnail image |
| `image_fills/` | All images used inside the file |
| `exports/` | Exported frames as PNG/SVG/PDF (with `--export-images`) |

### For Each Team

| File | Description |
|------|-------------|
| `team_components.json` | All published team library components |
| `team_component_sets.json` | All published component sets |
| `team_styles.json` | All published team library styles |

---

## Incremental Backup

When you run the tool more than once, it automatically detects your previous backup and **only downloads files that have changed** since then. Unchanged files are copied locally from the previous backup, which is much faster.

How it works:
1. The tool finds the most recent **completed** backup in the output folder
2. Compares the `last_modified` date of each file from Figma with the previous backup
3. **Changed** files are downloaded fresh from the API
4. **Unchanged** files are copied from the previous backup (no API calls needed)

The summary table at the end shows how many files were copied vs. downloaded:
```
Unchanged (Copied)    65
Files                  3
```

> **Note:** The first backup always downloads everything. Incremental mode kicks in from the second backup onward.

---

## Retry & Verification

### Automatic Retry

If a download fails (network timeout, server error), the tool:
1. **Retries each API call up to 3 times** with exponential backoff (1s, 2s, 4s)
2. Handles Figma's `429 Too Many Requests` by waiting the specified time
3. After all items are processed, **automatically retries all failed items** one more time

### Final Verification

When the backup finishes, the tool verifies that every item was saved correctly:
- **All OK** → `[OK] Backup completed successfully! All items verified.`
- **Some failed** → `[!] WARNING X item(s) still failed after retry. See: backup.log`

If items still failed, you can:
- Run the tool again (it will resume and retry failed items)
- Check `backup.log` inside the backup folder for detailed error messages

---

## Resume Capability

If your backup gets interrupted (network error, power outage, Ctrl+C), don't worry! Just run the tool again:

```bash
./figma-backup.sh
```

It will:
1. Detect the incomplete backup automatically
2. Ask: **"Incomplete backup found. Resume?"**
3. If you say yes, it skips everything already downloaded
4. Continues from exactly where it stopped

> The progress is saved in a `.backup_manifest.json` file inside each backup folder.

---

## Backup Directory Structure

```
figma_backup_output/
  2024-01-15_14-30/                  # Timestamp of when backup started
    .backup_manifest.json            # Progress tracking (for resume)
    teams/
      My Team/
        team_info.json
        team_components.json
        team_component_sets.json
        team_styles.json
        Project Name/
          project_info.json
          Design File/
            file_data.json           # Full file content
            comments.json            # All comments
            versions.json            # Version history
            components.json          # Components in this file
            component_sets.json      # Component sets
            styles.json              # Styles
            thumbnail.png            # Thumbnail
            image_fills/             # Images used in the file
              abc123.png
              def456.jpg
            exports/                 # Frame exports (optional)
              png/
                0-1.png
              svg/
                0-1.svg
```

---

## Rate Limits

The tool automatically manages [Figma API rate limits](https://www.figma.com/developers/api#rate-limits) so you don't have to worry about them:

| Tier | What it covers | Speed |
|------|---------------|-------|
| Tier 1 | Files, images, versions | ~10 requests/min |
| Tier 2 | Teams, projects, comments | ~30 requests/min |
| Tier 3 | Components, styles | ~50 requests/min |

If a rate limit is hit, the tool automatically waits and retries. No action needed from you.

> **Note:** For large accounts with many files, the backup may take a while due to these limits. The progress bar shows estimated time remaining.

---

## Troubleshooting

### "Python was not found"
Install Python from [python.org/downloads](https://www.python.org/downloads/). On Windows, make sure to check **"Add Python to PATH"** during installation.

### "FIGMA_TOKEN is required"
You need to create a `.env` file. Copy the example: `cp .env.example .env` and fill in your token.

### "Invalid Figma token"
Your token might be expired or incorrect. Generate a new one from [Figma Settings](https://www.figma.com/settings) under "Personal access tokens".

### "No teams found"
Check that your team ID is correct. See [Finding Your Team ID](#finding-your-team-id).

### Backup is slow
This is normal for large accounts. Figma's API has rate limits (see [Rate Limits](#rate-limits)). The progress bar shows estimated time remaining. You can also use `--no-comments --no-versions` to speed things up.

### Backup was interrupted
Just run the tool again! It will ask if you want to resume. See [Resume Capability](#resume-capability).

---

## License

MIT -- see [LICENSE](LICENSE) for details.
