class MathClass:
    # def add(self, a,b):
    #     return a+b

    def add(self,a,b):
        return a-b

obj_ref = MathClass()
print(obj_ref.add(3,4))
print(obj_ref.add(3.12,4.45))