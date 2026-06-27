from __future__ import annotations

import threading

# Inprocess pause/cancel control for running download jobs


class JobCancelled(Exception):
    """Raised inside the worker when a job is cancelled at a checkpoint."""


class JobControl:
    def __init__(self) -> None:
        self._cancel = threading.Event()
        # set = running; cleared = paused Starts running
        self._resume = threading.Event()
        self._resume.set()

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def cancel(self) -> None:
        self._cancel.set()

        # unblock a paused worker
        self._resume.set()  
    def checkpoint(self) -> None:
        """Block while paused, then raise ``JobCancelled`` if cancelled."""
        self._resume.wait()
        if self._cancel.is_set():
            raise JobCancelled()


_registry: dict[str, JobControl] = {}
_lock = threading.Lock()


def register(job_id: str) -> JobControl:
    control = JobControl()
    with _lock:
        _registry[job_id] = control
    return control


def get(job_id: str) -> JobControl | None:
    with _lock:
        return _registry.get(job_id)


def discard(job_id: str) -> None:
    with _lock:
        _registry.pop(job_id, None)


def cancel_all() -> None:
    #on shutdown, unblock every live worker
    with _lock:
        controls = list(_registry.values())
    for control in controls:
        control.cancel()
