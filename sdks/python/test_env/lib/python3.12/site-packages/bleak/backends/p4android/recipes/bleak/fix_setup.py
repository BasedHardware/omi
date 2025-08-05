from setuptools import find_packages, setup

VERSION = "[VERSION]"  # Version will be filled in by the bleak recipe
NAME = "bleak"

setup(
    name=NAME,
    version=VERSION,
    packages=find_packages(exclude=("tests", "examples", "docs")),
)
