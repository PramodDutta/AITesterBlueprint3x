a = 10 # Global

class Person:
    b = 11 # Instance, Class , Attribute...property
    def print_infor(self):
        l = 10 # local l varaible
        print(self.b)

    def talk(self):
        print(self.b)
        print(a)
