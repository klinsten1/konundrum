"""
database.py — pure sqlite3

Veiligheidsregel:
  get_challenges_safe()  → geen antwoorden, veilig voor templates
  get_challenge_full()   → met antwoorden, ALLEEN server-side in /api/check

Challenge types:
  is_final=0  →  1 antwoordveld  (answer_1)
  is_final=1  →  2 antwoordvelden (answer_name + answer_city)
               Dit is automatisch het laatste sublevel van een steen.

Piramide:
  Stenen hebben row + col. De piramide bouwt zichzelf op uit de database.
  Nieuwe steen toevoegen = piramide groeit automatisch.
"""
import sqlite3, os

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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin      INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT UNIQUE NOT NULL,   -- bijv. S1
            label        TEXT NOT NULL,           -- weergavenaam op blok
            row          INTEGER NOT NULL,        -- 0 = onderste rij
            col          INTEGER NOT NULL,        -- positie in rij
            dependencies TEXT DEFAULT ''          -- komma-gescheiden stone.name waarden
        );

        CREATE TABLE IF NOT EXISTS challenges (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            stone_id       INTEGER NOT NULL REFERENCES stones(id),
            ord            INTEGER DEFAULT 0,
            slug           TEXT NOT NULL UNIQUE,  -- challenges/<slug>.html
            is_final       INTEGER DEFAULT 0,     -- 1 = laatste sublevel → name+city
            answer_1       TEXT    DEFAULT '',    -- voor is_final=0
            answer_name    TEXT    DEFAULT '',    -- voor is_final=1
            answer_city    TEXT    DEFAULT '',    -- voor is_final=1
            hint_1         TEXT    DEFAULT '',
            hint_name      TEXT    DEFAULT '',
            hint_city      TEXT    DEFAULT '',
            hint_threshold REAL    DEFAULT 0.6
        );

        CREATE TABLE IF NOT EXISTS user_progress (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id),
            stone_id        INTEGER NOT NULL REFERENCES stones(id),
            challenge_id    INTEGER REFERENCES challenges(id),
            stone_completed INTEGER DEFAULT 0,
            solved_at       TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ── users ──────────────────────────────────────────────────────────────────────

def create_user(username, password_hash, is_admin=False):
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username,password_hash,is_admin) VALUES (?,?,?)",
                     (username, password_hash, 1 if is_admin else 0))
        conn.commit()
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()

def get_user_by_username(username):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    finally:
        conn.close()

def get_user_by_id(uid):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    finally:
        conn.close()


# ── stones ─────────────────────────────────────────────────────────────────────

def get_all_stones():
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM stones ORDER BY row,col").fetchall()
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

def create_stone(name, label, row, col, deps=""):
    conn = get_db()
    try:
        conn.execute("INSERT INTO stones (name,label,row,col,dependencies) VALUES (?,?,?,?,?)",
                     (name, label, row, col, deps))
        conn.commit()
        return conn.execute("SELECT * FROM stones WHERE name=?", (name,)).fetchone()
    finally:
        conn.close()

def update_stone(stone_id, name, label, row, col, deps):
    conn = get_db()
    try:
        conn.execute("UPDATE stones SET name=?,label=?,row=?,col=?,dependencies=? WHERE id=?",
                     (name, label, row, col, deps, stone_id))
        conn.commit()
    finally:
        conn.close()

def delete_stone(stone_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM user_progress WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM challenges    WHERE stone_id=?", (stone_id,))
        conn.execute("DELETE FROM stones        WHERE id=?",       (stone_id,))
        conn.commit()
    finally:
        conn.close()


# ── challenges ─────────────────────────────────────────────────────────────────

def get_challenges_safe(stone_id):
    """Geen antwoord-/hintvelden — veilig voor templates."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id,stone_id,ord,slug,is_final FROM challenges WHERE stone_id=? ORDER BY ord",
            (stone_id,)).fetchall()
    finally:
        conn.close()

def get_challenge_safe(challenge_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id,stone_id,ord,slug,is_final FROM challenges WHERE id=?",
            (challenge_id,)).fetchone()
    finally:
        conn.close()

def get_challenge_full(challenge_id):
    """Volledige rij met antwoorden — ALLEEN server-side gebruiken."""
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,)).fetchone()
    finally:
        conn.close()

def create_challenge(stone_id, slug, is_final,
                     answer_1, answer_name, answer_city,
                     hint_1, hint_name, hint_city,
                     hint_threshold, order):
    conn = get_db()
    try:
        conn.execute("""INSERT INTO challenges
            (stone_id,slug,is_final,answer_1,answer_name,answer_city,
             hint_1,hint_name,hint_city,hint_threshold,ord)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (stone_id, slug, 1 if is_final else 0,
             answer_1, answer_name, answer_city,
             hint_1, hint_name, hint_city, hint_threshold, order))
        conn.commit()
    finally:
        conn.close()

def update_challenge(challenge_id, slug, is_final,
                     answer_1, answer_name, answer_city,
                     hint_1, hint_name, hint_city,
                     hint_threshold, order):
    conn = get_db()
    try:
        conn.execute("""UPDATE challenges SET
            slug=?,is_final=?,answer_1=?,answer_name=?,answer_city=?,
            hint_1=?,hint_name=?,hint_city=?,hint_threshold=?,ord=?
            WHERE id=?""",
            (slug, 1 if is_final else 0,
             answer_1, answer_name, answer_city,
             hint_1, hint_name, hint_city, hint_threshold, order,
             challenge_id))
        conn.commit()
    finally:
        conn.close()

def delete_challenge(challenge_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM user_progress WHERE challenge_id=?", (challenge_id,))
        conn.execute("DELETE FROM challenges    WHERE id=?",           (challenge_id,))
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


# ── progress ───────────────────────────────────────────────────────────────────

def get_solved_challenge_ids(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT challenge_id FROM user_progress WHERE user_id=? AND challenge_id IS NOT NULL",
            (user_id,)).fetchall()
        return {r["challenge_id"] for r in rows}
    finally:
        conn.close()

def get_completed_stone_ids(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT stone_id FROM user_progress WHERE user_id=? AND stone_completed=1",
            (user_id,)).fetchall()
        return {r["stone_id"] for r in rows}
    finally:
        conn.close()

def mark_challenge_solved(user_id, stone_id, challenge_id):
    conn = get_db()
    try:
        if not conn.execute(
                "SELECT 1 FROM user_progress WHERE user_id=? AND challenge_id=?",
                (user_id, challenge_id)).fetchone():
            conn.execute(
                "INSERT INTO user_progress (user_id,stone_id,challenge_id) VALUES (?,?,?)",
                (user_id, stone_id, challenge_id))
            conn.commit()
    finally:
        conn.close()

def mark_stone_completed(user_id, stone_id):
    conn = get_db()
    try:
        if not conn.execute(
                "SELECT 1 FROM user_progress WHERE user_id=? AND stone_id=? AND stone_completed=1",
                (user_id, stone_id)).fetchone():
            conn.execute(
                "INSERT INTO user_progress (user_id,stone_id,stone_completed) VALUES (?,?,1)",
                (user_id, stone_id))
            conn.commit()
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

    # Rij 0 — 4 stenen, geen afhankelijkheden
    create_stone("S1", "CIPHER-1", 0, 0, "")
    create_stone("S2", "CIPHER-2", 0, 1, "")
    create_stone("S3", "CIPHER-3", 0, 2, "")
    create_stone("S4", "CIPHER-4", 0, 3, "")
    # Rij 1
    create_stone("S5", "LEVEL-2A", 1, 0, "S1,S2")
    create_stone("S6", "LEVEL-2B", 1, 1, "S2,S3")
    create_stone("S7", "LEVEL-2C", 1, 2, "S3,S4")
    # Rij 2
    create_stone("S8",  "LEVEL-3A", 2, 0, "S5,S6")
    create_stone("S9",  "LEVEL-3B", 2, 1, "S6,S7")
    # Top
    create_stone("S10", "MASTER",   3, 0, "S8,S9")

    # S1: 2 sublevels — eerste normaal, laatste is_final (name+city)
    create_challenge(1,"s1_c1",False,
                     "HELLO WORLD","","",
                     "Denk aan ROT13","","",0.6,0)
    create_challenge(1,"s1_c2",True,
                     "","Alan Turing","London",
                     "","Vader van de informatica","Hoofdstad VK",0.6,1)

    # S2: 1 sublevel, is_final
    create_challenge(2,"s2_c1",True,
                     "","Grace Hopper","New York",
                     "","Admiraal & programmeur","Grootste stad VS",0.6,0)

    # S3: 1 sublevel, normaal
    create_challenge(3,"s3_c1",False,
                     "CRYPTO","","",
                     "Denk aan Atbash","","",0.6,0)

    # S4: 1 sublevel, is_final
    create_challenge(4,"s4_c1",True,
                     "","Claude Shannon","Gaylord",
                     "","Informatietheorie","Michigan, VS",0.6,0)

    if not get_user_by_username("admin"):
        create_user("admin", generate_password_hash("admin123"), is_admin=True)
