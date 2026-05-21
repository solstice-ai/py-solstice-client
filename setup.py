from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(name="solsticeai",
      version="1.0.2",
      description="Solstice AI - Client Implementation to Access Lakeside Services",
      long_description=long_description,
      long_description_content_type="text/markdown",
      url="https://github.com/solstice-ai/py-solstice-client",
      author="Peter Ilfrich",
      author_email="peter@solstice-ai.com",
      license="Apache-2.0",
      packages=[
          "solsticeai"
      ],
      install_requires=[
          "requests",
          "pandas",
          "numpy",
          "pytz",
      ],
      tests_require=[
        "pytest",
      ],
      zip_safe=False)
