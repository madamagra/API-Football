"""
Servicio de Sincronización de Ligas (Evolución de Script 001)
Recorre las 217 ligas de Seleccion.csv rotando tokens A-E y controlando el presupuesto de 7.500 llamadas.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from core.api_client import APIFootballClient
from core.quota_manager import QuotaManager

TEMPORADA = 2026
ESTADOS_FINALIZADOS = {"FT", "AET", "PEN"}
ESTADOS_PROXIMOS = {"NS", "TBD"}

CAMPOS_PARTIDO = [
    "fixture_id", "league_id", "league_name", "country", "season", "round", "date", "timezone",
    "status_long", "status_short", "elapsed", "venue_id", "venue_name", "referee", "home_id",
    "home_name", "home_winner", "away_id", "away_name", "away_winner", "goals_home", "goals_away",
    "halftime_home", "halftime_away", "fulltime_home", "fulltime_away", "extratime_home",
    "extratime_away", "penalty_home", "penalty_away", "periods_json", "score_json", "events_json",
    "lineups_json", "statistics_json", "odds_json", "last_update_utc",
]

class SyncService:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.dir_001 = self.data_dir / "001"
        self.dir_001.mkdir(parents=True, exist_ok=True)
        self.archivo_seleccion = base_dir / "Seleccion.csv"
        self.quota_mgr = QuotaManager(data_dir=self.data_dir)
        self.api_client = APIFootballClient(data_dir=self.data_dir, quota_manager=self.quota_mgr)
        self.control_file = self.dir_001 / "control_descargas.csv"
        self.ciclo_file = self.dir_001 / "estado_ciclo.json"

    def cargar_seleccion(self) -> List[Dict[str, str]]:
        if not self.archivo_seleccion.exists():
            raise FileNotFoundError(f"No se encuentra Seleccion.csv en {self.archivo_seleccion}")
        lineas = self.archivo_seleccion.read_text(encoding="utf-8-sig").splitlines()
        delimitador = ";" if lineas[0].count(";") >= lineas[0].count(",") else ","
        lector = csv.DictReader(lineas, delimiter=delimitador)
        ligas = []
        for fila in lector:
            lid = (fila.get("Id") or fila.get("id") or "").strip()
            num = (fila.get("Num_request") or "").strip()
            tok = (fila.get("token") or "A").strip().upper().replace("TOKEN_", "")
            if lid and num.isdigit():
                ligas.append({
                    "num_request": num,
                    "league_id": lid,
                    "league_name": (fila.get("name") or "").strip(),
                    "country": (fila.get("country") or "").strip(),
                    "token": tok,
                    "orden": (fila.get("orden") or "").strip(),
                })
        return sorted(ligas, key=lambda x: int(x["num_request"]))

    def sync_leagues(self, max_leagues: Optional[int] = None) -> Dict[str, Any]:
        """Sincroniza partidos de las ligas respetando el presupuesto de 7.500 llamadas."""
        ligas = self.cargar_seleccion()
        if max_leagues:
            ligas = ligas[:max_leagues]

        proximos: Dict[str, Dict[str, Any]] = {}
        total_finalizados_nuevos = 0
        ligas_procesadas = 0
        errores = []

        for liga in ligas:
            lid = liga["league_id"]
            tok = liga["token"]

            can_req, msg = self.quota_mgr.can_request(tok)
            if not can_req:
                errores.append(f"Cuota agotada al llegar a liga {lid}: {msg}")
                break

            archivo_liga = self.dir_001 / f"{lid}.csv"
            partidos_existentes = self._cargar_partidos(archivo_liga)

            try:
                data = self.api_client.request(
                    "fixtures",
                    {"league": lid, "season": TEMPORADA, "timezone": "UTC"},
                    token=tok
                )
                ligas_procesadas += 1

                for item in data.get("response", []):
                    status = str(((item.get("fixture") or {}).get("status") or {}).get("short", "")).upper()
                    if status in ESTADOS_FINALIZADOS:
                        partido = self._convertir_partido(item)
                        fid = str(partido["fixture_id"])
                        if fid not in partidos_existentes:
                            total_finalizados_nuevos += 1
                        partidos_existentes[fid] = partido
                    elif status in ESTADOS_PROXIMOS:
                        proximo = self._convertir_proximo(item, liga)
                        if proximo.get("fixture_id"):
                            proximos[str(proximo["fixture_id"])] = proximo

                self._guardar_partidos(archivo_liga, partidos_existentes)

            except Exception as err:
                errores.append(f"Error en liga {lid} ({liga['league_name']}): {err}")

        # Guardar próximos partidos
        archivo_prox = self.dir_001 / "001_proximos_partidos.csv"
        self._guardar_proximos(archivo_prox, list(proximos.values()))

        return {
            "ligas_procesadas": ligas_procesadas,
            "total_ligas": len(ligas),
            "finalizados_nuevos": total_finalizados_nuevos,
            "proximos_encontrados": len(proximos),
            "errores": errores,
            "cuota_actual": self.quota_mgr.get_summary()
        }

    def _cargar_partidos(self, ruta: Path) -> Dict[str, Dict[str, Any]]:
        if not ruta.exists():
            return {}
        try:
            lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
            if not lineas: return {}
            lector = csv.DictReader(lineas)
            return {row["fixture_id"]: row for row in lector if row.get("fixture_id")}
        except Exception:
            return {}

    def _guardar_partidos(self, ruta: Path, partidos: Dict[str, Dict[str, Any]]) -> None:
        with ruta.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CAMPOS_PARTIDO, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(partidos.values())

    def _guardar_proximos(self, ruta: Path, lista: List[Dict[str, Any]]) -> None:
        if not lista: return
        campos = list(lista[0].keys())
        with ruta.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=campos, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(lista)

    def _convertir_partido(self, item: Dict[str, Any]) -> Dict[str, Any]:
        f = item.get("fixture", {}) or {}
        l = item.get("league", {}) or {}
        t = item.get("teams", {}) or {}
        g = item.get("goals", {}) or {}
        s = item.get("score", {}) or {}
        st = f.get("status", {}) or {}
        v = f.get("venue", {}) or {}
        return {
            "fixture_id": f.get("id", ""),
            "league_id": l.get("id", ""),
            "league_name": l.get("name", ""),
            "country": l.get("country", ""),
            "season": l.get("season", TEMPORADA),
            "round": l.get("round", ""),
            "date": f.get("date", ""),
            "timezone": f.get("timezone", ""),
            "status_long": st.get("long", ""),
            "status_short": st.get("short", ""),
            "elapsed": st.get("elapsed", ""),
            "venue_id": v.get("id", ""),
            "venue_name": v.get("name", ""),
            "referee": f.get("referee", ""),
            "home_id": (t.get("home") or {}).get("id", ""),
            "home_name": (t.get("home") or {}).get("name", ""),
            "home_winner": (t.get("home") or {}).get("winner", ""),
            "away_id": (t.get("away") or {}).get("id", ""),
            "away_name": (t.get("away") or {}).get("name", ""),
            "away_winner": (t.get("away") or {}).get("winner", ""),
            "goals_home": g.get("home", ""),
            "goals_away": g.get("away", ""),
            "halftime_home": (s.get("halftime") or {}).get("home", ""),
            "halftime_away": (s.get("halftime") or {}).get("away", ""),
            "fulltime_home": (s.get("fulltime") or {}).get("home", ""),
            "fulltime_away": (s.get("fulltime") or {}).get("away", ""),
            "extratime_home": (s.get("extratime") or {}).get("home", ""),
            "extratime_away": (s.get("extratime") or {}).get("away", ""),
            "penalty_home": (s.get("penalty") or {}).get("home", ""),
            "penalty_away": (s.get("penalty") or {}).get("away", ""),
            "periods_json": json.dumps(s.get("periods", {}), ensure_ascii=False),
            "score_json": json.dumps(s, ensure_ascii=False),
            "events_json": "",
            "lineups_json": "",
            "statistics_json": "",
            "odds_json": "",
            "last_update_utc": datetime.now(timezone.utc).isoformat(),
        }

    def _convertir_proximo(self, item: Dict[str, Any], liga: Dict[str, str]) -> Dict[str, Any]:
        p = self._convertir_partido(item)
        return {
            "consulta_local": datetime.now().astimezone().isoformat(),
            "fixture_id": p["fixture_id"],
            "league_id": p["league_id"],
            "league_name": p["league_name"],
            "country": p["country"],
            "season": p["season"],
            "round": p["round"],
            "date_utc": p["date"],
            "timezone": p["timezone"],
            "status_short": p["status_short"],
            "status_long": p["status_long"],
            "venue_id": p["venue_id"],
            "venue_name": p["venue_name"],
            "referee": p["referee"],
            "home_id": p["home_id"],
            "home_name": p["home_name"],
            "away_id": p["away_id"],
            "away_name": p["away_name"],
            "token": liga["token"],
            "num_request": liga["num_request"],
            "orden": liga["orden"],
        }
