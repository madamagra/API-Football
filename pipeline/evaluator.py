"""
Evaluador de Aciertos y Balances (Evolución de Scripts 200 y 401)
Comprueba el resultado real de las apuestas propuestas contra los CSVs de ligas finalizadas.
Calcula ROI, PnL, tasa de acierto y estadísticas por liga y lista Martingala.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

TZ_ESPANA = ZoneInfo("Europe/Madrid")
ESTADOS_FINALIZADOS = {"FT", "AET", "PEN"}

class BetEvaluator:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.dir_001 = self.data_dir / "001"
        self.dir_003 = self.data_dir / "003"
        self.dir_200 = self.data_dir / "200"
        self.dir_200.mkdir(parents=True, exist_ok=True)

    def evaluate_proposals(self, proposals_file: Optional[Path] = None, stake_per_bet: float = 1.0) -> Dict[str, Any]:
        if proposals_file is None:
            proposals_file = self.dir_003 / "003_empates_seleccionados.csv"

        if not proposals_file.exists():
            return {"status": "no_proposals", "mensaje": f"No existe el archivo de propuestas {proposals_file.name}"}

        propuestas = self._leer_csv(proposals_file)
        indice_resultados = self._cargar_resultados_ligas()

        filas_balance = []
        total_evaluados = 0
        aciertos_directos = 0
        aciertos_pido = 0
        pendientes = 0
        sin_datos = 0

        staked_direct = 0.0
        ret_direct = 0.0
        staked_pido = 0.0
        ret_pido = 0.0

        for p in propuestas:
            fid = str(p.get("fixture_id", "")).strip()
            real = indice_resultados.get(fid)

            # Extraer cuotas
            cx = self._to_float(p.get("cuota_x_num") or p.get("cuota_x"), 3.20)
            q_pido = self._to_float(p.get("pido_cuota_efectiva"), 1.25)
            pick_base = p.get("pido_pick_base", "1")

            if real is None:
                estado_partido = "Pendiente / Sin datos"
                resultado_real = "?"
                es_empate_real = None
                pido_acertado = None
                sin_datos += 1
            else:
                st = real.get("status_short", "")
                if st not in ESTADOS_FINALIZADOS:
                    estado_partido = f"Pendiente ({st})"
                    resultado_real = "?"
                    es_empate_real = None
                    pido_acertado = None
                    pendientes += 1
                else:
                    gh = int(real.get("goals_home", 0) or 0)
                    ga = int(real.get("goals_away", 0) or 0)
                    resultado_real = "1" if gh > ga else ("X" if gh == ga else "2")
                    es_empate_real = (resultado_real == "X")
                    pido_acertado = (resultado_real == pick_base or es_empate_real)

                    total_evaluados += 1
                    # Empate Directo
                    staked_direct += stake_per_bet
                    if es_empate_real:
                        aciertos_directos += 1
                        ret_direct += stake_per_bet * cx

                    # PIDO
                    staked_pido += stake_per_bet
                    if pido_acertado:
                        aciertos_pido += 1
                        ret_pido += stake_per_bet * q_pido

            filas_balance.append({
                "fixture_id": fid,
                "league_name": p.get("league_name", ""),
                "local": p.get("home_name", ""),
                "visitante": p.get("away_name", ""),
                "cuota_x": cx,
                "cuota_pido_efectiva": q_pido,
                "resultado_real": resultado_real,
                "empate_acertado": "ACERTADO" if es_empate_real is True else ("FALLADO" if es_empate_real is False else "PENDIENTE"),
                "pido_acertado": "ACERTADO" if pido_acertado is True else ("FALLADO" if pido_acertado is False else "PENDIENTE"),
                "vias": p.get("vias_activas", "")
            })

        # Guardar en data/200
        hoy = datetime.now(TZ_ESPANA).date().isoformat()
        archivo_balance = self.dir_200 / f"200_balance_partidos_{hoy}.csv"
        self._guardar_csv(archivo_balance, filas_balance)

        pnl_direct = ret_direct - staked_direct
        roi_direct = (pnl_direct / staked_direct * 100) if staked_direct > 0 else 0.0
        pnl_pido = ret_pido - staked_pido
        roi_pido = (pnl_pido / staked_pido * 100) if staked_pido > 0 else 0.0

        return {
            "total_propuestas": len(propuestas),
            "finalizados_evaluados": total_evaluados,
            "pendientes": pendientes,
            "sin_datos": sin_datos,
            "estrategia_empate_directo": {
                "aciertos": aciertos_directos,
                "tasa_acierto_pct": round(aciertos_directos / total_evaluados * 100, 2) if total_evaluados else 0,
                "staked": round(staked_direct, 2),
                "returned": round(ret_direct, 2),
                "pnl": round(pnl_direct, 2),
                "roi_pct": round(roi_direct, 2)
            },
            "estrategia_pido_doble_oportunidad": {
                "aciertos": aciertos_pido,
                "tasa_acierto_pct": round(aciertos_pido / total_evaluados * 100, 2) if total_evaluados else 0,
                "staked": round(staked_pido, 2),
                "returned": round(ret_pido, 2),
                "pnl": round(pnl_pido, 2),
                "roi_pct": round(roi_pido, 2)
            },
            "archivo_balance": str(archivo_balance)
        }

    def _cargar_resultados_ligas(self) -> Dict[str, Dict[str, Any]]:
        indice = {}
        for r in self.dir_001.glob("*.csv"):
            if "proximos" in r.name: continue
            try:
                lineas = r.read_text(encoding="utf-8-sig").splitlines()
                if not lineas: continue
                lector = csv.DictReader(lineas)
                for row in lector:
                    fid = str(row.get("fixture_id", "")).strip()
                    if fid:
                        indice[fid] = row
            except Exception:
                continue
        return indice

    def _to_float(self, val: Any, default: float = 0.0) -> float:
        try:
            if val is None: return default
            return float(str(val).replace(",", ".").strip())
        except ValueError:
            return default

    def _leer_csv(self, ruta: Path) -> List[Dict[str, str]]:
        lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
        if not lineas: return []
        delimitador = ";" if lineas[0].count(";") >= lineas[0].count(",") else ","
        lector = csv.DictReader(lineas, delimiter=delimitador)
        return [dict(r) for r in lector]

    def _guardar_csv(self, ruta: Path, lista: List[Dict[str, Any]]) -> None:
        if not lista: return
        campos = list(lista[0].keys())
        with ruta.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=campos, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(lista)
