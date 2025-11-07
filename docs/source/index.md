# argo-openai-proxy

![PyPI - Version](https://img.shields.io/pypi/v/argo-proxy)
![GitHub Release](https://img.shields.io/github/v/release/Oaklight/argo-proxy)

This project is a proxy application that forwards requests to an ARGO API and optionally converts the responses to be compatible with OpenAI's API format. It can be used in conjunction with [autossh-tunnel-dockerized](https://github.com/Oaklight/autossh-tunnel-dockerized) or other secure connection tools.

## TL;DR

```bash
pip install argo-proxy # install the package
argo-proxy # run the proxy
```

Function calling is available for Chat Completions endpoint starting from `v2.7.5`. Try with `pip install "argo-proxy>=2.7.5"`

## NOTICE OF USAGE

The machine or server making API calls to Argo must be connected to the Argonne internal network or through a VPN on an Argonne-managed computer if you are working off-site. Your instance of the argo proxy should always be on-premise at an Argonne machine. The software is provided "as is," without any warranties. By using this software, you accept that the authors, contributors, and affiliated organizations will not be liable for any damages or issues arising from its use. You are solely responsible for ensuring the software meets your requirements.

```{toctree}
:caption: Documentation
:hidden:

usage/index
examples/index
api/index
changelog
```

## Bug Reports and Contributions

This project is developed in my spare time. Bugs and issues may exist. If you encounter any or have suggestions for improvements, please [open an issue](https://github.com/Oaklight/argo-proxy/issues/new) or [submit a pull request](https://github.com/Oaklight/argo-proxy/compare). Your contributions are highly appreciated!
