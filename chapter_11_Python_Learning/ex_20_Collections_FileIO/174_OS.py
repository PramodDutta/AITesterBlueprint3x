import os
print(os.getcwd())
full_path = os.path.join(os.getcwd(), "chapter_11_Python_Learning/ex_20_Collections/pramod.txt")
print(full_path)

file = open(full_path, 'r')
print(file.read())