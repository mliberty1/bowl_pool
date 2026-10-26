#!/usr/bin/env bash
# ExecStart for bowl_pool.service on edge. Every (re)start is a deploy:
# fast-forward to origin/main, sync the venv, create any missing tables, then
# exec gunicorn. The prep steps fail open: a GitHub or PyPI outage, or a bad
# push, logs a warning and the last code on disk still serves. Recovery from
# a broken deploy is therefore "push a fix, then systemctl restart bowl_pool".
#
# This file lives in the repo and is replaced by the git reset below while it
# is running. That is safe: git unlinks and recreates the file, and bash keeps
# reading the old inode. The new version takes effect on the next start.
#
# Same pattern as family_cookbook/deploy/cookbook-start.sh.

APP=/var/bowl/app
VENV=/var/bowl/venv
LOG=/var/bowl/log/deploy.log
STAMP=/var/bowl/.requirements-hash

log() { echo "$(date -Is) $*" | tee -a "$LOG" >&2; }

cd "$APP" || exit 1
mkdir -p "$(dirname "$LOG")"

if git fetch --quiet origin && git reset --quiet --hard origin/main; then
    log "checked out $(git rev-parse HEAD)"
else
    log "WARNING: git update failed; starting with $(git rev-parse HEAD 2>/dev/null || echo unknown)"
fi

NEW=$(sha256sum requirements.txt | cut -d' ' -f1)
if [[ "$NEW" != "$(cat "$STAMP" 2>/dev/null)" ]]; then
    if "$VENV/bin/pip" install -q -r requirements.txt; then
        echo "$NEW" > "$STAMP"
        log "requirements installed"
    else
        log "WARNING: pip install failed; continuing with existing venv"
    fi
fi

# Schema is owned by SQLAlchemy models. create_all adds missing tables only;
# column changes to existing tables are still applied by hand with sqlite3.
"$VENV/bin/python" init_db.py >/dev/null || log "WARNING: init_db.py failed; see journal"

GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
export GIT_SHA
log "starting gunicorn at $GIT_SHA"
# One worker on purpose: app.py starts an APScheduler job in-process, and
# each gunicorn worker would run its own copy of the score updater.
exec "$VENV/bin/gunicorn" app:app --bind 127.0.0.1:8881 --workers 1
