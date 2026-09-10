import sys
from pathlib import Path
base = Path(".")
sys.path.insert(0, str(base))

from core.quota_manager import QuotaManager
from core.api_client import APIFootballClient
from core.classifiers_pfc import PFCEnsemblePredictor
from core.betting_math import calc_pido
from pipeline.simulator import LeagueMatchSimulator
from pipeline.draw_selector import DrawSelector

print("1. Probando QuotaManager...")
qm = QuotaManager(data_dir=base / "data", daily_limit=7500)
status = qm.get_summary()
assert status["limite_diario"] == 7500
print("   QuotaManager OK:", status["total_hoy"], "/", status["limite_diario"])

print("2. Probando Classifiers PFC...")
pfc = PFCEnsemblePredictor()
res_pl = pfc.evaluate_match(cuota_local=3.10, cuota_empate=3.20, cuota_visitante=2.40, pos_local=10, pos_visitante=11, league_name="Premier League")
print("   PFC Premier League (cuotaL=3.10):", res_pl["consenso_pick"], "Votos:", res_pl["votos"], "P(X):", res_pl["prob_empate"])
assert res_pl["is_j48_draw"] == True, "J48 de Premier League debe detectar empate cuando 2.20 < cuotaL <= 5.25"

print("3. Probando PIDO Math (PFC Pág. 125)...")
pido = calc_pido(cuota_pick=1.50, cuota_empate=3.30, stake_total=1.0)
assert abs(pido["retorno_bruto"] - 1.03125) < 1e-4, f"Retorno esperado 1.03125, obtenido {pido['retorno_bruto']}"
print("   PIDO Formula OK: Retorno idéntico =", pido["retorno_bruto"])

print("4. Probando LeagueMatchSimulator (Seleccion.csv)...")
sim = LeagueMatchSimulator(base_dir=base)
leagues = sim.get_available_leagues()
print(f"   Ligas cargadas de Seleccion.csv: {len(leagues)}")
assert len(leagues) == 217, f"Se esperaban 217 ligas, se encontraron {len(leagues)}"

sim_res = sim.simulate_league_season(league_id="39", num_weeks=12, matches_per_week=10)
print(f"   Simulación completada para {sim_res['liga_nombre']}: {sim_res['total_partidos']} partidos.")
print("   Acierto PIDO:", sim_res["estrategias"]["PIDO_Doble_Oportunidad"]["hit_rate"], "%")
print("   Acierto Empate Directo:", sim_res["estrategias"]["Empate_Directo_J48"]["hit_rate"], "%")

print("\n>>> TODOS LOS TESTS DE INTEGRACIÓN HAN PASADO CON ÉXITO <<<")
