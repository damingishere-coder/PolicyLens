"""Keep restore exclusive with requests and background external operations."""

import threading
from contextlib import contextmanager

from .service import ConflictError


class RuntimeGate:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests = 0
        self._external = False
        self._restoring = False

    @contextmanager
    def request(self, restoring=False):
        with self._lock:
            if self._restoring or (restoring and (self._requests or self._external)):
                raise ConflictError(
                    "当前仍有读取、保存或 AI／研究任务，请等待完成后再恢复备份；本次未切换数据。"
                )
            self._restoring = restoring
            self._requests += 1
        try:
            yield
        finally:
            with self._lock:
                self._requests -= 1
                if restoring:
                    self._restoring = False

    def begin_external(self):
        with self._lock:
            if self._restoring or self._external:
                raise ConflictError("已有 AI／研究任务或备份恢复正在进行；本次未开始新调用。")
            self._external = True

    def end_external(self):
        with self._lock:
            self._external = False

    @contextmanager
    def external(self):
        self.begin_external()
        try:
            yield
        finally:
            self.end_external()
