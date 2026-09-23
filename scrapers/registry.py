import importlib
import pkgutil

from . import cinemas


def modules():
    """All cinema modules, sorted by module name."""
    out = []
    for info in sorted(pkgutil.iter_modules(cinemas.__path__), key=lambda i: i.name):
        out.append(importlib.import_module(f"{cinemas.__name__}.{info.name}"))
    return out


def by_id(cinema_id: str):
    for m in modules():
        if m.CINEMA.id == cinema_id:
            return m
    raise KeyError(cinema_id)
