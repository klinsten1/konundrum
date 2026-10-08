# Deploying Konundrum on PythonAnywhere

This guide gets the app running on a free PythonAnywhere account. It assumes the
project is in a Git repository (recommended) or that you'll upload the files.

> Note on Python version: your local machine runs Python 3.14, but PythonAnywhere
> currently offers older versions (around 3.10–3.13, depending on your account's
> system image). That's fine — the app uses only standard Flask + `sqlite3`, so
> any 3.10+ version works. You do **not** upload your local `.venv`; you create a
> fresh virtualenv on PythonAnywhere.

---

## 1. Create an account

Sign up for a free "Beginner" account:
- EU: https://eu.pythonanywhere.com/
- Rest of the world: https://www.pythonanywhere.com/

Confirm your email. Note your username — your site will live at
`https://<username>.pythonanywhere.com`.

## 2. Get the code onto PythonAnywhere

Open a **Bash console** from the Dashboard, then either clone from Git:

```bash
git clone <your-repo-url> konundrum
```

…or, if you don't use Git, upload the project as a `.zip` via the **Files** tab
and unzip it in the console:

```bash
unzip konundrum.zip -d konundrum
```

You should end up with a folder like `/home/<username>/konundrum` containing
`app.py`, `database.py`, `wsgi.py`, `templates/`, `challenges/`, etc.

> Do **not** upload `konundrum.db` or your local `.venv` (both are in
> `.gitignore`). The database is created automatically on first run.

## 3. Create a virtualenv and install dependencies

In the Bash console (pick a Python version your account supports, e.g. 3.13):

```bash
cd ~/konundrum
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Note the full path printed for the virtualenv — you'll need it:
`/home/<username>/konundrum/.venv`.

## 4. Create the web app

1. Go to the **Web** tab → **Add a new web app**.
2. Choose **Manual configuration** (not the "Flask" quickstart — we have our own
   WSGI file). Pick the same Python version you used for the virtualenv.
3. After it's created, scroll to the settings and fill in:
   - **Source code**: `/home/<username>/konundrum`
   - **Working directory**: `/home/<username>/konundrum`
   - **Virtualenv**: `/home/<username>/konundrum/.venv`

## 5. Point the WSGI file at the app

On the **Web** tab, click the **WSGI configuration file** link. Delete the
sample contents and replace them with:

```python
import os, sys

project_dir = "/home/<username>/konundrum"   # <-- change <username>
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# A strong secret for sessions. Generate one with:
#   python -c "import secrets; print(secrets.token_hex(32))"
os.environ.setdefault("SECRET_KEY", "PASTE-A-LONG-RANDOM-STRING-HERE")

from app import app as application, bootstrap
bootstrap()
```

Save it.

> This mirrors the project's own `wsgi.py`. You use PythonAnywhere's WSGI editor
> because it needs the absolute project path and your secret key.

## 6. Set the secret key properly

The line above sets `SECRET_KEY` inline, which is the simplest approach on
PythonAnywhere. Generate a real value once in the Bash console and paste it in:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Never leave it as the placeholder, and don't commit the real key to Git.

## 7. Reload and visit

Click the big green **Reload** button on the **Web** tab, then open
`https://<username>.pythonanywhere.com`. You should see the login page.

## 8. First login + lock down admin

The app seeds a default admin on first run:

- username: `admin`
- password: `admin123`

**Change it immediately**: log in, go to **Stats** (profile page), and use the
**Change password** card. `admin123` must not stay on a public site.

---

## Where your data lives

- Database: `konundrum.db` is created in the project folder on first run.
  PythonAnywhere's disk is persistent, so your data and admin edits survive
  reloads and restarts. (This is why PythonAnywhere suits this app better than
  ephemeral "serverless" hosts.)
- Content and puzzle files: `templates/home_content.html`,
  `templates/about_content.html`, and `challenges/*.html` are created if missing
  and edited live via the admin pages. They persist too.

## Updating the app later

```bash
cd ~/konundrum
git pull                 # or re-upload changed files
source .venv/bin/activate
pip install -r requirements.txt   # only if dependencies changed
```

Then hit **Reload** on the **Web** tab. The `bootstrap()` call runs the safe
database migrations automatically, so schema changes are applied without losing
existing data.

## Backups

To download a copy of your live data, use the **Files** tab to download
`konundrum.db`, or from a Bash console:

```bash
cp ~/konundrum/konundrum.db ~/konundrum_backup_$(date +%F).db
```

## Troubleshooting

- **500 error / "Something went wrong"**: open the **Error log** link on the Web
  tab — it shows the Python traceback.
- **Changes don't show up**: you forgot to hit **Reload** on the Web tab.
- **ImportError**: check that the Virtualenv path and Source code path on the Web
  tab are correct, and that `pip install -r requirements.txt` ran inside the
  activated virtualenv.
