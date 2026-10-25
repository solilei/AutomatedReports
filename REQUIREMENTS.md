# Cadet Soft Skills Report — Requirements

A Python web app where instructors score cadets on six soft-skill attributes, the site averages the scores per cadet, and admins export a filled-in copy of the Cadet Soft Skills Report template (see `report.md`).

---

## 1. Platform and Proof of Concept

- [ ] Built with Python using the Django framework
- [ ] Proof of concept (PoC) runs locally on one machine
- [ ] PoC is reachable from `localhost` only; network access is not enabled until hosting is decided
- [ ] PoC uses SQLite (single database file, no setup)
- [ ] PoC uses **fake cadet names only**; no real cadet data until the app runs on approved hosting
- [ ] Database layer is written so it can switch to PostgreSQL for production
- [ ] PoC includes every feature in this document; Microsoft sign-in is built but switched off

## 2. Authentication

### Login modes
- [ ] Configuration setting selects the login mode: `local`, `microsoft`, or `both`
- [ ] PoC defaults to `local`

### Microsoft sign-in
- [ ] "Sign in with Microsoft" using the organisation's existing work accounts (Microsoft Entra ID)
- [ ] Only accounts from the organisation's own tenant are accepted
- [ ] A person's first Microsoft sign-in creates a **pending** account with no access
- [ ] An admin must approve a pending account before it can view or edit anything
- [ ] The site stores no passwords for Microsoft accounts; MFA and leaver handling come from the organisation's Microsoft setup

### Local accounts (fallback, and for local testing)
- [ ] There is no self-registration page
- [ ] Admin creates each local account in the web UI
- [ ] On creation, a one-time temporary password is shown on screen to the admin (no email sending)
- [ ] User must set their own password at first login
- [ ] Authenticator-app MFA (TOTP) is supported for local accounts
- [ ] MFA can be switched off for local PoC testing
- [ ] MFA is required whenever local login is used on a real server
- [ ] 5 failed sign-in attempts in a row (wrong password or authenticator code) lock the account for 15 minutes; an admin reset clears the lock

### First admin
- [ ] The first admin account is created from the command line on the host machine
- [ ] The web UI never offers a way to become an admin without an existing admin

### Sessions
- [ ] Users are logged out automatically after 30 minutes of inactivity
- [ ] Once hosted (off `localhost`), all traffic is HTTPS-only with secure cookies

## 3. Roles and Permissions

- [ ] Two roles: **Admin** and **Instructor**
- [ ] Only signed-in, approved, active users can see any page with cadet data
- [ ] Admin can do everything an Instructor can (pick groups, submit score sets)

### Instructor can
- [ ] Select any group (no per-group assignment)
- [ ] Create, view and edit **their own** score sets
- [ ] View the group's combined results (averages, sums, flags)

### Instructor cannot
- [ ] See other instructors' individual scores or score sets
- [ ] Export anything
- [ ] Upload rosters, manage accounts, manage subjects, lock/archive/delete groups, or view the audit log

### Admin can additionally
- [ ] Upload rosters
- [ ] Create, approve, deactivate and promote accounts
- [ ] Manage the subject list
- [ ] Lock, unlock, archive and delete groups
- [ ] Permanently delete cadets
- [ ] Export group reports
- [ ] View the audit log
- [ ] See all score sets
- [ ] The last remaining admin cannot be demoted or deactivated

## 4. Roster Upload

- [ ] Admin-only
- [ ] Accepts `.xlsx` files only
- [ ] Enforces a maximum file size of 5 MB
- [ ] Roster contains one column for group number, one for cadet name, plus other columns that are ignored
- [ ] After upload, the site shows the file's header row and the admin picks the Name column (there is no Group column; see below)
- [ ] The site remembers the last column choice and pre-selects it next time
- [ ] If the roster has a cadet ID column, the admin can choose it as the cadet identifier
- [ ] One file contains one course only; the file's cadets all belong to the one group the admin names
- [ ] Admin types the group number (e.g. `C216`, which is also the course) at upload time; the file has no group column
- [ ] Group numbers use letters, digits, `.`, `_` and `-` only, and contain at least one letter or digit
- [ ] Names over 200 characters or cadet IDs over 50 are rejected with the row number
- [ ] Admin can discard an upload before applying it; the stored file is deleted

### Cadet identity
- [ ] If an ID column is chosen, cadets are identified by ID and displayed by name
- [ ] Digit-only IDs ignore leading zeros (`00123` and `123` are the same cadet)
- [ ] If no ID column, cadets are identified by (group, name)
- [ ] Without an ID column, an upload with duplicate names in the same group is rejected with a clear message until the admin fixes the file

### Re-uploading an existing group
- [ ] The site shows a preview of changes before applying anything: cadets added, cadets no longer present
- [ ] Changes apply only after the admin confirms
- [ ] If the roster changed after the preview was shown, confirming shows the updated preview instead of applying
- [ ] New cadets are added
- [ ] Cadets missing from the new file are marked **inactive** (hidden, data kept), not deleted
- [ ] Nothing is deleted silently; only an admin can permanently delete a cadet

## 5. Groups

- [ ] A group's number (e.g. `C216`) is unique and never reused; it is the group's key
- [ ] Group status: **active**, **locked**, or **archived**
- [ ] Group selection is a dropdown of active and locked groups (archived groups hidden)

## 6. Subjects

- [ ] Subjects are a fixed list managed by admins
- [ ] Instructors pick a subject from a dropdown when scoring (no free text)
- [ ] A deactivated subject cannot start new score sets; existing score sets for it stay editable
- [ ] A subject used by a locked or archived group cannot be renamed

## 7. Scoring

### Score sets
- [ ] A score set is keyed by (instructor, subject, group)
- [ ] An instructor teaching two subjects to the same group submits one score set per subject
- [ ] Each score set holds, per active cadet, a score for each of the six attributes:
  - [ ] Attentiveness / Engagement
  - [ ] Motivation / Diligence / Enthusiasm
  - [ ] Discipline / Courtesy
  - [ ] Attire / Appearance
  - [ ] Teamwork
  - [ ] Communication / Participation / Interaction
- [ ] Each score is a whole number 1–5 or blank: 5 Excellent (A), 4 Above standard (B), 3 Meets standard (C), 2 Below standard (D), 1 Unacceptable (E)
- [ ] Each score set holds an optional free-text comment per cadet

### Scoring page
- [ ] Flow: select group → select subject → full list of active cadets in the group → enter scores and comments → Save
- [ ] Saving requires at least one score to be entered
- [ ] On an instructor's **first** save of a score set, blank cells are filled with 3 and saved as 3, with no warning
- [ ] On later saves, blank cells stay blank; the site warns how many cadets/cells are blank and will be counted as 3, and saves only after the instructor confirms
- [ ] Cadets added since this instructor's last save are visibly marked ("added since your last save")
- [ ] Instructors can edit their saved score sets at any time while the group is not locked

### Locking
- [ ] Admin can lock a group (e.g. when the report goes to HGS)
- [ ] A locked group is read-only for everyone
- [ ] Only an admin can unlock a group

## 8. Results

- [ ] Per-group results table showing active cadets only
- [ ] Columns: No., Name, six attribute averages, **sum of the six averages** (range 6–30) as the last column
- [ ] Averages are taken across all saved score sets for that group (all instructors and subjects)
- [ ] A blank score inside a **saved** score set counts as 3
- [ ] A saved score set with no row for a cadet (e.g. the cadet was added later) counts as 3 for every attribute of that cadet
- [ ] Instructors who never saved a score set for the group are not counted
- [ ] A cadet with no saved scores at all shows "no data", not 3.00
- [ ] Averages are rounded to a whole number (no decimal places); the sum is the sum of the six rounded averages
- [ ] Each average cell is coloured using the template's band colours, by rounding the average to the nearest point (5 green → 1 red)
- [ ] Exactly x.5 rounds up, so 2.5 counts as C
- [ ] A cadet is **flagged** if any single attribute average is below 2.5 (below C, which triggers HGS consultation per the template)
- [ ] Inactive cadets are excluded from results

## 9. Export

- [ ] Admin-only
- [ ] The **group report** is the only export product
- [ ] One group per file (`.xlsx`)
- [ ] Reproduces the Cadet Soft Skills Report template layout (title, department, instruction text, grading-system key, colours) with cells filled in
- [ ] Sheet name is the group number (e.g. `C216`)
- [ ] Header fields:
  - [ ] Course: the group number (e.g. `C216`)
  - [ ] Instructor: names of every instructor who contributed a score set
  - [ ] Subject: every subject included
  - [ ] Date: the export date
- [ ] Table rows: one per active cadet, six attribute averages, and the sum of averages in the Total column
- [ ] Average cells use the template's band colours
- [ ] The "Additional comments" section lists comments grouped by cadet, formatted as _cadet name — instructor (subject): comment_
- [ ] Inactive cadets are excluded

## 10. Account and Data Lifecycle

- [ ] Admin can deactivate an instructor; a deactivated instructor cannot log in
- [ ] Score sets from deactivated instructors still count in averages and exports
- [ ] Admin can **archive** a group: read-only and hidden from dropdowns
- [ ] Unarchiving returns the group to the status it had before it was archived (active or locked)
- [ ] Admin can permanently **delete** an archived group and all its data
- [ ] No automatic deletion until the organisation's retention period is known

## 11. Audit Log

- [ ] Every change is recorded with who, what, and when
- [ ] Logged events include:
  - [ ] Score changes (old value → new value)
  - [ ] Comment changes
  - [ ] Roster uploads and confirmed re-upload changes
  - [ ] Exports
  - [ ] Account creation, approval, promotion and deactivation
  - [ ] Group lock, unlock, archive and delete
  - [ ] Cadet deletion
- [ ] Admins can view the audit log in the web UI

---

## Open Questions

- [ ] **Sample roster**: add a sample roster with fake names to the project folder so the real column layout can be checked before building
- [ ] **Cadet ID column**: does the real roster include a cadet/student ID? This decides whether cadets are identified by ID or by (group, name)
- [ ] **Retention period**: ask the organisation's data-protection owner how long cadet scores must or may be kept after a course finishes; this decides whether automatic deletion is added
- [ ] **Microsoft Entra ID app registration**: IT needs to register the app before Microsoft sign-in can be switched on
- [ ] **Production hosting**: not decided yet. Options: Azure App Service in the organisation's tenant (preferred), an internal server/VM, or a third-party host (only with data-protection sign-off)
- [ ] **Production database**: PostgreSQL host to be chosen along with production hosting
- [ ] **Network access and HTTPS**: how colleagues will reach the site and how HTTPS will be provided; depends on hosting
- [ ] **Data-protection sign-off**: confirm the chosen hosting and data handling are acceptable before real cadet data is loaded
- [x] **Confirm assumed defaults** (confirmed 2026-10-25):
  - [x] `.xlsx`-only uploads, maximum file size 5 MB
  - [x] Averages and sums shown as whole numbers (changed from 2 decimal places)
  - [x] An average of exactly 2.5 counts as C (rounds up)
  - [x] The last remaining admin cannot be demoted or deactivated
