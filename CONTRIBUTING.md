# Contributing to csvw

## Installing csvw for development

1. Fork `cldf/csvw`
2. Clone your fork
3. Install `csvw` for development (preferably in a separate [virtual environment](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/)) running
```shell script
pip install -r requirements
```

## Running the test suite

The test suite is run via

```shell script
pytest
```

Cross-platform compatibility tests can additionally be run via
```shell script
tox -r
```

