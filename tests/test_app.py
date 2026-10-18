"""Automated tests for the Library Management System.

Every test gets a brand-new, empty SQLite database in a temporary folder,
so tests never touch your real data and never affect each other.
"""

import pytest

from app import create_app

VALID_BOOK = {
    "title": "Test Driven Development",
    "author": "Kent Beck",
    "isbn": "978-0321146533",
    "published_year": "2002",
    "genre": "Programming",
}


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test_library.db"),
            "SEED_SAMPLE_DATA": False,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def add_book(client, **overrides):
    """Helper: submit the add-book form and return the response."""
    data = {**VALID_BOOK, **overrides}
    return client.post("/books/add", data=data)


def test_health_endpoint_reports_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["version"] == "dev"  # default when not running a CI-built image


def test_home_page_shows_empty_library(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"No books in the library yet" in response.data


def test_add_book_page_loads(client):
    response = client.get("/books/add")
    assert response.status_code == 200
    assert b"Add a New Book" in response.data


def test_add_book_success(client):
    response = add_book(client)
    assert response.status_code == 302  # redirected to the new book's page

    home = client.get("/")
    assert b"Test Driven Development" in home.data
    assert b"Kent Beck" in home.data


def test_add_book_stores_isbn_without_hyphens(client):
    add_book(client)
    books = client.get("/api/books").get_json()
    assert books[0]["isbn"] == "9780321146533"


def test_add_book_requires_title_and_author(client):
    response = add_book(client, title="", author="   ")
    assert response.status_code == 400
    assert b"Title is required." in response.data
    assert b"Author is required." in response.data
    assert client.get("/api/books").get_json() == []


def test_add_book_rejects_invalid_isbn(client):
    response = add_book(client, isbn="12345")
    assert response.status_code == 400
    assert b"ISBN must contain 10 or 13 digits" in response.data


def test_add_book_rejects_duplicate_isbn(client):
    add_book(client)
    response = add_book(client, title="Another Title")
    assert response.status_code == 400
    assert b"A book with this ISBN already exists." in response.data
    assert len(client.get("/api/books").get_json()) == 1


def test_add_book_rejects_invalid_year(client):
    response = add_book(client, published_year="3000")
    assert response.status_code == 400
    assert b"Published year must be between 1000" in response.data

    response = add_book(client, published_year="abc")
    assert response.status_code == 400
    assert b"Published year must be a number." in response.data


def test_book_detail_page(client):
    add_book(client)
    response = client.get("/books/1")
    assert response.status_code == 200
    assert b"Test Driven Development" in response.data
    assert b"9780321146533" in response.data
    assert b"available" in response.data


def test_missing_book_returns_404(client):
    response = client.get("/books/999")
    assert response.status_code == 404
    assert b"Page Not Found" in response.data


def test_issue_and_return_book(client):
    add_book(client)

    response = client.post(
        "/books/1/issue", data={"borrower": "Asha"}, follow_redirects=True
    )
    assert b"was issued to Asha" in response.data
    book = client.get("/api/books").get_json()[0]
    assert book["status"] == "issued"
    assert book["borrower"] == "Asha"

    response = client.post("/books/1/return", follow_redirects=True)
    assert b"was returned" in response.data
    book = client.get("/api/books").get_json()[0]
    assert book["status"] == "available"
    assert book["borrower"] is None


def test_issue_requires_borrower_name(client):
    add_book(client)
    response = client.post(
        "/books/1/issue", data={"borrower": ""}, follow_redirects=True
    )
    assert b"Please enter the borrower&#39;s name." in response.data
    assert client.get("/api/books").get_json()[0]["status"] == "available"


def test_cannot_issue_book_twice(client):
    add_book(client)
    client.post("/books/1/issue", data={"borrower": "Asha"})
    response = client.post(
        "/books/1/issue", data={"borrower": "Ravi"}, follow_redirects=True
    )
    assert b"This book is already issued." in response.data
    assert client.get("/api/books").get_json()[0]["borrower"] == "Asha"


def test_delete_book(client):
    add_book(client)
    response = client.post("/books/1/delete", follow_redirects=True)
    assert b"was deleted" in response.data
    assert client.get("/api/books").get_json() == []
    assert client.get("/books/1").status_code == 404


def test_search_books(client):
    add_book(client)
    add_book(client, title="Docker in Practice", author="Ian Miell", isbn="9781617297809")

    response = client.get("/?q=docker")
    assert b">Docker in Practice</a>" in response.data
    assert b">Test Driven Development</a>" not in response.data

    response = client.get("/?q=nothing-matches-this")
    assert b"No books match" in response.data


def test_api_returns_json_list(client):
    add_book(client)
    response = client.get("/api/books")
    assert response.status_code == 200
    assert response.is_json
    books = response.get_json()
    assert len(books) == 1
    assert books[0]["title"] == "Test Driven Development"


def test_sample_books_added_when_seeding_enabled(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "seed.db")})
    books = app.test_client().get("/api/books").get_json()
    assert len(books) == 3


def test_status_filter_shows_only_matching_books(client):
    add_book(client)
    add_book(client, title="Docker in Practice", author="Ian Miell", isbn="9781617297809")
    client.post("/books/2/issue", data={"borrower": "Asha"})

    response = client.get("/?status=issued")
    assert b">Docker in Practice</a>" in response.data
    assert b">Test Driven Development</a>" not in response.data

    response = client.get("/?status=available")
    assert b">Test Driven Development</a>" in response.data
    assert b">Docker in Practice</a>" not in response.data


def test_unknown_status_filter_shows_all_books(client):
    add_book(client)
    response = client.get("/?status=nonsense")
    assert response.status_code == 200
    assert b">Test Driven Development</a>" in response.data


def test_dashboard_shows_live_counts(client):
    add_book(client)
    add_book(client, title="Docker in Practice", author="Ian Miell", isbn="9781617297809")
    client.post("/books/1/issue", data={"borrower": "Asha"})

    html = client.get("/").get_data(as_text=True)
    assert '<span class="stat-number">2</span>' in html  # total
    assert html.count('<span class="stat-number">1</span>') == 2  # available + on loan
    assert "50% of the collection" in html


def test_invalid_field_is_highlighted(client):
    response = add_book(client, isbn="12345")
    assert b'aria-invalid="true"' in response.data
    assert b"The book was not saved." in response.data


def test_image_version_is_shown_on_pages_and_health(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "version.db"),
            "SEED_SAMPLE_DATA": False,
            "APP_VERSION": "sha-abc1234",
        }
    )
    client = app.test_client()
    assert client.get("/health").get_json()["version"] == "sha-abc1234"
    assert b"sha-abc1234" in client.get("/").data


def test_dashboard_shows_recently_added_books(client):
    add_book(client)
    add_book(client, title="Docker in Practice", author="Ian Miell", isbn="9781617297809")
    html = client.get("/").get_data(as_text=True)
    assert "Recently added" in html
    # Newest book first
    assert html.index("<strong>Docker in Practice</strong>") < html.index(
        "<strong>Test Driven Development</strong>"
    )


def test_recently_added_is_hidden_while_searching(client):
    add_book(client)
    assert b"Recently added" not in client.get("/?q=test").data


def test_logo_is_served(client):
    html = client.get("/").get_data(as_text=True)
    assert "img/logo.svg" in html
    response = client.get("/static/img/logo.svg")
    assert response.status_code == 200
    assert b"<svg" in response.data
    response.close()
