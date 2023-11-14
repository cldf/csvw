
Releasing csvw
==============

- Do platform test via tox:
```shell
tox -r
```

- Make sure flake8 passes:
```shell
flake8 src
```

- Make sure docs can be created:
```shell
cd docs
make clean html
cd ..
```

- Update the version number, by removing the trailing `.dev0` in:
  - `setup.cfg`
  - `src/csvw/__init__.py`
  - `docs/conf.py`

- Edit `CHANGES`

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
python -m build -n
twine upload dist/*
```

- Push to github:
```shell
git push origin
git push --tags
```

- Increment version number and append `.dev0` to the version number for the new development cycle:
  - `src/csvw/__init__.py`
  - `setup.cfg`
  - `docs/conf.py`

- Commit/push the version change:
```shell
git commit -a -m "bump version for development"
git push origin
```
