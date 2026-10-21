"""Fail the build when a new `except` swallows an error without logging it.

Silent handlers are how Android push stayed broken for three months and how the
Karekope/Kemps duplicate miss became unexplainable: the failure path and the success
path produce byte-identical output, so nothing is measurable after the fact.

A handler passes if it logs, re-raises, carries a `# silent-ok: <reason>` comment on its
`except` line (for handlers that collect failures and log them once after a loop), or is
listed in ALLOWED below with a reason.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

_LOG_METHODS = {"exception", "error", "warning", "warn", "critical", "info"}

# Handlers that are control flow rather than error suppression, or that record a queryable
# trace in the DB instead of a log line (see "Error handling" in CLAUDE.md).
ALLOWED = {
    ("api/users.py", "HTTPException"): "optional-auth dependency: an invalid token legitimately means 'no user'",
    ("services/notifications.py", "DeviceNotRegisteredError"): "writes PushDeliveryTicket.status='failed'",
    ("services/notifications.py", "PushTicketError"): "writes PushDeliveryTicket.status='failed'",
    ("services/receipts.py", "DeviceNotRegisteredError"): "writes row.status='failed'",
    ("services/receipts.py", "PushTicketError"): "writes row.status='failed'",
}


def _handles_visibly(handler: ast.ExceptHandler) -> bool:
    module = ast.Module(body=handler.body, type_ignores=[])
    for node in ast.walk(module):
        if isinstance(node, ast.Raise):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_METHODS
        ):
            return True
    return False


def test_no_exception_handler_swallows_silently():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        source = path.read_text()
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ExceptHandler) or _handles_visibly(node):
                continue
            if "silent-ok:" in lines[node.lineno - 1]:
                continue
            exc = ast.unparse(node.type) if node.type else "bare except"
            if (rel, exc) in ALLOWED:
                continue
            offenders.append(f"src/{rel}:{node.lineno} except {exc}")

    assert not offenders, (
        "These handlers neither log nor re-raise. Add logger.exception(...), or add an entry to "
        "ALLOWED in this file with the reason:\n  " + "\n  ".join(offenders)
    )
