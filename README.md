# SKEO Opencart-Lazada-Shopee-WooCommerce Extension Accessory

## Setup

Configure `config.ini` and fill up the sections for Lazada, Opencart, WooCommerce and Shopee.

## Environment

### Using docker setup

1. Install [docker](docs.docker.com/get-docker)

2. Run the app:

   - **Make**: `make docker-run ARGS="--help"`
   - **Bash**: `./scripts/docker_run --help`

### Using local machine setup

1. Setup and put your credentials in `config.ini` file. To disable a system,
   just comment it out in the `.ini` file.

```ini
[Common]
Store=../skeo_sync.db
DefaultSystem=Opencart
EnableLazadaToShopeeUpload=1

[Lazada]
Domain=
AppKey=
AppSecret=

[Shopee]
ShopID=
PartnerID=
PartnerKey=

[Opencart]
Domain=
Username=
Password=

[WooCommerce]
Domain=
ConsumerKey=
ConsumerSecret=
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

## Troubleshooting

### I got an error when syncing Shopee: `your access to shop has expired`. What do?

You need to refresh your app's authorization to your shop. Check out the
[Shopee Open Platform Docs](https://open.shopee.com/documents?module=63&type=2&id=56)
on how to setup **Shop Authorization**.

There's a script included here to generate the URL that you need to visit:

```sh
$ make pypy3-run ARGS="shreauth --config=config.prod.ini"
```

### How do I get / setup the access and refresh tokens for Lazada?

1. Open you app on the [**APP Console**](https://open.lazada.com/app/index.htm)
2. In `App Management > Auth Management`, add your authorized seller whitelist.
3. In `API Explorer`, select the region and click on the **Get Token** link. Use
   `Type = By Code` and click on the **Get Code** link. Authorize and take note
   of the redirected URL and get the `code` part. For example:
   ```
   https://127.0.0.1/?code=0_xxxxxxxxxxxx
   ```
4. Run the following:
   ```sh
   $ make pypy3-run ARGS="lzreauth --config=config.prod.ini --token=0_xxxxxxxxxxxx"
   ```

### My Lazada item stocks does not update?

As of Feb 2021, using the [update endpoint](https://open.lazada.com/doc/api.htm?spm=a2o9m.11193494.0.0.761f266b7z0ooD#/api?cid=5&path=/product/price_quantity/update)
sometimes will not work if the quantity is set to something lower than an arbitrary
number. This number is of unknown origin. Real great.

**Update from Mar 2021**: Lazada Open API support replied to our query and said that
this was a known issue and escalated to the regional support. 🥳 Now we wait.

**Workarounds**
1. Manual quantity changes should only be made in Lazada; or
2. Distribute quantity changes in Lazada and another system (e.g 50 in Lazada, 50 in
   Opencart = 100)
