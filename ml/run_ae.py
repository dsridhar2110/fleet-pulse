"""One-shot: train autoencoder on cached windows, score, save. Kept minimal
so it completes fast in a foreground shell (TF hangs in detached shells here)."""
import numpy as np
import pandas as pd

X = np.load("data/app/ae_windows.npz")["X"]
win = pd.read_parquet("data/app/ae_meta.parquet")

import keras
from keras import layers

keras.utils.set_random_seed(7)
healthy = (win["split"] == "train") & (win["label"] == 0) & (
    win["days_to_failure"].isna() | (win["days_to_failure"] > 14))
Xt = X[healthy.to_numpy()]

model = keras.Sequential([
    layers.Input(shape=(196,)),
    layers.Dense(64, activation="relu"),
    layers.Dense(16, activation="relu"),
    layers.Dense(64, activation="relu"),
    layers.Dense(196, activation="linear"),
])
model.compile(optimizer="adam", loss="mse")
h = model.fit(Xt, Xt, epochs=40, batch_size=256, validation_split=0.1, verbose=0,
              callbacks=[keras.callbacks.EarlyStopping(patience=5, restore_best_weights=True)])
print(f"trained {len(h.history['loss'])} epochs, best val loss {min(h.history['val_loss']):.4f}")

recon = model.predict(X, batch_size=1024, verbose=0)
win["anomaly_score"] = ((X - recon) ** 2).mean(axis=1)
win.drop(columns=["days_to_failure"]).to_parquet("data/app/anomaly_scores.parquet", index=False)
model.save("data/app/autoencoder.keras")
print("saved anomaly_scores.parquet + autoencoder.keras")
