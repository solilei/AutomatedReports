# Running the proof of concept locally

This guide takes a new computer to a working copy of the Cadet Soft Skills app. Only that computer can open the site (`http://127.0.0.1:8000`). Other computers on the network cannot open it. The project is local only for now. Hosting for colleagues is on hold.

To show the app to a new audience, use **"Showcase on a new PC"** in `README.md`. It has the demo accounts and a walkthrough, one step at a time. This guide gives the details behind those steps.

Use **fake cadet names only**. The sample rosters in `samples/` are fake.

---

## 1. Requirements

| Item | Notes |
|---|---|
| Python 3.14 | The project uses this version for development and tests. Download it from python.org. On Windows, select **"Add python.exe to PATH"** in the installer. |
| The project folder | Copy it from a computer that has it. The GitHub copy contains the program, the sample rosters, `README.md` and this guide. It does not contain `SHOWCASE_CREDENTIALS.md` or the tests. |
| An authenticator app (optional) | For example Microsoft Authenticator or Google Authenticator. You need it only if MFA stays on (section 5). |

You do not need a database server. The app uses SQLite, which keeps all data in one file (`db.sqlite3`) in the project folder.

> **Do not put the project folder in a folder that OneDrive syncs.** If OneDrive syncs the SQLite file while the app writes to it, the database can become damaged. OneDrive would also copy cadet data to cloud storage. Use a plain local folder, for example `C:\Dev\AutomatedReports` or `~/Dev/AutomatedReports`.

## 2. Get the code

1. Copy the project folder to a plain local folder (see the OneDrive warning above).
2. Do not copy `.venv` or `db.sqlite3`. The next steps make new ones.
3. Open a terminal in the folder.

A clone from GitHub (`git clone <repository URL> AutomatedReports`) gives a working program, the sample rosters, `README.md` and this guide. It does not give `SHOWCASE_CREDENTIALS.md` or the tests.

## 3. Make the virtual environment and install the packages

A virtual environment is a private folder of Python packages for this project only. It keeps these packages separate from all other Python packages on the computer.

**Windows (PowerShell)**
```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If PowerShell does not run the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` one time. Then try again.

**macOS / Linux**
```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The prompt now starts with `(.venv)`. In each new terminal, activate the environment again before you run a `python manage.py ...` command.

## 4. Make the database

```bash
python manage.py migrate
```

This command makes `db.sqlite3` with all the tables. You can run it again at any time. It applies only new changes.

## 5. Select MFA on or off

MFA (multi-factor authentication) adds a second check at sign-in. After the password, the site asks for a 6-digit code from an authenticator app.

- **MFA on (default).** At first sign-in, the site shows a QR code. Scan it with the authenticator app. Then type the code that the app shows.
- **MFA off (easier for quick tests).** In the terminal that starts the server, set the environment variable `MFA_REQUIRED` to `false`:

  ```powershell
  # Windows PowerShell
  $env:MFA_REQUIRED = "false"
  ```
  ```bash
  # macOS / Linux
  export MFA_REQUIRED=false
  ```

The setting stays until you close that terminal. When `DJANGO_DEBUG` is off, the site always keeps MFA on. Thus you can disable MFA only on a development computer.

## 6. Make the first admin

```bash
python manage.py createadmin --username admin --full-name "Demo Admin"
```

The command shows a temporary password **one time**. Copy it. At first sign-in, you set your own password. The password must have at least 12 characters. It must not be too common or all numbers.

## 7. Load the demo data (optional, recommended)

```bash
python manage.py seed_demo
```

This command adds the three sample rosters to the ATPL programme (groups C216, C217 and C218, with 44 fake cadets). It also makes two instructors, `alex` (Meteorology, Air Law) and `sam` (Meteorology, General Navigation). It saves three score sets for C216. Sam's General Navigation set stays missing on purpose. The command shows each instructor's temporary password **one time**. Copy both. It runs only on a database with no groups.

To start again from an empty database, stop the server, delete `db.sqlite3` and run `python manage.py migrate`. The new database holds the ATPL programme and its 13 subjects.

The site has one admin only. To give the admin role to another account, run `python manage.py transferadmin --to <username>`. The target account must be an active, approved instructor.

## 8. Start the server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000** in a browser. To stop the server, press `Ctrl+C`.

Never start the server with `0.0.0.0` or another address. Other computers on the network could then open the site. The proof of concept must not allow that.

## 9. Try the app

For a full demo with named accounts, use the walkthrough in `README.md` ("Showcase on a new PC"). A short version:

1. Sign in as `admin` with the temporary password. Set your own password. If MFA is on, scan the QR code.
2. **Instructors:** if you loaded the demo data, sign in as `alex` or `sam` with the temporary password from `seed_demo`. To make a new instructor, open *Accounts* → *Create local account*. The site shows the temporary password one time. An instructor can score a subject only after the admin assigns it (*Accounts* → *Subjects*).
3. **Scoring:** on *Home*, select a group (for example C216) and press *Open*. Select a subject and press *Score*. Enter scores from 1 to 5 and comments. Press *Save*. The site fills blank cells with 3 and asks you to check them. Press *Confirm and save*. If the group was locked, or its cadet list changed, while the page was open, the site saves nothing. The page tells you why and keeps what you entered.
4. **Results:** on the group page, open *Results*. It shows the averages, totals, colours and flags. If a saved set has no row for a cadet (for example, a cadet added after the save), that set counts as 3. A cadet shows "no data" only when no saved set covers a subject that the cadet takes.
5. **Export (admin):** on the group page, press *Export report*. The browser downloads the `.xlsx` file.
6. **Roster upload (admin):** open *Upload roster*. Select an `.xlsx` file from `samples/` and type a **new** group number (for example `C300`). Press *Upload*. Select the Name column and press *Continue*. Check the preview and press *Confirm and apply*.
7. **Locking and archiving (admin):** use the *Lock* and *Archive* buttons on the group page. A locked group is read-only for everyone.
8. **Programmes (admin):** open *Programmes* to add a programme, its subjects and an optional group-number prefix. You can change the prefix only while the programme has no groups.
9. **Audit log (admin):** the audit log lists each of the changes above.

## 10. Run the tests

```bash
python manage.py test
```

All tests must pass. The tests use a separate temporary database. They do not change `db.sqlite3`.

## 11. Password resets

The site has no "forgot password" link and sends no email. An admin resets passwords. You can also reset a password from the command line on the computer that runs the app.

### A user forgot their password, lost their authenticator app, or has a locked account
1. Sign in as an admin and open **Accounts**.
2. Press **Reset** on the user's row. The button shows only for local accounts. Users of Microsoft accounts change their passwords through Microsoft.
3. The site shows a new **temporary password one time**. Give it to the user.

The reset also:
- unlinks the user's authenticator app. If MFA is on, the user scans a new QR code at the next sign-in.
- clears the sign-in lock (see below).
- makes the user set a new password at the next sign-in.

The audit log records the reset.

### The sign-in lock
After **5 wrong passwords or authenticator codes in a row**, the site locks the account for **15 minutes**. During this time, the correct password also does not work. The sign-in page then shows "Too many failed sign-in attempts". Wait 15 minutes, or ask an admin to press **Reset**. The audit log records each lock.

### The only admin forgot their password
In the project folder, with the virtual environment active, run this command:

```bash
python manage.py changepassword admin
```

The command asks for the new password two times. Then sign in with the new password. The authenticator app stays linked. If the account is locked, wait 15 minutes.

### The only admin lost their authenticator app
`changepassword` does not unlink the authenticator app. `createadmin` cannot help either, because it does not work when an admin already exists. Hand the admin role to another account for a short time:
1. Give the admin role to an active, approved instructor, for example `alex`. The old admin becomes an instructor.

   ```bash
   python manage.py transferadmin --to alex
   ```
2. Sign in as `alex`. Press **Reset** on the old admin's row in **Accounts**. Copy the temporary password.
3. Give the admin role back:

   ```bash
   python manage.py transferadmin --to admin
   ```
4. Sign in as `admin` with the temporary password. Set a new password and scan the new QR code.

The audit log records each hand-over and the reset. For local tests, you can also disable MFA for the session (`MFA_REQUIRED=false`, section 5).

### Test data only
If the data is fake and you do not need it, delete `db.sqlite3` and start again (section 12).

## 12. Start again with an empty database

1. Stop the server.
2. Delete `db.sqlite3`.
3. Do steps 4, 6 and 7 again.

## 13. Settings for local use

All settings are environment variables. `README.md` has the full list. These settings are useful locally:

| Variable | Example | Effect |
|---|---|---|
| `MFA_REQUIRED` | `false` | The site does not ask for the authenticator code (local use only). |
| `DJANGO_TIME_ZONE` | `Europe/London` | The time zone for dates in the audit log and the export. The default is `Etc/GMT-8` (UTC+8). |
| `ROSTER_MAX_UPLOAD_BYTES` | `5242880` | The largest roster file that the site accepts (default 5 MB). |

Keep `LOGIN_MODE` set to `local`. Microsoft sign-in needs an Entra app registration from IT. That work is on hold with hosting. The hosting notes (`docs/HOSTING.md`) are a local file that is not on GitHub.

Each time an admin opens the upload page, the site discards unfinished roster uploads that are older than 24 hours. The command `python manage.py discard_stale_uploads` does the same task at any time. Local use does not need a schedule for it.

## 14. Troubleshooting

| Problem | Solution |
|---|---|
| The terminal cannot find `python` or `py` | Python is not on PATH. Install Python again with "Add to PATH" selected, or use the full path to `python.exe`. |
| `No module named django` | The virtual environment is not active. Run the activate command from step 3. |
| `no such table` | Run `python manage.py migrate`. |
| `seed_demo` shows `Database already has groups` | The demo data is already in the database. To start again, delete `db.sqlite3` and run `migrate` (section 7). |
| `That port is already in use` | A different server is running. Stop it, or run `python manage.py runserver 127.0.0.1:8001`. |
| You lost the temporary admin password | Run `python manage.py changepassword admin` (section 11). |
| "Too many failed sign-in attempts" | Wait 15 minutes, or ask an admin to press *Reset* on the account (section 11). |
| The site always rejects the authenticator code | Make sure that the phone sets its clock automatically. The codes depend on the exact time. |
| The site signed you out | A session ends after 30 minutes without activity, or when the browser closes. |
