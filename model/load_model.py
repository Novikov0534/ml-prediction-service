import pickle


def load_model(path: str):
    """Load a model from a trusted local pickle file."""
    with open(path, "rb") as file:
        return pickle.load(file)
