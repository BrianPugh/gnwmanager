from datetime import datetime, timezone


def timestamp_now() -> int:
    return int(round(datetime.now().replace(tzinfo=timezone.utc).timestamp()))
