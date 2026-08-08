# # SET
# # Collection of Unique
# # {} - parenthesis

# list_of_unique_items = {1, 2, 3, 4, 4, 5, 5}
# print(list_of_unique_items)

# list1 = [45.2, 33, 33, 45, 21]
# set1 = set(list1)
# print(set1)

# t = ("TheTestingAcademy", "for", "TheTestingAcademy")
# print(t)
# print(set(t))

# mixed = {1, "QA", False, 3.5}
mixed = {1, "QA", True, 3.5}
# print(mixed)

# empty = set()
# print(type(empty))

# for item in mixed:
#     print(item)


# mixed.add(10)
# print(mixed)
# mixed.remove(10)
# print(mixed)


a = {1, 2, 3}
b = {3, 4, 5}

# print(a | b)
# print(a.union(b))


# print(a & b)            # {3}
# print(a.intersection(b))


# print(a - b)
print(b - a)  # Keep elements from b that are not present in a.

set1 = {1, 2, 3}
set2 = {4, 5, 6}
my_set = set1.union(set2)
print(my_set)

my_set = set1.intersection(set2)
print(my_set)

my_set = set1.difference(set2)
print(my_set)

my_set = set2.difference(set1)
print(my_set)
