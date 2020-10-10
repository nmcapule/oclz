"""Package for syncing implementation between shops."""

import logging
import os
import sqlite3
import sys

import sync.integrations.lazada
import sync.integrations.opencart
import sync.integrations.shopee

from sync import constants, client, oauth2
from sync.common.errors import (
    Error,
    NotFoundError,
    MultipleResultsError,
    CommunicationError,
    UnhandledSystemError,
)
from sync.integrations.lazada import LazadaClient
from sync.integrations.opencart import OpencartClient
from sync.integrations.shopee import ShopeeClient


def UploadFromLazadaToShopee(sync_client,
                             lazada_client,
                             shopee_client,
                             read_only=False):
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
            shopee_item_id = shopee_client.CreateProduct(lazada_product)
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
        raise CommunicationError("Error creating oauth2: %s" %
                                 result.error_description)

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

    lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(
        constants._SYSTEM_LAZADA)

    result = lazada_client._Request(
        "/auth/token/refresh",
        {"refresh_token": lazada_oauth2_dict["refresh_token"]},
        domain="https://auth.lazada.com/rest",
        raw=True,
    )
    if result.error_code != constants._ERROR_SUCCESS:
        raise CommunicationError("Error updating oauth2: %s" %
                                 result.error_description)

    update_oauth2_dict = result.result

    oauth2_service.SaveOauth2Tokens(
        constants._SYSTEM_LAZADA,
        update_oauth2_dict["access_token"],
        update_oauth2_dict["refresh_token"],
        update_oauth2_dict["expires_in"],
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
        raise CommunicationError(
            "Unexpected number of external product models!")

    return cached_models - online_models


def DoCleanupProcedure(config):
    """Kicks off the process to remove records that no longer exists in OC."""
    opencart_client = OpencartClient(
        domain=config.get("Opencart", "Domain"),
        username=config.get("Opencart", "Username"),
        password=config.get("Opencart", "Password"),
    )
    sync_client = client.SyncClient(opencart_client=opencart_client)

    with sync_client:
        deleted_models = ListDeletedSystemModels(sync_client,
                                                 constants._SYSTEM_OPENCART)
        sync_client._DeleteInventoryItems(deleted_models)


def DoLazadaResetAccessToken(config, auth_code):
    """Kicks off the process to reset / renew the access token by auth code."""
    oauth2_service = oauth2.Oauth2Service(dbpath=config.get("Common", "Store"))
    with oauth2_service:
        lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(
            constants._SYSTEM_LAZADA)

        lazada_client = LazadaClient(
            domain=config.get("Lazada", "Domain"),
            app_key=config.get("Lazada", "AppKey"),
            app_secret=config.get("Lazada", "AppSecret"),
            with_refresh=False,
        )

        CreateLazadaOauth2Tokens(oauth2_service, lazada_client, code=auth_code)


def DoSyncProcedure(config, read_only=False):
    """Kicks off the process to sync product quantities between systems."""
    oauth2_service = oauth2.Oauth2Service(dbpath=config.get("Common", "Store"))

    with oauth2_service:
        lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(
            constants._SYSTEM_LAZADA)
        lazada_client = LazadaClient(
            domain=config.get("Lazada", "Domain"),
            app_key=config.get("Lazada", "AppKey"),
            app_secret=config.get("Lazada", "AppSecret"),
            access_token=lazada_oauth2_dict["access_token"],
        )
        opencart_client = OpencartClient(
            domain=config.get("Opencart", "Domain"),
            username=config.get("Opencart", "Username"),
            password=config.get("Opencart", "Password"),
        )
        shopee_client = ShopeeClient(
            shop_id=config.getint("Shopee", "ShopID"),
            partner_id=config.getint("Shopee", "PartnerID"),
            partner_key=config.get("Shopee", "PartnerKey"),
        )
        sync_client = client.SyncClient(
            opencart_client=opencart_client,
            lazada_client=lazada_client,
            shopee_client=shopee_client,
        )

        with sync_client:
            sync_client.Sync(read_only=read_only)
            UploadFromLazadaToShopee(sync_client,
                                     lazada_client,
                                     shopee_client,
                                     read_only=read_only)

        UpdateLazadaOauth2Tokens(oauth2_service,
                                 lazada_client,
                                 read_only=read_only)
