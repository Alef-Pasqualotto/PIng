import json
import queue
import threading
from collections import defaultdict

from logging_config import get_logger


logger = get_logger("attendance_events")
_lock = threading.Lock()
_subscribers: dict[int, set[queue.Queue]] = defaultdict(set)


def subscribe(session_id: int) -> queue.Queue:
    subscriber = queue.Queue(maxsize=20)
    with _lock:
        _subscribers[session_id].add(subscriber)
    logger.info("Attendance event subscriber added: session=%s count=%s", session_id, subscriber_count(session_id))
    return subscriber


def unsubscribe(session_id: int, subscriber: queue.Queue) -> None:
    with _lock:
        subscribers = _subscribers.get(session_id)
        if not subscribers:
            return
        subscribers.discard(subscriber)
        if not subscribers:
            _subscribers.pop(session_id, None)
    logger.info("Attendance event subscriber removed: session=%s", session_id)


def publish(session_id: int, event_type: str = "roster_changed") -> None:
    payload = json.dumps({"type": event_type, "session_id": session_id})
    with _lock:
        subscribers = list(_subscribers.get(session_id, ()))
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(payload)
        except queue.Full:
            logger.warning("Dropping attendance event for slow subscriber: session=%s", session_id)
    logger.debug("Attendance event published: session=%s type=%s subscribers=%s", session_id, event_type, len(subscribers))


def subscriber_count(session_id: int) -> int:
    with _lock:
        return len(_subscribers.get(session_id, ()))
