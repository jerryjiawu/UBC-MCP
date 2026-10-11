# Screenshot Viewer

Retrieves your most recent Windows screenshot from a small cloud-hosted
Flask server, previews it on your iPhone, and lets you copy it to the
clipboard or save it to Photos — with no Mac, Xcode, or app compiling
required.

## How it works

```
Windows PC                    Cloud (DigitalOcean App Platform)         iPhone
-----------                   ---------------------------------         ------
uploader.py  --- POST /upload --->   Flask server (app.py)   <--- GET /screenshot --- Scriptable script
(watches Pictures\Screenshots)        stores latest image in memory       (Copy to Clipboard / Save to Photos)
```

Both the upload and download endpoints require a shared secret key
(`X-API-Key` header), and DigitalOcean App Platform gives you free HTTPS, so
the key and image are encrypted in transit.

## 1. Generate a secret key

Run this once and save the output somewhere safe — you'll paste it into two
places below (the server's env var, and the uploader's `.env`), plus the
iOS script:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 2. Push this folder to GitHub

DigitalOcean App Platform deploys from a GitHub repo.

```powershell
cd "c:\Users\itsro\OneDrive\Documents\UBC MCP"
git add screenshot-app
git commit -m "Add screenshot viewer app"
git push
```

(If `UBC MCP` isn't already pushed to GitHub, create a repo on GitHub first
and `git remote add origin <url>`.)

## 3. Deploy the server on DigitalOcean App Platform

1. Go to <https://cloud.digitalocean.com/apps> and click **Create App**.
2. Choose **GitHub** as the source, pick your repo/branch.
3. When asked for the source directory, set it to `screenshot-app/server`.
4. App Platform should auto-detect Python. Set the **Run Command** to:
   ```
   gunicorn app:app --bind 0.0.0.0:8080
   ```
5. Under **Environment Variables**, add:
   - Key: `API_SECRET`
   - Value: the secret key you generated in step 1
   - Type: **Encrypted**
6. Pick the smallest instance size (Basic, ~$5/mo) and deploy.
7. Once deployed, note your app's URL, e.g.
   `https://screenshot-app-xxxxx.ondigitalocean.app`.
8. Verify it's up: visit `https://<your-app-url>/health` — you should see
   `{"status": "ok"}`.

(Alternatively, if you have `doctl` installed, edit `.do/app.yaml` with your
repo name and run `doctl apps create --spec .do/app.yaml`.)

## 4. Set up the Windows uploader

```powershell
cd "c:\Users\itsro\OneDrive\Documents\UBC MCP\screenshot-app\windows-uploader"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env   # fill in SERVER_URL (your app's URL) and API_SECRET
```

`SCREENSHOT_DIR` can be left blank — it auto-detects both the OneDrive-redirected
Pictures folder and the plain default, so it works whether or not OneDrive is
managing your Pictures folder.

Test it manually:

```powershell
.venv\Scripts\python uploader.py
```

It uses filesystem events (not polling), so a screenshot taken with
**Win+PrtScn** is uploaded within about a second — watch for an `[uploaded]`
line in the console. Press Ctrl+C to stop.

### Running it inside this project (recommended if you use mcp_manager.py)

This project's `mcp_manager.py` already manages its other background
services (Discord bot, MCP servers, etc.) from one dashboard/tray icon, and
the uploader is registered there too as `screenshot-uploader`. Just run:

```powershell
python mcp_manager.py
```

and it starts/stops/restarts alongside everything else from the dashboard
at `http://127.0.0.1:5055` (or the tray icon) — no separate setup needed.

### Running it standalone instead

If you'd rather not use mcp_manager.py, either double-click
`run_uploader.bat` whenever you want it running, or set it to start
automatically at login:

```powershell
cd "c:\Users\itsro\OneDrive\Documents\UBC MCP\screenshot-app\windows-uploader"
.\register_startup_task.ps1
```

This registers a Scheduled Task ("ScreenshotUploader") that silently runs
the uploader every time you log in. Remove it later with:

```powershell
Unregister-ScheduledTask -TaskName "ScreenshotUploader" -Confirm:$false
```

## 5. Set up the iPhone script (Scriptable — free, no compiling)

1. Install **Scriptable** from the iOS App Store (free, official app by
   Simon Støvring).
2. Open Scriptable, tap **+** to add a new script.
3. Open [`ios/Screenshot.js`](./ios/Screenshot.js) on your computer, copy its
   entire contents, and paste them into the new Scriptable script.
4. Edit the two constants at the top of the script on your phone:
   - `SERVER_URL` → your DigitalOcean app URL from step 3.
   - `API_KEY` → the same secret key from step 1.
5. Rename the script (tap the name at the top) to e.g. "Screenshot".
6. Tap the ▶ Run button to test — it should preview your latest screenshot,
   then offer **Copy to Clipboard** / **Save to Photos** / **Copy & Save**.

### Add a one-tap Home Screen icon

Current versions of Scriptable no longer put "Add to Home Screen" in the
script list's long-press menu. The reliable way to get an icon now is
through the built-in **Shortcuts** app:

1. Open the **Shortcuts** app (pre-installed on every iPhone).
2. Go to the **My Shortcuts** tab and tap **+** (top right) to create a new
   shortcut.
3. Tap **Add Action**, search for **Scriptable**, and choose
   **Run Script in App** — NOT plain "Run Script". The plain "Run Script"
   action runs in a lightweight Siri/Shortcuts context that cannot show
   `Alert` or `QuickLook` dialogs, which is what causes the error
   "Alerts are not supported in Siri". "Run Script in App" switches to the
   actual Scriptable app so the preview and buttons work correctly.
4. Tap the script name inside that action and select your **Screenshot**
   script.
5. Tap the shortcut's name at the top ("New Shortcut") and rename it to
   **Screenshot**.
6. Tap the three-dot menu (**⋯**) in the top-right, or the small settings/
   info icon near the shortcut name, to open **Shortcut Details**.
7. Tap the icon preview to pick a custom color/glyph, then tap
   **Add to Home Screen** near the bottom of that screen.
8. Confirm the name/icon and tap **Add** (top right) — you'll now have a
   normal-looking app icon on your Home Screen that runs the script directly.

## Notes

- The server only keeps the single most recent screenshot in memory (not on
  disk), so there's nothing to clean up, but it also means the image is lost
  if the app restarts/redeploys — that's fine since the uploader will push
  the next screenshot automatically.
- This is intentionally simple (single shared secret, in-memory storage) for
  personal use. Don't reuse this server for anything containing sensitive
  data beyond casual screenshots.
- Real screenshots only land in `Pictures\Screenshots` when taken with
  **Win+PrtScn** (full-screen) or the Xbox Game Bar. The Snip & Sketch tool
  (`Win+Shift+S`) copies to clipboard but doesn't save to that folder unless
  you manually save it — if you use that tool, set `SCREENSHOT_DIR` in the
  uploader's `.env` to wherever you save your snips instead.
