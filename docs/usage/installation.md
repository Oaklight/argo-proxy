# Installation

![PyPI - Version](https://img.shields.io/pypi/v/argo-proxy)

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

### Upgrade to Latest Version

To upgrade to the latest version:

```bash
argo-proxy --version  # Display current version
# Check against PyPI version
pip install argo-proxy --upgrade
```

### Development Installation

If you decide to use the development version (make sure you are at the root of the repo cloned):

![GitHub Release](https://img.shields.io/github/v/release/Oaklight/argo-proxy)

```bash
git clone https://github.com/Oaklight/argo-proxy.git
cd argo-proxy
pip install .
```

## Function Calling Support

Function calling is available for Chat Completions endpoint starting from `v2.7.5`. To use function calling features:

```bash
pip install "argo-proxy>=2.7.5"
```

## Verification

After installation, verify that argo-proxy is installed correctly:

```bash
argo-proxy --version
```

This should display the installed version number.
