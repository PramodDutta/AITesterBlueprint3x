import pytest

@pytest.mark.smoke
def test_method2():
    print("test1")
    assert 1-1 == 2

@pytest.mark.regression
def test_login():
    print("test2")
    assert 1 + 1 == 2