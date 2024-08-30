from solver.workflow.is_test_file import is_test_file


def test_is_test_file():
    assert is_test_file("test/test_file.py")
    assert is_test_file("tests/test_file.py")
    assert is_test_file("testing/test_file.py")
    assert is_test_file("tests/admin_inlines/tests.py")
    assert is_test_file("test_file_test.py")
    assert is_test_file("test_file.py")
    assert is_test_file("testcases/test_file.py")
    assert is_test_file("test/test_file.py")
    assert is_test_file("src/test_file.py")
    assert is_test_file("src/test_file_test.py")
    assert is_test_file("src/tests/test_file.py")
    assert is_test_file("src/testing/test_file.py")
    assert is_test_file("src/testcases/test_file.py")
    assert is_test_file("testcases/mymodule.py")


def test_is_not_test_file():
    assert not is_test_file("src/main.py")
    assert not is_test_file("src/utils.py")
    assert not is_test_file("src/test.py")
    assert not is_test_file("src/_pytest.py")
    assert not is_test_file("src/_pytest/skipping.py")
    assert not is_test_file("_pytest/skipping_test.py")
    assert not is_test_file("src/_pytest/pathlib.py")
