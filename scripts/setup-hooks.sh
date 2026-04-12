#!/usr/bin/env bash
# Configure git to use our custom hooks directory
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
echo "Git hooks configured. Pre-commit secret guard is active."
