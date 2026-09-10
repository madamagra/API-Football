"""
Modelos de Clasificación de Minería de Datos (J48 y Redes Bayesianas)
Extraídos de la tesis: "Sistema de predicción de resultados en eventos deportivos" (Valera, 2013)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

def get_zona_liga(posicion: int) -> str:
    """Convierte la posición numérica en liga a zona categórica (Tabla 10, pág. 58)."""
    if 1 <= posicion <= 4:
        return "CHAMP"
    elif 5 <= posicion <= 7:
        return "EL"
    elif 8 <= posicion <= 10:
        return "TRANQ"
    elif 11 <= posicion <= 14:
        return "MEDIA"
    elif 15 <= posicion <= 17:
        return "PEL"
    else:
        return "DESC"

class J48PremierLeague:
    """Árbol J48 de Premier League (Figura 122, pág. 247). Acierto en empates = 61.8%."""
    def predict(self, cuota_local: float) -> Tuple[str, float]:
        if cuota_local <= 2.20:
            return "1", 28.0 / 84.0
        elif cuota_local <= 5.25:
            return "X", 28.0 / 58.0  # Rama de EMPATE directo
        else:
            return "2", 0.25

class J48CompeticionLiga:
    """Árbol J48 Global para Competición de Liga (Figura 118, pág. 240)."""
    def predict(self, cuota_local: float, zona_visitante: str) -> Tuple[str, float]:
        if cuota_local <= 2.50:
            return "1", 337.0 / 812.0
        zv = zona_visitante.upper()
        if zv in ("CHAMP", "EL"):
            return "2", 0.43
        elif zv in ("TRANQ", "MEDIA"):
            return "X", 14.0 / 24.0 if zv == "MEDIA" else 0.50
        elif zv == "PEL":
            if cuota_local <= 1.95:
                return "1", 5.0 / 16.0
            elif cuota_local <= 2.30:
                return "2", 4.0 / 10.0
            else:
                return "X", 0.25
        else: # DESC
            if cuota_local <= 2.55:
                return "2", 0.25
            elif cuota_local <= 3.75:
                return "X", 0.25
            else:
                return "2", 0.25

class J48SerieA:
    """Árbol J48 para Serie A (Figura 123, pág. 249)."""
    def predict(self, cuota_local: float, zona_visitante: str) -> Tuple[str, float]:
        zv = zona_visitante.upper()
        if zv == "CHAMP":
            return "2", 18.0 / 33.0
        elif zv == "EL":
            return ("1", 5.0 / 16.0) if cuota_local <= 2.85 else (("2", 0.25) if cuota_local <= 3.15 else ("1", 0.25))
        elif zv == "TRANQ":
            return ("1", 0.25) if cuota_local <= 2.80 else ("X", 0.25)
        elif zv == "MEDIA":
            return ("1", 5.0 / 16.0) if cuota_local <= 1.95 else ("2", 4.0 / 10.0)
        elif zv == "PEL":
            return ("2", 4.0 / 10.0) if cuota_local <= 2.30 else ("X", 0.25)
        else:
            return ("1", 7.0 / 21.0) if cuota_local <= 2.15 else ("X", 0.25)

class BayesNetPremierLeague:
    """Red Bayesiana para Premier League (Tabla 61, pág. 247-248)."""
    def __init__(self):
        self.priors = {"1": 0.446, "X": 0.331, "2": 0.223}
        self.cuota_v_probs = {
            "Baja": {"1": 0.142, "X": 0.590, "2": 0.691},
            "Alta": {"1": 0.858, "X": 0.410, "2": 0.309},
        }
        self.zona_l_probs = {
            "CHAMP": {"1": 0.254, "X": 0.183, "2": 0.125},
            "EL":    {"1": 0.152, "X": 0.125, "2": 0.208},
            "TRANQ": {"1": 0.123, "X": 0.087, "2": 0.097},
            "MEDIA": {"1": 0.254, "X": 0.240, "2": 0.153},
            "PEL":   {"1": 0.138, "X": 0.106, "2": 0.264},
            "DESC":  {"1": 0.080, "X": 0.260, "2": 0.153},
        }

    def predict_proba(self, cuota_visitante: float, zona_local: str) -> Dict[str, float]:
        cv = "Baja" if cuota_visitante <= 3.075 else "Alta"
        zl = zona_local.upper() if zona_local.upper() in self.zona_l_probs else "MEDIA"
        s1 = self.priors["1"] * self.cuota_v_probs[cv]["1"] * self.zona_l_probs[zl]["1"]
        sx = self.priors["X"] * self.cuota_v_probs[cv]["X"] * self.zona_l_probs[zl]["X"]
        s2 = self.priors["2"] * self.cuota_v_probs[cv]["2"] * self.zona_l_probs[zl]["2"]
        total = s1 + sx + s2
        return {"1": s1 / total, "X": sx / total, "2": s2 / total}

class BayesNetCompeticionLiga:
    """Red Bayesiana para Competición de Liga (Tabla 57, pág. 240)."""
    def __init__(self):
        self.priors = {"1": 0.493, "X": 0.249, "2": 0.259}
        self.cuota_l_probs = {
            "Baja":  {"1": 0.227, "X": 0.039, "2": 0.030},
            "Media": {"1": 0.656, "X": 0.670, "2": 0.485},
            "Alta":  {"1": 0.116, "X": 0.292, "2": 0.485},
        }
        self.cuota_v_probs = {
            "Baja":    {"1": 0.031, "X": 0.071, "2": 0.248},
            "Media":   {"1": 0.205, "X": 0.372, "2": 0.382},
            "Alta":    {"1": 0.565, "X": 0.526, "2": 0.343},
            "MuyAlta": {"1": 0.199, "X": 0.031, "2": 0.026},
        }
        self.zona_v_probs = {
            "CHAMP": {"1": 0.121, "X": 0.195, "2": 0.356},
            "EL":    {"1": 0.158, "X": 0.115, "2": 0.156},
            "TRANQ": {"1": 0.153, "X": 0.214, "2": 0.104},
            "MEDIA": {"1": 0.244, "X": 0.184, "2": 0.160},
            "PEL":   {"1": 0.160, "X": 0.122, "2": 0.118},
            "DESC":  {"1": 0.164, "X": 0.170, "2": 0.107},
        }

    def predict_proba(self, cuota_local: float, cuota_visitante: float, zona_visitante: str) -> Dict[str, float]:
        cl = "Baja" if cuota_local <= 1.475 else ("Media" if cuota_local <= 2.525 else "Alta")
        cv = "Baja" if cuota_visitante <= 2.025 else ("Media" if cuota_visitante <= 3.175 else ("Alta" if cuota_visitante <= 7.075 else "MuyAlta"))
        zv = zona_visitante.upper() if zona_visitante.upper() in self.zona_v_probs else "MEDIA"
        s1 = self.priors["1"] * self.cuota_l_probs[cl]["1"] * self.cuota_v_probs[cv]["1"] * self.zona_v_probs[zv]["1"]
        sx = self.priors["X"] * self.cuota_l_probs[cl]["X"] * self.cuota_v_probs[cv]["X"] * self.zona_v_probs[zv]["X"]
        s2 = self.priors["2"] * self.cuota_l_probs[cl]["2"] * self.cuota_v_probs[cv]["2"] * self.zona_v_probs[zv]["2"]
        total = s1 + sx + s2
        return {"1": s1 / total, "X": sx / total, "2": s2 / total}

class PFCEnsemblePredictor:
    """Aplica la regla de consenso unánime del PFC y cálculo de riesgo ponderado."""
    def __init__(self):
        self.j48_premier = J48PremierLeague()
        self.j48_global = J48CompeticionLiga()
        self.j48_serie_a = J48SerieA()
        self.bayes_premier = BayesNetPremierLeague()
        self.bayes_global = BayesNetCompeticionLiga()

    def evaluate_match(self, cuota_local: float, cuota_empate: float, cuota_visitante: float,
                       pos_local: int, pos_visitante: int, league_name: str = "") -> Dict[str, Any]:
        zl = get_zona_liga(pos_local)
        zv = get_zona_liga(pos_visitante)

        votes = []
        is_pl = "premier" in league_name.casefold()
        is_sa = "serie a" in league_name.casefold()

        # 1. Árbol J48 principal
        if is_pl:
            p_j48, r_j48 = self.j48_premier.predict(cuota_local)
            p_bayes_dict = self.bayes_premier.predict_proba(cuota_visitante, zl)
        elif is_sa:
            p_j48, r_j48 = self.j48_serie_a.predict(cuota_local, zv)
            p_bayes_dict = self.bayes_global.predict_proba(cuota_local, cuota_visitante, zv)
        else:
            p_j48, r_j48 = self.j48_global.predict(cuota_local, zv)
            p_bayes_dict = self.bayes_global.predict_proba(cuota_local, cuota_visitante, zv)

        votes.append(p_j48)

        # 2. Red Bayesiana
        best_bayes = max(p_bayes_dict, key=p_bayes_dict.get)
        r_bayes = 1.0 - p_bayes_dict[best_bayes]
        votes.append(best_bayes)

        # 3. Modelos globales adicionales para consenso de 4 clasificadores (Pág. 77)
        p_j48_g, r_j48_g = self.j48_global.predict(cuota_local, zv)
        p_bayes_g_dict = self.bayes_global.predict_proba(cuota_local, cuota_visitante, zv)
        best_bayes_g = max(p_bayes_g_dict, key=p_bayes_g_dict.get)
        votes.append(p_j48_g)
        votes.append(best_bayes_g)

        # Regla de Consenso: ¿Unanimidad?
        unique = set(votes)
        has_consensus = len(unique) == 1
        pick_consenso = votes[0] if has_consensus else "-"

        # Riesgo ponderado (60% Bayes + 40% J48)
        weighted_risk = 0.60 * r_bayes + 0.40 * r_j48 if has_consensus else None

        # Criterio EV+ al Empate: P(X)*Cuota_X > 1.05
        prob_empate = p_bayes_dict.get("X", 0.25)
        ev_draw = (prob_empate * cuota_empate) - 1.0
        is_value_draw = ev_draw > 0.05

        # Detección de Empate J48
        is_j48_draw = (p_j48 == "X") or (p_j48_g == "X")

        return {
            "votos": votes,
            "consenso_pick": pick_consenso,
            "has_consensus": has_consensus,
            "riesgo_ponderado": round(weighted_risk, 3) if weighted_risk else None,
            "prob_bayes": {k: round(v, 4) for k, v in p_bayes_dict.items()},
            "prob_empate": round(prob_empate, 4),
            "ev_empate": round(ev_draw, 4),
            "is_value_draw": is_value_draw,
            "is_j48_draw": is_j48_draw,
            "zona_local": zl,
            "zona_visitante": zv,
        }
