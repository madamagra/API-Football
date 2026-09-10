"""
Selector Multicriterio de Empates (Evolución de Script 003 + Criterios PFC)
Combina las vías A, B, C, D del usuario con las vías E (J48), F (Bayes), G (EV+ Valor) y PIDO.
Genera además las listas Martingala cronológicas con separación temporal >= 1h 59m.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from core.betting_math import calc_pido, calc_fitness_pfc

INTERVALO_MINIMO = timedelta(hours=1, minutes=59)
TZ_ESPANA = ZoneInfo("Europe/Madrid")

class DrawSelector:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.data_dir = base_dir / "data"
        self.dir_001 = self.data_dir / "001"
        self.dir_002 = self.data_dir / "002"
        self.dir_003 = self.data_dir / "003"
        self.dir_003.mkdir(parents=True, exist_ok=True)

    def select_draws(
        self,
        matches: Optional[List[Dict[str, Any]]] = None,
        max_cuota_x: float = 3.20,
        max_media_goles: float = 1.20,
        max_cuota_under_2_5: float = 2.00,
        min_racha_empates: int = 3,
        resultado_habitual_buscado: str = "0-0",
        min_jornadas_habitual: int = 4,
        enable_via_a: bool = True,
        enable_via_b: bool = True,
        enable_via_c: bool = True,
        enable_via_d: bool = True,
        enable_via_j48_pfc: bool = True,
        enable_via_bayes_pfc: bool = True,
        enable_via_ev_pfc: bool = True,
        min_bayes_prob: float = 0.28,
        min_ev_edge: float = 0.05,
        enforce_filter_last5_draw: bool = True,
        stake_per_bet: float = 1.0
    ) -> Dict[str, Any]:
        """
        Ejecuta la selección de empates bajo los criterios seleccionados por el usuario.
        """
        if matches is None:
            archivo_pron = self.dir_002 / "002_pronosticos.csv"
            if not archivo_pron.exists():
                archivo_pron = self.dir_001 / "001_proximos_partidos.csv"
            if not archivo_pron.exists():
                return {"status": "no_data", "mensaje": "No hay partidos en data/002 ni data/001."}
            matches = self._leer_csv(archivo_pron)

        seleccionados = []
        descartados_filtro_ultimos5 = 0

        # Cache de estadísticas de ligas para racha y últimos 5 partidos
        cache_ligas = {}

        for m in matches:
            lid = str(m.get("league_id", ""))
            hid = str(m.get("home_id", ""))
            aid = str(m.get("away_id", ""))

            if lid not in cache_ligas:
                cache_ligas[lid] = self._calcular_stats_liga(lid)
            stats_liga = cache_ligas[lid]

            stats_home = stats_liga.get(hid, {"media_goles": 1.5, "racha_actual": 0, "ultimos5_tiene_empate": True, "resultado_frecuente": ""})
            stats_away = stats_liga.get(aid, {"media_goles": 1.5, "racha_actual": 0, "ultimos5_tiene_empate": True, "resultado_frecuente": ""})

            # Cuotas numéricas
            cx = self._to_float(m.get("cuota_x"), default=3.20)
            cl = self._to_float(m.get("cuota_1"), default=2.10)
            cv = self._to_float(m.get("cuota_2"), default=3.30)
            cu25 = self._to_float(m.get("cuota_under_2_5"), default=1.85)

            media_h = stats_home.get("media_goles", 1.5)
            media_a = stats_away.get("media_goles", 1.5)

            # Vía A (Cuotas + Medias Goles + Under 2.5)
            crit_a = (
                enable_via_a and
                (cx <= max_cuota_x) and
                (media_h <= max_media_goles) and
                (media_a <= max_media_goles) and
                (cu25 <= max_cuota_under_2_5)
            )

            # Vía B (Cuotas + Goles + Pronóstico API -1.5 / -0.5)
            pred_uo = str(m.get("pronostico_under_over", "")).strip()
            crit_b = (
                enable_via_b and
                (cx <= max_cuota_x) and
                (media_h <= max_media_goles) and
                (media_a <= max_media_goles) and
                (pred_uo in ("-1.5", "-0.5"))
            )

            # Vía C (Racha actual de empates)
            racha_h = stats_home.get("racha_actual", 0)
            racha_a = stats_away.get("racha_actual", 0)
            crit_c = enable_via_c and (racha_h >= min_racha_empates or racha_a >= min_racha_empates)

            # Vía D (Resultado habitual buscado ej 0-0)
            crit_d = (
                enable_via_d and
                (stats_home.get("resultado_frecuente") == resultado_habitual_buscado) and
                (stats_away.get("resultado_frecuente") == resultado_habitual_buscado)
            )

            # Vía E (PFC Árbol J48 rama de Empate)
            is_j48_draw = str(m.get("pfc_is_j48_draw", "")).lower() in ("true", "1") or (m.get("pfc_consenso") == "X")
            if not is_j48_draw and "premier" in str(m.get("league_name", "")).lower():
                is_j48_draw = (2.20 < cl <= 5.25)
            crit_e = enable_via_j48_pfc and is_j48_draw

            # Vía F (PFC Bayes Net Probabilidad de Empate)
            prob_x = self._to_float(m.get("pfc_prob_empate"), default=0.25)
            crit_f = enable_via_bayes_pfc and (prob_x >= min_bayes_prob)

            # Vía G (PFC Apuesta de Valor Matemático EV+)
            ev = self._to_float(m.get("pfc_ev_empate"), default=(prob_x * cx - 1.0))
            crit_g = enable_via_ev_pfc and (ev >= min_ev_edge)

            # ¿Cumple alguna de las vías activas?
            seleccionado_por_alguna_via = crit_a or crit_b or crit_c or crit_d or crit_e or crit_f or crit_g

            if not seleccionado_por_alguna_via:
                continue

            # FILTRO OBLIGATORIO: descarte si no ha empatado nunca en últimos 5
            if enforce_filter_last5_draw:
                has_drawn_h = stats_home.get("ultimos5_tiene_empate", True)
                has_drawn_a = stats_away.get("ultimos5_tiene_empate", True)
                if not has_drawn_h or not has_drawn_a:
                    descartados_filtro_ultimos5 += 1
                    continue

            vias_activas = []
            if crit_a: vias_activas.append("Vía A (Cuotas/Goles/U2.5)")
            if crit_b: vias_activas.append("Vía B (Pronóstico -1.5/-0.5)")
            if crit_c: vias_activas.append(f"Vía C (Racha {max(racha_h, racha_a)}X)")
            if crit_d: vias_activas.append(f"Vía D ({resultado_habitual_buscado})")
            if crit_e: vias_activas.append("Vía E (J48 Empate)")
            if crit_f: vias_activas.append(f"Vía F (Bayes {prob_x*100:.0f}%)")
            if crit_g: vias_activas.append(f"Vía G (EV+ {ev*100:.1f}%)")

            # Cálculo PIDO exacto (PFC Sección 5.2.2)
            # Pick base preferido: local (1) o visitante (2) según cuota
            pick_base = "1" if cl <= cv else "2"
            cuota_pick = min(cl, cv)
            pido_calc = calc_pido(cuota_pick, cx, stake_total=stake_per_bet)
            risk_est = self._to_float(m.get("pfc_riesgo"), default=0.25)
            fitness = calc_fitness_pfc(cx, risk_est)

            fila_out = dict(m)
            fila_out.update({
                "vias_activas": " + ".join(vias_activas),
                "num_vias": len(vias_activas),
                "cuota_1_num": cl,
                "cuota_x_num": cx,
                "cuota_2_num": cv,
                "prob_bayes_x": prob_x,
                "ev_draw": round(ev, 3),
                "racha_home": racha_h,
                "racha_away": racha_a,
                # Datos PIDO
                "pido_pick_base": pick_base,
                "pido_stake_pick": pido_calc["stake_pick"],
                "pido_stake_x": pido_calc["stake_empate"],
                "pido_cuota_efectiva": pido_calc["cuota_efectiva"],
                "pido_beneficio_garantizado": pido_calc["beneficio_neto"],
                "pfc_fitness": fitness
            })
            seleccionados.append(fila_out)

        # Generar listas Martingala cronológicas (separación >= 1h 59m)
        martingalas = self._construir_martingalas(seleccionados)

        # Guardar en CSV
        self._guardar_csv(self.dir_003 / "003_empates_seleccionados.csv", seleccionados)
        self._guardar_csv(self.dir_003 / "003_simplificada_martingalas.csv", martingalas)

        return {
            "total_evaluados": len(matches),
            "seleccionados": len(seleccionados),
            "descartados_filtro_5": descartados_filtro_ultimos5,
            "martingalas_creadas": len(set(m["lista_martingala"] for m in martingalas)) if martingalas else 0,
            "archivo_completo": str(self.dir_003 / "003_empates_seleccionados.csv"),
            "archivo_martingalas": str(self.dir_003 / "003_simplificada_martingalas.csv"),
            "partidos": seleccionados[:100]  # Primeros 100 para UI
        }

    def _calcular_stats_liga(self, league_id: str) -> Dict[str, Dict[str, Any]]:
        ruta = self.dir_001 / f"{league_id}.csv"
        if not ruta.exists():
            return {}
        try:
            lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
            if not lineas: return {}
            lector = csv.DictReader(lineas)
            partidos_validos = []
            for r in lector:
                st = str(r.get("status_short", "")).upper().strip()
                if st in ("FT", "AET", "PEN"):
                    try:
                        f_dt = datetime.fromisoformat(str(r.get("date", "")).replace("Z", "+00:00"))
                        gh = int(r.get("goals_home", 0) or 0)
                        ga = int(r.get("goals_away", 0) or 0)
                        partidos_validos.append((f_dt, str(r.get("home_id", "")), str(r.get("away_id", "")), gh, ga))
                    except Exception:
                        continue

            partidos_validos.sort(key=lambda x: x[0])  # Cronológico ascendente

            teams_stats = {}
            for dt, hid, aid, gh, ga in partidos_validos:
                es_empate = (gh == ga)
                # Local
                sh = teams_stats.setdefault(hid, {"goles": 0, "partidos": 0, "historial_empates": [], "local_empates": [], "scores": []})
                sh["goles"] += gh
                sh["partidos"] += 1
                sh["historial_empates"].append(es_empate)
                sh["local_empates"].append(es_empate)
                sh["scores"].append(f"{gh}-{ga}")

                # Visitante
                sa = teams_stats.setdefault(aid, {"goles": 0, "partidos": 0, "historial_empates": [], "away_empates": [], "scores": []})
                sa["goles"] += ga
                sa["partidos"] += 1
                sa["historial_empates"].append(es_empate)
                sa["away_empates"].append(es_empate)
                sa["scores"].append(f"{gh}-{ga}")

            resumen = {}
            for tid, d in teams_stats.items():
                p = d["partidos"]
                media = (d["goles"] / p) if p > 0 else 1.5

                # Racha viva de empates (desde el más reciente hacia atrás)
                racha = 0
                for e in reversed(d["historial_empates"]):
                    if not e: break
                    racha += 1

                # Últimos 5 en condición local/visitante
                ult_local = d["local_empates"][-5:]
                ult_away = d["away_empates"][-5:]
                has_draw_local = any(ult_local) if ult_local else False
                has_draw_away = any(ult_away) if ult_away else False

                # Marcador más frecuente
                scores = d["scores"][-5:]
                freq_score = max(set(scores), key=scores.count) if scores else ""

                resumen[tid] = {
                    "media_goles": round(media, 2),
                    "racha_actual": racha,
                    "ultimos5_tiene_empate": has_draw_local or has_draw_away,
                    "resultado_frecuente": freq_score
                }
            return resumen
        except Exception:
            return {}

    def _construir_martingalas(self, partidos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not partidos: return []

        # Ordenar cronológicamente
        con_fecha = []
        for p in partidos:
            try:
                dt_str = str(p.get("date_utc", p.get("date", ""))).replace("Z", "+00:00")
                dt = datetime.fromisoformat(dt_str)
                con_fecha.append((dt, p))
            except Exception:
                con_fecha.append((datetime.max.replace(tzinfo=timezone.utc), p))

        con_fecha.sort(key=lambda x: x[0])

        listas: List[List[Tuple[datetime, Dict[str, Any]]]] = []
        for dt, p in con_fecha:
            for l in listas:
                if all(abs((dt - otro_dt).total_seconds()) >= INTERVALO_MINIMO.total_seconds() for otro_dt, _ in l):
                    l.append((dt, p))
                    break
            else:
                listas.append([(dt, p)])

        salida = []
        orden_global = 1
        for idx_l, l in enumerate(listas):
            letra = chr(65 + (idx_l % 26))
            for idx_p, (dt, p) in enumerate(l, start=1):
                f_esp = dt.astimezone(TZ_ESPANA) if dt != datetime.max else None
                salida.append({
                    "orden_cronologico_global": orden_global,
                    "numero_apuesta": f"{letra}{idx_p}",
                    "lista_martingala": f"Martingala Empates {letra}",
                    "dia_partido": f_esp.strftime("%d-%m-%Y") if f_esp else "",
                    "hora_partido_espana": f_esp.strftime("%H:%M") if f_esp else "",
                    "league_name": p.get("league_name", ""),
                    "equipo_local": p.get("home_name", ""),
                    "equipo_visitante": p.get("away_name", ""),
                    "cuota_x": p.get("cuota_x_num", ""),
                    "cuota_pido_efectiva": p.get("pido_cuota_efectiva", ""),
                    "vias_activas": p.get("vias_activas", "")
                })
                orden_global += 1
        return salida

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
