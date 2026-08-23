import pytest

@pytest.mark.reg
def test_anwser1():
    assert 3 == 3

@pytest.mark.smoke
def test_anwser2():
    assert 3 == 3

