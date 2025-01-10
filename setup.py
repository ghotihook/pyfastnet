from setuptools import setup, find_packages

setup(
    name="fastnet_decoder",
    version="0.1.0",
    description="Library for decoding FastNet protocol frames",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Alex Salmon",
    author_email="alex@ivila.net",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[],  # Add dependencies if needed
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)