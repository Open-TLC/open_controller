class SimLogger:
    def __init__(self, changes_only: bool) -> None:
        self.prevstatus: str = ""
        self.prevprint: int = 0
        self.changes_only = changes_only

    def log_status(self, status: str, steps: int, time: str) -> None:
        if self._should_log(status, steps):
            print(time + " " + status)
            self.prevprint = steps
        self.prevstatus = status

    def log(self, content: str) -> None:
        print(content)

    def _status_changed(self, new_status: str) -> bool:
        return self.prevstatus != new_status

    def _should_log(self, status: str, steps: int) -> bool:
        if self.changes_only and self._status_changed(status):
            return True
        if self._status_changed(status) or (steps - self.prevprint) > 10:
            return True
        return False
