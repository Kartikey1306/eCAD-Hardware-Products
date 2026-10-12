# Contributing to eHardware-Designs-Products

Thank you for your interest in contributing!

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make your changes
4. Run the build and tests locally
5. Submit a pull request

## Development Setup

```bash
git clone https://github.com/embeddedos-org/eHardware-Designs-Products.git
cd eHardware-Designs-Products
cmake -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

## Code Guidelines

- **Standard:** C11
- **Warnings:** `-Wall -Wextra` must compile clean
- **Naming:** `snake_case` for all identifiers
- **Types:** Use `<stdint.h>` types

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
feat: add new feature
fix: resolve bug
docs: update documentation
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

### Exception: the EmbeddedOS original boards

The EmbeddedOS original boards in `boards/eos/` are Copyright (c) 2026 Kartikeydheer Srivastava, all rights
reserved. They are not under the MIT License, and the paragraph above does not apply to them.
The exact files are listed in [boards/eos/README.md](boards/eos/README.md#licence).

A change to those files is accepted only if its author agrees that Kartikeydheer Srivastava
may use and relicense the change on any terms. Say so in the pull request.
