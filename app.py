"""
app.py — Konundrum Flask app

Veiligheid:
  - Antwoorden zitten ALLEEN in de database
  - Templates krijgen nooit antwoord/hint-velden te zien
  - /api/check controleert server-side en stuurt enkel result + feedback terug
  - Challenge HTML-bestanden worden server-side geladen en als Jinja-string gerenderd
    (geen directe file-path exposure naar de browser)
"""
from flask import (Flask, render_template, render_template_string,
                   request, redirect, url_for, session, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from difflib import SequenceMatcher
from functools import wraps
from markupsafe import Markup
import os, re
import database as db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "verander-dit-voor-productie")

CHALLENGES_DIR = os.path.join(os.path.dirname(__file__), "challenges")


# ── decorators ─────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return inner

def admin_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("pyramid"))
        return f(*args, **kwargs)
    return inner


# ── helpers ────────────────────────────────────────────────────────────────────

def sim(a, b):
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def check_field(user_val, correct_val, threshold, hint_text):
    """Returns dict with status ('correct'|'hint'|'wrong') and msg."""
    if not user_val:
        return {"status": "empty", "msg": ""}
    if user_val.lower().strip() == correct_val.lower().strip():
        return {"status": "correct", "msg": "✓ Correct!"}
    if threshold > 0 and sim(user_val, correct_val) >= threshold:
        tip = hint_text if hint_text else "Je zit op het goede spoor."
        return {"status": "hint", "msg": f"Bijna! {tip}"}
    return {"status": "wrong", "msg": "✗ Niet correct."}

def get_unlocked_ids(user_id):
    completed = db.get_completed_stone_ids(user_id)
    unlocked  = set()
    for stone in db.get_all_stones():
        deps = [d.strip() for d in (stone["dependencies"] or "").split(",") if d.strip()]
        dep_ids = set()
        for dep_name in deps:
            s = db.get_stone_by_name(dep_name)
            if s:
                dep_ids.add(s["id"])
        if dep_ids.issubset(completed):
            unlocked.add(stone["id"])
    return unlocked

def stone_status(stone_id, challenges, solved, completed, unlocked):
    if stone_id not in unlocked:
        return "locked"
    if stone_id in completed:
        return "complete"
    done = sum(1 for c in challenges if c["id"] in solved)
    return "partial" if done > 0 else "available"

def load_challenge_html(slug):
    """
    Laad het challenge HTML-bestand server-side.
    De slug wordt gevalideerd zodat path traversal onmogelijk is.
    """
    if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
        return "<p style='color:red'>Ongeldige slug.</p>"
    path = os.path.join(CHALLENGES_DIR, f"{slug}.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return f"""<div class="ch-placeholder">
  ⚠ Vraagbestand ontbreekt: <code>challenges/{slug}.html</code><br>
  Maak dit bestand aan en voeg de vraag/afbeelding/script toe.
</div>"""

def ensure_challenge_file(slug):
    """Maak een starter-bestand als het nog niet bestaat."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
        return
    path = os.path.join(CHALLENGES_DIR, f"{slug}.html")
    os.makedirs(CHALLENGES_DIR, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(STARTER_TEMPLATE.replace("{{slug}}", slug))

STARTER_TEMPLATE = """\
<!--
  Konundrum challenge: {{slug}}
  =====================================================
  Bewerk dit bestand vrij. Je kunt hier zetten:
    - Tekst / HTML
    - Een afbeelding: <img src="/static/images/mijn-foto.jpg" ...>
    - Inline JavaScript (zie voorbeeld hieronder)

  De antwoordboxen worden automatisch onder deze inhoud geplaatst.
  Zet hier NOOIT antwoorden — die staan veilig in de database.
  =====================================================
-->

<p>Schrijf hier jouw vraag of omschrijving...</p>

<!--
VOORBEELD MET AFBEELDING:
<figure>
  <img src="/static/images/aanwijzing.jpg"
       alt="aanwijzing"
       style="max-width:100%;border-radius:6px;margin:1rem 0;">
  <figcaption style="font-size:12px;color:var(--text-dim);">
    Afbeelding: omschrijving
  </figcaption>
</figure>

VOORBEELD MET JAVASCRIPT-ANIMATIE:
<canvas id="cvs-{{slug}}" width="420" height="140"
  style="background:#050810;border:1px solid var(--border);
         border-radius:4px;display:block;margin:1rem 0;max-width:100%;">
</canvas>
<script>
(function() {
  const c = document.getElementById('cvs-{{slug}}');
  if (!c) return;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#00ff88';
  ctx.font = 'bold 18px monospace';
  ctx.fillText('Jouw aanwijzing hier...', 20, 50);
  ctx.fillStyle = '#00b4ff';
  ctx.font = '14px monospace';
  ctx.fillText('Voeg meer aanwijzingen toe...', 20, 90);
})();
</script>
-->
"""

# ── pyramid helpers ────────────────────────────────────────────────────────────

def build_pyramid_rows(user_id):
    """
    Bouw piramide-rijen op basis van alle stenen in de database.
    Nieuwe stenen (row/col) worden automatisch opgenomen.
    """
    solved    = db.get_solved_challenge_ids(user_id)
    completed = db.get_completed_stone_ids(user_id)
    unlocked  = get_unlocked_ids(user_id)

    rows = {}
    for stone in db.get_all_stones():
        challenges = db.get_challenges_safe(stone["id"])
        done     = sum(1 for c in challenges if c["id"] in solved)
        total_ch = len(challenges)
        status   = stone_status(stone["id"], challenges, solved, completed, unlocked)
        r = stone["row"]
        rows.setdefault(r, []).append({
            "stone":  stone,
            "status": status,
            "done":   done,
            "total":  total_ch,
            "pct":    int(done / total_ch * 100) if total_ch else 0,
        })
    return sorted(rows.items())


# ── auth ───────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("pyramid") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session.update(user_id=user["id"], username=user["username"],
                           is_admin=bool(user["is_admin"]))
            return redirect(url_for("pyramid"))
        error = "Verkeerde gebruikersnaam of wachtwoord."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            error = "Vul alle velden in."
        elif len(password) < 4:
            error = "Wachtwoord moet minstens 4 tekens zijn."
        elif db.get_user_by_username(username):
            error = "Gebruikersnaam al in gebruik."
        else:
            user = db.create_user(username, generate_password_hash(password))
            session.update(user_id=user["id"], username=user["username"], is_admin=False)
            return redirect(url_for("pyramid"))
    return render_template("register.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── game ───────────────────────────────────────────────────────────────────────

@app.route("/pyramid")
@login_required
def pyramid():
    rows  = build_pyramid_rows(session["user_id"])
    score = len(db.get_solved_challenge_ids(session["user_id"]))
    total = db.count_all_challenges()
    return render_template("pyramid.html", rows=rows, score=score, total=total)


@app.route("/stone/<int:stone_id>")
@login_required
def stone_view(stone_id):
    user_id = session["user_id"]
    s = db.get_stone(stone_id)
    if not s:
        abort(404)
    if stone_id not in get_unlocked_ids(user_id):
        return redirect(url_for("pyramid"))

    challenges  = db.get_challenges_safe(stone_id)   # geen antwoorden!
    solved      = db.get_solved_challenge_ids(user_id)
    stone_done  = stone_id in db.get_completed_stone_ids(user_id)

    # Laad HTML-snippets server-side — slug gevalideerd in load_challenge_html()
    challenge_html = {c["id"]: Markup(load_challenge_html(c["slug"])) for c in challenges}

    return render_template("stone.html",
                           stone=s,
                           challenges=challenges,
                           solved=solved,
                           stone_done=stone_done,
                           challenge_html=challenge_html)


@app.route("/api/check", methods=["POST"])
@login_required
def api_check():
    """
    Antwoord-check — volledig server-side.
    Input:  { challenge_id, answer_1 }  of  { challenge_id, answer_name, answer_city }
    Output: { result, fields: {…}, stone_completed }
    Antwoorden worden NOOIT in de response meegestuurd.
    """
    data         = request.get_json(force=True)
    challenge_id = data.get("challenge_id")
    user_id      = session["user_id"]

    ch = db.get_challenge_full(challenge_id)   # server-side only
    if not ch:
        return jsonify(result="error", msg="Onbekende challenge."), 400

    if ch["stone_id"] not in get_unlocked_ids(user_id):
        return jsonify(result="error", msg="Steen niet ontgrendeld."), 403

    thr = ch["hint_threshold"]

    if ch["is_final"]:
        # Two-field check
        f_name = check_field(data.get("answer_name",""), ch["answer_name"], thr, ch["hint_name"])
        f_city = check_field(data.get("answer_city",""), ch["answer_city"], thr, ch["hint_city"])
        all_correct = (f_name["status"] == "correct" and f_city["status"] == "correct")
        fields = {"answer_name": f_name, "answer_city": f_city}
    else:
        # Single-field check
        f1 = check_field(data.get("answer_1",""), ch["answer_1"], thr, ch["hint_1"])
        all_correct = (f1["status"] == "correct")
        fields = {"answer_1": f1}

    stone_completed = False
    if all_correct:
        db.mark_challenge_solved(user_id, ch["stone_id"], challenge_id)
        challenges = db.get_challenges_safe(ch["stone_id"])
        solved     = db.get_solved_challenge_ids(user_id)
        if all(c["id"] in solved for c in challenges):
            db.mark_stone_completed(user_id, ch["stone_id"])
            stone_completed = True

    return jsonify(
        result="correct" if all_correct else "wrong",
        fields=fields,
        stone_completed=stone_completed
    )


# ── admin ──────────────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin():
    stones = db.get_all_stones()
    # Admin mag volledige challenge-info zien (incl. antwoorden)
    stone_data = []
    for s in stones:
        conn = db.get_db()
        chs = conn.execute("SELECT * FROM challenges WHERE stone_id=? ORDER BY ord",
                           (s["id"],)).fetchall()
        conn.close()
        stone_data.append({"stone": s, "challenges": chs})
    return render_template("admin.html", stone_data=stone_data)


@app.route("/admin/stone/add", methods=["GET", "POST"])
@admin_required
def admin_add_stone():
    all_stones = db.get_all_stones()
    error = None
    if request.method == "POST":
        name  = request.form.get("name","").strip()
        label = request.form.get("label","").strip()
        row   = request.form.get("row",  type=int)
        col   = request.form.get("col",  type=int)
        deps  = request.form.get("dependencies","").strip()
        if not name or row is None or col is None:
            error = "Naam, rij en kolom zijn verplicht."
        elif db.get_stone_by_name(name):
            error = f"Naam '{name}' al in gebruik."
        else:
            new = db.create_stone(name, label, row, col, deps)
            return redirect(url_for("admin_stone_challenges", stone_id=new["id"]))
    return render_template("admin_stone_form.html",
                           stone=None, all_stones=all_stones, error=error)


@app.route("/admin/stone/<int:stone_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_stone(stone_id):
    s = db.get_stone(stone_id)
    if not s: abort(404)
    all_stones = [x for x in db.get_all_stones() if x["id"] != stone_id]
    error = None
    if request.method == "POST":
        db.update_stone(stone_id,
                        request.form.get("name","").strip(),
                        request.form.get("label","").strip(),
                        request.form.get("row",  type=int),
                        request.form.get("col",  type=int),
                        request.form.get("dependencies","").strip())
        return redirect(url_for("admin"))
    return render_template("admin_stone_form.html",
                           stone=s, all_stones=all_stones, error=error)


@app.route("/admin/stone/<int:stone_id>/delete", methods=["POST"])
@admin_required
def admin_delete_stone(stone_id):
    db.delete_stone(stone_id)
    return redirect(url_for("admin"))


@app.route("/admin/stone/<int:stone_id>/challenges")
@admin_required
def admin_stone_challenges(stone_id):
    s = db.get_stone(stone_id)
    if not s: abort(404)
    conn = db.get_db()
    chs = conn.execute("SELECT * FROM challenges WHERE stone_id=? ORDER BY ord",
                       (stone_id,)).fetchall()
    conn.close()
    return render_template("admin_challenges.html", stone=s, challenges=chs)


@app.route("/admin/challenge/add/<int:stone_id>", methods=["GET", "POST"])
@admin_required
def admin_add_challenge(stone_id):
    s = db.get_stone(stone_id)
    if not s: abort(404)
    error = None
    if request.method == "POST":
        slug      = re.sub(r'[^a-zA-Z0-9_-]', '_', request.form.get("slug","").strip())
        is_final  = bool(request.form.get("is_final"))
        answer_1  = request.form.get("answer_1","").strip()
        ans_name  = request.form.get("answer_name","").strip()
        ans_city  = request.form.get("answer_city","").strip()
        hint_1    = request.form.get("hint_1","").strip()
        hint_name = request.form.get("hint_name","").strip()
        hint_city = request.form.get("hint_city","").strip()
        threshold = request.form.get("hint_threshold", 0.6, type=float)
        order     = request.form.get("order", 0, type=int)

        if not slug:
            error = "Slug is verplicht."
        elif db.slug_exists(slug):
            error = f"Slug '{slug}' al in gebruik."
        elif is_final and (not ans_name or not ans_city):
            error = "Naam en stad zijn verplicht voor een finaal sublevel."
        elif not is_final and not answer_1:
            error = "Antwoord is verplicht."
        else:
            db.create_challenge(stone_id, slug, is_final,
                                answer_1, ans_name, ans_city,
                                hint_1, hint_name, hint_city,
                                threshold, order)
            ensure_challenge_file(slug)
            return redirect(url_for("admin_stone_challenges", stone_id=stone_id))

    next_order = db.count_challenges_for_stone(stone_id)
    return render_template("admin_challenge_form.html",
                           stone=s, challenge=None, next_order=next_order, error=error)


@app.route("/admin/challenge/<int:challenge_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_challenge(challenge_id):
    ch = db.get_challenge_full(challenge_id)
    if not ch: abort(404)
    s = db.get_stone(ch["stone_id"])
    error = None
    if request.method == "POST":
        slug      = re.sub(r'[^a-zA-Z0-9_-]', '_', request.form.get("slug","").strip())
        is_final  = bool(request.form.get("is_final"))
        answer_1  = request.form.get("answer_1","").strip()
        ans_name  = request.form.get("answer_name","").strip()
        ans_city  = request.form.get("answer_city","").strip()
        hint_1    = request.form.get("hint_1","").strip()
        hint_name = request.form.get("hint_name","").strip()
        hint_city = request.form.get("hint_city","").strip()
        threshold = request.form.get("hint_threshold", 0.6, type=float)
        order     = request.form.get("order", 0, type=int)

        if not slug:
            error = "Slug is verplicht."
        elif db.slug_exists(slug, exclude_id=challenge_id):
            error = f"Slug '{slug}' al in gebruik."
        elif is_final and (not ans_name or not ans_city):
            error = "Naam en stad zijn verplicht voor een finaal sublevel."
        elif not is_final and not answer_1:
            error = "Antwoord is verplicht."
        else:
            db.update_challenge(challenge_id, slug, is_final,
                                answer_1, ans_name, ans_city,
                                hint_1, hint_name, hint_city,
                                threshold, order)
            ensure_challenge_file(slug)
            return redirect(url_for("admin_stone_challenges", stone_id=s["id"]))

    return render_template("admin_challenge_form.html",
                           stone=s, challenge=ch, next_order=ch["ord"], error=error)


@app.route("/admin/challenge/<int:challenge_id>/delete", methods=["POST"])
@admin_required
def admin_delete_challenge(challenge_id):
    ch = db.get_challenge_full(challenge_id)
    if not ch: abort(404)
    stone_id = ch["stone_id"]
    db.delete_challenge(challenge_id)
    return redirect(url_for("admin_stone_challenges", stone_id=stone_id))


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    db.seed_demo_data()
    for slug in db.get_all_slugs():
        ensure_challenge_file(slug)
    app.run(debug=True)
