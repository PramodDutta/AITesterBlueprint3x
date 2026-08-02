def before_after_ui_test(func):
     def wrapper():
          print("Before the TC code execute!")
          func()
          print("After the TC Done")
     return wrapper()


@before_after_ui_test
def test_ui():
     print("Hi, I am testing a UI Test")