"""
Simulador de Partidos al Empate para las 217 Ligas de Seleccion.csv
Ejecuta simulaciones tanto históricas como sintéticas evaluando las estrategias del usuario y del PFC.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.betting_math import calc_pido, calc_fitness_pfc
from core.classifiers_pfc import PFCEnsemblePredictor, get_zona_liga

class LeagueMatchSimulator:
    def __init__(self, base_dir: Path, seed: int = 123):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.dir_001 = self.data_dir / "001"
        self.archivo_seleccion = base_dir / "Seleccion.csv"
        self.pfc_engine = PFCEnsemblePredictor()
        random.seed(seed)

    def get_available_leagues(self) -> List[Dict[str, str]]:
        if not self.archivo_seleccion.exists():
            return []
        lineas = self.archivo_seleccion.read_text(encoding="utf-8-sig").splitlines()
        delimitador = ";" if lineas[0].count(";") >= lineas[0].count(",") else ","
        lector = csv.DictReader(lineas, delimiter=delimitador)
        return [
            {
                "id": (row.get("Id") or row.get("id") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "country": (row.get("country") or "").strip(),
                "token": (row.get("token") or "A").strip()
            }
            for row in lector if row.get("Id") or row.get("id")
        ]

    def simulate_league_season(
        self,
        league_id: str,
        num_weeks: int = 12,
        matches_per_week: int = 10,
        stake_per_bet: float = 1.0,
        criteria: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Simula una temporada de 12 semanas para una liga específica de Seleccion.csv.
        """
        crit = criteria or {
            "max_cuota_x": 3.20,
            "max_media_goles": 1.20,
            "min_racha": 3,
            "enable_via_a": True,
            "enable_via_b": True,
            "enable_via_c": True,
            "enable_via_j48": True,
            "enable_via_bayes": True,
            "enable_via_ev": True,
            "min_bayes_prob": 0.28,
            "filter_last5": True
        }

        # Generar o cargar equipos de la liga
        leagues = {l["id"]: l for l in self.get_available_leagues()}
        l_info = leagues.get(league_id, {"name": f"Liga {league_id}", "country": "World"})
        l_name = l_info["name"]

        team_names = [f"Equipo {chr(65+i)}{i+1}" for i in range(20)]
        team_ratings = {t: 20 - i for i, t in enumerate(team_names)}

        total_matches = 0
        total_real_draws = 0

        # Estrategias acumuladas
        stats_pido = {"bets": 0, "hits": 0, "staked": 0.0, "returned": 0.0}
        stats_direct = {"bets": 0, "hits": 0, "staked": 0.0, "returned": 0.0}
        stats_value = {"bets": 0, "hits": 0, "staked": 0.0, "returned": 0.0}
        stats_control = {"bets": 0, "hits": 0, "staked": 0.0, "returned": 0.0}

        weekly_rows = []

        for w in range(1, num_weeks + 1):
            shuffled = team_names.copy()
            random.shuffle(shuffled)

            w_with_pred = 0
            w_hits_simple = 0
            w_hits_do = 0
            w_pido_pnl = 0.0
            w_direct_pnl = 0.0

            for m_idx in range(matches_per_week):
                home = shuffled[m_idx * 2]
                away = shuffled[m_idx * 2 + 1]
                pos_h = team_names.index(home) + 1
                pos_a = team_names.index(away) + 1

                # Probabilidades futbolísticas con ventaja local
                diff = (team_ratings[home] + 2.5) - team_ratings[away]
                if abs(diff) <= 2:
                    p1, px, p2 = 0.38, 0.32, 0.30
                elif diff > 0:
                    p1 = min(0.70, 0.44 + 0.03 * diff)
                    px = max(0.18, 0.28 - 0.01 * diff)
                    p2 = 1.0 - (p1 + px)
                else:
                    p2 = min(0.65, 0.40 + 0.03 * abs(diff))
                    px = max(0.18, 0.28 - 0.01 * abs(diff))
                    p1 = 1.0 - (p2 + px)

                # Cuotas de casa con margen 6%
                cl = round(1.0 / (p1 * 1.06), 2)
                cx = round(1.0 / (px * 1.06), 2)
                cv = round(1.0 / (p2 * 1.06), 2)

                # Resultado real
                rand_res = random.random()
                actual = "1" if rand_res < p1 else ("X" if rand_res < (p1 + px) else "2")
                total_matches += 1
                if actual == "X": total_real_draws += 1

                # Inferencia PFC
                pfc_eval = self.pfc_engine.evaluate_match(cl, cx, cv, pos_h, pos_a, l_name)
                consenso = pfc_eval["consenso_pick"]
                prob_x_bayes = pfc_eval["prob_empate"]
                is_val = pfc_eval["is_value_draw"]
                is_j48_x = pfc_eval["is_j48_draw"]

                # Control Azar (Apostar a empate a ciegas)
                stats_control["bets"] += 1
                stats_control["staked"] += stake_per_bet
                if actual == "X": stats_control["hits"] += 1; stats_control["returned"] += stake_per_bet * cx

                # Criterio Empate Directo (J48 o Consenso X)
                if (is_j48_x and crit.get("enable_via_j48")) or (consenso == "X"):
                    stats_direct["bets"] += 1
                    stats_direct["staked"] += stake_per_bet
                    ret = (stake_per_bet * cx) if actual == "X" else 0.0
                    stats_direct["returned"] += ret
                    w_direct_pnl += (ret - stake_per_bet)
                    if actual == "X": stats_direct["hits"] += 1

                # Criterio Valor Bayesiano
                if is_val and crit.get("enable_via_ev"):
                    stats_value["bets"] += 1
                    stats_value["staked"] += stake_per_bet
                    ret = (stake_per_bet * cx) if actual == "X" else 0.0
                    stats_value["returned"] += ret
                    if actual == "X": stats_value["hits"] += 1

                # Criterio PIDO (Doble Oportunidad cubriendo empate)
                if consenso in ("1", "2"):
                    w_with_pred += 1
                    pick_cuota = cl if consenso == "1" else cv
                    pido = calc_pido(pick_cuota, cx, stake_total=stake_per_bet)

                    stats_pido["bets"] += 1
                    stats_pido["staked"] += stake_per_bet

                    is_hit_s = (actual == consenso)
                    is_hit_do = (actual == consenso or actual == "X")

                    if is_hit_s: w_hits_simple += 1
                    if is_hit_do:
                        w_hits_do += 1
                        stats_pido["hits"] += 1
                        stats_pido["returned"] += pido["retorno_bruto"]
                        w_pido_pnl += pido["beneficio_neto"]
                    else:
                        w_pido_pnl -= stake_per_bet
                elif consenso == "X":
                    w_with_pred += 1
                    stats_pido["bets"] += 1
                    stats_pido["staked"] += stake_per_bet
                    if actual == "X":
                        w_hits_simple += 1
                        w_hits_do += 1
                        stats_pido["hits"] += 1
                        stats_pido["returned"] += stake_per_bet * cx
                        w_pido_pnl += (stake_per_bet * cx - stake_per_bet)
                    else:
                        w_pido_pnl -= stake_per_bet

            pct_s = (w_hits_simple / w_with_pred * 100) if w_with_pred > 0 else 0
            pct_do = (w_hits_do / w_with_pred * 100) if w_with_pred > 0 else 0
            weekly_rows.append({
                "semana": w,
                "con_pred": w_with_pred,
                "sin_pred": matches_per_week - w_with_pred,
                "aciertos_simples": w_hits_simple,
                "pct_simples": round(pct_s, 2),
                "aciertos_do": w_hits_do,
                "pct_do": round(pct_do, 2),
                "pnl_pido": round(w_pido_pnl, 2),
                "pnl_direct_draw": round(w_direct_pnl, 2)
            })

        def calc_m(d):
            stk = d["staked"]
            ret = d["returned"]
            pnl = ret - stk
            return {
                "bets": d["bets"],
                "hits": d["hits"],
                "hit_rate": round(d["hits"] / d["bets"] * 100, 2) if d["bets"] else 0,
                "staked": round(stk, 2),
                "returned": round(ret, 2),
                "pnl": round(pnl, 2),
                "roi_pct": round(pnl / stk * 100, 2) if stk > 0 else 0
            }

        return {
            "liga_id": league_id,
            "liga_nombre": l_name,
            "total_partidos": total_matches,
            "empates_reales": total_real_draws,
            "pct_empates": round(total_real_draws / total_matches * 100, 2),
            "estrategias": {
                "PIDO_Doble_Oportunidad": calc_m(stats_pido),
                "Empate_Directo_J48": calc_m(stats_direct),
                "Valor_Bayesiano_EV": calc_m(stats_value),
                "Control_Ciego_Empate": calc_m(stats_control)
            },
            "tabla_semanal": weekly_rows
        }
