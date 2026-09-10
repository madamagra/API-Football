"""
Enriquecedor de Partidos Próximos (Evolución de Script 002)
Descarga cuotas (odds), predicciones de API-Football y calcula los modelos del PFC (J48 y Bayes Net).
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.api_client import APIFootballClient
from core.classifiers_pfc import PFCEnsemblePredictor
from core.quota_manager import QuotaManager

VENTANA_HORAS = 72

class FixtureEnricher:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.dir_001 = self.data_dir / "001"
        self.dir_002 = self.data_dir / "002"
        self.dir_002.mkdir(parents=True, exist_ok=True)
        self.quota_mgr = QuotaManager(data_dir=self.data_dir)
        self.api_client = APIFootballClient(data_dir=self.data_dir, quota_manager=self.quota_mgr)
        self.pfc_engine = PFCEnsemblePredictor()

    def enrich_upcoming(self, max_matches: Optional[int] = None) -> Dict[str, Any]:
        archivo_prox = self.dir_001 / "001_proximos_partidos.csv"
        if not archivo_prox.exists():
            return {"status": "no_data", "mensaje": "No se ha encontrado 001_proximos_partidos.csv. Ejecuta primero la sincronización."}

        partidos = self._leer_csv(archivo_prox)
        ahora = datetime.now(timezone.utc)
        limite = ahora + timedelta(hours=VENTANA_HORAS)

        candidatos = []
        for p in partidos:
            try:
                f_dt = datetime.fromisoformat(str(p.get("date_utc", "")).replace("Z", "+00:00"))
                if ahora <= f_dt <= limite:
                    candidatos.append(p)
            except Exception:
                continue

        if max_matches:
            candidatos = candidatos[:max_matches]

        enriquecidos = []
        mercados = []
        errores = []

        for p in candidatos:
            fid = str(p.get("fixture_id", ""))
            tok = p.get("token", "A")

            can_req, msg = self.quota_mgr.can_request(tok)
            if not can_req:
                errores.append(f"Cuota agotada al enriquecer fixture {fid}: {msg}")
                break

            fila = dict(p)
            cuota_l, cuota_x, cuota_v = 2.00, 3.20, 3.50  # Defaults si no hay cuotas
            cuota_u25 = 1.90

            try:
                # 1. Petición de Odds
                odds_data = self.api_client.request("odds", {"fixture": fid}, token=tok)
                res_odds, filas_m = self._parse_odds(odds_data, fila)
                fila.update(res_odds)
                mercados.extend(filas_m)
                if fila.get("cuota_1"): cuota_l = float(fila["cuota_1"])
                if fila.get("cuota_x"): cuota_x = float(fila["cuota_x"])
                if fila.get("cuota_2"): cuota_v = float(fila["cuota_2"])
                if fila.get("cuota_under_2_5"): cuota_u25 = float(fila["cuota_under_2_5"])
            except Exception as e:
                errores.append(f"Odds fixture {fid}: {e}")

            try:
                # 2. Petición de Predictions API-Football
                pred_data = self.api_client.request("predictions", {"fixture": fid}, token=tok)
                fila.update(self._parse_prediction(pred_data))
            except Exception as e:
                errores.append(f"Predictions fixture {fid}: {e}")

            # 3. Inferencia de Modelos Cuantitativos PFC (J48, Bayes Net, Consenso, EV+)
            pos_l = int(fila.get("pos_local", 10) or 10)
            pos_v = int(fila.get("pos_visitante", 10) or 10)
            pfc_res = self.pfc_engine.evaluate_match(
                cuota_local=cuota_l,
                cuota_empate=cuota_x,
                cuota_visitante=cuota_v,
                pos_local=pos_l,
                pos_visitante=pos_v,
                league_name=str(fila.get("league_name", ""))
            )
            fila["pfc_votos"] = " ".join(pfc_res["votos"])
            fila["pfc_consenso"] = pfc_res["consenso_pick"]
            fila["pfc_riesgo"] = pfc_res["riesgo_ponderado"]
            fila["pfc_prob_empate"] = pfc_res["prob_empate"]
            fila["pfc_ev_empate"] = pfc_res["ev_empate"]
            fila["pfc_is_value_draw"] = pfc_res["is_value_draw"]
            fila["pfc_is_j48_draw"] = pfc_res["is_j48_draw"]

            enriquecidos.append(fila)

        # Guardar resultados
        out_pron = self.dir_002 / "002_pronosticos.csv"
        out_merc = self.dir_002 / "002_mercados.csv"
        self._guardar_csv(out_pron, enriquecidos)
        self._guardar_csv(out_merc, mercados)

        return {
            "partidos_enriquecidos": len(enriquecidos),
            "total_candidatos": len(candidatos),
            "errores": errores,
            "cuota_actual": self.quota_mgr.get_summary()
        }

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

    def _parse_odds(self, data: Dict[str, Any], base: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        salida = {"cuota_1": "", "cuota_x": "", "cuota_2": "", "cuota_under_2_5": "", "cuota_over_2_5": ""}
        mercados = []
        for item in data.get("response", []):
            for bm in item.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    bname = str(bet.get("name", "")).casefold()
                    for val in bet.get("values", []):
                        mercados.append({
                            "fixture_id": base.get("fixture_id", ""),
                            "bookmaker": bm.get("name", ""),
                            "mercado": bet.get("name", ""),
                            "seleccion": val.get("value", ""),
                            "cuota": val.get("odd", "")
                        })
                        vstr = str(val.get("value", "")).casefold()
                        if "match winner" in bname or "1x2" in bname:
                            if vstr in ("home", "1") and not salida["cuota_1"]: salida["cuota_1"] = str(val.get("odd"))
                            elif vstr in ("draw", "x") and not salida["cuota_x"]: salida["cuota_x"] = str(val.get("odd"))
                            elif vstr in ("away", "2") and not salida["cuota_2"]: salida["cuota_2"] = str(val.get("odd"))
                        elif "goals over/under" in bname:
                            h = str(val.get("handicap", "")).strip()
                            if "under" in vstr and ("2.5" in h or "2.5" in vstr):
                                if not salida["cuota_under_2_5"]: salida["cuota_under_2_5"] = str(val.get("odd"))
                            elif "over" in vstr and ("2.5" in h or "2.5" in vstr):
                                if not salida["cuota_over_2_5"]: salida["cuota_over_2_5"] = str(val.get("odd"))
        return salida, mercados

    def _parse_prediction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        resp = (data.get("response") or [{}])[0]
        pred = resp.get("predictions", {}) or {}
        winner = pred.get("winner", {}) or {}
        percent = pred.get("percent", {}) or {}
        return {
            "pronostico_ganador": winner.get("name", ""),
            "pronostico_doble_oportunidad": pred.get("win_or_draw", False),
            "pronostico_under_over": pred.get("under_over", ""),
            "pronostico_consejo": pred.get("advice", ""),
            "pred_prob_local": percent.get("home", ""),
            "pred_prob_empate": percent.get("draw", ""),
            "pred_prob_visitante": percent.get("away", "")
        }
