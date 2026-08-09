class Dog:
    name = None
    breed = None
    def __init__(self):
        print("I will be called")

chow_ref = Dog()
mow_ref = Dog()

print(chow_ref.name)
print(mow_ref.name)
