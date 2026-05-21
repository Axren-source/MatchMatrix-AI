import pandas as pd
import pickle
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix


DATASET_FILE = "dataset.csv"
MODEL_FILE = "rf_model.pkl"


FEATURE_COLUMNS = [
    "home_form",
    "away_form",
    "home_goals_avg",
    "away_goals_avg",
    "home_conceded_avg",
    "away_conceded_avg",
    "home_goal_diff_avg",
    "away_goal_diff_avg",
    "home_win_rate",
    "away_win_rate",
    "home_clean_sheet_rate",
    "away_clean_sheet_rate",
    "home_failed_to_score_rate",
    "away_failed_to_score_rate",
    "is_international",
]

TARGET_COLUMN = "result"


def main():
    print("Loading dataset...")
    df = pd.read_csv(DATASET_FILE).dropna()

    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    # ⚡ EXTREME DRAW PENALTY - Weight draws much lower in training
    class_weights = {0: 1.0, 1: 0.35, 2: 1.0}  # Draw weight reduced to 0.35 (was 0.6)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("\nTraining Random Forest (Anti-Draw Bias)...\n")

    # ⚡ IMPROVED HYPERPARAMETERS
    model = RandomForestClassifier(
        n_estimators=300,           # More trees for better accuracy
        max_depth=12,               # Slightly deeper trees
        min_samples_split=5,        # Prevent overfitting
        min_samples_leaf=2,         # Better leaf structure
        random_state=42,
        class_weight=class_weights,  # 🔥 KEY: Penalize draw predictions
        n_jobs=-1                   # Use all CPU cores
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    print(f"\n📊 Accuracy: {accuracy:.2%}")
    
    print("\n📋 Detailed Classification Report:\n", classification_report(
        y_test, y_pred, 
        target_names=["Away Win", "Draw", "Home Win"]
    ))

    # Show confusion matrix to understand draw bias
    print("\n🔍 Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(cm)
    
    # Feature importance
    print("\n⭐ Feature Importance:")
    feature_importance = pd.DataFrame({
        'feature': FEATURE_COLUMNS,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    print(feature_importance.to_string(index=False))

    with open(MODEL_FILE, "wb") as f:
        pickle.dump(model, f)

    print(f"\n✅ Model saved as {MODEL_FILE}")
    print(f"   - Training samples: {len(X_train)}")
    print(f"   - Test samples: {len(X_test)}")
    print(f"   - Classes: Away Win (0), Draw (1), Home Win (2)")


if __name__ == "__main__":
    main()