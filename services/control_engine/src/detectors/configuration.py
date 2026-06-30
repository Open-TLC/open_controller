from typing import Any


class AreaDetectorConfiguration:
    def __init__(self, conf: dict[str, Any]) -> None:
        self.type = conf["type"]
        self.id = conf["id"]
