
from datetime import datetime


def parse_chat_text(conversation: str):
    parsed_messages = []

    for line in conversation.splitlines():
        parts = line.split(" - ", 1)

        if len(parts) != 2:
            continue

        timestamp_text = parts[0].strip()

        try:
            timestamp = datetime.strptime(
                timestamp_text,
                "%d/%m/%Y, %I:%M %p"
            )
        except ValueError:
            continue

        sender_and_content = parts[1].split(": ", 1)

        if len(sender_and_content) != 2:
            continue

        sender = sender_and_content[0].strip()
        message_content = sender_and_content[1].strip()

        if not sender or not message_content:
            continue

        parsed_messages.append({
            "timestamp": timestamp,
            "sender": sender,
            "content": message_content
        })

    return sorted(
        parsed_messages,
        key=lambda message: message["timestamp"]
    )



def analyze_reply_intervals(parsed_messages, user_name):
    reply_times = []
    reply_details = []

    if not parsed_messages:
        return {
            "reply_details": [],
            "reply_times": [],
            "average_reply_time": None
        }

    parsed_messages = sorted(
        parsed_messages,
        key=lambda message: message["timestamp"]
    )

    current_sender = parsed_messages[0]["sender"]
    last_message_time = parsed_messages[0]["timestamp"]

    for message in parsed_messages[1:]:
        sender = message["sender"]
        timestamp = message["timestamp"]

        if sender == current_sender:
            last_message_time = timestamp
            continue

        # Only calculate when the other person replies to you.
        if current_sender.strip().casefold() == user_name.strip().casefold():
            reply_minutes = (
                timestamp - last_message_time
            ).total_seconds() / 60

            if reply_minutes >= 0:
                reply_times.append(reply_minutes)

                reply_details.append({
                    "from": sender,
                    "to": current_sender,
                    "minutes": reply_minutes
                })

        current_sender = sender
        last_message_time = timestamp

    average_reply_time = (
        sum(reply_times) / len(reply_times)
        if reply_times
        else None
    )

    return {
        "reply_details": reply_details,
        "reply_times": reply_times,
        "average_reply_time": average_reply_time
    }

