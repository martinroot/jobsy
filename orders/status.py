"""Order status transitions for jobsy."""

NEW = "new"
ASSIGNED = "assigned"
RUNNING = "running"
NEEDINFO = "needinfo"
DONE = "done"
FAILED = "failed"
BLOCKED = "blocked"
PAYMENT_FAILED = "payment_failed"

TERMINAL = {DONE, FAILED, PAYMENT_FAILED}

ACTIVE_TRANSITIONS = {
    NEW: [ASSIGNED],
    ASSIGNED: [RUNNING, NEEDINFO, FAILED],
    RUNNING: [NEEDINFO, DONE, FAILED, BLOCKED],
    NEEDINFO: [RUNNING, FAILED, BLOCKED],
    BLOCKED: [RUNNING, FAILED],
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ACTIVE_TRANSITIONS.get(from_status, [])


def is_terminal(status: str) -> bool:
    return status in TERMINAL
