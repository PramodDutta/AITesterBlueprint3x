
class Car:
    def __init__(self):
        self.public_pramod = "pramod"
        self._protected_baby = "pass123"
        self.__private_baby = "pass123"

    def nany(self):
        self.__password_yogesh_private = "345"

object_ref = Car()
print(object_ref.public_pramod)

object_ref.nany()
# print(object_ref.__password_yogesh_private) - Not alloaes ecap