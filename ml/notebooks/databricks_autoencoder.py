# %% [markdown]
# # FleetPulse Module 2 on Databricks — Keras autoencoder anomaly detector
#
# **Why this runs here:** deep-learning training belongs on the compute platform,
# not a laptop — and this closes the JD's Keras/TensorFlow ask on the same
# Databricks workspace that ran the feature pipeline.
#
# **Before running (2 minutes):**
# 1. Upload `ae_windows.npz` and `ae_meta.parquet` (from `ml/data/databricks_upload/`)
#    into the existing volume `workspace.default.fleetpulse` (Catalog → fleetpulse →
#    Upload to this volume).
# 2. Import this notebook, attach **Serverless**, **Run all**.
#
# **What it does:** trains a `196 → 64 → 16 → 64 → 196` autoencoder on healthy
# machine-weeks only, scores every machine-week by reconstruction error, and
# benchmarks against the project's baselines. ~3 minutes end to end.
#
# **When done:** download `anomaly_scores.parquet` from the volume back to
# `ml/data/app/` (Catalog → fleetpulse → file → ⋮ → Download).

# %% Check TensorFlow is available
# If this cell FAILS with ImportError: add a new cell above it containing exactly
#   %pip install tensorflow
# run that cell, then Run all again.
import tensorflow as tf
print("tensorflow present:", tf.__version__)

# %% Load the cached windows from the volume
import numpy as np
import pandas as pd

VOL = "/Volumes/workspace/default/fleetpulse"
X = np.load(f"{VOL}/ae_windows.npz")["X"]
win = pd.read_parquet(f"{VOL}/ae_meta.parquet")
print(f"{X.shape[0]:,} windows x {X.shape[1]} dims (14 days x 14 sensors, z-scored per machine)")

# %% Train on healthy train-split windows only
import keras
from keras import layers

keras.utils.set_random_seed(7)
healthy = (win["split"] == "train") & (win["label"] == 0) & (
    win["days_to_failure"].isna() | (win["days_to_failure"] > 14))
X_train = X[healthy.to_numpy()]
print(f"training on {len(X_train):,} healthy train windows")

model = keras.Sequential([
    layers.Input(shape=(X.shape[1],)),
    layers.Dense(64, activation="relu"),
    layers.Dense(16, activation="relu"),      # bottleneck: a fortnight in 16 numbers
    layers.Dense(64, activation="relu"),
    layers.Dense(X.shape[1], activation="linear"),
])
model.compile(optimizer="adam", loss="mse")
hist = model.fit(X_train, X_train, epochs=40, batch_size=256,
                 validation_split=0.1, verbose=2,
                 callbacks=[keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True)])
print(f"stopped after {len(hist.history['loss'])} epochs — best val loss {min(hist.history['val_loss']):.4f}")

# %% Score every machine-week: reconstruction error = anomaly score
from sklearn.metrics import average_precision_score

recon = model.predict(X, batch_size=1024, verbose=0)
win["anomaly_score"] = ((X - recon) ** 2).mean(axis=1)

test = win[win["split"] == "test"]
ae_ap = average_precision_score(test["label"], test["anomaly_score"])

# project baselines (from ml/data/app/metrics.json, same test window & labels)
BASELINES = {
    "Rolling z-score alarm": 0.2019,
    "IsolationForest": 0.0739,
    "XGBoost (calibrated, supervised)": 0.4794,
    "random (prevalence)": 0.0126,
}
print(f"Autoencoder test PR-AUC: {ae_ap:.4f}")
for k, v in BASELINES.items():
    print(f"  {k:<36} {v}")

# %% Save scores back to the volume (download this file afterwards)
win.drop(columns=["days_to_failure"]).to_parquet(f"{VOL}/anomaly_scores.parquet", index=False)
print("wrote", f"{VOL}/anomaly_scores.parquet")
print("→ download it to ml/data/app/anomaly_scores.parquet on the Mac")

# %% Quick visual: do failing machines reconstruct worse?
import matplotlib.pyplot as plt

h, f = test[test["label"] == 0], test[test["label"] == 1]
fig, ax = plt.subplots(figsize=(9, 3.5))
ax.hist(h["anomaly_score"], bins=60, density=True, alpha=.7, label=f"healthy (n={len(h):,})", color="#1F9E78")
ax.hist(f["anomaly_score"], bins=60, density=True, alpha=.7, label=f"fails within 7d (n={len(f)})", color="#D64545")
ax.set_xlabel("reconstruction error"); ax.set_ylabel("density"); ax.legend()
ax.set_title("Failing machines look 'blurry' to a network trained on normal")
plt.show()
