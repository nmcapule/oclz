# SKEO Opencart-Lazada-Shopee Extension Accessory


## Setup

Configure `config.ini` and fill up the sections for Lazada, Opencart and Shopee.

## Environment

1. Install pyenv and friends

```shell
$ # Install pyenv and friends
$ brew install pyenv pyenv-virtualenv
$ # Create venv for 2.7.15 under name "oclz"
$ pyenv virtualenv 2.7.15 oclz
```

2. Add this thing on your ~/.bashrc (or ~/.zshrc)

```
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

3. Activate and install "requests"

```shell
$ pyenv activate oclz
(oclz) -> $ pip install requests
```

4. Try executing:

```
$ python sync.py --chkconfig
```
