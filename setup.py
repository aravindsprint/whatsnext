from setuptools import setup, find_packages

setup(
    name="whatsnext",
    version="1.0.0",
    author="Aravind Govindaraj",
    author_email="aravindsprint@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["requests>=2.28.0"],
)
