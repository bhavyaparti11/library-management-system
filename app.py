"""Library Management System: a small Flask + SQLite web application.

Features: a dashboard with live statistics, a searchable and filterable book
catalogue, adding books, viewing details, issuing a book to a borrower,
returning it, and deleting it. A JSON API (/api/books) and a health check
(/health) are also provided for automation and monitoring.
"""

import os
import re
import sqlite3
from datetime import datetime

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATABASE = os.path.join(BASE_DIR, "instance", "library.db")
STATUS_FILTERS = ("all", "available", "issued")

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    isbn TEXT NOT NULL UNIQUE,
    published_year INTEGER,
    genre TEXT,
    status TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('available', 'issued')),
    borrower TEXT,
    created_at TEXT NOT NULL
);
"""

SAMPLE_BOOKS = [
    ("Clean Code", "Robert C. Martin", "9780132350884", 2008, "Programming"),
    ("The Pragmatic Programmer", "Andrew Hunt", "9780201616224", 1999, "Programming"),
    ("Docker Deep Dive", "Nigel Poulton", "9781916585256", 2023, "DevOps"),
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Return one SQLite connection per request (stored on Flask's `g`)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None):
    """Close the connection at the end of every request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(seed_sample_data):
    """Create the books table if it does not exist and optionally add samples."""
    db = get_db()
    db.executescript(SCHEMA)
    if seed_sample_data:
        count = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        if count == 0:
            now = timestamp()
            # INSERT OR IGNORE is safe even if two server workers start together.
            db.executemany(
                "INSERT OR IGNORE INTO books "
                "(title, author, isbn, published_year, genre, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [book + (now,) for book in SAMPLE_BOOKS],
            )
    db.commit()


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def find_book(book_id):
    """Return the book with this id, or show a 404 page if it does not exist."""
    book = get_db().execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if book is None:
        abort(404)
    return book


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_book(form):
    """Check the add-book form. Returns (cleaned_data, {field: error_message})."""
    data = {
        "title": form.get("title", "").strip(),
        "author": form.get("author", "").strip(),
        "isbn": re.sub(r"[\s-]", "", form.get("isbn", "")),
        "published_year": form.get("published_year", "").strip(),
        "genre": form.get("genre", "").strip(),
    }
    errors = {}

    if not data["title"]:
        errors["title"] = "Title is required."
    elif len(data["title"]) > 200:
        errors["title"] = "Title must be 200 characters or fewer."

    if not data["author"]:
        errors["author"] = "Author is required."
    elif len(data["author"]) > 100:
        errors["author"] = "Author must be 100 characters or fewer."

    if not data["isbn"]:
        errors["isbn"] = "ISBN is required."
    elif not re.fullmatch(r"\d{9}[\dXx]|\d{13}", data["isbn"]):
        errors["isbn"] = "ISBN must contain 10 or 13 digits (hyphens are allowed)."
    else:
        data["isbn"] = data["isbn"].upper()

    if data["published_year"]:
        current_year = datetime.now().year
        if not data["published_year"].isdigit():
            errors["published_year"] = "Published year must be a number."
        elif not 1000 <= int(data["published_year"]) <= current_year:
            errors["published_year"] = (
                f"Published year must be between 1000 and {current_year}."
            )
        else:
            data["published_year"] = int(data["published_year"])
    else:
        data["published_year"] = None

    if len(data["genre"]) > 50:
        errors["genre"] = "Genre must be 50 characters or fewer."

    return data, errors


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-not-a-real-secret"),
        DATABASE=os.environ.get("DATABASE_PATH", DEFAULT_DATABASE),
        SEED_SAMPLE_DATA=os.environ.get("SEED_SAMPLE_DATA", "true").lower() == "true",
        # Set inside the Docker image by GitHub Actions (see Dockerfile), so the
        # running container can show exactly which image version it is.
        APP_VERSION=os.environ.get("APP_VERSION", "dev"),
        BUILD_DATE=os.environ.get("BUILD_DATE", ""),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db(app.config["SEED_SAMPLE_DATA"])

    register_routes(app)
    return app


def register_routes(app):
    @app.context_processor
    def inject_version():
        """Make the image version available to every template (sidebar/footer)."""
        return {
            "app_version": app.config["APP_VERSION"],
            "build_date": app.config["BUILD_DATE"],
        }

    @app.template_filter("cover_hue")
    def cover_hue(text):
        """Pick a stable colour (0-359) for a book's cover tile from its title."""
        return sum(ord(char) for char in text or "") * 37 % 360

    @app.route("/")
    def index():
        query = request.args.get("q", "").strip()
        status = request.args.get("status", "all")
        if status not in STATUS_FILTERS:
            status = "all"

        conditions, params = [], []
        if query:
            like = f"%{query}%"
            conditions.append("(title LIKE ? OR author LIKE ? OR isbn LIKE ?)")
            params += [like, like, like]
        if status != "all":
            conditions.append("status = ?")
            params.append(status)

        sql = "SELECT * FROM books"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        db = get_db()
        books = db.execute(sql + " ORDER BY title", params).fetchall()

        stats = db.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(status = 'available'), 0) AS available, "
            "COALESCE(SUM(status = 'issued'), 0) AS issued, "
            "COUNT(DISTINCT genre) AS genres FROM books"
        ).fetchone()
        return render_template(
            "index.html", books=books, stats=stats, query=query, status=status
        )

    @app.route("/books/add", methods=["GET", "POST"])
    def add_book():
        if request.method == "GET":
            return render_template("add_book.html", form={}, errors={})

        data, errors = validate_book(request.form)
        if not errors:
            db = get_db()
            try:
                cursor = db.execute(
                    "INSERT INTO books "
                    "(title, author, isbn, published_year, genre, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        data["title"],
                        data["author"],
                        data["isbn"],
                        data["published_year"],
                        data["genre"] or None,
                        timestamp(),
                    ),
                )
                db.commit()
            except sqlite3.IntegrityError:
                errors["isbn"] = "A book with this ISBN already exists."
            else:
                flash(f'"{data["title"]}" was added to the library.', "success")
                return redirect(url_for("book_detail", book_id=cursor.lastrowid))

        return render_template("add_book.html", form=request.form, errors=errors), 400

    @app.route("/books/<int:book_id>")
    def book_detail(book_id):
        return render_template("book_detail.html", book=find_book(book_id))

    @app.route("/books/<int:book_id>/issue", methods=["POST"])
    def issue_book(book_id):
        book = find_book(book_id)
        borrower = request.form.get("borrower", "").strip()
        if book["status"] == "issued":
            flash("This book is already issued.", "error")
        elif not borrower:
            flash("Please enter the borrower's name.", "error")
        elif len(borrower) > 100:
            flash("Borrower name must be 100 characters or fewer.", "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE books SET status = 'issued', borrower = ? WHERE id = ?",
                (borrower, book_id),
            )
            db.commit()
            flash(f'"{book["title"]}" was issued to {borrower}.', "success")
        return redirect(url_for("book_detail", book_id=book_id))

    @app.route("/books/<int:book_id>/return", methods=["POST"])
    def return_book(book_id):
        book = find_book(book_id)
        if book["status"] != "issued":
            flash("This book is not currently issued.", "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE books SET status = 'available', borrower = NULL WHERE id = ?",
                (book_id,),
            )
            db.commit()
            flash(f'"{book["title"]}" was returned.', "success")
        return redirect(url_for("book_detail", book_id=book_id))

    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    def delete_book(book_id):
        book = find_book(book_id)
        db = get_db()
        db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        db.commit()
        flash(f'"{book["title"]}" was deleted.', "success")
        return redirect(url_for("index"))

    @app.route("/api/books")
    def api_books():
        books = get_db().execute("SELECT * FROM books ORDER BY id").fetchall()
        return jsonify([dict(book) for book in books])

    @app.route("/health")
    def health():
        try:
            get_db().execute("SELECT 1").fetchone()
        except sqlite3.Error:
            return jsonify({"status": "error", "database": "unavailable"}), 500
        return jsonify(
            {
                "status": "ok",
                "database": "connected",
                "version": app.config["APP_VERSION"],
            }
        )

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("404.html"), 404


if __name__ == "__main__":
    # Local development server. Inside Docker, Gunicorn is used instead.
    create_app().run(host="127.0.0.1", port=5000, debug=True)
