from setuptools import setup, find_packages

setup(
    name="odevalidator",
    version="0.1",
    author_email="fake@email.com",
    description="ODE Data Validation Library",
    py_modules = ['odevalidator', 'odevalidator.result', 'odevalidator.sequential'],
    packages=find_packages()
)
