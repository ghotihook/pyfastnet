from setuptools import setup, find_packages

setup(
    name="pyfastnet",
    version="1.0.2",  # Ensure this matches your intended version
    author="Alex Salmon",
    author_email="alex@ivila.net",
    description="A Python library for decoding FastNet protocol data streams.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ghotihook/pyfastnet",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[]  # Add dependencies if required
)