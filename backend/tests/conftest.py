"""
Test configuration and fixtures.

Sets up environment variables so that modules that load from config
(like the layout engine) work without a real .env file.
"""
import os
import pytest

# Provide stub credentials so pydantic-settings can initialize without error.
# Tests that don't call Granite or the compiler will work fine with these.
os.environ.setdefault("WATSONX_APIKEY", "test-key-stub")
os.environ.setdefault("WATSONX_PROJECT_ID", "test-project-stub")
os.environ.setdefault("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
os.environ.setdefault("USE_FONTSPEC", "false")
os.environ.setdefault("LATEX_COMPILER", "pdflatex")
os.environ.setdefault("LOG_LEVEL", "WARNING")
