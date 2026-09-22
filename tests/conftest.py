"""Keep pytest temporary files on the workspace in restricted Windows hosts."""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def pytest_configure(config: object) -> None:
    # Some managed Windows environments deny enumeration of the user's global
    # %TEMP%/pytest-of-<user> directory. Use a unique, ignored workspace path
    # unless the caller explicitly supplied --basetemp.
    option = getattr(config, "option")
    if getattr(option, "basetemp", None) is None:
        root = Path(__file__).resolve().parents[1]
        suffix = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        option.basetemp = str(root / f".pytest-tmp-run-{suffix}")
