a = 10
class Counter:
    counter = 0  # class attribute, shared by all

    def __init__(self, name):
        self.name = name  # public
        self.__name_private = name  # private
        self._name_protected = name  # private

    @classmethod
    def total(cls):                # class method
        return cls.count

    @staticmethod
    def is_valid(name):            # static method
        return bool(name.strip())