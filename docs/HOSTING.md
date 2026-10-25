# Hosting the app for colleagues

This guide covers what it takes to move from the local proof of concept (`docs/RUN_LOCALLY.md`) to a site colleagues can open. **Nothing here has been done yet.** Real cadet data must not be loaded until every item in section 8 is ticked.

---

## 1. Can it be hosted on the company OneDrive?

**No.** OneDrive (and SharePoint, which sits behind it) stores and shares *files*. This app is a *program*: it needs a computer that keeps Python running all the time, answers web requests, and writes to a database. OneDrive has no way to run a Python program, so it can't host the site.

Things that look like workarounds, and why to avoid them:

| Idea | Problem |
|---|---|
| Put the project folder in OneDrive and run it from each person's PC | Each person gets their own separate copy of the data. Scores never combine, and OneDrive syncing a live SQLite file can corrupt it. |
| Put `db.sqlite3` in a shared OneDrive folder | SQLite is not built for several machines writing over a sync service. Expect conflicts, lost scores and corrupt files. |
| Share one person's PC on the network | The PC must stay on, the proof of concept is deliberately locked to `localhost`, and it has no HTTPS. |

### What OneDrive / SharePoint *is* good for here
- **Storing the exported reports.** The template text says reports go to "the appropriate GSH shared folder". That folder can stay on SharePoint/OneDrive. Admins export from the app and save the `.xlsx` there.
- **Keeping this documentation and the sample rosters** for the team.

### The closest option to "on our Microsoft setup"
The company's OneDrive runs on Microsoft 365, which comes with a Microsoft Entra ID tenant (the company's work accounts). **Azure App Service** in that same tenant is the matching place to *run* the app. It is the option REQUIREMENTS.md already prefers. Colleagues sign in with the same work accounts they use for OneDrive, and the data stays inside the organisation's Microsoft environment.

---

## 2. The simplest options at a glance

Three realistic ways to put the site online. Whichever you pick, the code changes in section 4 are needed, and the proof of concept stays `localhost`-only until hosting is decided (REQUIREMENTS.md).

| | A. Azure "Web App + Database" | B. A computer on the office network | C. Beginner-friendly host |
|---|---|---|---|
| **What it is** | Azure App Service and PostgreSQL, created by one wizard in the Azure portal | A PC or small server inside the office, run by IT | A company that runs Python sites for you (e.g. PythonAnywhere, Render) |
| **Effort** | Low to medium: point-and-click wizard, no servers to look after | Medium: someone must keep it switched on, patched and backed up | Lowest: sign up in a browser, upload the code or connect GitHub |
| **Cost** | A monthly Azure charge for a small app and database (IT can price it) | No new spend if the hardware exists | Free tiers to try; a small monthly fee for real use |
| **Who must approve** | IT (Azure subscription) and data protection | IT (network, firewall, certificate) and data protection | Data protection (a third party holds the data) |
| **Sign in with Microsoft** | Works, and fits best: same tenant as OneDrive | Works if colleagues can reach the server | Works (it's just a web address), but data sits outside the organisation |
| **OK for real cadet data?** | **Yes, once signed off. Recommended.** | Yes, if IT provides HTTPS and backups | Only with explicit data-protection sign-off |

### A. Azure "Web App + Database" (recommended)
The easiest Azure route needs no command line:
1. In the Azure portal, choose **Create a resource**, search for **Web App + Database**, and select it.
2. Pick the subscription and resource group IT gives you, a region approved by data protection, and a name. Set **Runtime stack** to Python and **Engine** to PostgreSQL – Flexible Server.
3. Choose the smallest hosting plan offered for real use (IT will advise), then **Review + create**.
4. The wizard creates the web app, a database on a private network and the link between them. It saves the database connection details in the web app's settings, under its own names. Copy them into the `DB_*` settings this app reads (section 5.3).
5. To deploy without the command line, use **Deployment Center** in the web app to connect the GitHub repository (every push then deploys), or the **Azure App Service** extension in VS Code (right-click the project → *Deploy to Web App*).
6. Then follow sections 5.3 to 5.7 for settings, the first admin, access limits and backups.

Section 5 shows the same setup with the Azure command line, step by step.

### B. A computer on the office network
Best when Azure isn't available and IT already runs internal servers. IT provides a fixed internal name (e.g. `cadet-reports.internal`), a certificate for HTTPS, a firewall rule that allows the office network only, and backups. The app runs behind a web server such as nginx or IIS rather than `runserver`. A Windows machine needs a Windows-capable production server such as waitress (another new dependency), because gunicorn runs on Linux only. Details are in section 7.

### C. Beginner-friendly hosts
- **PythonAnywhere:** everything happens in the browser. Upload the code, run the Django web-app wizard, and set the environment variables. It offers an EU-hosted option.
- **Render:** connect the GitHub repository; it builds and deploys on every push, and offers PostgreSQL.

These are the quickest way to get a working address, but the data is held by a company outside the organisation. REQUIREMENTS.md allows that only with data-protection sign-off. Even a demo with fake names means relaxing the `localhost`-only rule for the proof of concept, so agree that first.

---

## 3. Who needs to be involved

| Who | What they provide |
|---|---|
| **Data-protection owner** | Sign-off that Azure (and the chosen region) is acceptable for cadet data, and the retention period (REQUIREMENTS.md open questions). |
| **IT / Azure administrator** | An Azure subscription (or a resource group in an existing one), permission to create App Service and PostgreSQL resources, network rules, and billing. |
| **Entra ID administrator** | The app registration for "Sign in with Microsoft" (section 6). |
| **You (developer)** | The code changes in section 4, deployment, and creating the first admin. |

---

## 4. Code changes needed before hosting

The proof of concept is built to run locally. These changes are still needed before it can run on App Service. Each new package needs your approval first (project rule).

| # | Change | Why |
|---|---|---|
| 1 | Add **gunicorn** (new dependency) | `runserver` is a development server only. Gunicorn is the standard production server for Django on Linux, and App Service uses it. |
| 2 | Add **psycopg** (new dependency) | The PostgreSQL driver. The settings already switch to PostgreSQL with `DB_ENGINE=postgresql`, but the driver isn't installed. |
| 3 | Serve static files: set `STATIC_ROOT`, run `collectstatic`, and add **WhiteNoise** (new dependency) or similar | With `DEBUG` off, Django doesn't serve the CSS. Without this the site loads unstyled. |
| 4 | Set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` | App Service handles HTTPS in front of the app and passes plain HTTP inside. Without this setting, the HTTPS redirect loops forever and sign-in forms fail the CSRF check. |
| 5 | Decide how the first admin signs in when `LOGIN_MODE=microsoft` | `createadmin` makes a *local* account, and `microsoft` mode refuses local sign-in, so nobody could approve the first Microsoft user. Either run in `both` mode (local admin with MFA plus Microsoft for everyone else), or extend `createadmin` to make a Microsoft-linked admin. |
| 6 | Make `DJANGO_DEBUG` default to off | Today it defaults to on. A server started without the variable would show debug pages and allow MFA to be switched off. |
| 7 | Test against PostgreSQL | Run the test suite once with `DB_ENGINE=postgresql` against a test database. SQLite is more lenient (e.g. about text length). |
| 8 | Optional: handle two admins creating the same new group at the same moment | Very rare; today the second admin gets an error page and nothing is half-applied. |

Already done: sign-in attempt limits (5 failures lock an account for 15 minutes) and the other code-review fixes.

---

## 5. Azure App Service: step by step

Replace everything in `<angle brackets>`. Commands use the Azure CLI (`az`); every step can also be done in the Azure portal.

### 5.1 Prepare
1. Install the Azure CLI and sign in with your work account:
   ```bash
   az login
   ```
2. Choose a **region** approved by data protection (e.g. the region closest to you), and names for the resources.

### 5.2 Create the resources
```bash
# A folder (resource group) for everything belonging to this app
az group create --name <rg-cadet-reports> --location <region>

# The PostgreSQL database server (smallest paid tier is enough to start)
az postgres flexible-server create \
  --resource-group <rg-cadet-reports> --name <cadet-reports-db> --location <region> \
  --tier Burstable --sku-name Standard_B1ms \
  --admin-user <dbadmin> --admin-password '<strong password>'

az postgres flexible-server db create \
  --resource-group <rg-cadet-reports> --server-name <cadet-reports-db> --database-name cadetreports

# The Linux plan the web app runs on, and the web app itself
az appservice plan create --resource-group <rg-cadet-reports> --name <cadet-reports-plan> --is-linux --sku B1
az webapp list-runtimes --os linux        # pick the newest PYTHON version listed
az webapp create --resource-group <rg-cadet-reports> --plan <cadet-reports-plan> \
  --name <cadet-reports> --runtime "PYTHON:<version>"
```
The site address becomes `https://<cadet-reports>.azurewebsites.net`. The app is built on Python 3.14. If App Service doesn't offer 3.14 yet, use the newest version it lists and run the full test suite on that version first.

**Network access to the database.** Ask IT to choose: either *private access* (the database is only reachable from the web app through a virtual network, which is the safer option), or public access limited by firewall rules to the web app's outbound addresses. Never open the database to the whole internet.

### 5.3 Configure the app
Generate a secret key once and keep it private:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```
Then set the app's environment variables (App Service calls them *App settings*):
```bash
az webapp config appsettings set --resource-group <rg-cadet-reports> --name <cadet-reports> --settings \
  DJANGO_DEBUG=false \
  DJANGO_SECRET_KEY='<generated key>' \
  DJANGO_ALLOWED_HOSTS=<cadet-reports>.azurewebsites.net \
  DJANGO_TIME_ZONE=<Area/City> \
  DB_ENGINE=postgresql DB_NAME=cadetreports DB_USER=<dbadmin> \
  DB_PASSWORD='<strong password>' DB_HOST=<cadet-reports-db>.postgres.database.azure.com \
  LOGIN_MODE=local \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true
```
Keep secrets out of the repository. For extra protection, IT can store them in **Azure Key Vault** and reference them from App settings.

Force HTTPS and set the start command:
```bash
az webapp update --resource-group <rg-cadet-reports> --name <cadet-reports> --https-only true
az webapp config set --resource-group <rg-cadet-reports> --name <cadet-reports> \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --timeout 120 config.wsgi"
```
`0.0.0.0` is correct **here only**. Inside App Service the app runs in a container that can only be reached through Azure's HTTPS front end. On your own machine, keep using plain `runserver` (127.0.0.1).

### 5.4 Deploy the code
From the project folder, package the committed code (so `.env`, `.venv` and `db.sqlite3` are never uploaded) and deploy it:
```bash
git archive --format=zip -o app.zip HEAD
az webapp deploy --resource-group <rg-cadet-reports> --name <cadet-reports> --src-path app.zip --type zip
```
App Service installs `requirements.txt` during the deploy.

### 5.5 Set up the database and the first admin
Open a shell on the running app, which counts as "the command line on the host machine":
```bash
az webapp ssh --resource-group <rg-cadet-reports> --name <cadet-reports>
# inside the SSH session. If `python` can't find Django, first activate the app's
# virtual environment as described in Azure's "Configure a Linux Python app" docs.
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createadmin --username <admin> --full-name "<Full Name>"
```
Sign in at `https://<cadet-reports>.azurewebsites.net`, set the password, and enrol the authenticator app. MFA is always on when `DJANGO_DEBUG=false`.

Repeat `migrate` after every deploy that adds database changes.

### 5.6 Limit who can reach the site
In the portal: *Web app → Networking → Access restrictions*. Allow only the company's network ranges or VPN (IT supplies them) and deny everything else. Alternatively, IT can put the app behind a private endpoint so it is only reachable on the internal network.

### 5.7 Backups
Azure Database for PostgreSQL takes automatic backups (7 days by default; adjustable up to 35). Set this to match the retention period from data protection. Test a restore once before relying on it.

### 5.8 Optional: company domain
To use an address like `cadet-reports.<company>.com`, add it under *Web app → Custom domains*, add a managed certificate, and include it in `DJANGO_ALLOWED_HOSTS`.

---

## 6. Switching on "Sign in with Microsoft"

Done by the **Entra ID administrator**, after the app is hosted.

1. Azure portal → **Microsoft Entra ID → App registrations → New registration**.
2. **Name:** `Cadet Soft Skills`.
3. **Supported account types:** *Accounts in this organizational directory only (single tenant)*. This is what limits sign-in to company accounts.
4. **Redirect URI:** platform *Web*, value `https://<cadet-reports>.azurewebsites.net/accounts/microsoft/callback/` (use the custom domain if you added one).
5. Register. From the *Overview* page copy the **Application (client) ID** and **Directory (tenant) ID**.
6. **Certificates & secrets → New client secret.** Copy the secret *value* straight away; it is only shown once. Note its expiry date, because the secret must be renewed before then or sign-in stops working.
7. **API permissions:** keep the default *Microsoft Graph → User.Read (delegated)*. No admin consent beyond the default is needed.
8. Add the values to the App settings:
   ```bash
   az webapp config appsettings set --resource-group <rg-cadet-reports> --name <cadet-reports> --settings \
     LOGIN_MODE=both \
     ENTRA_TENANT_ID=<tenant id> ENTRA_CLIENT_ID=<client id> \
     ENTRA_CLIENT_SECRET='<secret value>' \
     ENTRA_REDIRECT_URI=https://<cadet-reports>.azurewebsites.net/accounts/microsoft/callback/
   ```
9. Test it: a colleague signs in with Microsoft and sees "pending". An admin approves them under *Accounts*.

Use `both` until item 5 in section 4 is resolved. After that, `microsoft` alone is possible.

---

## 7. Alternative: an internal server or VM

If Azure isn't approved, IT can provide a Linux server on the company network. The same section 4 changes apply, plus:
- Install Python, PostgreSQL (or point at an existing one) and a reverse proxy such as nginx in front of gunicorn.
- The reverse proxy handles HTTPS with a certificate from IT, and sets the `X-Forwarded-Proto` header.
- Run gunicorn as a service (systemd) bound to `127.0.0.1`, so only the reverse proxy can reach it.
- Arrange database backups and OS patching.

A third-party host is only allowed with data-protection sign-off (REQUIREMENTS.md).

---

## 8. Go-live checklist

- [ ] Data-protection sign-off on hosting, region and data handling
- [ ] Retention period agreed; backup retention set to match
- [ ] Section 4 code changes done, tests passing (including on PostgreSQL)
- [ ] `DJANGO_DEBUG=false`, a unique `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` set
- [ ] HTTPS-only switched on; the site never answers on plain HTTP
- [ ] Database not reachable from the internet
- [ ] Site access limited to the company network / VPN
- [ ] First admin created over SSH, MFA enrolled
- [ ] Entra app registration done, client-secret expiry date noted in a calendar
- [ ] Test run with fake data: create accounts, upload a roster, score, export, lock, archive, check the audit log
- [ ] Only then: load real rosters
