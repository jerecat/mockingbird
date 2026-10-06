from mockingbird.adapter_utils import execution_path_refs, result_from_execution
from mockingbird.models import JobExecution


def _execution():
    return JobExecution("job-a", "start", "finish", 1.25, paths={"stdout": "out.log", "stderr": "err.log"})


def test_result_from_execution_carries_identity_and_refs():
    execution = _execution()
    result = result_from_execution(execution, "FAIL", artifacts=["artifact://opaque", "/some/path"])
    assert result.id == "job-a"
    assert result.duration_s == 1.25
    assert result.artifacts == ["artifact://opaque", "/some/path"]


def test_execution_path_refs_selects_present_refs():
    execution = _execution()
    assert execution_path_refs(execution, "stdout", "missing", "stderr") == ["out.log", "err.log"]
