# Installation

[![PyPI version](https://img.shields.io/pypi/v/argo-proxy?color=green)](https://pypi.org/project/argo-proxy/)

## Prerequisites

- **Python 3.10+** is required.
- It is recommended to use conda, mamba, or pipx, etc., to manage an exclusive environment.
- **Conda/Mamba** Download and install from: <https://conda-forge.org/download/>
- **pipx** Download and install from: <https://pipx.pypa.io/stable/installation/>

## Installation via pip

### Basic Installation

Install the current stable version from PyPI:

```bash
pip install argo-proxy
```

### Pre-release Installation

To install the latest pre-release (e.g., v3.0.0 beta):

```bash
pip install --pre argo-proxy
```

### Upgrade to Latest Version

```bash
# Check current version and available updates
argo-proxy update check

# Install latest stable
argo-proxy update install

# Install latest pre-release
argo-proxy update install --pre
```

Or manually:

```bash
pip install argo-proxy --upgrade
```

### Development Installation

If you decide to use the development version (make sure you are at the root of the repo cloned):

[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/argo-proxy)](https://github.com/Oaklight/argo-proxy/releases)

```bash
git clone https://github.com/Oaklight/argo-proxy.git
cd argo-proxy
pip install .
```

## Verification

After installation, verify that argo-proxy is installed correctly:

```bash
argo-proxy --version
```

This should display the installed version number and check for updates.
