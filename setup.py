"""Setup configuration for AutoRXTE."""
from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip() 
        for line in requirements_file.read_text().splitlines() 
        if line.strip() and not line.startswith('#')
    ]

setup(
    name="autorxte",
    version="1.1.0",
    author="AutoRXTE Development Team",
    description="Automated pipeline for RXTE X-ray data analysis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/WizardEternal/AutoRXTE",
    project_urls={
        "Bug Reports": "https://github.com/WizardEternal/AutoRXTE/issues",
        "Source": "https://github.com/WizardEternal/AutoRXTE",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Astronomy",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "autorxte=autorxte.cli.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "autorxte": ["*.yaml"],
    },
)
