"""Actionable lifecycle preconditions, independent of CLI rendering."""


class PrerequisiteError(RuntimeError):
    def __init__(self, message: str, *steps: str):
        super().__init__(message)
        self.steps = steps


class PlanChangedError(PrerequisiteError):
    def __init__(self):
        super().__init__("execution settings changed since plan; update the plan before run", "plan")
