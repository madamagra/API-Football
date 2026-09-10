# Sistema de Pronóstico y Simulación de Empates (API-Football v3 + PFC Valera)

Sistema cuantitativo para predecir, filtrar y simular empates en competiciones de fútbol, integrando los criterios empíricos del usuario (Vías A, B, C, D) con los clasificadores de minería de datos de la Universidad Carlos III de Madrid (J48, Redes Bayesianas, Consenso Bagging y Cobertura PIDO).

Diseñado para operar con una **cuota máxima estricta de 7.500 llamadas/día** a API-Football (api-sports.io) y preparado para ejecutarse en **localhost** y desplegarse en **Render.com**.

---

## 1. Instalación y Requisitos

### Requisitos Previos:
- Python 3.10 o superior.
- Clave o claves de API-Football (suscripción de 7.500 llamadas/día).

### Instalación de dependencias:
```bash
pip install -r requirements.txt
```

### Configuración del entorno (.env):
Edita el archivo `.env` en la raíz del proyecto con tus tokens de API-Football:
```env
TOKEN_A=tu_clave_aqui
TOKEN_B=tu_clave_aqui
TOKEN_C=tu_clave_aqui
TOKEN_D=tu_clave_aqui
TOKEN_E=tu_clave_aqui

DAILY_REQUEST_LIMIT=7500
CIRCUIT_BREAKER_MARGIN=50
PORT=8000
```
*(Si usas una única clave para las 7.500 llamadas, puedes asignar la misma clave a todos los `TOKEN_*` o a `SPORTS_API_KEY`)*.

---

## 2. Ejecución en Localhost

Arranca el servidor web interactivo:
```bash
py app.py
```
O usando Uvicorn directamente con recarga en vivo:
```bash
py -m uvicorn app:app --reload --port 8000
```
Abre tu navegador en:
👉 `http://localhost:8000`
Documentación interactiva OpenAPI (Swagger):
👉 `http://localhost:8000/docs`

---

## 3. Despliegue en Render.com

El proyecto incluye configuración nativa para Render:
- **`Procfile`**: `web: uvicorn app:app --host 0.0.0.0 --port $PORT`
- **`render.yaml`**: Definición como Web Service Python.

### Pasos para desplegar:
1. Sube este proyecto a un repositorio en **GitHub** o **GitLab**.
2. En tu cuenta de **Render.com**, haz clic en **New +** -> **Web Service**.
3. Conecta tu repositorio.
4. Render detectará automáticamente el archivo `Procfile` y `requirements.txt`.
5. En la sección **Environment Variables**, añade:
   - `TOKEN_A`, `TOKEN_B`, etc.
   - `DAILY_REQUEST_LIMIT`: `7500`
6. Haz clic en **Deploy Web Service**.

---

## 4. Control de Cuota (7.500 llamadas/día)

El módulo `core/quota_manager.py`:
- **Petición `/status`**: Costo **0 llamadas** contra el cupo. Se consulta para sincronizar el consumo oficial reportado por API-Sports.
- **Circuit Breaker**: Si el contador alcanza 7.450 llamadas en el día, se suspenden automáticamente las llamadas externas para salvaguardar el margen de seguridad de la cuenta.
- **Rotación A-E**: Las 217 ligas de `Seleccion.csv` están balanceadas entre los 5 grupos de tokens (A, B, C, D, E), consumiendo solo ~217 llamadas/día en la sincronización base.

---

## 5. Resumen de Criterios Multicriterio

| Vía / Criterio | Descripción | Fuente |
|---|---|---|
| **Vía A** | Cuota X &le; Límite AND Medias goles &le; Límite AND Cuota Under 2.5 &le; Límite | Usuario (Script 003) |
| **Vía B** | Cuota X & Goles &le; Límite AND Pronóstico API &isin; {-1.5, -0.5} | Usuario (Script 003) |
| **Vía C** | Racha actual de empates consecutivos &ge; K partidos | Usuario (Script 003) |
| **Vía D** | Marcador más frecuente en últimos 5 partidos es "0-0" (&ge; M jornadas) | Usuario (Script 003) |
| **Filtro 5 partidos** | Descarte obligatorio si el local no empató en últimos 5 en casa o visitante fuera | Usuario (Script 003) |
| **Vía E (J48)** | Activación de rama de empate X en Árbol C4.5 (Premier: 2.20 &lt; CuotaL &le; 5.25) | PFC Valera (Anexo C) |
| **Vía F (Bayes)** | Probabilidad condicional bayesiana P(X) &ge; Umbral (ej. &ge; 28%) | PFC Valera (Anexo C) |
| **Vía G (EV+)** | Apuesta de valor con esperanza matemática positiva: P(X) &times; CuotaX &gt; 1.05 | PFC Valera |
| **PIDO** | Reparto exacto de capital para igualar retorno si gana el pick o hay empate | PFC Valera (Pág. 125) |
