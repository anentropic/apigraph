.PHONY: pypi, tag, shell, typecheck, pytest, pytest-pdb, test

pypi:
	poetry publish --build
	make tag

tag:
	git tag $$(python -c "from apigraph import __version__; print(__version__)")
	git push --tags

typecheck:
	mypy -p apigraph --ignore-missing-imports

pytest:
	py.test -v -s tests/

pytest-pdb:
	py.test -vv -s --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb tests/

test:
	$(MAKE) typecheck
	$(MAKE) pytest
