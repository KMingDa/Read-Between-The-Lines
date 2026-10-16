
from pathlib import Path
from datetime import datetime


def parse_chat_file(file_path):
    try:
        content = file_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print("File not found!")
        return []

    if not content:
        return []

    messages = content.splitlines()
    parsed_messages = []

    for message in messages:
        parts = message.split(" - ", 1)

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

        message_details = parts[1]
        sender_and_content = message_details.split(": ", 1)

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

    return parsed_messages




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

        # Only measure when the other person replies to the user.
        if current_sender.strip().casefold() == user_name.strip().casefold():
            reply_minutes = (
                timestamp - last_message_time
            ).total_seconds() / 60

            if reply_minutes >= 0:
                reply_times.append(reply_minutes)

                reply_details.append({
                    "from": current_sender,
                    "to": sender,
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




file_path = Path("data/synthetic/whatsapp_invalid_sample.txt")
parsed_messages = parse_chat_file(file_path)

if not parsed_messages:
    print("No valid messages to analyze.")
else:
    print("Parsed messages:")

    for message in parsed_messages:
        print(
            message["timestamp"],
            "|",
            message["sender"],
            "|",
            message["content"]
        )

    results = analyze_reply_intervals(parsed_messages)

    print("\nMessage intervals:")

    if results["reply_details"]:
        for detail in results["reply_details"]:
            print(
                detail["to"],
                "after",
                detail["from"],
                ":",
                detail["minutes"],
                "minutes"
            )
    else:
        print("No intervals between different senders.")

    print("\nAll intervals:", results["reply_times"])

    if results["average_reply_time"] is not None:
        print(
            "Average interval:",
            round(results["average_reply_time"], 2),
            "minutes"
        )
    else:
        print("Average interval unavailable.")
