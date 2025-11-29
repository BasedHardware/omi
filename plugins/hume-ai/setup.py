from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="omi-audio-emotion-analysis",
    version="1.0.0",
    author="Livia Ellen",
    author_email="",
    description="Real-time emotion analysis for Omi audio using Hume AI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/liviaellen/omi",
    py_modules=["main", "app"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
)
