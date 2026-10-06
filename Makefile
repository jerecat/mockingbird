.PHONY: test architecture sanity self-demo external-demo clean

test:
	pytest

architecture:
	pytest -q tests/test_architecture_contracts.py tests/test_core_boundaries.py tests/test_core_isolation.py

sanity:
	reg all examples/sanity-linux.yaml

self-demo:
	reg all examples/self-host.yaml

external-demo:
	python -m pip install -e examples/external_adapter
	reg all examples/external-adapter.yaml

clean:
	rm -rf work runs work-self runs-self work-external runs-external .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
