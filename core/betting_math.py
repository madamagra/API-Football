"""
Matemática y Gestión de Apuestas:
- PIDO: Partidos Individuales con Doble Oportunidad (cobertura matemática de empate)
- Criterio de Kelly y Valor Esperado (EV+)
- Algoritmo Genético Fitness = sqrt(Cuota) / Riesgo
- Sistema 2/3 y Lucky 15
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

def calc_pido(cuota_pick: float, cuota_empate: float, stake_total: float = 1.0) -> Dict[str, float]:
    """
    Fórmula de reparto PIDO (PFC Sección 5.2.2, Pág. 125):
    Garantiza retorno idéntico si gana el Pick o si hay Empate (X).
    """
    suma = cuota_pick + cuota_empate
    coef_pick = 1.0 - (cuota_pick / suma)
    coef_x = 1.0 - (cuota_empate / suma)

    stake_pick = coef_pick * stake_total
    stake_x = coef_x * stake_total

    retorno_bruto = stake_pick * cuota_pick
    cuota_efectiva = (cuota_pick * cuota_empate) / suma

    return {
        "stake_pick": round(stake_pick, 4),
        "stake_empate": round(stake_x, 4),
        "coef_pick": round(coef_pick, 4),
        "coef_empate": round(coef_x, 4),
        "retorno_bruto": round(retorno_bruto, 4),
        "cuota_efectiva": round(cuota_efectiva, 4),
        "beneficio_neto": round(retorno_bruto - stake_total, 4)
    }

def calc_fitness_pfc(cuota: float, riesgo: float) -> float:
    """Función Fitness del PFC (Figura 43, Pág. 129): Fitness = sqrt(Cuota) / Riesgo"""
    r = max(0.001, riesgo)
    return round(math.sqrt(cuota) / r, 4)

def calc_kelly_fraction(prob: float, cuota: float, fraction: float = 0.25) -> float:
    """Criterio de Kelly fraccional para control de riesgo."""
    b = cuota - 1.0
    p = prob
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, round(f * fraction, 4))
