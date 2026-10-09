"""Exception hierarchy.

Every expected failure is a subclass of :class:`TdmaError`, so the CLI can map
each category to a distinct exit status while genuine bugs still surface as
tracebacks instead of being swallowed.
"""


class TdmaError(Exception):
    """Base class for all expected, user-facing failures."""


class InputValidationError(TdmaError):
    """The coordinate input or a configuration value is malformed."""


class ScheduleValidationError(TdmaError):
    """A computed schedule violates the collision constraints.

    This should never happen; it exists so that a bug in the optimizer can never
    be reported as a successful, conflict-free schedule.
    """

    def __init__(self, message: str, errors: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.errors = errors
