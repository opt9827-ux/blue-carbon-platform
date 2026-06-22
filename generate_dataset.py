"""
BhoomiChain Dataset Generator
==============================
Generates a realistic 1-year LoRaWAN / NB-IoT agricultural sensor dataset.
Mimics Dragino NB8-20 / LHT65 sensor packets for Telangana India farmland.

Fields generated (per 15-min epoch):
  timestamp, device_eui, gateway_id, rssi, snr, spreading_factor,
  soil_moisture_pct, soil_temp_c, air_temp_c, humidity_pct,
  battery_mv, lora_fcnt, payload_hex, soc_index, rainfall_mm

Run: python generate_dataset.py
"""

import pandas as pd
import numpy as np
import hashlib, json, os
from datetime import datetime, timedelta

np.random.seed(42)

# ── Config ──────────────────────────────────────────────────────────────────
START      = datetime(2024, 1, 1, 0, 0, 0)
INTERVALS  = 365 * 24 * 4          # 15-min steps in 1 year = 35,040
DEVICE_EUIS = ["70B3D57ED006A1F2", "70B3D57ED006A1F3", "70B3D57ED006A1F4"]
GATEWAYS    = ["A84041FFFF3E5D28", "A84041FFFF3E5D29"]

# Telangana seasonal calendar (approximate)
# Kharif:  Jun-Oct  (sowing Jun, harvest Oct-Nov)  → high moisture needs
# Rabi:    Nov-Mar  (sowing Nov, harvest Mar-Apr)   → moderate moisture
# Summer:  Apr-May                                  → hot, dry, stress

def seasonal_base(month):
    """Return (soil_moisture_base, rainfall_prob, air_temp_base)"""
    if   month in [6,7,8,9,10]:   return 52.0, 0.25, 30.0   # Kharif / Monsoon
    elif month in [11,12,1,2,3]:  return 38.0, 0.05, 24.0   # Rabi / cool-dry
    else:                          return 22.0, 0.02, 37.0   # Summer / hot-dry

def diurnal_temp(hour):
    return 4.5 * np.sin(np.pi * (hour - 5) / 12)

def encode_lora_payload(sm, st, at, hum, bat):
    """Encode sensor values into a realistic 11-byte LoRaWAN payload hex string."""
    sm_i  = int(np.clip(sm,  0, 100) * 10)
    st_i  = int(np.clip(st, -20, 80) * 10 + 200)
    at_i  = int(np.clip(at, -20, 80) * 10 + 200)
    hum_i = int(np.clip(hum, 0, 100) * 10)
    bat_i = int(np.clip(bat, 2000, 4200))
    raw = (
        sm_i.to_bytes(2,'big') +
        st_i.to_bytes(2,'big') +
        at_i.to_bytes(2,'big') +
        hum_i.to_bytes(2,'big') +
        bat_i.to_bytes(2,'big') +
        b'\x01'
    )
    return raw.hex().upper()

def compute_soc_index(sm, st, hum, rainfall):
    """
    Empirical SOC proxy index (0.0 – 1.0) based on:
    moisture × temp × humidity interactions, calibrated for Vertisol.
    """
    sm_norm  = np.clip(sm  / 60.0, 0, 1)
    st_norm  = 1 - np.clip((st - 15) / 35.0, 0, 1)  # cooler → better SOC
    hum_norm = np.clip(hum / 80.0, 0, 1)
    rain_bonus = 0.05 if rainfall > 5 else 0.0
    soc = 0.45 * sm_norm + 0.30 * st_norm + 0.20 * hum_norm + rain_bonus
    return round(float(np.clip(soc, 0, 1)), 4)

# ── Generate rows ─────────────────────────────────────────────────────────────
rows = []
ts   = START

# State variables for each device
state = {eui: {"soil_moisture": 40.0, "battery": 3700, "fcnt": 0}
         for eui in DEVICE_EUIS}

for step in range(INTERVALS):
    month = ts.month
    hour  = ts.hour
    doy   = ts.timetuple().tm_yday  # day-of-year 1–365

    sm_base, rain_prob, at_base = seasonal_base(month)

    # Rainfall event
    rainfall = float(np.random.exponential(8) if np.random.rand() < rain_prob else 0)
    rainfall = round(min(rainfall, 80), 2)

    for eui in DEVICE_EUIS:
        s = state[eui]
        dev_offset = DEVICE_EUIS.index(eui) * 1.5   # spatial offset

        # Air temperature
        at = at_base + diurnal_temp(hour) + np.random.normal(0, 0.8) + dev_offset * 0.3

        # Humidity (inversely related to temp, higher in monsoon)
        hum_base = 75 if month in [6,7,8,9] else 55
        hum = hum_base - 0.4 * diurnal_temp(hour) + np.random.normal(0, 3)
        hum = np.clip(hum, 20, 99)

        # Soil moisture: drifts toward seasonal base, affected by rain/evaporation
        rain_effect = rainfall * 0.6
        evap_rate   = max(0, (at - 22) * 0.05) + 0.15   # %/15min
        s["soil_moisture"] += rain_effect - evap_rate
        s["soil_moisture"] += np.random.normal(0, 0.2)   # sensor noise
        s["soil_moisture"]  = np.clip(s["soil_moisture"], 8, 85)
        sm = s["soil_moisture"] + dev_offset * 0.5

        # Soil temperature tracks air temp with lag
        st = at * 0.72 + 8.5 + np.random.normal(0, 0.4)

        # Battery drain
        s["battery"] -= np.random.uniform(0.02, 0.08)
        if s["battery"] < 2400:
            s["battery"] = 3700  # replaced
        bat = s["battery"]

        # LoRa RF params
        sf   = int(np.random.choice([7, 8, 9, 10], p=[0.45, 0.30, 0.15, 0.10]))
        rssi = int(np.random.normal(-95, 8))
        snr  = round(float(np.random.normal(6.5, 3)), 1)
        gw   = np.random.choice(GATEWAYS)

        s["fcnt"] += 1
        payload = encode_lora_payload(sm, st, at, hum, bat)
        soc     = compute_soc_index(sm, st, hum, rainfall)

        rows.append({
            "timestamp":         ts.strftime("%Y-%m-%d %H:%M:%S"),
            "device_eui":        eui,
            "gateway_id":        gw,
            "spreading_factor":  sf,
            "rssi_dbm":          rssi,
            "snr_db":            snr,
            "soil_moisture_pct": round(float(sm), 2),
            "soil_temp_c":       round(float(st), 2),
            "air_temp_c":        round(float(at), 2),
            "humidity_pct":      round(float(hum), 2),
            "rainfall_mm":       rainfall,
            "battery_mv":        int(bat),
            "lora_fcnt":         s["fcnt"],
            "payload_hex":       payload,
            "soc_index":         soc,
        })

    ts += timedelta(minutes=15)

# ── Save ───────────────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)
df = pd.DataFrame(rows)
df.to_csv("data/bhoomichain_lorawan_dataset.csv", index=False)
print(f"✅  Dataset saved: data/bhoomichain_lorawan_dataset.csv")
print(f"    Rows : {len(df):,}  |  Columns : {len(df.columns)}")
print(f"    Date range : {df.timestamp.iloc[0]}  →  {df.timestamp.iloc[-1]}")
print(f"    Devices : {df.device_eui.unique().tolist()}")
print(df.describe().round(2).to_string())
