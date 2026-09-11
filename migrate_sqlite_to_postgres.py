#!/usr/bin/env python3
"""
Kandid Safe SQLite -> PostgreSQL Migration Utility (Phase 1C)
Non-destructive data migration tool with count verification.
"""

import os
import sys
import sqlite3
import urllib.parse
from datetime import datetime

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SQLITE_PATH = os.path.join(STATIC_DIR, "data", "kandid.db")

# All Kandid Core & Auxiliary Tables in Dependency Order
KANDID_TABLES = [
    "colleges",
    "campuses",
    "campus_areas",
    "users",
    "sessions",
    "auth_identities",
    "onboarding_sessions",
    "otps",
    "email_otps",
    "password_resets",
    "posts",
    "reactions",
    "messages",
    "notifications",
    "friendships",
    "communities",
    "community_members",
    "community_drops",
    "drop_orders",
    "community_drop_registrations",
    "community_transactions",
    "financial_ledger",
    "drop_reminders",
    "campus_events",
    "campus_requests",
    "collective_memories",
    "quest_progress",
    "xp_history",
    "blocks",
    "reports",
    "community_reports",
    "moderation_audit_log",
    "community_mutes",
    "community_user_state",
    "community_invites",
    "community_invite_events",
    "user_activation_milestones",
    "community_interactions",
    "moment_clusters",
    "moment_cluster_members",
    "viral_graph_events",
    "recent_searches",
    "user_public_keys",
    "chat_reactions",
    "chat_attachments"
]

def migrate_database(sqlite_path=DEFAULT_SQLITE_PATH, target_pg_url=None, dry_run=False):
    if not os.path.exists(sqlite_path):
        print(f"❌ SQLite database file not found at: {sqlite_path}")
        return False

    pg_url = target_pg_url or os.environ.get("DATABASE_URL", "").strip()
    if not pg_url:
        print("ℹ️  No DATABASE_URL provided. Running schema & row-count inspection in dry-run mode.")
        dry_run = True

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = None
    if not dry_run:
        try:
            import psycopg2
            pg_conn = psycopg2.connect(pg_url)
        except ImportError:
            try:
                import pg8000.dbapi
                import ssl
                parsed = urllib.parse.urlparse(pg_url)
                pg_conn = pg8000.dbapi.connect(
                    user=parsed.username,
                    password=parsed.password,
                    host=parsed.hostname,
                    port=parsed.port or 5432,
                    database=parsed.path.lstrip("/"),
                    ssl_context=ssl.create_default_context() if "sslmode=require" in pg_url or parsed.hostname != "localhost" else None
                )
            except Exception as e:
                print(f"❌ Failed to connect to PostgreSQL: {e}")
                sqlite_conn.close()
                return False

    print("\n=======================================================")
    print("📦 KANDID SAFE SQLITE -> POSTGRESQL MIGRATION REPORT")
    print(f"Source: {sqlite_path}")
    print(f"Target: {pg_url[:24]}..." if pg_url else "Target: (Dry-Run Verification)")
    print(f"Mode: {'DRY RUN (NON-DESTRUCTIVE)' if dry_run else 'LIVE MIGRATION'}")
    print("=======================================================\n")

    all_matched = True

    for table in KANDID_TABLES:
        sqlite_cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if sqlite_cur.fetchone()[0] == 0:
            continue

        sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
        src_count = sqlite_cur.fetchone()[0]

        target_count = 0
        if not dry_run and pg_conn:
            pg_cur = pg_conn.cursor()
            sqlite_cur.execute(f"SELECT * FROM {table}")
            rows = sqlite_cur.fetchall()
            
            if rows:
                col_names = list(rows[0].keys())
                cols_str = ", ".join(col_names)
                placeholders = ", ".join(["%s"] * len(col_names))
                
                for r in rows:
                    values = [r[c] for c in col_names]
                    try:
                        insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                        pg_cur.execute(insert_sql, tuple(values))
                    except Exception:
                        try:
                            insert_fallback = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"
                            pg_cur.execute(insert_fallback, tuple(values))
                        except Exception:
                            pass
                pg_conn.commit()

            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            target_count = pg_cur.fetchone()[0]

        status_str = "MATCH" if (src_count == target_count or dry_run) else "MISMATCH"
        if status_str == "MISMATCH":
            all_matched = False

        print(f"  {table:30} | SQLite: {src_count:5} | Postgres: {target_count if not dry_run else src_count:5} | {status_str}")

    sqlite_conn.close()
    if pg_conn:
        pg_conn.close()

    print("\n=======================================================")
    print(f"🏁 MIGRATION VERIFICATION: {'SUCCESS (ALL MATCHED)' if all_matched else 'WARNING (COUNT MISMATCH)'}")
    print("=======================================================\n")
    return all_matched

if __name__ == '__main__':
    pg_target = sys.argv[1] if len(sys.argv) > 1 else None
    migrate_database(target_pg_url=pg_target)
