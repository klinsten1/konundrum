# Konundrum 🔐

Cryptografie-piramide challenge website — Flask + SQLite.

## Snelle start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**

Database en voorbeelddata worden automatisch aangemaakt.

---

## Standaard login

| Rol   | Username | Wachtwoord |
|-------|----------|------------|
| Admin | admin    | admin123   |

---

## Piramide werking

De piramide wordt **automatisch opgebouwd** op basis van de `row` en `col` waarden in de database.

```
rij 3 (top):        [ S10 ]
rij 2:          [ S8 ]    [ S9 ]
rij 1:      [ S5 ]  [ S6 ]  [ S7 ]
rij 0:  [ S1 ] [ S2 ] [ S3 ] [ S4 ]
```

**Nieuwe steen toevoegen = piramide groeit automatisch.**
Stel gewoon `row` en `col` in, de rest regelt de app.

---

## Sublevel types

| Type        | Antwoordvelden     | Badge       |
|-------------|--------------------|-------------|
| SINGLE      | 1 veld (antwoord)  | blauw       |
| NAME + CITY | 2 velden           | geel ★      |

**Aanbeveling:** maak het laatste sublevel van elke steen altijd NAME+CITY.

---

## Vraagbestanden

Elke challenge heeft een HTML-bestand in de `challenges/` map:

```
challenges/
  s1_c1.html   ← vraag voor sublevel s1_c1
  s1_c2.html
  s2_c1.html
  ...
```

**Wat je kunt toevoegen:**
- Tekst / HTML
- Afbeeldingen: `<img src="/static/images/foto.jpg">`
- Inline JavaScript / Canvas animaties

**Wat je NOOIT in een challenge-bestand zet:** antwoorden.
Die staan veilig in de database en komen nooit in de browser.

Bestanden worden automatisch aangemaakt via Admin → Sublevel toevoegen.

---

## Hints

Elke challenge heeft een `hint_threshold` (standaard 60%):
- Antwoord ≥ 60% gelijkenis → "Bijna! [hint tekst]"
- Antwoord < 60% → "Niet correct."
- 0% = hints uitgeschakeld

---

## Veiligheid

- Antwoorden zitten **alleen in de database**
- `get_challenges_safe()` geeft templates **nooit** antwoord-velden
- `/api/check` controleert server-side, stuurt enkel `correct/hint/wrong` terug
- Slug-validatie voorkomt path traversal (`[a-zA-Z0-9_-]` only)
- Challenge HTML-bestanden worden server-side geladen (geen client-side file paths)

---

## Productie

```bash
export SECRET_KEY="lang-willekeurig-geheim"
pip install gunicorn
gunicorn -w 4 app:app
```
