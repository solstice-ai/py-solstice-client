from setuptools import setup

setup(name="solsticeai",
      version="1.0.0",
      packages=[
          "solsticeai"
      ],
      install_requires=[
          "requests",
          "pandas",
          "numpy",
          "pytz",
      ],
      zip_safe=False)
