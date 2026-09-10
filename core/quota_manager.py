"""
Gestor Central de Cuota y Presupuesto de API (Máx 7.500 llamadas/día)
Controla el consumo en tiempo real, sincroniza con /status (0 costo) y previene sobrecostes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

class QuotaManager:
    def __init__(self, data_dir: Path, daily_limit: int = 7500, margin: int = 50):
        self.data_dir = data_dir
        self.daily_limit = daily_limit
        self.margin = margin
        self.max_allowed = max(0, daily_limit - margin)
        self.consumo_file = data_dir / "consumo_diario_tokens.json"
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.consumo_file.exists():
            self._save_state(self._initial_state())

    def _get_today_date(self) -> str:
        return datetime.now().astimezone().date().isoformat()

    def _initial_state(self) -> Dict[str, Any]:
        return {
            "fecha_local": self._get_today_date(),
            "limite_configurado": self.daily_limit,
            "margen_seguridad": self.margin,
            "max_permitidas": self.max_allowed,
            "total_llamadas_hoy": 0,
            "tokens": {t: 0 for t in "ABCDE"},
            "api_server_reported": {
                t: {"current": 0, "limit_day": self.daily_limit, "updated_at": None}
                for t in "ABCDE"
            },
            "circuit_breaker_active": False,
            "last_request_utc": None
        }

    def load_state(self) -> Dict[str, Any]:
        hoy = self._get_today_date()
        try:
            if self.consumo_file.exists():
                datos = json.loads(self.consumo_file.read_text(encoding="utf-8"))
                if datos.get("fecha_local") == hoy:
                    return datos
        except Exception:
            pass
        nuevo = self._initial_state()
        self._save_state(nuevo)
        return nuevo

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.consumo_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def can_request(self, token: str = "A") -> Tuple[bool, str]:
        state = self.load_state()
        total = state.get("total_llamadas_hoy", 0)

        if total >= self.max_allowed:
            state["circuit_breaker_active"] = True
            self._save_state(state)
            return False, f"Límite diario alcanzado ({total}/{self.daily_limit} con margen {self.margin}). Circuito abierto."

        tok_count = state.get("tokens", {}).get(token, 0)
        # Si un token individual reportó agotamiento según la API
        rep = state.get("api_server_reported", {}).get(token, {})
        if rep.get("current", 0) >= rep.get("limit_day", self.daily_limit) and rep.get("limit_day", 0) > 0:
            return False, f"Token {token} reportó cupo agotado en API-Sports."

        return True, "OK"

    def record_request(self, token: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        state = self.load_state()
        state["total_llamadas_hoy"] = state.get("total_llamadas_hoy", 0) + 1
        state["tokens"][token] = state.get("tokens", {}).get(token, 0) + 1
        state["last_request_utc"] = datetime.now().astimezone().isoformat()

        if headers:
            rem = headers.get("x-ratelimit-requests-remaining") or headers.get("X-RateLimit-Remaining")
            lim = headers.get("x-ratelimit-requests-limit") or headers.get("X-RateLimit-Limit")
            if rem is not None and lim is not None:
                try:
                    remaining_int = int(rem)
                    limit_int = int(lim)
                    used = max(0, limit_int - remaining_int)
                    state["api_server_reported"][token] = {
                        "current": used,
                        "limit_day": limit_int,
                        "remaining": remaining_int,
                        "updated_at": state["last_request_utc"]
                    }
                except ValueError:
                    pass

        if state["total_llamadas_hoy"] >= self.max_allowed:
            state["circuit_breaker_active"] = True

        self._save_state(state)
        return state

    def update_from_status_api(self, token: str, status_response: Dict[str, Any]) -> None:
        """Actualiza el estado con la llamada gratuita a /status"""
        state = self.load_state()
        acc = (status_response.get("response") or {}).get("requests") or {}
        cur = int(acc.get("current", 0) or 0)
        lim = int(acc.get("limit_day", self.daily_limit) or self.daily_limit)
        state["api_server_reported"][token] = {
            "current": cur,
            "limit_day": lim,
            "remaining": max(0, lim - cur),
            "updated_at": datetime.now().astimezone().isoformat()
        }
        self._save_state(state)

    def get_summary(self) -> Dict[str, Any]:
        state = self.load_state()
        total = state.get("total_llamadas_hoy", 0)
        restantes = max(0, self.daily_limit - total)
        return {
            "fecha": state["fecha_local"],
            "total_hoy": total,
            "limite_diario": self.daily_limit,
            "restantes": restantes,
            "porcentaje_usado": round(total / self.daily_limit * 100, 2) if self.daily_limit else 0,
            "circuit_breaker": state.get("circuit_breaker_active", False),
            "consumo_tokens": state.get("tokens", {}),
            "api_reported": state.get("api_server_reported", {})
        }
