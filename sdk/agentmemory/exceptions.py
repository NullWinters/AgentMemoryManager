class MemoryServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}
