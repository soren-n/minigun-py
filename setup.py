from setuptools import find_packages, setup, Command
from pathlib import Path
import sys
import os

# Project metadata
NAME = 'minigun-soren-n'
DESCRIPTION = 'A library for property based testing of Python programs.'
URL = 'https://github.com/soren-n/minigun'
OTHER_URL = {
    "Bug Tracker": 'https://github.com/soren-n/minigun/issues',
}
EMAIL = 'sorennorbaek@gmail.com'
AUTHOR = 'Soren Norbaek'
REQUIRES_PYTHON = '>=3.10.1'
REQUIRED = ['tqdm']

# Define long description
readme_path = Path('README.md')
with readme_path.open('r', encoding = 'utf-8') as readme_file:
    LONG_DESCRIPTION = '\n%s' % readme_file.read()

# Define version
init_path = Path('minigun/__init__.py')
with init_path.open('r', encoding = 'utf-8') as init_file:
    VERSION = init_file.readline().split(' = ')[1][1:-2]

# Upload command
class UploadCommand(Command):
    description = 'Build and publish the package.'
    user_options = []

    @staticmethod
    def status(s): print('\033[1m{0}\033[0m'.format(s))
    def initialize_options(self): pass
    def finalize_options(self): pass

    def run(self):
        self.status('Removing previous builds ...')
        try: os.removedirs(Path('dist'))
        except: pass

        self.status('Building Source and Wheel (universal) distribution ...')
        os.system('{0} setup.py sdist bdist_wheel --universal'.format(sys.executable))

        self.status('Uploading the package to PyPI via Twine ...')
        os.system('twine upload dist/*')

        self.status('Pushing git tags ...')
        os.system('git tag v{0}'.format(VERSION))
        os.system('git push --tags')

        sys.exit()

setup(
    name = NAME,
    license = 'MIT',
    version = VERSION,
    description = DESCRIPTION,
    long_description = LONG_DESCRIPTION,
    long_description_content_type = 'text/markdown',
    url = URL,
    author = AUTHOR,
    author_email = EMAIL,
    requires_python = REQUIRES_PYTHON,
    install_requires = REQUIRED,
    packages = find_packages(exclude = ["tests", "docs", "examples"]),
    entry_points = {},
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: MacOS',
        'Operating System :: Microsoft',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10'
    ],
    cmdclass = {
        'upload': UploadCommand
    }
)
