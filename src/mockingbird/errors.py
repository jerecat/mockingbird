"""Actionable lifecycle preconditions, independent of CLI rendering."""


class PrerequisiteError(RuntimeError):
    def __init__(self, message: str, *steps: str):
        super().__init__(message)
        self.steps = steps
