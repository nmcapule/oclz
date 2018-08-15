"""Package for syncing implementation between shops."""

import ConfigParser
import logging
import os
import sqlite3
import sys

import lazada
import opencart
import shopee

from errors import Error, NotFoundError, MultipleResultsError, CommunicationError, UnhandledSystemError
from lazada import LazadaClient
from opencart import OpencartClient
from shopee import ShopeeClient


_SCRIPT_VERSION = '0.5'

_SYSTEM_OPENCART = 'OPENCART'
_SYSTEM_LAZADA = 'LAZADA'
_SYSTEM_SHOPEE = 'SHOPEE'
_EXTERNAL_SYSTEMS = [_SYSTEM_LAZADA, _SYSTEM_OPENCART, _SYSTEM_SHOPEE]

_ERROR_SUCCESS = 0

_DEFAULT_DB_PATH = './skeo_sync.db'
_DEFAULT_CONF_PATH = 'config.ini'

_CREATE_TABLE_OAUTH2 = """
CREATE TABLE IF NOT EXISTS oauth2 (
    system TEXT,
    access_token TEXT,
    refresh_token TEXT,
    created_on DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_on DATETIME
)
"""
_DROP_TABLE_OAUTH2 = """
DROP TABLE oauth2
"""

_CREATE_TABLE_SYNC_BATCH = """
CREATE TABLE IF NOT EXISTS sync_batch (
  sync_batch_id INTEGER PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  script_version TEXT
)
"""
_DROP_TABLE_SYNC_BATCH = """
DROP TABLE sync_batch
"""

_CREATE_TABLE_SYNC_LOGS = """
CREATE TABLE IF NOT EXISTS sync_logs (
  sync_batch_id INTEGER,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  model TEXT,
  system TEXT,
  previous_stocks INTEGER,
  computed_stocks INTEGER,
  upload_error_code TEXT,
  upload_error_description TEXT
)
"""
_DROP_TABLE_SYNC_LOGS = """
DROP TABLE sync_logs
"""

_CREATE_TABLE_INVENTORY_SYSTEM_CACHE = """
CREATE TABLE IF NOT EXISTS inventory_system_cache (
  model TEXT,
  system TEXT,
  stocks INTEGER,
  last_sync_batch_id INTEGER
)
"""
_DROP_TABLE_INVENTORY_SYSTEM_CACHE = """
DROP TABLE inventory_system_cache
"""

_CREATE_TABLE_INVENTORY_SYSTEM_CACHE_DELTA = """
CREATE TABLE IF NOT EXISTS inventory_system_cache_delta (
  model TEXT,
  system TEXT,
  cached_stocks INTEGER,
  current_stocks INTEGER,
  stocks_delta INTEGER,
  last_sync_batch_id INTEGER
)
"""
_DROP_TABLE_INVENTORY_SYSTEM_CACHE_DELTA = """
DROP TABLE inventory_system_cache_delta
"""

_CREATE_TABLE_INVENTORY = """
CREATE TABLE IF NOT EXISTS inventory (
  model TEXT PRIMARY KEY,
  stocks INTEGER,
  last_sync_batch_id INTEGER
)
"""
_DROP_TABLE_INVENTORY = """
DROP TABLE inventory
"""


class InventoryItem:
    """Describes an inventory item."""

    def __init__(self, model, stocks=0, last_sync_batch_id=0):
        self.model = model
        self.stocks = stocks
        self.last_sync_batch_id = last_sync_batch_id


class InventorySystemCacheItem(InventoryItem):
    """Describes an inventory item for an external system."""

    def __init__(self, model, system, stocks=0, last_sync_batch_id=0):
        self.model = model
        self.system = system
        self.stocks = stocks
        self.last_sync_batch_id = last_sync_batch_id


class Oauth2Service:
    """Implements tracking of Oauth2 tokens."""

    def __init__(self, dbpath=None):
        self._db_client = self._Connect(dbpath or _DEFAULT_DB_PATH)

        self._Setup()

    def __enter__(self):
        return self

    def __exit__(self, unused_exc_type, unused_exc_value, unused_traceback):
        self.Close()

    def _Setup(self):
        """Creates all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(_CREATE_TABLE_OAUTH2)
        self._db_client.commit()

    def _Drop(self):
        """Drops all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(_DROP_TABLE_OAUTH2)
        self._db_client.commit()

    def _Connect(self, dbpath):
        """Creates a connection to sqlite3 database."""
        return sqlite3.connect(dbpath)

    def _Disconnect(self):
        """Dsiconnects from sqlite3 datbase."""
        self._db_client.close()
        self._db_client = None

    def Close(self):
        """Safely closes connection to sqlite3 database."""
        if self._db_client:
            self._Disconnect()

    def SaveOauth2Tokens(self, system, access_token, refresh_token, expires_on):
        """Saves the oauth2 tokens of a system to the database."""
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            UPDATE oauth2
            SET access_token=?, refresh_token=?, expires_on=?, created_on=CURRENT_TIMESTAMP
            WHERE system=?
            """, (access_token, refresh_token, expires_on, system,))

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO oauth2 (system, access_token, refresh_token, expires_on)
                VALUES (?, ?, ?, ?)
                """, (system, access_token, refresh_token, expires_on,))

        self._db_client.commit()

    def GetOauth2Tokens(self, system):
        """Retrieves latest tokens from a system.

        Returns:
            dict, detail of Oauth2 tokens for a system.
        """

        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT system, access_token, refresh_token, created_on, expires_on
            FROM oauth2
            WHERE system=?
            """, (system,))

        result = cursor.fetchone()
        if result is None:
            raise NotFoundError('Oauth2 for system not found: %s' % system)

        return {
            'system': result[0],
            'access_token': result[1],
            'refresh_token': result[2],
            'created_on': result[3],
            'expires_on': result[4],
        }


class SyncClient:
    """Implements syncing."""

    def __init__(self, dbpath=None, opencart_client=None, lazada_client=None, shopee_client=None):
        self._opencart_client = opencart_client
        self._lazada_client = lazada_client
        self._shopee_client = shopee_client

        self._db_client = self._Connect(dbpath or _DEFAULT_DB_PATH)
        self.sync_batch_id = -1

        self._Setup()

    def __enter__(self):
        return self

    def __exit__(self, unused_exc_type, unused_exc_value, unused_traceback):
        self.Close()

    def _Connect(self, dbpath):
        """Creates a connection to sqlite3 database."""
        return sqlite3.connect(dbpath)

    def _Disconnect(self):
        """Dsiconnects from sqlite3 datbase."""
        self._db_client.close()
        self._db_client = None

    def _Setup(self):
        """Creates all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(_CREATE_TABLE_SYNC_BATCH)
        cursor.execute(_CREATE_TABLE_SYNC_LOGS)
        cursor.execute(_CREATE_TABLE_INVENTORY_SYSTEM_CACHE)
        cursor.execute(_CREATE_TABLE_INVENTORY_SYSTEM_CACHE_DELTA)
        cursor.execute(_CREATE_TABLE_INVENTORY)

        self._db_client.commit()

    def _Drop(self):
        """Drops all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(_DROP_TABLE_SYNC_BATCH)
        cursor.execute(_DROP_TABLE_SYNC_LOGS)
        cursor.execute(_DROP_TABLE_INVENTORY_SYSTEM_CACHE)
        cursor.execute(_DROP_TABLE_INVENTORY_SYSTEM_CACHE_DELTA)
        cursor.execute(_DROP_TABLE_INVENTORY)

        self._db_client.commit()

    def Close(self):
        """Safely closes connection to sqlite3 database."""
        if self._db_client:
            self._Disconnect()

    def PurgeAndSetup(self, system):
        """This reinitializes and defaults products from what is in Opencart.

        Args:
          system: str, The system code of which to use as a basis of new datasets.
        """
        self._Drop()
        self._Setup()
        self._PopulateInventoryFromSystem(system)

    def _InitSyncBatch(self):
        """Creates a new sync batch process record.

        Returns:
          int, The primary key of the sync batch.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """INSERT INTO sync_batch (script_version) VALUES (?)""",
            (_SCRIPT_VERSION,))

        self._db_client.commit()
        self.sync_batch_id = cursor.lastrowid

    def _System(self, system):
        """Returns the client for the given system.

        Args:
          system: str, The system code.

        Returns:
          LazadaClient or OpencartClient or ShopeeClient, The client to use.

        Raises:
          UnhandledSystemError, The given system code not yet supported.
        """
        if system == _SYSTEM_LAZADA:
            return self._lazada_client
        elif system == _SYSTEM_OPENCART:
            return self._opencart_client
        elif system == _SYSTEM_SHOPEE:
            return self._shopee_client
        else:
            raise UnhandledSystemError('System is not handled: %s' % system)

    def _PopulateInventoryFromSystem(self, system):
        """Repopulate inventory table with records from a given system.

        Args:
          system: str, The system code.

        Raises:
          UnhandledSystemError, The given system code not yet supported.
          lazada.CommunicationError: Cannot communicate with LAzada
          opencart.CommunicationError: Cannot communicate with opencart
          shopee.CommunicationError: Cannot communicate with opencart
        """
        client = self._System(system)

        client.Refresh()
        for p in client.ListProducts():
            item = InventoryItem(
                model=p.model, stocks=p.stocks,
                last_sync_batch_id=self.sync_batch_id)
            self._UpsertInventoryItem(item)

    def _GetInventoryItem(self, model):
        """Retrieves a single InventoryItem.

        Args:
          model: string, The sku / model of the product being searched.

        Returns:
          InventoryItem, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in the database.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT model, stocks, last_sync_batch_id
            FROM inventory
            WHERE model=?
            """, (model,))

        result = cursor.fetchone()
        if result is None:
            raise NotFoundError('InventoryItem not found: %s' % model)

        return InventoryItem(
            model=result[0], stocks=result[1], last_sync_batch_id=result[2])

    def _GetInventoryItems(self):
        """Retrieves all items from the inventory.

        Returns:
            Array<InventoryItem>, List of inventory items
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT model, stocks, last_sync_batch_id
            FROM inventory
            """)

        result = []
        for p in cursor.fetchall():
            result.append(InventoryItem(model=p[0], stocks=p[1], last_sync_batch_id=p[2]))
        return result

    def _DeleteInventoryItems(self, models):
        """Deletes the given models from the inventory table."""
        cursor = self._db_client.cursor()
        for model in models:
            logging.info("Deleting item `%s` from inventory table" % model)
            cursor.execute(
                """
                DELETE FROM inventory
                WHERE model=?
                """, (model,))

        self._db_client.commit()

    def _UpsertInventoryItem(self, item):
        """Updates a single InventoryItem record.

        Args:
          item: InventoryItem, The prodcut being updated.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            UPDATE inventory
            SET stocks=?, last_sync_batch_id=?
            WHERE model=?
            """, (item.stocks, item.last_sync_batch_id, item.model,))

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO inventory (model, stocks, last_sync_batch_id)
                VALUES (?, ?, ?)
                """, (item.model, item.stocks, item.last_sync_batch_id,))

        self._db_client.commit()

    def _GetInventorySystemCacheItem(self, system, model):
        """Retrieves a single InventorySystemCacheItem.

        Args:
          system: string, The system code.
          model: string, The sku / model of the product being searched.

        Returns:
          InventorySystemCacheItem, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in the cached system
              database.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT model, system, stocks, last_sync_batch_id
            FROM inventory_system_cache
            WHERE model=? AND system=?
            """, (model, system,))

        result = cursor.fetchone()
        if result is None:
            raise NotFoundError(
                'InventorySystemCacheItem not found: %s in %s' % (model, system,))

        return InventorySystemCacheItem(
            model=result[0], system=result[1], stocks=result[2],
            last_sync_batch_id=result[3])

    def _UpsertInventorySystemCacheItem(self, system, item):
        """Updates a single InventorySystemCacheItem record.

        Args:
          item: InventoryItem, The prodcut being updated.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            UPDATE inventory_system_cache
            SET stocks=?, last_sync_batch_id=?
            WHERE model=? AND system=?
            """, (item.stocks, item.last_sync_batch_id, item.model, system,))

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO inventory_system_cache
                    (model, system, stocks, last_sync_batch_id)
                VALUES (?, ?, ?, ?)
                """,
                (item.model, system, item.stocks, item.last_sync_batch_id,))

        self._db_client.commit()

    def _CollectExternalProductModels(self, filter_system=None):
        """Returns a list of all unique product models from the external sources."""
        models = set([])

        for system in _EXTERNAL_SYSTEMS:
            if filter_system and system != filter_system:
                continue

            client = self._System(system)
            for p in client.ListProducts():
                # Skip falsy product models, ie: undefined, empty strings
                if not p.model:
                    continue
                models.add(p.model)

        return models

    def ProductAvailability(self):
        """Returns an object declaring product availability on each of the systems."""
        lookup = {}
        for system in _EXTERNAL_SYSTEMS:
            lookup[system] = set(self._CollectExternalProductModels(system))
        return lookup

    def _CalculateSystemStocksDelta(self, system, model):
        """Calculates the delta between last saw and current external system's
        stocks of a product."""
        client = self._System(system)

        try:
            current_stocks = client.GetProduct(model).stocks
            cached_stocks = self._GetInventorySystemCacheItem(
                system, model).stocks
        except Exception as e:
            logging.warn(e)
            return 0, 0

        return current_stocks - cached_stocks, current_stocks

    def _RecordSystemStocksDelta(self, system, model, stocks_delta, current_stocks):
        """Adds a record of the diff between cached and current stocks of an item
        in an external system."""
        cached_stocks = current_stocks - stocks_delta

        cursor = self._db_client.cursor()
        cursor.execute(
            """
            INSERT INTO inventory_system_cache_delta
                (model, system, cached_stocks, current_stocks, stocks_delta,
                 last_sync_batch_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (model, system, cached_stocks, current_stocks, stocks_delta,
             self.sync_batch_id,))

        self._db_client.commit()

    def _UpdateExternalSystemItem(self, system, item):
        """Update item attributes of an item in an external system.

        Args:
          system: str, The system code of the external system to be updated.
          item: InventoryItem, The item to be updated.

        Raises:
          NotFoundError: The sku / model of the product is not in the external
              system.
          MultipleResultsError: The sku / model is not unique in the external
              system.
          CommunicationError: Cannot communicate properly with the external system.
        """
        client = self._System(system)
        system_item = client.GetProduct(item.model)

        logging.info(
            'Updating inventory system cache for %s %s' % (system, item.model,))
        fresh_item = InventorySystemCacheItem(
            system=system, model=system_item.model, stocks=system_item.stocks,
            last_sync_batch_id=self.sync_batch_id)
        self._UpsertInventorySystemCacheItem(system, fresh_item)

        if item.stocks == system_item.stocks:
            logging.info('No need to update %s in %s: same' %
                         (item.model, system,))
            return

        result = client.UpdateProductStocks(item.model, item.stocks)

        # Create a record of syncing under sync_logs table.
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            INSERT INTO sync_logs
              (sync_batch_id, system, model, previous_stocks, computed_stocks,
                  upload_error_code, upload_error_description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.sync_batch_id, system, item.model, system_item.stocks,
             item.stocks, int(result.error_code), str(result.error_description)))

        self._db_client.commit()

        # If successful in update, update in system cache.
        if result.error_code == _ERROR_SUCCESS:
            self._UpsertInventorySystemCacheItem(system, item)

    def Sync(self):
        """Executes the whole syncing batch process."""
        self._InitSyncBatch()

        for model in self._CollectExternalProductModels():
            stocks_delta = 0
            for system in _EXTERNAL_SYSTEMS:
                system_stocks_delta, current_stocks = (
                    self._CalculateSystemStocksDelta(system, model))
                if system_stocks_delta != 0:
                    logging.info(
                        'Change in stocks of %s in %s: %d', system, model,
                        system_stocks_delta)
                    self._RecordSystemStocksDelta(
                        system, model, system_stocks_delta, current_stocks)
                stocks_delta += system_stocks_delta

            try:
                item = self._GetInventoryItem(model)
            except NotFoundError as e:
                # If item is not found, try getting frmo Opencart.
                try:
                    opencart_client = self._System(_SYSTEM_OPENCART)
                    p = opencart_client.GetProduct(model)

                    item = InventoryItem(
                        model=p.model, stocks=p.stocks,
                        last_sync_batch_id=self.sync_batch_id)
                except NotFoundError as e:
                    logging.error('This item is not in OPENCART?: %s' % model)
                    continue

            item.stocks += stocks_delta
            if item.stocks <= 0:
                item.stocks = 0
            item.last_sync_batch_id = self.sync_batch_id

            # Update self inventory.
            self._UpsertInventoryItem(item)

            # Update external systems and inventory system cache.
            for system in _EXTERNAL_SYSTEMS:
                try:
                    self._UpdateExternalSystemItem(system, item)
                except CommunicationError as e:
                    logging.error(
                        'Skipping external update due to error: ' + str(e))
                except NotFoundError as e:
                    logging.warn('Skipping external update: ' + str(e))
                except MultipleResultsError as e:
                    logging.warn(
                        'Skipping external update due to multiple: ' + str(e))


def UploadFromLazadaToShopee(sync_client, lazada_client, shopee_client):
    """Creates mising products from Shopee using data from Lazada."""

    lookup = sync_client.ProductAvailability()
    lazada_items = lookup[_SYSTEM_LAZADA]
    shopee_items = lookup[_SYSTEM_SHOPEE]

    items_to_upload = lazada_items - shopee_items
    for model in items_to_upload:
        try:
            lazada_product = lazada_client.GetProductDirect(model)
            shopee_item_id = shopee_client.CreateProduct(lazada_product)
        except Exception as e:
            logging.error('Oh no error syncing %s: %s' % (model, str(e)))


def CreateLazadaOauth2Tokens(oauth2_service, lazada_client, code):
    """Creates Oauth2 tokens of the client for Lazada Open API platform."""
    result = lazada_client._Request(
        '/auth/token/create',
        {'code': code},
        domain='https://auth.lazada.com/rest',
        raw=True)
    if result.error_code != _ERROR_SUCCESS:
        raise CommunicationError(
            'Error creating oauth2: %s' % result.error_description)

    update_oauth2_dict = result.result

    oauth2_service.SaveOauth2Tokens(
        _SYSTEM_LAZADA,
        update_oauth2_dict['access_token'],
        update_oauth2_dict['refresh_token'],
        update_oauth2_dict['expires_in'])


def UpdateLazadaOauth2Tokens(oauth2_service, lazada_client):
    """Updates Oauth2 tokens of the client for Lazada Open API platform."""
    lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(_SYSTEM_LAZADA)

    result = lazada_client._Request(
        '/auth/token/refresh',
        {'refresh_token': lazada_oauth2_dict['refresh_token']},
        domain='https://auth.lazada.com/rest',
        raw=True)
    if result.error_code != _ERROR_SUCCESS:
        raise CommunicationError(
            'Error updating oauth2: %s' % result.error_description)

    update_oauth2_dict = result.result

    oauth2_service.SaveOauth2Tokens(
        _SYSTEM_LAZADA,
        update_oauth2_dict['access_token'],
        update_oauth2_dict['refresh_token'],
        update_oauth2_dict['expires_in'])


def ListDeletedSystemModels(sync_client, system):
    """Returns item models that no longer exist in a system but does so in the DB.
    
    Raises:
      CommunicationError, Unexpected number of external product models.
    """
    if sync_client._System(system) is None:
        raise CommunicationError('%s is not initialized!' % system)

    cached_products = sync_client._GetInventoryItems()
    cached_models = set([p.model for p in cached_products])

    online_models = set(sync_client._CollectExternalProductModels(system))
    if len(online_models) == 0:
        raise CommunicationError('Unexpected number of external product models!')

    return cached_models - online_models


def DoCleanupProcedure(config):
    """Kicks off the process to remove records that no longer exists in OC."""
    opencart_client = OpencartClient(
        domain=config.get('Opencart', 'Domain'),
        username=config.get('Opencart', 'Username'),
        password=config.get('Opencart', 'Password'))
    sync_client = SyncClient(opencart_client=opencart_client)

    with sync_client:
        deleted_models = ListDeletedSystemModels(sync_client, _SYSTEM_OPENCART)
        sync_client._DeleteInventoryItems(deleted_models)


def DoSyncProcedure(config):
    """Kicks off the process to sync product quantities between systems."""
    oauth2_service = Oauth2Service()
    with oauth2_service:
        lazada_oauth2_dict = oauth2_service.GetOauth2Tokens(_SYSTEM_LAZADA)
        lazada_client = LazadaClient(
            domain=config.get('Lazada', 'Domain'),
            app_key=config.get('Lazada', 'AppKey'),
            app_secret=config.get('Lazada', 'AppSecret'),
            access_token=lazada_oauth2_dict['access_token'])
        # CreateLazadaOauth2Tokens(oauth2_service, lazada_client, code='')
        opencart_client = OpencartClient(
            domain=config.get('Opencart', 'Domain'),
            username=config.get('Opencart', 'Username'),
            password=config.get('Opencart', 'Password'))
        shopee_client = ShopeeClient(
            shop_id=config.getint('Shopee', 'ShopID'),
            partner_id=config.getint('Shopee', 'PartnerID'),
            partner_key=config.get('Shopee', 'PartnerKey'))
        sync_client = SyncClient(
            opencart_client=opencart_client, lazada_client=lazada_client,
            shopee_client=shopee_client)

        with sync_client:
            sync_client.Sync()
            UploadFromLazadaToShopee(sync_client, lazada_client, shopee_client)

        UpdateLazadaOauth2Tokens(oauth2_service, lazada_client)


def Config(filename):
    """Reads and returns the ConfigParser instance."""
    config = ConfigParser.RawConfigParser()
    config.read(os.path.join(os.path.abspath(os.path.dirname(__file__)), filename))

    return config


def main(argv):
    logging.basicConfig(level=logging.DEBUG)
    config = Config(_DEFAULT_CONF_PATH)

    if len(argv) == 1:
        DoCleanupProcedure(config)
        DoSyncProcedure(config)
    elif argv[1] == '--sync':
        DoSyncProcedure(config)
    elif argv[1] == '--cleanup':
        DoCleanupProcedure(config)
    elif argv[1] == '--chkconfig':
        logging.info(config.sections())


if __name__ == '__main__':
    main(sys.argv)
