from pathlib import Path
import pickle
import json

from sklearn.datasets import load_wine
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

features, labels = load_wine(return_X_y=True)
model = RandomForestClassifier(n_estimators=100, random_state=42)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(model, features, labels, cv=cv, scoring="accuracy")
model.fit(features, labels)

output = Path(__file__).with_name("model.pkl")
with output.open("wb") as file:
    pickle.dump(model, file)

evaluation = {
    "method": "stratified_cv5", "accuracy": float(scores.mean()),
    "fold_scores": scores.tolist(), "samples": len(labels),
    "random_state": 42,
}
output.with_name("evaluation.json").write_text(json.dumps(evaluation, indent=2))
print(f"Cross-validation accuracy: {evaluation['accuracy']:.4f}")

print(f"Model saved: {output}")
print(f"Features: {model.n_features_in_}; classes: {model.classes_.tolist()}")
