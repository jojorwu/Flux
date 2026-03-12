.PHONY: build clean

build:
	@echo "Building flux-patcher..."
	@# In this case, building just means ensuring Python is available
	@# and maybe setting up a venv if needed.
	@# For now, we'll just check python version.
	@python3 --version
	@echo "flux-patcher is ready to use."

clean:
	rm -rf __pycache__
	rm -rf .flux-workspace
