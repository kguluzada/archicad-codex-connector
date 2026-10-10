"""Errors returned through both CLI and MCP without discarding native details."""


class ConnectorError(Exception):
    def __init__(self, code, message, *, details=None, outcome_unknown=False):
        super().__init__(message)
        self.code = code
        self.details = details
        self.outcome_unknown = outcome_unknown

    def as_dict(self):
        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "outcome_unknown": self.outcome_unknown,
        }
