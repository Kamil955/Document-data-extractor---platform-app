import enum


class RunResult(enum.Enum):
    """What one pass of the worker did; the loop decides from it how long to sleep."""

    IDLE = "idle"  # nothing to do
    PROCESSED = "processed"  # one job finished (successfully or recorded as failed)
    DEFERRED = "deferred"  # a model service is down: the job was put back in the queue
