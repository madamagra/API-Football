"""
Cliente HTTP para API-Football v3 (api-sports.io)
Gestiona rotación de tokens A-E, reintentos con backoff, rate limiting y control de cuota.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.quota_manager import QuotaManager

BASE_URL = "https://v3.football.api-sports.io"

class APIFootballClient:
    def __init__(self, data_dir: Path, quota_manager: Optional[QuotaManager] = None):
        self.data_dir = data_dir
        self.quota_mgr = quota_manager or QuotaManager(data_dir=data_dir)
        self.session = self._create_session()
        self.timeout = 30
        self.pause = 0.25

    def _create_session(self) -> requests.Session:
        retries = Retry(
            total=3,
            backoff_factor=1.2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False
        )
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=retries))
        return session

    def get_token_key(self, token: str) -> str:
        t = token.upper().replace("TOKEN_", "").strip()
        key = os.getenv(f"TOKEN_{t}", "").strip()
        if not key:
            # Fallback a clave única si el usuario tiene una sola
            key = os.getenv("SPORTS_API_KEY", "").strip() or os.getenv("API_KEY", "").strip()
        return key

    def get_status(self, token: str = "A") -> Dict[str, Any]:
        """Consulta /status (no cuenta contra la cuota diaria)."""
        key = self.get_token_key(token)
        if not key or key == "tu_token_aqui":
            return {"status": "unconfigured", "error": "Token no configurado en .env"}

        try:
            resp = self.session.get(
                f"{BASE_URL}/status",
                headers={"x-apisports-key": key},
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("response"):
                self.quota_mgr.update_from_status_api(token, data)
            return data
        except Exception as err:
            return {"status": "error", "error": str(err)}

    def request(self, endpoint: str, params: Dict[str, Any], token: str = "A") -> Dict[str, Any]:
        """Realiza una petición a la API verificando antes el cupo."""
        # 1. Comprobar cuota
        can_proceed, reason = self.quota_mgr.can_request(token)
        if not can_proceed:
            raise RuntimeError(f"PETICION BLOQUEADA POR CUOTA: {reason}")

        key = self.get_token_key(token)
        if not key or key == "tu_token_aqui":
            raise ValueError(f"TOKEN_{token} no está configurado en .env")

        resp = self.session.get(
            f"{BASE_URL}/{endpoint}",
            params=params,
            headers={"x-apisports-key": key},
            timeout=self.timeout
        )

        # 2. Registrar consumo en QuotaManager
        self.quota_mgr.record_request(token, dict(resp.headers))
        time.sleep(self.pause)

        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")

        data = resp.json()
        if data.get("errors"):
            # Si la API reporta errores de quota o bloqueo
            err_str = json.dumps(data["errors"], ensure_ascii=False)
            if "quota" in err_str.casefold() or "rate" in err_str.casefold():
                self.quota_mgr.record_request(token)
            raise RuntimeError(f"Error devuelto por API-Sports: {err_str}")

        return data
