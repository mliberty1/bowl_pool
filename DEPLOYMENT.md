# Deployment

Production runs on the home server `edge` behind Caddy, as `bowl_pool.service`.
Every push to `main` deploys automatically. This document describes the
mechanism, the one-time setup, and how to recover when something breaks.
It is the same pattern as the family cookbook; see
`family_cookbook/doc/edge_migrate.md` for the longer write-up and the
host-level notes (Caddy, certificates, ssh access).

## How a deploy works

```
GitHub Actions (push to main)
  POST https://bowl.libertyfamily.us/webhook/update   Authorization: Bearer <token>
    -> app sends SIGTERM to its gunicorn master, exits 0
    -> systemd bowl_pool.service (Restart=always) runs deploy/bowl_pool-start.sh
         git fetch && git reset --hard origin/main
         pip install -r requirements.txt      (only when requirements.txt changed)
         python init_db.py                    (db.create_all: adds missing tables)
         exec gunicorn app:app --bind 127.0.0.1:8881 --workers 1
  then poll https://bowl.libertyfamily.us/healthz until git_sha == pushed commit
```

**Restart is deploy.** `sudo systemctl restart bowl_pool` on edge does exactly
what a push does. The prep steps in the start script fail open: if GitHub or
PyPI is unreachable, or `init_db.py` fails, the script logs a warning to
`/var/bowl/log/deploy.log` and still starts gunicorn on whatever code is on
disk.

One gunicorn worker on purpose: `app.py` starts an APScheduler job in-process
that pulls scores every five minutes, and each worker would run its own copy.

## Layout on edge

| Path                           | Purpose                                          |
|--------------------------------|--------------------------------------------------|
| `/var/bowl/app/`               | `git clone` of github.com/mliberty1/bowl_pool    |
| `/var/bowl/venv/`              | Python venv                                      |
| `/var/bowl/env`                | Environment file, `root:bowl` 0640               |
| `/var/bowl/log/deploy.log`     | One line per start, written by the start script  |
| `/var/bowl/.requirements-hash` | Stamp so pip only runs when requirements change  |
| `/etc/systemd/system/bowl_pool.service` | Copy of `deploy/bowl_pool.service`      |

Caddy: `bowl.libertyfamily.us { reverse_proxy 127.0.0.1:8881 }`.

`/var/bowl/env` holds `SECRET_KEY`, `DATABASE_URL`, `DEPLOY_TOKEN`, and the
Mailgun variables (`MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `EMAIL_FROM`).
Generate secrets with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Never edit tracked files in `/var/bowl/app`; every start does
`git reset --hard origin/main` and discards them.

## One-time setup (switching from the hand-run unit)

Done 2026-10-26. Kept for rebuilding the host. The service was first set up
with a plain `ExecStart=gunicorn ...` unit and `Restart=on-failure`. To move
it to the webhook flow, on edge:

```bash
# 1. token into the env file (same value goes into the GitHub secret)
sudo sh -c 'echo "DEPLOY_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")" >> /var/bowl/env'
sudo grep ^DEPLOY_TOKEN /var/bowl/env          # copy this value for step 4

# 2. bring the clone up to the commit that contains deploy/
sudo -u bowl git -C /var/bowl/app pull --ff-only
ls /var/bowl/app/deploy/                       # expect bowl_pool-start.sh and bowl_pool.service

# 3. install the new unit and restart (this first restart is the first deploy)
sudo cp /var/bowl/app/deploy/bowl_pool.service /etc/systemd/system/bowl_pool.service
sudo systemctl daemon-reload
sudo systemctl restart bowl_pool
systemctl status bowl_pool --no-pager
curl -s http://127.0.0.1:8881/healthz          # git_sha should match HEAD of the clone
tail /var/bowl/log/deploy.log

# test the webhook from the LAN
TOKEN=$(sudo grep ^DEPLOY_TOKEN /var/bowl/env | cut -d= -f2)
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8881/webhook/update
# expect 202 {"status":"restarting",...}; the unit restarts within seconds
```

4. In GitHub, repo Settings -> Secrets and variables -> Actions, add
   `BOWL_POOL_DEPLOY_TOKEN` with the value from step 1.

The next push to `main` should show a green `deploy` run that finishes in
well under a minute. Expect 5 to 15 seconds of 502 from Caddy during each
deploy while gunicorn restarts, longer when `requirements.txt` changed.

If `/var/bowl/app` is not a git clone (step 2 fails), the start script will
log `git update failed` on every start and keep serving the existing code.
Fix by re-creating it as a clone:

```bash
sudo -u bowl git clone https://github.com/mliberty1/bowl_pool.git /var/bowl/app.new
sudo mv /var/bowl/app /var/bowl/app.old && sudo mv /var/bowl/app.new /var/bowl/app
sudo systemctl restart bowl_pool
```

The database must not live inside `app/`; `DATABASE_URL` in `/var/bowl/env`
should point elsewhere under `/var/bowl`.

## Schema changes

`init_db.py` runs `db.create_all()` on every start, which creates tables that
do not exist yet. It does **not** add columns to existing tables or alter
anything. For those, apply the change by hand with `sqlite3` on edge before
pushing code that depends on it, or make the code tolerate the old schema
until the column exists.

## Rollback and recovery

- **Bad push:** `git revert` and push. The Action redeploys.
- **App too broken to serve the webhook:** push the fix, then on edge
  `sudo systemctl restart bowl_pool`. The restart pulls the fix.
- **Pin an old commit temporarily:**
  `sudo -u bowl git -C /var/bowl/app reset --hard <sha>` then
  `sudo systemctl restart bowl_pool`. This only holds until the next restart
  pulls `origin/main` again, so push the revert as well.
- **What happened:** `tail /var/bowl/log/deploy.log` and
  `journalctl -u bowl_pool -n 50`.
- **The Action is red but the site is fine:** the verify step polls
  `/healthz` for three minutes; a slow pip install can exceed that. Check
  `/healthz` by hand before doing anything.

## Retiring Render

The Render service `bowl-pool` is no longer the deployment target. Once edge
has run through a bowl season without trouble, suspend and delete it, then
remove `render.yaml` and the Render notes from `DEVELOPMENT.md`.
