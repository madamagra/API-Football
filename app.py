"""
Servidor Web FastAPI y API REST para Localhost y Render.com
Controla la sincronización con API-Football (máx 7.500 llamadas/día),
la selección multicriterio de empates y la simulación interactiva.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Configurar rutas
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.quota_manager import QuotaManager
from core.api_client import APIFootballClient
from core.betting_math import calc_pido
from pipeline.sync_service import SyncService
from pipeline.fixture_enricher import FixtureEnricher
from pipeline.draw_selector import DrawSelector
from pipeline.evaluator import BetEvaluator
from pipeline.simulator import LeagueMatchSimulator

app = FastAPI(
    title="API-Football Draw Predictor & Simulator",
    description="Sistema cuantitativo de predicción y simulación de empates con control de cuota (7.500 llamadas/día).",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar servicios
quota_mgr = QuotaManager(data_dir=BASE_DIR / "data")
sync_service = SyncService(base_dir=BASE_DIR)
enricher_service = FixtureEnricher(base_dir=BASE_DIR)
selector_service = DrawSelector(base_dir=BASE_DIR)
evaluator_service = BetEvaluator(base_dir=BASE_DIR)
simulator_service = LeagueMatchSimulator(base_dir=BASE_DIR)

# Montar estáticos
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Modelos Pydantic
class CriteriaRequest(BaseModel):
    max_cuota_x: float = 3.20
    max_media_goles: float = 1.20
    max_cuota_under_2_5: float = 2.00
    min_racha_empates: int = 3
    resultado_habitual_buscado: str = "0-0"
    min_jornadas_habitual: int = 4
    enable_via_a: bool = True
    enable_via_b: bool = True
    enable_via_c: bool = True
    enable_via_d: bool = True
    enable_via_j48_pfc: bool = True
    enable_via_bayes_pfc: bool = True
    enable_via_ev_pfc: bool = True
    min_bayes_prob: float = 0.28
    min_ev_edge: float = 0.05
    enforce_filter_last5_draw: bool = True
    stake_per_bet: float = 1.0

class SimulateRequest(BaseModel):
    league_id: str = "39"
    num_weeks: int = 12
    matches_per_week: int = 10
    stake_per_bet: float = 1.0
    criteria: Optional[Dict[str, Any]] = None

class PidoRequest(BaseModel):
    cuota_pick: float
    cuota_empate: float
    stake_total: float = 1.0

class SyncRequest(BaseModel):
    max_leagues: Optional[int] = 20

# Endpoints
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = static_dir / "index.html"
    if not index_file.exists():
        return "<h1>Servidor activo. Cargando interfaz...</h1>"
    return FileResponse(str(index_file))

@app.get("/health")
async def health_check():
    """Health check requerido para Render.com"""
    return {
        "status": "healthy",
        "service": "api-football-draw-predictor",
        "quota_calls_today": quota_mgr.get_summary()["total_hoy"],
        "quota_limit": quota_mgr.get_summary()["limite_diario"]
    }

@app.get("/api/quota")
async def get_quota_status():
    """Devuelve el estado de consumo de cuota diaria y estado de tokens."""
    return quota_mgr.get_summary()

@app.get("/api/leagues")
async def get_leagues():
    """Devuelve las 217 ligas disponibles de Seleccion.csv."""
    return simulator_service.get_available_leagues()

@app.post("/api/pido/calculate")
async def calculate_pido(req: PidoRequest):
    """Calcula el reparto matemático exacto de stake PIDO (pág. 125)."""
    return calc_pido(req.cuota_pick, req.cuota_empate, req.stake_total)

@app.post("/api/select-draws")
async def select_draws(crit: CriteriaRequest):
    """Ejecuta el selector de empates multicriterio."""
    res = selector_service.select_draws(
        max_cuota_x=crit.max_cuota_x,
        max_media_goles=crit.max_media_goles,
        max_cuota_under_2_5=crit.max_cuota_under_2_5,
        min_racha_empates=crit.min_racha_empates,
        resultado_habitual_buscado=crit.resultado_habitual_buscado,
        min_jornadas_habitual=crit.min_jornadas_habitual,
        enable_via_a=crit.enable_via_a,
        enable_via_b=crit.enable_via_b,
        enable_via_c=crit.enable_via_c,
        enable_via_d=crit.enable_via_d,
        enable_via_j48_pfc=crit.enable_via_j48_pfc,
        enable_via_bayes_pfc=crit.enable_via_bayes_pfc,
        enable_via_ev_pfc=crit.enable_via_ev_pfc,
        min_bayes_prob=crit.min_bayes_prob,
        min_ev_edge=crit.min_ev_edge,
        enforce_filter_last5_draw=crit.enforce_filter_last5_draw,
        stake_per_bet=crit.stake_per_bet
    )
    return res

@app.post("/api/simulate")
async def simulate_season(req: SimulateRequest):
    """Simula una temporada completa de empates para una liga."""
    res = simulator_service.simulate_league_season(
        league_id=req.league_id,
        num_weeks=req.num_weeks,
        matches_per_week=req.matches_per_week,
        stake_per_bet=req.stake_per_bet,
        criteria=req.criteria
    )
    return res

@app.post("/api/sync-leagues")
async def trigger_sync(req: SyncRequest):
    """Dispara la sincronización con API-Football bajo control de cuota."""
    return sync_service.sync_leagues(max_leagues=req.max_leagues)

@app.post("/api/enrich-fixtures")
async def trigger_enrichment():
    """Descarga cuotas y predicciones para partidos de las próximas 72h."""
    return enricher_service.enrich_upcoming()

@app.post("/api/evaluate")
async def trigger_evaluation():
    """Evalúa los pronósticos propuestos contra resultados reales."""
    return evaluator_service.evaluate_proposals()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Iniciando servidor en http://{host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=False)
