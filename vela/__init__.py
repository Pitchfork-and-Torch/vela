"""VELA: Variance-aware Epoch Language for Adaptation."""

__version__ = "0.4.0"

from vela.ast import Program
from vela.parser import parse
from vela.checker import check
from vela.compile import compile_source

__all__ = ["Program", "parse", "check", "compile_source", "__version__"]
