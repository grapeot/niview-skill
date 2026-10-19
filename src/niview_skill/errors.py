class NiViewError(Exception):
    def __init__(self, code: int | None, msg: str, http_status: int | None = None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.http_status = http_status

    def as_dict(self) -> dict:
        return {"http_status": self.http_status, "code": self.code, "msg": self.msg}


class AuthError(NiViewError):
    """The token is missing or rejected by the server."""
