"""Put `src` on the path once, so test modules can import at the top of the file.

Each test module used to do this itself, which meant every `from ideaos...`
import sat below a statement and tripped E402. A conftest runs before the
modules it sits beside, so the shim happens once and the imports move back to
where a reader expects them.

In an installed checkout this is a no-op — the package is already importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
