from pathlib import Path
import pickle

from sklearn.datasets import load_wine
from sklearn.ensemble import RandomForestClassifier

features, labels = load_wine(return_X_y=True)
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(features, labels)

output = Path(__file__).with_name("model.pkl")
with output.open("wb") as file:
    pickle.dump(model, file)

print(f"Model saved: {output}")
print(f"Features: {model.n_features_in_}; classes: {model.classes_.tolist()}")
