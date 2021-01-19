"""
Unit and regression test for the kinope package.
"""

# Import package, test suite, and other packages as needed
import kinope
import pytest
import sys

def test_kinope_imported():
    """Sample test, will always pass so long as import statement worked"""
    assert "kinope" in sys.modules
