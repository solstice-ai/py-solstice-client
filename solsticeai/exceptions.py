from typing import Dict, Optional


class LakesideError(BaseException):
    def __init__(self, msg):
        super().__init__(msg)


class LakesideCommsError(LakesideError):
    def __init__(self, msg: str,  status_code: int, error_payload: Optional[Dict[str, str]] = None):
        super().__init__(msg)
        self.status_code = status_code
        self.payload = error_payload
        if isinstance(self.payload, dict) and "error" in self.payload:
            # extract the "error" message from the payload, if it is provided in standard format
            self.payload = self.payload["error"]
