# SKEO Opencart-Lazada-Shopee Extension Accessory

## Setup

Configure `config.ini` and fill up the sections for Lazada, Opencart and Shopee.

## Environment

### Using docker setup

1. Install [docker](docs.docker.com/get-docker)

2. Run the app:

   - **Make**: `make docker-run ARGS="--help"`
   - **Bash**: `./scripts/docker_run --help`

### Using local machine setup

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

### Formatter

Use `black` formatter please.
