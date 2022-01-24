.PHONY: run help install install-dev

run:
        @. ./bin/activate; python -m src

help:
        @echo 'make [install[-dev]]'

install:
        @python3.9 -m venv .; . ./bin/activate; pip install -r etc/requirements/release

install-dev: install
        @. ./bin/activate; pip install -r etc/requirements/dev

clean:
        @rm -r bin include lib lib64 share pyvenv.cfg