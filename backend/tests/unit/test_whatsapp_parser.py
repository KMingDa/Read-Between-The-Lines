from datetime import datetime

import pytest

from app.domain.entities import Message
from app.domain.parsing.whatsapp import parse_whatsapp_chat


def test_parses_valid_lines_into_messages():
    messages = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: Hey, how are you?\n"
        "10/10/2026, 9:31 PM - Sam:  I'm good  "
    )

    assert messages == [
        Message(timestamp=datetime(2026, 10, 10, 9, 30), sender="Alex", content="Hey, how are you?"),
        Message(timestamp=datetime(2026, 10, 10, 21, 31), sender="Sam", content="I'm good"),
    ]


def test_content_keeps_later_colons_and_dashes():
    [message] = parse_whatsapp_chat("10/10/2026, 9:30 AM - Alex: meet at 9:45 - ok?")

    assert message.sender == "Alex"
    assert message.content == "meet at 9:45 - ok?"


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_returns_no_messages(text):
    assert parse_whatsapp_chat(text) == []


@pytest.mark.parametrize(
    "line",
    [
        "just some text",                                                   # no " - " separator
        "not a date - Alex: hi",                                            # unparseable timestamp
        "10/10/2026, 9:30 AM - Messages are end-to-end encrypted.",         # system line, no "sender: "
        "10/10/2026, 9:30 AM - : hi",                                       # empty sender
        "10/10/2026, 9:30 AM - Alex: ",                                     # empty content
        "10/10/2026, 9:30 AM - Alex:no-space-after-colon",                  # needs ": "
    ],
)
def test_malformed_lines_on_their_own_give_no_messages(line):
    assert parse_whatsapp_chat(line) == []


@pytest.mark.parametrize(
    "text",
    [
        "\x00\x1b[31m - : \u202e",
        "99/99/9999, 99:99 PM - X: y",
        "10/10/2026, 9:30 AM - " + "A" * 5000 + ": " + "B" * 5000,
        " - \n - : \n:\n" * 50,
    ],
)
def test_garbage_input_never_raises(text):
    parse_whatsapp_chat(text)


def test_lines_before_the_first_message_are_ignored():
    messages = parse_whatsapp_chat(
        "Chat export header\n"
        "\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
    )

    assert [m.content for m in messages] == ["first"]


# ---------- multiline messages ----------

def test_continuation_lines_belong_to_the_message_above():
    messages = parse_whatsapp_chat(
        "garbage\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
        "continuation of first message\n"
        "10/10/2026, 9:31 AM - Sam: second\n"
    )

    assert [m.content for m in messages] == ["first\ncontinuation of first message", "second"]


def test_multiline_message_keeps_blank_lines_and_drops_trailing_spaces():
    [message] = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: Shopping list:  \n"
        "- milk\n"
        "\n"
        "- eggs   \n"
        "\n"
    )

    assert message.content == "Shopping list:\n- milk\n\n- eggs"


def test_line_that_looks_like_a_message_but_has_a_bad_date_is_a_continuation():
    [message] = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: plan\n"
        "step 1 - book: tickets\n"
    )

    assert message.content == "plan\nstep 1 - book: tickets"


def test_lines_after_a_system_notice_are_not_added_to_the_previous_message():
    messages = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: hi\n"
        "10/10/2026, 9:31 AM - Sam left\n"
        "stray line\n"
    )

    assert [m.content for m in messages] == ["hi"]


def test_message_with_empty_first_line_takes_its_text_from_following_lines():
    [message] = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: \n"
        "text on the next line\n"
    )

    assert message.content == "text on the next line"


# ---------- senders and ordering ----------

@pytest.mark.parametrize(
    "sender",
    ["Sam Lee", "+44 7700 900123", "Zoë 🌸", "Dr. Who"],
)
def test_sender_names_are_kept_as_written(sender):
    [message] = parse_whatsapp_chat(f"10/10/2026, 9:30 AM - {sender}: hi")

    assert message.sender == sender


def test_sender_name_is_trimmed():
    [message] = parse_whatsapp_chat("10/10/2026, 9:30 AM -  Alex : hi")

    assert message.sender == "Alex"


def test_consecutive_messages_from_one_sender_stay_separate():
    messages = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: one\n"
        "10/10/2026, 9:30 AM - Alex: two\n"
        "10/10/2026, 9:31 AM - Alex: three\n"
    )

    assert [(m.sender, m.content) for m in messages] == [("Alex", "one"), ("Alex", "two"), ("Alex", "three")]


def test_output_is_sorted_by_timestamp():
    messages = parse_whatsapp_chat(
        "10/10/2026, 9:32 AM - Alex: third\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
        "10/10/2026, 9:31 AM - Sam: second\n"
    )

    assert [m.content for m in messages] == ["first", "second", "third"]


# ---------- timestamps ----------

@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("13/10/2026, 9:30 AM", datetime(2026, 10, 13, 9, 30)),   # day first
        ("01/02/2026, 9:30 AM", datetime(2026, 2, 1, 9, 30)),     # 1 Feb, not 2 Jan
        ("10/10/2026, 12:05 AM", datetime(2026, 10, 10, 0, 5)),   # midnight hour
        ("10/10/2026, 12:05 PM", datetime(2026, 10, 10, 12, 5)),  # noon hour
        ("10/10/2026, 9:30 am", datetime(2026, 10, 10, 9, 30)),   # lower-case am/pm
        ("10/10/2026, 9:30\u202fAM", datetime(2026, 10, 10, 9, 30)),  # narrow no-break space (newer exports)
    ],
)
def test_supported_timestamp_format(timestamp, expected):
    [message] = parse_whatsapp_chat(f"{timestamp} - Alex: hi")

    assert message.timestamp == expected


@pytest.mark.parametrize(
    "timestamp",
    [
        "10/13/2026, 9:30 AM",          # month-first (US exports)
        "10/10/26, 9:30 AM",            # two-digit year
        "10/10/2026, 21:30",            # 24-hour clock
        "[10/10/2026, 9:30:00 AM]",     # bracketed iOS style
    ],
)
def test_unsupported_timestamp_formats_are_skipped(timestamp):
    # Documents current behaviour: only "dd/mm/yyyy, h:mm AM" is accepted.
    assert parse_whatsapp_chat(f"{timestamp} - Alex: hi") == []
