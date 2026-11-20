import hashlib

import pytest

from app.domain.imports import derive_title, fingerprint

# ---------- fingerprint ----------


def test_fingerprint_is_the_sha256_hex_of_the_text():
    assert fingerprint("chat\nline") == hashlib.sha256(b"chat\nline").hexdigest()


@pytest.mark.parametrize(
    "variant",
    [
        "\ufeffchat\nline",           # BOM
        "chat\r\nline",               # Windows line endings
        "chat\rline",                 # old Mac line endings
        "chat\nline\n",               # final newline
        "chat\nline\r\n\n  \t",       # trailing blank lines and spaces at the end of the file
        "\ufeffchat\r\nline\r\n",     # all of the above
    ],
)
def test_fingerprint_ignores_bom_line_endings_and_whitespace_at_the_end(variant):
    assert fingerprint(variant) == fingerprint("chat\nline")


@pytest.mark.parametrize(
    "different",
    [
        "chat\nline!",       # content
        "Chat\nline",        # letter case
        "chat \nline",       # a space inside the text
        " chat\nline",       # leading whitespace is kept
        "chat\n\nline",      # an extra line inside the text
        "chét\nline",  # no Unicode normalisation (é written as e + accent)
    ],
)
def test_any_other_change_gives_a_different_fingerprint(different):
    assert fingerprint(different) != fingerprint("chat\nline")


# ---------- derive_title ----------


@pytest.mark.parametrize(
    "filename, senders, title",
    [
        ("WhatsApp Chat with Alex.txt", ["Sam"], "Alex"),
        ("whatsapp chat with Family Group 🎉.TXT", [], "Family Group 🎉"),
        ("WhatsApp Chat with   .txt", ["Sam"], "Sam"),  # blank name: use the senders
        ("_chat.txt", ["Alex"], "Alex"),
        ("_chat.txt", ["Alex", "Sam"], "Alex & Sam"),
        ("_chat.txt", ["Alex", "Sam", "Bea"], "Alex, Sam & Bea"),
        ("_chat.txt", ["Alex", "Sam", "Bea", "Kai", "Lou"], "Alex, Sam & 3 others"),
        ("my export.txt", [], "my export"),
    ],
)
def test_title(filename, senders, title):
    assert derive_title(filename, senders) == title


def test_title_longer_than_255_characters_is_shortened_with_an_ellipsis():
    title = derive_title("_chat.txt", ["A" * 300])

    assert len(title) == 255
    assert title == "A" * 254 + "…"
