# Running the proof of concept locally

This guide takes you from a fresh machine to a working copy of the Cadet Soft Skills app on your own computer. The site is reachable only from that computer (`http://127.0.0.1:8000`). Nobody else on the network can open it.

Use **fake cadet names only**. The sample rosters in `samples/` are fake.

---

## 1. What you need

| Item | Notes |
|---|---|
| Python 3.14 | The version the project is built and tested on. Download from python.org. On Windows, tick **"Add python.exe to PATH"** in the installer. |
| Git | To get the code. Or download the project as a ZIP and unzip it. |
| An authenticator app (optional) | Microsoft Authenticator, Google Authenticator or similar. Only needed if you keep MFA switched on (section 5). |

No database server is needed. The app uses SQLite, which keeps everything in one file (`db.sqlite3`) in the project folder.

> **Do not put the project folder inside a OneDrive-synced folder.** OneDrive syncing a SQLite file while the app writes to it can corrupt the database, and it would copy cadet data into cloud storage. Use a plain local folder such as `C:\Dev\AutomatedReports` or `~/Dev/AutomatedReports`.

## 2. Get the code

```bash
git clone <repository URL> AutomatedReports
cd AutomatedReports
```

## 3. Create the virtual environment and install packages

A virtual environment is a private folder of Python packages for this project only, so it doesn't clash with anything else on the machine.

**Windows (PowerShell)**
```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If PowerShell refuses to run the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

**macOS / Linux**
```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Your prompt now starts with `(.venv)`. Activate it again in every new terminal before running any `python manage.py ...` command.

## 4. Create the database

```bash
python manage.py migrate
```

This creates `db.sqlite3` with all the tables. Running it again later is safe; it only applies new changes.

## 5. Choose whether MFA is on

MFA (multi-factor authentication) means that after the password, the site also asks for a 6-digit code from an authenticator app.

- **MFA on (default).** At first sign-in the site shows a QR code. Scan it with your authenticator app and type the code it shows.
- **MFA off (easier for quick testing).** Set the environment variable `MFA_REQUIRED` to `false` in the terminal where you start the server:

  ```powershell
  # Windows PowerShell
  $env:MFA_REQUIRED = "false"
  ```
  ```bash
  # macOS / Linux
  export MFA_REQUIRED=false
  ```

The setting lasts until that terminal is closed. MFA is always forced on when `DJANGO_DEBUG` is off, so you can only switch it off on a development machine.

## 6. Create the first admin

```bash
python manage.py createadmin --username admin --full-name "Demo Admin"
```

It prints a temporary password **once**. Copy it. You choose your own password at first sign-in (at least 12 characters, not too common, not all numbers).

## 7. Load the demo data (optional, recommended)

```bash
python manage.py seed_demo
```

This adds the subjects Air Law, Meteorology and Navigation and the three sample rosters (groups C216, C217, C218; 44 fake cadets). It only runs on a database with no groups.

## 8. Start the server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000** in a browser. Stop the server with `Ctrl+C`.

Never start it with `0.0.0.0` or another address. That would make it reachable from the network, which the proof of concept must not be.

## 9. Try it out

1. Sign in as `admin` with the temporary password, then set your own password (and scan the QR code if MFA is on).
2. **Instructors:** go to *Accounts* → *Create local account*, and create an instructor. The temporary password is shown once on screen; give it to the person (or open a private browser window and sign in as them).
3. **Scoring:** on *Home*, pick a group (e.g. C216) and press *Open*. Choose a subject and press *Score*. Enter scores 1–5 and comments, then press *Save*.
4. **Results:** on the group page, open *Results* to see averages, totals, colours and flags.
5. **Export (admin):** on the group page, choose *Export report* to download the `.xlsx` file.
6. **Roster upload (admin):** *Upload roster*, choose an `.xlsx` file from `samples/`, type a **new** group number (e.g. `C300`), pick the Name column (and Cadet ID column), check the preview, and confirm.
7. **Locking and archiving (admin):** use the *Lock* / *Archive* buttons on the group page. A locked group is read-only for everyone.
8. **Audit log (admin):** every change above is listed there.

## 10. Run the tests

```bash
python manage.py test
```

All tests should pass. They use a separate temporary database and don't touch `db.sqlite3`.

## 11. Resetting passwords

There is no "forgot password" link and no email. Passwords are reset by an admin, or from the command line on the machine running the app.

### A user forgot their password, lost their authenticator, or is locked out
1. Sign in as an admin and open **Accounts**.
2. Press **Reset** on the user's row. (The button only appears for local accounts. Microsoft accounts reset their passwords through Microsoft.)
3. The site shows a new **temporary password once**. Give it to the user.

The reset also:
- removes their authenticator app, so they scan a new QR code at the next sign-in (if MFA is on);
- clears the sign-in lock (see below);
- makes them choose a new password at the next sign-in.

The reset is recorded in the audit log.

### The sign-in lock
After **5 wrong passwords or authenticator codes in a row**, the account is locked for **15 minutes**, even with the right password. The sign-in page then says "Too many failed sign-in attempts". Either wait 15 minutes or ask an admin to press **Reset**. Locks are recorded in the audit log.

### The only admin forgot their password
Use the command line in the project folder, with the virtual environment active:

```bash
python manage.py changepassword admin
```

It asks for the new password twice. You then sign in with it as normal. Your authenticator app stays linked. If the account is locked, wait 15 minutes.

### The only admin lost their authenticator app
`changepassword` doesn't remove the authenticator link. Instead, create a second admin, sign in as them, and **Reset** the first:

```bash
python manage.py createadmin --username admin2 --full-name "Backup Admin"
```

Or, while testing locally, switch MFA off for the session (`MFA_REQUIRED=false`, section 5).

### Throwaway test data only
If none of this matters because the data is fake, delete `db.sqlite3` and start again (section 12).

## 12. Start again from scratch

Stop the server, delete `db.sqlite3`, then repeat steps 4, 6 and 7.

## 13. Settings you might change locally

All settings are environment variables; the full list is in `README.md`. The useful ones locally:

| Variable | Example | Effect |
|---|---|---|
| `MFA_REQUIRED` | `false` | Skip the authenticator code (local only). |
| `DJANGO_TIME_ZONE` | `Europe/London` | Time zone for dates in the audit log and export. Default is `Etc/GMT-8` (UTC+8). |
| `ROSTER_MAX_UPLOAD_BYTES` | `5242880` | Largest roster file accepted (default 5 MB). |

Leave `LOGIN_MODE` at `local`. Microsoft sign-in needs an Entra app registration from IT; see `docs/HOSTING.md`.

## 14. Troubleshooting

| Problem | Fix |
|---|---|
| `python` or `py` not found | Python isn't on PATH. Reinstall with "Add to PATH" ticked, or use the full path to `python.exe`. |
| `No module named django` | The virtual environment isn't active. Run the activate command from step 3. |
| `no such table` | Run `python manage.py migrate`. |
| `Database already has groups` from `seed_demo` | Demo data is already loaded. Delete `db.sqlite3` to start again. |
| `That port is already in use` | Another server is running. Stop it, or use `python manage.py runserver 127.0.0.1:8001`. |
| Lost the temporary admin password | Run `python manage.py changepassword admin` (section 11). |
| "Too many failed sign-in attempts" | Wait 15 minutes, or an admin presses *Reset* on the account (section 11). |
| Authenticator code always rejected | Check the phone's clock is set automatically. Codes depend on the exact time. |
| Signed out unexpectedly | Sessions end after 30 minutes without activity, or when the browser closes. |
