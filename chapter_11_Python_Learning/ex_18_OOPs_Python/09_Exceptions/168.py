try:
    data = open("test.json").read()
except FileNotFoundError as fnf:
    print(fnf)