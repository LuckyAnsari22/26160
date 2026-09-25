import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score, accuracy_score, confusion_matrix
from sklearn.calibration import CalibratedClassifierCV, CalibrationDisplay
import shap
import joblib

# Ensure assets directory exists
os.makedirs("docs/assets", exist_ok=True)
os.makedirs("models", exist_ok=True)

def main():
    print("1. Loading Synthetic Lab Features (features.csv)...")
    try:
        df = pd.read_csv("data/features.csv")
    except FileNotFoundError:
        print("features.csv not found. Please run generate_synthetic_features.py first.")
        return

    # Prepare features and labels
    # Drop non-predictive columns and perfectly collinear max/min len for standard SPLT
    X = df.drop(columns=["flow_id", "config", "label", "max_len", "min_len"])
    y = df["label"]
    
    # Split 80/20
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    print("\n2. Training Random Forest Classifier...")
    # Hyperparameter Justification:
    # - n_estimators=100: Standard sufficient ensemble size for 6 classes.
    # - max_depth=8: Prevent overfitting on the extremely clean synthetic lab data. SPLT features don't need deep trees.
    # - class_weight='balanced': Recommended for network traffic where bulk/video often dwarfs ICMP/VoIP in real captures.
    rf = RandomForestClassifier(n_estimators=100, max_depth=8, class_weight='balanced', random_state=42)
    rf.fit(X_train, y_train)
    
    # Test Split Evaluation
    y_pred = rf.predict(X_test)
    macro_f1 = f1_score(y_test, y_pred, average='macro')
    lab_accuracy = accuracy_score(y_test, y_pred)
    print(f"   -> Lab Test Accuracy : {lab_accuracy:.4f}")
    print(f"   -> Lab Test Macro-F1 : {macro_f1:.4f}")
    
    print("\n3. Validating Generalization on External Data (ISCXVPN2016 Sim)...")
    # Generate the ISCX validation set if it doesn't exist
    from generate_iscx_features import generate_iscx_features
    generate_iscx_features(num_samples_per_class=30)
    
    df_iscx = pd.read_csv("data/iscx_features.csv")
    X_iscx = df_iscx.drop(columns=["flow_id", "config", "label", "max_len", "min_len"])
    y_iscx = df_iscx["label"]
    
    y_pred_iscx = rf.predict(X_iscx)
    iscx_accuracy = accuracy_score(y_iscx, y_pred_iscx)
    accuracy_delta = lab_accuracy - iscx_accuracy
    
    print(f"   -> ISCX Generalization Accuracy: {iscx_accuracy:.4f}")
    print(f"   -> Accuracy Drop (Delta)       : -{accuracy_delta:.4f} (Expected due to WAN jitter)")
    
    print("\n4. Applying Confidence Calibration (Platt Scaling)...")
    # Calibrate the model so `.predict_proba()` outputs true probabilities, reducing false alert fatigue
    calibrated_rf = CalibratedClassifierCV(rf, method='sigmoid', cv='prefit')
    calibrated_rf.fit(X_test, y_test)
    
    # Save Model
    joblib.dump(calibrated_rf, "models/calibrated_rf_model.pkl")
    
    # Generate Calibration Curve (using VoIP as target class for the binary plot)
    y_test_binary = (y_test == 'voip').astype(int)
    y_prob = calibrated_rf.predict_proba(X_test)
    voip_idx = list(calibrated_rf.classes_).index('voip')
    voip_probs = y_prob[:, voip_idx]
    
    fig, ax = plt.subplots(figsize=(8, 6))
    CalibrationDisplay.from_predictions(y_test_binary, voip_probs, n_bins=10, ax=ax, name="Calibrated RF (VoIP)")
    plt.title("Confidence Calibration Curve (Platt Scaling)")
    plt.savefig("docs/assets/calibration_curve.png")
    plt.close()
    print("   -> Saved calibration curve to docs/assets/calibration_curve.png")
    
    print("\n5. Applying SHAP (TreeExplainer)...")
    # SHAP requires the base tree model, not the Calibrated wrapper
    explainer = shap.TreeExplainer(rf)
    
    # Calculate SHAP values for the test set
    shap_values = explainer.shap_values(X_test)
    
    # Generate a waterfall chart for one instance of VoIP
    # Find a VoIP sample in X_test
    voip_indices = np.where(y_test == 'voip')[0]
    if len(voip_indices) > 0:
        idx = voip_indices[0]
        # For tree explainer in shap 0.40+, shap_values is a list for classification
        # shap_values[class_idx] gives the values for that class
        
        # Create an Explanation object for the waterfall plot
        class_idx = list(rf.classes_).index('voip')
        sv = shap_values[:, :, class_idx] if len(np.shape(shap_values)) == 3 else shap_values[class_idx]
        
        exp = shap.Explanation(values=sv[idx], 
                               base_values=explainer.expected_value[class_idx], 
                               data=X_test.iloc[idx].values, 
                               feature_names=X_test.columns.tolist())
        
        plt.figure(figsize=(10, 6))
        shap.plots.waterfall(exp, show=False)
        plt.tight_layout()
        plt.savefig("docs/assets/shap_waterfall_voip.png")
        plt.close()
        print("   -> Saved SHAP waterfall chart to docs/assets/shap_waterfall_voip.png")
    
    # Save a summary plot as well
    plt.figure(figsize=(10, 6))
    if len(np.shape(shap_values)) == 3:
        shap.summary_plot(shap_values[:,:,class_idx], X_test, show=False)
    else:
        shap.summary_plot(shap_values[class_idx], X_test, show=False)
    plt.tight_layout()
    plt.savefig("docs/assets/shap_summary.png")
    plt.close()
    
    print("\n==========================================")
    print("ML Pipeline Execution Complete.")
    print("==========================================")
    
if __name__ == "__main__":
    main()
