import pandas as pd
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, 'TD.csv')

df = pd.read_csv(file_path)
print(df)