"""
BhoomiChain — ML Forecasting Engine
=====================================
Trains a Random Forest on the LoRaWAN dataset to:
  1. Forecast optimal irrigation windows (next 48 h)
  2. Estimate SOC trajectory
  3. Generate actionable farm recommendations
  4. Output forecast_output.json for the dashboard

Run: python ml_forecast.py
"""

import pandas as pd
import numpy as np
import json, os
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

print("=" * 60)
print("  BhoomiChain ML Forecasting Engine")
print("=" * 60)

# ── Load dataset ─────────────────────────────────────────────────────────────
CSV = "data/bhoomichain_lorawan_dataset.csv"
if not os.path.exists(CSV):
    print("Dataset not found. Run generate_dataset.py first.")
    exit(1)

df = pd.read_csv(CSV, parse_dates=["timestamp"])
df = df[df.device_eui == df.device_eui.iloc[0]].copy()   # use device 1
df = df.sort_values("timestamp").reset_index(drop=True)
print(f"✅ Loaded {len(df):,} rows for device {df.device_eui.iloc[0]}")

# ── Feature engineering ───────────────────────────────────────────────────────
WINDOW = 8   # 2-hour rolling window (8 × 15min)

df["hour"]       = df.timestamp.dt.hour
df["dayofyear"]  = df.timestamp.dt.dayofyear
df["month"]      = df.timestamp.dt.month
df["sin_hour"]   = np.sin(2 * np.pi * df.hour / 24)
df["cos_hour"]   = np.cos(2 * np.pi * df.hour / 24)
df["sin_doy"]    = np.sin(2 * np.pi * df.dayofyear / 365)
df["cos_doy"]    = np.cos(2 * np.pi * df.dayofyear / 365)

for col in ["soil_moisture_pct", "soil_temp_c", "air_temp_c",
            "humidity_pct", "soc_index"]:
    df[f"{col}_roll_mean"] = df[col].rolling(WINDOW, min_periods=1).mean()
    df[f"{col}_roll_std"]  = df[col].rolling(WINDOW, min_periods=1).std().fillna(0)
    df[f"{col}_diff"]      = df[col].diff().fillna(0)

# Lag features
for lag in [1, 2, 4, 8, 16]:
    df[f"sm_lag{lag}"] = df.soil_moisture_pct.shift(lag).bfill()
    df[f"st_lag{lag}"] = df.soil_temp_c.shift(lag).bfill()

df["vapour_pressure_deficit"] = (
    0.6108 * np.exp(17.27 * df.air_temp_c / (df.air_temp_c + 237.3)) *
    (1 - df.humidity_pct / 100)
)

# Target: soil moisture 4 steps ahead (1 hour)
HORIZON = 4
df["target_sm"]  = df.soil_moisture_pct.shift(-HORIZON)
df["target_soc"] = df.soc_index.shift(-HORIZON)
df = df.dropna().copy()

FEATURES = [
    "soil_moisture_pct", "soil_temp_c", "air_temp_c", "humidity_pct",
    "soc_index", "rainfall_mm", "sin_hour", "cos_hour", "sin_doy", "cos_doy",
    "soil_moisture_pct_roll_mean", "soil_moisture_pct_roll_std",
    "soil_temp_c_roll_mean", "humidity_pct_roll_mean",
    "soil_moisture_pct_diff", "vapour_pressure_deficit",
    "sm_lag1", "sm_lag2", "sm_lag4", "sm_lag8",
    "st_lag1", "st_lag4",
]

X = df[FEATURES].values
y_sm  = df.target_sm.values
y_soc = df.target_soc.values

X_train, X_test, ysm_train, ysm_test, ysoc_train, ysoc_test = \
    train_test_split(X, y_sm, y_soc, test_size=0.2, shuffle=False)

print(f"\n📊 Training on {len(X_train):,} samples, testing on {len(X_test):,}")

# ── Train soil moisture model ─────────────────────────────────────────────────
print("\n🌱 Training Random Forest (Soil Moisture forecast)…")
rf_sm = RandomForestRegressor(
    n_estimators=200, max_depth=12, min_samples_leaf=4,
    n_jobs=-1, random_state=42)
rf_sm.fit(X_train, ysm_train)
sm_pred = rf_sm.predict(X_test)
r2_sm   = r2_score(ysm_test, sm_pred)
mae_sm  = mean_absolute_error(ysm_test, sm_pred)
rmse_sm = np.sqrt(mean_squared_error(ysm_test, sm_pred))
print(f"   R² = {r2_sm:.4f}  |  MAE = {mae_sm:.3f} %  |  RMSE = {rmse_sm:.3f} %")

# ── Train SOC model ───────────────────────────────────────────────────────────
print("🌿 Training Gradient Boosting (SOC index forecast)…")
gb_soc = GradientBoostingRegressor(
    n_estimators=150, max_depth=5, learning_rate=0.08,
    min_samples_leaf=6, random_state=42)
gb_soc.fit(X_train, ysoc_train)
soc_pred_test = gb_soc.predict(X_test)
r2_soc   = r2_score(ysoc_test, soc_pred_test)
mae_soc  = mean_absolute_error(ysoc_test, soc_pred_test)
rmse_soc = np.sqrt(mean_squared_error(ysoc_test, soc_pred_test))
print(f"   R² = {r2_soc:.4f}  |  MAE = {mae_soc:.4f}  |  RMSE = {rmse_soc:.4f}")

# ── Feature importances ────────────────────────────────────────────────────────
importances = dict(zip(FEATURES, rf_sm.feature_importances_))
top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:6]

# ── Rolling forecast for next 48h ─────────────────────────────────────────────
print("\n🔮 Generating 48-hour rolling forecast…")
# Use last 200 rows as seed
seed = df.tail(200)[FEATURES].values.copy()
recent = df.tail(1)[["soil_moisture_pct","soil_temp_c","air_temp_c",
                       "humidity_pct","soc_index","rainfall_mm"]].values[0]

forecast_times   = []
forecast_sm      = []
forecast_soc     = []
forecast_alerts  = []
forecast_actions = []

last_ts = df.timestamp.iloc[-1]

# Build rolling forecast by sliding the last feature row forward
current_features = seed[-1].copy()

for step in range(192):   # 192 × 15min = 48h
    ft = last_ts + timedelta(minutes=15 * (step + 1))
    h  = ft.hour
    doy = ft.timetuple().tm_yday
    month = ft.month

    # Update time features
    current_features[FEATURES.index("sin_hour")] = np.sin(2*np.pi*h/24)
    current_features[FEATURES.index("cos_hour")] = np.cos(2*np.pi*h/24)
    current_features[FEATURES.index("sin_doy")]  = np.sin(2*np.pi*doy/365)
    current_features[FEATURES.index("cos_doy")]  = np.cos(2*np.pi*doy/365)

    sm_hat  = float(rf_sm.predict(current_features.reshape(1,-1))[0])
    soc_hat = float(gb_soc.predict(current_features.reshape(1,-1))[0])
    sm_hat  = np.clip(sm_hat, 5, 90)
    soc_hat = np.clip(soc_hat, 0.1, 0.95)

    # Next-step: propagate predictions as new lag features
    current_features[FEATURES.index("sm_lag1")] = \
        current_features[FEATURES.index("soil_moisture_pct")]
    current_features[FEATURES.index("soil_moisture_pct")] = sm_hat
    current_features[FEATURES.index("soc_index")]         = soc_hat

    forecast_times.append(ft.strftime("%Y-%m-%d %H:%M"))
    forecast_sm.append(round(sm_hat, 2))
    forecast_soc.append(round(soc_hat, 4))

    # Irrigation alert
    if sm_hat < 30:
        alert = "CRITICAL"
        action = "Irrigate immediately — soil moisture critically low"
    elif sm_hat < 40:
        alert = "WARNING"
        action = f"Schedule irrigation in {max(1, int((sm_hat-30)*0.5))}h"
    elif sm_hat > 75:
        alert = "EXCESS"
        action = "Reduce/pause irrigation — risk of waterlogging & SOC leaching"
    else:
        alert  = "OPTIMAL"
        action = "Monitor — conditions optimal for root development"

    forecast_alerts.append(alert)
    forecast_actions.append(action)

# ── Find next optimal irrigation windows ────────────────────────────────────
irr_windows = []
in_window = False
window_start = None
for i, (t, sm, alert) in enumerate(zip(forecast_times, forecast_sm, forecast_alerts)):
    if alert in ("WARNING", "CRITICAL") and not in_window:
        window_start = t
        window_start_sm = sm
        in_window = True
    elif alert not in ("WARNING", "CRITICAL") and in_window:
        irr_windows.append({
            "start": window_start,
            "end":   t,
            "trigger_sm": window_start_sm,
            "recommendation": f"Irrigate from {window_start} to {t}"
        })
        in_window = False
        if len(irr_windows) >= 5:
            break

# ── Historical summary (for charts) ─────────────────────────────────────────
# Last 7 days hourly averages
recent_7d = df[df.timestamp >= df.timestamp.max() - timedelta(days=7)].copy()
recent_7d["hour_ts"] = recent_7d.timestamp.dt.floor("h")
hourly = recent_7d.groupby("hour_ts").agg(
    sm=("soil_moisture_pct","mean"),
    st=("soil_temp_c","mean"),
    at=("air_temp_c","mean"),
    hum=("humidity_pct","mean"),
    soc=("soc_index","mean"),
    rain=("rainfall_mm","sum"),
).reset_index()

# Monthly averages for seasonal chart
monthly = df.groupby("month").agg(
    sm=("soil_moisture_pct","mean"),
    soc=("soc_index","mean"),
    at=("air_temp_c","mean"),
    rain=("rainfall_mm","sum"),
).reset_index()
month_names = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]
monthly["month_name"] = monthly.month.apply(lambda m: month_names[m-1])

# ── ML recommendations ────────────────────────────────────────────────────────
current_sm  = float(df.soil_moisture_pct.iloc[-1])
current_soc = float(df.soc_index.iloc[-1])
current_at  = float(df.air_temp_c.iloc[-1])
current_hum = float(df.humidity_pct.iloc[-1])
month_now   = df.timestamp.iloc[-1].month

# SOC trend (last 30 days vs prev 30)
last30  = df.tail(2880).soc_index.mean()
prev30  = df.tail(5760).head(2880).soc_index.mean()
soc_trend = "improving" if last30 > prev30 + 0.01 else \
            "declining" if last30 < prev30 - 0.01 else "stable"

recommendations = []
if current_sm < 35:
    recommendations.append({
        "priority": "HIGH",
        "category": "Irrigation",
        "action": "Irrigate now — soil moisture below optimal range (35–65%)",
        "benefit": "Prevent crop stress, maintain SOC microbial activity"
    })
if soc_trend == "declining":
    recommendations.append({
        "priority": "HIGH",
        "category": "SOC Management",
        "action": "Apply organic mulch or compost to arrest SOC decline",
        "benefit": "Restore microbial biomass, improve water retention"
    })
if current_at > 38:
    recommendations.append({
        "priority": "MEDIUM",
        "category": "Heat Stress",
        "action": "Consider shade netting or evening irrigation to cool soil",
        "benefit": "Reduce evapotranspiration, protect root zone"
    })
if month_now in [6, 7] and current_sm < 40:
    recommendations.append({
        "priority": "HIGH",
        "category": "Kharif Sowing",
        "action": "Pre-sow irrigation: bring SM to 55–65% before sowing",
        "benefit": "Optimal germination conditions for Kharif crops"
    })
if month_now in [11, 12] and current_sm > 50:
    recommendations.append({
        "priority": "MEDIUM",
        "category": "Rabi Sowing",
        "action": "Good soil conditions for Rabi crop sowing",
        "benefit": "Adequate moisture for wheat / chickpea establishment"
    })
recommendations.append({
    "priority": "LOW",
    "category": "Cover Cropping",
    "action": "Plant leguminous cover crop in inter-season (Apr–May)",
    "benefit": "+0.08–0.15 SOC index improvement over 60 days (N fixation)"
})
recommendations.append({
    "priority": "LOW",
    "category": "Reduced Tillage",
    "action": "Switch to zero-tillage or strip-till for next season",
    "benefit": "Preserve soil structure, reduce SOC oxidation by ~30%"
})

# ── Save all outputs ──────────────────────────────────────────────────────────
output = {
    "generated_at": datetime.now().isoformat(),
    "model_metrics": {
        "soil_moisture": {"r2": round(r2_sm,4),  "mae": round(mae_sm,3),  "rmse": round(rmse_sm,3)},
        "soc_index":     {"r2": round(r2_soc,4), "mae": round(mae_soc,4), "rmse": round(rmse_soc,4)},
    },
    "top_features": [{"name": f, "importance": round(v, 4)} for f,v in top_features],
    "current_state": {
        "timestamp":    str(df.timestamp.iloc[-1]),
        "soil_moisture": round(current_sm, 2),
        "soil_temp":    round(float(df.soil_temp_c.iloc[-1]), 2),
        "air_temp":     round(current_at, 2),
        "humidity":     round(current_hum, 2),
        "soc_index":    round(current_soc, 4),
        "soc_trend":    soc_trend,
    },
    "forecast_48h": {
        "timestamps": forecast_times,
        "soil_moisture": forecast_sm,
        "soc_index": forecast_soc,
        "alerts": forecast_alerts,
        "actions": forecast_actions,
    },
    "irrigation_windows": irr_windows,
    "recommendations": recommendations,
    "historical_7d": {
        "timestamps": [str(t) for t in hourly.hour_ts],
        "soil_moisture": [round(v,2) for v in hourly["sm"]],
        "soil_temp":     [round(v,2) for v in hourly["st"]],
        "air_temp":      [round(v,2) for v in hourly["at"]],
        "humidity":      [round(v,2) for v in hourly["hum"]],
        "soc":           [round(v,4) for v in hourly["soc"]],
        "rainfall":      [round(v,2) for v in hourly["rain"]],
    },
    "monthly_averages": {
        "months": list(monthly.month_name),
        "soil_moisture": [round(v,2) for v in monthly["sm"]],
        "soc_index":     [round(v,4) for v in monthly["soc"]],
        "air_temp":      [round(v,2) for v in monthly["at"]],
        "rainfall":      [round(v,2) for v in monthly["rain"]],
    },
    "dataset_stats": {
        "total_rows": len(df),
        "date_range": [str(df.timestamp.min()), str(df.timestamp.max())],
        "devices": list(pd.read_csv(CSV).device_eui.unique()),
        "avg_soil_moisture": round(float(df.soil_moisture_pct.mean()), 2),
        "avg_soc": round(float(df.soc_index.mean()), 4),
        "avg_air_temp": round(float(df.air_temp_c.mean()), 2),
    }
}

os.makedirs("data", exist_ok=True)
with open("data/forecast_output.json", "w") as f:
    json.dump(output, f, indent=2)

print("\n✅ Forecast saved → data/forecast_output.json")
print(f"\n🔮 Next irrigation windows:")
for w in irr_windows[:3]:
    print(f"   ⚠  {w['recommendation']}")
print(f"\n💡 Top recommendations:")
for r in recommendations[:4]:
    print(f"   [{r['priority']:6}] {r['category']}: {r['action'][:65]}")
print(f"\n📈 Model performance:")
print(f"   Soil Moisture  R²={r2_sm:.4f}  MAE={mae_sm:.2f}%  RMSE={rmse_sm:.2f}%")
print(f"   SOC Index      R²={r2_soc:.4f}  MAE={mae_soc:.4f}  RMSE={rmse_soc:.4f}")
print("\n✅ All outputs ready. Launch the dashboard with: open dashboard.html")
