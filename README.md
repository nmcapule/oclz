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

1. Setup and put your credentials in `config.ini` file.

```ini
[Common]
Store=../skeo_sync.db

[Lazada]
Domain=
AppKey=
AppSecret=

[Opencart]
Domain=
Username=
Password=

[Shopee]
ShopID=
PartnerID=
PartnerKey=
```

2. Run with make, which will install pypy and pip and requirements.txt

```sh
# For testing and check config only.
$ make pypy3-run ARGS="chkconfig"
# For syncing in read-only mode (no write).
$ make pypy3-run ARGS="sync --readonly"
# For syncing using a different config.
$ make pypy3-run ARGS="sync --config=config.prod.ini"
```

### Formatter

Use `black` formatter please.
