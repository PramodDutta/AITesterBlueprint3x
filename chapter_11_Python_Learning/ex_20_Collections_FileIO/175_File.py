import os

file_path = os.path.join(os.getcwd(),'chapter_11_Python_Learning/ex_20_Collections_FileIO/testdata.txt')
file_data = open(file_path,'r')
print(file_data.read())


