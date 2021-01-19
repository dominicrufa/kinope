"""
kinope
an enhanced sampling and free energy calculation library for protein conformational reorganization
"""

# Add imports here
from .kinope import *

# Handle versioneer
from ._version import get_versions
versions = get_versions()
__version__ = versions['version']
__git_revision__ = versions['full-revisionid']
del get_versions, versions
