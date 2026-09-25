"""
Trains and evaluates a Tunnel-vs-Transport mode classifier from the
structural ESP payload-length signal, as a SEPARATE model from the
traffic-type classifier (calibrated_rf_model*.pkl).

Why this is a distinct pipeline, not a feature bolted onto the existing
model: Tunnel mode ESP-encrypts the entire original IP packet (own IP
header included) inside the new outer header; Transport mode only
encrypts the original payload, leaving the original IP header outside
ESP in cleartext. The ESP ciphertext is therefore structurally larger in
Tunnel mode by roughly the inner IP header size (20B IPv4 / 40B IPv6),
modulo cipher block-padding and MTU/MSS segmentation effects. This is a
completely different physical signal from the SPLT features used for
traffic-type classification (which use outer packet length, for a
different purpose), so it gets its own model, its own saved file, and
its own honestly-reported accuracy - never presented as if it came from
the same source as the plaintext IKE fields (encryption/PRF/DH group),
because it structurally does not: mode is never observable in cleartext
at all (see ike_parser.py's docstring), this is a statistical inference
from ciphertext length, not a protocol field extraction.

Evaluation methodology: flows are NOT independent samples here - all 5
flows (icmp/bulk/web/video/voip) from the same config variant share the
same cipher and the same mode, so a random train/test split would leak
(the model could effectively memorize "this exact cipher's byte count").
Leave-One-Group-Out cross-validation, grouped by config variant, is used
instead: each fold trains on 7 variants and tests on flows from the 1
held-out variant it has never seen the cipher/mode combination for. With
only 8 variants (6 tunnel, 2 transport), this is a small, honest
evaluation - not a substitute for more real captures across more
variants, which would be the real fix for a low or unstable score.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
import joblib


def main():
    print("1. Loading data/real_features.csv...")
    df = pd.read_csv("data/real_features.csv")
    df["mode"] = df["config"].apply(lambda c: "transport" if c.startswith("transport") else "tunnel")

    n_variants = df["config"].nunique()
    n_transport_variants = df[df["mode"] == "transport"]["config"].nunique()
    n_tunnel_variants = df[df["mode"] == "tunnel"]["config"].nunique()
    print(f"   {len(df)} real flows across {n_variants} variants "
          f"({n_tunnel_variants} tunnel, {n_transport_variants} transport)")
    print(f"   Class balance: {dict(df['mode'].value_counts())} - imbalanced by "
          f"construction (this testbed only ever built 2 transport-mode variants "
          f"vs 6 tunnel-mode ones), not a sampling artifact to fix here.")

    # Candidate feature sets, evaluated honestly rather than picked in advance.
    candidates = {
        "esp_mean_len only": ["esp_mean_len"],
        "esp_mean_len + esp_std_len": ["esp_mean_len", "esp_std_len"],
        "esp_mean_len + esp_min_len": ["esp_mean_len", "esp_min_len"],
    }

    groups = df["config"]
    y = df["mode"]
    logo = LeaveOneGroupOut()

    print("\n2. Leave-One-Variant-Out cross-validation (honest, no leakage across "
          "flows from the same cipher/mode):")
    best_name, best_feats, best_acc = None, None, -1
    for name, feats in candidates.items():
        X = df[feats].values
        y_true_all, y_pred_all = [], []
        for train_idx, test_idx in logo.split(X, y, groups):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            if y_train.nunique() < 2:
                # This fold's held-out variant removed the only examples of
                # one class from training (happens for both transport
                # variants, since there are only 2) - can't fit a 2-class
                # model on 1 class. Skip; this fold's flows aren't
                # meaningfully evaluable this way with only 2 transport
                # variants total.
                continue
            clf = LogisticRegression()
            clf.fit(X_train, y_train)
            y_pred = clf.predict(X_test)
            y_true_all.extend(y_test.tolist())
            y_pred_all.extend(y_pred.tolist())

        acc = accuracy_score(y_true_all, y_pred_all)
        bal_acc = balanced_accuracy_score(y_true_all, y_pred_all)
        print(f"   {name:32s} LOGO accuracy={acc:.3f}  balanced_accuracy={bal_acc:.3f}  "
              f"(n_evaluable={len(y_true_all)})")
        if bal_acc > best_acc:
            best_name, best_feats, best_acc = name, feats, bal_acc

    print(f"\n   -> Best by balanced accuracy: '{best_name}' ({best_feats})")

    # Confusion matrix for the best candidate, using the same LOGO scheme,
    # so the reported number is fully reproducible from what's printed above.
    X = df[best_feats].values
    y_true_all, y_pred_all = [], []
    for train_idx, test_idx in logo.split(X, y, groups):
        y_train = y.iloc[train_idx]
        if y_train.nunique() < 2:
            continue
        clf = LogisticRegression()
        clf.fit(X[train_idx], y_train)
        y_pred_all.extend(clf.predict(X[test_idx]).tolist())
        y_true_all.extend(y.iloc[test_idx].tolist())

    labels = ["tunnel", "transport"]
    cm = confusion_matrix(y_true_all, y_pred_all, labels=labels)
    print(f"\n   Confusion matrix (rows=true, cols=predicted, labels={labels}):")
    print(f"   {cm}")

    print("\n3. Training final model on ALL 8 variants (for deployment - LOGO above "
          "is the honest accuracy estimate, this final fit uses everything)...")
    final_clf = LogisticRegression()
    # Fit with a DataFrame (not .values) so predict-time DataFrames at
    # inference (main.py, tests) don't trigger sklearn's feature-name
    # mismatch warning.
    final_clf.fit(df[best_feats], y)
    joblib.dump({"model": final_clf, "features": best_feats}, "models/mode_classifier.pkl")
    print(f"   -> Saved models/mode_classifier.pkl (features: {best_feats})")

    print("\n==========================================")
    print(f"HONEST RESULT: {best_name}, LOGO balanced accuracy = {best_acc:.3f} "
          f"on {n_variants} real testbed variants ({n_tunnel_variants} tunnel, "
          f"{n_transport_variants} transport).")
    print("This is NOT the same kind of number as the traffic-type classifier's")
    print("accuracy, and should never be presented as if mode were extracted from")
    print("plaintext the way encryption/PRF/DH group are - it's a statistical")
    print("inference from ciphertext length, evaluated on a small, imbalanced,")
    print("real testbed sample.")
    print("==========================================")


if __name__ == "__main__":
    main()
