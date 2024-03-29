from setuptools import find_packages, setup
from pathlib import Path

# Project metadata
NAME = 'minigun-soren-n'
DESCRIPTION = 'A library for property-based testing of Python programs.'
URL = 'https://github.com/soren-n/minigun'
OTHER_URL = {
    "Bug Tracker": 'https://github.com/soren-n/minigun/issues',
}
EMAIL = 'sorennorbaek@gmail.com'
AUTHOR = 'Soren Norbaek'
REQUIRES_PYTHON = '>=3.10'

# Define long description
readme_path = Path('README.md')
with readme_path.open('r', encoding = 'utf-8') as readme_file:
    LONG_DESCRIPTION = '\n%s' % readme_file.read()

# Define version
init_path = Path('minigun/__init__.py')
with init_path.open('r', encoding = 'utf-8') as init_file:
    VERSION = init_file.readline().split(' = ')[1][1:-2]

# Read requirements
requirements_path = Path('requirements.txt')
install_requires = []
with open(requirements_path) as requirements_file:
    install_requires = requirements_file.readlines()

setup(
    name = NAME,
    license = 'GPLv3',
    version = VERSION,
    description = DESCRIPTION,
    long_description = LONG_DESCRIPTION,
    long_description_content_type = 'text/markdown',
    url = URL,
    author = AUTHOR,
    author_email = EMAIL,
    requires_python = REQUIRES_PYTHON,
    install_requires = install_requires,
    packages = find_packages(exclude = ["tests", "docs", "examples"]),
    entry_points = {},
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: MacOS',
        'Operating System :: Microsoft',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10'
    ]
)
