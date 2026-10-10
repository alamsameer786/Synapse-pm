import joblib
import pandas as pd
import numpy as np
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

# ===========================================================
# CONFIGURATION
# ===========================================================

MODEL_PATH = r"C:\Users\DELL\OneDrive\Desktop\Synapse PM\services\training\models\current_model\synapse_model.pkl"

DATASET_PATH = r"C:\Users\DELL\OneDrive\Desktop\Synapse PM\data_fixed.xlsx"

TARGET_COLUMN = "RUL_hours"

# Columns that must NEVER be used as model input features because they are
# derived from / leak information about the target (RUL_hours).
LEAKAGE_COLS = [
    "RUL_hours",
    "health_score",
    "failure_probability",
    "condition_label",
    "degradation_stage",
    "maintenance_event",
    "failure_event",
    "row_id",
    "machine_id",
    "machine_type",
    "timestamp",
]

# ===========================================================
# LOAD MODEL
# ===========================================================

print("=" * 60)
print("Loading model...")
print("=" * 60)

model = joblib.load(MODEL_PATH)

print("Model Loaded Successfully")
print(type(model))

# ===========================================================
# LOAD DATASET
# ===========================================================

print("\nLoading dataset...")

df = pd.read_excel(DATASET_PATH)

# Defensive cleanup: strip stray whitespace from column names, which is a
# common cause of "KeyError" when a CSV has been round-tripped through Excel.
df.columns = df.columns.str.strip()

print("Dataset Shape:", df.shape)
print("\nColumns:")
print(df.columns.tolist())

# ===========================================================
# VALIDATE TARGET COLUMN EXISTS
# ===========================================================

if TARGET_COLUMN not in df.columns:
    raise ValueError(
        f"\nTarget column '{TARGET_COLUMN}' not found in dataset.\n"
        f"Available columns are:\n{df.columns.tolist()}\n"
        f"-> Check that DATASET_PATH points to the correct file/sheet, "
        f"and that the column name matches exactly (case + spelling)."
    )

# ===========================================================
# REMOVE NON-FEATURE / LEAKAGE COLUMNS
# ===========================================================

X = df.drop(columns=LEAKAGE_COLS, errors="ignore")
y = df[TARGET_COLUMN]

# Drop rows where the target is missing (can't score those)
valid_mask = y.notna()
if (~valid_mask).any():
    print(f"\nDropping {(~valid_mask).sum()} rows with missing target values.")
X = X.loc[valid_mask].reset_index(drop=True)
y = y.loc[valid_mask].reset_index(drop=True)

print("\nFeatures:", X.shape)
print("Target:", y.shape)

# ===========================================================
# FEATURE ORDER / ALIGNMENT CHECK
# ===========================================================

expected_n = getattr(model, "n_features_in_", None)
feature_names = None

if hasattr(model, "feature_names_in_"):
    feature_names = list(model.feature_names_in_)

if feature_names is not None:
    missing_in_data = [c for c in feature_names if c not in X.columns]
    extra_in_data = [c for c in X.columns if c not in feature_names]

    if missing_in_data:
        raise ValueError(
            f"\nDataset is missing columns the model expects: {missing_in_data}\n"
            f"Dataset columns available (after dropping target/leakage): "
            f"{X.columns.tolist()}"
        )

    if extra_in_data:
        print(f"\nDropping {len(extra_in_data)} extra columns not used by the model: {extra_in_data}")

    print("\nReordering columns to match model's training order...")
    X = X[feature_names]

elif expected_n is not None:
    print("\nModel has no stored feature names; checking feature COUNT only.")
    if X.shape[1] != expected_n:
        raise ValueError(
            f"Feature mismatch! Model expects {expected_n} features but "
            f"dataset (after dropping target/leakage columns) has {X.shape[1]}.\n"
            f"Dataset feature columns: {X.columns.tolist()}"
        )
else:
    print("\nModel exposes no feature metadata; proceeding as-is (unsafe if order differs).")

# ===========================================================
# PREDICTION
# ===========================================================

print("\nPredicting...")

predictions = model.predict(X)

# ===========================================================
# METRICS
# ===========================================================

mae = mean_absolute_error(y, predictions)
mse = mean_squared_error(y, predictions)
rmse = np.sqrt(mse)
r2 = r2_score(y, predictions)

# Guard against divide-by-zero in MAPE when RUL_hours == 0 (failure rows)
nonzero_mask = y != 0
if nonzero_mask.any():
    mape = np.mean(np.abs((y[nonzero_mask] - predictions[nonzero_mask]) / y[nonzero_mask])) * 100
else:
    mape = np.nan

# ===========================================================
# RESULTS
# ===========================================================

print("\n" + "=" * 60)
print("MODEL PERFORMANCE")
print("=" * 60)
print(f"MAE  : {mae:.2f}")
print(f"MSE  : {mse:.2f}")
print(f"RMSE : {rmse:.2f}")
print(f"R\u00b2   : {r2:.4f}")
print(f"MAPE : {mape:.2f}%  (rows with target=0 excluded)")
print("=" * 60)

# ===========================================================
# SAMPLE PREDICTIONS
# ===========================================================

result = pd.DataFrame({
    "Actual": y,
    "Predicted": predictions
})

print("\nFirst 10 Predictions:\n")
print(result.head(10))