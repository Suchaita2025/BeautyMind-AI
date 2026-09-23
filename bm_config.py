import os, random, sqlite3
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
P = {k: f"{BASE}/{k}" for k in ["data", "models", "db", "skin_data", "outputs", "app"]}
for _d in P.values():
    os.makedirs(_d, exist_ok=True)
DB_PATH = f"{P['db']}/beautymind.db"
SEED = 42

def set_seed(s=SEED):
    random.seed(s); np.random.seed(s)
    os.environ["PYTHONHASHSEED"] = str(s)

def get_conn():
    return sqlite3.connect(DB_PATH)