# AutomatedReports

A Django web app for cadet soft-skill reports. Instructors score cadets on six soft-skill attributes. The site calculates the averages. An admin exports the filled-in Cadet Soft Skills Report (`.xlsx`).

**This is a local proof of concept.** It runs on one computer. Only that computer can open it, at `http://127.0.0.1:8000`. Hosting for colleagues is on hold. The earlier hosting notes are in `docs/HOSTING.md`, a local file that is not on GitHub. Use **fake cadet names only**. The rosters in `samples/` are fake.

More detail: [docs/RUN_LOCALLY.md](docs/RUN_LOCALLY.md) covers setup, password resets and troubleshooting.

---

## Features

### Roles
- **Admin:** can do everything that an instructor can do. An admin also manages rosters, accounts, programmes and subject assignments. An admin can lock, archive and delete groups, export reports and read the audit log.
- **Instructor:** can open the groups of a programme where the admin assigned them a subject. An instructor scores only the subjects assigned to them, and sees results only for those subjects. Instructors cannot export, manage anything or read the audit log.
- **One admin only.** The site has exactly one admin. The command `transferadmin --to <username>` hands the role to another account.

### Sign-in and accounts
- **No self-registration.** An admin creates each account. The site shows the admin a one-time temporary password. The site sends no email.
- **First admin.** Create the first admin from the command line on the PC (`createadmin`). The command does not work when an admin already exists. The website has no way to make an admin.
- **New password at first sign-in.** A password must have at least 12 characters. It must not be too common, all numbers or too similar to the username.
- **Authenticator-app MFA.** At first sign-in, the user scans a QR code. After that, the user types a 6-digit code at each sign-in. You can disable MFA for local tests. MFA is always on when debug mode is off.
- **Lockout.** 5 wrong passwords or codes in a row lock the account for 15 minutes.
- **Admin account tools:** approve (with the subjects to assign), edit subjects, deactivate, reactivate and **Reset**. Reset gives a new temporary password, clears the lock and unlinks the authenticator app.
- **Admin safeguards.** An admin cannot deactivate their own account. A web form cannot make an admin.
- **Automatic sign-out** after 30 minutes without activity, or when the browser closes.
- **"Sign in with Microsoft"** (Microsoft Entra ID): the program includes it, but it is off.
  - The site accepts only accounts from the organisation's own Microsoft tenant.
  - A first Microsoft sign-in makes a pending account. The account waits for admin approval.
  - The site stores no password for these accounts.

### Roster upload (admin)
- **Upload.** Use one `.xlsx` file (5 MB maximum) for each group. The admin types the group number, for example `C216`. A group number can contain letters, digits, `.`, `_` and `-`.
- **Column picker.** The site shows the header row and some sample rows. The admin selects the Name column; other columns are ignored, and a file with just one Name column works. The site remembers this choice for the next upload. The site skips title rows above the header row.
- **Checks.** The site rejects these problems and gives the spreadsheet row number:
  - names longer than 200 characters
  - duplicate names in the group (upper and lower case do not count as different)
- **Cadet identity:** the site matches cadets by name when a group is uploaded again. Upper and lower case do not change a name. Rows with a blank name are skipped.
- **Preview before changes.** The preview:
  - lists new cadets, cadets that are no longer in the file, returning cadets and renamed cadets
  - flags names that look like one name with a spelling change
  - shows the updated preview, and applies nothing, if the roster changed after the site showed the first preview
  - applies nothing if the programme no longer fits when the admin confirms. For example, the group now belongs to another programme, or the programme was deactivated. Discard the upload and upload the file again.
- **Discard.** An admin can discard an upload. This deletes the stored file. The site discards uploads that stay unfinished for 24 hours.
- **No silent deletion.** If a new file does not include a cadet, the site marks that cadet inactive. The site hides an inactive cadet but keeps the data. Only an admin can permanently delete a cadet.

### Groups (admin)
- **Groups page.** It shows the number of active cadets, inactive cadets and score sets for each group. Each group also has a **Manage cadets** page.
- **Statuses:**
  - **Active.**
  - **Locked:** read-only for everyone. For example, lock a group when the report goes to HGS. Only an admin can unlock a group.
  - **Archived:** read-only and not in the dropdowns. Unarchive returns the group to its previous status.
- **Permanent delete.** An admin can delete an archived group with all its data. This includes the group's unfinished uploads. It also deletes cadet names, scores and comments from the group's audit entries.
- **Group numbers.** Each group number is unique. The site never uses a group number again, even after a deletion.

### Programmes and subjects (admin)
- **Programmes.** A programme holds a list of subjects. **ATPL** is built in. It has 13 fixed subjects that nobody can rename or deactivate. The admin can add other programmes with their own subjects.
- **Group-number prefix.** A programme can have a prefix, for example `C` for ATPL. Each group number in the programme is then the prefix followed by digits. The admin can change the prefix only while the programme has no groups.
- **Groups.** Each group belongs to one programme. The admin picks the programme at upload. ATPL group numbers are `C` followed by digits (for example `C216`). The admin can change the programme of a group until it has score sets.
- **Assignments.** The admin assigns subjects to each account. An instructor sees a group only if the instructor has a subject in its programme. The admin must also be assigned a subject to score it.
- **Cadets and subjects.** Each cadet takes every subject of the programme. The admin can take a cadet off a subject (**Manage cadets** → **Subjects**).
- **Add, rename, deactivate or reactivate** a subject in other programmes. Nobody can rename a subject that a locked or archived group uses. A deactivated subject cannot start a new score set. Its existing score sets stay editable.

### Scoring (instructors and admins)
- **Sequence:** select a group, then one of your assigned subjects. Then complete a grid of the group's active cadets who take that subject.
- **Six attributes for each cadet:**
  - Attentiveness / Engagement
  - Motivation / Diligence / Enthusiasm
  - Discipline / Courtesy
  - Attire / Appearance
  - Teamwork
  - Communication / Participation / Interaction
- **Scores.** Each score is a whole number from 1 to 5, or blank:
  - 5: A, Excellent
  - 4: B, Above standard
  - 3: C, Meets standard
  - 2: D, Below standard
  - 1: E, Unacceptable

  Each cadet can also get a comment of up to 1000 characters.
- **One score set for each instructor, subject and group.** An instructor who teaches two subjects to a group saves one set for each subject.
- **Save rules:**
  - A save needs at least one score.
  - **Save** fills each blank cell with 3 on the screen and highlights the cells. The site saves nothing yet.
  - The instructor checks the cells and presses **Confirm and save**. A saved set never has blank cells.
- **Roster changes during scoring:**
  - The grid marks cadets that an admin added after the instructor's last save: "added since your last save".
  - If the cadet list changes while the page is open, the site saves nothing. The page then shows the current list and keeps the scores and comments that you entered.
  - If an admin locks the group while the page is open, the site saves nothing. The page shows "Not saved: group … is locked" and keeps what you entered.
- **My score sets** lists the score sets of the user who is signed in.
- **Shared subjects.** Two instructors can score the same subject for a group. Each of them can then see the other's score set for that subject, with scores and comments. Admins can see all score sets.

### Results
- **Table for each group:** No., name, the six attribute averages and a Total. The Total is the sum of the six averages (6–30).
- **Averages** are whole numbers. An average of exactly x.5 rounds up, so 2.5 counts as C.
- **Grade colours.** The site colours each average cell with the report's grade colour, from green (5) to red (1).
- **Flag.** The site flags a cadet **Below C – HGS consultation** if an attribute average is below 2.5.
- **Missing scores in results:**
  - If a saved set has no row for a cadet, that set counts as 3 for each attribute of the cadet. For example, a cadet added after all saves shows 3 for each attribute.
  - A cadet shows "no data" only when no saved set covers a subject that the cadet takes.
  - The table does not include inactive cadets.
- **Who sees what.** Admins see all subjects. Instructors see only the subjects assigned to them, with the score sets of all instructors of those subjects. Both can show one subject at a time.

### Missing scores
- **Rule.** Each active subject must be scored in each active group of its programme. When several instructors teach a subject, a save by any one of them clears the gap; the others may still add their own scores, and results average them. A subject is missing when no assigned instructor has saved it, or when a cadet was added after the last save and no set has a row for that cadet.
- **Admin:** a **Missing scores (N)** link in the navigation, a page that lists each gap, and a box on each group page. Locking a group with gaps works, with a warning.
- **Instructor:** the Home page lists the instructor's own missing scores, each with a link to the grid.

### Export (admin)
- **One `.xlsx` file for each group.** The file copies the layout of the Cadet Soft Skills Report template:
  - title, department, instructions and grading-system key, in the template colours
  - landscape A4
  - a sheet with the group number as its name
- **Header:** the course (the group number), each instructor who saved a score set, each subject and the export date.
- **Table:** one row for each active cadet, with coloured averages and the Total. The table does not include inactive cadets.
- **"Additional comments":** the comments, grouped by cadet, in the format *cadet name — instructor (subject): comment*.

### Audit log (admin)
- **Who, what and when for each change:**
  - score changes (old value → new value) and comment changes
  - roster uploads, applies and discards, and cadet changes
  - exports
  - account creation, approval, deactivation, resets and lockouts
  - subject assignments and programme and subject changes
  - group lock, unlock, archive and delete
  - cadet deletion
- **Filter** by action and by group.
- **No edits or deletions.** Nobody can edit or delete an entry. One exception: a group deletion also deletes the cadet details in that group's entries.

### Other
- **`seed_demo`** loads three fake ATPL groups, the instructors `alex` and `sam` with assigned subjects, and three score sets for demos.
- **Time zone.** Times and export dates use UTC+8 by default.
- **Database.** The program uses SQLite: one file, with no setup. The database code can change to PostgreSQL later.
- **Local only.** Only this computer can open the site (`127.0.0.1`).

---

## Showcase on a new PC

These steps take a new computer to a full demo. Setup takes approximately 10 minutes. The demo takes approximately 15 minutes.

### 1. Requirements for the PC

- **Python 3.14** from python.org. On Windows, select **"Add python.exe to PATH"** in the installer.
- **The project folder.** Copy the full folder to a plain local folder, for example `C:\Dev\AutomatedReports` or `~/Dev/AutomatedReports`.
  - Do not copy `.venv` or `db.sqlite3`. They belong to the old PC. Step 2 makes new ones.
  - Do not use a folder that OneDrive syncs. Syncing can damage the database file.
  - The GitHub copy contains the program, the sample rosters, this README and `docs/RUN_LOCALLY.md`. It does not contain `SHOWCASE_CREDENTIALS.md` or the tests. Copy the folder. Do not only clone the GitHub copy.
- **A web browser.** The optional MFA demo (step 6) also needs a phone with an authenticator app.

### 2. One-time setup

Open a terminal in the project folder.

**Windows (PowerShell)**
```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createadmin --username admin --full-name "Demo Admin"
```
If PowerShell does not run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` one time. Then try again.

**macOS / Linux**
```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createadmin --username admin --full-name "Demo Admin"
```

The commands do these tasks:
- `migrate` makes the database file `db.sqlite3`.
- `seed_demo` loads three fake ATPL groups (C216, C217 and C218, with 44 cadets). It makes the instructors `alex` and `sam` with their subjects. It saves three score sets for C216. It shows each instructor's **temporary password one time**. Copy both.
- `createadmin` shows a **temporary password one time**. Copy it. You need it in step 4.

### 3. Start the server

Disable MFA for the demo, so nobody needs an authenticator app. Then start the server. Use the same terminal. The prompt must start with `(.venv)`.

```powershell
# Windows PowerShell
$env:MFA_REQUIRED = "false"
python manage.py runserver
```
```bash
# macOS / Linux
MFA_REQUIRED=false python manage.py runserver
```

Open **http://127.0.0.1:8000**. To stop the server, press `Ctrl+C`. Never start the server with `0.0.0.0`.

### 4. Demo accounts

**`SHOWCASE_CREDENTIALS.md`** in the project folder contains the usernames and passwords. It is a local file that never goes to GitHub. Copy it with the folder.
- The admin is `admin`. The instructors are `alex` and `sam`.
- Each user signs in first with a one-time temporary password (from `createadmin` and `seed_demo`). Then the user sets the password from that file.

Use a **normal browser window for the admin**. Use a **private (incognito) window for the instructors**. Then both users can stay signed in at the same time.

### 5. Demo walkthrough

**A. The admin looks at the data** (normal window)
1. Sign in as `admin` with the temporary password from step 2.
2. Set the admin password from `SHOWCASE_CREDENTIALS.md`.
3. Open **Programmes**. ATPL is built in, with 13 fixed subjects.
4. Open **Accounts**. `alex` and `sam` already have subjects. Press **Subjects** on a row to change them. Tell the audience: there is no self-registration, and an instructor can score only the assigned subjects.
5. Open **Missing scores (7)** in the navigation. It lists each unscored subject and the instructors who can score it. For example, nobody has scored C216 General Navigation (`sam`'s subject). C217 and C218 have no scores yet. Meteorology is listed once per group, with both `alex` and `sam`: a save by either of them clears it.

**B. The first instructor scores** (private window)
1. Sign in as `alex` with the temporary password from `seed_demo`.
2. Set Alex's password from `SHOWCASE_CREDENTIALS.md`.
3. On **Home**, select **C216**. Press **Open**. The subject dropdown shows only Alex's subjects: Meteorology and Air Law.
4. Select **Meteorology**. Press **Score**. The grid already holds the demo scores.
5. Give the first cadet (**Hana Tan**) a **2** for *Attire / Appearance*. Clear one other cell. Add a comment for one cadet. Press **Save**.
6. The site fills the blank cell with 3 and highlights it. Nothing is saved yet. Check the cell and press **Confirm and save**.
7. Open **Results** (a link on the group page). An instructor sees results only for the subjects assigned to them. The **Subject** dropdown shows one subject at a time.
8. Press **Sign out**.

**C. The second instructor scores the same subject** (same private window)
1. Sign in as `sam` with the temporary password from `seed_demo`.
2. Set Sam's password from `SHOWCASE_CREDENTIALS.md`.
3. **Home** shows **Your missing scores**, including C216 General Navigation. Press that link.
4. Score **General Navigation** and save. The C216 line disappears from **Home**.
5. Open **Meteorology** for C216. Give **Hana Tan** a **1** for *Attire / Appearance*. Press **Save**, then **Confirm and save**.
6. Open **Results**. Select the subject **Meteorology**. Alex gave Hana Tan a 2 and Sam gave a 1 for *Attire*. The average is (2 + 1) / 2 = 1.5. The site rounds a .5 average up, so the cell shows **2**. The average is below 2.5. Thus the site flags the row **Below C – HGS consultation**. The site colours each cell by grade.
   - This result needs Alex's 2 from part B. If Alex's score stays at 4, the average is 2.5. The cell then shows 3 and the site does not flag the row.

**D. Admin features** (normal window)
1. Open **Missing scores**. C216 no longer appears. C217 and C218 are still listed.
2. Open **Results** for C216. The admin sees all subjects together.
3. On the group page, press **Export report**. The browser downloads the filled-in report (`.xlsx`). Open it in Excel or LibreOffice.
4. Open **Audit log**. It shows each score change (old value → new value), assignment and export, with who and when.
5. In the private window, Sam opens a C216 scoring page and changes a score, but does not save. In the normal window, press **Lock** for C216 on the group page. Sam now presses **Save**. The site saves nothing and shows "Not saved: group C216 is locked". Sam's change stays on the screen. Then press **Unlock**.
6. Open **Manage cadets** → a cadet's **Subjects** link. Take the cadet off one subject. The cadet no longer shows in that subject's grid.
7. Open **Upload roster**. Select the programme **ATPL**. Select `samples/sample_roster_C217.xlsx`, type the group number **C300** and press **Upload**.
8. Select **Full Name** as the Name column. The other columns are ignored. Press **Continue**.
9. Check the preview. Press **Confirm and apply**. C300 is now in the Home dropdown.
10. Optional: press **Archive** on a group. You can also open **Programmes** to add a programme and its subjects. To hand the admin role to another account, run `python manage.py transferadmin --to <username>`.

### 6. Optional: show MFA

1. Press `Ctrl+C` to stop the server.
2. Start the server again with MFA on:
   - Windows: run `Remove-Item Env:MFA_REQUIRED`, then run `python manage.py runserver`.
   - macOS / Linux: run `python manage.py runserver`.
3. Sign in as `alex`. The site shows a QR code.
4. Scan the QR code with an authenticator app, for example Microsoft Authenticator or Google Authenticator. Type the 6-digit code.
5. After this, Alex must type a code at each sign-in. If Alex loses the phone, the admin presses **Reset** on Alex's row in **Accounts**.

### 7. Reset for the next showcase

1. Stop the server.
2. Delete `db.sqlite3`. This deletes the demo accounts and scores.
3. Run `migrate`, `seed_demo` and `createadmin` again (step 2). `migrate` makes ATPL and its subjects again.
4. Continue from step 3.

### Facts for a demo

- A session ends after **30 minutes** without activity, or when the browser closes.
- **5 wrong passwords in a row** lock an account for 15 minutes. The admin can clear the lock with **Reset** in **Accounts**.
- If you forget the admin password, run `python manage.py changepassword admin`. Run it in the project folder, with `.venv` active.

---

## Everyday commands

```bash
python manage.py runserver               # start the site on 127.0.0.1 only. Never use 0.0.0.0.
python manage.py test                    # run the tests. They use a separate temporary database.
python manage.py discard_stale_uploads   # delete roster uploads that stayed unfinished for 24 hours
```

Each time an admin opens the upload page, the site also does the `discard_stale_uploads` cleanup. Thus local use does not need a schedule.

## Configuration

All settings are environment variables. The default values suit a local proof of concept.

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Debug mode. Accepts `1`, `true`, `yes` or `on`. Debug mode works only with the local hosts `127.0.0.1` and `localhost`. When debug mode is off, you must set `DJANGO_SECRET_KEY`. Also, the site then keeps MFA on, ignores `MFA_REQUIRED` and accepts HTTPS only. |
| `DJANGO_SECRET_KEY` | an insecure development key (debug mode only) | The Django secret key. |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | The host names that the app serves, with commas between them. If this list has any other host, the site is a real server: the app does not start until `DJANGO_DEBUG` is off. |
| `DJANGO_TIME_ZONE` | `Etc/GMT-8` (UTC+8) | The time zone for times on the pages, in the audit log and on the export date. |
| `DB_ENGINE` | `sqlite` | `sqlite` or `postgresql`. PostgreSQL also needs a driver. The project does not install it yet. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` | none | The PostgreSQL connection. |
| `DB_PORT` | `5432` | The PostgreSQL port. |
| `LOGIN_MODE` | `local` | `local`, `microsoft` or `both`. Keep `local`. Microsoft sign-in needs an app registration from IT, and that work is on hold with hosting. |
| `MFA_REQUIRED` | `True` | Ask for an authenticator-app code at local sign-in. |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_REDIRECT_URI` | empty | The Microsoft Entra settings. They are necessary when `LOGIN_MODE` is `microsoft` or `both`. |
| `ROSTER_MAX_UPLOAD_BYTES` | `5242880` (5 MB) | The largest roster `.xlsx` file that the site accepts. |

## Fake data only

Use fake cadet names only. Never load real cadet data into this proof of concept.
