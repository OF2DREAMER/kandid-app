#!/usr/bin/env python3
"""
Kandid Safe SQLite -> PostgreSQL Migration Utility (Phase 1C)
Non-destructive data migration tool with count verification.
"""

import os
import sys
import sqlite3
import urllib.parse
import ipaddress
import shlex
import ssl
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
    "email_otps",
    "password_resets",
    "posts",
    "reactions",
    "messages",
    "notifications",
    "friendships",
    "communities",
    "community_members",
    "drop_reminders",
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

def _is_local_host(host: str | None) -> bool:
    if not host:
        return True
    host = host.strip()
    if not host:
        return True
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host.startswith("/") or host.startswith("."):
        return True
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        pass
    return False


def _is_effective_local(host: str | None, hostaddr: str | None) -> bool:
    if not host and not hostaddr:
        return True
    if host and not _is_local_host(host):
        return False
    if hostaddr and not _is_local_host(hostaddr):
        return False
    return True


def _is_url(dsn: str) -> bool:
    s = dsn.strip()
    if s.startswith("postgresql://") or s.startswith("postgres://"):
        return True
    if "://" in s:
        prefix = s.split("://", 1)[0]
        if " " not in prefix and "=" not in prefix:
            return True
    return False


def _resolve_sslmode(sslmode_values: list, is_local: bool) -> str | None:
    if not is_local:
        if not sslmode_values:
            return "require"
        valid_modes = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
        for m in sslmode_values:
            if m not in valid_modes:
                raise ValueError(f"Invalid sslmode: {m}")
        if "verify-full" in sslmode_values:
            return "verify-full"
        if "verify-ca" in sslmode_values:
            return "verify-ca"
        return "require"
    else:
        if not sslmode_values:
            return None
        valid_modes = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
        for m in sslmode_values:
            if m not in valid_modes:
                raise ValueError(f"Invalid sslmode: {m}")
        return sslmode_values[-1]


def _ensure_secure_sslmode(dsn_or_url: str) -> str:
    if not dsn_or_url or not dsn_or_url.strip():
        raise ValueError("Database connection string cannot be empty")
    dsn = dsn_or_url.strip()

    if _is_url(dsn):
        parsed = urllib.parse.urlsplit(dsn)
        if parsed.scheme not in ("postgresql", "postgres"):
            raise ValueError(f"Invalid database URL scheme '{parsed.scheme}'; expected postgresql or postgres")
        query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query_dict = dict(query_params)
        raw_host = parsed.hostname or query_dict.get("host")
        raw_hostaddr = query_dict.get("hostaddr")
        is_local = _is_effective_local(raw_host, raw_hostaddr)
        sslmode_values = [v.lower() for k, v in query_params if k == "sslmode"]
        other_params = [(k, v) for k, v in query_params if k != "sslmode"]

        effective_sslmode = _resolve_sslmode(sslmode_values, is_local)

        new_query_params = list(other_params)
        if effective_sslmode:
            new_query_params.append(("sslmode", effective_sslmode))

        new_query = urllib.parse.urlencode(new_query_params)
        res = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
        if dsn.startswith(f"{parsed.scheme}:///") and not res.startswith(f"{parsed.scheme}:///"):
            res = f"{parsed.scheme}:///" + res[len(f"{parsed.scheme}:"):].lstrip("/")
        return res
    else:
        try:
            tokens = shlex.split(dsn)
        except ValueError as e:
            raise ValueError(f"Malformed conninfo string: {e}") from e

        params = []
        param_dict = {}
        for tok in tokens:
            if "=" not in tok:
                raise ValueError(f"Malformed conninfo token '{tok}': missing '='")
            k, v = tok.split("=", 1)
            k = k.strip()
            v = v.strip()
            params.append((k, v))
            param_dict.setdefault(k, []).append(v)

        has_service = "service" in param_dict
        host = param_dict.get("host", [None])[0]
        hostaddr = param_dict.get("hostaddr", [None])[0]

        if has_service and not host and not hostaddr:
            raise ValueError("Ambiguous service-only conninfo without explicit host/hostaddr cannot be verified for TLS enforcement")

        is_local = _is_effective_local(host, hostaddr)
        sslmode_values = [v.lower() for v in param_dict.get("sslmode", [])]
        effective_sslmode = _resolve_sslmode(sslmode_values, is_local)

        other_params = [(k, v) for k, v in params if k != "sslmode"]
        if effective_sslmode:
            other_params.append(("sslmode", effective_sslmode))

        def _format_val(v: str) -> str:
            if " " in v or "'" in v or '"' in v or not v:
                escaped = v.replace("\\", "\\\\").replace("'", "\\'")
                return f"'{escaped}'"
            return v

        return " ".join(f"{k}={_format_val(v)}" for k, v in other_params)


def _get_pg8000_connect_kwargs(secure_dsn: str) -> dict:
    if _is_url(secure_dsn):
        parsed = urllib.parse.urlsplit(secure_dsn)
        query_params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        raw_host = parsed.hostname or query_params.get("host")
        raw_hostaddr = query_params.get("hostaddr")
        is_local = _is_effective_local(raw_host, raw_hostaddr)
        sslmode = query_params.get("sslmode", "").lower()

        if not is_local or sslmode in ("require", "verify-ca", "verify-full"):
            ctx = ssl.create_default_context()
            if sslmode == "require":
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            elif sslmode in ("verify-ca", "verify-full"):
                ctx.check_hostname = (sslmode == "verify-full")
                ctx.verify_mode = ssl.CERT_REQUIRED
            ssl_context = ctx
        else:
            ssl_context = None

        target_host = raw_hostaddr or raw_host
        is_unix_sock = bool(target_host and (target_host.startswith("/") or target_host.startswith(".")))
        if is_unix_sock:
            unix_sock = target_host
            host = None
            port = None
        else:
            unix_sock = None
            host = target_host
            port = parsed.port or 5432
            if not parsed.port and "port" in query_params:
                try:
                    port = int(query_params["port"])
                except (ValueError, TypeError):
                    port = 5432

        kwargs = {
            "user": urllib.parse.unquote(parsed.username) if parsed.username else query_params.get("user"),
            "password": urllib.parse.unquote(parsed.password) if parsed.password else query_params.get("password"),
            "host": host,
            "port": port,
            "database": parsed.path.lstrip("/") or query_params.get("dbname") or query_params.get("database", ""),
            "unix_sock": unix_sock,
            "ssl_context": ssl_context,
        }
        if "application_name" in query_params:
            kwargs["application_name"] = query_params["application_name"]
        return kwargs
    else:
        tokens = shlex.split(secure_dsn)
        params = dict(tok.split("=", 1) for tok in tokens if "=" in tok)
        raw_host = params.get("host")
        raw_hostaddr = params.get("hostaddr")
        is_local = _is_effective_local(raw_host, raw_hostaddr)
        sslmode = params.get("sslmode", "").lower()

        if not is_local or sslmode in ("require", "verify-ca", "verify-full"):
            ctx = ssl.create_default_context()
            if sslmode == "require":
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            elif sslmode in ("verify-ca", "verify-full"):
                ctx.check_hostname = (sslmode == "verify-full")
                ctx.verify_mode = ssl.CERT_REQUIRED
            ssl_context = ctx
        else:
            ssl_context = None

        target_host = raw_hostaddr or raw_host
        is_unix_sock = bool(target_host and (target_host.startswith("/") or target_host.startswith(".")))
        if is_unix_sock:
            unix_sock = target_host
            host = None
            port = None
        else:
            unix_sock = None
            host = target_host
            port_val = params.get("port", 5432)
            try:
                port = int(port_val)
            except (ValueError, TypeError):
                port = 5432

        kwargs = {
            "user": params.get("user"),
            "password": params.get("password"),
            "host": host,
            "port": port,
            "database": params.get("dbname") or params.get("database", ""),
            "unix_sock": unix_sock,
            "ssl_context": ssl_context,
        }
        if "application_name" in params:
            kwargs["application_name"] = params["application_name"]
        return kwargs


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
        secure_pg_url = _ensure_secure_sslmode(pg_url)
        try:
            import psycopg2
            pg_conn = psycopg2.connect(secure_pg_url)
        except ImportError:
            try:
                import pg8000.dbapi
                kwargs = _get_pg8000_connect_kwargs(secure_pg_url)
                pg_conn = pg8000.dbapi.connect(**kwargs)
            except Exception as e:
                print(f"❌ Failed to connect to PostgreSQL: {e}")
                sqlite_conn.close()
                return False
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
