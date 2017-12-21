
Releasing csvw
==============

- Do platform test via tox:
```
tox -r --skip-missing-interpreters
```

- Make sure statement coverage is at 100%
- Make sure flake8 passes:
```
flake8 csvw
```

- Change version to the new version number in

  - `setup.py`
  - `csvw/__init__.py`

- Bump version number:
```
git commit -a -m"bumped version number"
```

- Create a release tag:
```
git tag -a v<version> -m"first version to be released on pypi"
```

- Push to github:
```
git push origin
git push --tags
```

- Make sure your system Python has ``setuptools-git`` installed and release to PyPI:
```
git checkout tags/v$1
rm dist/*
python setup.py sdist bdist_wheel
twine upload dist/*
```
