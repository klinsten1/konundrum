"""
database.py — pure sqlite3

Features:
  - users.email + country (no email confirmation)
  - attempts per sublevel visible to admin
  - admin_stats() for overview page
  - challenge_hints for trigger-based hints
  - password_resets for token-based password recovery
"""
import sqlite3, os, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "konundrum.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            username         TEXT UNIQUE NOT NULL,
            email            TEXT UNIQUE NOT NULL DEFAULT '',
            password_hash    TEXT NOT NULL,
            is_admin         INTEGER DEFAULT 0,
            country          TEXT DEFAULT '',
            created_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS stones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT UNIQUE NOT NULL,
            label        TEXT NOT NULL,
            row          INTEGER NOT NULL,
            col          INTEGER NOT NULL,
            dependencies TEXT DEFAULT '',
            home_content TEXT DEFAULT '',
            campaign     TEXT DEFAULT 'greeks'
        );
        CREATE TABLE IF NOT EXISTS challenges (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            stone_id       INTEGER NOT NULL REFERENCES stones(id),
            ord            INTEGER DEFAULT 0,
            slug           TEXT NOT NULL UNIQUE,
            title          TEXT DEFAULT '',
            points         INTEGER DEFAULT 10,
            is_final       INTEGER DEFAULT 0,
            answer_1       TEXT DEFAULT '',
            answer_name    TEXT DEFAULT '',
            answer_city    TEXT DEFAULT '',
            hint_1         TEXT DEFAULT '',
            hint_name      TEXT DEFAULT '',
            hint_city      TEXT DEFAULT '',
            hint_threshold REAL DEFAULT 0.6
        );
        CREATE TABLE IF NOT EXISTS user_attempts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(id),
            challenge_id  INTEGER NOT NULL REFERENCES challenges(id),
            stone_id      INTEGER NOT NULL REFERENCES stones(id),
            attempts      INTEGER DEFAULT 0,
            solved        INTEGER DEFAULT 0,
            points_earned INTEGER DEFAULT 0,
            first_try     TEXT DEFAULT NULL,
            solved_at     TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS user_stones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            stone_id     INTEGER NOT NULL REFERENCES stones(id),
            completed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, stone_id)
        );
        CREATE TABLE IF NOT EXISTS solve_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            challenge_id INTEGER REFERENCES challenges(id),
            stone_id     INTEGER REFERENCES stones(id),
            event_type   TEXT NOT NULL,
            label        TEXT DEFAULT '',
            points       INTEGER DEFAULT 0,
            happened_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS challenge_hints (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            field        TEXT NOT NULL DEFAULT 'answer_1',
            trigger_answer TEXT NOT NULL,
            hint_text    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            token      TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT (datetime('now')),
            used       INTEGER DEFAULT 0
        );
        -- Full log of every answer a user submits per puzzle (for later analysis).
        CREATE TABLE IF NOT EXISTS answer_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id),
            challenge_id    INTEGER NOT NULL REFERENCES challenges(id),
            stone_id        INTEGER REFERENCES stones(id),
            field           TEXT NOT NULL DEFAULT 'answer_1',
            submitted_answer TEXT NOT NULL DEFAULT '',
            is_correct      INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def migrate_db():
    """Safe migrations — add missing columns to existing DB."""
    conn = get_db()
    try:
        def add_col(table, col, typedef):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

        add_col("users", "email",            "TEXT NOT NULL DEFAULT ''")
        add_col("users", "country",          "TEXT DEFAULT ''")
        add_col("stones","home_content",     "TEXT DEFAULT ''")
        add_col("stones","campaign",         "TEXT DEFAULT 'greeks'")
        add_col("challenges","title",        "TEXT DEFAULT ''")
        add_col("challenges","points",       "INTEGER DEFAULT 10")

        # New tables for hints, password reset and the answer log
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS challenge_hints (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_id INTEGER NOT NULL REFERENCES challenges(id),
                field        TEXT NOT NULL DEFAULT 'answer_1',
                trigger_answer TEXT NOT NULL,
                hint_text    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS password_resets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                token      TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT (datetime('now')),
                used       INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS answer_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL REFERENCES users(id),
                challenge_id    INTEGER NOT NULL REFERENCES challenges(id),
                stone_id        INTEGER REFERENCES stones(id),
                field           TEXT NOT NULL DEFAULT 'answer_1',
                submitted_answer TEXT NOT NULL DEFAULT '',
                is_correct      INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            );
        """)
        # Make sure existing stones have a campaign set
        conn.execute("UPDATE stones SET campaign='greeks' WHERE campaign IS NULL OR campaign=''")
        conn.commit()
    finally:
        conn.close()


# ── users ──────────────────────────────────────────────────────────────────────

def create_user(username, email, password_hash, is_admin=False, country=""):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username,email,password_hash,is_admin,country) VALUES (?,?,?,?,?)",
            (username, email, password_hash, 1 if is_admin else 0, country))
        conn.commit()
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()

def update_user_country(user_id, country):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET country=? WHERE id=?", (country, user_id))
        conn.commit()
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()

def get_user_by_email(email):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    finally:
        conn.close()

def get_user_by_id(uid):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    finally:
        conn.close()

def get_all_users():
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()


# ── stones ─────────────────────────────────────────────────────────────────────

def get_all_stones():
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM stones ORDER BY row,col").fetchall()
    finally:
        conn.close()

def get_stones_by_campaign(campaign):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM stones WHERE campaign=? ORDER BY row,col", (campaign,)).fetchall()
    finally:
        conn.close()

def get_all_campaigns():
    """Distinct campaign names that currently have stones."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT campaign FROM stones WHERE campaign IS NOT NULL AND campaign<>'' ORDER BY campaign"
        ).fetchall()
        return [r["campaign"] for r in rows]
    finally:
        conn.close()

def get_stone(stone_id):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM stones WHERE id=?", (stone_id,)).fetchone()
    finally:
        conn.close()

def get_stone_by_name(name):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM stones WHERE name=?", (name,)).fetchone()
    finally:
        conn.close()

def create_stone(name, label, row, col, deps="", home_content="", campaign="greeks"):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO stones (name,label,row,col,dependencies,home_content,campaign) VALUES (?,?,?,?,?,?,?)",
            (name, label, row, col, deps, home_content, campaign or "greeks"))
        conn.commit()
        return conn.execute("SELECT * FROM stones WHERE name=?", (name,)).fetchone()
    finally:
        conn.close()

def update_stone(stone_id, name, label, row, col, deps, home_content="", campaign="greeks"):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE stones SET name=?,label=?,row=?,col=?,dependencies=?,home_content=?,campaign=? WHERE id=?",
            (name, label, row, col, deps, home_content, campaign or "greeks", stone_id))
        conn.commit()
    finally:
        conn.close()

def delete_stone(stone_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM user_stones   WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM user_attempts WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM solve_history WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM answer_log    WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM challenges    WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM stones        WHERE id=?",       (stone_id,))
        conn.commit()
    finally:
        conn.close()


# ── challenges ─────────────────────────────────────────────────────────────────

def get_challenges_safe(stone_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id,stone_id,ord,slug,title,points,is_final FROM challenges WHERE stone_id=? ORDER BY ord",
            (stone_id,)).fetchall()
    finally:
        conn.close()

def get_challenge_safe(challenge_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id,stone_id,ord,slug,title,points,is_final FROM challenges WHERE id=?",
            (challenge_id,)).fetchone()
    finally:
        conn.close()

def get_challenge_full(challenge_id):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,)).fetchone()
    finally:
        conn.close()

def get_challenge_by_slug(slug):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id,stone_id,ord,slug,title,points,is_final FROM challenges WHERE slug=?",
            (slug,)).fetchone()
    finally:
        conn.close()

def create_challenge(stone_id, slug, title, points, is_final,
                     answer_1, answer_name, answer_city,
                     hint_1, hint_name, hint_city, hint_threshold, order):
    conn = get_db()
    try:
        conn.execute("""INSERT INTO challenges
            (stone_id,slug,title,points,is_final,answer_1,answer_name,answer_city,
             hint_1,hint_name,hint_city,hint_threshold,ord)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (stone_id, slug, title, points, 1 if is_final else 0,
             answer_1, answer_name, answer_city,
             hint_1, hint_name, hint_city, hint_threshold, order))
        conn.commit()
    finally:
        conn.close()

def update_challenge(challenge_id, slug, title, points, is_final,
                     answer_1, answer_name, answer_city,
                     hint_1, hint_name, hint_city, hint_threshold, order):
    conn = get_db()
    try:
        conn.execute("""UPDATE challenges SET
            slug=?,title=?,points=?,is_final=?,answer_1=?,answer_name=?,answer_city=?,
            hint_1=?,hint_name=?,hint_city=?,hint_threshold=?,ord=? WHERE id=?""",
            (slug, title, points, 1 if is_final else 0,
             answer_1, answer_name, answer_city,
             hint_1, hint_name, hint_city, hint_threshold, order, challenge_id))
        conn.commit()
    finally:
        conn.close()

def delete_challenge(challenge_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM challenge_hints  WHERE challenge_id=?", (challenge_id,))
        conn.execute("DELETE FROM user_attempts    WHERE challenge_id=?", (challenge_id,))
        conn.execute("DELETE FROM solve_history    WHERE challenge_id=?", (challenge_id,))
        conn.execute("DELETE FROM answer_log       WHERE challenge_id=?", (challenge_id,))
        conn.execute("DELETE FROM challenges       WHERE id=?",           (challenge_id,))
        conn.commit()
    finally:
        conn.close()

def slug_exists(slug, exclude_id=None):
    conn = get_db()
    try:
        if exclude_id:
            return conn.execute("SELECT 1 FROM challenges WHERE slug=? AND id!=?",
                                (slug, exclude_id)).fetchone() is not None
        return conn.execute("SELECT 1 FROM challenges WHERE slug=?",
                            (slug,)).fetchone() is not None
    finally:
        conn.close()

def count_challenges_for_stone(stone_id):
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM challenges WHERE stone_id=?",
                            (stone_id,)).fetchone()[0]
    finally:
        conn.close()

def count_all_challenges():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM challenges").fetchone()[0]
    finally:
        conn.close()

def get_all_slugs():
    conn = get_db()
    try:
        return [r[0] for r in conn.execute("SELECT slug FROM challenges").fetchall()]
    finally:
        conn.close()

def total_possible_points():
    conn = get_db()
    try:
        r = conn.execute("SELECT SUM(points) FROM challenges").fetchone()[0]
        return r or 0
    finally:
        conn.close()


# ── attempts & progress ────────────────────────────────────────────────────────

def record_attempt(user_id, stone_id, challenge_id):
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM user_attempts WHERE user_id=? AND challenge_id=?",
            (user_id, challenge_id)).fetchone()
        if existing:
            if existing["solved"]:
                return existing["attempts"]
            conn.execute(
                "UPDATE user_attempts SET attempts=attempts+1 WHERE user_id=? AND challenge_id=?",
                (user_id, challenge_id))
        else:
            conn.execute(
                "INSERT INTO user_attempts (user_id,challenge_id,stone_id,attempts,first_try) VALUES (?,?,?,1,datetime('now'))",
                (user_id, challenge_id, stone_id))
        conn.commit()
        r = conn.execute("SELECT attempts FROM user_attempts WHERE user_id=? AND challenge_id=?",
                         (user_id, challenge_id)).fetchone()
        return r["attempts"] if r else 1
    finally:
        conn.close()

def mark_challenge_solved(user_id, stone_id, challenge_id, points):
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM user_attempts WHERE user_id=? AND challenge_id=?",
            (user_id, challenge_id)).fetchone()
        if existing and existing["solved"]:
            return False
        if existing:
            conn.execute(
                "UPDATE user_attempts SET solved=1,points_earned=?,solved_at=datetime('now') WHERE user_id=? AND challenge_id=?",
                (points, user_id, challenge_id))
        else:
            conn.execute(
                "INSERT INTO user_attempts (user_id,challenge_id,stone_id,attempts,solved,points_earned,first_try,solved_at) VALUES (?,?,?,1,1,?,datetime('now'),datetime('now'))",
                (user_id, challenge_id, stone_id, points))
        ch = conn.execute("SELECT slug,title FROM challenges WHERE id=?", (challenge_id,)).fetchone()
        label = (ch["title"] or ch["slug"]) if ch else str(challenge_id)
        conn.execute(
            "INSERT INTO solve_history (user_id,challenge_id,stone_id,event_type,label,points) VALUES (?,?,?,'challenge',?,?)",
            (user_id, challenge_id, stone_id, label, points))
        conn.commit()
        return True
    finally:
        conn.close()

def mark_stone_completed(user_id, stone_id):
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO user_stones (user_id,stone_id) VALUES (?,?)", (user_id, stone_id))
        stone = conn.execute("SELECT label FROM stones WHERE id=?", (stone_id,)).fetchone()
        label = stone["label"] if stone else str(stone_id)
        conn.execute(
            "INSERT INTO solve_history (user_id,stone_id,event_type,label,points) VALUES (?,?,'stone',?,0)",
            (user_id, stone_id, label))
        conn.commit()
    finally:
        conn.close()

# ── answer log (every submission per puzzle, for later analysis) ────────────────

def log_answer(user_id, challenge_id, stone_id, field, submitted_answer, is_correct):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO answer_log (user_id,challenge_id,stone_id,field,submitted_answer,is_correct) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, challenge_id, stone_id, field, submitted_answer, 1 if is_correct else 0))
        conn.commit()
    finally:
        conn.close()

def get_answer_log_for_challenge(challenge_id, limit=500):
    """All submissions for one puzzle, newest first, with usernames."""
    conn = get_db()
    try:
        return conn.execute("""
            SELECT al.*, u.username
            FROM answer_log al
            JOIN users u ON u.id = al.user_id
            WHERE al.challenge_id=?
            ORDER BY al.created_at DESC
            LIMIT ?
        """, (challenge_id, limit)).fetchall()
    finally:
        conn.close()

def get_answer_log(limit=1000):
    """Full answer log across all puzzles, newest first."""
    conn = get_db()
    try:
        return conn.execute("""
            SELECT al.*, u.username, c.slug, c.title
            FROM answer_log al
            JOIN users u ON u.id = al.user_id
            LEFT JOIN challenges c ON c.id = al.challenge_id
            ORDER BY al.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

def count_answer_log():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM answer_log").fetchone()[0]
    finally:
        conn.close()


def get_solved_challenge_ids(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT challenge_id FROM user_attempts WHERE user_id=? AND solved=1", (user_id,)).fetchall()
        return {r["challenge_id"] for r in rows}
    finally:
        conn.close()

def get_completed_stone_ids(user_id):
    conn = get_db()
    try:
        rows = conn.execute("SELECT stone_id FROM user_stones WHERE user_id=?", (user_id,)).fetchall()
        return {r["stone_id"] for r in rows}
    finally:
        conn.close()

def get_user_total_points(user_id):
    conn = get_db()
    try:
        r = conn.execute(
            "SELECT SUM(points_earned) FROM user_attempts WHERE user_id=? AND solved=1", (user_id,)).fetchone()[0]
        return r or 0
    finally:
        conn.close()

def get_attempt_count(user_id, challenge_id):
    conn = get_db()
    try:
        r = conn.execute("SELECT attempts FROM user_attempts WHERE user_id=? AND challenge_id=?",
                         (user_id, challenge_id)).fetchone()
        return r["attempts"] if r else 0
    finally:
        conn.close()

def get_user_stats(user_id):
    conn = get_db()
    try:
        pts = conn.execute(
            "SELECT SUM(points_earned) FROM user_attempts WHERE user_id=? AND solved=1",
            (user_id,)).fetchone()[0] or 0
        solved_ch = conn.execute(
            "SELECT COUNT(*) FROM user_attempts WHERE user_id=? AND solved=1", (user_id,)).fetchone()[0]
        total_attempts = conn.execute(
            "SELECT SUM(attempts) FROM user_attempts WHERE user_id=?", (user_id,)).fetchone()[0] or 0
        solved_stones = conn.execute(
            "SELECT COUNT(*) FROM user_stones WHERE user_id=?", (user_id,)).fetchone()[0]
        attempts_per_ch = conn.execute("""
            SELECT c.slug, c.title, ua.attempts, ua.solved, ua.points_earned, ua.first_try, ua.solved_at
            FROM user_attempts ua
            JOIN challenges c ON c.id = ua.challenge_id
            WHERE ua.user_id=? ORDER BY ua.first_try DESC
        """, (user_id,)).fetchall()
        history = conn.execute("""
            SELECT * FROM solve_history WHERE user_id=?
            ORDER BY happened_at DESC LIMIT 50
        """, (user_id,)).fetchall()
        user = conn.execute(
            "SELECT username, email, country, created_at FROM users WHERE id=?",
            (user_id,)).fetchone()
        return {
            "points": pts, "solved_challenges": solved_ch,
            "total_attempts": total_attempts, "solved_stones": solved_stones,
            "attempts_per_challenge": attempts_per_ch, "history": history,
            "user": user,
        }
    finally:
        conn.close()


# ── admin stats ────────────────────────────────────────────────────────────────

def get_admin_stats():
    """All stats for admin overview page."""
    conn = get_db()
    try:
        total_users    = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0]
        total_stones   = conn.execute("SELECT COUNT(*) FROM stones").fetchone()[0]
        total_ch       = conn.execute("SELECT COUNT(*) FROM challenges").fetchone()[0]
        total_pts      = conn.execute("SELECT SUM(points) FROM challenges").fetchone()[0] or 0
        total_attempts = conn.execute("SELECT SUM(attempts) FROM user_attempts").fetchone()[0] or 0
        total_solves   = conn.execute("SELECT SUM(solved) FROM user_attempts").fetchone()[0] or 0

        # Attempts per challenge — sorted by most attempts (hint indicator)
        ch_attempts = conn.execute("""
            SELECT c.slug, c.title, c.points,
                   COALESCE(SUM(ua.attempts),0) AS total_attempts,
                   COALESCE(SUM(ua.solved),0)   AS total_solves,
                   COUNT(DISTINCT ua.user_id)   AS unique_players
            FROM challenges c
            LEFT JOIN user_attempts ua ON ua.challenge_id = c.id
            GROUP BY c.id
            ORDER BY total_attempts DESC, total_solves ASC
        """).fetchall()

        # Recent activity (last 20 events across all users)
        recent = conn.execute("""
            SELECT sh.*, u.username
            FROM solve_history sh
            JOIN users u ON u.id = sh.user_id
            ORDER BY sh.happened_at DESC LIMIT 20
        """).fetchall()

        # Users list with stats
        users = conn.execute("""
            SELECT u.id, u.username, u.email, u.country, u.created_at,
                   COALESCE(SUM(ua.points_earned),0) AS points,
                   COALESCE(SUM(ua.solved),0)        AS solved_ch,
                   COALESCE(SUM(ua.attempts),0)      AS attempts,
                   COALESCE(us.stones,0)             AS solved_stones
            FROM users u
            LEFT JOIN user_attempts ua ON ua.user_id = u.id
            LEFT JOIN (SELECT user_id, COUNT(*) AS stones FROM user_stones GROUP BY user_id) us
                   ON us.user_id = u.id
            WHERE u.is_admin = 0
            GROUP BY u.id
            ORDER BY points DESC
        """).fetchall()

        return {
            "total_users": total_users,
            "total_stones": total_stones, "total_ch": total_ch,
            "total_pts": total_pts, "total_attempts": total_attempts,
            "total_solves": total_solves,
            "ch_attempts": ch_attempts, "recent": recent, "users": users,
        }
    finally:
        conn.close()


# ── challenge hints (trigger-based) ────────────────────────────────────────────

def get_hints_for_challenge(challenge_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM challenge_hints WHERE challenge_id=? ORDER BY id",
            (challenge_id,)).fetchall()
    finally:
        conn.close()

def get_hint_for_answer(challenge_id, field, user_answer):
    """Find a hint based on exact trigger answer (case-insensitive)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM challenge_hints WHERE challenge_id=? AND field=?",
            (challenge_id, field)).fetchall()
        user_clean = user_answer.lower().strip()
        for row in rows:
            if row["trigger_answer"].lower().strip() == user_clean:
                return row["hint_text"]
        return None
    finally:
        conn.close()

def create_hint(challenge_id, field, trigger_answer, hint_text):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO challenge_hints (challenge_id,field,trigger_answer,hint_text) VALUES (?,?,?,?)",
            (challenge_id, field, trigger_answer, hint_text))
        conn.commit()
    finally:
        conn.close()

def update_hint(hint_id, field, trigger_answer, hint_text):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE challenge_hints SET field=?,trigger_answer=?,hint_text=? WHERE id=?",
            (field, trigger_answer, hint_text, hint_id))
        conn.commit()
    finally:
        conn.close()

def delete_hint(hint_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM challenge_hints WHERE id=?", (hint_id,))
        conn.commit()
    finally:
        conn.close()

def delete_hints_for_challenge(challenge_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM challenge_hints WHERE challenge_id=?", (challenge_id,))
        conn.commit()
    finally:
        conn.close()


# ── password reset ─────────────────────────────────────────────────────────────

def create_password_reset(user_id):
    token = secrets.token_urlsafe(32)
    conn = get_db()
    try:
        # Invalidate previous tokens
        conn.execute("UPDATE password_resets SET used=1 WHERE user_id=? AND used=0", (user_id,))
        conn.execute(
            "INSERT INTO password_resets (user_id, token) VALUES (?,?)",
            (user_id, token))
        conn.commit()
        return token
    finally:
        conn.close()

def get_valid_reset_token(token):
    """Returns reset row if token is valid (< 1 hour old, not used)."""
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT * FROM password_resets
            WHERE token=? AND used=0
              AND datetime(created_at, '+1 hour') > datetime('now')
        """, (token,)).fetchone()
        return row
    finally:
        conn.close()

def use_reset_token(token):
    conn = get_db()
    try:
        conn.execute("UPDATE password_resets SET used=1 WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()

def update_user_password(user_id, password_hash):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
        conn.commit()
    finally:
        conn.close()


# ── hall of fame ───────────────────────────────────────────────────────────────

def get_hall_of_fame():
    conn = get_db()
    try:
        return conn.execute("""
            SELECT u.username,
                   COALESCE(SUM(ua.points_earned),0) AS total_points,
                   COALESCE(SUM(ua.solved),0)        AS solved_challenges,
                   COALESCE(us.solved_stones,0)      AS solved_stones,
                   COALESCE(SUM(ua.attempts),0)      AS total_attempts
            FROM users u
            LEFT JOIN user_attempts ua ON ua.user_id = u.id
            LEFT JOIN (SELECT user_id, COUNT(*) AS solved_stones FROM user_stones GROUP BY user_id) us
                   ON us.user_id = u.id
            WHERE u.is_admin = 0
            GROUP BY u.id
            ORDER BY total_points DESC, solved_challenges DESC
        """).fetchall()
    finally:
        conn.close()


# ── seed ───────────────────────────────────────────────────────────────────────

def seed_demo_data():
    from werkzeug.security import generate_password_hash
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM stones").fetchone()[0]
    conn.close()
    if count > 0:
        return
    create_stone("S1","CIPHER-1",0,0,"","<p>Classic substitution ciphers. Solve sublevels in any order — NAME+CITY last.</p>")
    create_stone("S2","CIPHER-2",0,1,"","<p>Encoding techniques.</p>")
    create_stone("S3","CIPHER-3",0,2,"")
    create_stone("S4","CIPHER-4",0,3,"")
    create_stone("S5","LEVEL-2A",1,0,"S1,S2")
    create_stone("S6","LEVEL-2B",1,1,"S2,S3")
    create_stone("S7","LEVEL-2C",1,2,"S3,S4")
    create_stone("S8","LEVEL-3A",2,0,"S5,S6")
    create_stone("S9","LEVEL-3B",2,1,"S6,S7")
    create_stone("S10","MASTER",3,0,"S8,S9")
    create_challenge(1,"s1_c1","ROT13",10,False,"HELLO WORLD","","","","","",0,0)
    create_challenge(1,"s1_c2","Who am I?",20,True,"","Alan Turing","London","","","",0,1)
    create_challenge(2,"s2_c1","Who is this?",20,True,"","Grace Hopper","New York","","","",0,0)
    create_challenge(3,"s3_c1","Atbash",10,False,"CRYPTO","","","","","",0,0)
    create_challenge(4,"s4_c1","Information Theory",20,True,"","Claude Shannon","Gaylord","","","",0,0)
    if not get_user_by_username("admin"):
        create_user("admin","admin@konundrum.local",generate_password_hash("admin123"),is_admin=True)
