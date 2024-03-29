"""Package for syncing implementation between shops."""

import json
import logging

import sync.integrations.lazada
import sync.integrations.opencart
import sync.integrations.shopee
import sync.integrations.woocommerce
import sync.integrations.tiktok

from sync import constants, client, oauth2
from sync.common.errors import (
    CommunicationError,
)
from sync.integrations.lazada import LazadaClient
from sync.integrations.opencart import OpencartClient
from sync.integrations.shopee import ShopeeClient
from sync.integrations.woocommerce import WooCommerceClient
from sync.integrations.tiktok import TiktokClient


def UploadFromLazadaToShopee(
    sync_client, lazada_client, shopee_client, read_only=False
):
    """Creates mising products from Shopee using data from Lazada."""

    if read_only:
        logging.info("Skipping upload from Lazada to Shopee: read-only mode")
        return

    lookup = sync_client.ProductAvailability()
    lazada_items = lookup[constants._SYSTEM_LAZADA]
    shopee_items = lookup[constants._SYSTEM_SHOPEE]

    items_to_upload = lazada_items - shopee_items
    for model in items_to_upload:
        try:
            lazada_product = lazada_client.GetProductDirect(model)
            # shopee_item_id = shopee_client.CreateProduct(lazada_product)
        except Exception as e:
            logging.error("Oh no error syncing %s: %s" % (model, str(e)))


def CreateLazadaOauth2Tokens(oauth2_service, lazada_client, code):
    """Creates Oauth2 tokens of the client for Lazada Open API platform."""
    result = lazada_client._Request(
        "/auth/token/create",
        {"code": code},
        domain="https://auth.lazada.com/rest",
        raw=True,
    )
    if result.error_code != constants._ERROR_SUCCESS:
        raise CommunicationError("Error creating oauth2: %s" % result.error_description)

    update_oauth2_dict = result.result

    oauth2_service.SaveOauth2Tokens(
        constants._SYSTEM_LAZADA,
        update_oauth2_dict["access_token"],
        update_oauth2_dict["refresh_token"],
        update_oauth2_dict["expires_in"],
    )


def UpdateLazadaOauth2Tokens(oauth2_service, lazada_client, read_only=False):
    """Updates Oauth2 tokens of the client for Lazada Open API platform."""
    if read_only:
        logging.info("Skipping update Lazada oauth2 tokens: read-only mode")
        return

    lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(constants._SYSTEM_LAZADA)

    result = lazada_client._Request(
        "/auth/token/refresh",
        {"refresh_token": lazada_oauth2_dict["refresh_token"]},
        domain="https://auth.lazada.com/rest",
        raw=True,
    )
    if result.error_code != constants._ERROR_SUCCESS:
        raise CommunicationError("Error updating oauth2: %s" % result.error_description)

    update_oauth2_dict = result.result

    oauth2_service.SaveOauth2Tokens(
        constants._SYSTEM_LAZADA,
        update_oauth2_dict["access_token"],
        update_oauth2_dict["refresh_token"],
        update_oauth2_dict["expires_in"],
    )


def CreateTiktokOauth2Tokens(oauth2_service, tiktok_client, code):
    """Creates Oauth2 tokens of the client for TiktokOpen API platform."""
    result = tiktok_client._Request(
        "/api/token/getAccessToken",
        {
            "app_key": tiktok_client._app_key,
            "app_secret": tiktok_client._app_secret,
            "auth_code": code,
            "grant_type": "authorized_code",
        },
        domain="https://auth.tiktok-shops.com",
    )
    if result.error_code != constants._ERROR_SUCCESS:
        raise CommunicationError("Error creating oauth2: %s" % result.error_description)

    update_oauth2_dict = result.result.get("data")

    oauth2_service.SaveOauth2Tokens(
        constants._SYSTEM_TIKTOK,
        update_oauth2_dict.get("access_token"),
        update_oauth2_dict.get("refresh_token"),
        update_oauth2_dict.get("access_token_expire_in"),
    )


def UpdateTiktokOauth2Tokens(oauth2_service, tiktok_client, read_only=False):
    """Updates Oauth2 tokens of the client for Tiktok API platform."""
    if read_only:
        logging.info("Skipping update Tiktok oauth2 tokens: read-only mode")
        return

    tiktok_oauth2_dict = oauth2_service.GetOauth2Tokens(constants._SYSTEM_TIKTOK)

    result = tiktok_client._Request(
        "/api/token/refreshToken",
        {
            "app_key": tiktok_client._app_key,
            "app_secret": tiktok_client._app_secret,
            "refresh_token": tiktok_oauth2_dict["refresh_token"],
            "grant_type": "refresh_token",
        },
        domain="https://auth.tiktok-shops.com",
    )
    if result.error_code != constants._ERROR_SUCCESS:
        raise CommunicationError("Error updating oauth2: %s" % result.error_description)

    update_oauth2_dict = result.result.get("data")

    oauth2_service.SaveOauth2Tokens(
        constants._SYSTEM_TIKTOK,
        update_oauth2_dict.get("access_token"),
        update_oauth2_dict.get("refresh_token"),
        update_oauth2_dict.get("access_token_expire_in"),
    )


def ListDeletedSystemModels(sync_client, system):
    """Returns item models that no longer exist in a system but does so in the DB.

    Raises:
      CommunicationError, Unexpected number of external product models.
    """
    if sync_client._System(system) is None:
        raise CommunicationError("%s is not initialized!" % system)

    cached_products = sync_client._GetInventoryItems()
    cached_models = set([p.model for p in cached_products])

    online_models = set(sync_client._CollectExternalProductModels(system))
    if len(online_models) == 0:
        raise CommunicationError("Unexpected number of external product models!")

    return cached_models - online_models


def DoCleanupProcedure(config):
    """Kicks off the process to remove records that no longer exists in OC."""
    if constants._CONFIG_OPENCART not in config.sections():
        logging.info("Opencart is disabled. Skipping cleanup.")
        return

    opencart_client = OpencartClient(
        domain=config.get(constants._CONFIG_OPENCART, "Domain"),
        username=config.get(constants._CONFIG_OPENCART, "Username"),
        password=config.get(constants._CONFIG_OPENCART, "Password"),
    )
    sync_client = client.SyncClient(
        dbpath=config.get("Common", "Store"),
        opencart_client=opencart_client,
    )

    with sync_client:
        deleted_models = ListDeletedSystemModels(
            sync_client, constants._SYSTEM_OPENCART
        )
        sync_client._DeleteInventoryItems(deleted_models)


def DoGenerateShopeeShopAuthorizationURL(config):
    """Prints shop authorization URL to connect a Shopee shop to a Shopee app."""
    if constants._CONFIG_SHOPEE not in config.sections():
        logging.info("Shopee is disabled. Skipping URL generation.")
        return

    shopee_client = ShopeeClient(
        shop_id=config.getint(constants._CONFIG_SHOPEE, "ShopID"),
        partner_id=config.getint(constants._CONFIG_SHOPEE, "PartnerID"),
        partner_key=config.get(constants._CONFIG_SHOPEE, "PartnerKey"),
        with_refresh=False,
    )
    logging.info(f"Authorization URL: {shopee_client.GenerateShopAuthorizationURL()}")


def DoLazadaResetAccessToken(config, auth_code):
    """Kicks off the process to reset / renew the access token by auth code."""
    oauth2_service = oauth2.Oauth2Service(dbpath=config.get("Common", "Store"))
    with oauth2_service:
        lazada_client = LazadaClient(
            domain=config.get("Lazada", "Domain"),
            app_key=config.get("Lazada", "AppKey"),
            app_secret=config.get("Lazada", "AppSecret"),
            with_refresh=False,
        )

        CreateLazadaOauth2Tokens(oauth2_service, lazada_client, code=auth_code)


def DoTiktokResetAccessToken(config, auth_code):
    """Kicks off the process to reset / renew the access token by auth code."""
    oauth2_service = oauth2.Oauth2Service(dbpath=config.get("Common", "Store"))
    with oauth2_service:
        tiktok_client = TiktokClient(
            domain=config.get("Tiktok", "Domain"),
            app_key=config.get("Tiktok", "AppKey"),
            app_secret=config.get("Tiktok", "AppSecret"),
            with_refresh=False,
        )

        CreateTiktokOauth2Tokens(oauth2_service, tiktok_client, code=auth_code)


def DoSyncProcedure(config, read_only=False):
    """Kicks off the process to sync product quantities between systems."""
    oauth2_service = oauth2.Oauth2Service(dbpath=config.get("Common", "Store"))

    with oauth2_service:
        lazada_client = None
        opencart_client = None
        shopee_client = None
        woocommerce_client = None
        tiktok_client = None

        if constants._CONFIG_LAZADA in config.sections():
            lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(
                constants._SYSTEM_LAZADA
            )
            lazada_client = LazadaClient(
                domain=config.get(constants._CONFIG_LAZADA, "Domain"),
                app_key=config.get(constants._CONFIG_LAZADA, "AppKey"),
                app_secret=config.get(constants._CONFIG_LAZADA, "AppSecret"),
                access_token=lazada_oauth2_dict["access_token"],
                with_refresh=False,
            )
            UpdateLazadaOauth2Tokens(
                oauth2_service, lazada_client, read_only=read_only
            )
            lazada_client.Refresh()
        if constants._CONFIG_OPENCART in config.sections():
            opencart_client = OpencartClient(
                domain=config.get(constants._CONFIG_OPENCART, "Domain"),
                username=config.get(constants._CONFIG_OPENCART, "Username"),
                password=config.get(constants._CONFIG_OPENCART, "Password"),
            )
        if constants._CONFIG_SHOPEE in config.sections():
            shopee_client = ShopeeClient(
                shop_id=config.getint(constants._CONFIG_SHOPEE, "ShopID"),
                partner_id=config.getint(constants._CONFIG_SHOPEE, "PartnerID"),
                partner_key=config.get(constants._CONFIG_SHOPEE, "PartnerKey"),
            )
        if constants._CONFIG_WOOCOMMERCE in config.sections():
            woocommerce_client = WooCommerceClient(
                domain=config.get(constants._CONFIG_WOOCOMMERCE, "Domain"),
                consumer_key=config.get(constants._CONFIG_WOOCOMMERCE, "ConsumerKey"),
                consumer_secret=config.get(
                    constants._CONFIG_WOOCOMMERCE, "ConsumerSecret"
                ),
            )
        if constants._CONFIG_TIKTOK in config.sections():
            tiktok_oauth2_dict = oauth2_service.GetOauth2Tokens(
                constants._SYSTEM_TIKTOK
            )
            tiktok_client = TiktokClient(
                domain=config.get(constants._CONFIG_TIKTOK, "Domain"),
                app_key=config.get(constants._CONFIG_TIKTOK, "AppKey"),
                app_secret=config.get(constants._CONFIG_TIKTOK, "AppSecret"),
                access_token=tiktok_oauth2_dict["access_token"],
                shop_id=config.get(constants._CONFIG_TIKTOK, "ShopID"),
                warehouse_id=config.get(constants._CONFIG_TIKTOK, "WarehouseID"),
                with_refresh=False,
            )
            UpdateTiktokOauth2Tokens(
                oauth2_service, tiktok_client, read_only=read_only
            )
            tiktok_client.Refresh()

        default_client = None
        if config.get("Common", "DefaultSystem") == constants._CONFIG_OPENCART:
            default_client = opencart_client
        if config.get("Common", "DefaultSystem") == constants._CONFIG_LAZADA:
            default_client = lazada_client
        if config.get("Common", "DefaultSystem") == constants._CONFIG_SHOPEE:
            default_client = shopee_client
        if config.get("Common", "DefaultSystem") == constants._CONFIG_WOOCOMMERCE:
            default_client = woocommerce_client
        if config.get("Common", "DefaultSystem") == constants._CONFIG_TIKTOK:
            default_client = tiktok_client

        sync_client = client.SyncClient(
            dbpath=config.get("Common", "Store"),
            opencart_client=opencart_client,
            lazada_client=lazada_client,
            shopee_client=shopee_client,
            woocommerce_client=woocommerce_client,
            tiktok_client=tiktok_client,
            default_client=default_client,
        )

        with sync_client:
            sync_client.Sync(read_only=read_only)
            if lazada_client and json.loads(
                config.get("Common", "EnableLazadaToShopeeUpload")
            ):
                UploadFromLazadaToShopee(
                    sync_client, lazada_client, shopee_client, read_only=read_only
                )
