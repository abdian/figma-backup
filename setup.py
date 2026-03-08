from setuptools import setup, find_packages

setup(
    name="figma-backup",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
        "rich>=13.0.0",
        "click>=8.1.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "figma-backup=figma_backup.cli:cli",
        ],
    },
    python_requires=">=3.8",
    description="Complete Figma account backup tool",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/abdian/figma-backup",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: System :: Archiving :: Backup",
    ],
)
