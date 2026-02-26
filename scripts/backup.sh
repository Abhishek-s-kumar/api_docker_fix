#!/usr/bin/env bash
# WRD API — Automated backup: PostgreSQL + git-repo
# Usage: bash scripts/backup.sh
# Cron: 0 2 * * * /app/scripts/backup.sh

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
DB_CONTAINER="${DB_CONTAINER:-wrd-postgres}"
DB_NAME="${DB_NAME:-wazuh_api}"
DB_USER="${DB_USER:-api}"
GIT_REPO="${GIT_REPO:-/app/git-repo}"

mkdir -p "$BACKUP_DIR"

echo "═══════════════════════════════════════"
echo " WRD API Backup — $TIMESTAMP"
echo "═══════════════════════════════════════"

# ── Database backup ──────────────────────────────────────────
echo "→ Backing up PostgreSQL database..."
DB_BACKUP="$BACKUP_DIR/wrd_db_${TIMESTAMP}.sql.gz"
docker exec "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DB_BACKUP"
echo "  ✓ Database: $DB_BACKUP ($(du -sh "$DB_BACKUP" | cut -f1))"

# ── Git repo backup ───────────────────────────────────────────
echo "→ Backing up git-repo..."
REPO_BACKUP="$BACKUP_DIR/wrd_rules_${TIMESTAMP}.tar.gz"
tar --exclude="$GIT_REPO/.git" -czf "$REPO_BACKUP" -C "$(dirname "$GIT_REPO")" "$(basename "$GIT_REPO")" 2>/dev/null || true
echo "  ✓ Rules: $REPO_BACKUP ($(du -sh "$REPO_BACKUP" | cut -f1))"

# ── Rotate old backups ────────────────────────────────────────
echo "→ Rotating backups older than $RETAIN_DAYS days..."
find "$BACKUP_DIR" -name "wrd_*.gz" -mtime "+$RETAIN_DAYS" -delete
REMAINING=$(find "$BACKUP_DIR" -name "wrd_*.gz" | wc -l)
echo "  ✓ $REMAINING backup(s) retained"

echo ""
echo "✅ Backup complete: $TIMESTAMP"
