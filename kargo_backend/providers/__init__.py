from .base import ProviderConfigError, ProviderError, RouteProvider

__all__ = [
    "GoogleRouteOptimizationProvider",
    "LocalOrtoolsProvider",
    "ProviderConfigError",
    "ProviderError",
    "RouteProvider",
]


def __getattr__(name: str):
    if name == "GoogleRouteOptimizationProvider":
        from .google import GoogleRouteOptimizationProvider

        return GoogleRouteOptimizationProvider
    if name == "LocalOrtoolsProvider":
        from .local import LocalOrtoolsProvider

        return LocalOrtoolsProvider
    raise AttributeError(name)
