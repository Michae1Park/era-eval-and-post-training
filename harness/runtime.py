import threading
import time
import traceback
from dataclasses import dataclass, field

INFRA_ERRORS = ("APIConnectionError", "APITimeoutError", "InternalServerError", "RateLimitError",
                "ConnectError", "ReadTimeout", "RemoteProtocolError", "ServiceUnavailableError")
AGENT_STATUSES = ("ok", "agent_error", "timeout")


class TaskTimeout(BaseException):
    pass


class TaskCancelled(BaseException):
    pass


cancel_all = threading.Event()
_local = threading.local()


@dataclass
class Guard:
    deadline: float
    started: float = field(default_factory=time.monotonic)

    def check(self) -> None:
        if cancel_all.is_set():
            raise TaskCancelled
        if time.monotonic() > self.deadline:
            raise TaskTimeout


def check() -> None:
    guard = getattr(_local, "guard", None)
    if guard:
        guard.check()


def guarded(fn):
    def wrapper(*args, **kwargs):
        check()
        result = fn(*args, **kwargs)
        check()
        return result

    return wrapper


def classify(error: BaseException) -> str:
    if isinstance(error, TaskTimeout):
        return "timeout"
    names = {type(e).__name__ for e in _chain(error)}
    if names & set(INFRA_ERRORS):
        return "infra_error"
    frames = traceback.extract_tb(error.__traceback__)
    deepest = frames[-1].filename if frames else ""
    return "agent_error" if "era_agent" in deepest else "harness_error"


def _chain(error: BaseException):
    while error is not None:
        yield error
        error = error.__cause__ or error.__context__


def execute(agent, task: dict, sample: int, timeout: float, retries: int, backoff: float) -> dict:
    record = {"task_id": task["id"], "sample": sample, "mode": task["mode"], "as_of": task["as_of"],
              "split": task["split"], "attempts": 0}
    started = time.perf_counter()
    for attempt in range(retries + 1):
        record["attempts"] = attempt + 1
        _local.guard = Guard(time.monotonic() + timeout)
        try:
            record |= agent.run(task) | {"status": "ok"}
            record.pop("error", None)
            break
        except TaskCancelled:
            raise
        except BaseException as e:  # noqa: BLE001
            status = classify(e)
            record |= {"status": status, "error": f"{type(e).__name__}: {e}"[:2000]}
            if status != "infra_error" or attempt == retries:
                break
            time.sleep(backoff * 2 ** attempt)
        finally:
            _local.guard = None
    record["seconds"] = round(time.perf_counter() - started, 2)
    steps = record.get("steps") or []
    record["tokens"] = {"input": sum(s.get("input_tokens") or 0 for s in steps),
                        "output": sum(s.get("output_tokens") or 0 for s in steps)}
    return record
