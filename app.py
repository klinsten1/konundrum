"""
app.py — Konundrum
Features: email confirmation, 404 page, admin overview, about page, password reset, trigger hints
"""
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from markupsafe import Markup
import os, re
import database as db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "verander-dit-voor-productie")

CHALLENGES_DIR = os.path.join(os.path.dirname(__file__), "challenges")
HOME_CONTENT   = os.path.join(os.path.dirname(__file__), "templates", "home_content.html")
ABOUT_CONTENT  = os.path.join(os.path.dirname(__file__), "templates", "about_content.html")

# ── mail (optional) ────────────────────────────────────────────────────────────
# Set MAIL_SERVER etc. as environment variables for real email.
# If MAIL_SERVER is not configured, the confirm link is logged to console.

def send_confirmation_email(email, username, token):
    confirm_url = f"{request.host_url.rstrip('/')}{url_for('confirm_email', token=token)}"
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
            f"Confirm your email address via this link:\n{confirm_url}\n\n"
            f"If you didn't create an account, please ignore this message.\n\nKonundrum",
            "plain", "utf-8")
        msg["Subject"] = "Confirm your Konundrum account"
        msg["From"]    = sender
        msg["To"]      = email
        with smtplib.SMTP(server, port) as s:
            s.starttls()
            if user:
                s.login(user, password)
            s.sendmail(sender, [email], msg.as_string())
        return True
    except Exception as e:
        print(f"[MAIL] Could not send email ({e}). Confirmation link: {confirm_url}")
        return False


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
            return redirect(url_for("pyramid"))
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

def build_pyramid_rows(user_id):
    solved    = db.get_solved_challenge_ids(user_id)
    completed = db.get_completed_stone_ids(user_id)
    unlocked  = get_unlocked_ids(user_id)
    rows = {}
    for stone in db.get_all_stones():
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
            if not user["email_confirmed"] and not user["is_admin"]:
                error = "Please confirm your email address first. Check your inbox."
            else:
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
            user = db.create_user(username, email, generate_password_hash(password))
            send_confirmation_email(email, username, user["confirm_token"])
            return render_template("register_done.html", email=email)
    return render_template("register.html", error=error)

@app.route("/confirm/<token>")
def confirm_email(token):
    user = db.get_user_by_token(token)
    if not user:
        return render_template("404.html", code=400,
                               msg="Invalid or expired confirmation link."), 400
    db.confirm_user_email(user["id"])
    session.update(user_id=user["id"], username=user["username"], is_admin=False)
    return redirect(url_for("home"))

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
    content = Markup(load_file_content(HOME_CONTENT))
    score   = db.get_user_total_points(session["user_id"])
    total   = db.total_possible_points()
    return render_template("home.html", content=content, score=score, total=total)

@app.route("/about")
def about():
    content = Markup(load_file_content(ABOUT_CONTENT))
    return render_template("about.html", content=content)

@app.route("/pyramid")
@login_required
def pyramid():
    rows  = build_pyramid_rows(session["user_id"])
    score = db.get_user_total_points(session["user_id"])
    total = db.total_possible_points()
    return render_template("pyramid.html", rows=rows, score=score, total=total)

@app.route("/stone/<int:stone_id>")
@login_required
def stone_view(stone_id):
    user_id = session["user_id"]
    s = db.get_stone(stone_id)
    if not s: abort(404)
    if stone_id not in get_unlocked_ids(user_id):
        return redirect(url_for("pyramid"))
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
        return redirect(url_for("pyramid"))
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

@app.route("/profile")
@login_required
def profile():
    stats    = db.get_user_stats(session["user_id"])
    total_ch = db.count_all_challenges()
    total_pts= db.total_possible_points()
    total_st = len(db.get_all_stones())
    return render_template("profile.html", stats=stats,
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
    if ch["is_final"]:
        f_name = check_field(data.get("answer_name",""), ch["answer_name"], challenge_id, "answer_name")
        f_city = check_field(data.get("answer_city",""), ch["answer_city"], challenge_id, "answer_city")
        all_correct = (f_name["status"] == "correct" and f_city["status"] == "correct")
        fields = {"answer_name": f_name, "answer_city": f_city}
    else:
        f1 = check_field(data.get("answer_1",""), ch["answer_1"], challenge_id, "answer_1")
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
        if not name or row is None or col is None:
            error = "Name, row, and column are required."
        elif db.get_stone_by_name(name):
            error = f"Name '{name}' already in use."
        else:
            new = db.create_stone(name, label, row, col, deps, home)
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
                        request.form.get("home_content","").strip())
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


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    db.migrate_db()
    db.seed_demo_data()
    for slug in db.get_all_slugs():
        ensure_challenge_file(slug)
    # Starter content files
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
    app.run(debug=True)
