"""Download the MIMIC-IV demo patients across modalities from PhysioNet."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("Multi-MIMIC")   # set from the git tag when the package is built
except PackageNotFoundError:
    __version__ = "0.0.0"
