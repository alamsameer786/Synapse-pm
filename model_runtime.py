"""Compatibility classes for SynapsePM v25 Kaggle joblib artifacts.
Keep behavior identical to the training script used to create the pickles.
"""
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler

WINDOWS = (5, 10, 20)
MAX_FEATURES = 100

class FastFeatureEngineer:
    def __init__(self, windows=WINDOWS, max_features=MAX_FEATURES):
        self.windows = tuple(windows)
        self.max_features = int(max_features)
        self.base_features = []
        self.selected_features = []

    def _create(self, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        out = pd.DataFrame(index=work.index)
        for col in self.base_features:
            out[col] = pd.to_numeric(work[col], errors="coerce").astype(float)
        if 'engine_id' in work.columns and 'time_cycles' in work.columns:
            work_sorted = work.sort_values(['engine_id', 'time_cycles'])
            for col in self.base_features:
                g = work_sorted.groupby('engine_id', sort=False)[col]
                for w in self.windows:
                    out[f"{col}_mean_{w}"] = g.transform(lambda s: s.rolling(w, min_periods=1).mean())
                    out[f"{col}_std_{w}"] = g.transform(lambda s: s.rolling(w, min_periods=2).std())
        out = out.replace([np.inf, -np.inf], np.nan)
        out = out.reindex(df.index)
        return out.fillna(0.0)

    def fit(self, train_df: pd.DataFrame, base_features):
        self.base_features = list(base_features)
        X = self._create(train_df)
        variances = X.var(axis=0).fillna(0.0)
        candidates = variances[variances > 1e-10].index.tolist()
        if not candidates:
            self.selected_features = self.base_features[:self.max_features]
            return self
        if len(candidates) > self.max_features:
            self.selected_features = variances.loc[candidates].nlargest(self.max_features).index.tolist()
        else:
            self.selected_features = candidates
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        X = self._create(df)
        available = [c for c in self.selected_features if c in X.columns]
        if not available:
            available = self.base_features[:self.max_features]
        return X[available].copy()

class FastPreprocessor:
    def __init__(self):
        self.feature_names = []
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = RobustScaler()

    def fit(self, X: pd.DataFrame):
        self.feature_names = list(X.columns)
        Xv = X[self.feature_names].to_numpy(dtype=float)
        Xi = self.imputer.fit_transform(Xv)
        Xi = np.nan_to_num(Xi, nan=0.0, posinf=0.0, neginf=0.0)
        self.scaler.fit(Xi)
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        Xv = X[self.feature_names].to_numpy(dtype=float)
        Xi = self.imputer.transform(Xv)
        Xi = np.nan_to_num(Xi, nan=0.0, posinf=0.0, neginf=0.0)
        return self.scaler.transform(Xi).astype(np.float32)
