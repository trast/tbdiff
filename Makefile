all: bin-wrappers/git-tbdiff

bin-wrappers/git-tbdiff: git-tbdiff.py
	mkdir -p bin-wrappers
	cp git-tbdiff.py bin-wrappers/git-tbdiff
	chmod a+x bin-wrappers/git-tbdiff
