from .config import Settings, load_settings

__all__ = ["RoutingOrchestrator", "Settings", "load_settings"]


def __getattr__(name: str):
    if name == "RoutingOrchestrator":
        from .service import RoutingOrchestrator

        return RoutingOrchestrator
    raise AttributeError(name)
