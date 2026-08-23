import csv
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, 'TD.csv')

with open(file_path) as csvfile:
    reader = csv.reader(csvfile)
    next(reader)  # skip header row
    for col in reader:
        print(col[0], col[1], sep="|")