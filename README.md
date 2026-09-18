# UBC MCP

A suite of MCP (Model Context Protocol) tools for platforms used by UBC professors and students, such as Canvas and CWL.

> **Disclaimer:** This is an unofficial, community-built project and is not affiliated with, endorsed by, or supported by the University of British Columbia (UBC). Use at your own risk and in accordance with UBC's terms of service.

## Status

Early development. Currently implemented:

- `src/cwl.py` — automates CWL (Campus-Wide Login) authentication via Selenium.
- `canvas.py` — placeholder for upcoming Canvas integration.

## Requirements

- Python 3.9+
- Google Chrome (for Selenium's Chrome WebDriver)

## Setup

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root with your CWL credentials:

   ```
   CWL_USERNAME=your_username
   CWL_PASSWORD=your_password
   ```

## Usage

Run the CWL login script directly to test authentication:

```powershell
python src/cwl.py
```

## Project Structure

```
canvas.py        # Canvas MCP tools (in progress)
requirements.txt # Python dependencies
src/
  cwl.py         # CWL login automation
```

## Roadmap

- [ ] Canvas API integration (`canvas.py`)
- [ ] Expose tools via an MCP server
- [ ] Additional UBC platform integrations
