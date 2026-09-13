from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"

def load_data():
    return {
        "requests": pd.read_csv(DATASET / "requests.csv"),
        "profiles": pd.read_csv(DATASET / "financial_profiles.csv"),
        "events": pd.read_csv(DATASET / "financial_events.csv"),
        "payment_options": pd.read_csv(DATASET / "request_payment_options.csv"),
        "exchange_rates": pd.read_csv(DATASET / "exchange_rates.csv"),
        "messages": pd.read_csv(DATASET / "messages.csv"),
        "images": pd.read_csv(DATASET / "images.csv")
    }

if __name__ == "__main__":
    data = load_data()

    for name, df in data.items():
        print(f"{name}: {df.shape}")
        print(df.columns.tolist())
        print()