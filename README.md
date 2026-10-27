# Site Labour Attendance

A single-page Flask and SQLite app. Local data lives in `instance/attendance.db`; production must set `DATABASE_PATH=/var/data/attendance.db` and attach a Render persistent disk at `/var/data`. If the configured database directory is unavailable the app fails startup/request handling instead of silently making a new database elsewhere.

## Run on Windows

Install Python 3.10 or newer. In PowerShell from this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app app run --host 0.0.0.0
```

Open http://127.0.0.1:5000. `DATABASE_PATH` can point to another SQLite file; without it the app creates/uses `instance/attendance.db`. To access it on Android on the same Wi-Fi, find the computer's local IPv4 address with `ipconfig`, allow Python through Windows Firewall on the Private network, then open `http://COMPUTER-IP:5000` on the phone. Both devices must be on the same trusted network.

## GitHub and Render deployment

1. Create a new empty repository on GitHub. In this folder, run `git init`, `git add .`, `git commit -m "Build Site Labour Attendance"`, `git branch -M main`, `git remote add origin https://github.com/YOUR-NAME/YOUR-REPO.git`, then `git push -u origin main`.
2. In Render, choose **New > Web Service**, connect GitHub, and select the repository.
3. Set build command to `pip install -r requirements.txt` and start command to `gunicorn app:app`.
4. Select a **paid** web service plan. Free web services cannot attach persistent disks, and their filesystem is ephemeral.
5. In Advanced/service settings, add a persistent disk mounted at `/var/data`. Choose a disk size (Render does not allow shrinking later). A disk-backed service is limited to one service instance, and redeploys briefly stop the old instance before attaching the disk to the new one.
6. Add environment variable `DATABASE_PATH=/var/data/attendance.db`. Also set `SECRET_KEY` to a long random secret. Do not set `DATABASE_PATH` to a path outside the mounted disk.
7. Create the service and deploy. Check the service logs for successful startup. In the app, save a test attendance, restart/redeploy the service, and confirm the same date/count remains visible. Keep real records only after confirming the disk is attached and path configured.

Render's current pricing lists persistent disk storage at **$0.25 per GB per month**, charged in addition to the selected web-service compute plan. Minimum disk size and compute plan pricing can vary by region and account; review the live [Render pricing page](https://render.com/pricing) before creating the service. A Free web service cannot meet the persistence requirement.

## Back up and restore

Use SQLite's online backup API so the backup is consistent even while the app is running. On the host, run Python with the source and destination paths adjusted:

```python
import sqlite3
src = sqlite3.connect('/var/data/attendance.db')
dst = sqlite3.connect('/var/data/attendance-backup.db')
src.backup(dst)
dst.close()
src.close()
```

Copy the completed backup file to safe storage. To restore, stop the service (or ensure nobody is writing), copy the backup to a temporary file on the mounted disk, validate it with `PRAGMA integrity_check`, then replace `attendance.db` while the service is stopped. Keep a second backup before restore. Do not copy a live database file by itself: journal/WAL state may be active. Render disk snapshots are useful but do not replace independent backups.

## Notes

The app enforces unique dates in SQLite, uses parameterized queries, transactions, server validation and a session CSRF token. Confirmed moves to occupied dates explicitly delete the identified destination record and retain the edited record's ID and creation time. Local `instance/` database files are ignored by Git.
