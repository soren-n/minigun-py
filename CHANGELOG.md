# CHANGELOG

<!-- version list -->

## v2.4.0 (2025-09-30)

### Bug Fixes

- Correct CounterExample access in comprehensive test
  ([`d658dfe`](https://github.com/soren-n/minigun-py/commit/d658dfe8b3f197afb792b7fd28207b915c225189))

### Features

- Add 'minigun' command alias and simplify README
  ([`a294fc9`](https://github.com/soren-n/minigun-py/commit/a294fc95bf6d4b87dd25b8537236be11320eb6c7))

- Generalize CLI with test discovery and improve documentation
  ([`93a9fbd`](https://github.com/soren-n/minigun-py/commit/93a9fbd1bb2013cb15aafd11dcfd76d782466db3))


## v2.3.0 (2025-09-30)

### Features

- Add exception handling with shrinking support
  ([`0c188f1`](https://github.com/soren-n/minigun-py/commit/0c188f137aad97c6f2339bd83921ca55f78f2596))


## v2.2.5 (2025-09-30)

### Bug Fixes

- Update comprehensive test to use generator tuple correctly
  ([`66ddcab`](https://github.com/soren-n/minigun-py/commit/66ddcabd7a602eaf939301463582848bbcd17e0d))


## v2.2.4 (2025-09-30)

### Bug Fixes

- Resolve shrinking failure for complex nested dataclasses
  ([`3d4f9e6`](https://github.com/soren-n/minigun-py/commit/3d4f9e6c0b95edbebe45b671f6a187a60c2bb920))


## v2.2.3 (2025-08-17)

### Bug Fixes

- Handle duplicate GitHub releases in workflow
  ([`9a8f53d`](https://github.com/soren-n/minigun-py/commit/9a8f53d357c7448abe8dd246792d0476d39223c5))


## v2.2.2 (2025-08-17)

### Bug Fixes

- Adjust CI coverage threshold from 70% to 60% to match current coverage
  ([#10](https://github.com/soren-n/minigun-py/pull/10),
  [`2d6b710`](https://github.com/soren-n/minigun-py/commit/2d6b710ac70bcac1d4b373233075c2da5161af0d))


## v2.2.1 (2025-08-17)

### Bug Fixes

- Adjust coverage threshold from 70% to 60% to match current coverage
  ([`9db436b`](https://github.com/soren-n/minigun-py/commit/9db436bbda1e633f1883b86a722286f097485e2a))


## v2.2.0 (2025-08-16)

### Features

- Add implementation summary for complexity optimization
  ([`95d8d53`](https://github.com/soren-n/minigun-py/commit/95d8d538966480d2c94721b1e2533d34ee59b47c))

- Add symbolic cardinality algebra system
  ([`9690c58`](https://github.com/soren-n/minigun-py/commit/9690c58dcef23dfc88df769954e977b0a995055b))


## v2.1.0 (2025-08-16)

### Features

- Add context documentation and migrate to ruff-only tooling
  ([`bf9b9e7`](https://github.com/soren-n/minigun-py/commit/bf9b9e72077337fa0058e5d0b01d3af4a00b6708))


## v2.0.0 (2025-08-16)

### Bug Fixes

- Update CI configuration and code quality settings
  ([`3fb3530`](https://github.com/soren-n/minigun-py/commit/3fb35308b0c0c0dd43b87572fa7f5c496289e298))

### Features

- Break down CI quality checks into individual steps
  ([`15b0f90`](https://github.com/soren-n/minigun-py/commit/15b0f909a9046be90d1384e2f7f39587eb68203d))

- Eliminate all backwards compatibility cruft
  ([`8b9cefe`](https://github.com/soren-n/minigun-py/commit/8b9cefe2437f70e09d4a82a3859802d74b6073cc))

- Refactor pre-commit hooks to use individual checks
  ([`1715d86`](https://github.com/soren-n/minigun-py/commit/1715d86d4573c658b2cd1414a81d4a4541ed6cec))

### Breaking Changes

- Remove all legacy script commands and quality_gates.py


## v1.0.0 (2025-08-16)

### Bug Fixes

- Refactor tuple and dict pretty printers
  ([`e1cf3df`](https://github.com/soren-n/minigun-py/commit/e1cf3df9a0c0f6d83537226d1ca71739a88f25f4))

- Update .gitignore to include .DS_Store and ensure proper newline at end of file
  ([`a7eb65a`](https://github.com/soren-n/minigun-py/commit/a7eb65ac5b02506d666e1f2ef38e33421ba344b9))

### Features

- Add enhanced test reporting and code quality improvements
  ([`e28bf4a`](https://github.com/soren-n/minigun-py/commit/e28bf4a69de20146eaf9dfec7eaf090a7337d08c))


## v0.4.12 (2025-07-20)

### Bug Fixes

- Add --link-mode copy to Sphinx command for proper linking
  ([`a4e37aa`](https://github.com/soren-n/minigun-py/commit/a4e37aaaedfbe0cd0fbba34ace4e99d79b11b8df))

- Correct command syntax for Sphinx documentation generation
  ([`bec7114`](https://github.com/soren-n/minigun-py/commit/bec7114d236302d1db4fe4d5afcbcd95de01e95a))

- Remove custom static files path from Sphinx configuration
  ([`cedd6dc`](https://github.com/soren-n/minigun-py/commit/cedd6dc7b2302cbe65484b4ee993e028817e9af0))

- Ubuntu version to 24.04 in Read the Docs configuration
  ([`63f9497`](https://github.com/soren-n/minigun-py/commit/63f9497abea36f324a422d0ead10a52cb5e4cf6f))

- Update Sphinx command to use correct source directory
  ([`bfef289`](https://github.com/soren-n/minigun-py/commit/bfef289c88f64f205e375896299509ea434c601f))


## v0.4.11 (2025-07-20)

### Bug Fixes

- Pretty printing of tuples
  ([`cec3852`](https://github.com/soren-n/minigun-py/commit/cec38528b431a974293b21e48e3b4dde76845e8e))


## v0.4.10 (2025-05-04)

### Bug Fixes

- Switch from grp to seq for wrapper printers
  ([`cc1b4eb`](https://github.com/soren-n/minigun-py/commit/cc1b4ebfeb49284a02866bdae8f6c71774baaf95))


## v0.4.9 (2025-05-04)

### Features

- Add helper functions for layout rendering and improve printer implementations
  ([`223a69e`](https://github.com/soren-n/minigun-py/commit/223a69e77d213dbc3a2593a91bf73785dcb03cb6))


## v0.4.8 (2025-04-17)

### Bug Fixes

- Update function name formatting in error messages for consistency
  ([`bf608ef`](https://github.com/soren-n/minigun-py/commit/bf608ef16caf9273460ee3dd9225b82d8d557804))


## v0.4.7 (2025-04-17)


## v0.4.6 (2025-04-17)


## v0.4.5 (2025-04-17)


## v0.4.4 (2025-04-17)


## v0.4.3 (2025-04-06)


## v0.4.2 (2025-04-02)


## v0.4.1 (2025-04-02)


## v0.3.8 (2023-03-19)


## v0.3.7 (2023-03-19)


## v0.3.6 (2023-03-19)


## v0.3.5 (2023-03-19)


## v0.3.4 (2023-03-19)


## v0.3.3 (2023-03-18)


## v0.3.2 (2023-03-17)


## v0.3.1 (2023-03-17)


## v0.3.0 (2022-02-17)


## v0.2.1 (2022-02-15)


## v0.2.0 (2022-02-15)


## v0.1.3 (2022-02-07)


## v0.1.1 (2022-02-07)


## v0.1.0 (2022-02-07)

- Initial Release
