from datetime import datetime
from pathlib import Path

import pytest

from app.domain.entities import Message, ReplyInterval, ReplyIntervalAnalysis
from app.domain.metrics import analyze_reply_intervals
from app.domain.parsing.whatsapp import parse_whatsapp_chat

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"

# Jamie double-texts, Taylor replies 10 min after Jamie's LAST message,
# Jamie replies, Taylor replies 30 min later.
CHAT = """\
10/10/2026, 9:00 AM - Jamie: Hi
10/10/2026, 9:05 AM - Jamie: You there?
10/10/2026, 9:15 AM - Taylor: Yes!
10/10/2026, 9:20 AM - Jamie: Great
10/10/2026, 9:50 AM - Taylor: Sorry, busy
"""

NO_INTERVALS = ReplyIntervalAnalysis(intervals=(), average_minutes=None)


def chat(text):
    return parse_whatsapp_chat(text).messages


def minutes(analysis):
    return [interval.minutes for interval in analysis.intervals]


def test_system_messages_between_turns_are_ignored():
    messages = [
        Message(timestamp=datetime(2026, 1, 1, 10, 0), sender="Jamie", content="hi"),
        Message(timestamp=datetime(2026, 1, 1, 10, 1), sender=None, content="Taylor joined"),
        Message(timestamp=datetime(2026, 1, 1, 10, 4), sender="Taylor", content="hey"),
    ]

    result = analyze_reply_intervals(messages, "Jamie")

    assert result.intervals == (ReplyInterval(replier="Taylor", replied_to="Jamie", minutes=4.0),)


def test_empty_messages_return_no_intervals():
    assert analyze_reply_intervals([], "Jamie") == NO_INTERVALS


def test_measures_other_persons_replies_to_the_user():
    result = analyze_reply_intervals(chat(CHAT), "Jamie")

    assert result == ReplyIntervalAnalysis(
        intervals=(
            ReplyInterval(replier="Taylor", replied_to="Jamie", minutes=10.0),
            ReplyInterval(replier="Taylor", replied_to="Jamie", minutes=30.0),
        ),
        average_minutes=20.0,
    )


def test_reply_is_timed_from_users_last_message_in_a_burst():
    # Jamie wrote at 9:00 and 9:05; Taylor's 9:15 reply counts as 10 min, not 15.
    result = analyze_reply_intervals(chat(CHAT), "Jamie")

    assert minutes(result)[0] == 10.0


def test_burst_from_the_other_person_counts_once():
    messages = chat(
        "10/10/2026, 9:00 AM - Jamie: hi\n"
        "10/10/2026, 9:04 AM - Taylor: hey\n"
        "10/10/2026, 9:06 AM - Taylor: sorry\n"
        "10/10/2026, 9:07 AM - Taylor: was driving\n"
    )

    assert minutes(analyze_reply_intervals(messages, "Jamie")) == [4.0]


def test_users_own_replies_are_not_counted():
    result = analyze_reply_intervals(chat(CHAT), "Taylor")

    assert result.intervals == (ReplyInterval(replier="Jamie", replied_to="Taylor", minutes=5.0),)
    assert result.average_minutes == 5.0


@pytest.mark.parametrize("user_name", ["jamie", "  JAMIE  "])
def test_user_name_match_ignores_case_and_surrounding_spaces(user_name):
    result = analyze_reply_intervals(chat(CHAT), user_name)

    assert minutes(result) == [10.0, 30.0]


@pytest.mark.parametrize("user_name", ["Jamie Lee", "Jam", "", "   "])
def test_unknown_or_blank_user_name_gives_no_intervals(user_name):
    assert analyze_reply_intervals(chat(CHAT), user_name) == NO_INTERVALS


def test_reply_across_midnight():
    messages = chat(
        "10/10/2026, 11:59 PM - Jamie: night\n"
        "11/10/2026, 12:01 AM - Taylor: still up\n"
    )

    assert minutes(analyze_reply_intervals(messages, "Jamie")) == [2.0]


def test_same_minute_reply_counts_as_zero():
    messages = chat(
        "10/10/2026, 9:00 AM - Jamie: hi\n"
        "10/10/2026, 9:00 AM - Taylor: hi\n"
    )

    assert minutes(analyze_reply_intervals(messages, "Jamie")) == [0.0]


def test_unsorted_input_is_sorted_before_measuring():
    messages = list(reversed(chat(CHAT)))

    assert minutes(analyze_reply_intervals(messages, "Jamie")) == [10.0, 30.0]


def test_multiline_messages_do_not_change_intervals():
    messages = chat(
        "10/10/2026, 9:00 AM - Jamie: line one\n"
        "line two\n"
        "10/10/2026, 9:07 AM - Taylor: reply\n"
        "more reply\n"
    )

    assert minutes(analyze_reply_intervals(messages, "Jamie")) == [7.0]


def test_out_of_order_sample_file():
    text = (DATA_DIR / "whatsapp_invalid_sample.txt").read_text(encoding="utf-8")

    result = analyze_reply_intervals(chat(text), "Jamie")

    # Sorted: Jamie 2:00, 2:01, 2:02 | Taylor 2:06, 2:08 | Jamie 2:10
    assert result.intervals == (ReplyInterval(replier="Taylor", replied_to="Jamie", minutes=4.0),)


def test_works_on_messages_built_without_the_parser():
    messages = [
        Message(timestamp=datetime(2026, 1, 1, 10, 0), sender="Jamie", content="a"),
        Message(timestamp=datetime(2026, 1, 1, 10, 3), sender="Taylor", content="b"),
    ]

    assert minutes(analyze_reply_intervals(messages, "Jamie")) == [3.0]
