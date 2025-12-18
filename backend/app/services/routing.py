# backend/app/services/routing.py

from __future__ import annotations

import os
from typing import Dict, Any


class RoutingError(RuntimeError):
    pass


def get_mapbox_token() -> str:
    token = (os.getenv("MAPBOX_ACCESS_TOKEN") or "").strip()
    if not token:
        raise RoutingError("MAPBOX_ACCESS_TOKEN is not set")
    return token