
Releasing csvw
==============

- Do platform test via tox:
```
tox -r --skip-missing-interpreters
```

- Make sure statement coverage is at 100%
- Make sure flake8 passes:
```
flake8 src
```

- Update the version number, by removing the trailing `.dev0` in:
  - `setup.py`
  - `src/csvw/__init__.py`

- Create the release commit:
```shell
git commit -a -m "release <VERSION>"
```

- Create a release tag:
```
git tag -a v<VERSION> -m"<VERSION> release"
```

- Release to PyPI:
```shell
rm dist/*
python setup.py sdist bdist_wheel
twine upload dist/*
```

- Push to github:
```
git push origin
git push --tags
```

- Increment version number and append `.dev0` to the version number for the new development cycle:
  - `src/csvw/__init__.py`
  - `setup.py`

- Commit/push the version change:
```shell
git commit -a -m "bump version for development"
git push origin
```
