"""
app.py — Konundrum
Features: 404 page, admin overview, about page, password reset, trigger hints, user country/profile
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from markupsafe import Markup
import os, re
import database as db

app = Flask(__name__)
# In production, set SECRET_KEY as an environment variable. The fallback is only
# meant for local development — never rely on it on a public server.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

CHALLENGES_DIR = os.path.join(os.path.dirname(__file__), "challenges")
HOME_CONTENT   = os.path.join(os.path.dirname(__file__), "templates", "home_content.html")
ABOUT_CONTENT  = os.path.join(os.path.dirname(__file__), "templates", "about_content.html")

# ── countries (dropdown for user preferences) ──────────────────────────────────

COUNTRIES = [
    "België", "Nederland", "Luxemburg", "Frankrijk", "Duitsland",
    "Verenigd Koninkrijk", "Ierland", "Spanje", "Portugal", "Italië",
    "Zwitserland", "Oostenrijk", "Denemarken", "Zweden", "Noorwegen",
    "Finland", "Polen", "Tsjechië", "Griekenland", "Verenigde Staten",
    "Canada", "Australië", "Nieuw-Zeeland", "Japan", "Anders",
]


# ── campaigns (pyramids) ───────────────────────────────────────────────────────
# Each campaign is one pyramid. "greeks" is the first/only one for now.
# Add a new entry here when you add a follow-up pyramid, and tag its stones with
# that campaign key (stones.campaign). "unlock_after" lets a campaign stay hidden
# until the previous pyramid is fully solved, so later it can appear in a dropdown.

CAMPAIGNS = {
    "greeks": {"label": "Greeks", "unlock_after": None},
    # Example for later:
    # "romans": {"label": "Romans", "unlock_after": "greeks"},
}
DEFAULT_CAMPAIGN = "greeks"


def campaign_is_complete(user_id, campaign):
    """True when the user has completed every stone in a campaign."""
    stones = db.get_stones_by_campaign(campaign)
    if not stones:
        return False
    completed = db.get_completed_stone_ids(user_id)
    return all(s["id"] in completed for s in stones)


def user_campaigns(user_id):
    """Campaigns the user may enter. Always includes the default; follow-ups
    unlock once their prerequisite campaign is fully solved. Returns a list of
    dicts: {key, label, unlocked}."""
    result = []
    for key, meta in CAMPAIGNS.items():
        prereq = meta.get("unlock_after")
        unlocked = True if not prereq else campaign_is_complete(user_id, prereq)
        result.append({"key": key, "label": meta["label"], "unlocked": unlocked})
    return result


# ── mail (optional, password reset only) ───────────────────────────────────────
# Set MAIL_SERVER etc. as environment variables for real email.
# If MAIL_SERVER is not configured, the reset link is logged to console.

def send_reset_email(email, username, token):
    reset_url = f"{request.host_url.rstrip('/')}{url_for('reset_password', token=token)}"
    try:
        import smtplib
        from email.mime.text import MIMEText
        server   = os.environ.get("MAIL_SERVER")
        port     = int(os.environ.get("MAIL_PORT", 587))
        user     = os.environ.get("MAIL_USER", "")
        password = os.environ.get("MAIL_PASSWORD", "")
        sender   = os.environ.get("MAIL_FROM", user)
        if not server:
            raise ValueError("no mail server")
        msg = MIMEText(
            f"Hello {username},\n\n"
            f"You requested a password reset.\n"
            f"Use this link (valid for 1 hour):\n{reset_url}\n\n"
            f"If you didn't request this, please ignore this message.\n\nKonundrum",
            "plain", "utf-8")
        msg["Subject"] = "Reset your password — Konundrum"
        msg["From"]    = sender
        msg["To"]      = email
        with smtplib.SMTP(server, port) as s:
            s.starttls()
            if user:
                s.login(user, password)
            s.sendmail(sender, [email], msg.as_string())
        return True
    except Exception as e:
        print(f"[MAIL] Could not send reset email ({e}). Reset link: {reset_url}")
        return False


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
            return redirect(url_for("greeks"))
        return f(*args, **kwargs)
    return inner


# ── helpers ────────────────────────────────────────────────────────────────────

def check_field(user_val, correct_val, challenge_id, field):
    """Check answer: correct, trigger-hint, or wrong."""
    if not user_val:
        return {"status": "empty", "msg": ""}
    if user_val.lower().strip() == correct_val.lower().strip():
        return {"status": "correct", "msg": "✓ Correct!"}
    # Look for a trigger-hint for this specific answer
    hint = db.get_hint_for_answer(challenge_id, field, user_val)
    if hint:
        return {"status": "hint", "msg": f"💡 {hint}"}
    return {"status": "wrong", "msg": "✗ Incorrect."}

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
    if stone_id not in unlocked:   return "locked"
    if stone_id in completed:      return "complete"
    done = sum(1 for c in challenges if c["id"] in solved)
    return "partial" if done > 0 else "available"

def load_challenge_html(slug):
    if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
        return "<p style='color:red'>Ongeldige slug.</p>"
    path = os.path.join(CHALLENGES_DIR, f"{slug}.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return f'<div class="ch-placeholder">⚠ Vraagbestand ontbreekt: <code>challenges/{slug}.html</code></div>'

def ensure_challenge_file(slug):
    if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
        return
    path = os.path.join(CHALLENGES_DIR, f"{slug}.html")
    os.makedirs(CHALLENGES_DIR, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(STARTER_TEMPLATE.replace("SLUG_PLACEHOLDER", slug))

STARTER_TEMPLATE = """\
<!--
  Konundrum challenge: SLUG_PLACEHOLDER
  Edit freely: text, images, JavaScript.
  Answers are NEVER stored in this file.
-->
<p>Write the question for this sublevel here...</p>

<!--
IMAGE:
<img src="/static/images/clue.jpg" style="max-width:100%;border-radius:6px;margin:.5rem 0;">

JAVASCRIPT / CANVAS:
<canvas id="cvs-SLUG_PLACEHOLDER" width="420" height="120"
  style="background:#050810;border:1px solid var(--border);border-radius:4px;display:block;margin:1rem 0;max-width:100%;">
</canvas>
<script>
(function(){
  const c=document.getElementById('cvs-SLUG_PLACEHOLDER');
  if(!c)return;
  const ctx=c.getContext('2d');
  ctx.fillStyle='#00ff88';ctx.font='bold 16px monospace';
  ctx.fillText('Your clue here...',20,60);
})();
</script>
-->
"""

def build_board_rows(user_id, campaign=DEFAULT_CAMPAIGN):
    solved    = db.get_solved_challenge_ids(user_id)
    completed = db.get_completed_stone_ids(user_id)
    unlocked  = get_unlocked_ids(user_id)
    rows = {}
    for stone in db.get_stones_by_campaign(campaign):
        challenges = db.get_challenges_safe(stone["id"])
        done     = sum(1 for c in challenges if c["id"] in solved)
        total_ch = len(challenges)
        status   = stone_status(stone["id"], challenges, solved, completed, unlocked)
        rows.setdefault(stone["row"], []).append({
            "stone": stone, "status": status,
            "done": done, "total": total_ch,
            "pct": int(done / total_ch * 100) if total_ch else 0,
        })
    return sorted(rows.items())

def is_final_unlocked(stone_id, user_id, final_challenge_id):
    challenges = db.get_challenges_safe(stone_id)
    solved     = db.get_solved_challenge_ids(user_id)
    non_finals = [c for c in challenges if not c["is_final"] and c["id"] != final_challenge_id]
    return all(c["id"] in solved for c in non_finals)

def load_file_content(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


# ── error handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template("404.html", code=403, msg="Geen toegang."), 403

@app.errorhandler(500)
def server_error(e):
    return render_template("404.html", code=500, msg="Interne fout."), 500


# ── auth ───────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("home") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session.update(user_id=user["id"], username=user["username"],
                           is_admin=bool(user["is_admin"]))
            return redirect(url_for("home"))
        else:
            error = "Incorrect username or password."
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email    = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        country  = request.form.get("country","").strip()
        if country not in COUNTRIES:
            country = ""
        if not username or not email or not password:
            error = "Please fill in all fields."
        elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            error = "Invalid email address."
        elif len(password) < 4:
            error = "Password must be at least 4 characters."
        elif db.get_user_by_username(username):
            error = "Username already taken."
        elif db.get_user_by_email(email):
            error = "Email address already in use."
        else:
            user = db.create_user(username, email, generate_password_hash(password),
                                  country=country)
            # log in directly — no email confirmation needed
            session.update(user_id=user["id"], username=user["username"], is_admin=False)
            return redirect(url_for("home"))
    return render_template("register.html", error=error, countries=COUNTRIES)

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    msg = None
    error = None
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        if not email:
            error = "Please enter your email address."
        else:
            user = db.get_user_by_email(email)
            if user:
                token = db.create_password_reset(user["id"])
                send_reset_email(email, user["username"], token)
            # Always show success (prevents email enumeration)
            msg = "If this email address is registered with us, you'll receive a reset link."
    return render_template("forgot_password.html", msg=msg, error=error)

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    reset = db.get_valid_reset_token(token)
    if not reset:
        return render_template("404.html", code=400,
                               msg="Invalid or expired reset link. Please request a new one."), 400
    error = None
    if request.method == "POST":
        password  = request.form.get("password","")
        password2 = request.form.get("password2","")
        if len(password) < 4:
            error = "Password must be at least 4 characters."
        elif password != password2:
            error = "Passwords do not match."
        else:
            db.update_user_password(reset["user_id"], generate_password_hash(password))
            db.use_reset_token(token)
            return redirect(url_for("login"))
    return render_template("reset_password.html", token=token, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── public pages ───────────────────────────────────────────────────────────────

@app.route("/home")
@login_required
def home():
    raw = load_file_content(HOME_CONTENT)
    # Replace the {{USERNAME}} placeholder with the current user's (escaped) name.
    from markupsafe import escape
    raw = raw.replace("{{USERNAME}}", str(escape(session.get("username", ""))))
    content = Markup(raw)
    score   = db.get_user_total_points(session["user_id"])
    total   = db.total_possible_points()
    return render_template("home.html", content=content, score=score, total=total)

@app.route("/about")
def about():
    content = Markup(load_file_content(ABOUT_CONTENT))
    return render_template("about.html", content=content)

@app.route("/greeks")
@login_required
def greeks():
    # The Greeks pyramid — the default campaign.
    return _render_board("greeks")

@app.route("/board/<campaign>")
@login_required
def board(campaign):
    # Generic campaign view, ready for future follow-up pyramids.
    if campaign not in CAMPAIGNS:
        abort(404)
    # Enforce unlock rules for follow-up campaigns.
    for c in user_campaigns(session["user_id"]):
        if c["key"] == campaign and not c["unlocked"]:
            return redirect(url_for("greeks"))
    if campaign == DEFAULT_CAMPAIGN:
        return redirect(url_for("greeks"))
    return _render_board(campaign)

def _render_board(campaign):
    user_id = session["user_id"]
    rows    = build_board_rows(user_id, campaign)
    score   = db.get_user_total_points(user_id)
    total   = db.total_possible_points()
    return render_template("greeks.html", rows=rows, score=score, total=total,
                           campaign=campaign,
                           campaign_label=CAMPAIGNS[campaign]["label"],
                           campaigns=user_campaigns(user_id))

@app.route("/stone/<int:stone_id>")
@login_required
def stone_view(stone_id):
    user_id = session["user_id"]
    s = db.get_stone(stone_id)
    if not s: abort(404)
    if stone_id not in get_unlocked_ids(user_id):
        return redirect(url_for("greeks"))
    challenges = db.get_challenges_safe(stone_id)
    solved     = db.get_solved_challenge_ids(user_id)
    completed  = db.get_completed_stone_ids(user_id)
    stone_done = stone_id in completed
    ch_meta = {}
    for c in challenges:
        final_locked = c["is_final"] and not is_final_unlocked(stone_id, user_id, c["id"])
        ch_meta[c["id"]] = {
            "attempts":    db.get_attempt_count(user_id, c["id"]),
            "final_locked": final_locked,
        }
    return render_template("stone.html", stone=s, challenges=challenges,
                           solved=solved, stone_done=stone_done, ch_meta=ch_meta)

@app.route("/challenge/<slug>")
@login_required
def challenge_view(slug):
    user_id = session["user_id"]
    ch = db.get_challenge_by_slug(slug)
    if not ch: abort(404)
    stone = db.get_stone(ch["stone_id"])
    if not stone or ch["stone_id"] not in get_unlocked_ids(user_id):
        return redirect(url_for("greeks"))
    solved      = db.get_solved_challenge_ids(user_id)
    is_solved   = ch["id"] in solved
    attempts    = db.get_attempt_count(user_id, ch["id"])
    final_locked = ch["is_final"] and not is_final_unlocked(ch["stone_id"], user_id, ch["id"])
    content     = Markup(load_challenge_html(slug))
    all_ch = db.get_challenges_safe(ch["stone_id"])
    idx    = next((i for i, c in enumerate(all_ch) if c["id"] == ch["id"]), 0)
    prev_ch = all_ch[idx - 1] if idx > 0 else None
    next_ch = all_ch[idx + 1] if idx < len(all_ch) - 1 else None
    return render_template("challenge.html", stone=stone, challenge=ch,
                           content=content, is_solved=is_solved, attempts=attempts,
                           final_locked=final_locked, prev_ch=prev_ch, next_ch=next_ch)

@app.route("/hall-of-fame")
@login_required
def hall_of_fame():
    ranking     = db.get_hall_of_fame()
    total_ch    = db.count_all_challenges()
    total_stones= len(db.get_all_stones())
    total_pts   = db.total_possible_points()
    return render_template("hall_of_fame.html", ranking=ranking,
                           total_ch=total_ch, total_stones=total_stones, total_pts=total_pts)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    saved = False          # country saved
    pw_msg = None          # password change success
    pw_error = None        # password change error
    if request.method == "POST":
        action = request.form.get("action", "country")
        if action == "password":
            current  = request.form.get("current_password", "")
            new1     = request.form.get("new_password", "")
            new2     = request.form.get("new_password2", "")
            user     = db.get_user_by_id(session["user_id"])
            if not user or not check_password_hash(user["password_hash"], current):
                pw_error = "Current password is incorrect."
            elif len(new1) < 4:
                pw_error = "New password must be at least 4 characters."
            elif new1 != new2:
                pw_error = "New passwords do not match."
            else:
                db.update_user_password(user["id"], generate_password_hash(new1))
                pw_msg = "Password updated."
        else:
            country = request.form.get("country", "").strip()
            if country in COUNTRIES or country == "":
                db.update_user_country(session["user_id"], country)
                saved = True
    stats    = db.get_user_stats(session["user_id"])
    total_ch = db.count_all_challenges()
    total_pts= db.total_possible_points()
    total_st = len(db.get_all_stones())
    return render_template("profile.html", stats=stats, countries=COUNTRIES, saved=saved,
                           pw_msg=pw_msg, pw_error=pw_error,
                           total_ch=total_ch, total_pts=total_pts, total_st=total_st)


# ── api ────────────────────────────────────────────────────────────────────────

@app.route("/api/check", methods=["POST"])
@login_required
def api_check():
    data         = request.get_json(force=True)
    challenge_id = data.get("challenge_id")
    user_id      = session["user_id"]
    ch = db.get_challenge_full(challenge_id)
    if not ch:
        return jsonify(result="error", msg="Unknown challenge."), 400
    if ch["stone_id"] not in get_unlocked_ids(user_id):
        return jsonify(result="error", msg="Stone not unlocked."), 403
    if ch["is_final"] and not is_final_unlocked(ch["stone_id"], user_id, challenge_id):
        return jsonify(result="locked", msg="Solve all other sublevels first."), 403
    if challenge_id in db.get_solved_challenge_ids(user_id):
        return jsonify(result="already_solved", msg="Already solved!", fields={}, stone_completed=False)
    db.record_attempt(user_id, ch["stone_id"], challenge_id)

    def _log(field, value, field_result):
        # Record every non-empty submission so you can analyse answers later.
        if value and value.strip():
            db.log_answer(user_id, challenge_id, ch["stone_id"], field,
                          value.strip(), field_result["status"] == "correct")

    if ch["is_final"]:
        f_name = check_field(data.get("answer_name",""), ch["answer_name"], challenge_id, "answer_name")
        f_city = check_field(data.get("answer_city",""), ch["answer_city"], challenge_id, "answer_city")
        _log("answer_name", data.get("answer_name",""), f_name)
        _log("answer_city", data.get("answer_city",""), f_city)
        all_correct = (f_name["status"] == "correct" and f_city["status"] == "correct")
        fields = {"answer_name": f_name, "answer_city": f_city}
    else:
        f1 = check_field(data.get("answer_1",""), ch["answer_1"], challenge_id, "answer_1")
        _log("answer_1", data.get("answer_1",""), f1)
        all_correct = (f1["status"] == "correct")
        fields = {"answer_1": f1}
    stone_completed = False
    if all_correct:
        db.mark_challenge_solved(user_id, ch["stone_id"], challenge_id, ch["points"])
        challenges = db.get_challenges_safe(ch["stone_id"])
        solved     = db.get_solved_challenge_ids(user_id)
        if all(c["id"] in solved for c in challenges):
            db.mark_stone_completed(user_id, ch["stone_id"])
            stone_completed = True
    return jsonify(result="correct" if all_correct else "wrong", fields=fields,
                   stone_completed=stone_completed,
                   attempts=db.get_attempt_count(user_id, challenge_id),
                   points=ch["points"] if all_correct else 0)


# ── admin ──────────────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin():
    stones = db.get_all_stones()
    stone_data = []
    for s in stones:
        conn = db.get_db()
        chs = conn.execute("SELECT * FROM challenges WHERE stone_id=? ORDER BY ord", (s["id"],)).fetchall()
        conn.close()
        stone_data.append({"stone": s, "challenges": chs})
    return render_template("admin.html", stone_data=stone_data)

@app.route("/admin/overview")
@admin_required
def admin_overview():
    stats = db.get_admin_stats()
    return render_template("admin_overview.html", stats=stats)

@app.route("/admin/answers")
@admin_required
def admin_answers():
    # Full log of who answered what, across all puzzles.
    log   = db.get_answer_log(limit=1000)
    total = db.count_answer_log()
    return render_template("admin_answers.html", log=log, total=total,
                           challenge=None, stone=None)

@app.route("/admin/challenge/<int:challenge_id>/answers")
@admin_required
def admin_challenge_answers(challenge_id):
    ch = db.get_challenge_full(challenge_id)
    if not ch: abort(404)
    s   = db.get_stone(ch["stone_id"])
    log = db.get_answer_log_for_challenge(challenge_id, limit=500)
    return render_template("admin_answers.html", log=log, total=len(log),
                           challenge=ch, stone=s)

@app.route("/admin/home", methods=["GET","POST"])
@admin_required
def admin_home_content():
    msg = None
    content = load_file_content(HOME_CONTENT)
    if request.method == "POST":
        new_content = request.form.get("content","")
        with open(HOME_CONTENT, "w", encoding="utf-8") as f:
            f.write(new_content)
        msg = "Homepage saved."
        content = new_content
    return render_template("admin_home.html", content=content, msg=msg, page="home")

@app.route("/admin/about", methods=["GET","POST"])
@admin_required
def admin_about_content():
    msg = None
    content = load_file_content(ABOUT_CONTENT)
    if request.method == "POST":
        new_content = request.form.get("content","")
        with open(ABOUT_CONTENT, "w", encoding="utf-8") as f:
            f.write(new_content)
        msg = "About page saved."
        content = new_content
    return render_template("admin_home.html", content=content, msg=msg, page="about")

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
        home  = request.form.get("home_content","").strip()
        camp  = request.form.get("campaign","").strip() or DEFAULT_CAMPAIGN
        if not name or row is None or col is None:
            error = "Name, row, and column are required."
        elif db.get_stone_by_name(name):
            error = f"Name '{name}' already in use."
        else:
            new = db.create_stone(name, label, row, col, deps, home, camp)
            return redirect(url_for("admin_stone_challenges", stone_id=new["id"]))
    return render_template("admin_stone_form.html", stone=None, all_stones=all_stones, error=error)

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
                        request.form.get("dependencies","").strip(),
                        request.form.get("home_content","").strip(),
                        request.form.get("campaign","").strip() or DEFAULT_CAMPAIGN)
        return redirect(url_for("admin"))
    return render_template("admin_stone_form.html", stone=s, all_stones=all_stones, error=error)

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
    chs = conn.execute("SELECT * FROM challenges WHERE stone_id=? ORDER BY ord", (stone_id,)).fetchall()
    conn.close()
    return render_template("admin_challenges.html", stone=s, challenges=chs)

@app.route("/admin/challenge/add/<int:stone_id>", methods=["GET", "POST"])
@admin_required
def admin_add_challenge(stone_id):
    s = db.get_stone(stone_id)
    if not s: abort(404)
    error = None
    if request.method == "POST":
        slug      = re.sub(r'[^a-zA-Z0-9_-]','_', request.form.get("slug","").strip())
        title     = request.form.get("title","").strip()
        points    = request.form.get("points",10,type=int)
        is_final  = bool(request.form.get("is_final"))
        answer_1  = request.form.get("answer_1","").strip()
        ans_name  = request.form.get("answer_name","").strip()
        ans_city  = request.form.get("answer_city","").strip()
        order     = request.form.get("order",0,type=int)
        if not slug: error = "Slug is required."
        elif db.slug_exists(slug): error = f"Slug '{slug}' already in use."
        elif is_final and (not ans_name or not ans_city): error = "Name and city are required."
        elif not is_final and not answer_1: error = "Answer is required."
        else:
            db.create_challenge(stone_id,slug,title,points,is_final,
                                answer_1,ans_name,ans_city,"","","",0,order)
            ensure_challenge_file(slug)
            return redirect(url_for("admin_stone_challenges", stone_id=stone_id))
    next_order = db.count_challenges_for_stone(stone_id)
    return render_template("admin_challenge_form.html", stone=s, challenge=None,
                           next_order=next_order, error=error)

@app.route("/admin/challenge/<int:challenge_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_challenge(challenge_id):
    ch = db.get_challenge_full(challenge_id)
    if not ch: abort(404)
    s = db.get_stone(ch["stone_id"])
    error = None
    if request.method == "POST":
        slug      = re.sub(r'[^a-zA-Z0-9_-]','_', request.form.get("slug","").strip())
        title     = request.form.get("title","").strip()
        points    = request.form.get("points",10,type=int)
        is_final  = bool(request.form.get("is_final"))
        answer_1  = request.form.get("answer_1","").strip()
        ans_name  = request.form.get("answer_name","").strip()
        ans_city  = request.form.get("answer_city","").strip()
        order     = request.form.get("order",0,type=int)
        if not slug: error = "Slug is required."
        elif db.slug_exists(slug, exclude_id=challenge_id): error = f"Slug '{slug}' already in use."
        elif is_final and (not ans_name or not ans_city): error = "Name and city are required."
        elif not is_final and not answer_1: error = "Answer is required."
        else:
            db.update_challenge(challenge_id,slug,title,points,is_final,
                                answer_1,ans_name,ans_city,"","","",0,order)
            ensure_challenge_file(slug)
            return redirect(url_for("admin_stone_challenges", stone_id=s["id"]))
    return render_template("admin_challenge_form.html", stone=s, challenge=ch,
                           next_order=ch["ord"], error=error)

@app.route("/admin/challenge/<int:challenge_id>/delete", methods=["POST"])
@admin_required
def admin_delete_challenge(challenge_id):
    ch = db.get_challenge_full(challenge_id)
    if not ch: abort(404)
    stone_id = ch["stone_id"]
    db.delete_challenge(challenge_id)
    return redirect(url_for("admin_stone_challenges", stone_id=stone_id))


@app.route("/admin/challenge/<int:challenge_id>/hints", methods=["GET", "POST"])
@admin_required
def admin_challenge_hints(challenge_id):
    ch = db.get_challenge_full(challenge_id)
    if not ch: abort(404)
    s = db.get_stone(ch["stone_id"])
    msg = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            field   = request.form.get("field", "answer_1")
            trigger = request.form.get("trigger_answer","").strip()
            text    = request.form.get("hint_text","").strip()
            if trigger and text:
                db.create_hint(challenge_id, field, trigger, text)
                msg = "Hint added."
        elif action == "delete":
            hint_id = request.form.get("hint_id", type=int)
            if hint_id:
                db.delete_hint(hint_id)
                msg = "Hint deleted."
    hints = db.get_hints_for_challenge(challenge_id)
    return render_template("admin_hints.html", stone=s, challenge=ch, hints=hints, msg=msg)


# ── bootstrap ──────────────────────────────────────────────────────────────────

def bootstrap():
    """Prepare the database and content files. Safe to call on every start:
    init/migrate are idempotent, seeding only runs on an empty database, and
    content/challenge files are only written when missing.
    Call this from both the dev runner and the WSGI entry point."""
    db.init_db()
    db.migrate_db()
    db.seed_demo_data()
    for slug in db.get_all_slugs():
        ensure_challenge_file(slug)
    # Starter content files (only written if they don't exist yet)
    for path, content in [
        (HOME_CONTENT, """<h2 style="font-family:var(--mono);color:var(--blue);margin-bottom:1rem;">Welcome to Konundrum</h2>
<p>Solve the cryptography pyramid from bottom to top.</p>
<ul style="margin:1rem 0 1rem 1.5rem;line-height:2;">
  <li>Each <strong style="color:var(--green)">stone</strong> contains multiple sublevels.</li>
  <li>Solve sublevels in any order — the final sublevel (NAME+CITY) must be last.</li>
  <li>A stone is unlocked once the required stones below are fully solved.</li>
  <li>Each sublevel awards points. Compare your score on the <a href="/hall-of-fame">Hall of Fame</a>.</li>
</ul>
<p style="color:var(--text-dim);">Edit this text via Admin → Homepage.</p>
"""),
        (ABOUT_CONTENT, """<h2 style="font-family:var(--mono);color:var(--blue);margin-bottom:1rem;">About Konundrum</h2>
<p>Konundrum is a cryptography challenge where you must decipher a pyramid of ciphers.</p>
<p style="margin-top:.75rem;color:var(--text-dim);">Edit this text via Admin → About page.</p>
"""),
    ]:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)


# ── entry point (local development only) ────────────────────────────────────────

if __name__ == "__main__":
    bootstrap()
    # Debug is off unless FLASK_DEBUG=1 is set. Never run with debug on a public server.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
