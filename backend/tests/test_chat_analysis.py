from datetime import datetime
from pathlib import Path

import pytest

from app.chat_analysis import analyze_reply_intervals, parse_chat_text

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"

# Jamie double-texts, Taylor replies 10 min after Jamie's LAST message,
# Jamie replies, Taylor replies 30 min later.
CHAT = """\
10/10/2026, 9:00 AM - Jamie: Hi
10/10/2026, 9:05 AM - Jamie: You there?
10/10/2026, 9:15 AM - Taylor: Yes!
10/10/2026, 9:20 AM - Jamie: Great
10/10/2026, 9:50 AM - Taylor: Sorry, busy
"""


# ---------- parse_chat_text ----------

def test_parses_valid_lines_into_timestamp_sender_content():
    messages = parse_chat_text(
        "10/10/2026, 9:30 AM - Alex: Hey, how are you?\n"
        "10/10/2026, 9:31 PM - Sam:  I'm good  "
    )

    assert messages == [
        {"timestamp": datetime(2026, 10, 10, 9, 30), "sender": "Alex", "content": "Hey, how are you?"},
        {"timestamp": datetime(2026, 10, 10, 21, 31), "sender": "Sam", "content": "I'm good"},
    ]


def test_content_keeps_later_colons_and_dashes():
    [message] = parse_chat_text("10/10/2026, 9:30 AM - Alex: meet at 9:45 - ok?")

    assert message["sender"] == "Alex"
    assert message["content"] == "meet at 9:45 - ok?"


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_returns_no_messages(text):
    assert parse_chat_text(text) == []


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
def test_malformed_lines_are_skipped(line):
    assert parse_chat_text(line) == []


def test_malformed_lines_do_not_drop_valid_neighbours():
    messages = parse_chat_text(
        "garbage\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
        "continuation of first message\n"
        "10/10/2026, 9:31 AM - Sam: second\n"
    )

    assert [m["content"] for m in messages] == ["first", "second"]  # continuation line is dropped


def test_output_is_sorted_by_timestamp():
    messages = parse_chat_text(
        "10/10/2026, 9:32 AM - Alex: third\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
        "10/10/2026, 9:31 AM - Sam: second\n"
    )

    assert [m["content"] for m in messages] == ["first", "second", "third"]


@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("13/10/2026, 9:30 AM", datetime(2026, 10, 13, 9, 30)),   # day first
        ("01/02/2026, 9:30 AM", datetime(2026, 2, 1, 9, 30)),     # 1 Feb, not 2 Jan
        ("10/10/2026, 12:05 AM", datetime(2026, 10, 10, 0, 5)),   # midnight hour
        ("10/10/2026, 12:05 PM", datetime(2026, 10, 10, 12, 5)),  # noon hour
        ("10/10/2026, 9:30 am", datetime(2026, 10, 10, 9, 30)),   # lower-case am/pm
        ("10/10/2026, 9:30 AM", datetime(2026, 10, 10, 9, 30)),  # narrow no-break space (newer exports)
    ],
)
def test_supported_timestamp_format(timestamp, expected):
    [message] = parse_chat_text(f"{timestamp} - Alex: hi")

    assert message["timestamp"] == expected


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
    assert parse_chat_text(f"{timestamp} - Alex: hi") == []


# ---------- analyze_reply_intervals ----------

def test_empty_messages_return_no_intervals():
    assert analyze_reply_intervals([], "Jamie") == {
        "reply_details": [],
        "reply_times": [],
        "average_reply_time": None,
    }


def test_measures_other_persons_replies_to_the_user():
    result = analyze_reply_intervals(parse_chat_text(CHAT), "Jamie")

    assert result["reply_details"] == [
        {"from": "Taylor", "to": "Jamie", "minutes": 10.0},
        {"from": "Taylor", "to": "Jamie", "minutes": 30.0},
    ]
    assert result["reply_times"] == [10.0, 30.0]
    assert result["average_reply_time"] == 20.0


def test_reply_is_timed_from_users_last_message_in_a_burst():
    # Jamie wrote at 9:00 and 9:05; Taylor's 9:15 reply counts as 10 min, not 15.
    result = analyze_reply_intervals(parse_chat_text(CHAT), "Jamie")

    assert result["reply_times"][0] == 10.0


def test_users_own_replies_are_not_counted():
    result = analyze_reply_intervals(parse_chat_text(CHAT), "Taylor")

    assert result["reply_details"] == [{"from": "Jamie", "to": "Taylor", "minutes": 5.0}]
    assert result["average_reply_time"] == 5.0


@pytest.mark.parametrize("user_name", ["jamie", "  JAMIE  "])
def test_user_name_match_ignores_case_and_surrounding_spaces(user_name):
    result = analyze_reply_intervals(parse_chat_text(CHAT), user_name)

    assert result["reply_times"] == [10.0, 30.0]


@pytest.mark.parametrize("user_name", ["Jamie Lee", "Jam", "", "   "])
def test_unknown_or_blank_user_name_gives_no_intervals(user_name):
    result = analyze_reply_intervals(parse_chat_text(CHAT), user_name)

    assert result == {"reply_details": [], "reply_times": [], "average_reply_time": None}


def test_reply_across_midnight():
    messages = parse_chat_text(
        "10/10/2026, 11:59 PM - Jamie: night\n"
        "11/10/2026, 12:01 AM - Taylor: still up\n"
    )

    assert analyze_reply_intervals(messages, "Jamie")["reply_times"] == [2.0]


def test_same_minute_reply_counts_as_zero():
    messages = parse_chat_text(
        "10/10/2026, 9:00 AM - Jamie: hi\n"
        "10/10/2026, 9:00 AM - Taylor: hi\n"
    )

    assert analyze_reply_intervals(messages, "Jamie")["reply_times"] == [0.0]


def test_unsorted_input_is_sorted_before_measuring():
    messages = list(reversed(parse_chat_text(CHAT)))

    assert analyze_reply_intervals(messages, "Jamie")["reply_times"] == [10.0, 30.0]


def test_out_of_order_sample_file():
    # Replaces the old backend/test_read_chat.py script, which used this file.
    text = (DATA_DIR / "whatsapp_invalid_sample.txt").read_text(encoding="utf-8")

    result = analyze_reply_intervals(parse_chat_text(text), "Jamie")

    # Sorted: Jamie 2:00, 2:01, 2:02 | Taylor 2:06, 2:08 | Jamie 2:10
    assert result["reply_details"] == [{"from": "Taylor", "to": "Jamie", "minutes": 4.0}]
