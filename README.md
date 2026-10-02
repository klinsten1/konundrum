# Konundrum 🔐

Cryptography pyramid challenge website — Flask + SQLite.

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**

Database and sample data are created automatically.

---

## Default login

| Role  | Username | Password |
|-------|----------|----------|
| Admin | admin    | admin123 |

---

## Pyramid mechanics

The pyramid is **automatically built** based on the `row` and `col` values in the database.

```
row 3 (top):        [ S10 ]
row 2:          [ S8 ]    [ S9 ]
row 1:      [ S5 ]  [ S6 ]  [ S7 ]
row 0:  [ S1 ] [ S2 ] [ S3 ] [ S4 ]
```

**Adding a new stone = pyramid grows automatically.**
Just set `row` and `col`, the app handles the rest.

---

## Sublevel types

| Type        | Answer fields      | Badge       |
|-------------|--------------------|-------------|
| SINGLE      | 1 field (answer)   | blue        |
| NAME + CITY | 2 fields           | yellow ★    |

**Recommendation:** make the last sublevel of each stone always NAME+CITY.

---

## Challenge files

Each challenge has an HTML file in the `challenges/` folder:

```
challenges/
  s1_c1.html   ← question for sublevel s1_c1
  s1_c2.html
  s2_c1.html
  ...
```

**What you can add:**
- Text / HTML
- Images: `<img src="/static/images/photo.jpg">`
- Inline JavaScript / Canvas animations

**What you NEVER put in a challenge file:** answers.
Those are safely stored in the database and never reach the browser.

Files are automatically created via Admin → Add sublevel.

---

## Hints

Each challenge can have multiple **trigger hints**:
- In Admin → Sublevel → Hints you can link specific wrong answers to hints
- When a player enters exactly that trigger answer (case-insensitive), they see the hint
- Example: trigger "caesar" → hint "Think of an older cipher than Caesar..."
- You can set multiple triggers per challenge, each with their own hint text
- No match = simply "Incorrect."

---

## Password reset

- Login page has a "Forgot password?" link
- User enters email address → receives a reset link (valid for 1 hour)
- Without MAIL_SERVER config the link is logged to console (same as confirmation email)

---

## Security

- Answers are **only in the database**
- `get_challenges_safe()` never gives templates answer fields
- `/api/check` checks server-side, only sends `correct/hint/wrong` back
- Slug validation prevents path traversal (`[a-zA-Z0-9_-]` only)
- Challenge HTML files are loaded server-side (no client-side file paths)

---

## Production

```bash
export SECRET_KEY="long-random-secret"
pip install gunicorn
gunicorn -w 4 app:app
```
