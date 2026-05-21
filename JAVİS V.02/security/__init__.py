"""
security package — public API layer.

Dışarıya sadece bu __init__.py üzerinden erişilir.
Internal modüller (owner.py) doğrudan import edilebilir ama
önerilen yol paket API'sidir.

Kullanım örnekleri:
    from security import set_owner_pin          # önerilen
    from security import verify_owner_pin
    from security import has_owner_pin
    from security.owner import set_owner_pin    # direkt submodule da geçerli
"""

from __future__ import annotations

from security.owner import (
    has_owner_pin,
    set_owner_pin,
    verify_owner_pin,
)

__all__ = [
    "has_owner_pin",
    "set_owner_pin",
    "verify_owner_pin",
]