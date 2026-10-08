"""
wsgi.py — WSGI entry point for production (e.g. PythonAnywhere).

PythonAnywhere imports a WSGI file and looks for a module-level `application`.
Point your PythonAnywhere web app's WSGI config at this file (or copy its
contents into the editor PythonAnywhere gives you), and set `application`.

Locally you don't need this file — just run `python app.py`.
"""
import os
import sys

# Make sure this project folder is importable, regardless of where the WSGI
# server starts from.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import app as application, bootstrap

# Prepare the database and content files once, at import time.
bootstrap()
