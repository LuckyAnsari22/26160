import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.calibration import CalibratedClassifierCV
import shap
import joblib

# Ensure assets directory exists
os.makedirs("docs/assets", exist_ok=True)
os.makedirs("models", exist_ok=True)

MIN_SAMPLES_PER_CLASS_FOR_SPLIT = 5


def main():
    print("1. Loading REAL testbed features (data/real_features.csv)...")
    try:
        df = pd.read_csv("data/real_features.csv")
    except FileNotFoundError:
        print("data/real_features.csv not found. Run feature_extractor.py's "
              "batch_process() against data/raw/dataset_manifest.csv first.")
        return

    print(f"\n2. Per-class sample counts (real flows, 20-packet floor already applied "
          f"by SPLTFeatureExtractor):")
    counts = df["label"].value_counts()
    print(counts.to_string())

    # "email" is not just underrepresented - it is completely absent. Every
    # one of the 8 email captures in the manifest had 10-19 packets (the
    # SMTP-stub generator only ever sends ~5 tiny messages), which is below
    # the 20-packet floor, so SPLTFeatureExtractor discarded all 8 of them.
    # There is no way to train or evaluate this class on real data as this
    # dataset currently stands - reporting that honestly rather than silently
    # dropping it or training a "6-class" model that's actually 5.
    expected_classes = {"icmp", "bulk", "web", "video", "voip", "email"}
    present_classes = set(counts.index)
    missing_classes = expected_classes - present_classes
    if missing_classes:
        print(f"\n   *** MISSING CLASSES (0 real examples, not just few): "
              f"{sorted(missing_classes)} ***")
        print("   Root cause: every capture for this class fell below the "
              "20-packet flow floor - a data-generation limitation, not a "
              "flow-extraction bug. This class is excluded below; any "
              "reported accuracy is only over the classes that actually "
              "have real data.")

    too_few = counts[counts < MIN_SAMPLES_PER_CLASS_FOR_SPLIT]
    if not too_few.empty:
        print(f"\n   *** LOW-SAMPLE CLASSES (< {MIN_SAMPLES_PER_CLASS_FOR_SPLIT} real "
              f"examples): {too_few.to_dict()} ***")

    usable = df[df["label"].isin(counts[counts >= 2].index)].copy()
    dropped_classes = set(df["label"].unique()) - set(usable["label"].unique())
    if dropped_classes:
        print(f"\n   Dropping class(es) with <2 examples entirely (can't "
              f"stratify-split a class with only 1 sample): {dropped_classes}")

    n_total = len(usable)
    n_classes = usable["label"].nunique()
    print(f"\n   *** HONEST SAMPLE-SIZE CAVEAT ***")
    print(f"   Total usable real flows: {n_total} across {n_classes} classes "
          f"({dict(usable['label'].value_counts())})")
    print(f"   This is far too small for a statistically reliable accuracy/F1 "
          f"figure. Each variant contributes exactly ONE real flow per traffic "
          f"type (one 15s capture = one client-server conversation), so more "
          f"variants does not mean more independent samples of the same kind "
          f"of traffic - it means more cipher configs, which barely affects "
          f"SPLT shape. The numbers below are reported as-is, per instruction, "
          f"NOT as a claim that this is a properly-validated model.")

    X = usable.drop(columns=["flow_id", "config", "label", "max_len", "min_len"])
    y = usable["label"]

    # Same 80/20 split, same random_state, same RF hyperparameters as the
    # synthetic pipeline (train_model.py) - unmodified, so the comparison is
    # apples-to-apples and not tuned/cherry-picked to chase a number.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\n   Train split: {len(X_train)} rows {dict(y_train.value_counts())}")
    print(f"   Test split:  {len(X_test)} rows {dict(y_test.value_counts())}")

    print("\n3. Training Random Forest Classifier (same hyperparameters as the "
          "synthetic pipeline - not tuned for this data)...")
    rf = RandomForestClassifier(n_estimators=100, max_depth=8, class_weight='balanced', random_state=42)
    rf.fit(X_train, y_train)

    y_pred = rf.predict(X_test)
    macro_f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
    real_accuracy = accuracy_score(y_test, y_pred)
    print(f"   -> REAL Test Accuracy : {real_accuracy:.4f}  (on n={len(X_test)} test samples)")
    print(f"   -> REAL Test Macro-F1 : {macro_f1:.4f}")
    print("\n   Per-class report:")
    print(classification_report(y_test, y_pred, zero_division=0))

    print("\n4. Applying Confidence Calibration (Platt Scaling)...")
    calibrated_rf = CalibratedClassifierCV(rf, method='sigmoid', cv='prefit')
    calibrated_rf.fit(X_test, y_test)

    joblib.dump(calibrated_rf, "models/calibrated_rf_model_real.pkl")
    print("   -> Saved to models/calibrated_rf_model_real.pkl "
          "(synthetic model at models/calibrated_rf_model.pkl left untouched)")

    print("\n5. Applying SHAP (TreeExplainer)...")
    try:
        explainer = shap.TreeExplainer(rf)
        shap_values = explainer.shap_values(X_test)

        plt.figure(figsize=(10, 6))
        class_idx = 0
        if len(np.shape(shap_values)) == 3:
            shap.summary_plot(shap_values[:, :, class_idx], X_test, show=False)
        else:
            shap.summary_plot(shap_values[class_idx], X_test, show=False)
        plt.tight_layout()
        plt.savefig("docs/assets/shap_summary_real.png")
        plt.close()
        print("   -> Saved docs/assets/shap_summary_real.png "
              "(n is tiny here, treat as illustrative only)")
    except Exception as e:
        print(f"   -> SHAP step skipped: {e}")

    print("\n==========================================")
    print("Real-data ML pipeline run complete.")
    print("==========================================")

    return {
        "real_accuracy": real_accuracy,
        "real_macro_f1": macro_f1,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "class_counts": dict(counts),
        "missing_classes": sorted(missing_classes),
    }


if __name__ == "__main__":
    main()
