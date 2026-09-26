"""Trust service (TASKS §3.3): promote · update_after_run · check_drift."""
from app.trust.promote import promote, reject

__all__ = ["promote", "reject"]

try:  # trust ladder (P2.2.4) and drift watcher (P2.3.1) land separately
    from app.trust.ladder import update_after_run  # noqa: F401

    __all__.append("update_after_run")
except ImportError:
    pass
try:
    from app.trust.drift import check_drift  # noqa: F401

    __all__.append("check_drift")
except ImportError:
    pass
