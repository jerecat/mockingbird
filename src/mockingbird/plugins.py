from __future__ import annotations

import importlib
import re
from typing import Any, TypeVar

from .contracts import CapacityProvider, ExecutionAdapter, SourceProvider

_PLUGIN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_T = TypeVar("_T")


def _load_class(category: str, spec: str, default_class: str, contract: type[_T]) -> type[_T]:
    """Resolve a built-in short name or an external ``module:Class`` plugin.

    Built-ins keep the compact YAML form, for example ``demo_linux``. Project
    integrations can live outside this repository and use an explicit import
    path such as ``my_verification.adapter:Adapter``.
    """

    if ":" in spec:
        module_name, class_name = spec.rsplit(":", 1)
        if not module_name or not class_name:
            raise ValueError(f"invalid external plugin specification: {spec!r}")
    else:
        if not _PLUGIN_NAME.fullmatch(spec):
            raise ValueError(
                f"invalid built-in plugin name {spec!r}; external plugins use module:Class"
            )
        module_name = f"mockingbird.{category}.{spec}"
        class_name = default_class

    module = importlib.import_module(module_name)
    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise RuntimeError(f"plugin {module_name} does not provide {class_name}") from exc

    if not isinstance(cls, type) or not issubclass(cls, contract):
        raise TypeError(
            f"plugin {spec!r} must provide a subclass of {contract.__name__}"
        )
    return cls


def load_adapter(name: str) -> ExecutionAdapter:
    cls = _load_class("adapters", name, "Adapter", ExecutionAdapter)
    return cls()


def load_capacity_provider(name: str, config: dict[str, Any]) -> CapacityProvider:
    cls = _load_class("capacity", name, "Provider", CapacityProvider)
    return cls(config)


def load_source_provider(name: str) -> SourceProvider:
    cls = _load_class("sources", name, "Provider", SourceProvider)
    return cls()
