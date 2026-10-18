# Demo Guide and Command Cheat Sheet

All commands are for **PowerShell**, run from the project folder:

```powershell
cd C:\Users\Bhavya\Downloads\library-management-system\library-management-system
```

Published image name: `ghcr.io/bhavyaparti11/library-management-system`

---

## 1. Command cheat sheet

### Development mode (live code, no rebuilds)

```powershell
.\scripts\dev.ps1            # start: http://localhost:5000
docker compose logs -f       # watch the dev server logs (Ctrl+C to stop watching)
.\scripts\dev.ps1 -Stop      # stop dev mode
docker start library-app     # bring the normal container back afterwards
```

### Tests

```powershell
.\.venv\Scripts\Activate.ps1     # once per terminal; the prompt shows (.venv)
pytest                           # expect: 23 passed
```

### Images, containers, logs, health

```powershell
docker images library-app                      # local images and tags
docker ps                                      # running containers
docker ps -a                                   # all containers, including stopped
docker logs --tail 30 library-app              # last 30 log lines
docker logs -f library-app                     # follow logs live (Ctrl+C to stop)
Invoke-RestMethod http://localhost:5000/health # {"database":"connected","status":"ok","version":...}
Invoke-RestMethod http://localhost:5000/api/books | Format-Table id, title, status
```

### Build and run the production image from local code

```powershell
.\scripts\update-local.ps1 -Build    # docker build + safe container swap + health check
```

Doing it by hand (what the script does for you):

```powershell
docker build -t library-app:local .
docker stop library-app
docker rm library-app                # removes the CONTAINER only, never the volume
docker run -d --name library-app --restart unless-stopped -p 127.0.0.1:5000:5000 -v library-data:/app/data library-app:local
```

### Pull and run the image published by GitHub Actions

```powershell
.\scripts\update-local.ps1                     # newest "latest"
.\scripts\update-local.ps1 -Tag sha-1a2b3c4    # one exact version (tag from the Actions summary)
.\scripts\update-local.ps1 -Watch              # check every 60 s and update automatically
```

### Database volume (your books)

```powershell
docker volume ls                       # library-data should be listed
docker volume inspect library-data
docker cp library-app:/app/data/library.db .\library-backup.db    # make a backup copy
```

> **Never** run `docker volume rm library-data` or `docker compose down -v`:
> those delete every book. Removing or recreating a *container* is always safe.

### Git and GitHub Actions

```powershell
git status                          # what changed
git add .
git commit -m "Describe the change"
git push                            # starts the GitHub Actions pipeline
```

Then open **https://github.com/bhavyaparti11/library-management-system/actions**.
If you have the GitHub CLI: `gh run list` and `gh run watch`.

### Going back to the original version 1 image (if ever needed)

```powershell
docker stop library-app; docker rm library-app
docker run -d --name library-app -p 127.0.0.1:5000:5000 -v library-data:/app/data library-app:v1
```

---

## 2. One-time GitHub setup for image publishing

Publishing uses the automatic `GITHUB_TOKEN`. No password or secret is stored
anywhere, so there is nothing to add under *Settings > Secrets*.

1. **Allow the workflow to write packages.** Repository > **Settings** >
   **Actions** > **General** > *Workflow permissions*. Either option works because
   `ci.yml` asks for `packages: write` itself, but if publishing fails with
   `denied: permission_denied`, choose **Read and write permissions** and save.
2. **Push to `main` once.** The first successful run creates the package.
3. **Make the package public** so your laptop can pull it without logging in:
   your GitHub profile > **Packages** > `library-management-system` >
   **Package settings** > **Change visibility** > **Public**.

   *Alternative (keep it private):* create a Personal Access Token (classic)
   with only the `read:packages` scope, then run `docker login ghcr.io -u bhavyaparti11`
   and paste the token as the password. Never commit the token to Git.

---

## 3. Demonstration sequence

**Before the demo:** start Docker Desktop and wait for *Engine running*.

| # | Show | Do this |
|---|------|---------|
| 1 | Redesigned site | `.\scripts\dev.ps1`, open http://localhost:5000. Show the dashboard cards, filters, search, a book page, issue + return, the 404 page (`/books/9999`). Sidebar says **dev (live code)**. |
| 2 | Code change | In VS Code, edit `templates/index.html`: change `<h1>Library Dashboard</h1>` to `<h1>College Library Dashboard</h1>`. Or in `static/style.css` change `--blue-600: #2563eb;` to `--blue-600: #7c3aed;` (buttons turn purple). Save. |
| 3 | Instant update | Refresh the browser: the change appears. **No image rebuild.** |
| 4 | Push | `.\scripts\dev.ps1 -Stop`, then `pytest`, then `git add .`, `git commit -m "Demo change"`, `git push`. Open the **Actions** tab. |
| 5 | Tests pass | Click the run: job **Run automated tests** goes green (23 tests). |
| 6 | Image built + validated | Job **Build, test and publish Docker image**: the *Build* step, then the *Test:* steps (health, version, pages, 404, add book). |
| 7 | Publication | The *Publish* steps push `:sha-xxxxxxx` and `:latest`. The run **Summary** shows the image names. The package appears under your profile > Packages. |
| 8 | Run it locally | `.\scripts\update-local.ps1`. The sidebar now shows **sha-xxxxxxx**, the same commit as on GitHub. Your books are still there. |

---

## 4. Explaining it to your teacher

**What is the project?** A Flask web app for a library (add, search, issue,
return, delete books) that stores data in SQLite. It runs inside a Docker
container, and every change is automatically tested and packaged by GitHub Actions.

**Why didn't `git push` update my laptop before?** GitHub Actions runs on
GitHub's computers, not on my laptop. It builds a *new* image there, but my
laptop kept running the *old* container. Nothing connected the two.

**How is that fixed now?**
- For *development*, I don't need the pipeline to see changes: dev mode mounts
  my code folder into the container, so saving a file updates the running app.
- For *releases*, the pipeline publishes the tested image to GitHub Container
  Registry, and `update-local.ps1` pulls that exact image and swaps my container.

**Can GitHub update my laptop directly?** No. GitHub cannot reach into my
laptop. Something on the laptop must *pull*. `update-local.ps1 -Watch` does that
automatically by checking the registry every minute. (A self-hosted runner could
also do it, but that means running a GitHub agent on my laptop, which is more
complex and a security risk for a student project.)

**Image vs container vs volume?**
- *Image* = a frozen package of the app and everything it needs (like a class).
- *Container* = a running copy of an image (like an object). You can delete
  and recreate it at any time.
- *Volume* = storage that lives outside the container. My database is in the
  `library-data` volume, so replacing the container never loses books.

**What do the four kinds of "update" mean?**

| Action | When it's needed | Speed |
|--------|------------------|-------|
| Refresh the browser | Template, CSS or JS changed (dev mode) | Instant |
| Restart the Flask app | `app.py` changed (dev mode does it automatically) | ~1 s |
| Rebuild the image | Dependencies or `Dockerfile` changed, or making a release | ~10-60 s |
| Recreate the container | To start running a different image | ~5 s |

**Why two setups (dev and production)?** Dev mode uses Flask's debug server,
which reloads code but is not secure or fast enough for real users. The
production image uses Gunicorn, runs as a non-root user, contains a fixed copy
of the code, and is the exact thing that was tested in CI.

**What does CI/CD stand for here?** *Continuous Integration*: every push is
tested automatically. *Continuous Delivery*: every successful push to `main`
produces a versioned, ready-to-run image. I deliberately don't *deploy* to the
cloud; my laptop pulls the image instead.

**Why tag with the commit SHA?** `latest` always moves to the newest image,
but `sha-1a2b3c4` points to exactly one commit forever, so I can always tell
(and prove, from the sidebar or `/health`) which code is running, and go back
to an older version.

**What stops broken code being published?** The `docker` job has `needs: test`,
so it only runs if pytest passed. Within it, the publish steps come after the
smoke tests, so a failed check stops the job before anything is pushed. Pull
requests are tested but never published.
