from collections import *
# list -> coCollection of items
# tuple -> list but can't modified
# set ->  no duplicates
# dict -> key and value pair

# ++ version of the in built, better version of the inbuilt
# t = tuple(34, True, 123)


# info = namedtuple('info', ['name', 'age', 'ismarried', 'number'])
# t = info('pramod', 34, True, 9.8)
# print(t)

# print(t.name)
# print(t.age)
# print(t.ismarried)
# print(t.number)

c = Counter('abcdeabcdabcaba')  # count elements from a string
print(c.most_common(3))
print(c.total())

from collections import defaultdict

groups = defaultdict(list)
for word in ["apple", "avocado", "banana"]:
    groups[word[0]].append(word)

counts  = defaultdict(int)   # missing -> 0
uniques = defaultdict(set)   # missing -> set()
nested  = defaultdict(lambda: defaultdict(int))
print(counts)