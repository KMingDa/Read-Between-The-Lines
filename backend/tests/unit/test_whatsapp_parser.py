from datetime import datetime
from pathlib import Path

import pytest

from app.domain.entities import Message
from app.domain.parsing.whatsapp import parse_whatsapp_chat

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"


def messages(text, **kwargs):
    return list(parse_whatsapp_chat(text, **kwargs).messages)


# ---------- basics (behaviour from before the upgrade) ----------

def test_parses_valid_lines_into_messages():
    assert messages(
        "10/10/2026, 9:30 AM - Alex: Hey, how are you?\n"
        "10/10/2026, 9:31 PM - Sam:  I'm good  "
    ) == [
        Message(timestamp=datetime(2026, 10, 10, 9, 30), sender="Alex", content="Hey, how are you?"),
        Message(timestamp=datetime(2026, 10, 10, 21, 31), sender="Sam", content="I'm good"),
    ]


def test_synthetic_sample_file_parses_as_before():
    parsed = parse_whatsapp_chat((DATA_DIR / "whatsapp_sample.txt").read_text(encoding="utf-8"))

    assert [(m.timestamp.minute, m.sender) for m in parsed.messages] == [
        (30, "Alex"), (31, "Sam"), (32, "Alex"), (33, "Sam"),
    ]
    assert parsed.messages[-1].content == "What are you doing today?"
    assert parsed.skipped_line_count == 0


def test_content_keeps_later_colons_and_dashes():
    [message] = messages("10/10/2026, 9:30 AM - Alex: meet at 9:45 - ok?")

    assert message.sender == "Alex"
    assert message.content == "meet at 9:45 - ok?"


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_returns_nothing(text):
    parsed = parse_whatsapp_chat(text)

    assert (parsed.messages, parsed.skipped_line_count, parsed.warnings) == ((), 0, ())


@pytest.mark.parametrize(
    "line",
    [
        "just some text",                                   # no timestamp
        "not a date - Alex: hi",                            # no timestamp
        "10/10/2026, 9:30 AM - : hi",                       # empty sender
        "10/10/2026, 9:30 AM - Alex: ",                     # empty content
        "31/02/2026, 9:30 AM - Alex: hi",                   # no such date
        "10/10/2026, 25:00 - Alex: hi",                     # no such hour
        "10/10/2026, 13:30 PM - Alex: hi",                  # 13 PM
        "10/10/2026, 9:61 AM - Alex: hi",                   # no such minute
    ],
)
def test_malformed_line_is_skipped_and_counted(line):
    parsed = parse_whatsapp_chat(line)

    assert parsed.messages == ()
    assert parsed.skipped_line_count == 1


@pytest.mark.parametrize(
    "text",
    [
        "\x00\x1b[31m - : \u202e",
        "99/99/9999, 99:99 PM - X: y",
        "10/10/2026, 9:30 AM - " + "A" * 5000 + ": " + "B" * 5000,
        " - \n - : \n:\n" * 50,
        "[\n[]\n[10/10/2026, 9:30] \n\r\n\u2028\n\x85",
        "10/10/2026, 9:30 AM - Alex: hi\n" + "\u200e" * 1000,
    ],
)
def test_garbage_input_never_raises(text):
    parse_whatsapp_chat(text)


def test_lines_before_the_first_message_are_skipped():
    parsed = parse_whatsapp_chat(
        "Chat export header\n"
        "\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
    )

    assert [m.content for m in parsed.messages] == ["first"]
    assert parsed.skipped_line_count == 1  # blank lines are not counted


# ---------- multiline messages ----------

def test_continuation_lines_belong_to_the_message_above():
    parsed = parse_whatsapp_chat(
        "garbage\n"
        "10/10/2026, 9:30 AM - Alex: first\n"
        "continuation of first message\n"
        "10/10/2026, 9:31 AM - Sam: second\n"
    )

    assert [m.content for m in parsed.messages] == ["first\ncontinuation of first message", "second"]
    assert parsed.skipped_line_count == 1


def test_multiline_message_keeps_blank_lines_and_drops_trailing_spaces():
    [message] = messages(
        "10/10/2026, 9:30 AM - Alex: Shopping list:  \n"
        "- milk\n"
        "\n"
        "- eggs   \n"
        "\n"
    )

    assert message.content == "Shopping list:\n- milk\n\n- eggs"


def test_line_that_looks_like_a_message_but_has_no_timestamp_is_a_continuation():
    [message] = messages(
        "10/10/2026, 9:30 AM - Alex: plan\n"
        "step 1 - book: tickets\n"
    )

    assert message.content == "plan\nstep 1 - book: tickets"


def test_message_with_empty_first_line_takes_its_text_from_following_lines():
    [message] = messages(
        "10/10/2026, 9:30 AM - Alex: \n"
        "text on the next line\n"
    )

    assert message.content == "text on the next line"


def test_crlf_line_endings():
    assert [m.content for m in messages(
        "10/10/2026, 21:30 - Alex: one\r\ntwo\r\n10/10/2026, 21:31 - Sam: three\r\n"
    )] == ["one\ntwo", "three"]


# ---------- system messages ----------

def test_timestamped_line_without_sender_is_a_system_message():
    parsed = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: hi\n"
        "10/10/2026, 9:31 AM - Messages and calls are end-to-end encrypted.\n"
        "10/10/2026, 9:32 AM - Sam: hey\n"
    )

    assert [(m.sender, m.content) for m in parsed.messages] == [
        ("Alex", "hi"),
        (None, "Messages and calls are end-to-end encrypted."),
        ("Sam", "hey"),
    ]
    assert parsed.messages[1].timestamp == datetime(2026, 10, 10, 9, 31)


def test_lines_after_a_system_message_are_skipped_not_attached():
    parsed = parse_whatsapp_chat(
        "10/10/2026, 9:30 AM - Alex: hi\n"
        "10/10/2026, 9:31 AM - Sam left\n"
        "stray line\n"
    )

    assert [(m.sender, m.content) for m in parsed.messages] == [("Alex", "hi"), (None, "Sam left")]
    assert parsed.skipped_line_count == 1


def test_colon_without_a_space_does_not_make_a_sender():
    [message] = messages("10/10/2026, 9:30 AM - Alex:no-space-after-colon")

    assert (message.sender, message.content) == (None, "Alex:no-space-after-colon")


# ---------- order and senders ----------

def test_keeps_export_order_when_the_clock_goes_back():
    # After a daylight-saving change the export repeats an hour; the file order is the true order.
    parsed = parse_whatsapp_chat(
        "25/10/2026, 2:50 AM - Alex: before the clocks went back\n"
        "25/10/2026, 2:05 AM - Sam: after the clocks went back\n"
    )

    assert [m.sender for m in parsed.messages] == ["Alex", "Sam"]
    assert [m.timestamp.minute for m in parsed.messages] == [50, 5]


def test_messages_in_the_same_minute_keep_their_order():
    assert [(m.sender, m.content) for m in messages(
        "10/10/2026, 9:30 AM - Alex: one\n"
        "10/10/2026, 9:30 AM - Sam: two\n"
        "10/10/2026, 9:30 AM - Alex: three\n"
        "10/10/2026, 9:30 AM - Alex: three\n"
    )] == [("Alex", "one"), ("Sam", "two"), ("Alex", "three"), ("Alex", "three")]


@pytest.mark.parametrize("sender", ["Sam Lee", "+44 7700 900123", "Zoë 🌸", "Dr. Who"])
def test_sender_names_are_kept_as_written(sender):
    [message] = messages(f"10/10/2026, 9:30 AM - {sender}: hi")

    assert message.sender == sender


def test_sender_name_is_trimmed():
    [message] = messages("10/10/2026, 9:30 AM -  Alex : hi")

    assert message.sender == "Alex"


# ---------- supported formats ----------

@pytest.mark.parametrize(
    "line, expected",
    [
        ("10/10/2026, 9:30 PM - Alex: Hi", datetime(2026, 10, 10, 21, 30)),     # Android 12-hour
        ("10/10/2026, 21:30 - Alex: Hi", datetime(2026, 10, 10, 21, 30)),       # Android 24-hour
        ("10/10/26, 21:30 - Alex: Hi", datetime(2026, 10, 10, 21, 30)),         # two-digit year
        ("13/10/26, 9:30 PM - Alex: Hi", datetime(2026, 10, 13, 21, 30)),       # day first
        ("10/13/26, 9:30 PM - Alex: Hi", datetime(2026, 10, 13, 21, 30)),       # month first
        ("13.10.26, 21:30 - Alex: Hi", datetime(2026, 10, 13, 21, 30)),         # dots
        ("13-10-2026, 21:30 - Alex: Hi", datetime(2026, 10, 13, 21, 30)),       # dashes
        ("13/10/2026 21:30 - Alex: Hi", datetime(2026, 10, 13, 21, 30)),        # no comma
        ("[13/10/2026, 21:30:05] Alex: Hi", datetime(2026, 10, 13, 21, 30, 5)),  # iOS, seconds
        ("[10/13/26, 9:30:05 PM] Alex: Hi", datetime(2026, 10, 13, 21, 30, 5)),  # iOS 12-hour
        ("[13/10/2026 21:30:05] Alex: Hi", datetime(2026, 10, 13, 21, 30, 5)),   # iOS, no comma
        ("\u200e[13/10/2026, 21:30:05] Alex: Hi", datetime(2026, 10, 13, 21, 30, 5)),  # LRM first
        ("\u200f\u202a13/10/2026, 21:30 - Alex: Hi", datetime(2026, 10, 13, 21, 30)),  # RLM + embedding
        ("\ufeff13/10/2026, 21:30 - Alex: Hi", datetime(2026, 10, 13, 21, 30)),        # BOM
        ("13/10/2026, 12:05 AM - Alex: Hi", datetime(2026, 10, 13, 0, 5)),      # midnight, 12-hour
        ("13/10/2026, 12:05 PM - Alex: Hi", datetime(2026, 10, 13, 12, 5)),     # noon, 12-hour
        ("13/10/2026, 00:05 - Alex: Hi", datetime(2026, 10, 13, 0, 5)),         # midnight, 24-hour
    ],
)
def test_supported_format(line, expected):
    [message] = messages(line)

    assert (message.timestamp, message.sender, message.content) == (expected, "Alex", "Hi")


@pytest.mark.parametrize(
    "suffix", [" PM", " pm", " p.m.", " P.M.", " p. m.", "\u202fPM", "\u00a0pm", "PM"]
)
def test_am_pm_variants(suffix):
    [message] = messages(f"13/10/2026, 9:30{suffix} - Alex: Hi")

    assert message.timestamp == datetime(2026, 10, 13, 21, 30)


@pytest.mark.parametrize(
    "year, expected",
    [
        ("09", 2009),    # two digits: 2000 + yy
        ("99", 2099),
        ("1999", 1999),  # four digits: taken literally, nothing added
    ],
)
def test_year_expansion(year, expected):
    [message] = messages(f"13/10/{year}, 21:30 - Alex: Hi")

    assert message.timestamp == datetime(expected, 10, 13, 21, 30)


def test_direction_marks_at_the_start_of_the_text_are_removed():
    [message] = messages("\u200e[13/10/2026, 21:30:05] Alex: \u200eimage omitted")

    assert message.content == "image omitted"


@pytest.mark.parametrize(
    "line",
    [
        "2026/10/13, 21:30 - Alex: hi",       # year first
        "13/10/2026, 9:30 nachm. - Alex: hi",  # AM/PM word in another language
        "13/10/2026, 21h30 - Alex: hi",        # "h" between hours and minutes
        "13/10/2026, 9 PM - Alex: hi",         # no minutes
        "13/10-2026, 21:30 - Alex: hi",        # mixed date separators
    ],
)
def test_unsupported_timestamp_formats_are_skipped(line):
    parsed = parse_whatsapp_chat(line)

    assert parsed.messages == ()
    assert parsed.skipped_line_count == 1


# ---------- date order ----------

def test_day_first_is_inferred_from_a_day_above_12():
    parsed = parse_whatsapp_chat(
        "05/04/2026, 10:00 - Alex: a\n"
        "13/04/2026, 10:00 - Sam: b\n"
    )

    assert parsed.detected_date_order == "day_first"
    assert parsed.messages[0].timestamp == datetime(2026, 4, 5, 10, 0)
    assert (parsed.date_order_ambiguous, parsed.warnings) == (False, ())


def test_month_first_is_inferred_from_a_month_position_above_12():
    parsed = parse_whatsapp_chat(
        "05/04/2026, 10:00 - Alex: a\n"
        "04/13/2026, 10:00 - Sam: b\n"
    )

    assert parsed.detected_date_order == "month_first"
    assert parsed.messages[0].timestamp == datetime(2026, 5, 4, 10, 0)
    assert (parsed.date_order_ambiguous, parsed.warnings) == (False, ())


@pytest.mark.parametrize(
    "dates, order, first_three",
    [
        (["03/01/2026", "12/01/2026", "02/02/2026"], "day_first", [(1, 3), (1, 12), (2, 2)]),
        (["01/03/2026", "01/12/2026", "02/02/2026"], "month_first", [(1, 3), (1, 12), (2, 2)]),
    ],
)
def test_time_order_breaks_the_tie_when_no_number_is_above_12(dates, order, first_three):
    parsed = parse_whatsapp_chat("\n".join(f"{d}, 10:00 - Alex: hi" for d in dates))

    assert parsed.detected_date_order == order
    assert [(m.timestamp.month, m.timestamp.day) for m in parsed.messages] == first_three
    assert (parsed.date_order_ambiguous, parsed.warnings) == (False, ())


def test_ambiguous_dates_default_to_day_first_with_a_warning():
    parsed = parse_whatsapp_chat(
        "01/02/2026, 10:00 - Alex: a\n"
        "01/03/2026, 10:00 - Sam: b\n"
    )

    assert parsed.detected_date_order == "day_first"
    assert parsed.date_order_ambiguous is True
    assert parsed.messages[0].timestamp == datetime(2026, 2, 1, 10, 0)
    [warning] = parsed.warnings
    assert "ambiguous" in warning and "month first" in warning


def test_dates_that_read_the_same_both_ways_are_not_ambiguous():
    parsed = parse_whatsapp_chat(
        "05/05/2026, 10:00 - Alex: a\n"
        "05/05/2026, 10:05 - Sam: b\n"
    )

    assert (parsed.date_order_ambiguous, parsed.warnings) == (False, ())


@pytest.mark.parametrize(
    "override, first_date", [("month_first", (1, 2)), ("day_first", (2, 1))]
)
def test_override_decides_the_date_order(override, first_date):
    parsed = parse_whatsapp_chat(
        "01/02/2026, 10:00 - Alex: a\n01/03/2026, 10:00 - Sam: b", date_order=override
    )

    assert parsed.detected_date_order == override
    assert (parsed.messages[0].timestamp.month, parsed.messages[0].timestamp.day) == first_date
    assert (parsed.date_order_ambiguous, parsed.warnings) == (False, ())


def test_override_that_makes_a_date_impossible_skips_it_with_a_warning():
    parsed = parse_whatsapp_chat(
        "10/13/2026, 9:30 PM - Alex: hi\n"
        "its second line\n",
        date_order="day_first",
    )

    assert parsed.messages == ()
    assert parsed.skipped_line_count == 2
    [warning] = parsed.warnings
    assert "does not exist when read day first" in warning


def test_conflicting_dates_are_reported_not_silently_guessed():
    parsed = parse_whatsapp_chat(
        "13/01/2026, 10:00 - Alex: a\n"
        "01/13/2026, 10:00 - Sam: b\n"
    )

    assert [m.content for m in parsed.messages] == ["a"]
    assert parsed.date_order_ambiguous is True
    assert parsed.skipped_line_count == 1
    assert len(parsed.warnings) == 2


def test_invalid_override_is_rejected():
    with pytest.raises(ValueError, match="date_order"):
        parse_whatsapp_chat("", date_order="dmy")


# ---------- skipped lines ----------

def test_skipped_line_count_covers_every_kind_of_unused_line():
    parsed = parse_whatsapp_chat(
        "Exported chat\n"                         # skipped: before the first message
        "\n"                                      # blank: not counted
        "10/10/2026, 9:00 PM - Alex: hi\n"
        "still Alex\n"                            # continuation
        "10/10/2026, 9:01 PM - Sam left\n"        # system message
        "stray\n"                                 # skipped: after a system message
        "10/10/2026, 9:02 PM - : nobody\n"        # skipped: empty sender
        "10/10/2026, 25:00 - Sam: broken\n"       # skipped: impossible time
        "its continuation\n"                      # skipped: belongs to the broken entry
        "10/10/2026, 9:03 PM - Sam: back\n"
    )

    assert [(m.sender, m.content) for m in parsed.messages] == [
        ("Alex", "hi\nstill Alex"), (None, "Sam left"), ("Sam", "back"),
    ]
    assert parsed.skipped_line_count == 5
